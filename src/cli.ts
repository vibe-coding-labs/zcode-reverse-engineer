#!/usr/bin/env node

/**
 * ZCode Reverse Engineer CLI — MVP
 *
 * Commands:
 *   login   — Perform OAuth login to get ZCode JWT token
 *   ask     — Send a message to ZCode AI and stream the response
 *   proxy   — Start a reverse proxy server (Anthropic → ZCode)
 */

import { Command } from "commander";
import { login, loadCredentials, refreshAccessToken } from "./oauth.js";
import { askStream, ask } from "./api.js";
import { startProxyServer } from "./proxy.js";

const program = new Command();

program
  .name("zcode-mvp")
  .description("ZCode Reverse Engineering MVP — prove AI API protocol understanding")
  .version("1.0.0");

program
  .command("login")
  .description("Perform OAuth login and save credentials")
  .action(async () => {
    try {
      await login();
      console.log("\n✅ Login complete! You can now use:\n");
      console.log("   npm run ask -- \"your question\"");
      console.log("   npm run proxy");
    } catch (error) {
      console.error("\n❌ Login failed:", (error as Error).message);
      process.exit(1);
    }
  });

program
  .command("ask")
  .description("Send a message to ZCode AI")
  .argument("[message]", "Your question for the AI")
  .option("-m, --model <model>", "Model name (default: claude-sonnet-4-6)")
  .option("-s, --system <prompt>", "System prompt")
  .option("-n, --no-stream", "Disable streaming (wait for full response)")
  .action(async (message?: string, options?: { model?: string; system?: string; stream?: boolean }) => {
    try {
      const creds = loadCredentials();
      if (!creds) {
        console.error("❌ No credentials found. Please run: npm run login");
        process.exit(1);
      }

      // Check if token is expired
      if (creds.expiresAt && Date.now() > creds.expiresAt) {
        console.log("⚠ Token expired, attempting refresh...");
        try {
          const newCreds = await refreshAccessToken(creds);
          Object.assign(creds, newCreds);
        } catch {
          console.error("❌ Token refresh failed. Please run: npm run login");
          process.exit(1);
        }
      }

      // If no message provided as arg, prompt for it
      if (!message) {
        const readline = await import("readline");
        const rl = readline.createInterface({
          input: process.stdin,
          output: process.stdout,
        });
        message = await new Promise<string>((resolve) => {
          rl.question("Enter your message: ", (answer) => {
            rl.close();
            resolve(answer);
          });
        });
      }

      const apiOptions = {
        model: options?.model || "claude-sonnet-4-6",
        systemPrompt: options?.system,
        stream: options?.stream !== false, // default true
      };

      if (apiOptions.stream) {
        process.stdout.write("\n");
        for await (const chunk of askStream(creds, message!, apiOptions)) {
          process.stdout.write(chunk);
        }
        process.stdout.write("\n\n");
      } else {
        process.stdout.write("\n⏳ Waiting for complete response...\n\n");
        const text = await ask(creds, message!, apiOptions);
        console.log(text);
        console.log();
      }
    } catch (error) {
      console.error("\n❌ Error:", (error as Error).message);
      process.exit(1);
    }
  });

program
  .command("proxy")
  .description("Start a reverse proxy server (listens on http://localhost:6379)")
  .option("-p, --port <port>", "Port to listen on", "6379")
  .option("--host <host>", "Host to bind to", "127.0.0.1")
  .action(async (options?: { port?: string; host?: string }) => {
    const creds = loadCredentials();
    if (!creds) {
      console.error("❌ No credentials found. Please run: npm run login");
      process.exit(1);
    }

    const port = parseInt(options?.port || "6379", 10);
    const host = options?.host || "127.0.0.1";
    await startProxyServer(creds, port, host);
  });

program.parse(process.argv);
