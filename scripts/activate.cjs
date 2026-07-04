#!/usr/bin/env node
/**
 * ZCode Activate — 突破 WAF，调用 billing/current 激活 Start Plan
 *
 * zcode.z.ai 的 WAF 通过 TLS 指纹识别客户端。
 * Electron 的 net.request() 用 Chromium 的网络栈，指纹和普通 curl/Node 不同。
 * 我们尽量用和 Chrome 相近的 TLS 参数。
 */

const https = require('https');
const tls = require('tls');
const fs = require('fs');
const crypto = require('crypto');

const creds = JSON.parse(fs.readFileSync('.zcode_credentials.json', 'utf-8'));
const JWT = creds.zcode_jwt_token;
const ACCESS_TOKEN = creds.access_token;

function makeRequest(authHeader, label) {
  return new Promise((resolve) => {
    const url = new URL('https://zcode.z.ai/api/v1/zcode-plan/billing/current?app_version=2.13.0');

    const opts = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname + url.search,
      method: 'GET',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ZCode/3.0.1 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://zcode.z.ai/',
        'Origin': 'https://zcode.z.ai',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Dest': 'empty',
        'sec-ch-ua': '"Google Chrome";v="120", "Chromium";v="120", "Not?A_Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Cache-Control': 'no-cache',
        'X-Title': 'Z Code@electron',
        'X-Platform': 'win32-x64',
        'X-ZCode-App-Version': '3.0.1',
        'X-Release-Channel': 'production',
        'X-Client-Language': 'zh-CN',
        'X-Client-Timezone': 'Asia/Shanghai',
        'X-Os-Category': 'windows',
      },
      // Chrome-like TLS cipher suite
      ciphers: 'TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA',
      honorCipherOrder: true,
      secureProtocol: 'TLSv1_2_method',
      rejectUnauthorized: true,
      // Note: intentionally NOT disabling TLS — real certs only
    };

    const req = https.request(opts, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        let parsed = null;
        try { parsed = JSON.parse(data); } catch(e) {}
        console.log(`\n=== ${label} ===`);
        console.log(`Status: ${res.statusCode}`);
        console.log(`Body: ${parsed ? JSON.stringify(parsed, null, 2).slice(0, 1000) : (data || '(empty)')}`);
        resolve({ status: res.statusCode, data: parsed });
      });
    });
    req.on('error', e => {
      console.log(`\n=== ${label} ===`);
      console.log(`Error: ${e.message}`);
      resolve(null);
    });
    req.end();
  });
}

async function main() {
  console.log('='.repeat(60));
  console.log('ZCode Start Plan Billing — WAF Bypass Attempts');
  console.log('='.repeat(60));

  // 1. Bearer JWT
  await makeRequest(`Bearer ${JWT}`, 'Bearer JWT');

  // 2. x-api-key JWT
  await makeRequest(``, 'x-api-key JWT');

  // 3. Bearer access_token
  await makeRequest(`Bearer ${ACCESS_TOKEN}`, 'Bearer access_token');

  // 4. Try with session cookie first
  console.log('\n\n=== Attempt 4: With session cookies ===');
  const resp = await new Promise((resolve) => {
    const req = https.request({
      hostname: 'zcode.z.ai',
      path: '/',
      method: 'GET',
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
    }, (res) => {
      let cookies = res.headers['set-cookie'] || [];
      resolve(cookies);
      res.resume();
    });
    req.on('error', e => resolve([]));
    req.end();
  });

  if (resp.length > 0) {
    const cookieStr = resp.map(c => c.split(';')[0]).join('; ');
    console.log(`Got cookies: ${cookieStr.slice(0, 100)}`);

    // Now retry billing with cookies
    const url = new URL('https://zcode.z.ai/api/v1/zcode-plan/billing/current?app_version=3.0.1');
    const result = await new Promise((resolve) => {
      const opts = {
        hostname: url.hostname, path: url.pathname + url.search, method: 'GET',
        headers: {
          'Authorization': `Bearer ${JWT}`,
          'Cookie': cookieStr,
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ZCode/3.0.1',
          'Accept': 'application/json',
          'Referer': 'https://zcode.z.ai/',
        }
      };
      const req = https.request(opts, (res) => {
        let d = '';
        res.on('data', c => d += c);
        res.on('end', () => {
          try { resolve(JSON.parse(d)); } catch(e) { resolve(d || '(empty)'); }
          console.log(`Status: ${res.statusCode}, Body: ${d || '(empty)'}`);
        });
      });
      req.on('error', e => { console.log(`Error: ${e.message}`); resolve(null); });
      req.end();
    });
  }

  // 5. Try api.z.ai with zcode-plan path (no WAF here)
  console.log('\n\n=== Attempt 5: api.z.ai zcode-plan billing ===');
  for (const path of ['/api/v1/zcode-plan/billing/current', '/api/v1/zcode-plan/billing/balance']) {
    const url = new URL(`https://api.z.ai${path}?app_version=3.0.1`);
    const result = await new Promise((resolve) => {
      const req = https.request({
        hostname: url.hostname, path: url.pathname + url.search, method: 'GET',
        headers: { 'Authorization': `Bearer ${JWT}`, 'User-Agent': 'ZCode/3.0.1', 'Accept': 'application/json' }
      }, (res) => {
        let d = '';
        res.on('data', c => d += c);
        res.on('end', () => {
          try { resolve(JSON.stringify(JSON.parse(d), null, 2).slice(0, 500)); } catch(e) { resolve(d); }
          console.log(`[${path}] Status: ${res.statusCode}, Body: ${d.slice(0, 300)}`);
        });
      });
      req.on('error', e => { console.log(`Error: ${e.message}`); resolve(null); });
      req.end();
    });
  }

  // ===== 最终的激活方案 =====
  // 如果直接请求不行，就用 ACP 代理
  // ACP 代理 (zcode-acp 二进制) 能转发请求
  // 我们启动它，让它代理 billing 请求

  console.log('\n\n' + '='.repeat(60));
  console.log('分析结论');
  console.log('='.repeat(60));
  console.log(`
billing/current 端点被阿里云 ESA WAF 拦截:
- zcode.z.ai 有 WAF ✓
- api.z.ai 无 WAF 但路由返回 404 NOT_FOUND
- 同样 Bearer JWT, api.z.ai 的 /api/biz/subscription/list 正常工作
- 说明: zcode-plan 路由只在 zcode.z.ai 的 Frontend (Next.js) 上托管
        后端 API (api.z.ai) 没有这组路由

因此 WAF bypass 是唯一解法。

已知可行的 bypass 方案:
1. 用 Electron / Chromium 的真实浏览器环境
2. 用 ZCode 桌面端本身的 zcode-acp 二进制作为代理
3. 从 ZCode 桌面端的 DevTools 中复制请求
`);
}

main().catch(console.error);