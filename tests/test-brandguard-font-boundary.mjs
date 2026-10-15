import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '..');
const css = await readFile(path.join(root, 'assets/css/theme.css'));
const browser = await chromium.launch();
let count = 0;
try {
  for (const { brand, notice, active } of [
    { brand: '', notice: true, active: false },
    { brand: 'glee-main', notice: true, active: false },
    { brand: 'askjamie-main', notice: false, active: false },
    { brand: 'askjamie-main', notice: true, active: true },
  ]) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [], requests = [];
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.route('**/*', async route => {
      const u = new URL(route.request().url());
      requests.push(u.href);
      if (u.origin !== 'https://font-boundary.test') return route.abort();
      if (u.pathname === '/theme.css') return route.fulfill({ contentType: 'text/css', body: css });
      if (u.pathname.startsWith('/assets/fonts/')) return route.fulfill({ contentType: 'font/woff2', body: await readFile(path.join(root, u.pathname.slice(1))) });
      return route.fulfill({ contentType: 'text/html', body: `<!doctype html><html data-theme="light"><head>
        <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self'; font-src 'self' data:; script-src 'none'">
        <link rel="stylesheet" href="/theme.css"></head><body class="${brand}">
        ${notice ? '<aside class="brandguard-demo-notice">Case context</aside>' : ''}
        <main><div class="askjamie-hero-copy"><h1>Font boundary witness</h1><p class="hero-subtitle">Readable text</p></div></main></body></html>` });
    });
    try {
      await page.goto('https://font-boundary.test/');
      await page.evaluate(() => document.fonts.ready);
      const family = await page.locator('body').evaluate(el => getComputedStyle(el).fontFamily);
      assert.equal(family.includes('BrandGuard Open Sans'), active, `font policy scope: ${brand || 'OKH'}`);
      assert.equal(requests.some(url => url.includes('/assets/fonts/brandguard-')), active, `only BrandGuard may request its local faces: ${brand || 'OKH'}`);
      assert.ok(requests.every(url => new URL(url).origin === 'https://font-boundary.test'), 'no remote font requests under the self-only policy');
      assert.deepEqual(errors, [], 'font declarations must preserve the strict CSP');
      count++;
    } finally { await context.close(); }
  }
} finally { await browser.close(); }
console.log(`PASS ${count} font scope and self-only CSP boundaries`);
