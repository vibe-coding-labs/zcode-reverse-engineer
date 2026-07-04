# API 端点目录

> 通过逆向分析 ZCode v3.0.1 / v2.13.0 JS Bundle 提取的所有 API 端点。

---

## 认证相关

| 端点 | 用途 | 方法 | 认证方式 |
|------|------|------|---------|
| `https://chat.z.ai/api/oauth/authorize` | OAuth 授权 | GET | 用户交互 |
| `https://zcode.z.ai/api/v1/oauth/token` | Token 交换 | POST | 授权码 |
| `https://api.z.ai/api/auth/z/login` | Business JWT 交换 | POST | access_token |
| `https://chat.z.ai/api/oauth/userinfo` | 用户信息 | GET | Bearer access_token |
| `https://chat.z.ai/api/v1/auths/` | 游客会话 | GET | 无 |

## 套餐/计费

| 端点 | 用途 | 认证方式 | 状态 |
|------|------|---------|------|
| `https://zcode.z.ai/api/v1/zcode-plan/billing/current` | Start Plan 账单 | Bearer JWT (zcode.z.ai session) | ⚠️ WAF 拦截 |
| `https://zcode.z.ai/api/v1/zcode-plan/billing/balance` | Start Plan 余额 | Bearer JWT (zcode.z.ai session) | ⚠️ WAF 拦截 |
| `https://api.z.ai/api/biz/subscription/list` | Coding Plan 订阅 | Bearer JWT | ✅ 可用 |
| `https://api.z.ai/api/monitor/usage/quota/limit` | 使用配额 | Bearer JWT | ✅ 可用 |
| `https://zcode.z.ai/api/v1/client/configs` | 客户端配置 | 无 | ✅ 可用 |
| `https://open.bigmodel.cn/api/biz/subscription/list` | BigModel 订阅 | Bearer JWT | ✅ 可用 |

## AI API

| 端点 | 用途 | 认证方式 |
|------|------|---------|
| `https://api.z.ai/api/anthropic/v1/messages` | AI 对话 (Z.AI) | x-api-key JWT |
| `https://open.bigmodel.cn/api/anthropic/v1/messages` | AI 对话 (BigModel) | x-api-key API Key |

### 请求格式

```http
POST https://api.z.ai/api/anthropic/v1/messages
Content-Type: application/json
x-api-key: <zcode_jwt_token>
anthropic-version: 2023-06-01

{
    "model": "glm-5.1",
    "max_tokens": 64000,
    "stream": true,
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
    ]
}
```

## OAuth 配置

### Z.AI (默认)

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
}
```

### BigModel (智谱 AI)

```javascript
{
    id: "zcode",
    displayName: "BigModel",
    authorizeUrl: "https://bigmodel.cn/login",
    tokenUrl: "https://zcode.z.ai/api/v1/oauth/token",
    userinfoUrl: "https://zcode.z.ai/api/oauth/userinfo",
    appId: "zcode",
    redirectUri: "zcode://oauth/callback",
}
```

## 请求头规范

```javascript
{
    "User-Agent": "ZCode/${appVersion}",
    "HTTP-Referer": "https://zcode.z.ai",
    "X-Title": "Z Code@electron",
    "X-ZCode-App-Version": appVersion,
    "X-Platform": "${platform}-${arch}",
    "X-Release-Channel": "production",
    "X-Client-Language": locale,
    "X-Client-Timezone": timezone,
    "X-Os-Category": osCategory,
}
```