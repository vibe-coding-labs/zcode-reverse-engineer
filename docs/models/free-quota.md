# 免费/Start Plan 额度与鉴权路径

> 逆向确认（2026-08-18）：ZCode 的免费额度（Start Plan）走独立端点，且公开配置可验证。

---

## 免费额度（Start Plan）——公开可验证

`GET https://zcode.z.ai/api/v1/client/configs?app_version=3.0.1`（**无需任何认证**）返回 `data.configs.startPlanPreview`：

| 模型 | 每日额度 | 周期 | 单位 |
|------|----------|------|------|
| **GLM-5.3**（旗舰，原 GLM-5.2） | **3,000,000 tokens** | 每日 | token |
| **GLM-5-Turbo**（≈ Sonnet 级别） | **2,000,000 tokens** | 每日 | token |

- 两模型独立计算、每日重置
- **`showName` 官方可随时调整**（2026-06 分析时为 GLM-5.2，2026-08-18 实测已为 GLM-5.3），`grantUnits` 数字不变
- 免费额度是**使用时服务器侧按账号自动授予**；「免费/Start Plan 账户是否被授予」由服务端判定，客户端无需硬编码

## 鉴权路径（ASAR 源码实锤）

ZCode 有两条互不相干的请求通道：

| 通道 | 计费 | Base URL | 认证头 |
|------|------|----------|--------|
| **API Key 通道** | 用户自己的 BigModel/Z.ai API Key 按量计费 | `https://open.bigmodel.cn/api/anthropic` / `https://api.z.ai/api/anthropic` | `x-api-key: <密钥>` |
| **Plan 通道**（免费 Start Plan + 付费 Coding Plan） | ZCode 账号额度 | `https://zcode.z.ai/api/v1/zcode-plan/anthropic` | `Authorization: Bearer <zcode_jwt>` |

### 端点构建（`out/host/chunk-J73IRXND.js`）

```js
zcodePlanOpenAiBaseUrl:     `${o}/api/v1/zcode-plan`,
zcodePlanAnthropicBaseUrl:  `${o}/api/v1/zcode-plan/anthropic`,
zcodePlanBillingCurrentUrl: `${o}/api/v1/zcode-plan/billing/current`,
zcodePlanBillingBalanceUrl: `${o}/api/v1/zcode-plan/billing/balance`,
```

其中 `o` = 生产端 `https://zcode.z.ai`。

### 认证头决策（`out/host/index.js`）

```js
let g = i?.providerId && jt(i.providerId)
    ? { Authorization: `Bearer ${a}` }   // 走订阅额度 → 用 JWT
    : { "x-api-key": a };                // 走 API Key → 用密钥
```

`jt` = 提供商属于 `{zaiCodingPlan, zaiStartPlan, bigmodelCodingPlan, bigmodelStartPlan, zapi}`（`TX` 集合）→ Bearer。

### 额度检查

- `GET ${origin}/api/v1/zcode-plan/billing/current`（Bearer JWT）→ `data.plans[]`：
  `plan_id`、`status`、`total_units` / `used_units` / `available_units`、`period_end`
- `GET ${origin}/api/v1/zcode-plan/billing/balance`（Bearer JWT）→ `data.balances[]`

## 账号侧验证记录（2026-08-18）

| 请求 | 结果 | 说明 |
|------|------|------|
| `GET api.z.ai/api/biz/subscription/list`（Bearer JWT） | `{"code":200,"data":[]}` | 无付费订阅 = 免费用户 |
| `GET api.z.ai/api/monitor/usage/quota/limit` | `{"code":500,"msg":"当前用户不存在coding plan"}` | 免费用户无 coding plan 配额接口 |
| `GET zcode.z.ai/api/v1/zcode-plan/billing/current` | 401（JWT 已过期） | 过期 token 的结果，不代表无免费额度 |
| `GET zcode.z.ai/api/v1/client/configs` | 200（无需认证） | **免费额度公开可拉** |

> 注意：`billing/current` 返回 401 通常是 JWT 过期，不代表免费额度不存在。免费额度在调用模型时由服务器扣减。

## 相关实现

- 中转站 `zcode-2api` 已实现：`quota` 命令、JWT 自动续期、多账号额度感知轮换，详见 `zcode-2api/docs/FREE_QUOTA.md`