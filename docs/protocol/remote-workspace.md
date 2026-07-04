# 远程工作区协议

> SSH 远程工作区连接与任务同步协议分析。

---

## 远程工作区架构

```mermaid
graph TB
    subgraph Local["本地"]
        LC["ZCode 客户端"]
        subgraph SSHClient["SSH 连接层"]
            SA["SSH_AUTH_SOCK 转发"]
            PK["Private Key 认证"]
            PW["Password 认证"]
        end
    end

    subgraph Network["网络"]
        SSH["SSH 隧道"]
        WS["WebSocket 中继"]
    end

    subgraph Remote["远程服务器"]
        RS["远程 Shell"]
        subgraph Sync["任务同步"]
            TM["task_stream_mirror"]
            ST["状态同步"]
        end
    end

    LC --> SSHClient
    SSHClient --> SSH
    SSH --> RS
    RS --> TM
    TM -->|mirror 批处理| LC
    RS --> ST
    ST -->|状态更新| LC
```

---

## SSH 连接配置

```javascript
// source: host/index.js
{
    kind: "ssh",
    host: "192.168.1.100",
    port: 22,
    username: "user",
    privateKeyPath: "/path/to/key",
    passwordCredentialKey: "ssh:password:ref"  // 可选，从加密存储读取
}
```

### 环境变量白名单

SSH 会话中透传的环境变量：

| 变量 | 说明 |
|------|------|
| `SSH_AUTH_SOCK` | SSH 认证 socket 转发 |
| `AWS_PROFILE`, `AWS_REGION` | AWS 凭证 |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP 凭证 |
| `LANG`, `LC_*` | 本地化设置 |
| `TERM`, `COLORTERM` | 终端类型 |
| `XDG_CONFIG_HOME`, `XDG_DATA_HOME` | 用户配置路径 |
| `NPM_*` | Node.js 环境 |

---

## 任务同步机制

### 任务流镜像批处理

```mermaid
sequenceDiagram
    participant Local as 本地客户端
    participant Remote as 远程工作区
    participant Task as 任务引擎

    Local->>Remote: SSH 连接建立
    Remote->>Remote: 执行任务
    Remote-->>Local: task_stream_mirror_batch
    Note over Local: 镜像任务事件到本地
    Local->>Local: 合并到本地状态

    Note over Remote: 任务进度更新
    Remote-->>Local: task_stream_mirror (增量)

    Local->>Remote: 中断/停止命令
    Remote->>Task: 停止任务
    Remote-->>Local: 最终状态同步
```

---

## 协议要点

| 特性 | 说明 |
|------|------|
| 传输协议 | SSH (libssh2) |
| 认证方式 | Private Key / Password |
| 环境透传 | 白名单机制 |
| 任务同步 | `task_stream_mirror_batch` 批处理 |
| 连接管理 | 自动重连 + session 恢复 |