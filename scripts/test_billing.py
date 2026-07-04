#!/usr/bin/env python3
"""
ZCode billing/current — 在浏览器页面上下文中执行请求，
带上首页 session cookie + Bearer JWT，验证 Start Plan 权益。
"""
import asyncio, json, os, sys

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".zcode_credentials.json")

def load_jwt():
    try:
        with open(CREDENTIALS_FILE) as f:
            return json.load(f).get("zcode_jwt_token", "")
    except: return None

async def main():
    jwt = load_jwt()
    if not jwt:
        print("❌ 未找到 JWT，请先运行 python zcode_auth.py login")
        sys.exit(1)

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        page = await context.new_page()

        # Step 1: 监听 billing 请求和响应
        billing_result = {}

        async def on_response(response):
            url = response.url
            if "zcode-plan/billing/current" in url or "zcode-plan/billing/balance" in url:
                try:
                    body = await response.json()
                except:
                    body = await response.text()
                billing_result[url] = {
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                }
                print(f"\n  ← {response.status} {url.split('?')[0]}")
                print(f"    Headers: {dict(response.headers)}")
                print(f"    Body: {json.dumps(body, indent=2, ensure_ascii=False)[:500] if isinstance(body, dict) else body}")

        page.on("response", on_response)

        # Step 2: 加载首页（建立 session cookie）
        print("1. 加载首页（建立 session）...")
        await page.goto("https://zcode.z.ai/", wait_until="domcontentloaded", timeout=30000)
        print(f"   首页加载完成")

        # 查看已经有了哪些 cookie
        cookies = await context.cookies()
        print(f"   Cookies: {[f'{c[\"name\"]}={c[\"value\"][:20]}...' for c in cookies]}")

        # Step 3: 通过 page.evaluate 在页面中发 fetch 请求
        # 这样 session cookie + 请求头都会被带上
        print("\n2. 在页面上下文中 fetch billing/current...")
        result = await page.evaluate(f"""
            async () => {{
                const url = 'https://zcode.z.ai/api/v1/zcode-plan/billing/current?app_version=3.0.1';
                const resp = await fetch(url, {{
                    headers: {{
                        'Authorization': 'Bearer {jwt}',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    }}
                }});
                const text = await resp.text();
                let data = null;
                try {{ data = JSON.parse(text); }} catch(e) {{}}
                return {{
                    status: resp.status,
                    statusText: resp.statusText,
                    body: data || text,
                    headers: Object.fromEntries([...resp.headers]),
                }};
            }}
        """)

        print(f"  Status: {result['status']} {result['statusText']}")
        if isinstance(result['body'], dict):
            print(f"  Body: {json.dumps(result['body'], indent=2, ensure_ascii=False)[:1000]}")
        else:
            print(f"  Body: {result['body'][:300] or '(empty)'}")
        print()

        # Step 4: 也试 balance
        print("3. fetch billing/balance...")
        result2 = await page.evaluate(f"""
            async () => {{
                const url = 'https://zcode.z.ai/api/v1/zcode-plan/billing/balance?app_version=3.0.1';
                const resp = await fetch(url, {{
                    headers: {{
                        'Authorization': 'Bearer {jwt}',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    }}
                }});
                const text = await resp.text();
                let data = null;
                try {{ data = JSON.parse(text); }} catch(e) {{}}
                return {{
                    status: resp.status,
                    body: data || text,
                }};
            }}
        """)
        print(f"  Status: {result2['status']}")
        if isinstance(result2['body'], dict):
            print(f"  Body: {json.dumps(result2['body'], indent=2, ensure_ascii=False)[:1000]}")
        else:
            print(f"  Body: {result2['body'][:300] or '(empty)'}")
        print()

        # Step 5: 如果 billing 仍然 401，尝试看看 zcode.z.ai 的
        # 登录页面/API，了解它的认证机制
        if result['status'] == 401:
            print("4. 探测 zcode.z.ai 的认证机制...")

            # 试一下 zcode.z.ai 本身有没有登录 API
            endpoints = [
                ("GET", "/api/auth/session"),
                ("GET", "/api/auth/csrf"),
                ("GET", "/api/me"),
            ]
            for method, path in endpoints:
                url = f"https://zcode.z.ai{path}"
                resp_data = await page.evaluate(f"""
                    async () => {{
                        const resp = await fetch('{url}', {{ method: '{method}' }});
                        const text = await resp.text();
                        return {{ status: resp.status, body: text.slice(0, 200) }};
                    }}
                """)
                print(f"  [{method}] {url} → {resp_data['status']}: {resp_data['body'][:100]}")

        await browser.close()

asyncio.run(main())