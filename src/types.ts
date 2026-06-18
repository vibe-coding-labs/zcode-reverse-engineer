/** OAuth token exchange response from zcode.z.ai */
export interface ZCodeTokenResponse {
  code?: number;
  msg?: string;
  data?: {
    zai?: {
      access_token: string;
      refresh_token?: string;
    };
    bigmodel?: {
      access_token: string;
      refresh_token?: string;
    };
    user?: ZCodeUserProfile;
    expires_in?: number;
  };
}

/** Business login token response from api.z.ai */
export interface ZCodeBusinessLoginResponse {
  code?: number;
  success?: boolean;
  data?: {
    access_token?: string;
    accessToken?: string;
    expires_in?: number;
  };
}

export interface ZCodeUserProfile {
  id?: string;
  username?: string;
  displayName?: string;
  avatarUrl?: string;
  email?: string;
}

/** Stored credential info */
export interface ZCodeCredentials {
  provider: string;
  accessToken: string;
  zcodeJwtToken: string;
  refreshToken?: string;
  expiresAt?: number;
  userInfo?: ZCodeUserProfile;
}

/** Anthropic Messages API request body */
export interface AnthropicMessageRequest {
  model: string;
  max_tokens: number;
  temperature?: number;
  stream: boolean;
  system?: Array<{ type: "text"; text: string }>;
  messages: Array<{
    role: "user" | "assistant";
    content: string | Array<{ type: "text"; text: string }>;
  }>;
  thinking?: {
    type: "enabled" | "disabled";
    budget_tokens?: number;
  };
}

/** SSE stream event from Anthropic Messages API */
export interface AnthropicStreamEvent {
  type: "message_start" | "message_delta" | "message_stop" |
        "content_block_start" | "content_block_delta" | "content_block_stop" |
        "ping" | "error";
  message?: {
    id: string;
    type: string;
    role: string;
    content: Array<any>;
    model: string;
    stop_reason: string | null;
    stop_sequence: string | null;
    usage: {
      input_tokens: number;
      output_tokens: number;
    };
  };
  index?: number;
  content_block?: any;
  delta?: {
    type?: string;
    text?: string;
    partial_json?: string;
  };
  usage?: {
    output_tokens: number;
    input_tokens?: number;
  };
  error?: {
    type: string;
    message: string;
  };
}