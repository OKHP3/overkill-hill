import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { chromium } from 'playwright';

// Serve this checkout on an isolated loopback port, never an existing preview.
const root = path.resolve(import.meta.dirname, '..');
const server = http.createServer((request, response) => {
  let file = path.resolve(root, '.' + new URL(request.url, 'http://localhost').pathname);
  if (file !== root && !file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : 'application/octet-stream';
  try { response.setHeader('Content-Type', type); response.end(fs.readFileSync(file)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
let failures = 0;
try {
  browser = await chromium.launch({ headless: true });
  for (const scenario of ['disabled', 'blocked', 'early-failure', 'missing-observer', 'constructor-failure', 'observe-failure', 'stalled-observer', 'normal', 'reduced', 'phone']) {
    const context = await browser.newContext({
      javaScriptEnabled: scenario !== 'disabled',
      viewport: { width: scenario === 'phone' ? 390 : 1280, height: 800 },
      reducedMotion: scenario === 'reduced' ? 'reduce' : 'no-preference',
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await context.route('**/*', route => {
      if (!route.request().url().startsWith(base)) return route.abort();
      if (route.request().url().includes('/assets/js/app.js')) {
        if (scenario === 'blocked') return route.abort();
        if (scenario === 'early-failure') return route.fulfill({ contentType: 'text/javascript', body: 'throw new Error("Injected startup failure");' });
      }
      return route.continue();
    });
    await context.addInitScript(mode => {
      if (mode === 'missing-observer') delete window.IntersectionObserver;
      if (['constructor-failure', 'observe-failure', 'stalled-observer'].includes(mode)) {
        window.IntersectionObserver = class {
          constructor() { if (mode === 'constructor-failure') throw new Error('Injected constructor failure'); }
          observe() { if (mode === 'observe-failure') throw new Error('Injected observe failure'); }
          disconnect() {}
          unobserve() {}
        };
      }
    }, scenario);
    try {
      await page.goto(base + '/', { waitUntil: 'load' });
      // Audit underlying page behavior after the first-visit dialog is closed.
      const announcement = page.locator('#capability-transition-dialog[open]');
      if (await announcement.count()) {
        await page.getByRole('button', { name: 'Close transition announcement' }).click();
        await page.waitForFunction(() => !document.getElementById('capability-transition-dialog').open);
      }
      assert.equal(new URL(page.url()).pathname, '/');
      assert.match(await page.title(), /OverKill/);
      await page.waitForFunction(() => [...document.querySelectorAll('.reveal-on-scroll')].every(el => Number(getComputedStyle(el).opacity) === 1), null, { timeout: 2500 });
      assert.ok(await page.locator('main h1').innerText());
      const art = page.locator('main .reveal-on-scroll img').first();
      assert.ok(await art.evaluate(el => el.complete && el.naturalWidth > 0), 'Hero art loads');
      if (scenario === 'normal') {
        const pending = page.locator('.reveal-on-scroll:not(.is-visible)').last();
        assert.ok(await pending.count(), 'Below-fold content awaits optional animation');
        await pending.scrollIntoViewIfNeeded();
        await page.waitForFunction(() => [...document.querySelectorAll('.reveal-on-scroll')].some(el => getComputedStyle(el).animationName === 'scroll-reveal-in' && el.getAnimations().some(a => a.playState === 'running')));
      }
      if (['reduced', 'phone'].includes(scenario)) {
        assert.ok(await page.locator('.reveal-on-scroll').evaluateAll(els => els.every(el => getComputedStyle(el).animationName === 'none')));
      }
      if (process.env.REVEAL_SCREENSHOT_DIR && ['disabled', 'normal', 'phone'].includes(scenario)) {
        fs.mkdirSync(process.env.REVEAL_SCREENSHOT_DIR, { recursive: true });
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
        await page.screenshot({ path: path.join(process.env.REVEAL_SCREENSHOT_DIR, `reveal-${scenario}.png`) });
      }
      if (['normal', 'reduced', 'constructor-failure', 'observe-failure'].includes(scenario)) {
        const skip = page.locator('.okh-skip-link');
        await skip.focus();
        await page.keyboard.press('Enter');
        assert.equal(await page.evaluate(() => document.activeElement.id), 'main', 'Skip link moves keyboard focus');
        assert.equal(new URL(page.url()).hash, '#main');
      }
      const link = page.locator('main a[href^="/"]').first();
      const target = await link.getAttribute('href');
      await link.click();
      await page.waitForURL(base + target);
      assert.equal(new URL(page.url()).pathname, target);
      assert.deepEqual(errors, scenario === 'early-failure' ? ['Injected startup failure', 'Injected startup failure'] : []);
      console.log(`PASS ${scenario}: visible content, art and working destination link`);
    } catch (error) {
      failures++;
      console.error(`FAIL ${scenario}: ${error.message}`);
    } finally { await context.close(); }
  }
} finally {
  await browser?.close();
  server.close();
}
assert.equal(failures, 0, `${failures} reveal scenarios failed`);
