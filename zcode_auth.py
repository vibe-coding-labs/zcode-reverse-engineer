#!/usr/bin/env python3
"""
ZCode Auth — ZCode OAuth 授权流程自动化工具

基于 ZCode v3.0.1 逆向工程，完整实现了 OAuth 授权码模式的全部流程。

## 模式说明

  python zcode_auth.py login       — 完整浏览器登录流程（自动打开浏览器）
  python zcode_auth.py code <URL>  — 手动粘贴回调 URL（推荐用于无桌面环境）
  python zcode_auth.py quota       — 查询配额和套餐信息
  python zcode_auth.py whoami      — 显示当前用户信息
  python zcode_auth.py refresh     — 刷新 Token
  python zcode_auth.py check       — 检查认证状态和可用 API

## 授权流程

  1. 生成授权链接 → 浏览器打开 → 用户登录授权
  2. 捕获回调 URL → 提取 authorization code
  3. 交换 code → OAuth access_token
  4. 交换 access_token → ZCode Business JWT
  5. 获取用户信息
  6. 查询套餐/配额

## 参考

  详细文档: docs/auth-flow.md
  分析报告: ANALYSIS_REPORT.md
"""

import http.server
import json
import os
import secrets
import socket
import string
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import base64
from datetime import datetime, timezone


# ─── OAuth Configuration (from reverse engineering) ────────────────────────

OAUTH_CONFIG = {
    "authorize_url": "https://chat.z.ai/api/oauth/authorize",
    "token_url": "https://zcode.z.ai/api/v1/oauth/token",
    "business_login_url": "https://api.z.ai/api/auth/z/login",
    "userinfo_url": "https://chat.z.ai/api/oauth/userinfo",
    "subscription_list_url": "https://api.z.ai/api/biz/subscription/list",
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


# ─── Helpers ────────────────────────────────────────────────────────────────

def generate_state(length=32):
    """Generate a cryptographically random state string for CSRF protection."""
    return "".join(secrets.choice(string.hexdigits) for _ in range(length))


def decode_jwt_payload(jwt_token):
    """Decode the payload portion of a JWT token without verification."""
    try:
        parts = jwt_token.split(".")
        if len(parts) < 2:
            return {"error": "Not a valid JWT format"}
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def http_request(url, method="GET", body=None, headers=None, timeout=30):
    """Make an HTTP request and return (status_code, response_data_dict_or_string)."""
    if headers is None:
        headers = {}

    effective_headers = {
        "Content-Type": "application/json",
        **headers,
    }

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=effective_headers, method=method)
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


def print_json(data, indent=2):
    """Pretty-print JSON data."""
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=indent, ensure_ascii=False))
    else:
        print(data)


# ─── Credentials Management ────────────────────────────────────────────────

def load_credentials():
    """Load saved credentials from secure JSON file."""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ Failed to read credentials: {e}")
    return None


def save_credentials(creds):
    """Save credentials to JSON file with secure permissions (0600)."""
    fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Credentials saved to {CREDENTIALS_FILE}")


def get_jwt():
    """Helper to quickly get the ZCode JWT from saved credentials."""
    creds = load_credentials()
    if not creds:
        return None
    return creds.get("zcode_jwt_token")


# ─── OAuth Callback Server ────────────────────────────────────────────────

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
        with OAuthCallbackHandler._lock:
            OAuthCallbackHandler._auth_code = None
            OAuthCallbackHandler._auth_state = None


# ─── Token Exchange ────────────────────────────────────────────────────────

def exchange_code_for_tokens(code, redirect_uri, state):
    """Step 3: Exchange authorization code for OAuth access token."""
    body = {
        "provider": PROVIDER,
        "code": code,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    headers = {**ZCODE_HEADERS}
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
        raise RuntimeError(
            f"Token exchange failed: no access_token in response: "
            f"{json.dumps(data, ensure_ascii=False)[:500]}"
        )

    expires_in = data.get("data", {}).get("expires_in") if isinstance(data, dict) else None
    refresh_token = data.get("data", {}).get(PROVIDER, {}).get("refresh_token") if isinstance(data, dict) else None

    expires_at = int(time.time() * 1000) + expires_in * 1000 if expires_in else None

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "expires_in": expires_in,
    }


def exchange_business_token(access_token):
    """Step 4: Exchange OAuth access_token for ZCode Business JWT."""
    body = {"token": access_token}
    headers = {**ZCODE_HEADERS}
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
        raise RuntimeError(
            f"Business login failed: no token in response: "
            f"{json.dumps(data, ensure_ascii=False)[:300]}"
        )

    return jwt


