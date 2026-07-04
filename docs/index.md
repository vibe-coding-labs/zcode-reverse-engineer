# ZCode Reverse Engineer

> ZCode AI 编程助手通信协议逆向分析文档

---

## 项目概述

本项目对 [ZCode](https://zcode-ai.com/) 桌面客户端 (v3.0.1 Windows / v2.13.0 Linux) 进行逆向工程，分析其通信协议与认证架构。

### 分析范围

<div class="grid cards" markdown>

-   :material-lock-open-variant-outline: **OAuth 授权协议**

    ---

    完整分析 ZCode 的 OAuth 2.0 授权码流程，包括 PKCE、Token 交换、Business JWT 签发。

-   :material-cloud-outline: **AI 通信协议**

    ---

    Anthropic Messages API 格式的调用链路、认证头部、流式响应处理。

-   :material-vector-polyline: **ACP 代理运行时**

    ---

    动态路由、协议转换 (Anthropic ↔ OpenAI ↔ Gemini)、Gateway 认证、MITM 代理。

-   :material-currency-usd: **计费与订阅**

    ---

    Start Plan 免费套餐激活协议、Coding Plan 订阅管理、配额查询 API。

-   :material-database-outline: **模型目录**

    ---

    21个预配置 AI 模型，包括 GLM-5、DeepSeek-V4、Kimi K2、Qwen 3.5 等。

-   :material-webhook: **WebSocket / 流式管道**

    ---

    事件转换管道、JSON-RPC 协议、流式响应去重合并。

</div>

### 技术栈

| 项目 | 说明 |
|------|------|
| **目标平台** | Windows x64 (v3.0.1), Linux x64 (v2.13.0) |
| **提取方法** | NSIS 7z 解包 / AppImage extract → ASAR 提取 |
| **分析语言** | JavaScript (Webpack bundle), TypeScript |
| **验证工具** | Python, Node.js, Playwright |

### 当前状态

| 模块 | 完成度 | 说明 |
|------|--------|------|
| OAuth 授权协议 | ✅ 100% | 完整流程已实机验证 |
| Business Token 交换 | ✅ 100% | JWT 获取与解码 |
| API 端点目录 | ✅ 100% | 所有认证/计费/AI 端点 |
| Start Plan 激活协议 | ✅ 100% | 服务端自动授予，WAF 分析 |
| 模型目录 | ✅ 100% | 21个模型完整 catalog |
| 订阅/计费 API | ✅ 90% | 端点已知，配额数字需真实登录 |
| Coding Plan 付费流程 | ❌ 未开始 | Stripe/PayPal 支付链路 |
| WebSocket 流式管道 | ❌ 未开始 | SSE 事件管道实现 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 本地构建文档站

```bash
mkdocs serve
# 访问 http://127.0.0.1:8000
```

### 3. 运行 OAuth 授权

```bash
# 方式一：浏览器自动打开
python zcode_auth.py login

# 方式二：手动粘贴回调 URL（推荐用于无桌面环境）
python zcode_auth.py code "<回调URL>"

# 查看配额信息
python zcode_auth.py quota
```

详见 [OAuth 授权流程](auth-flow.md) 文档。

---

## 项目结构

```
.
├── docs/                       # 文档站 (MkDocs)
│   ├── auth-flow.md            # OAuth 授权流程文档
│   ├── activation-protocol.md  # Start Plan 激活协议
│   ├── ANALYSIS_REPORT.md      # 完整逆向分析报告
│   └── reference/              # 参考资料
├── scripts/                    # 诊断/激活脚本
├── data/                       # 提取的二进制和源码
├── zcode_auth.py               # OAuth 自动化脚本
├── mkdocs.yml                  # 文档站配置
└── README.md                   # 项目说明
```

---

## 相关链接

- :material-web: [ZCode 官网](https://zcode-ai.com/)
- :material-chat: [Z.AI 登录](https://chat.z.ai/)
- :material-github: [GitHub 仓库](https://github.com/vibe-coding-labs/zcode-reverse-engineer)