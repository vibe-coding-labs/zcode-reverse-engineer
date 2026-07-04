# 项目结构

> ZCode Reverse Engineer 项目文件说明。

---

## 顶层目录

```
.
├── docs/                        # MkDocs 文档站源文件
│   ├── index.md                 # 首页
│   ├── auth-flow.md             # OAuth 授权流程文档
│   ├── activation-protocol.md   # Start Plan 激活协议文档
│   ├── ANALYSIS_REPORT.md       # 完整逆向分析报告 (symlink)
│   └── reference/               # 参考资料
│       ├── api-endpoints.md     # API 端点目录
│       ├── model-catalog.md     # 模型目录
│       └── project-structure.md # 本文件
├── scripts/                     # 诊断和激活脚本
│   ├── activate.cjs             # Node.js WAF bypass 尝试
│   ├── activate_playwright.py   # Playwright 浏览器模式脚本
│   ├── capture_login.py         # OAuth 登录流程捕获
│   ├── test_billing.py          # billing/current API 测试
│   └── trace_login.py           # 无头浏览器登录追踪
├── data/                        # 提取的二进制文件和源码
│   ├── windows/                 # Windows 安装包
│   ├── windows-extracted/       # Windows ASAR 提取结果
│   ├── linux-x64/               # Linux AppImage
│   ├── linux-x64-extracted/     # Linux AppImage 提取结果
│   └── credentials/             # 认证凭据 (gitignored)
├── src/                         # 分析辅助源码
│   ├── oauth.ts                 # OAuth 流程 TypeScript 分析
│   └── types.ts                 # 类型定义
├── dist/                        # 编译输出 (gitignored)
├── zcode_auth.py                # Python OAuth 自动化脚本
├── mkdocs.yml                   # MkDocs 配置
├── README.md                    # 项目说明
├── ANALYSIS_REPORT.md           # 完整逆向分析报告
├── package.json                 # Node.js 依赖
└── .gitignore                   # Git 忽略规则
```

## docs/ 目录

MkDocs 文档站源文件，使用 Material for MkDocs 主题渲染。

```bash
# 本地预览
mkdocs serve

# 构建静态站点
mkdocs build

# 部署到 GitHub Pages
mkdocs gh-deploy
```

## 脚本说明

### zcode_auth.py

Python OAuth 自动化脚本，支持多模式操作：

| 命令 | 功能 |
|------|------|
| `login` | 完整 OAuth 登录（浏览器自动打开） |
| `code <URL>` | 手动粘贴回调 URL |
| `quota` | 查询配额和套餐信息 |
| `whoami` | 显示当前登录用户信息 |
| `check` | 测试所有 API 端点连通性 |
| `refresh` | 刷新过期 Token |
| `guest` | 游客模式（研究用） |

### scripts/activate_playwright.py

通过 Playwright 驱动真实 Chromium 浏览器，绕过 WAF 验证 Start Plan。

```bash
pip install playwright
playwright install chromium
python scripts/activate_playwright.py check
```

## 数据文件

`data/` 目录包含提取的原始二进制文件和反编译源码：

```
data/
├── windows/ZCode-3.0.1-win-x64.exe     # Windows 安装包
├── windows-extracted/app-64/           # Windows 提取的 ASAR 内容
│   └── resources/asar-out/             # 反编译后的 JS bundle
│       ├── out/host/index.js           # 网络通信层 (1.1 MB)
│       ├── out/main/index.js           # 主进程逻辑 (614 KB)
│       └── out/renderer/               # UI 渲染进程 (3.7 MB)
├── linux-x64/ZCode-2.13.0-linux-x64.AppImage
└── linux-x64-extracted/
    └── squashfs-root/resources/
        ├── glm/zcode.cjs               # GLM Agent 引擎 (9.4 MB)
        └── acp/dist/                   # ACP 代理运行时
```