def fetch_user_info(access_token):
    """Step 5: Fetch user information using OAuth access token."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        **ZCODE_HEADERS,
    }
    status, data = http_request(
        OAUTH_CONFIG["userinfo_url"],
        method="GET",
        headers=headers,
    )
    return data if isinstance(data, dict) else {}


# ─── Commands ──────────────────────────────────────────────────────────────

def cmd_login():
    """Full OAuth login flow with local callback server and auto browser open."""
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
        import webbrowser
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
    print(f"  ✓ OAuth access token obtained")

    # 6. Exchange for business JWT
    print(f"  🔄 Exchanging for ZCode Business JWT...")
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

    # 8. Decode JWT and show summary
    jwt_payload = decode_jwt_payload(zcode_jwt)
    user_id = jwt_payload.get("user_id", "?")
    customer_id = jwt_payload.get("customer_id", "?")

    # 9. Save credentials
    creds = {
        "provider": PROVIDER,
        "access_token": token_result["access_token"],
        "zcode_jwt_token": zcode_jwt,
        "refresh_token": token_result.get("refresh_token"),
        "expires_in": token_result.get("expires_in"),
        "expires_at": token_result.get("expires_at"),
        "user_info": user_info,
        "jwt_payload": jwt_payload,
        "created_at": int(time.time() * 1000),
    }
    save_credentials(creds)

    print(f"\n  ✅ Login complete!")
    print(f"     User: {name} (user_id={user_id}, customer_id={customer_id})")
    print(f"\n  Next steps:")
    print(f"    python {os.path.basename(__file__)} quota   — Check free quota / subscription")
    print(f"    python {os.path.basename(__file__)} whoami  — Show user info")
    print(f"    python {os.path.basename(__file__)} check   — Full auth status check")
    print()

    return creds


def cmd_code():
    """Process a callback URL manually (paste from browser after login).

    Use this when running on a server without a desktop browser:
      1. Run:  python zcode_auth.py code "<URL>"
      2. Paste the callback URL you copied from the browser address bar
    """
    if len(sys.argv) < 3:
        print("Usage: python zcode_auth.py code <callback_url>")
        print()
        print("Example: python zcode_auth.py code 'http://127.0.0.1:9999/callback?code=xxx&state=yyy'")
        print()
        print("Steps:")
        print("  1. Generate a login URL (use 'login' mode on a desktop, or construct one manually)")
        print("  2. Open it in a browser and log in")
        print("  3. After authorization, copy the 'connection failed' URL from the address bar")
        print("  4. Paste it here as the argument")
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

    # We need a redirect_uri that matches what was used during authorization.
    # Since the user pasted a callback targeting 127.0.0.1:9999, use that.
    redirect_uri = f"{parsed.scheme}://{parsed.netloc}/callback"

    print(f"  ✓ Extracted code: {code[:30]}...")
    print(f"  ✓ State: {state}")
    print(f"  ✓ Using redirect_uri: {redirect_uri}")

    # Exchange code
    print(f"  🔄 Exchanging code for OAuth access token...")
    try:
        token_result = exchange_code_for_tokens(code, redirect_uri, state or "unknown")
    except RuntimeError as e:
        print(f"  ❌ {e}")
        sys.exit(1)
    print(f"  ✓ OAuth access token obtained")

    # Business JWT
    print(f"  🔄 Exchanging for ZCode Business JWT...")
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

    # Decode JWT
    jwt_payload = decode_jwt_payload(zcode_jwt)
    user_id = jwt_payload.get("user_id", "?")
    customer_id = jwt_payload.get("customer_id", "?")

    creds = {
        "provider": PROVIDER,
        "access_token": token_result["access_token"],
        "zcode_jwt_token": zcode_jwt,
        "refresh_token": token_result.get("refresh_token"),
        "expires_in": token_result.get("expires_in"),
        "expires_at": token_result.get("expires_at"),
        "user_info": user_info,
        "jwt_payload": jwt_payload,
        "created_at": int(time.time() * 1000),
    }
    save_credentials(creds)

    print(f"\n  ✅ Login complete!")
    print(f"     User: {name} (user_id={user_id}, customer_id={customer_id})")
    print(f"\n  Next step:")
    print(f"    python {os.path.basename(__file__)} quota")
    print()


def cmd_refresh():
    """Refresh expired OAuth access token and re-exchange for ZCode JWT."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' or 'code' first.")
        sys.exit(1)

    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        print("❌ No refresh token available. Run 'login' or 'code' again.")
        sys.exit(1)

    print("  🔄 Refreshing OAuth access token...")
    body = {
        "provider": PROVIDER,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    headers = {**ZCODE_HEADERS}
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
    creds["expires_in"] = expires_in
    creds["expires_at"] = expires_at

    save_credentials(creds)
    print("  ✅ Token refreshed and saved.")
    print(f"     New JWT: {new_jwt[:30]}...{new_jwt[-10:]}")


def cmd_quota():
    """Query free tier quota, subscription, and billing info."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' or 'code' first.")
        sys.exit(1)

    jwt = creds.get("zcode_jwt_token", "")
    if not jwt:
        print("❌ No ZCode JWT available. Run 'login' or 'code' first.")
        sys.exit(1)

    auth_header = f"Bearer {jwt}"

    print("=" * 60)
    print("  ZCode Quota & Subscription Check")
    print("=" * 60)
    print(f"  JWT: {jwt[:30]}...{jwt[-10:]}")
    print()

    # 1. Subscription list
    print(f"  [1/3] Coding Plan Subscription...")
    headers = {"Authorization": auth_header, **ZCODE_HEADERS}
    status, sub_data = http_request(
        OAUTH_CONFIG["subscription_list_url"],
        method="GET",
        headers=headers,
    )
    print(f"        HTTP {status}")
    if isinstance(sub_data, dict):
        plans = sub_data.get("data", [])
        if plans:
            print(f"        Active subscriptions: {len(plans)}")
            for p in plans:
                print(f"          - {json.dumps(p, ensure_ascii=False)[:200]}")
        else:
            print(f"        ⚠ No active subscriptions (no Coding Plan)")
            print(f"        {json.dumps(sub_data, ensure_ascii=False)[:200]}")
    else:
        print(f"        {str(sub_data)[:200]}")
    print()

    # 2. Usage quota
    print(f"  [2/3] Usage Quota...")
    status, quota_data = http_request(
        OAUTH_CONFIG["usage_quota_url"],
        method="GET",
        headers=headers,
    )
    print(f"        HTTP {status}")
    if isinstance(quota_data, dict):
        msg = quota_data.get("msg", "")
        if "不存在coding plan" in msg:
            print(f"        ⚠ No Coding Plan quota available")
            print(f"        Start Plan may be available through ZCode desktop app")
        else:
            print_json(quota_data)
    else:
        print(f"        {str(quota_data)[:200]}")
    print()

    # 3. Try Start Plan billing endpoint
    print(f"  [3/3] Start Plan Billing (via zcode.z.ai)...")
    billing_urls = [
        "https://zcode.z.ai/api/v1/zcode-plan/billing/current",
        "https://zcode.z.ai/api/v1/zcode-plan/billing/balance",
    ]
    for url in billing_urls:
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
                print(f"        {url}")
                print(f"        HTTP {r.status}")
                print(f"        {json.dumps(data, ensure_ascii=False)[:500]}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")[:100]
            print(f"        {url}")
            print(f"        HTTP {e.code}: {raw}")
        except Exception as e:
            print(f"        Error: {e}")
    print()

    # Summary
    print(f"  Summary:")
    if isinstance(sub_data, dict) and not sub_data.get("data"):
        print(f"    ❌ Coding Plan: NOT SUBSCRIBED")
    print(f"    💡 To activate Start Plan: Download ZCode desktop app, login, and claim it")
    print()


def cmd_whoami():
    """Show current user info from saved credentials."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' or 'code' first.")
        sys.exit(1)

    print("=" * 60)
    print("  Current User")
    print("=" * 60)

    # User info
    user_info = creds.get("user_info", {})
    if user_info:
        print(f"\n  ── OAuth User Info ──")
        for k, v in user_info.items():
            if isinstance(v, str) and len(v) < 200:
                print(f"    {k}: {v}")
            elif isinstance(v, (int, float, bool)):
                print(f"    {k}: {v}")
            elif v is None:
                print(f"    {k}: null")

    # JWT payload
    jwt_payload = creds.get("jwt_payload")
    if not jwt_payload:
        jwt_payload = decode_jwt_payload(creds.get("zcode_jwt_token", ""))
    if jwt_payload and "error" not in jwt_payload:
        print(f"\n  ── JWT Payload (decoded) ──")
        customer = jwt_payload.get("customer", {})
        print(f"    user_id: {jwt_payload.get('user_id')}")
        print(f"    customer_id: {jwt_payload.get('customer_id')}")
        print(f"    user_type: {jwt_payload.get('user_type')}")
        print(f"    channel: {customer.get('channel')}")
        print(f"    created: {customer.get('createTime')}")
        print(f"    enabled: {customer.get('enableStatus')}")

    # Token info
    print(f"\n  ── Token Info ──")
    print(f"    Provider: {creds.get('provider', '?')}")
    expires_at = creds.get("expires_at")
    if expires_at:
        dt = datetime.fromtimestamp(expires_at / 1000, tz=timezone.utc)
        remaining = max(0, expires_at - time.time() * 1000)
        print(f"    Expires: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')} ({remaining // 60000} min remaining)")
    else:
        print(f"    Expires: unknown")
    print(f"    Has refresh_token: {'yes' if creds.get('refresh_token') else 'no'}")
    print(f"    JWT: {creds.get('zcode_jwt_token', '')[:30]}...{creds.get('zcode_jwt_token', '')[-10:]}")
    print()


