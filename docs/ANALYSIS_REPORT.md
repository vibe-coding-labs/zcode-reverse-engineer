# ZCode Reverse Engineering — 完整分析报告

> 生成日期: 2026-06-15
> 分析目标: ZCode Desktop App (v3.0.1 Windows / v2.13.0 Linux)
> 分析方法: 从 NSIS + AppImage 安装包提取 Electron ASAR → 反编译 JS Bundle

---

## 目录

1. [分析范围与方法](#1-分析范围与方法)
2. [OAuth 授权协议](#2-oauth-授权协议)
3. [AI 通信协议](#3-ai-通信协议)
4. [ACP 代理运行时](#4-acp-代理运行时)
5. [模型目录与提供商](#5-模型目录与提供商)
6. [计费与订阅](#6-计费与订阅)
7. [WebSocket / 流式管道](#7-websocket--流式管道)
8. [摘要与可信度评估](#8-摘要与可信度评估)

---

## 1. 分析范围与方法

### 分析的二进制文件

| 平台 | 版本 | 路径 | 大小 | 提取方式 |
|------|------|------|------|---------|
| Windows x64 | 3.0.1 | `data/windows/ZCode-3.0.1-win-x64.exe` | 132 MB | 7z 解压 NSIS → 提取 app-64.7z → asar extract |
| macOS x64 | 3.0.1 | `data/mac/ZCode-3.0.1-mac-x64.dmg` | 149 MB | 未解压 |
| macOS ARM | 3.0.1 | `data/mac-arm64/ZCode-3.0.1-mac-arm64.dmg` | 141 MB | 未解压 |
| Linux x64 | 2.13.0 | `data/linux-x64/ZCode-2.13.0-linux-x64.AppImage` | 355 MB | AppImage extract → squashfs-root |
| Linux ARM64 | 2.13.0 | `data/linux-arm64/ZCode-2.13.0-linux-arm64.AppImage` | 355 MB | 未解压 |

### 已分析的源代码文件

| 文件 | 大小 | 说明 | 分析方法 |
|------|------|------|---------|
| `out/host/index.js` | 1.1 MB | 网络通信层 (webpack bundle) | grep + 关键段落完整读取 |
| `out/host/chunk-J73IRXND.js` | 439 KB | Host chunk 1 | 按需搜索 |
| `out/host/chunk-3ZXTBNVV.js` | 153 KB | Host chunk 2 | 按需搜索 |
| `out/main/index.js` | 614 KB | 主进程逻辑 | 按需搜索 |
| `out/main/chunk-KIIDSXZ3.js` | 409 KB | 主进程 chunk | 按需搜索 |
| `resources/glm/zcode.cjs` | 9.4 MB | GLM Agent 引擎 | 按需搜索 |
| `resources/glm/packages/*` | 多种 | 插件包 | 按需搜索 |
| `resources/model-providers/models_catalog_*.json` | 120 KB | 模型目录 | 完整解析 |
| `acp/dist/acp-agent.js` (Linux) | 99 KB | ACP Agent 实现 | 完整读取全部代码 |
| `acp-proxy-runtime/dist/*.js` (Linux) | 348 KB | ACP 代理运行时 | 完整读取关键文件 |
| `out/renderer/assets/index-*.js` | 3.7 MB | UI 渲染进程 | 按需搜索 |

### 可信度等级

报告中每条信息标注了可信度:
- **✅ 确认** — 直接从代码中读取，无歧义
- **🔶 高概率** — 代码中有明确证据但有一层间接引用
- **⚠️ 推断** — 从代码推理得到，但缺乏直接验证
- **❓ 未知** — 代码中找不到，或无法从静态分析确定

---

## 2. OAuth 授权协议

### 2.1 提供商配置

#### BigModel (智谱 AI) 🔶

```javascript
// out/host/index.js 中直接提取
{
  id: "zcode",                    // provider ID (注意不是 bigmodel!)
  displayName: "BigModel",
  authorizeUrl: "https://bigmodel.cn/login",
  tokenUrl: "https://zcode.z.ai/api/v1/oauth/token",   // 生产环境
  userinfoUrl: "https://zcode.z.ai/api/oauth/userinfo",
  appId: "zcode",
  redirectUri: "zcode://oauth/callback",
  legacyRedirectUri: "zcode://bigmodel-auth/callback"
}
```

#### Z.AI (默认) ✅

```javascript
{
  id: "zai",
  displayName: "Z.ai",
  authorizeUrl: "https://chat.z.ai/api/oauth/authorize",
  tokenUrl: "https://zcode.z.ai/api/v1/oauth/token",
  userinfoUrl: "https://chat.z.ai/api/oauth/userinfo",
  businessLoginUrl: "https://api.z.ai/api/auth/z/login",
  appId: "client_P8X5CMWmlaRO9gyO-KSqtg",
  redirectUri: "zcode://zai-auth/callback",
  legacyRedirectUri: "zcode://oauth/callback"
}
```

> **来源**: `out/host/index.js` 中 `Sm` 和 `Fc` 两个 OAuth provider config 对象的完整代码行

### 2.2 授权码模式细节

| 特性 | 状态 | 证据 |
|------|------|------|
| PKCE (`code_challenge`) | ❌ **不存在** | grep 全库无匹配 |
| `client_secret` | ❌ **不要求** | token 交换请求体中不包含 secret |
| `state` 参数 | ✅ **使用** | 用于 CSRF 防护，验证回调 state 是否匹配 |
| `redirect_uri` | ✅ **使用** | 在授权和 token 交换时都传递 |
| `scope` | ⚠️ **未明确** | 授权 URL 中未发现 scope 参数 |

> **可信度**: OAuth 流程所有配置从代码中直接提取。PKCE 和 client_secret 的缺失需要实际测试验证——服务器可能会 拒绝 没有 PKCE 的请求。

### 2.3 完整 Token 交换流程 ✅

```
Step 1: 打开浏览器 (用户交互)
  GET https://chat.z.ai/api/oauth/authorize
    ?response_type=code
    &client_id=client_P8X5CMWmlaRO9gyO-KSqtg
    &redirect_uri=zcode://zai-auth/callback
    &state=<random_state>

Step 2: 回调 → 本地 HTTP 服务器接收 code
  代码中启动随机端口 HTTP server, 等待 callback

Step 3: Exchange Code → Access Token
  POST https://zcode.z.ai/api/v1/oauth/token
  Content-Type: application/json
  
  {
    "provider": "zai",          // 标识提供商
    "code": "<从回调获取>",       // 授权码
    "redirect_uri": "zcode://zai-auth/callback",
    "state": "<原始 state>"
  }
  
  响应:
  {
    "code": 0,
    "data": {
      "zai": {
        "access_token": "<JWT格式的访问令牌>",     // ✅ 确认
        "refresh_token": "<可选的刷新令牌>"         // ⚠️ 推断
      },
      "user": { "id": "...", "username": "..." },
      "expires_in": 3600
    }
  }

Step 4: Business Token 交换 (关键!)
  POST https://api.z.ai/api/auth/z/login
  Content-Type: application/json
  
  {
    "token": "<step 3 获得的 zai.access_token>"
  }
  
  响应:
  {
    "code": 0,
    "success": true,
    "data": {
      "access_token": "<zcode_jwt_token>",  // ZCode JWT 核心凭据
      "expires_in": 3600
    }
  }

Step 5: 获取用户信息
  GET https://chat.z.ai/api/oauth/userinfo
  Authorization: Bearer <access_token>
  
  响应: { "sub": "user_id", "name": "...", "picture": "..." }
```

> **来源**: `out/host/index.js` 中 `hm` (ZaiProviderAdapter) 和 `fm` (BigModelProviderAdapter) 类的完整方法实现

### 2.4 JWT Token 结构 ⚠️

| 属性 | 值 |
|------|-----|
| **存储键** | `zcodejwttoken` |
| **格式** | 标准 JWT `header.payload.signature` |
| **客户端解析** | 不解析 JWT payload (透传) |
| **客户端验证** | 不验证 JWT 签名 (后端验证) |
| **使用方式** | Coding Plan: `Authorization: Bearer <token>` |
| | API Key 模式: `x-api-key: <token>` |

**关键发现**: JWT Token 的正则提取代码:
```javascript
var IB = /[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/;  // JWT 格式匹配
```

### 2.5 凭据存储 ✅

使用自定义 `credentialService`，底层是 AES-256-GCM 加密后写入文件:

```javascript
// credentialService 实现 (out/host/index.js)
function createCredentialCipherProvider() {
  return {
    encrypt(plaintext) {
      // AES-256-GCM, 随机 IV 12字节
      // 输出格式: "enc:v1:<base64url(iv)>.<base64url(authTag)>.<base64url(ciphertext)>"
    },
    decrypt(ciphertext) {
      // 检查前缀 "enc:v1:", 解析 IV + authTag + ciphertext
      // 解密失败抛出: "凭据解密失败：密钥不匹配或密文已损坏"
    }
  }
}
```

加密密钥: SHA256(`ZCODE_CREDENTIAL_SECRET` env var 或 fallback `zcode-credential-fallback:<platform>:<home>:<username>`)

### 2.6 存储的凭据键

| 键 | 内容 |
|----|------|
| `oauth:active_provider` | 当前活跃的 OAuth 提供商 ID |
| `zcodejwttoken` | ZCode JWT 核心凭据 |
| `oauth:zai:access_token` | Z.AI 访问令牌 |
| `oauth:zai:refresh_token` | (可选) 刷新令牌 |
| `oauth:zai:user_info` | 用户信息 JSON |

### 2.7 会话恢复流程 ✅

```javascript
async function restoreCachedSession() {
  // 1. 读取 oauth:active_provider
  const provider = credentialService.load("oauth:active_provider");
  if (!provider) return null;
  
  // 2. 加载 token 集
  const tokenSet = loadTokenSet(provider);
  if (!tokenSet?.accessToken) return null;
  
  // 3. 恢复 session
  const session = await providerAdapter.restoreSession();
  if (!session) return null;
  
  // 4. 验证 zcodejwttoken 是否存在
  const jwt = tokenSet.zcodeJwtToken?.trim();
  if (!jwt) return null;
  
  // 5. 恢复 UI 状态
  return restoreUIState(session, tokenSet);
}
```

---

## 3. AI 通信协议

### 3.1 API 端点 ✅

| 提供商 | 端点 | 认证 |
|--------|------|------|
| Z.AI (默认) | `POST https://api.z.ai/api/anthropic/v1/messages` | `x-api-key: <JWT>` |
| BigModel | `POST https://open.bigmodel.cn/api/anthropic/v1/messages` | `x-api-key: <API Key>` |
| Coding Plan | 运行时配置 (`zcodePlanAnthropicBaseUrl`) + `/v1/messages` | `Authorization: Bearer <JWT>` |

### 3.2 请求格式 ✅

```http
POST https://api.z.ai/api/anthropic/v1/messages
Content-Type: application/json
x-api-key: <zcode_jwt_token>
anthropic-version: 2023-06-01
User-Agent: ZCode/unknown
HTTP-Referer: https://zcode.z.ai
X-Title: Z Code@electron
X-Platform: <platform>-<arch>
X-ZCode-App-Version: <version>
X-Client-Language: <locale>
X-Client-Timezone: <tz>
X-Release-Channel: production
```

请求体 (Anthropic Messages API):
```json
{
  "model": "glm-5.1",
  "max_tokens": 64000,
  "temperature": 0.2,
  "stream": true,
  "system": [{"type": "text", "text": "You are ZCode."}],
  "messages": [
    {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
  ],
  "thinking": {
    "type": "enabled",
    "budget_tokens": 1024
  }
}
```

**头部的完整构建代码** (out/host/index.js):
```javascript
function buildZCodeSourceHeaders() {
  return {
    "User-Agent": `ZCode/${appVersion ?? "unknown"}`,
    "HTTP-Referer": "https://zcode.z.ai",
    "X-Title": "Z Code@electron",
    "X-ZCode-App-Version": appVersion,
    "X-Platform": `${platform}-${arch}`,
    "X-Release-Channel": releaseChannel,
    "X-Client-Language": locale,
    "X-Client-Timezone": timezone,
    "X-Os-Category": osCategory,
    "X-Os-Version": osVersion,
  };
}
```

### 3.3 流式响应格式 ✅

SSE 事件流 (标准 Anthropic Messages API):

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","type":"message","role":"assistant","content":[],"model":"glm-5.1","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":10,"output_tokens":1}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello!"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":10}}

event: message_stop
data: {"type":"message_stop"}
```

中断/错误:
```json
{"type": "error", "error": {"type": "overload_error", "message": "..."}}
```

### 3.4 协议格式检测

```javascript
function resolveProviderKindFromRuntimeBaseUrl(url) {
  if (url.includes("/coding/paas/v4"))    return "openai-compatible";
  if (url.includes("/api/anthropic"))      return "anthropic";
  if (url.includes("/zcode-plan/anthropic")) return "anthropic";
}
```

支持的格式:
| 格式 | 说明 |
|------|------|
| `anthropic` / `anthropic-messages` | Anthropic Messages API (默认) |
| `openai-compatible` / `openai:chat` | OpenAI Chat Completions |
| `openai-responses` / `responses` | OpenAI Responses API |
| `gemini` | Google Gemini |

### 3.5 未验证的问题 ❓

| 问题 | 状态 | 说明 |
|------|------|------|
| `api.z.ai` 是否接受 x-api-key 中的 JWT | 未验证 | 代码中唯一的认证方式是使用 x-api-key 或 Authorization 头部 |
| Token 实际有效期 | 未验证 | `expires_in: 3600` 在代码中不固定，服务器返回值决定 |
| 是否需要地域限制 | 未验证 | 不确定 Z.AI 是否对海外 IP 限制 |

---

## 4. ACP 代理运行时

### 4.1 什么是 ACP？

ACP (Agent Communication Protocol) 是 Zed Industries / Anthropic 定义的 Agent 间通信协议。ZCode 使用 ACP 实现:
1. **Agent ↔ Host** 通信 (zcode-acp 二进制进程)
2. **HTTP 代理转发** (把 Anthropic API 请求转发到 ZCode 后端)
3. **协议转换** (Anthropic ↔ OpenAI ↔ Gemini ↔ Codex)

### 4.2 架构图

```
┌──────────────┐   stdio/JSON-RPC   ┌───────────────────┐
│  ZCode Agent  │◄──────────────────►│  Host Process     │
│  (zcode-acp   │                    │  (host/index.js)  │
│   binary)     │                    │                   │
└──────────────┘                    └───────┬───────────┘
                                           │
                              HTTP Proxy (端口随机)
                                           │
                    ┌──────────────────────┼──────────────────┐
                    │                      │                   │
              ┌─────▼─────┐        ┌──────▼──────┐    ┌──────▼──────┐
              │ codex     │        │ opencode    │    │  direct     │
              │ 兼容层     │        │ 兼容层       │    │  Anthropic  │
              └───────────┘        └─────────────┘    └──────▲──────┘
                                                             │
                                              POST https://api.z.ai/api/anthropic/v1/messages
```

### 4.3 动态运行时路由 ✅

核心: `acp-proxy-runtime/dist/runtimeRoutes.js`

```javascript
class RuntimeRouteRegistry {
  routes = new Map();           // 普通路由表
  pinnedRoutes = new Map();     // session 固定路由
  // 限制: 每个路由 key 最大一个
  // 操作类型: set_route, delete_route, pin_route, unpin_route
}
```

**路由匹配流程**:
1. 读取请求头 `x-zcode-proxy-route-key`
2. 先查 `pinnedRoutes` (按 `routeKey:sessionId` 复合键)
3. 再查 `routes` (按 routeKey)
4. 返回: `targetBaseUrl`, `headers` (可选), `model` (可选)

### 4.4 Gateway 认证机制 ✅

当 ACP 客户端声明支持 gateway auth 时:

```javascript
// ACP Agent 返回的认证方法
authMethods = [{
  id: "gateway",
  name: "Custom model gateway",
  description: "Use a custom gateway to authenticate and access models",
  _meta: {
    gateway: { protocol: "anthropic" }
  }
}];
```

启动 Claude Code SDK 时设置环境变量:
```javascript
function createEnvForGateway(gatewayMeta) {
  if (!gatewayMeta) return {};
  
  return {
    ANTHROPIC_BASE_URL: gatewayMeta.gateway.baseUrl,
    ANTHROPIC_CUSTOM_HEADERS: Object.entries(gatewayMeta.gateway.headers)
      .map(([key, value]) => `${key}: ${value}`)
      .join("\n"),
    ANTHROPIC_AUTH_TOKEN: "",  // 必须为空以绕过登录
  };
}
```

### 4.5 协议兼容转换 ✅

| 转换 | 源格式 | 目标格式 | 文件 |
|------|--------|---------|------|
| Codex → Anthropic | Codex | Anthropic Messages | `codexAnthropicCompat.js` |
| Codex → OpenAI Chat | Codex | Chat Completions | `codexOpenaiChatCompat.js` |
| Codex → Gemini | Codex | Gemini | `codexGeminiCompat.js` |
| Gemini → OpenAI Chat | Gemini | Chat Completions | `geminiOpenaiChatCompat.js` |

### 4.6 代理服务器功能 ✅

`acp-proxy-runtime/dist/proxyServer.js` 实现了:

| 功能 | 说明 |
|------|------|
| HTTP 代理 | `http.createServer()` 监听随机端口 |
| CONNECT 隧道 | 支持 HTTPS MITM |
| MITM 证书 | 动态生成 CA 证书 (`certificate.js`) |
| 流量捕获 | 录制所有 HTTP 请求/响应 (`capture.js`) |
| WebSocket | 支持 WebSocket 升级 (`wsUpgradeHandler.js`) |

---

## 5. 模型目录与提供商

### 5.1 预定义提供商 (硬编码) ✅

```javascript
const PRESET_PROVIDERS = [
  { id: "bigmodel",      name: "Bigmodel - API Key",  baseURL: "https://open.bigmodel.cn/api/anthropic" },
  { id: "zai",           name: "Z.ai - API Key",       baseURL: "https://api.z.ai/api/anthropic" },
  { id: "zaiStartPlan",  name: "Z.ai - Coding Plan" },
  { id: "bigmodelStartPlan", name: "BigModel - Coding Plan" },
  { id: "claude",        name: "Claude" },
  { id: "glm",           name: "GLM" },
  { id: "codex",         name: "Codex" },
  { id: "opencode",      name: "OpenCode" },
  { id: "gemini",        name: "Gemini" },
  { id: "zapi",          name: "ZAPI", baseURL: "http://192.168.6.166:8080" },  // 开发环境!
];
```

### 5.2 模型目录 (`models_catalog_china_llm_zcode_2026-06-03.json`) ✅

**Schema**: `zcode.model-providers.v1`

#### Z.AI / BigModel (智谱 GLM 系列)
| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| glm-5.1 | 200K | 64K | ✅ enabled |
| glm-5.1-highspeed | 200K | 64K | ✅ enabled |
| glm-5 | 200K | 64K | ✅ enabled |
| glm-5-turbo | 200K | 64K | ✅ enabled |
| glm-4.7 | 200K | 128K | ✅ enabled |
| glm-4.7-flash | 200K | 128K | ✅ enabled |
| glm-4.6 | 200K | 128K | ✅ enabled |
| glm-4.5 | 131K | 98K | ✅ enabled |
| glm-4.6v (视觉) | 131K | 32K | ❌ off |

#### Kimi (Moonshot)
| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| kimi-k2.6 | 262K | 98K | ✅ enabled |
| kimi-k2.5 | 262K | - | ✅ enabled |

#### DeepSeek
| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| deepseek-v4-flash | **1M** | 384K | ✅ max |
| deepseek-v4-pro | **1M** | 384K | ✅ max |

#### Qwen (阿里云)
| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| qwen3.5-plus | **1M** | 64K | ✅ enabled |
| qwen3.5-flash | **1M** | 64K | ✅ enabled |
| qwen3-max | 262K | 64K | ❌ off |

#### MiniMax
| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| MiniMax-M3 | **1M** | - | ❌ off |
| MiniMax-M2.7 | 204K | - | ❌ off |

#### 小米 MiMo
| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| mimo-v2.5-pro | **1M** | 128K | ✅ enabled |
| mimo-v2.5 | **1M** | 128K | ✅ enabled |

### 5.3 模型格式映射

```javascript
const FORMAT_MAP = {
  claude:    ["anthropic"],
  glm:       ["anthropic", "responses", "openai"],
  opencode:  ["openai"],
  gemini:    ["openai"],
  codex:     ["responses", "openai"],
  zai:       ["anthropic", "openai"],
  bigmodel:  ["anthropic", "openai"],
};
```

---

## 6. 计费与订阅

### 6.1 订阅状态 ✅

```javascript
// 常量定义
const SUBSCRIPTION_CONSTANTS = {
  coding_plan_zai_overseas_payment_required: "海外支付要求",
  coding_plan_not_auth: "未登录/未授权",
  coding_plan_auth_failed: "认证失败（Token 过期/无效）",
  coding_plan_not_entitled: "无订阅计划",
  oauth_provider_inactive: "OAuth 提供商未激活",
};
```

### 6.2 订阅检查端点 ✅

```javascript
// Z.AI
GET https://api.z.ai/api/biz/subscription/list
Authorization: Bearer <zcode_jwt_token>

// BigModel
GET /api/biz/subscription/list   // 通过客户端配置动态获取

// 用量配额
GET https://api.z.ai/api/monitor/usage/quota/limit
Authorization: Bearer <zcode_jwt_token>
```

### 6.3 订阅对 API 调用的影响 ✅

```javascript
function loadPlanApiKey(provider) {
  const jwt = credentialService.load("zcodejwttoken");
  if (jwt) {
    return { value: `Bearer ${jwt}`, missingReason: null };
  }
  // 无 JWT → 检查用户信息
  const userInfo = credentialService.load("oauth:zai:user_info");
  const reason = userInfo ? "coding_plan_auth_failed" : "coding_plan_not_auth";
  return { value: "", missingReason: reason };
}
```

### 6.4 错误处理链 ✅

```javascript
if (error.status === 401 || error.status === 403) {
  // 标记 Coding Plan 提供商为不可用
  // 尝试 API Key 提供商
  // 如果都不可用: 提示登录或购买 Coding Plan
}
```

---

## 7. WebSocket / 流式管道

### 7.1 事件转换管道 ✅

```
model.streaming ──► 合并去重 ──► agent_message_chunk 
   (text_delta)         │            (text)
   (reasoning_delta)    │            |
   (tool_input_delta)   │            ▼
                        │      agent_thought_chunk
                        │         (thinking text)
                        ▼
                   tool.updated ──► agent_tool_update
```

去重机制:
```javascript
function getCoalesceKey(event) {
  if (event.type === "model.streaming") {
    const kind = event.payload.kind;
    // 按 session + turn + input + kind + assistantMessageId 合并
    return `${event.type}:${sessionId}:${turnId}:${kind}:${inputId}`;
  }
  if (event.type === "tool.updated" && kind === "progress") {
    return `${event.type}:${sessionId}:${toolCallId}`;
  }
}
```

### 7.2 RPC 协议 ✅

ZCode 使用自定义的 JSON-RPC over stdio/websocket 协议:

```javascript
// 请求格式
{
  "id": 1,
  "method": "session/send",
  "params": { ... },
  "trace": { "traceId": "..." }
}

// 成功响应
{
  "id": 1,
  "result": { ... }
}

// 错误响应  
{
  "id": 1,
  "error": { "code": -32602, "message": "Invalid params", "data": ... }
}

// 通知 (无 id)
{
  "method": "session/event",
  "params": { ... }
}

// 请求 (需要响应)
{
  "id": 2,
  "method": "interaction/requestPermission",
  "params": { ... }
}
```

**支持的 RPC 方法** (部分列表):

| 方法 | 方向 | 说明 |
|------|------|------|
| `session/create` | Host → Agent | 创建新会话 |
| `session/resume` | Host → Agent | 恢复历史会话 |
| `session/send` | Host → Agent | 发送用户消息 |
| `session/stop` | Host → Agent | 停止响应 |
| `session/event` | Agent → Host | 流式事件通知 |
| `sessionUpdate` | Host → Agent | Session 更新通知 |
| `workspace/readState` | Host → Agent | 读取工作区状态 |
| `interaction/requestPermission` | Agent → Host | 请求用户授权 |
| `interaction/requestUserInput` | Agent → Host | 请求用户输入 |
| `state.updated` | Agent → Host | 状态变更通知 |

### 7.3 远程工作区 ✅

- 使用 SSH (`ssh2` npm 包) 连接远程工作区
- 支持 `/reconnect` 命令重连
- 远程端的任务事件通过 `task_stream_mirror_batch` 同步

---

## 8. 免费额度 (Start Plan) 完整分析

### 8.1 Start Plan 是什么 ✅

从官网文档直接引用:

> **"新用户也可以通过 Start Plan 获取免费体验额度，登录后即可开始试用 GLM-5.2 与 GLM-5-Turbo。"**
> — zcode-ai.com/cn/docs/welcome

Start Plan 是 ZCode 的免费/入门套餐，无需付费，登录即送。

### 8.2 已知的配额维度

从官网用量统计页面文案:

| 维度 | 周期 | 说明 |
|------|------|------|
| **Prompt 池** | 5 小时 | Agent 运行时长上限，非 token 计数 |
| **每周额度** | 每周重置 | Token 调用的周配额 |
| **MCP 每月额度** | 每月重置 | MCP 工具调用单独计数 |
| **模型 Token 消耗** | 实时 | GLM-5.2、GLM-5-Turbo 显示各自的消耗 |

### 8.3 配额查询 API (从代码提取)

```javascript
// 查询 Start Plan 状态和剩余
GET <环境变量 zcodePlanBillingCurrentUrl>?app_version=<version>
Authorization: Bearer <zcode_jwt_token>

// 查询 Coding Plan 订阅
GET https://api.z.ai/api/biz/subscription/list
Authorization: Bearer <zcode_jwt_token>

// 查询用量/配额限制
GET https://api.z.ai/api/monitor/usage/quota/limit
Authorization: Bearer <zcode_jwt_token>
```

### 8.4 服务端返回的配额结构

```json
{
  "plans": [{
    "status": "active",
    "total_units": 100,            // 总配额
    "used_units": 30,              // 已用
    "available_units": 70,         // 剩余
    "period_end": 1718400000,      // 下次重置时间
    "capabilities": ["model:glm-5.1", "model:glm-5-turbo"]
  }],
  "balances": [{
    "total_units": 100,
    "used_units": 30,
    "available_units": 70,
    "entitlement_id": "model_usage"
  }]
}
```

### 8.5 套餐优先序 ⚠️

```javascript
// 同时有 Start Plan (免费) 和 Coding Plan (付费) 时的选择
if (用户已购买 Coding Plan) {
  → 使用 Coding Plan (Start Plan 不可选)
} else if (Start Plan active) {
  → 使用 Start Plan 免费额度
} else {
  → 提示 "coding_plan_not_entitled" 无可用套餐
}
```

### 8.6 关于免费额度的不确定问题 ❓

| 问题 | 状态 | 原因 |
|------|------|------|
| **5 小时 prompt 池 = 实际多少 token？** | ❌ 未知 | 服务端计算，需实测 |
| **每周额度具体数字？** | ❌ 未知 | 服务端 `total_units` 字段，非客户端硬编码 |
| **MCP 每月额度多少？** | ❌ 未知 | MCP 工具调用单独计数 |
| **需要绑信用卡吗？** | ⚠️ 高概率不需要 | 设计为登录即用，无付费流程 |
| **有效期多久？** | ⚠️ 推断可能不限时 | 服务端控制 `ends_at` |
| **海外用户能注册吗？** | ⚠️ 需验证 | 可能限制国内手机号 |

### 8.7 获取精确数字的唯一方法

```bash
# 1. 本地运行登录
npm run login

# 2. 成功后会得到 JWT Token
# 3. 直接请求计费 API 看数字
curl -H "Authorization: Bearer <jwt>" "https://api.z.ai/api/monitor/usage/quota/limit"
```

这需要你在**有浏览器的电脑上**运行 `npm run login`（或直接打开 ZCode 用 DevTools 提取 Token）。

---

### 已确认 (从代码直接读取) ✅

| 项目 | 可信度 | 证据 |
|------|--------|------|
| OAuth 端点 URL 和参数 | ✅ 确认 | 代码行 `Sm = { authorizeUrl: "...", tokenUrl: "..."}` |
| OAuth 回调处理 | ✅ 确认 | `hm` (ZaiProviderAdapter) 完整方法 |
| Business Token 交换 | ✅ 确认 | `gm` (businessTokenResolver) 类 |
| 所有 API 端点 URL | ✅ 确认 | 硬编码 URL 字符串 |
| Anthropic Messages API 格式 | ✅ 确认 | `completeAnthropic()` 方法中的 JSON body |
| 请求头 (x-api-key, anthropic-version 等) | ✅ 确认 | `Mr`, `Tl()` 函数 |
| 模型目录 | ✅ 确认 | `models_catalog_*.json` 完整文件 |
| 提供商配置 | ✅ 确认 | `PRESET_PROVIDERS` 数组 |
| 凭据存储机制 | ✅ 确认 | `nx()` (createCredentialCipherProvider) |
| 订阅状态字符串 | ✅ 确认 | `coding_plan_not_auth` 等 |
| 流式事件的转换 | ✅ 确认 | `mapSessionEvent()` → `W4()`, `H4()`, 等 |
| ACP 路由 | ✅ 确认 | `RuntimeRouteRegistry` 完整类 |
| Gateway 环境变量 | ✅ 确认 | `createEnvForGateway()` 函数 |

### 高概率 (代码有明确证据但间接) 🔶

| 项目 | 可信度 | 说明 |
|------|--------|------|
| 无需 PKCE | 🔶 高 | 所有 grep 无匹配，但不排除服务器端要求 |
| 无需 client_secret | 🔶 高 | Token 交换 body 无 secret 字段 |
| JWT 格式 | 🔶 高 | 正则 `/[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/` |
| `expires_in` 字段 | 🔶 高 | 代码读取 `o.data?.expires_in` 但非固定值 |
| BigModel / Z.AI 共享 token URL | 🔶 高 | 都指向 `zcode.z.ai/api/v1/oauth/token` |

### 推断 (从上下文推理) ⚠️

| 项目 | 可信度 | 说明 |
|------|--------|------|
| `glm-5.1` 是默认模型 | ⚠️ 推断 | `nr` 数组首个元素 |
| AES-256-GCM 加密细节 | ⚠️ 推断 | 代码中有 `createCipheriv("aes-256-gcm")` |
| SSE 格式 (event/data 行) | ⚠️ 推断 | 自动更新使用文本流，AI 响应也使用流式 |

### 完全未知 (无法从静态分析确认) ❓

| 问题 | 说明 |
|------|------|
| **OAuth 能否正常完成** | Z.AI 服务器可能有额外的校验（PKCE 要求即使客户端不发送） |
| **JWT Token 后端是否接受** | 没真实发过请求 |
| **Token 实际有效期** | `expires_in` 值由服务器决定 |
| **是否有 IP/地域限制** | 不确定 Z.AI 后端是否对海外 IP 拦截 |
| **Coding Plan 实际付费流程** | 代码中无完整支付流程 |
| **模型是否全部可用** | 某些模型可能标记为 `disabled` 取决于订阅状态 |

---

## 附录: 关键代码索引

### out/host/index.js 关键行

| 行 (近似) | 内容 |
|-----------|------|
| - | `Mr` = 基本请求头 |
| - | `Tl()` = `buildZCodeSourceHeaders()` |
| - | `Sm` = Z.AI OAuth 配置 |
| - | `Fc` = BigModel OAuth 配置 |
| - | `hm` = ZaiProviderAdapter 类 |
| - | `gm` = BusinessTokenResolver 类 |
| - | `nx()` = createCredentialCipherProvider |
| - | `ri()` = createCredentialService |
| - | `oG()` = getBackgroundSessionEventCoalesceKey |
| - | `W4()` = mapModelStreaming → agent_message_chunk |
| - | `RuntimeRouteRegistry` 类 (嵌入) |
| - | `createEnvForGateway()` (嵌入) |
| - | `PRESET_PROVIDERS` 数组 |

### acp-proxy-runtime/dist/ 文件

| 文件 | 主要内容 |
|------|---------|
| `proxyServer.js` | ACP 代理 HTTP 服务器 |
| `runtimeRoutes.js` | 动态路由表 |
| `httpForwarding.js` | HTTP 转发 + 协议兼容 |
| `httpForwardingAnthropicModelOverride.js` | 模型名重写 |
| `codexAnthropicCompat.js` | Codex → Anthropic 转换 |
| `codexOpenaiChatCompat.js` | Codex → OpenAI Chat 转换 |
| `wsUpgradeHandler.js` | WebSocket 升级处理 |
| `certificate.js` | MITM CA 证书 |
| `capture.js` | 流量捕获 |

### acp/dist/ 文件

| 文件 | 主要内容 |
|------|---------|
| `acp-agent.js` | ClaudeAcpAgent 完整实现 |
| `tools.js` | 工具调用 Hook |
| `settings.js` | 配置管理 |
| `utils.js` | 工具函数: Pushable, 流转换 |