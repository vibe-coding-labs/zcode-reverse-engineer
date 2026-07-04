# Start Plan 激活协议分析报告

> 分析日期: 2026-07-04
> 分析方法: 逆向工程 ZCode v3.0.1 / v2.13.0 JS Bundle + 真实 API 验证
> 验证账号: CC11001100 (user_id=8009570, customer_id=49761776504527802)

---

## 一、协议概述

Start Plan 是 ZCode 的**免费入门套餐**，登录即送（无需绑卡）。激活协议的核心链路：

```
用户 → OAuth 登录 → access_token → ZCode JWT → 服务端自动授予 Start Plan
                                                      ↓
                                          billing/current 返回 active plan
                                                      ↓
                                            plans[].status === "active"
```

**关键发现：不存在客户端触发"领取/claim/activate"的 API 端点。** Start Plan 由服务端在新用户满足条件时**自动授予**。

---

## 二、协议链路详解

### 2.1 认证层（已跑通 ✅）

```
Step 1: 浏览器打开 OAuth 授权链接
  GET https://chat.z.ai/api/oauth/authorize
    ?response_type=code
    &client_id=client_P8X5CMWmlaRO9gyO-KSqtg
    &redirect_uri=http://127.0.0.1:9999/callback
    &state=<random_state>

Step 2: 授权码交换
  POST https://zcode.z.ai/api/v1/oauth/token
  → { data: { zai: { access_token: "eyJ..." } } }

Step 3: Business Token 交换
  POST https://api.z.ai/api/auth/z/login
  → { data: { access_token: "eyJ..." } }  // ZCode JWT
```

### 2.2 权益检查层（被 WAF 拦截 ❌）

```
Step 4: 检查 Start Plan 权益
  GET https://zcode.z.ai/api/v1/zcode-plan/billing/current?app_version=3.0.1
  Authorization: Bearer <ZCode JWT>
  
  期望响应:
  {
    "code": 0,
    "data": {
      "plans": [{
        "plan_id": "...",          // 含 "start-plan" 标识
        "name": "...",
        "status": "active",        // ← 关键：active 表示有权益
        "total_units": 100,
        "used_units": 30,
        "available_units": 70,
        "period_end": 1718400000
      }],
      "balances": [{ ... }]
    }
  }
  
  实际遇到: HTTP 401 空 body（WAF 拦截）
```

### 2.3 权益判定逻辑（从代码提取）

```javascript
// JS Bundle host/index.js — 权益检查函数链

// 1. Vm() — 构建 billing URL
function Vm() {
    let e = new URL(FY);  // FY = process.env.zcodePlanBillingCurrentUrl
    e.searchParams.set("app_version", fn);
    return e.toString();
    // → "https://zcode.z.ai/api/v1/zcode-plan/billing/current?app_version=3.0.1"
}

// 2. rz() — 检查 plan 是否 active
function rz(plans) {
    return !!plans?.some(plan => {
        let status = plan.status?.trim().toLowerCase();
        let planId = plan.plan_id?.trim().toLowerCase();
        let name = plan.name?.trim().toLowerCase();
        let isStartPlan = !planId && !name ? true : XN(planId) || XN(name);
        return status === "active" && isStartPlan;
    });
}

// 3. XN() — 判断是否为 Start Plan 标识
function XN(str) {
    return str ? str.includes("start-plan") || str.includes("start plan") : false;
}

// 4. JN() — 完整的验证逻辑
async function JN(provider, context) {
    let auth = await resolveStartPlanAuthorization(provider, context);
    let url = Vm();
    let response = await apiClient.request(url, {
        method: "GET",
        headers: { Authorization: auth }
    });
    let hasActivePlan = rz(response.data?.plans);
    return hasActivePlan 
        ? { kind: "available" }
        : { kind: "unavailable", reason: "coding_plan_not_entitled" };
}
```

---

## 三、WAF 拦截分析

### 3.1 问题

`zcode.z.ai/api/v1/zcode-plan/billing/current` 被阿里云 ESA WAF 防护：

| 特征 | 值 |
|------|-----|
| WAF 类型 | 阿里云 ESA (Edge Security Accelerator) |
| 拦截方式 | JS Challenge (acw_tc cookie) |
| 拦截范围 | `/api/v1/zcode-plan/*` 路径 |
| 拦截响应 | HTTP 401 空 body |
| Header 特征 | `Server: ESA`, `Set-Cookie: acw_tc=...` |

### 3.2 验证结果

| 尝试方式 | 结果 |
|----------|------|
| Python urllib (标准) | ❌ WAF 拦截 |
| Python urllib (完整浏览器 headers) | ❌ WAF 拦截 |
| Node.js https (浏览器 TLS cipher) | ❌ WAF 拦截 |
| Node.js http2 (ALPN) | ❌ 不支持 HTTP/2 |
| Python + session cookies | ❌ WAF 仍然拦截 |
| curl | ❌ WAF 拦截 |