def cmd_check():
    """Comprehensive auth status check — test all discovered API endpoints."""
    creds = load_credentials()
    if not creds:
        print("❌ No credentials found. Run 'login' or 'code' first.")
        sys.exit(1)

    jwt = creds.get("zcode_jwt_token", "")
    access_token = creds.get("access_token", "")
    if not jwt:
        print("❌ No ZCode JWT available.")
        sys.exit(1)

    print("=" * 60)
    print("  ZCode Connectivity Check")
    print("=" * 60)
    print()

    check_cases = [
        # (Name, URL, Method, Headers, Body)
        ("OAuth User Info",
         "https://chat.z.ai/api/oauth/userinfo", "GET",
         {"Authorization": f"Bearer {access_token}"}, None),
        ("Subscription List",
         "https://api.z.ai/api/biz/subscription/list", "GET",
         {"Authorization": f"Bearer {jwt}"}, None),
        ("Usage Quota",
         "https://api.z.ai/api/monitor/usage/quota/limit", "GET",
         {"Authorization": f"Bearer {jwt}"}, None),
        ("AI API (Anthropic format)",
         "https://api.z.ai/api/anthropic/v1/messages", "POST",
         {"x-api-key": jwt, "anthropic-version": "2023-06-01"},
         {"model": "glm-5.1", "max_tokens": 10, "stream": False,
          "messages": [{"role": "user", "content": "hi"}]}),
    ]

    for name, url, method, extra_headers, body in check_cases:
        headers = {"Content-Type": "application/json", **ZCODE_HEADERS, **extra_headers}
        print(f"  [{name}]")
        print(f"    {method} {url}")
        try:
            status, data = http_request(url, method=method, body=body, headers=headers, timeout=15)
            print(f"    HTTP {status}")
            if isinstance(data, dict):
                if data.get("success") is True or data.get("code") in (0, 200):
                    print(f"    ✅ OK")
                elif "error" in data or "msg" in data:
                    msg = data.get("msg") or data.get("error", {}).get("message", "")
                    if msg:
                        print(f"    ⚠ {msg[:100]}")
                    else:
                        print(f"    ⚠ {json.dumps(data, ensure_ascii=False)[:100]}")
                else:
                    print(f"    Response: {json.dumps(data, ensure_ascii=False)[:200]}")
            else:
                print(f"    Response: {str(data)[:200]}")
        except Exception as e:
            print(f"    ❌ Error: {e}")
        print()

    # Summary
    print(f"  ── Auth Status ──")
    print(f"  OAuth Access Token: {'✅ valid' if access_token else '❌ missing'}")
    print(f"  ZCode JWT:         {'✅ valid' if jwt else '❌ missing'}")
    print(f"  User:              {creds.get('user_info', {}).get('name', '?')}")
    print()


