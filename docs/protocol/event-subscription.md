# 事件流订阅与投递机制

> 实时事件流订阅 (`sessionSubscribe`) 和 `tool_result` 事件格式分析。

---

## 事件订阅架构

```mermaid
graph TB
    subgraph Client["客户端订阅者"]
        DE["desktop-continuous<br/>桌面端实时"]
        BO["bot-channel-continuous<br/>Bot 频道"]
        WR["web-remote-replayable<br/>Web 远程回放"]
    end

    subgraph Subscribe["订阅参数"]
        SS["sessionSubscribe<br/>JSON-RPC 方法"]
        SID["sessionId<br/>会话 ID"]
        DK["deliveryKind<br/>投递类型"]
        AS["afterSeq<br/>从哪条 seq 开始"]
        IS["includeSnapshot<br/>是否包含快照"]
    end

    subgraph Delivery["投递"]
        EV["事件流<br/>session/event 通知"]
        SN["快照投递<br/>sessionSnapshot"]
    end

    DE --> SS
    BO --> SS
    WR --> SS
    SS --> SID
    SS --> DK
    SS --> AS
    SS --> IS
    DK -->|"desktop-continuous"| DE
    DK -->|"bot-channel-continuous"| BO
    DK -->|"replayable → web-remote-replayable"| WR
    AS --> EV
    IS --> SN
```

---

## 订阅参数

```javascript
// source: host/index.js — sessionSubscribe 调用
{
    sessionId: "sess_xxx",               // 要订阅的会话 ID
    deliveryKind: "desktop-continuous",  // 投递类型
    afterSeq: 42,                        // 从哪条序列号之后开始接收
    includeSnapshot: true                // 是否包含历史快照
}
```

### DeliveryKind 枚举

```mermaid
flowchart LR
    DK["deliveryKind"] --> DC["desktop-continuous<br/>桌面端实时"]
    DK --> BC["bot-channel-continuous<br/>Bot 频道"]
    DK --> RP["replayable<br/>Web 远程回放"]
    RP -->|"_4() 转换"| WR["web-remote-replayable"]
```

| 值 | 用途 | 说明 |
|------|------|------|
| `desktop-continuous` | 桌面端 | 默认值，实时流式投递 |
| `bot-channel-continuous` | Bot | 机器人频道持续投递 |
| `replayable` | Web 远程 | 客户端代码中映射为 `web-remote-replayable` |

```javascript
// source: host/index.js — _4 (toZCodeDeliveryKind)
function _4(deliveryKind) {
    return deliveryKind === "replayable"
        ? "web-remote-replayable"
        : "desktop-continuous";
}
```

---

## 订阅生命周期

```mermaid
sequenceDiagram
    participant Host as Host Process
    participant Agent as ACP Agent
    participant Store as 事件存储

    Host->>Agent: sessionSubscribe
    Note over Host,Agent: {sessionId, deliveryKind, afterSeq, includeSnapshot}

    alt includeSnapshot === true
        Agent-->>Host: sessionSnapshot (历史事件)
    end

    loop 持续投递
        Agent-->>Host: session/event (seq=N+1)
        Agent-->>Host: session/event (seq=N+2)
        Agent-->>Host: session/event (seq=N+3)
    end

    Host->>Host: onDynamicSessionEvent
    Note over Host: 映射到 agent_message_chunk 等
```

---

## 事件交付驱动

```mermaid
flowchart TB
    subgraph Source["事件源"]
        AG["ACP Agent"]
        WS["WebSocket 中继"]
        SS["SSE 流"]
    end

    subgraph Subscribe["订阅管理器"]
        SUB["sessionSubscribe handler"]
        MAP["deliveryKind 映射"]
        SNAP["快照组装"]
    end

    subgraph Delivery["交付层"]
        PE["publish(event)<br/>投递到订阅者"]
        DB["dispatch(event)<br/>分发给 UI"]
    end

    subgraph Handler["事件处理"]
        ODE["onDynamicSessionEvent<br/>动态会话事件"]
    end

    AG --> SUB
    WS --> SUB
    SS --> SUB
    SUB --> MAP
    SUB --> SNAP
    MAP --> PE
    SNAP --> PE
    PE --> DB
    DB --> ODE
    ODE -->|"agent_message_chunk"| UI["UI 渲染"]
    ODE -->|"agent_thought_chunk"| UI
    ODE -->|"tool_call_update"| UI
```

---

## tool_result 事件

`tool_result` 在代码中作为 content block 类型出现，属于 **Anthropic Messages API 的 content 数组**：

```javascript
// source: zcode.cjs — 事件类型注册
{
    tool_result_warning: "tool_result",  // 事件名映射
    // 在 mid_turn_event 时触发
}
```

在处理对话历史时，`tool_result` 类型的 content block 会被**跳过**（不参与用户文本提取）：

```javascript
// source: host/index.js
function extractUserText(parts) {
    return parts.flatMap(part => {
        if (typeof part === "string") return [part];
        if (!isObject(part) || part.type === "tool_result") return [];  // ← 跳过
        // ...
    });
}
```

### tool_result 在消息中的位置

```mermaid
sequenceDiagram
    participant User as 用户
    participant Agent as Agent
    participant Tool as 工具

    User->>Agent: 用户消息
    Agent->>Tool: tool_use (请求)
    Tool-->>Agent: tool_result (结果)
    Agent->>User: assistant 回复

    Note over Agent: tool_result 作为 content block<br/>存放在 assistant 消息中
```

### 消息结构示例

```json
{
    "role": "assistant",
    "content": [
        {
            "type": "tool_use",
            "id": "toolu_xxx",
            "name": "bash",
            "input": {"command": "ls"}
        },
        {
            "type": "text",
            "text": "执行完成"
        },
        {
            "type": "tool_result",  // ← 工具执行结果
            "tool_use_id": "toolu_xxx",
            "content": "file1.txt  file2.txt"
        }
    ]
}
```

---

## 事件序列号机制

```mermaid
flowchart LR
    subgraph Event["事件"]
        SEQ["seq: N<br/>序列号"]
        TS["timestamp<br/>时间戳"]
        TYPE["type<br/>事件类型"]
        PAY["payload<br/>事件负载"]
    end

    subgraph Subscribe2["订阅"]
        AS["afterSeq: N<br/>指定起始点"]
    end

    Event -->|"新事件 seq=N+1"| Store["事件存储"]
    Subscribe2 -->|"拉取 seq > N 的事件"| Store
    Store -->|"增量投递"| Client["客户端"]
```

| 参数 | 说明 |
|------|------|
| `seq` | 单调递增序列号，用于断点续传 |
| `afterSeq` | 订阅时指定，只接收该序列号之后的事件 |
| `includeSnapshot` | 是否先接收当前全量快照，再进入增量模式 |

---

## 关键代码索引

| 函数/变量 | 位置 | 说明 |
|-----------|------|------|
| `Ie.sessionSubscribe` | host/index.js | JSON-RPC 方法名 |
| `_4()` | host/index.js | `deliveryKind` 映射 |
| `onDynamicSessionEvent()` | host/index.js | 事件分发处理 |
| `deliveryKind` 枚举 | 多处 | `desktop-continuous` / `replayable` |
| `includeSnapshot` | host/index.js | 快照标志 |
| `publish()` | host/index.js | 事件投递 |
| `tool_result` | zcode.cjs | content block 类型 |