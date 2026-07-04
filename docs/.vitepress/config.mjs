import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'ZCode RE',
  description: 'ZCode AI 编程助手通信协议逆向分析',
  lang: 'zh-CN',

  head: [
    ['link', { rel: 'icon', href: '/favicon.svg', type: 'image/svg+xml' }],
  ],

  themeConfig: {
    logo: '/favicon.svg',

    // ===== 现代配色 =====
    nav: [
      { text: '🏠 首页', link: '/' },
      {
        text: '🔐 授权协议',
        items: [
          { text: 'OAuth 授权流程', link: '/auth/oauth-flow' },
          { text: 'Start Plan 激活', link: '/auth/activation-protocol' },
          { text: '凭据与安全', link: '/auth/credentials' },
        ],
      },
      {
        text: '📡 通信协议',
        items: [
          { text: '协议总览', link: '/protocol/overview' },
          { text: 'AI 通信协议', link: '/protocol/ai-protocol' },
          { text: 'ACP 代理运行时', link: '/protocol/acp-proxy' },
          { text: 'WebSocket 流式管道', link: '/protocol/websocket-pipeline' },
          { text: '远程工作区', link: '/protocol/remote-workspace' },
          { text: 'Agent 运行时', link: '/protocol/agent-runtime' },
        ],
      },
      {
        text: '🗃️ 模型与计费',
        items: [
          { text: '模型目录', link: '/models/catalog' },
          { text: '套餐与配额', link: '/models/billing' },
        ],
      },
      {
        text: '📖 参考资料',
        items: [
          { text: 'API 端点目录', link: '/reference/api-endpoints' },
          { text: '项目结构', link: '/reference/project-structure' },
          { text: '完整分析报告', link: '/reference/analysis-report' },
        ],
      },
    ],

    // ===== 详细侧边栏 =====
    sidebar: {
      '/auth/': [
        {
          text: '🔐 授权协议',
          collapsed: false,
          items: [
            {
              text: 'OAuth 授权流程',
              link: '/auth/oauth-flow',
            },
            {
              text: 'Start Plan 激活协议',
              link: '/auth/activation-protocol',
            },
            {
              text: '凭据与安全',
              link: '/auth/credentials',
            },
          ],
        },
        {
          text: '📖 快速参考',
          collapsed: true,
          items: [
            { text: '常见问题', link: '/auth/oauth-flow#常见问题' },
            { text: 'curl 命令链', link: '/auth/oauth-flow#完整-curl-命令链' },
            { text: 'Python 脚本', link: '/auth/oauth-flow#python-脚本使用指南' },
          ],
        },
      ],

      '/protocol/': [
        {
          text: '📡 通信协议',
          collapsed: false,
          items: [
            {
              text: '协议总览',
              link: '/protocol/overview',
            },
            {
              text: 'AI 通信协议',
              link: '/protocol/ai-protocol',
            },
            {
              text: 'ACP 代理运行时',
              link: '/protocol/acp-proxy',
            },
            {
              text: 'WebSocket 流式管道',
              link: '/protocol/websocket-pipeline',
            },
          ],
        },
        {
          text: '🔗 相关主题',
          collapsed: true,
          items: [
            { text: 'API 端点', link: '/reference/api-endpoints' },
            { text: '模型目录', link: '/models/catalog' },
          ],
        },
      ],

      '/models/': [
        {
          text: '🗃️ 模型与计费',
          collapsed: false,
          items: [
            {
              text: '模型目录',
              link: '/models/catalog',
            },
            {
              text: '套餐与配额',
              link: '/models/billing',
            },
          ],
        },
      ],

      '/reference/': [
        {
          text: '📖 参考资料',
          collapsed: false,
          items: [
            {
              text: 'API 端点目录',
              link: '/reference/api-endpoints',
            },
            {
              text: '项目结构',
              link: '/reference/project-structure',
            },
            {
              text: '完整分析报告',
              link: '/reference/analysis-report',
            },
          ],
        },
      ],
    },

    // ===== 社交 =====
    socialLinks: [
      { icon: 'github', link: 'https://github.com/vibe-coding-labs/zcode-reverse-engineer' },
    ],

    // ===== 页脚 =====
    footer: {
      message: '基于 GPL-3.0 协议开源',
      copyright: 'Copyright © 2026 Vibe Coding Labs',
    },

    // ===== 编辑链接 =====
    editLink: {
      pattern: 'https://github.com/vibe-coding-labs/zcode-reverse-engineer/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页',
    },

    // ===== 搜索 =====
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
          modal: { noResultsText: '未找到结果', resetButtonTitle: '清除' },
        },
      },
    },

    // ===== 大纲 =====
    outline: {
      level: [2, 4],
      label: '本页目录',
    },

    // ===== 上次更新 =====
    lastUpdated: {
      text: '最后更新',
    },

    // ===== 文档底部导航 =====
    docFooter: {
      prev: '上一页',
      next: '下一页',
    },

    // ===== 返回顶部 =====
    returnToTopLabel: '返回顶部',

    // ===== 暗色模式 =====
    darkModeSwitchLabel: '切换主题',
    lightModeSwitchTitle: '切换亮色模式',
    darkModeSwitchTitle: '切换暗色模式',
  },

  // ===== Markdown =====
  markdown: {
    image: { lazyLoading: true },
    lineNumbers: true,
    theme: {
      light: 'github-light',
      dark: 'github-dark',
    },
  },

  // ===== 清理 URL =====
  cleanUrls: true,
  ignoreDeadLinks: [/^.*$/,
    /^#\d+-/,
    /^\.\.\/ANALYSIS_REPORT/,
    /\.md$/,
    /\/auth-flow\b/,
    /\/acp-proxy\b/,
    /\/ai-protocol\b/,
  ],

  lastUpdated: true,
})