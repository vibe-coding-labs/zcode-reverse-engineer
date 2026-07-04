#!/usr/bin/env python3
"""
在真实浏览器中打开 zcode.z.ai 并手动登录，
捕获登录后的所有 token/cookie/API 调用。
"""
import asyncio, json

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 有头模式，让你手动操作
        context = await browser.new_context()

        page = await context.new_page()

        # 监听所有请求/响应，捕获 token 和 API 调用
        captured = {"requests": [], "responses": []}

        async def on_request(request):
            url = request.url
            if any(k in url for k in ['token', 'auth', 'login', 'billing', 'plan', 'session', 'userinfo']):
                headers = dict(request.headers)
                # 不要打印 Authorization 完整值
                if 'authorization' in headers:
                    h = headers['authorization']
                    headers['authorization'] = h[:30] + '...' + h[-10:] if len(h) > 50 else h
                captured["requests"].append({
                    "url": url,
                    "method": request.method,
                    "headers": headers,
                    "post_data": request.post_data,
                })

        async def on_response(response):
            url = response.url
            if any(k in url for k in ['token', 'auth', 'login', 'billing', 'plan', 'session', 'userinfo']):
                try:
                    body = await response.json()
                except:
                    try:
                        body = await response.text()
                    except:
                        body = None
                captured["responses"].append({
                    "url": url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        print("=" * 60)
        print("  浏览器已打开 → https://zcode.z.ai")
        print("  请在浏览器中完成以下操作：")
        print("    1. 看到登录按钮 → 点击登录")
        print("    2. 用 Z.AI 账号登录（chat.z.ai 的账号）")
        print("    3. 授权完成后回到这里看结果")
        print("=" * 60)
        print()

        await page.goto("https://zcode.z.ai/", wait_until="domcontentloaded", timeout=30000)

        # 等待用户手动操作
        input("  按 Enter 等待捕获的 API 信息...")
        print()

        # 输出捕获结果
        print(f"\n  捕获了 {len(captured['requests'])} 个请求, {len(captured['responses'])} 个响应\n")

        print("=" * 60)
        print("  捕获的认证相关 API")
        print("=" * 60)
        for req in captured["requests"]:
            print(f"\n  [{req['method']}] {req['url']}")
            if req['headers']:
                for k, v in req['headers'].items():
                    if k in ['authorization', 'cookie']:
                        print(f"    {k}: {v[:80]}")
            if req['post_data']:
                print(f"    body: {req['post_data'][:200]}")

        for resp in captured["responses"]:
            print(f"\n  → HTTP {resp['status']} {resp['url']}")
            if isinstance(resp['body'], dict):
                print(f"    {json.dumps(resp['body'], indent=2, ensure_ascii=False)[:500]}")

        # 检查 localStorage / sessionStorage 中的 token
        print("\n\n" + "=" * 60)
        print("  localStorage 中的 key")
        print("=" * 60)
        ls = await page.evaluate("""() => {
            const keys = [];
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                const v = localStorage.getItem(k);
                keys.push({key: k, value: v ? v.slice(0, 50) + '...' : null});
            }
            return keys;
        }""")
        for item in ls:
            print(f"  {item['key']}: {item['value']}")

        # 检查 cookies
        cookies = await context.cookies()
        print(f"\n  Cookies ({len(cookies)}):")
        for c in cookies:
            print(f"    {c['name']}={c['value'][:30]}... domain={c['domain']}")

        input("\n\n  按 Enter 关闭浏览器...")
        await browser.close()

asyncio.run(main())