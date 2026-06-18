/**
 * ZCode AI API Client.
 * Calls ZCode's backend using Anthropic Messages API format.
 *
 * Based on reverse-engineered protocol:
 * - Endpoint: POST https://api.z.ai/api/anthropic/v1/messages
 * - Auth: x-api-key header with ZCode JWT or Authorization: Bearer
 * - Streaming: SSE (server-sent events)
 */

import axios, { AxiosError } from "axios";
import type { ZCodeCredentials } from "./types.js";

// ZCode API endpoint (from reverse engineering)
const ZCODE_API_BASE = "https://api.z.ai/api/anthropic";

// Common headers used by ZCode
const ZCODE_HEADERS: Record<string, string> = {
  "User-Agent": "ZCode/unknown",
  "HTTP-Referer": "https://zcode.z.ai",
  "X-Title": "Z Code@electron",
  "anthropic-version": "2023-06-01",
};

export interface ApiCallOptions {
  model?: string;
  maxTokens?: number;
  temperature?: number;
  systemPrompt?: string;
  stream?: boolean;
}

/**
 * Build headers for ZCode AI API call
 */
function buildHeaders(creds: ZCodeCredentials): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "x-api-key": creds.zcodeJwtToken,
    ...ZCODE_HEADERS,
  };
}

/**
 * Send a query to ZCode's AI API and get a streaming response
 */
export async function* askStream(
  creds: ZCodeCredentials,
  message: string,
  options: ApiCallOptions = {}
): AsyncGenerator<string, void, unknown> {
  const model = options.model || "claude-sonnet-4-6";
  const maxTokens = options.maxTokens || 4096;
  const temperature = options.temperature ?? 0.2;
  const systemPrompt = options.systemPrompt || "You are a helpful assistant.";

  const body = {
    model,
    max_tokens: maxTokens,
    temperature,
    stream: true,
    system: [{ type: "text" as const, text: systemPrompt }],
    messages: [
      {
        role: "user" as const,
        content: [{ type: "text" as const, text: message }],
      },
    ],
  };

  try {
    const response = await axios.post(`${ZCODE_API_BASE}/v1/messages`, body, {
      headers: buildHeaders(creds),
      responseType: "stream",
      timeout: 120000,
      validateStatus: (status) => status < 500,
    });

    if (response.status !== 200) {
      // Try to read error body
      const errorBody = await new Promise<string>((resolve) => {
        let data = "";
        response.data.on("data", (chunk: Buffer) => { data += chunk.toString(); });
        response.data.on("end", () => resolve(data));
      });
      throw new Error(`API error (${response.status}): ${errorBody}`);
    }

    const stream = response.data;
    let buffer = "";

    for await (const chunk of stream) {
      buffer += chunk.toString();

      // Parse SSE events
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(":")) continue; // comment/empty

        if (trimmed.startsWith("data: ")) {
          const data = trimmed.slice(6);

          if (data === "[DONE]") {
            return;
          }

          try {
            const event = JSON.parse(data);
            yield* handleStreamEvent(event);
          } catch (e) {
            // Skip unparseable data
            console.error("⚠ Parse error:", (e as Error).message);
          }
        }
        // event: lines are informational, we process data: lines
      }
    }
  } catch (error) {
    if (error instanceof AxiosError) {
      const status = error.response?.status;
      const data = error.response?.data as string | undefined;

      if (status === 401 || status === 403) {
        throw new Error(`Authentication failed (HTTP ${status}). Token may be expired. Please run: npm run login`);
      }
      // Try to read the full error body
      let errorDetail = data || "";
      if (data && typeof data === "object" && data[Symbol.asyncIterator]) {
        errorDetail = await new Promise<string>((resolve) => {
          let d = "";
          (data as any).on("data", (c: Buffer) => { d += c.toString(); });
          (data as any).on("end", () => resolve(d));
        });
      }
      throw new Error(`API error (HTTP ${status}): ${errorDetail.slice(0, 500)}`);
    }
    throw error;
  }
}

/**
 * Handle SSE stream event from Anthropic Messages API
 */
function* handleStreamEvent(event: any): Generator<string> {
  switch (event.type) {
    case "message_start":
      // Optionally print model info
      if (event.message?.model) {
        yield `[Model: ${event.message.model}]\n`;
      }
      break;

    case "content_block_delta":
      if (event.delta?.type === "text_delta" && event.delta.text) {
        yield event.delta.text;
      }
      break;

    case "content_block_start":
    case "content_block_stop":
    case "message_delta":
      // These don't contain text content
      break;

    case "message_stop":
      break;

    case "ping":
      break;

    case "error":
      throw new Error(`API stream error: ${event.error?.message || JSON.stringify(event.error)}`);

    default:
      // Unknown event type - skip silently
      break;
  }
}

/**
 * Send a query and get the complete response as text
 */
export async function ask(
  creds: ZCodeCredentials,
  message: string,
  options: ApiCallOptions = {}
): Promise<string> {
  let fullText = "";
  for await (const chunk of askStream(creds, message, options)) {
    fullText += chunk;
  }
  return fullText.trim();
}