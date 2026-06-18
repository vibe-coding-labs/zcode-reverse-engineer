/**
 * Reverse proxy server for ZCode AI API.
 *
 * Listens for Anthropic Messages API requests and forwards them to ZCode's backend
 * (https://api.z.ai/api/anthropic/v1/messages), adding the ZCode JWT auth header.
 *
 * This allows any tool that supports a custom Anthropic API endpoint
 * (like Claude Code with ANTHROPIC_BASE_URL) to use ZCode's AI capabilities.
 */

import express from "express";
import { createProxyMiddleware } from "./proxy-middleware.js";
import type { ZCodeCredentials } from "./types.js";

const PROXY_TARGET = "https://api.z.ai/api/anthropic/v1/messages";
const ZCODE_HEADERS = {
  "User-Agent": "ZCode/unknown",
  "HTTP-Referer": "https://zcode.z.ai",
  "X-Title": "Z Code@electron",
  "anthropic-version": "2023-06-01",
};

/**
 * Start the reverse proxy server
 */
export async function startProxyServer(
  creds: ZCodeCredentials,
  port: number,
  host: string
): Promise<void> {
  const app = express();

  // Health check
  app.get("/health", (_req, res) => {
    res.json({ status: "ok", target: PROXY_TARGET });
  });

  // Proxy endpoints
  app.post("/v1/messages", async (req, res) => {
    const proxy = createProxyMiddleware(PROXY_TARGET, {
      headers: {
        "x-api-key": creds.zcodeJwtToken,
        ...ZCODE_HEADERS,
      },
    });
    proxy(req, res);
  });

  // Support both /api/anthropic/v1/messages and /v1/messages
  app.post("/api/anthropic/v1/messages", async (req, res) => {
    const proxy = createProxyMiddleware(PROXY_TARGET, {
      headers: {
        "x-api-key": creds.zcodeJwtToken,
        ...ZCODE_HEADERS,
      },
    });
    proxy(req, res);
  });

  // Model listing (returns the models we know about)
  app.get("/v1/models", (_req, res) => {
    res.json({
      object: "list",
      data: [
        { id: "claude-sonnet-4-6", object: "model", created: Date.now(), owned_by: "zcode" },
        { id: "claude-opus-4-6", object: "model", created: Date.now(), owned_by: "zcode" },
        { id: "claude-haiku-4-5", object: "model", created: Date.now(), owned_by: "zcode" },
      ],
    });
  });

  const server = app.listen(port, host, () => {
    console.log(`\n🔁 ZCode Reverse Proxy running on http://${host}:${port}`);
    console.log(`   Target: ${PROXY_TARGET}`);
    console.log(`   JWT: ${creds.zcodeJwtToken.slice(0, 20)}...${creds.zcodeJwtToken.slice(-10)}`);
    console.log(`\n   Usage examples:\n`);
    console.log(`   ANTHROPIC_BASE_URL=http://${host}:${port} claude`);
    console.log(`   curl http://${host}:${port}/v1/messages -H "Content-Type: application/json" -d '{...}'`);
    console.log();
  });

  // Graceful shutdown
  const shutdown = async () => {
    console.log("\nShutting down...");
    server.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}
