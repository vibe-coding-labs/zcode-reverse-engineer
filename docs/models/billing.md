# Coding Plan 付费流程分析

> Stripe/PayPal/支付宝多渠道支付体系分析。

---

## 支付架构总览

```mermaid
graph TB
    subgraph Client["ZCode 客户端"]
        PAY["付费服务层<br/>createSign / payStripe / subscribePaypal"]
        CFG["客户端配置<br/>codingPlanStaticProducts"]
    end

    subgraph API["支付网关 API"]
        CREATE["/pay/create-sign<br/>支付宝/微信签名"]
        CHECK["/pay/check<br/>支付状态"]
        PENDING["/pay/check-pending-orders<br/>待处理订单"]

        STRIPE["/stripe/query<br/>/stripe/bind<br/>/stripe/pay<br/>/stripe/unbind"]

        PAYPAL["/paypal/isSupport<br/>/paypal/setupToken<br/>/paypal/subscribe"]
    end

    subgraph Provider["提供商"]
        ALI["支付宝 ALI"]
        WX["微信支付 WX"]
        STRIPE_GW["Stripe"]
        PAYPAL_GW["PayPal"]
    end

    CLIENT --> |"getStaticProducts"| CFG
    PAY --> CREATE
    PAY --> STRIPE
    PAY --> PAYPAL
    CREATE --> ALI
    CREATE --> WX
    STRIPE --> STRIPE_GW
    PAYPAL --> PAYPAL_GW
    PAY --> CHECK
    PAY --> PENDING
```

---

## 产品定价

从客户端配置 `codingPlanStaticProducts` 提取的定价方案：

| 产品 | 价格 | 说明 |
|------|------|------|
| **GLM Coding Lite** | **¥49/月** | 基础编程套餐 |
| **GLM Coding Pro** | **¥149/月** | Lite 的 5 倍额度 |
| **GLM Coding Pro Max** | **¥469/月** | Pro 的 4 倍额度 |

### 产品配置结构

```javascript
// 从 client/configs 响应中提取
{
    "codingPlanStaticProducts": {
        "builtin:bigmodel-coding-plan": [
            {
                "productId": "product-02434c",
                "productName": "GLM Coding Lite",
                "productSmallTitle": "超值订阅，轻松畅享顶级编程体验",
                "description": "3x Claude Pro 用量额度",
                "monthlyOriginalAmount": 49,
                "monthlyPayAmount": 49,
                "monthlyRenewAmount": 49,
                "discountAmount": 49,
                "priceCurrency": "CNY",
                "priceUnit": "month",
                "displayOrder": 1,
                "productEquityList": [
                    {
                        "productEquityTitle": "GLM-5.1 驱动",
                        "productEquityDetails": "为 ZCode 编码体验优化"
                    }
                ]
            }
        ]
    }
}
```

---

## 支付流程

### 支付宝/微信支付

```mermaid
sequenceDiagram
    participant User as 用户
    participant App as ZCode App
    participant API as api.z.ai
    participant Alipay as 支付宝/微信

    User->>App: 点击购买 GLM Coding Lite
    App->>API: POST /pay/create-sign
    Note over API: {bizId, payType: "ALI", invitationCode, renew}
    API-->>App: 支付签名
    App->>Alipay: 唤起支付宝客户端
    Alipay-->>User: 用户确认支付
    Alipay-->>API: 异步通知支付结果
    App->>API: POST /pay/check
    Note over API: {bizId}
    API-->>App: 支付成功
    App->>User: 订阅激活
    App->>API: GET /biz/subscription/list
    API-->>App: [{plan_id: "coding_plan", status: "active"}]
```

### Stripe 支付

```mermaid
sequenceDiagram
    participant User as 用户
    participant App as ZCode App
    participant API as api.z.ai
    participant Stripe as Stripe

    User->>App: 点击购买
    App->>API: POST /stripe/query
    API-->>App: 已绑卡列表
    alt 没有绑卡
        App->>API: POST /stripe/bind
        Note over API: {paymentMethodId, returnUrl}
        App->>Stripe: 跳转 Stripe Checkout
        Stripe-->>User: 绑卡/支付
        Stripe-->>API: 回调
    end
    App->>API: POST /stripe/pay
    Note over API: {productId, paymentMethodId, isSubscribe: true}
    API-->>App: 支付成功
    App->>User: 订阅激活
```

### PayPal 支付

