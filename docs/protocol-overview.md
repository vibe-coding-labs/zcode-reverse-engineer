# 通信协议总览

> ZCode 的整体通信协议栈架构，从认证到 AI API 调用的完整链路。

---

## 协议栈全景

```mermaid
graph TB
    subgraph User["用户交互层"]
        UI[ZCode 桌面 UI<br/>Electron + React]
        AGT[ZCode Agent<br/>LLM Agent 引擎]
    end

    subgraph Auth["认证层"]
        OA["OAuth 2.0<br/>授权码模式"]
        JWT["JWT Token<br/>身份凭证"]
    end

    subgraph ACP["ACP 代理层"]
        RPC["JSON-RPC<br/>stdio/WebSocket"]
        HTTPP["HTTP Proxy<br/>动态路由"]
        COMPAT["协议转换<br/>Anthropic↔OpenAI↔Gemini"]
    end

    subgraph Network["网络层"]
        REST["REST API<br/>HTTPS"]
        SSE["SSE 流式<br/>Server-Sent Events"]
        WS["WebSocket<br/>实时双向"]
    end

    subgraph Backend["服务端"]
        ZAI_BE["Z.AI 后端<br/>api.z.ai"]
        ZCODE_BE["ZCode 平台<br/>zcode.z.ai"]
        BM_BE["BigModel<br/>open.bigmodel.cn"]
        CHAT["OAuth 提供商<br/>chat.z.ai"]
    end

    UI -->|用户操作| AGT
    AGT -->|stdio RPC| ACP
    AGT -->|HTTP| REST
    Auth -->|Bearer JWT| ACP
    Auth -->|x-api-key| REST
    ACP -->|代理转发| Network
    REST --> ZAI_BE
    REST --> ZCODE_BE
    SSE --> ZAI_BE
    WS --> ZAI_BE
    HTTPP --> ZAI_BE
    HTTPP --> BM_BE
    UI -->|登录| OA
    OA --> CHAT
    CHAT -->|授权码| JWT
    JWT -->|认证| ACP
    JWT -->|认证| REST
```

---

## 协议链路

### 认证链路

```mermaid
sequenceDiagram
    actor U as 用户
    participant Browser as 浏览器
    participant Chat as chat.z.ai
    participant ZCode as zcode.z.ai
    participant API as api.z.ai

    U->>Browser: 打开授权链接
    Browser->>Chat: GET /api/oauth/authorize
    Chat-->>Browser: 登录页
    U->>Browser: 输入手机号 + 验证码
    Browser->>Chat: 登录授权
    Chat-->>Browser: 302 重定向 (code)
    Browser->>ZCode: 回调含 code
    Note over ZCode,API: 授权码有效期极短 (1-5 分钟)
    ZCode->>ZCode: POST /api/v1/oauth/token
    Note over ZCode: 交换 access_token
    ZCode->>API: POST /api/auth/z/login
    Note over API: 交换 Business JWT
    API-->>ZCode: zcodejwttoken
    ZCode-->>Browser: 登录成功
```

### AI API 调用链路

```mermaid
sequenceDiagram
    participant App as ZCode App
    participant ACP as ACP Proxy
    participant API as api.z.ai
    participant ANTH as Anthropic API Compat

    App->>ACP: 发送用户消息
    Note over ACP: 解析 provider + model
    ACP->>ACP: 查找动态路由
    ACP->>API: POST /api/anthropic/v1/messages
    Note over API: x-api-key: JWT
    API-->>ACP: SSE 流式响应
    Note over ACP: 协议转换 (如需)
    ACP-->>App: JSON-RPC 事件
    Note over App: agent_message_chunk
```

### 计费检查链路

```mermaid
sequenceDiagram
    participant App as ZCode App
    participant ZCode as zcode.z.ai
    participant API as api.z.ai

    App->>App: 检查 provider 可用性
    App->>ZCode: GET /api/v1/zcode-plan/billing/current
    Note over ZCode: 检查 Start Plan 权益
    ZCode-->>App: plans[].status === "active"?
    App->>API: GET /api/biz/subscription/list
    Note over API: 检查 Coding Plan 订阅
    API-->>App: data[] / empty
    App->>API: GET /api/monitor/usage/quota/limit
    Note over API: 检查使用配额
    API-->>App: quota limits
    App->>App: 合并判定
    Note over App: Start Plan || Coding Plan → 可用
    Note over App: 无 Plan → coding_plan_not_entitled
```

---

## 协议要点

### 认证

| 特性 | 详情 |
|------|------|
| :octicons-git-commit-24: 协议 | OAuth 2.0 Authorization Code Grant |
| :octicons-lock-24: PKCE | ❌ 不使用 |
| :octicons-key-24: client_secret | ❌ 不需要 |
| :octicons-check-24: state 参数 | ✅ CSRF 防护 |
| :octicons-clock-24: Token 类型 | JWT (HS256 / HS512) |

### 通信

| 特性 | 详情 |
|------|------|
| :octicons-browser-24: API 格式 | Anthropic Messages API |
| :octicons-arrow-switch-24: 流式 | SSE (Server-Sent Events) |
| :octicons-code-24: RPC 协议 | JSON-RPC 2.0 over stdio/WebSocket |
| :octicons-shield-24: 认证方式 | `x-api-key` / `Authorization: Bearer` |

### 代理

| 特性 | 详情 |
|------|------|
| :octicons-hubot-24: Agent 通信 | ACP (Agent Communication Protocol) |
| :octicons-git-branch-24: 路由方式 | 动态路由表 + session 固定路由 |
| :octicons-versions-24: 协议转换 | Anthropic ↔ OpenAI ↔ Gemini ↔ Codex |
| :octicons-plug-24: Gateway | 自定义模型网关 |