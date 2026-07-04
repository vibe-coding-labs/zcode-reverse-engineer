import { defineConfig } from 'vitepress'

export default defineConfig({
  base: '/zcode-reverse-engineer/',
  title: 'zcode工具逆向分析',
  description: 'zcode工具逆向分析',
  lang: 'zh-CN',
  lastUpdated: true,
  ignoreDeadLinks: true,
  markdown: {
    lineNumbers: true,
  },
  themeConfig: {
    search: {
      provider: 'local',
    },
    nav: [
      { text: '文档首页', link: '/' },
      { text: 'GitHub', link: 'https://github.com/vibe-coding-labs/zcode-reverse-engineer' },
    ],
    sidebar: [
          { text: "zcode工具逆向分析", items: [
            { text: "首页", link: "/" },
            { text: "ZCode Reverse Engineering — 完整分析报告", link: "/ANALYSIS_REPORT" },
            { text: "ACP 代理运行时", link: "/acp-proxy" },
            { text: "Start Plan 激活协议分析报告", link: "/activation-protocol" },
            { text: "AI 通信协议", link: "/ai-protocol" },
            { text: "ZCode OAuth 授权流程完整文档", link: "/auth-flow" },
            { text: "通信协议总览", link: "/protocol-overview" },
            { text: "API 端点目录", link: "/reference/api-endpoints" },
            { text: "计费与订阅", link: "/reference/billing" },
            { text: "模型目录", link: "/reference/model-catalog" },
            { text: "项目结构", link: "/reference/project-structure" },
            { text: "WebSocket / 流式管道", link: "/websocket-pipeline" },
          ] }
        ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/vibe-coding-labs/zcode-reverse-engineer' },
    ],
    footer: {
      message: '基于 VitePress 构建',
    },
  },
})