```mermaid
sequenceDiagram
    participant User as 用户
    participant App as ZCode App
    participant API as api.z.ai
    participant PayPal as PayPal

    App->>API: GET /paypal/isSupport
    API-->>App: 是否支持 PayPal

    App->>API: POST /paypal/setupToken
    Note over API: {returnUrl, cancelUrl}
    API-->>App: setupToken
    App->>PayPal: 跳转 PayPal 授权
    PayPal-->>User: 用户确认

    App->>API: POST /paypal/subscribe
    Note over API: {productId, setupTokenId, amount}
    API-->>App: 订阅成功
```

---

## API 端点

### 通用支付

| 端点 | 方法 | 说明 |
|------|------|------|
| `/pay/create-sign` | POST | 支付宝/微信支付签名 |
| `/pay/check` | GET | 查询支付状态 |
| `/pay/check-pending-orders` | GET | 待处理订单 |
| `/pay/product/update/sign` | POST | 续费签名 |

### Stripe

| 端点 | 方法 | 说明 |
|------|------|------|
| `/stripe/query` | GET | 查询已绑卡 |
| `/stripe/bind` | POST | 绑定新卡 |
| `/stripe/unbind` | POST | 解绑 |
| `/stripe/pay` | POST | 支付/订阅 |

### PayPal

| 端点 | 方法 | 说明 |
|------|------|------|
| `/paypal/isSupport` | GET | 是否支持 |
| `/paypal/setupToken` | POST | 创建授权 token |
| `/paypal/subscribe` | POST | 订阅 |

---

## 代码实现

### 支付服务层

```javascript
// source: host/index.js — 支付服务类

// 获取产品列表
async function getStaticProducts() {
    let configs = await this.getClientConfigs();
    return parseStaticProducts(configs);
}

// 查询 Stripe 已绑卡
async function queryStripeCards() {
    return this.getZaiPay(providerId, "/stripe/query");
}

// Stripe 绑卡
async function bindStripeCard(data) {
    return this.postZaiPay(providerId, "/stripe/bind", {
        paymentMethodId: data.paymentMethodId,
        returnUrl: data.returnUrl,
        trackingContext: data.trackingContext
    });
}

// Stripe 支付
async function payStripe(data) {
    return this.postZaiPay(providerId, "/stripe/pay", {
        productId: data.productId,
        paymentMethodId: data.paymentMethodId,
        isSubscribe: true,
        returnUrl: data.returnUrl,
        channelCode: data.channelCode,
        estimatePayAmount: data.estimatePayAmount,
        invitationCode: data.invitationCode
    });
}

// PayPal 订阅
async function subscribePaypal(data) {
    return this.postZaiPay(providerId, "/paypal/subscribe", {
        productId: data.productId,
        setupTokenId: data.setupTokenId,
        amount: data.amount,
        isSubscribe: true,
        estimatePayAmount: data.estimatePayAmount,
        invitationCode: data.invitationCode
    });
}

// 支付宝/微信签名
async function createSign(data) {
    return this.post(providerId, "/pay/create-sign", {
        bizId: data.bizId,
        payType: data.payType || "ALI",
        invitationCode: data.invitationCode,
        renew: data.renew
    });
}
```

---

## 订阅状态

| 状态 | 说明 |
|------|------|
| `coding_plan_zai_overseas_payment_required` | 海外用户需要额外支付验证 |
| `coding_plan_not_auth` | 未登录 |
| `coding_plan_auth_failed` | Token 过期/无效 |
| `coding_plan_not_entitled` | 无订阅 |
| `oauth_provider_inactive` | OAuth 提供商未激活 |

---

## 完整支付链路

```mermaid
flowchart TB
    A["用户选择产品"] --> B{"支付方式"}
    B -->|"支付宝/微信"| C["POST /pay/create-sign<br/>payType=ALI/WX"]
    B -->|"Stripe"| D["POST /stripe/bind<br/>绑卡"]
    B -->|"PayPal"| E["POST /paypal/setupToken<br/>创建授权"]

    C --> F["用户完成支付"]
    D --> G["POST /stripe/pay<br/>扣款订阅"]
    E --> H["POST /paypal/subscribe<br/>确认订阅"]

    F --> I["POST /pay/check<br/>验证支付状态"]
    G --> I
    H --> I

    I --> J{"成功?"}
    J -->|"是"| K["GET /biz/subscription/list<br/>→ 订阅激活"]
    J -->|"否"| L["提示错误"]
```