/**
 * Minimal HTTP reverse proxy middleware for Express.
 * Forwards requests to a target URL using Node's built-in http/https modules,
 * preserving the request body and streaming the response back.
 */

import type { Request, Response } from "express";
import https from "node:https";
import http from "node:http";

export interface ProxyOptions {
  headers?: Record<string, string>;
}

/**
 * Create Express middleware that proxies requests to a target URL
 */
export function createProxyMiddleware(
  targetUrl: string,
  opts: ProxyOptions = {}
) {
  const parsedTarget = new URL(targetUrl);
  const isHttps = parsedTarget.protocol === "https:";

  return async (req: Request, res: Response) => {
    try {
      // Collect the request body
      const body = await new Promise<Buffer>((resolve, reject) => {
        const chunks: Buffer[] = [];
        req.on("data", (chunk: Buffer) => chunks.push(chunk));
        req.on("end", () => resolve(Buffer.concat(chunks)));
        req.on("error", reject);
      });

      // Build forward request options
      const forwardHeaders: Record<string, string> = {
        ...opts.headers,
        "Content-Type": req.headers["content-type"] as string || "application/json",
        "Content-Length": body.length.toString(),
        Accept: req.headers["accept"] as string || "text/event-stream, application/json",
      };

      // Copy specific headers from original request
      const copyHeaders = ["accept", "accept-encoding", "cache-control", "connection"];
      for (const h of copyHeaders) {
        if (req.headers[h]) {
          forwardHeaders[h] = req.headers[h] as string;
        }
      }

      const options: http.RequestOptions = {
        hostname: parsedTarget.hostname,
        port: parsedTarget.port || (isHttps ? 443 : 80),
        path: parsedTarget.pathname,
        method: req.method || "POST",
        headers: forwardHeaders,
        timeout: 120000,
      };

      const client = isHttps ? https : http;

      const proxyReq = client.request(options, (proxyRes) => {
        // Forward status and headers
        res.statusCode = proxyRes.statusCode || 200;
        const excludeHeaders = new Set(["transfer-encoding", "connection", "keep-alive"]);
        for (const [key, value] of Object.entries(proxyRes.headers)) {
          if (!excludeHeaders.has(key.toLowerCase()) && value !== undefined) {
            if (Array.isArray(value)) {
              res.setHeader(key, value);
            } else {
              res.setHeader(key, value);
            }
          }
        }

        // Stream the response
        proxyRes.pipe(res);
        proxyRes.on("error", (err) => {
          if (!res.headersSent) {
            res.statusCode = 502;
            res.json({ error: { type: "proxy_error", message: err.message } });
          }
        });
      });

      proxyReq.on("error", (err) => {
        if (!res.headersSent) {
          res.statusCode = 502;
          res.json({ error: { type: "proxy_error", message: `Failed to connect to upstream: ${err.message}` } });
        }
      });

      proxyReq.on("timeout", () => {
        proxyReq.destroy();
        if (!res.headersSent) {
          res.statusCode = 504;
          res.json({ error: { type: "timeout", message: "Upstream request timed out" } });
        }
      });

      // Send the request body
      if (body.length > 0) {
        proxyReq.write(body);
      }
      proxyReq.end();
    } catch (err) {
      if (!res.headersSent) {
        res.statusCode = 500;
        res.json({ error: { type: "internal", message: (err as Error).message } });
      }
    }
  };
}
