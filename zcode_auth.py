#!/usr/bin/env python3
"""
ZCode Auth — Python implementation of ZCode OAuth authorization flow.

Based on reverse engineering of ZCode v3.0.1:
  - OAuth: chat.z.ai/oauth/authorize → zcode.z.ai/api/v1/oauth/token → api.z.ai/api/auth/z/login
  - No PKCE, no client_secret required

Additional modes:
  python zcode_auth.py guest     — Get guest token (no phone needed, but limited access)
  python zcode_auth.py code <URL> — Process a callback URL manually (copy-paste from browser)
"""

import http.server
import json
import os
import random
import socket
import string
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import base64
from datetime import datetime, timezone

# ─── Configuration (from reverse engineering) ───────────────────────────

OAUTH_CONFIG = {
    "authorize_url": "https://chat.z.ai/api/oauth/authorize",
    "token_url": "https://zcode.z.ai/api/v1/oauth/token",
    "business_login_url": "https://api.z.ai/api/auth/z/login",
    "userinfo_url": "https://chat.z.ai/api/oauth/userinfo",
    "usage_quota_url": "https://api.z.ai/api/monitor/usage/quota/limit",
    "app_id": "client_P8X5CMWmlaRO9gyO-KSqtg",
}

PROVIDER = "zai"

ZCODE_HEADERS = {
    "User-Agent": "ZCode/unknown",
    "HTTP-Referer": "https://zcode.z.ai",
    "X-Title": "Z Code@electron",
}

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".zcode_credentials.json")


# ─── Helpers ─────────────────────────────────────────────────────────────

def generate_state(length=32):
    return "".join(random.choices(string.hexdigits, k=length))


def http_request(url, method="GET", body=None, headers=None, timeout=30):
    """Make an HTTP request and return (status_code, response_data_dict_or_string)."""
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except urllib.error.URLError as e:
        print(f"  ⚠ Network error: {e.reason}")
        return 0, {"error": str(e.reason)}


# ─── Credentials Management ──────────────────────────────────────────────

def load_credentials():
    """Load saved credentials from JSON file."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Failed to read credentials: {e}")
    return None


def save_credentials(creds):
    """Save credentials to JSON file."""
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Credentials saved to {CREDENTIALS_FILE}")


# ─── OAuth Callback Server ──────────────────────────────────────────────

class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP server that captures the OAuth callback."""

    _lock = threading.Lock()
    _auth_code = None
    _auth_state = None
    _server_instance = None

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            code = (params.get("code") or params.get("authCode") or [None])[0]
            returned_state = (params.get("state") or [None])[0]
            error = (params.get("error") or [None])[0]

            if error:
                self._send_html(400, f"<h2>Login Failed</h2><p>Error: {error}</p>")
                with self._lock:
                    if self._auth_code is None:
                        self._auth_code = f"ERROR:{error}"
                        self._server_instance.shutdown_event.set()
                return

            if not code:
                self._send_html(400, "<h2>Login Failed</h2><p>No authorization code received.</p>")
                return

            if returned_state and returned_state != self._auth_state:
                self._send_html(400, "<h2>State Mismatch</h2><p>Security check failed.</p>")
                return

            with self._lock:
                self._auth_code = code
                if self._server_instance:
                    self._server_instance.shutdown_event.set()

            self._send_html(200, """
            <!DOCTYPE html>
            <html><body style="display:flex;align-items:center;justify-content:center;height:100vh;
            font-family:sans-serif;background:#0f0f0f;color:#fff">
            <div style="text-align:center">
              <h1>✓ Login Successful!</h1>
              <p>You can close this window and return to the terminal.</p>
            </div>
            </body></html>
            """)
        elif parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self._send_html(404, "<h1>Not Found</h1>")

    def _send_html(self, status, html):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