### 3.3 原因

ESA WAF 的 JS Challenge 机制：
1. WAF 返回 `acw_tc` cookie + JS 挑战页面
2. 浏览器自动执行 JS 计算正确的 `acw_tc` 值
3. 重试请求，WAF 验证通过
4. **非浏览器客户端无法执行 JS** → 永远返回 401

### 3.4 桌面端如何绕过

ZCode 桌面端使用 **Electron 的 Chromium 网络栈**（`net.fetch()` / `net.request()`），本质上是完整的浏览器环境，能自动执行 WAF 的 JS Challenge。

---

## 四、Start Plan 授予机制（代码证据）

### 4.1 无客户端触发端点

在 9.4MB 的 `zcode.cjs` 和 1.1MB 的 `host/index.js` 中**不存在**：

- ❌ 没有 `activate Start Plan` 的 API 调用
- ❌ 没有 `claim Start Plan` 的按钮逻辑
- ❌ 没有 `领取免费额度` 的 POST 请求
- ❌ 没有 `redeem/free-trial` 等端点

### 4.2 Start Plan Preview 机制

```javascript
// 从 client configs 中获取 startPlanPreview 作为展示信息
function getStartPlanPreview() {
    let configs = await this.getClientConfigs();
    return parseStartPlanPreview(configs);
    // 返回: { planId, name, entitlements: [{ grantUnits, meter, period, showName, unitType }] }
}
```

`startPlanPreview` 仅用于 UI 展示"新用户可获赠的权益"，不是激活触发点。

### 4.3 结论

**Start Plan 是在服务端自动授予的**，授予条件可能包括：
- 用户首次通过 Z.AI OAuth 登录 ZCode
- 用户没有活跃的 Coding Plan 订阅
- 用户账号创建时间在某个阈值内

---

## 五、突破方案

### 方案 A：Playwright 真实浏览器（推荐）

```bash
# 安装 Playwright
pip install playwright
playwright install chromium

# 运行激活脚本（见 scripts/activate_playwright.py）
python scripts/activate_playwright.py
```

脚本会自动：
1. 打开 Chromium 无头浏览器
2. 访问 zcode.z.ai 首页（通过 JS Challenge）
3. 自动完成 OAuth 登录（需要用户扫码或手动输入验证码）
4. 调用 billing/current 获取真实配额数据
5. 保存结果到本地

### 方案 B：在桌面端 DevTools 中手动提取

如果你有 ZCode 桌面端：
1. 登录 ZCode
2. 打开 DevTools (`Ctrl+Shift+I`)
3. Network → 过滤 `billing/current`
4. 复制请求/响应数据

### 方案 C：直接启动 ZCode 桌面端 electron

利用现有已解压的 Linux 版二进制：

```bash
# 尝试直接运行桌面端
./data/linux-x64-extracted/squashfs-root/zcode --no-sandbox
```

---

## 六、总结

| 项目 | 状态 | 详情 |
|------|------|------|
| OAuth 认证协议 | ✅ 完整分析 | code → access_token → JWT 全部跑通 |
| Business Token 交换 | ✅ 完整分析 | api.z.ai/api/auth/z/login 已验证 |
| Start Plan 激活机制 | ✅ 完整分析 | **服务端自动授予，无客户端触发端点** |
| 权益检查协议 | ✅ 完整分析 | billing/current → plans[].status === "active" |
| WAF 突破 | ⚠️ 需要真实浏览器 | 阿里云 ESA JS Challenge 阻挡非浏览器请求 |
| 实际配额数字 | ❌ 未知 | 需通过真实浏览器环境获取 |

---

## 附录：反编译代码索引

| 代码位置 | 函数/变量 | 说明 |
|----------|----------|------|
| `host/index.js` | `FY` | billing URL (来自 env.zcodePlanBillingCurrentUrl) |
| `host/index.js` | `Vm()` | 构建 billing/current URL |
| `host/index.js` | `rz()` | 检查 plans[].status === "active" |
| `host/index.js` | `XN()` | 判断是否为 Start Plan 标识 |
| `host/index.js` | `JN()` | validateStartPlanAvailability |
| `host/index.js` | `GY()` | fetchZaiPlanEntitlementState |
| `host/index.js` | `p5()` | 解析 startPlanPreview |
| `zcode.cjs` | `slt()` | buildZCodeEndpointUrls |
| `zcode.cjs` | `Fk()` | normalizeZCodeEndpointOrigin |
| `main/index.js` | `XP()` | 构建 host process 环境变量 |