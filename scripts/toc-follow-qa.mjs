#!/usr/bin/env node
// Browser acceptance for every published sidebar, including noindex routes.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const base = (process.argv.find(a => a.startsWith('--base-url='))?.split('=')[1] || 'http://127.0.0.1:5000').replace(/\/$/, '');
const inventoryCode = 'import runpy,json;from pathlib import Path;m=runpy.run_path("scripts/build-release.py");print(json.dumps([p.as_posix() for p in m["load_public_pages"](Path.cwd())]))';
const files = JSON.parse(execFileSync(process.platform === 'win32' ? 'py' : 'python3', ['-c', inventoryCode], { encoding: 'utf8' }));
const menus = files.filter(file => /id=["']toc-widget["']/.test(readFileSync(file, 'utf8')));
for (const file of files) {
  const html = readFileSync(file, 'utf8');
  assert(!/class=["'][^"']*\btoc-list\b/.test(html) || menus.includes(file), `${file}: sidebar list is missing its shared follow hook`);
}
assert(menus.length > 0, 'Release inventory must contain sidebar menus');
console.log(`Inventory: ${files.length} public pages, ${menus.length} sidebar menus, ${files.length - menus.length} without sidebar menus.`);
const browser = await chromium.launch({ headless: true });
let failures = 0;
const geometry = (requireConvergence = false) => {
  const toc = document.getElementById('toc-widget');
  const r = toc.getBoundingClientRect();
  const matrix = new DOMMatrixReadOnly(getComputedStyle(toc).transform);
  const natural = r.top + scrollY - matrix.m42;
  const footer = document.querySelector('.site-footer').getBoundingClientRect();
  const stop = document.getElementById(toc.dataset.tocStopBefore)?.getBoundingClientRect();
  const boundaryTop = Math.min(footer.top, stop?.top ?? footer.top);
  const gap = Math.max(112, (document.querySelector('.site-header')?.getBoundingClientRect().height || 0) + 16);
  const desiredTop = Math.max(gap, (innerHeight - r.height) / 2);
  const maximum = Math.max(0, boundaryTop + scrollY - 32 - natural - r.height);
  const expected = natural - scrollY + Math.min(Math.max(0, scrollY + desiredTop - natural), maximum);
  const error = Math.abs(r.top - expected);
  return requireConvergence ? error < 2 : { top: r.top, bottom: r.bottom, height: r.height, expected, error, footer: footer.top, natural, scroll: scrollY, maxScroll: document.documentElement.scrollHeight - innerHeight };
};

// A diagram's temporary render container can disappear after a breakpoint
// change (FoundRy moved document scroll anchoring by 117px). Measure reduced
// motion against stable layout inputs, without waiting for the TOC transform.
const waitForStableLayoutFrames = async () => {
  let previous;
  let stable = 0;
  let timeout;
  try {
    await Promise.race([
      new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Layout did not stabilize within 5 seconds')), 5000); }),
      (async () => {
        for (let frame = 0; frame < 180; frame++) {
          await new Promise(requestAnimationFrame);
          const toc = document.getElementById('toc-widget');
          const box = toc.getBoundingClientRect();
          const translation = new DOMMatrixReadOnly(getComputedStyle(toc).transform).m42;
          const inputs = [document.body.offsetHeight, scrollY, innerWidth, innerHeight, box.height, box.top + scrollY - translation];
          stable = previous && inputs.every((value, index) => Math.abs(value - previous[index]) < 0.25) ? stable + 1 : 0;
          previous = inputs;
          if (stable === 3) return;
        }
        throw new Error('Layout did not stabilize within 180 animation frames');
      })(),
    ]);
  } finally { clearTimeout(timeout); }
};

try {
  // Keep the article's native shortcut usable with and without the shared script.
  for (const javaScriptEnabled of [true, false]) {
    for (const width of [320, 1280]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce', javaScriptEnabled });
      try {
        await page.goto(base + '/writings/first-diagram-is-a-liar/', { waitUntil: 'load' });
        const shortcut = page.locator('a.okh-skip-link[href="#toc-widget"]');
        assert.equal(await shortcut.count(), 1, 'Article has one early TOC shortcut');
        await shortcut.focus();
        await page.keyboard.press('Enter');
        await page.waitForFunction(() => document.activeElement?.id === 'toc-widget');
        await page.keyboard.press('Tab');
        assert(await page.locator('#toc-widget a').first().evaluate(a => a === document.activeElement),
          'Tab after the shortcut reaches the first TOC link');
        const target = await page.locator('#toc-widget a').first().getAttribute('href');
        await page.keyboard.press('Enter');
        await page.waitForFunction(hash => location.hash === hash, target);
        console.log(`PASS article TOC shortcut ${width}px JavaScript=${javaScriptEnabled}`);
      } catch (error) {
        failures++;
        console.error(`FAIL article TOC shortcut ${width}px JavaScript=${javaScriptEnabled}: ${error.message}`);
      } finally { await page.close(); }
    }
  }
  for (const file of menus) {
    const route = '/' + file.replace(/index\.html$/, '');
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' });
    try {
      await page.goto(base + route, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      // Instant browser scrolling isolates the sidebar's own easing.
      await page.evaluate(() => document.documentElement.style.setProperty('scroll-behavior', 'auto', 'important'));
      await page.waitForTimeout(200);
      assert.equal(await page.locator('#toc-widget').count(), 1, 'Exactly one shared sidebar hook');
      await page.waitForFunction(() => document.getElementById('toc-widget').classList.contains('toc-follow-active'),
        null, { polling: 'raf', timeout: 10000 });
      const structure = await page.evaluate(() => {
        const t = document.getElementById('toc-widget');
        const sticky = [];
        for (let p = t.parentElement; p; p = p.parentElement) if (getComputedStyle(p).position === 'sticky') sticky.push(p.className);
        return { sticky, missing: [...t.querySelectorAll('a[href^="#"]')].filter(a => !document.getElementById(a.hash.slice(1))).map(a => a.hash) };
      });
      assert.deepEqual(structure.sticky, [], 'Ancestor sticky positioning fights centered follow');
      assert.deepEqual(structure.missing, [], 'Every local menu target exists');
      const start = await page.evaluate(geometry);
      await page.evaluate(async y => {
        window.scrollTo(0, y);
        for (let i = 0; i < 3; i++) await new Promise(requestAnimationFrame);
      }, Math.min(start.maxScroll * 0.65, start.natural + 1000));
      const early = await page.evaluate(geometry);
      assert(early.error > 2, 'Normal motion should visibly ease rather than jump into place');
      // A stationary sample can mean a delayed frame under CI load, not that
      // the menu reached its destination. Check the actual visible geometry.
      await page.waitForFunction(geometry, true, { polling: 'raf', timeout: 10000 });
      const settled = await page.evaluate(geometry);
      assert(settled.error < 2, `Sidebar must settle into centered/bounded position: ${JSON.stringify(settled)}`);
      await page.evaluate(() => {
        const a = document.querySelector('#toc-widget a[href^="#"]');
        const target = document.getElementById(a.hash.slice(1));
        window.scrollTo(0, target.getBoundingClientRect().top + scrollY);
      });
      await page.waitForTimeout(100);
      assert(await page.locator('#toc-widget .toc-active').count() > 0, 'Scrollspy highlights a reached section');

      // A short desktop viewport must keep the last link reachable by keyboard.
      await page.setViewportSize({ width: 1440, height: 500 });
      await page.waitForTimeout(300);
      assert(await page.locator('#toc-widget').evaluate(t => t.getBoundingClientRect().height <= innerHeight - 112 + 1), 'Tall menu bounded by viewport');
      const last = page.locator('#toc-widget a').last();
      await last.focus();
      assert(await last.evaluate(a => {
        const t = a.closest('#toc-widget').getBoundingClientRect(); const r = a.getBoundingClientRect();
        return r.top >= t.top - 1 && r.bottom <= t.bottom + 1;
      }), 'Last menu link can be revealed through keyboard focus');

      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(150);
      assert.equal(await page.locator('#toc-widget').evaluate(t => t.style.transform), '', 'Desktop to mobile clears animation');
      // Reload mobile tests the former initialization-only breakpoint bug.
      await page.reload({ waitUntil: 'load' });
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.evaluate(() => {
        document.documentElement.style.scrollBehavior = 'auto';
        window.scrollTo(0, document.documentElement.scrollHeight * 0.55);
      });
      await page.evaluate(waitForStableLayoutFrames);
      const reduced = await page.evaluate(geometry);
      assert(reduced.error < 2, `Mobile to desktop/reduced motion must follow immediately: ${JSON.stringify(reduced)}`);
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.evaluate(waitForStableLayoutFrames);
      const bottom = await page.evaluate(geometry);
      assert(bottom.bottom <= bottom.footer - 30, `Sidebar must clear footer: ${JSON.stringify(bottom)}`);
      if (route === '/writings/murderbird/') {
        for (const width of [1024, 1440]) {
          await page.setViewportSize({ width, height: 900 });
          await page.locator('#visual-record').scrollIntoViewIfNeeded();
          await page.evaluate(waitForStableLayoutFrames);
          const boundary = await page.evaluate(() => ({
            tocBottom: document.getElementById('toc-widget').getBoundingClientRect().bottom,
            galleryTop: document.getElementById('visual-record').getBoundingClientRect().top,
          }));
          assert(boundary.tocBottom <= boundary.galleryTop - 30,
            `TOC must stop before full-width visual record at ${width}px: ${JSON.stringify(boundary)}`);
        }
      }
      console.log(`PASS ${route}`);
    } catch (error) {
      failures++;
      console.error(`FAIL ${route}: ${error.message}`);
    } finally { await page.close(); }
  }
  const legacy = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const legacyErrors = [];
  legacy.on('pageerror', error => legacyErrors.push(error.message));
  try {
    // Older MediaQueryList implementations expose addListener only. Keep the
    // real matching/change behavior while removing the newer subscription API.
    await legacy.addInitScript(() => Object.defineProperty(MediaQueryList.prototype, 'addEventListener', { value: undefined, configurable: true }));
    await legacy.goto(base + '/projects/mac-studio-local-ai-workbench/', { waitUntil: 'load' });
    await legacy.setViewportSize({ width: 1440, height: 900 });
    await legacy.evaluate(() => {
      document.documentElement.style.scrollBehavior = 'auto';
      window.scrollTo(0, document.documentElement.scrollHeight * 0.55);
    });
    await legacy.evaluate(waitForStableLayoutFrames);
    assert.deepEqual(legacyErrors, [], 'Legacy media-query subscriptions must not throw or abort shared script startup');
    const box = await legacy.evaluate(geometry);
    assert(box.error < 2, `Legacy media-query API must activate centered follow: ${JSON.stringify(box)}`);
    console.log('PASS legacy MediaQueryList mobile-to-desktop follow');
  } catch (error) {
    failures++;
    console.error(`FAIL legacy MediaQueryList: ${error.message}`);
  } finally { await legacy.close(); }
} finally { await browser.close(); }
if (failures) process.exitCode = 1;
