# 模型目录

> 从 `models_catalog_china_llm_zcode_2026-06-03.json` 提取的预配置 AI 模型目录。

---

## Z.AI / BigModel (智谱 GLM 系列)

| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| glm-5.1 | 200K | 64K | ✅ enabled |
| glm-5.1-highspeed | 200K | 64K | ✅ enabled |
| glm-5 | 200K | 64K | ✅ enabled |
| glm-5-turbo | 200K | 64K | ✅ enabled |
| glm-4.7 | 200K | 128K | ✅ enabled |
| glm-4.7-flash | 200K | 128K | ✅ enabled |
| glm-4.6 | 200K | 128K | ✅ enabled |
| glm-4.5 | 131K | 98K | ✅ enabled |
| glm-4.6v (视觉) | 131K | 32K | ❌ off |

## DeepSeek

| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| deepseek-v4-flash | **1M** | 384K | ✅ max |
| deepseek-v4-pro | **1M** | 384K | ✅ max |

## Kimi (Moonshot)

| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| kimi-k2.6 | 262K | 98K | ✅ enabled |
| kimi-k2.5 | 262K | - | ✅ enabled |

## Qwen (阿里云)

| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| qwen3.5-plus | **1M** | 64K | ✅ enabled |
| qwen3.5-flash | **1M** | 64K | ✅ enabled |
| qwen3-max | 262K | 64K | ❌ off |

## MiniMax

| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| MiniMax-M3 | **1M** | - | ❌ off |
| MiniMax-M2.7 | 204K | - | ❌ off |

## 小米 MiMo

| 模型 | 上下文 | 最大输出 | 推理 |
|------|--------|---------|------|
| mimo-v2.5-pro | **1M** | 128K | ✅ enabled |
| mimo-v2.5 | **1M** | 128K | ✅ enabled |

---

## 提供商配置

```javascript
const PRESET_PROVIDERS = [
    { id: "bigmodel",      name: "Bigmodel - API Key",  baseURL: "https://open.bigmodel.cn/api/anthropic" },
    { id: "zai",           name: "Z.ai - API Key",       baseURL: "https://api.z.ai/api/anthropic" },
    { id: "zaiStartPlan",  name: "Z.ai - Coding Plan" },
    { id: "bigmodelStartPlan", name: "BigModel - Coding Plan" },
    { id: "claude",        name: "Claude" },
    { id: "glm",           name: "GLM" },
    { id: "codex",         name: "Codex" },
    { id: "opencode",      name: "OpenCode" },
    { id: "gemini",        name: "Gemini" },
    { id: "zapi",          name: "ZAPI", baseURL: "http://192.168.6.166:8080" },
];
```

## 模型格式映射

| 提供商 | 格式 |
|--------|------|
| claude | anthropic |
| glm | anthropic, responses, openai |
| opencode | openai |
| gemini | openai |
| codex | responses, openai |
| zai | anthropic, openai |
| bigmodel | anthropic, openai |