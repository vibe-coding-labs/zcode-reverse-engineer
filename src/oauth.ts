/**
 * OAuth login flow for ZCode.
 * Based on reverse-engineered protocol from ZCode v3.0.1:
 *
 * 1. Open browser to https://chat.z.ai/api/oauth/authorize
 * 2. Start local HTTP server to receive OAuth callback
 * 3. Exchange code for tokens at https://zcode.z.ai/api/v1/oauth/token
 * 4. Exchange access_token for business token at https://api.z.ai/api/auth/z/login
 * 5. Store zcodejwttoken for future API calls
 */

import http from "node:http";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import axios from "axios";

import type { ZCodeTokenResponse, ZCodeBusinessLoginResponse, ZCodeCredentials } from "./types.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CRED_PATH = path.resolve(__dirname, "..", "..", ".zcode-credentials.json");

// === OAuth Config (from reverse engineering) ===
const OAUTH_CONFIG = {
  authorizeUrl: "https://chat.z.ai/api/oauth/authorize",
  tokenUrl: "https://zcode.z.ai/api/v1/oauth/token",
  businessLoginUrl: "https://api.z.ai/api/auth/z/login",
  userinfoUrl: "https://chat.z.ai/api/oauth/userinfo",
  appId: "client_P8X5CMWmlaRO9gyO-KSqtg",
};
const PROVIDER = "zai";

// Common headers used by ZCode (from reverse engineering)
const ZCODE_HEADERS = {
  "User-Agent": "ZCode/unknown",
  "HTTP-Referer": "https://zcode.z.ai",
  "X-Title": "Z Code@electron",
};

/**
 * Load stored credentials from disk
 */
export function loadCredentials(): ZCodeCredentials | null {
  try {
    if (fs.existsSync(CRED_PATH)) {
      return JSON.parse(fs.readFileSync(CRED_PATH, "utf-8"));
    }
  } catch { /* ignore */ }
  return null;
}

/**
 * Save credentials to disk
 */
export function saveCredentials(creds: ZCodeCredentials): void {
  // Secure write: 0600 permissions (owner read/write only)
  const tmp = CRED_PATH + ".tmp." + process.pid;
  fs.writeFileSync(tmp, JSON.stringify(creds, null, 2), "utf-8");
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, CRED_PATH);
  console.log(`✓ Credentials saved to ${CRED_PATH}`);
}

/**
 * Run the full OAuth login flow
 */
export async function login(): Promise<ZCodeCredentials> {
  // 1. Generate state & start local server for callback
  const state = randomBytes(16).toString("hex");
  const creds = await startCallbackServer(state);

  // 2. Open browser for OAuth authorization
  const params = new URLSearchParams({
    response_type: "code",
    client_id: OAUTH_CONFIG.appId,
    redirect_uri: creds.redirectUri,
    state: state,
    scope: "openid profile email",
  });
  const authUrl = `${OAUTH_CONFIG.authorizeUrl}?${params.toString()}`;

  console.log("\n🔐 Opening browser for Z.AI login...");
  console.log(`   URL: ${authUrl}\n`);

  // Try to open browser; if not possible, tell user to open it manually
  try {
    const { default: open } = await import("open");
    await open(authUrl);
  } catch {
    console.log("⚠  Could not open browser automatically. Please open this URL manually:");
    console.log(`   ${authUrl}\n`);
  }

  // 3. Wait for callback (server handles code exchange internally)
  console.log("⏳ Waiting for OAuth callback...");
  const result = await creds.promise;

  // 4. Exchange access_token for business token
  console.log("\n🔄 Exchanging access_token for ZCode JWT...");
  const businessToken = await exchangeBusinessToken(result.accessToken);
  console.log("✓ Business token obtained");

  // 5. Fetch user info
  let userInfo;
  try {
    const resp = await axios.get(OAUTH_CONFIG.userinfoUrl, {
      headers: {
        Authorization: `Bearer ${result.accessToken}`,
        "Content-Type": "application/json",
        ...ZCODE_HEADERS,
      },
    });
    userInfo = resp.data;
    console.log(`✓ Logged in as: ${userInfo.name || userInfo.preferred_username || userInfo.id}`);
  } catch (e) {
    console.log("⚠  Could not fetch user info (non-critical)");
  }

  const credentials: ZCodeCredentials = {
    provider: PROVIDER,
    accessToken: result.accessToken,
    zcodeJwtToken: businessToken,
    refreshToken: result.refreshToken,
    expiresAt: result.expiresAt,
    userInfo,
  };

  saveCredentials(credentials);
  return credentials;
}

/**
 * Start a local HTTP server to receive the OAuth redirect callback.
 * The callback handler will exchange the code for tokens.
 */
