# WebSocket / 流式管道

> ZCode 的事件流式处理管道，从模型流式输出到 Agent 事件的完整转换链。

---

## 事件转换管道

```mermaid
flowchart TB
    subgraph Model["模型输出"]
        MS["model.streaming<br/>text_delta / reasoning_delta / tool_input_delta"]
        TU["tool.updated<br/>progress"]
    end

    subgraph Coalesce["合并去重"]
        CK["CoalesceKey<br/>(session + turn + input + kind)"]
        DEDUP["去重器<br/>相同 key 的后续事件丢弃"]
    end

    subgraph Map["事件映射"]
        TO_TEXT["→ agent_message_chunk<br/>(对话文本)"]
        TO_THINK["→ agent_thought_chunk<br/>(思考过程)"]
        TO_TOOL["→ agent_tool_update<br/>(工具调用)"]
    end

    subgraph Deliver["投递"]
        RPC["JSON-RPC 通知<br/>session/event"]
    end

    MS --> CK
    TU --> CK
    CK --> DEDUP
    DEDUP --> TO_TEXT
    DEDUP --> TO_THINK
    DEDUP --> TO_TOOL
    TO_TEXT --> RPC
    TO_THINK --> RPC
    TO_TOOL --> RPC
```

---

## JSON-RPC 协议

ZCode 使用 JSON-RPC 2.0 作为 Agent ↔ Host 之间的通信协议。

### 请求格式

```json
{
    "id": 1,
    "method": "session/send",
    "params": {
        "message": "帮我写一个 Python 脚本"
    },
    "trace": {
        "traceId": "abc123"
    }
}
```

### 响应格式

```json
{
    "id": 1,
    "result": {
        "sessionId": "sess_xxx",
        "status": "processing"
    }
}
```

### 错误响应

```json
{
    "id": 1,
    "error": {
        "code": -32602,
        "message": "Invalid params",
        "data": { ... }
    }
}
```

### 通知（无需响应）

```json
{
    "method": "session/event",
    "params": {
        "type": "agent_message_chunk",
        "payload": {
            "text": "Hello!"
        }
    }
}
```

---

## 事件类型

```mermaid
mindmap
  root((事件类型))
    (模型流式事件)
      model.streaming
        text_delta
        reasoning_delta
        tool_input_delta
    (工具事件)
      tool.updated
        progress
        completed
      tool.error
    (Agent 事件)
      agent_message_chunk
      agent_thought_chunk
      agent_tool_update
      agent_error
    (会话事件)
      session/created
      session/stopped
      session/error
```

---

## 去重逻辑

ZCode 使用 CoalesceKey 机制合并重复的流式事件：

```mermaid
flowchart LR
    subgraph Events["事件流"]
        E1["model.streaming<br/>session=A, turn=1, kind=text"]
        E2["model.streaming<br/>session=A, turn=1, kind=text"]
        E3["model.streaming<br/>session=A, turn=1, kind=reasoning"]
    end

    subgraph Keys["CoalesceKey"]
        K1["model.streaming:A:1:text:X → agent_message_chunk"]
        K2["model.streaming:A:1:text:X → DEDUP"]
        K3["model.streaming:A:1:reasoning:X → agent_thought_chunk"]
    end

    E1 --> K1
    E2 --> K2
    E3 --> K3
```

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

---

## WebSocket 连接

```mermaid
sequenceDiagram
    participant Client as ZCode Client
    participant WS as WebSocket Server
    participant LLM as LLM Backend

    Client->>WS: wss://connect
    WS-->>Client: 连接确认

    Client->>WS: JSON-RPC: session/create
    WS-->>Client: session/created

    Client->>WS: JSON-RPC: session/send
    WS->>LLM: API 调用
    LLM-->>WS: SSE 流
    WS-->>Client: JSON-RPC 事件
    Note over Client: agent_message_chunk<br/>agent_thought_chunk<br/>agent_tool_update

    Client->>WS: JSON-RPC: session/stop
    WS-->>Client: session/stopped
```

---

## 远程工作区

ZCode 支持通过 SSH 连接远程工作区：

```mermaid
graph LR
    subgraph Local["本地"]
        LC[ZCode 客户端]
    end

    subgraph Remote["远程"]
        SSH[SSH 连接]
        RS[远程服务器]

        subgraph Sync["任务同步"]
            TM["task_stream_mirror_batch"]
            STATE["状态同步"]
        end
    end

    LC -->|SSH| SSH
    SSH --> RS
    RS --> TM
    RS --> STATE
    TM -->|同步| LC
    STATE -->|同步| LC
```