#!/usr/bin/env python3
"""
追踪 zcode.z.ai 的登录流程，捕获 OAuth 回调后如何建立 session。
用无头浏览器，不弹UI。
"""
import asyncio, json, sys

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        page = await context.new_page()

        # 拦截所有匹配模式的路由
        captured = {
            "auth_requests": [],
            "auth_responses": [],
            "tokens": [],
        }

        async def on_response(response):
            url = response.url
            # 只关注认证和 token 相关
            if not any(k in url for k in ['token', 'auth', 'oauth', 'login', 'session', 'userinfo', 'billing', 'zcode-plan']):
                return
            try:
                body = await response.json()
            except:
                try:
                    body = (await response.text())[:500]
                except:
                    body = None
            captured["auth_responses"].append({
                "url": url,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "body": body,
            })

        page.on("response", on_response)

        # 1. 打开 zcode.z.ai 首页
        print("1. Opening zcode.z.ai...")
        await page.goto("https://zcode.z.ai/", wait_until="domcontentloaded", timeout=30000)
        print("   ✓ Loaded")

        # 2. 找登录按钮并点击
        print("2. Looking for login button...")
        await page.wait_for_timeout(2000)

        # 取页面文字看有什么按钮
        text = await page.text_content("body")
        # 找包含登录/开始/试用等关键词
        login_btn = None
        for selector in [
            'button:has-text("登录")',
            'a:has-text("登录")',
            'button:has-text("Login")',
            'a:has-text("Login")',
            'button:has-text("开始")',
            'button:has-text("试用")',
            '[href*="login"]',
            '[href*="oauth"]',
            '[href*="authorize"]',
        ]:
            btn = await page.query_selector(selector)
            if btn:
                login_btn = btn
                print(f"   Found login button: {selector}")
                break

        if not login_btn:
            # 打印所有按钮看一下
            btns = await page.query_selector_all("button, a")
            print(f"   No login button found. Buttons on page:")
            for b in btns:
                t = await b.text_content()
                href = await b.get_attribute("href")
                if t or href:
                    print(f"     text='{t[:30] if t else ''}' href='{href}'")
        else:
            # 3. 点击登录
            print("3. Clicking login...")
            async with page.expect_navigation(timeout=30000) as nav:
                await login_btn.click()
            await nav.value
            print(f"   Redirected to: {page.url}")

            # 4. 如果在 chat.z.ai OAuth 页面
            if "chat.z.ai" in page.url:
                print("4. At chat.z.ai OAuth page. Need manual login.")
                # 提示用户在当前终端不能手动输入
                # 这种情况下，我们需要保存当前 URL 让用户手动处理
                print(f"\n   OAuth URL: {page.url}")
                print("   ⚠ 需要手机号+验证码登录，但这是无头环境。")
                print("   请复制上面的链接到有浏览器的设备上完成授权。")
            else:
                # 可能 zcode.z.ai 有独立的 session
                print(f"4. After login, at: {page.url}")
                cookies = await context.cookies()
                for c in cookies:
                    print(f"     cookie: {c['name']}={c['value'][:30]}")

        # 输出捕获的 API 调用
        print(f"\n\n=== 捕获的 API 调用 ({len(captured['auth_responses'])}) ===")
        for r in captured["auth_responses"]:
            status = r["status"]
            url = r["url"].split("?")[0]
            body_preview = ""
            if isinstance(r["body"], dict):
                body_preview = json.dumps(r["body"], ensure_ascii=False)[:200]
            elif r["body"]:
                body_preview = str(r["body"])[:200]
            print(f"  HTTP {status} {url}")
            if body_preview:
                print(f"    {body_preview}")
            print()

        await browser.close()

asyncio.run(main())