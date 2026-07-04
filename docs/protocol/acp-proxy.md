# ACP 代理运行时

> ACP (Agent Communication Protocol) 是 ZCode 的核心代理层，负责 Agent 间通信、HTTP 转发和协议转换。

---

## 架构总览

```mermaid
graph TB
    subgraph Host["ZCode Host Process"]
        S["Session 管理"]
        ACP_AGENT["ACP Agent<br/>(zcode-acp 二进制)"]
    end

    subgraph Proxy["ACP Proxy Runtime"]
        PR["HTTP Proxy Server<br/>随机端口"]
        RR["Runtime Route Registry<br/>动态路由表"]
        MITM["MITM CA 证书<br/>流量捕获"]
    end

    subgraph Forwarding["协议转发"]
        AF["Anthropic 转发<br/>anthropic/v1/messages"]
        OF["OpenAI 转发<br/>v1/chat/completions"]
        GF["Gemini 转发<br/>v1/models"]
    end

    subgraph Compat["协议兼容层"]
        CX_AN["codexAnthropicCompat<br/>Codex → Anthropic"]
        CX_OC["codexOpenaiChatCompat<br/>Codex → OpenAI"]
        CX_GM["codexGeminiCompat<br/>Codex → Gemini"]
        GM_OC["geminiOpenaiChatCompat<br/>Gemini → OpenAI"]
    end

    subgraph Backend["后端服务"]
        ZAI["Z.AI<br/>api.z.ai"]
        BM["BigModel<br/>open.bigmodel.cn"]
    end

    Host -->|"stdio<br/>JSON-RPC"| ACP_AGENT
    ACP_AGENT -->|HTTP Proxy| PR
    PR -->|"x-zcode-proxy-route-key"| RR
    RR -->|选择路由| Forwarding
    Forwarding -->|直接转发| Backend
    Forwarding -->|需要转换| Compat
    Compat -->|转换后转发| Backend
    PR --> MITM
```

---

## ACP Agent

ACP Agent (`zcode-acp` 二进制) 负责 LLM Agent 的运行和通信：

```mermaid
sequenceDiagram
    participant Host as ZCode Host
    participant Agent as ACP Agent (zcode-acp)
    participant Proxy as ACP Proxy

    Host->>Agent: session/create (JSON-RPC)
    Agent-->>Host: session/created

    Host->>Agent: session/send (用户消息)
    Agent-->>Host: session/event (model.streaming)
    Agent-->>Host: session/event (tool.updated)
    Agent-->>Host: session/event (agent_message_chunk)
    Agent-->>Host: session/event (agent_thought_chunk)

    Note over Agent,Proxy: Agent 通过 HTTP Proxy 调用 AI API
    Agent->>Proxy: POST /v1/messages
    Proxy-->>Agent: SSE 流式响应

    Host->>Agent: session/stop (中断)
    Agent-->>Host: session/stopped
```

### JSON-RPC 协议

```json
{
    "id": 1,
    "method": "session/send",
    "params": { "message": "Hello" },
    "trace": { "traceId": "..." }
}
```

### 支持的 RPC 方法

| 方法 | 方向 | 说明 |
|------|------|------|
| `session/create` | Host → Agent | 创建新会话 |
| `session/resume` | Host → Agent | 恢复历史会话 |
| `session/send` | Host → Agent | 发送用户消息 |
| `session/stop` | Host → Agent | 停止响应 |
| `session/event` | Agent → Host | 流式事件通知 |
| `sessionUpdate` | Host → Agent | Session 更新通知 |
| `workspace/readState` | Host → Agent | 工作区状态读取 |
| `interaction/requestPermission` | Agent → Host | 请求用户授权 |

---

## ACP Proxy Runtime

### 动态路由

```mermaid
graph LR
    subgraph Request["HTTP 请求"]
        K["x-zcode-proxy-route-key<br/>路由标识"]
        M["x-zcode-target-model<br/>目标模型"]
    end

    subgraph Registry["RuntimeRouteRegistry"]
        R["routes Map<br/>普通路由"]
        PR["pinnedRoutes Map<br/>session 固定路由"]
    end

    subgraph Route["路由结果"]
        URL["targetBaseUrl<br/>目标 URL"]
        H["headers<br/>自定义请求头"]
        MODEL["model<br/>模型名重写"]
    end

    K --> Registry
    M --> Registry
    R --> Route
    PR --> Route
```

### Gateway 认证

当 ACP 客户端支持 Gateway auth 时：

```mermaid
sequenceDiagram
    participant Agent as ACP Agent
    participant Host as Host
    participant GW as Custom Gateway

    Agent->>Host: authMethods: [{ id: "gateway" }]
    Host->>Host: createEnvForGateway()
    Note over Host: ANTHROPIC_BASE_URL = gateway.baseUrl
    Note over Host: ANTHROPIC_CUSTOM_HEADERS = gateway.headers
    Note over Host: ANTHROPIC_AUTH_TOKEN = ""

    Agent->>GW: API Call (via gateway)
    GW-->>Agent: Response
```

---

## 协议转换

```mermaid
graph TB
    subgraph Source["源格式"]
        CX[Codex]
        GM[Gemini]
    end

    subgraph Transform["转换器"]
        C_A[codexAnthropicCompat.js]
        C_O[codexOpenaiChatCompat.js]
        C_G[codexGeminiCompat.js]
        G_O[geminiOpenaiChatCompat.js]
    end

    subgraph Target["目标格式"]
        AN[Anthropic Messages]
        OC[OpenAI Chat Completions]
        GI[Gemini]
    end

    CX --> C_A
    CX --> C_O
    CX --> C_G
    GM --> G_O
    C_A --> AN
    C_O --> OC
    C_G --> GI
    G_O --> OC
```

---

## 流式事件管道

```mermaid
flowchart LR
    subgraph Input["模型流式事件"]
        TD[text_delta]
        RD[reasoning_delta]
        TID[tool_input_delta]
    end

    subgraph Merge["合并去重"]
        CK[getCoalesceKey<br/>按 session+turn+kind 合并]
    end

    subgraph Output["Agent 事件"]
        AMC[agent_message_chunk]
        ATC[agent_thought_chunk]
        ATU[agent_tool_update]
    end

    TD --> CK
    RD --> CK
    TID --> CK
    CK --> AMC
    CK --> ATC
    CK --> ATU
```

### 去重机制

```javascript
function getCoalesceKey(event) {
    if (event.type === "model.streaming") {
        const kind = event.payload.kind;
        return `${event.type}:${sessionId}:${turnId}:${kind}:${inputId}`;
    }
    if (event.type === "tool.updated" && kind === "progress") {
        return `${event.type}:${sessionId}:${toolCallId}`;
    }
}
```