class OAuthCallbackServer:
    """Wrapper around http.server that runs in a background thread."""

    def __init__(self, state):
        self.state = state
        self.shutdown_event = threading.Event()
        self._server = None
        self._thread = None
        self.port = self._find_free_port()

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def start(self):
        """Start the server in a background thread."""

        class HandlerFactory:
            def __init__(self, outer):
                self.outer = outer

            def __call__(self, *args, **kwargs):
                handler = OAuthCallbackHandler(*args, **kwargs)
                handler._auth_state = outer.state
                handler._server_instance = outer
                return handler

        outer = self
        self._server = http.server.HTTPServer(
            ("127.0.0.1", self.port), HandlerFactory(self)
        )
        self._server.timeout = 0.5

        def serve():
            while not self.shutdown_event.is_set():
                self._server.handle_request()

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()
        return self.port

    def wait_for_code(self, timeout=300):
        """Block until auth code received or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with OAuthCallbackHandler._lock:
                if OAuthCallbackHandler._auth_code is not None:
                    return OAuthCallbackHandler._auth_code
            time.sleep(0.1)
        return None

    def stop(self):
        self.shutdown_event.set()
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=2)
        # Reset for next use
        with OAuthCallbackHandler._lock:
            OAuthCallbackHandler._auth_code = None
            OAuthCallbackHandler._auth_state = None


# ─── Token Exchange ─────────────────────────────────────────────────────

def exchange_code_for_tokens(code, redirect_uri, state):
    """Step 3: Exchange authorization code for access token."""
    body = {
        "provider": PROVIDER,
        "code": code,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    headers = {
        "Content-Type": "application/json",
        **ZCODE_HEADERS,
    }
    status, data = http_request(
        OAUTH_CONFIG["token_url"],
        method="POST",
        body=body,
        headers=headers,
    )

    # Check business envelope
    code_val = data.get("code") if isinstance(data, dict) else None
    if code_val is not None and code_val not in (0, 200):
        raise RuntimeError(f"Token exchange failed: code={code_val} msg={data.get('msg', '')}")

    # Extract access token
    access_token = None
    if isinstance(data, dict):
        access_token = data.get("data", {}).get(PROVIDER, {}).get("access_token")

    if not access_token:
        raise RuntimeError(f"Token exchange failed: no access_token in response: {json.dumps(data, ensure_ascii=False)[:500]}")

    expires_in = data.get("data", {}).get("expires_in") if isinstance(data, dict) else None
    refresh_token = data.get("data", {}).get(PROVIDER, {}).get("refresh_token") if isinstance(data, dict) else None

    expires_at = int(time.time() * 1000) + expires_in * 1000 if expires_in else None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }


def exchange_business_token(access_token):
    """Step 4: Exchange access_token for ZCode JWT (business token)."""
    body = {"token": access_token}
    headers = {
        "Content-Type": "application/json",
        **ZCODE_HEADERS,
    }
    status, data = http_request(
        OAUTH_CONFIG["business_login_url"],
        method="POST",
        body=body,
        headers=headers,
    )

    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(f"Business login failed: {json.dumps(data, ensure_ascii=False)[:300]}")

    jwt = None
    if isinstance(data, dict):
        jwt = data.get("data", {}).get("access_token") or data.get("data", {}).get("accessToken")

    if not jwt:
        raise RuntimeError(f"Business login failed: no token in response: {json.dumps(data, ensure_ascii=False)[:300]}")

    return jwt


def fetch_user_info(access_token):
    """Step 5 (optional): Fetch user information."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        **ZCODE_HEADERS,
    }
    status, data = http_request(
        OAUTH_CONFIG["userinfo_url"],
        method="GET",
        headers=headers,
    )
    return data if isinstance(data, dict) else {}


# ─── Commands ───────────────────────────────────────────────────────────

def cmd_login():
    """Full OAuth login flow."""
    state = generate_state()

    print("=" * 60)
    print("  ZCode OAuth Login")
    print("=" * 60)

    # 1. Start callback server
    server = OAuthCallbackServer(state)
    port = server.start()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    print(f"\n  Local callback server started on port {port}")

    # 2. Build authorize URL
    params = {
        "response_type": "code",
        "client_id": OAUTH_CONFIG["app_id"],
        "redirect_uri": redirect_uri,
        "state": state,
    }
    auth_url = f"{OAUTH_CONFIG['authorize_url']}?{urllib.parse.urlencode(params)}"

    # 3. Try to open browser
    print(f"\n  🔐 Opening browser for Z.AI login...")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print(f"\n  If browser doesn't open, visit this URL:")
    print(f"  {auth_url}")
    print(f"\n  ⏳ Waiting for OAuth callback... (timeout: 5 min)")

    # 4. Wait for callback
    code = server.wait_for_code(timeout=300)
    server.stop()

    if not code:
        print("\n  ❌ Login timed out after 5 minutes.")
        sys.exit(1)

    if code.startswith("ERROR:"):
        print(f"\n  ❌ Login failed: {code[6:]}")
        sys.exit(1)

    print(f"  ✓ Authorization code received!")

    # 5. Exchange code for tokens
    print(f"  🔄 Exchanging code for tokens...")
    try:
        token_result = exchange_code_for_tokens(code, redirect_uri, state)
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    print(f"  ✓ Access token obtained")

    # 6. Exchange for business JWT
    print(f"  🔄 Exchanging for ZCode JWT...")
    try:
        zcode_jwt = exchange_business_token(token_result["access_token"])
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    print(f"  ✓ ZCode JWT obtained")

    # 7. Fetch user info (optional)
    user_info = {}
    try:
        user_info = fetch_user_info(token_result["access_token"])
        name = (
            user_info.get("name")
            or user_info.get("preferred_username")
            or user_info.get("email")
            or user_info.get("id")
            or "Unknown"
        )
        print(f"  ✓ Logged in as: {name}")
    except Exception:
        print(f"  ⚠ Could not fetch user info")

    # 8. Save credentials
    creds = {
        "provider": PROVIDER,
        "access_token": token_result["access_token"],
        "zcode_jwt_token": zcode_jwt,
        "refresh_token": token_result.get("refresh_token"),
        "expires_at": token_result.get("expires_at"),
        "user_info": user_info,
        "created_at": int(time.time() * 1000),
    }
    save_credentials(creds)

    print(f"\n  ✅ Login complete!")
    print(f"\n  Next steps:")
    print(f"    python {os.path.basename(__file__)} quota   — Check free quota")
    print(f"    python {os.path.basename(__file__)} whoami  — Show user info")
    print()

    return creds


