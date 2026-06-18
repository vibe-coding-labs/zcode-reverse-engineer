# ZCode Reverse Engineer

**逆向分析 ZCode (https://zcode-ai.com/) AI 编程助手的通信协议，实现反向代理。**

## 项目目标

1. ✅ 从 NSIS 安装器 / AppImage 中提取 Electron ASAR 包
2. ✅ 解包 ASAR 获取 JavaScript 源码
3. ✅ 分析 OAuth 登录授权协议
4. ✅ 分析 AI API 通信协议（Anthropic Messages API 格式）
5. ✅ 分析 ACP (Agent Communication Protocol) 代理运行时
6. ✅ **实现 MVP 验证逆向结果**

## 核心发现

### 认证流程 (OAuth 2.0)

```
1. 浏览器打开: https://chat.z.ai/api/oauth/authorize?client_id=client_P8X5CMWmlaRO9gyO-KSqtg&...
2. Callback 重定向 → 本地 HTTP 服务器接收 code
3. POST https://zcode.z.ai/api/v1/oauth/token
   Body: { "provider": "zai", "code": "...", "redirect_uri": "...", "state": "..." }
4. POST https://api.z.ai/api/auth/z/login  
   Body: { "token": "<access_token>" }
   → 返回 zcodejwttoken (JWT)
```

### AI API 协议 (Anthropic Messages API)

```
POST https://api.z.ai/api/anthropic/v1/messages
Headers:
  x-api-key: <zcode_jwt_token>         # 或 Authorization: Bearer <jwt>
  anthropic-version: "2023-06-01"
  User-Agent: "ZCode/unknown"
  HTTP-Referer: "https://zcode.z.ai"
  X-Title: "Z Code@electron"

Body (Anthropic Messages API):
{
  "model": "claude-sonnet-4-6",
  "max_tokens": 4096,
  "temperature": 0.2,
  "stream": true,
  "system": [{"type": "text", "text": "..."}],
  "messages": [{"role": "user", "content": [...]}]
}
```

### ACP (Agent Communication Protocol) 代理层

ZCode 集成了完整的 ACP 代理运行时，支持:

- **动态路由**: 通过 `x-zcode-proxy-route-key` HTTP 头控制请求路由到不同的后端
- **协议兼容**: 自动在 Anthropic / OpenAI / Gemini / Codex 格式间转换
- **Gateway 认证**: 通过 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_AUTH_TOKEN` 环境变量实现零配置代理

## MVP 使用

### 1. 安装 & 构建

```bash
cd zcode-reverse-engineer
npm install
npm run build
```

### 2. OAuth 登录 (首次)

```bash
npm run login
```
这会打开浏览器跳转到 Z.AI 登录页。登录成功后，凭证会保存到 `.zcode-credentials.json`。

### 3. 测试 AI 调用

```bash
npm run ask -- "用 TypeScript 写一个二分查找"
```

流式输出会实时显示在终端。

### 4. 启动反向代理 (供 Claude Code 等使用)

```bash
npm run proxy
```

启动后在其他终端:
```bash
# Claude Code 通过自定义网关使用 ZCode 的 AI
ANTHROPIC_BASE_URL=http://127.0.0.1:6379 ANTHROPIC_AUTH_TOKEN="" npx claude

# 或直接用 curl 测试
curl http://127.0.0.1:6379/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":256,"messages":[{"role":"user","content":"Hello"}]}'
```

## 数据文件

所有平台安装包已下载到 `data/` 目录:

| 平台 | 版本 | 文件 | 大小 |
|------|------|------|------|
| Windows x64 | 3.0.1 | `data/windows/ZCode-3.0.1-win-x64.exe` | 132 MB |
| macOS Intel | 3.0.1 | `data/mac/ZCode-3.0.1-mac-x64.dmg` | 149 MB |
| macOS ARM | 3.0.1 | `data/mac-arm64/ZCode-3.0.1-mac-arm64.dmg` | 141 MB |
| Linux x64 | 2.13.0 | `data/linux-x64/ZCode-2.13.0-linux-x64.AppImage` | 355 MB |
| Linux ARM64 | 2.13.0 | `data/linux-arm64/ZCode-2.13.0-linux-arm64.AppImage` | 355 MB |

## 源码分析索引

| 文件 | 大小 | 作用 |
|------|------|------|
| `out/host/index.js` | 1.1 MB | 网络通信层、OAuth 认证、ACP 代理路由 |
| `out/main/index.js` | 614 KB | Electron 主进程逻辑 |
| `out/renderer/assets/index-*.js` | 3.7 MB | UI 渲染进程 |
| `resources/glm/zcode.cjs` | 9.4 MB | GLM 引擎 / 自研 Agent |
| `resources/acp/dist/acp-agent.js` | 99 KB | ACP Agent 实现 (Linux v2.13.0) |
| `resources/acp-proxy-runtime/dist/*.js` | 多种 | 代理运行时 + 协议兼容层 |

## 技术栈

- **逆向目标**: Electron + TypeScript (编译为 JS bundle + chunk)
- **分析工具**: `7z`, `@electron/asar`
- **反编译**: 直接读 JS bundle (无混淆器)
- **MVP**: TypeScript + Express + Commander

## 许可证

MIT