function startCallbackServer(state: string): Promise<{
  promise: Promise<{ accessToken: string; refreshToken?: string; expiresAt?: number }>;
  redirectUri: string;
}> {
  return new Promise((resolve) => {
    const server = http.createServer();
    const port = 0; // random port
    server.listen(port, "127.0.0.1", () => {
      const addr = server.address()!;
      const actualPort = typeof addr === "object" ? addr.port : 8080;
      const redirectUri = `http://127.0.0.1:${actualPort}/callback`;

      const promise = new Promise<{ accessToken: string; refreshToken?: string; expiresAt?: number }>(
        async (resolvePromise, rejectPromise) => {
          server.on("request", async (req, res) => {
            const url = new URL(req.url!, `http://127.0.0.1:${actualPort}`);

            // Serve a simple "close this window" page for the redirect
            if (url.pathname === "/callback") {
              const code = url.searchParams.get("code") || url.searchParams.get("authCode");
              const returnedState = url.searchParams.get("state");

              if (!code) {
                const errMsg = url.searchParams.get("error") || "No code in callback";
                res.writeHead(400, { "Content-Type": "text/html" });
                res.end(`<h1>Login Failed: ${errMsg}</h1><p>You can close this window.</p>`);
                rejectPromise(new Error(`OAuth callback error: ${errMsg}`));
                return;
              }

              if (returnedState !== state) {
                res.writeHead(400, { "Content-Type": "text/html" });
                res.end("<h1>State mismatch — login failed</h1><p>You can close this window.</p>");
                rejectPromise(new Error("OAuth state mismatch"));
                return;
              }

              res.writeHead(200, { "Content-Type": "text/html" });
              res.end(`
                <!DOCTYPE html>
                <html><body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#0f0f0f;color:#fff">
                <div style="text-align:center">
                  <h1>✅ Login successful!</h1>
                  <p>You can close this window and return to the terminal.</p>
                </div>
                </body></html>
              `);

              try {
                console.log("📞 Callback received! Exchanging code for tokens...");
                const tokens = await exchangeCodeForTokens(code, redirectUri, state);
                resolvePromise(tokens);
              } catch (e) {
                rejectPromise(e);
              } finally {
                server.close();
              }
            } else if (url.pathname === "/favicon.ico") {
              res.writeHead(204);
              res.end();
            } else {
              res.writeHead(404);
              res.end();
            }
          });

          // Timeout after 5 minutes
          setTimeout(() => {
            server.close();
            rejectPromise(new Error("OAuth login timed out after 5 minutes"));
          }, 5 * 60 * 1000);
        }
      );

      resolve({ promise, redirectUri });
    });
  });
}

/**
 * Exchange OAuth authorization code for access token
 */
async function exchangeCodeForTokens(
  code: string,
  redirectUri: string,
  state: string
): Promise<{ accessToken: string; refreshToken?: string; expiresAt?: number }> {
  const response = await axios.post<ZCodeTokenResponse>(
    OAUTH_CONFIG.tokenUrl,
    {
      provider: PROVIDER,
      code: code,
      redirect_uri: redirectUri,
      state: state,
    },
    {
      headers: {
        "Content-Type": "application/json",
        ...ZCODE_HEADERS,
      },
    }
  );

  const data = response.data;

  if (data.code !== undefined && data.code !== 0 && data.code !== 200) {
    throw new Error(`Token exchange failed: code=${data.code} msg=${data.msg}`);
  }

  const accessToken = data.data?.zai?.access_token;
  if (!accessToken) {
    throw new Error(`Token exchange failed: missing data.zai.access_token, response: ${JSON.stringify(data)}`);
  }

  const expiresAt = data.data?.expires_in
    ? Date.now() + data.data.expires_in * 1000
    : undefined;

  return {
    accessToken,
    refreshToken: data.data?.zai?.refresh_token,
    expiresAt,
  };
}

/**
 * Exchange Z.AI access_token for ZCode JWT (business token)
 */
async function exchangeBusinessToken(accessToken: string): Promise<string> {
  const response = await axios.post<ZCodeBusinessLoginResponse>(
    OAUTH_CONFIG.businessLoginUrl,
    { token: accessToken },
    {
      headers: {
        "Content-Type": "application/json",
        ...ZCODE_HEADERS,
      },
    }
  );

  const data = response.data;
  if (data.success === false) {
    throw new Error(`Business login failed: ${JSON.stringify(data)}`);
  }

  const jwt = data.data?.access_token || data.data?.accessToken;
  if (!jwt) {
    throw new Error(`Business login failed: no token in response`);
  }

  return jwt;
}

/**
 * Refresh the access token using the refresh token
 */
export async function refreshAccessToken(creds: ZCodeCredentials): Promise<ZCodeCredentials> {
  if (!creds.refreshToken) {
    throw new Error("No refresh token available");
  }

  const response = await axios.post<ZCodeTokenResponse>(
    OAUTH_CONFIG.tokenUrl,
    {
      provider: PROVIDER,
      refresh_token: creds.refreshToken,
      grant_type: "refresh_token",
    },
    {
      headers: {
        "Content-Type": "application/json",
        ...ZCODE_HEADERS,
      },
    }
  );

  const data = response.data;
  const accessToken = data.data?.zai?.access_token;
  if (!accessToken) {
    throw new Error(`Token refresh failed: ${JSON.stringify(data)}`);
  }

  const jwt = await exchangeBusinessToken(accessToken);

  const updated: ZCodeCredentials = {
    ...creds,
    accessToken,
    zcodeJwtToken: jwt,
    expiresAt: data.data?.expires_in ? Date.now() + data.data.expires_in * 1000 : undefined,
  };

  saveCredentials(updated);
  return updated;
}
