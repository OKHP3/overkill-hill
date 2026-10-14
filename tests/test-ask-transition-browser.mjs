import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

// Exercise CSS with native dialog behavior. The separate immutable-source
// review verifies Ask's real controller; this fixture does not replace it.
const css = await readFile(new URL('../assets/css/theme.css', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true });
let count = 0;
try {
  for (const brand of ['askjamie-main', '', 'glee-main']) {
    for (const width of [320, 1280]) {
      for (const theme of ['light', 'dark']) {
        const context = await browser.newContext({ viewport: { width, height: 480 }, reducedMotion: 'reduce' });
        const page = await context.newPage();
        await page.route('**/*', route => route.request().url().endsWith('/theme.css')
          ? route.fulfill({ contentType: 'text/css', body: css })
          : route.fulfill({ contentType: 'text/html', body: `<!doctype html><html data-theme="${theme}"><head>
            <meta charset="utf-8"><link rel="stylesheet" href="/theme.css"></head><body class="${brand}">
            <section class="capability-transition"><h2>Platform transition</h2><p>The notice stays available.</p>
            <button class="btn btn-quiet" data-transition-open hidden>Review the update</button><a href="/story/">Read the story</a></section>
            <dialog class="capability-transition-dialog"><div class="capability-transition-dialog-content"><h2>What changes</h2>
            ${'<p>Long content must scroll inside the bounded dialog.</p>'.repeat(35)}
            <form method="dialog" class="capability-transition-actions"><button>Close update</button></form></div></dialog>
            <article class="capability-transition-story"><h2>The story</h2><p>Public background.</p></article></body></html>` }));
        try {
          await page.goto('https://ask-transition.test/', { waitUntil: 'load' });
          if (brand === 'askjamie-main') {
            assert.equal(await page.locator('[data-transition-open]').isVisible(), false, 'Ask hidden controls stay unpainted');
          }
          await page.locator('dialog').evaluate(el => el.showModal());
          const state = await page.locator('dialog').evaluate(el => {
            const s = getComputedStyle(el), r = el.getBoundingClientRect();
            return { border: s.borderTopWidth, borderColor: s.borderTopColor, width: r.width,
              top: r.top, bottom: r.bottom, left: r.left, right: r.right, overflow: s.overflowY,
              maxHeight: s.maxHeight, scrollable: el.scrollHeight > el.clientHeight,
              innerPadding: getComputedStyle(el.firstElementChild).paddingTop };
          });
          assert.equal(state.overflow, 'auto');
          assert.equal(state.scrollable, true, 'Long dialog content really requires scrolling');
          assert.ok(state.left >= 15 && state.right <= width - 15 && state.top >= 15 && state.bottom <= 465);
          if (brand === 'askjamie-main') {
            assert.equal(state.border, '5px');
            assert.equal(state.borderColor, 'rgb(45, 111, 126)');
            assert.ok(state.width <= 640 && state.width <= width - 32);
            assert.equal(state.innerPadding, width === 320 ? '20px' : '40px');
          } else {
            assert.equal(state.border, '1px', 'Primary and Glee retain their existing unscoped dialog border');
          }
          await page.locator('body').evaluate(el => el.classList.add('capability-transition-open'));
          const bodyOverflow = await page.locator('body').evaluate(el => getComputedStyle(el).overflow);
          if (brand === 'askjamie-main') assert.equal(bodyOverflow, 'hidden');
          else assert.notEqual(bodyOverflow, 'hidden', 'The Ask body marker cannot lock another brand');
          await page.getByRole('button', { name: 'Close update' }).press('Enter');
          assert.equal(await page.locator('dialog').evaluate(el => el.open), false);
          assert.equal(await page.locator('dialog').isVisible(), false, 'A closed native dialog stays unpainted');
          await page.locator('body').evaluate(el => el.classList.remove('capability-transition-open'));
          assert.notEqual(await page.locator('body').evaluate(el => getComputedStyle(el).overflow), 'hidden');
          count++;
        } finally { await context.close(); }
      }
    }
  }
} finally { await browser.close(); }
console.log(`PASS ${count} Ask transition CSS/native-dialog cases`);
