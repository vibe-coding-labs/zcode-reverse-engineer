#!/usr/bin/env python3
"""
ZCode Start Plan 激活协议验证脚本

通过 Playwright 驱动真实 Chromium 浏览器，绕过 zcode.z.ai 的阿里云 WAF，
调用 billing/current API 获取 Start Plan 的完整配额信息。

用法:
  python scripts/activate_playwright.py login    # OAuth 登录 + 获取配额
  python scripts/activate_playwright.py quota    # 只用已有的 JWT 查配额
  python scripts/activate_playwright.py check    # 完整诊断

前置条件:
  pip install playwright
  playwright install chromium
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ─── 配置 ───
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".zcode_credentials.json")
ZCODE_JWT = None

HEADERS_TEMPLATE = {
    "Authorization": "",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ZCode/3.0.1 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://zcode.z.ai/",
    "Origin": "https://zcode.z.ai",
    "X-Title": "Z Code@electron",
    "X-Platform": "win32-x64",
    "X-ZCode-App-Version": "3.0.1",
    "X-Release-Channel": "production",
    "X-Client-Language": "zh-CN",
    "X-Client-Timezone": "Asia/Shanghai",
    "X-Os-Category": "windows",
}


def load_jwt():
    global ZCODE_JWT
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
        ZCODE_JWT = creds.get("zcode_jwt_token", "")
        return ZCODE_JWT
    except (FileNotFoundError, json.JSONDecodeError):
        return None


async def call_billing(context):
    """通过浏览器环境调用 billing/current API."""
    headers = {**HEADERS_TEMPLATE, "Authorization": f"Bearer {ZCODE_JWT}"}

    page = await context.new_page()
    # 拦截请求并添加认证头
    await page.route("**/zcode-plan/billing/**", lambda route: route.continue_(headers=headers))

    try:
        resp = await page.request.get(
            "https://zcode.z.ai/api/v1/zcode-plan/billing/current?app_version=3.0.1",
            headers=headers,
        )
        status = resp.status
        try:
            data = await resp.json()
        except:
            text = await resp.text()
            data = {"raw": text[:500]}

        print(f"  HTTP {status}")
        print(f"  Response: {json.dumps(data, indent=2, ensure_ascii=False)[:2000]}")

        # 同时查询 balance
        resp2 = await page.request.get(
            "https://zcode.z.ai/api/v1/zcode-plan/billing/balance?app_version=3.0.1",
            headers=headers,
        )
        try:
            data2 = await resp2.json()
            print(f"\n  Balance: HTTP {resp2.status}")
            print(f"  {json.dumps(data2, indent=2, ensure_ascii=False)[:1000]}")
        except:
            pass

        return data

    finally:
        await page.close()


async def call_subscription_api(context):
    """通过 api.z.ai 查询 Coding Plan 订阅（无 WAF 问题）。"""
    page = await context.new_page()
    headers = {
        "Authorization": f"Bearer {ZCODE_JWT}",
        "Content-Type": "application/json",
    }

    for url, label in [
        ("https://api.z.ai/api/biz/subscription/list", "Subscription List"),
        ("https://api.z.ai/api/monitor/usage/quota/limit", "Usage Quota"),
    ]:
        try:
            resp = await page.request.get(url, headers=headers)
            try:
                data = await resp.json()
                print(f"  [{label}] HTTP {resp.status}")
                print(f"  {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
            except:
                text = await resp.text()
                print(f"  [{label}] HTTP {resp.status}: {text[:200]}")
        except Exception as e:
            print(f"  [{label}] Error: {e}")
        print()

    await page.close()


async def diagnose_waf(context):
    """诊断 WAF 行为，检查哪些路径被拦截。"""
    page = await context.new_page()

    paths = [
        ("/", "首页"),
        ("/api/v1/zcode-plan/billing/current?app_version=3.0.1", "billing/current"),
        ("/api/v1/zcode-plan/billing/balance?app_version=3.0.1", "billing/balance"),
        ("/api/v1/client/configs", "client configs"),
    ]

    for path, label in paths:
        url = f"https://zcode.z.ai{path}"
        try:
            resp = await page.request.get(url)
            try:
                data = await resp.json()
                print(f"  [{label}] {url}")
                print(f"    HTTP {resp.status}: {json.dumps(data, ensure_ascii=False)[:300]}")
            except:
                text = await resp.text()
                print(f"  [{label}] {url}")
                print(f"    HTTP {resp.status}: {text[:200]}")
        except Exception as e:
            print(f"  [{label}] Error: {e}")
        print()

    await page.close()


async def cmd_quota():
    """用已有 JWT 通过浏览器查配额（绕过 WAF）。"""
    if not load_jwt():
        print("❌ No JWT found. Run login first.")
        sys.exit(1)

    print("=" * 60)
    print("  ZCode Start Plan — Quota Check (Browser Mode)")
    print("=" * 60)
    print(f"  JWT: {ZCODE_JWT[:30]}...{ZCODE_JWT[-10:]}")
    print()

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ZCode/3.0.1 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        # Step 1: 访问首页建立 session（通过 WAF JS Challenge）
        print("  Step 1: 访问首页（通过 WAF JS Challenge）...")
        page = await context.new_page()
        await page.goto("https://zcode.z.ai/", wait_until="networkidle", timeout=30000)
        print(f"  首页加载完成，cookies: {await context.cookies()}")
        await page.close()
        print()

        # Step 2: 调用 billing/current
        print("  Step 2: 调用 billing/current...")
        await call_billing(context)
        print()

        # Step 3: 查询订阅信息
        print("  Step 3: 查询订阅和配额...")
        await call_subscription_api(context)

        await browser.close()


async def cmd_login():
    """通过 Playwright 浏览器完成 OAuth 登录 + 配额检查。"""
    print("=" * 60)
    print("  ZCode OAuth Login + Start Plan Check (Browser Mode)")
    print("=" * 60)
    print()
    print("  ⚠ 你需要在打开的浏览器中完成登录")
    print()

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 有头模式
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ZCode/3.0.1 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        # 打开 zcode.z.ai 首页
        page = await context.new_page()
        await page.goto("https://zcode.z.ai/", wait_until="networkidle", timeout=30000)
        print("  首页加载完成，请手动登录...")
        print("  登录完成后按 Enter 继续...")
        input()

        # 获取当前 cookies 和 localStorage 中的 token
        cookies = await context.cookies()
        print(f"  Cookies: {[c['name'] for c in cookies]}")

        # 尝试提取 localStorage 中的 JWT
        jwt = await page.evaluate("""() => {
            try {
                return localStorage.getItem('zcodejwttoken');
            } catch(e) { return null; }
        }""")
        if jwt:
            print(f"  localStorage JWT: {jwt[:30]}...{jwt[-10:]}")
            global ZCODE_JWT
            ZCODE_JWT = jwt

        # 检查 billing
        print("\n  检查 Start Plan 配额...")
        await call_billing(context)

        await browser.close()


async def cmd_check():
    """完整诊断：检查所有 API 端点的可达性。"""
    print("=" * 60)
    print("  ZCode 完整诊断 (Browser Mode)")
    print("=" * 60)
    print()

    load_jwt()

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="zh-CN",
        )

        # Step 1: 首页 + WAF
        print("  [1/4] 首页（通过 WAF）...")
        page = await context.new_page()
        await page.goto("https://zcode.z.ai/", wait_until="networkidle", timeout=30000)
        print(f"  ✅ 首页加载成功")
        await page.close()
        print()

        # Step 2: WAF 诊断
        print("  [2/4] WAF 路径诊断...")
        await diagnose_waf(context)
        print()

        # Step 3: billing/current
        print("  [3/4] billing/current...")
        if ZCODE_JWT:
            await call_billing(context)
        else:
            print("  ⚠ No JWT available")
        print()

        # Step 4: 订阅 API
        print("  [4/4] 订阅 API (api.z.ai)...")
        if ZCODE_JWT:
            await call_subscription_api(context)
        else:
            print("  ⚠ No JWT available")

        await browser.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    # 检查 playwright 是否可用
    try:
        import playwright
    except ImportError:
        print("❌ playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    if command == "quota":
        asyncio.run(cmd_quota())
    elif command == "login":
        asyncio.run(cmd_login())
    elif command == "check":
        asyncio.run(cmd_check())
    else:
        print(f"Unknown command: {command}")
        print("Usage: python scripts/activate_playwright.py {quota|login|check}")


if __name__ == "__main__":
    main()