def cmd_refresh():
    """Refresh expired tokens."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' first.")
        sys.exit(1)

    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        print("❌ No refresh token available. Run 'login' again.")
        sys.exit(1)

    print("  🔄 Refreshing access token...")
    body = {
        "provider": PROVIDER,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    headers = {
        "Content-Type": "application/json",
        **ZCODE_HEADERS,
    }
    status, data = http_request(
        OAUTH_CONFIG["token_url"],
        method="POST",
        body=body,
        headers=headers,
    )

    access_token = None
    if isinstance(data, dict):
        access_token = data.get("data", {}).get(PROVIDER, {}).get("access_token")

    if not access_token:
        print(f"  ❌ Refresh failed: {json.dumps(data, ensure_ascii=False)[:300]}")
        sys.exit(1)

    print("  ✓ Token refreshed")
    print("  🔄 Re-exchanging for ZCode JWT...")

    try:
        new_jwt = exchange_business_token(access_token)
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    expires_in = data.get("data", {}).get("expires_in") if isinstance(data, dict) else None
    expires_at = int(time.time() * 1000) + expires_in * 1000 if expires_in else None

    creds["access_token"] = access_token
    creds["zcode_jwt_token"] = new_jwt
    creds["expires_at"] = expires_at

    save_credentials(creds)
    print("  ✅ Token refreshed and saved.")


def cmd_quota():
    """Query free tier quota / billing info."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' first.")
        sys.exit(1)

    jwt = creds.get("zcode_jwt_token", "")
    if not jwt:
        print("❌ No ZCode JWT token available. Run 'login' first.")
        sys.exit(1)

    auth_header = f"Bearer {jwt}"

    print("=" * 60)
    print("  ZCode Quota & Usage")
    print("=" * 60)
    print(f"\n  JWT: {jwt[:30]}...{jwt[-10:]}")
    print()

    # 1. Query usage quota limit
    print("  📊 Querying usage quota/limit...")
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        **ZCODE_HEADERS,
    }
    status, quota_data = http_request(
        OAUTH_CONFIG["usage_quota_url"],
        method="GET",
        headers=headers,
    )
    print(f"  Status: HTTP {status}")
    if isinstance(quota_data, dict):
        print(f"  Response: {json.dumps(quota_data, indent=2, ensure_ascii=False)[:2000]}")
    else:
        print(f"  Response: {str(quota_data)[:500]}")
    print()

    # 2. Try billing/current for Start Plan
    print("  📊 Querying billing/current (Start Plan)...")
    # The billing URL comes from env var; try common patterns
    billing_urls = [
        "https://api.z.ai/api/billing/current",
        "https://api.z.ai/api/biz/billing/current",
    ]
    for url in billing_urls:
        print(f"  Trying: {url}")
        status, bill_data = http_request(url, method="GET", headers=headers)
        if isinstance(bill_data, dict) and bill_data.get("code") in (0, None):
            print(f"  Status: HTTP {status}")
            print(f"  Response: {json.dumps(bill_data, indent=2, ensure_ascii=False)[:2000]}")
            break
        else:
            print(f"  Status: HTTP {status} — not found or unauthorized")
    print()

    # 3. Try subscription list
    print("  📊 Querying subscription list (Coding Plan)...")
    status, sub_data = http_request(
        "https://api.z.ai/api/biz/subscription/list",
        method="GET",
        headers=headers,
    )
    print(f"  Status: HTTP {status}")
    if isinstance(sub_data, dict):
        print(f"  Response: {json.dumps(sub_data, indent=2, ensure_ascii=False)[:2000]}")

    print()
    print("  💡 Tip: To see exact free quota numbers, check the 'plans' field")
    print("    in billing/current response for total_units and available_units.")
    print()