def cmd_guest():
    """Get a guest Z.AI access token (for research).

    Note: Guest tokens get 401 from ZCode's API and cannot access
    Start Plan or Coding Plan features. Real authentication required.
    """
    print("=" * 60)
    print("  Z.AI Guest Login (Research Only)")
    print("=" * 60)

    status, data = http_request("https://chat.z.ai/api/v1/auths/", method="GET")

    if not isinstance(data, dict):
        print(f"  ❌ Failed to get guest session: {data}")
        sys.exit(1)

    print(f"  ✓ Guest session created")
    print(f"  ID: {data.get('id', '?')}")
    print(f"  Name: {data.get('name', '?')}")
    print(f"  Token: {str(data.get('token', ''))[:40]}...")
    print()
    print(f"  ⚠ Note: Guest tokens get 401 from ZCode API.")
    print(f"  Real login required for Start Plan access.")
    print()


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    commands = {
        "login": cmd_login,
        "code": cmd_code,
        "guest": cmd_guest,
        "refresh": cmd_refresh,
        "quota": cmd_quota,
        "whoami": cmd_whoami,
        "check": cmd_check,
    }

    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python zcode_auth.py {login|code|guest|refresh|quota|whoami|check}")
        print()
        print("  login   — Full browser-based OAuth login")
        print("  code    — Process a callback URL (paste from browser)")
        print("  guest   — Get a guest token (research only)")
        print("  refresh — Refresh expired tokens")
        print("  quota   — Check subscription and free quota")
        print("  whoami  — Show current user and JWT info")
        print("  check   — Test all API endpoints")
        sys.exit(1)


if __name__ == "__main__":
    main()