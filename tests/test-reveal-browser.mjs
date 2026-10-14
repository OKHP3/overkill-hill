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
      // The load event can precede completion of this lazy image request.
      await page.waitForFunction(image => image.complete && image.naturalWidth > 0,
        await art.elementHandle(), { timeout: 5000 });
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
  // The stylesheet is shared, but Glee's controller opts in only initially
  // offscreen elements. Exercise that public class contract independently of
  // controller timing, retaining positive controls for the other two brands.
  for (const brand of ['', 'glee-main', 'askjamie-main']) {
    for (const [width, reducedMotion] of [[1024, 'no-preference'], [1025, 'no-preference'], [1280, 'no-preference'], [1280, 'reduce']]) {
      const label = `${brand || 'primary'} ${width} ${reducedMotion}`;
      const context = await browser.newContext({ viewport: { width, height: 800 }, reducedMotion });
      const page = await context.newPage();
      await context.route('**/*', route => {
        if (route.request().url() === `${base}/reveal-contract`) {
          return route.fulfill({ contentType: 'text/html', body: `<!doctype html><html><head>
            <link rel="stylesheet" href="/assets/css/theme.css"></head><body class="${brand}">
            <main><h1>Visible content</h1>
            <p id="initial" class="reveal-on-scroll is-visible">Initially visible content</p>
            <p id="pending" class="reveal-on-scroll is-reveal-animate">Awaiting an intersection</p>
            <p id="eligible" class="reveal-on-scroll is-visible is-reveal-animate">Delivered intersection</p>
            <a href="/about/">Read about the site</a></main></body></html>` });
        }
        return route.request().url().startsWith(base) ? route.continue() : route.abort();
      });
      try {
        await page.goto(`${base}/reveal-contract`, { waitUntil: 'load' });
        const eligible = width >= 1025 && reducedMotion === 'no-preference';
        const animation = id => page.locator(`#${id}`).evaluate(el => getComputedStyle(el).animationName);
        assert.equal(await animation('initial'), eligible && brand !== 'glee-main' ? 'scroll-reveal-in' : 'none', 'Initial Glee content has no animation opt-in');
        assert.equal(await animation('pending'), 'none', 'The opt-in marker alone cannot start animation');
        assert.equal(await animation('eligible'), eligible ? 'scroll-reveal-in' : 'none', 'Both markers retain optional animation');
        await page.locator('#pending').evaluate(el => el.classList.add('is-visible'));
        assert.equal(await animation('pending'), eligible ? 'scroll-reveal-in' : 'none', 'A delivered intersection completes the class contract');
        if (eligible) {
          await page.emulateMedia({ reducedMotion: 'reduce' });
          assert.equal(await animation('eligible'), 'none', 'Live reduced-motion changes disable animation');
          await page.emulateMedia({ reducedMotion: 'no-preference' });
          await page.setViewportSize({ width: 1024, height: 800 });
          assert.equal(await animation('eligible'), 'none', 'Animation stops below the desktop boundary');
          await page.setViewportSize({ width: 1025, height: 800 });
          assert.equal(await animation('eligible'), 'scroll-reveal-in', 'The desktop boundary retains optional animation');
          assert.equal(await animation('initial'), brand === 'glee-main' ? 'none' : 'scroll-reveal-in');
        }
        await page.waitForFunction(() => [...document.querySelectorAll('.reveal-on-scroll')].every(el => {
          const style = getComputedStyle(el);
          return Number(style.opacity) === 1 && ['none', 'matrix(1, 0, 0, 1, 0, 0)'].includes(style.transform);
        }), null, { timeout: 2500 });
        assert.ok(await page.getByRole('heading', { name: 'Visible content' }).isVisible());
        await page.getByRole('link', { name: 'Read about the site' }).click();
        await page.waitForURL(`${base}/about/`);
        console.log(`PASS reveal contract ${label}: scoped animation, motion guards, readable content and navigation`);
      } catch (error) {
        failures++;
        console.error(`FAIL reveal contract ${label}: ${error.message}`);
      } finally { await context.close(); }
    }
  }
} finally {
  await browser?.close();
  server.close();
}
assert.equal(failures, 0, `${failures} reveal scenarios failed`);