def cmd_code():
    """Process a callback URL manually (paste from browser after login)."""
    if len(sys.argv) < 3:
        print("Usage: python zcode_auth.py code <callback_url>")
        print("Example: python zcode_auth.py code 'http://127.0.0.1:9999/callback?code=xxx&state=yyy'")
        sys.exit(1)

    callback_url = sys.argv[2]
    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)

    code = (params.get("code") or [None])[0]
    state = (params.get("state") or [None])[0]
    error = (params.get("error") or [None])[0]

    if error:
        print(f"  ❌ OAuth error: {error}")
        sys.exit(1)
    if not code:
        print("  ❌ No authorization code found in the URL.")
        print(f"  Parsed params: {params}")
        sys.exit(1)

    print(f"  ✓ Extracted code: {code[:30]}...")
    print(f"  ✓ State: {state}")

    # Exchange code
    redirect_uri = f"http://127.0.0.1:9999/callback"
    print(f"  🔄 Exchanging code for tokens...")
    try:
        token_result = exchange_code_for_tokens(code, redirect_uri, state or "unknown")
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    print(f"  ✓ Access token obtained")

    # Business JWT
    print(f"  🔄 Exchanging for ZCode JWT...")
    try:
        zcode_jwt = exchange_business_token(token_result["access_token"])
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    print(f"  ✓ ZCode JWT obtained")

    # User info
    user_info = {}
    try:
        user_info = fetch_user_info(token_result["access_token"])
        name = (
            user_info.get("name")
            or user_info.get("preferred_username")
            or user_info.get("email")
            or user_info.get("id")
            or "Unknown"
        )
        print(f"  ✓ Logged in as: {name}")
    except Exception:
        print(f"  ⚠ Could not fetch user info")

    creds = {
        "provider": PROVIDER,
        "access_token": token_result["access_token"],
        "zcode_jwt_token": zcode_jwt,
        "refresh_token": token_result.get("refresh_token"),
        "expires_at": token_result.get("expires_at"),
        "user_info": user_info,
        "created_at": int(time.time() * 1000),
    }
    save_credentials(creds)

    # Decode JWT
    print(f"\n=== JWT Payload ===")
    try:
        payload_b64 = zcode_jwt.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(padded).decode("utf-8"))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"  (could not decode: {e})")

    print(f"\n  ✅ Login complete ({creds.get('user_info', {}).get('name', '?')})!")
    print(f"  JWT expires in: {token_result.get('expires_at', 'unknown')}")
    print(f"\n  Next: python {os.path.basename(__file__)} quota")


def cmd_guest():
    """Get a guest Z.AI access_token (no phone number needed).
    Note: guest tokens get 401 from ZCode's API — real login required for Start Plan."""
    print("=" * 60)
    print("  Z.AI Guest Login")
    print("=" * 60)

    status, data = http_request("https://chat.z.ai/api/v1/auths/", method="GET")

    if not isinstance(data, dict):
        print(f"  ❌ Failed to get guest session: {data}")
        sys.exit(1)

    print(f"  ✓ Guest session created")
    print(f"\n  Note: Guest tokens get 401 from ZCode API.")
    print(f"  You need real phone login for Start Plan access.")
    """Show current user info from saved credentials."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' first.")
        sys.exit(1)

    print("=" * 60)
    print("  Current User")
    print("=" * 60)

    user_info = creds.get("user_info", {})
    if user_info:
        for k, v in user_info.items():
            if isinstance(v, str) and len(v) < 200:
                print(f"  {k}: {v}")
            elif isinstance(v, (int, float, bool)):
                print(f"  {k}: {v}")

    print()
    print(f"  Provider: {creds.get('provider', '?')}")
    print(f"  Token expires: ", end="")
    expires_at = creds.get("expires_at")
    if expires_at:
        dt = datetime.fromtimestamp(expires_at / 1000, tz=timezone.utc)
        remaining = max(0, expires_at - time.time() * 1000)
        print(f"{dt.strftime('%Y-%m-%d %H:%M:%S UTC')} ({remaining // 60000} min remaining)")
    else:
        print("unknown")

    print(f"  Has refresh token: {'yes' if creds.get('refresh_token') else 'no'}")
    print(f"  JWT: {creds.get('zcode_jwt_token', '')[:30]}...{creds.get('zcode_jwt_token', '')[-10:]}")
    print()


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "login":
        cmd_login()
    elif command == "code":
        cmd_code()
    elif command == "guest":
        cmd_guest()
    elif command == "refresh":
        cmd_refresh()
    elif command == "quota":
        cmd_quota()
    elif command == "whoami":
        cmd_whoami()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python zcode_auth.py {login|code|guest|refresh|quota|whoami}")
        sys.exit(1)


if __name__ == "__main__":
    main()