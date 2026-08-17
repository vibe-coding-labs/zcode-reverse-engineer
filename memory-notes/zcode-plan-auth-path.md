# 免费用量鉴权路径（已从 ASAR 源码确认）

确认日期：2026-08-18
来源：`data/windows-extracted/app-64/resources/asar-out/out/host/index.js` + `chunk-J73IRXND.js`

## 结论：免费/Start Plan 走的是另一套端点，不是 api.z.ai

| | 计费方式 | Base URL | 认证头 |
|---|---|---|---|
| **API Key 渠道** | 自己的 BigModel/Z.ai API Key 按量计费 | `https://open.bigmodel.cn/api/anthropic` / `https://api.z.ai/api/anthropic` | `x-api-key: <密钥>` |
| **Coding Plan / Start Plan 渠道** | ZCode 订阅额度（含免费 Start Plan） | `https://zcode.z.ai/api/v1/zcode-plan/anthropic` | `Authorization: Bearer <zcode_jwt>` |

## 源码证据链

1. **端点由 env/origin 构建**（`chunk-J73IRXND.js` 的 `buildZCodeEndpointUrls`）：
   ```js
   zcodePlanOpenAiBaseUrl:     `${o}/api/v1/zcode-plan`,
   zcodePlanAnthropicBaseUrl:  `${o}/api/v1/zcode-plan/anthropic`,
   zcodePlanBillingCurrentUrl: `${o}/api/v1/zcode-plan/billing/current`,
   zcodePlanBillingBalanceUrl: `${o}/api/v1/zcode-plan/billing/balance`,
   ```
   其中 `o` = 生产端 `zcode.z.ai`（`out/main/chunk-KIIDSXZ3.js` `const yl="https://zcode.z.ai"`）。

2. **Auth 头决策**（`host/index.js`）：
   ```js
   let g = i?.providerId && jt(i.providerId)
       ? { Authorization: `Bearer ${a}` }   // 走订阅额度 → 用 JWT
       : { "x-api-key": a };                // 走 API Key → 用密钥
   ```
   `jt` = 提供商属于 `{zaiCodingPlan, zaiStartPlan, bigmodelCodingPlan, bigmodelStartPlan, zapi}`（`TX` 集合）→ Bearer。

3. **Start Plan/BigModel 的 JWT 取法**（`host/index.js`）：
   ```js
   // resolveBigModelStartPlanZcodeJwt
   let activeProvider = await credentialService.load("oauth:active_provider");
   if (trustCachedZcodeJwt || activeProvider === "bigmodel") {
       let jwt = await credentialService.load("zcodejwttoken");
       if (jwt) return jwt;
   }
   // 否则用 provider.apiKey
   ```
   即：`zcodejwttoken` 就是这个 Bearer 凭据。

4. **billing/current 检查**（`JN`/`VM`）：`GET ${origin}/api/v1/zcode-plan/billing/current`，headers `Authorization: Bearer <jwt>`，返回 `data.plans[].status`、`plan_id`、`total_units/used_units/available_units`、`period_end`。Start Plan 无额度时 `kind:"unavailable", reason:"coding_plan_not_entitled"`。

## 对中转站 zcode-2api 的意义

当前 zcode-2api 走的是 `https://api.z.ai/api/anthropic` + `x-api-key: <JWT 当密钥用>`。
**这不一定会扣免费额度**；免费/Start Plan 的正确入口是：
```
POST https://zcode.z.ai/api/v1/zcode-plan/anthropic/v1/messages
Authorization: Bearer <zcode_jwt>
```
需要实测确认该入口对免费账号返回模型响应，并核对 billing/current 的额度扣减。