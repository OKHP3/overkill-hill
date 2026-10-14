import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright';

// Isolate the shared CSS contract; actual sibling runtime/pages are reviewed
// separately. The solid paper here gives an unambiguous painted background.
const css = await readFile(new URL('../assets/css/theme.css', import.meta.url), 'utf8');
const browser = await chromium.launch({ headless: true });
const luminance = rgb => rgb.map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; })
  .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
const rgb = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
function contrast(foreground, background, opacity = 1) {
  const bg = rgb(background), fg = rgb(foreground).map((v, i) => v * opacity + bg[i] * (1 - opacity));
  const a = luminance(fg), b = luminance(bg);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}
async function readState(page) {
  return page.evaluate(() => {
    const body = getComputedStyle(document.body), paper = getComputedStyle(document.querySelector('section'));
    const crumb = getComputedStyle(document.querySelector('.askjamie-breadcrumb'));
    const probe = document.createElement('i'); probe.style.color = 'var(--color-bg)'; document.body.append(probe);
    const expected = getComputedStyle(probe).color; probe.remove();
    return { background: body.backgroundColor, image: body.backgroundImage, expected, bg: paper.backgroundColor,
      breadcrumb: { size: crumb.fontSize, height: crumb.lineHeight, tracking: crumb.letterSpacing },
      text: [...document.querySelectorAll('.eyebrow,.breadcrumb-label,.breadcrumb-separator')].map(e => {
        const s = getComputedStyle(e); return { color: s.color, opacity: Number(s.opacity), fontSize: parseFloat(s.fontSize) };
      }) };
  });
}
function verify(state) {
  assert.equal(state.background, state.expected, 'Ask surface follows its effective palette');
  assert.equal(state.image, 'none', 'Generic light-body gradients must not remain painted');
  for (const text of state.text) assert.ok(contrast(text.color, state.bg, text.opacity) >= 4.5,
    `Normal-sized paper text meets 4.5:1, got ${contrast(text.color, state.bg, text.opacity).toFixed(2)}`);
  assert.ok(state.text.every(t => t.fontSize < 24), 'Normal-text threshold is applicable');
  assert.deepEqual(state.breadcrumb, { size: '15.2px', height: '24.32px', tracking: '0.152px' }, 'Breadcrumb keeps its readable typography');
  assert.equal(state.text.at(-1).opacity, 1, 'Separator is not faded into the paper');
}
let failures = 0;
try {
  for (const width of [320, 1280]) for (const [selection, os] of [
    ['light', 'dark'], ['dark', 'light'], ['auto', 'light'], ['auto', 'dark'],
  ]) {
    const context = await browser.newContext({ viewport: { width, height: 800 }, colorScheme: os, reducedMotion: 'reduce' });
    const page = await context.newPage();
    await page.route('https://ask-style.test/theme.css', route => route.fulfill({ contentType: 'text/css', body: css }));
    await page.route('https://ask-style.test/', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html>
      <html data-theme="light" ${selection === 'auto' ? '' : `data-color-scheme="${selection}"`}>
      <head><link rel="stylesheet" href="/theme.css"></head><body class="askjamie-main">
      <main><section style="background:var(--color-surface);padding:2rem;color:var(--color-fg)">
      <div class="askjamie-hero-copy"><p class="eyebrow">A useful introduction</p></div>
      <p class="eyebrow">A section introduction</p>
      <p class="askjamie-breadcrumb"><span class="breadcrumb-label">AskJamie</span>
      <span class="breadcrumb-separator">/</span></p></section></main></body></html>` }));
    try {
      await page.goto('https://ask-style.test/');
      const state = await readState(page); verify(state);
      await page.emulateMedia({ colorScheme: os === 'light' ? 'dark' : 'light' });
      const changed = await readState(page); verify(changed);
      if (selection === 'auto') assert.notEqual(changed.background, state.background, 'Auto follows changed OS preference');
      else assert.deepEqual(changed, state, 'Explicit selection overrides OS preference');
      if (selection === 'light') {
        await page.evaluate(() => document.body.style.setProperty('--color-inline-link', '#18424a'));
        assert.ok((await readState(page)).text.every(t => t.color === 'rgb(24, 66, 74)'), 'Text consumes the inherited link token');
        await page.evaluate(() => document.body.style.setProperty('--color-inline-link', 'initial'));
        assert.ok((await readState(page)).text.every(t => t.color === 'rgb(31, 90, 103)'), 'Missing token uses the existing fallback');
      }
      await page.evaluate(() => document.body.className = '');
      assert.equal((await readState(page)).text[0].color, 'rgb(60, 142, 161)', 'Similarly named hero outside Ask keeps the original generic color');
      await page.evaluate(() => document.body.className = 'glee-main');
      assert.equal((await readState(page)).text[0].color, 'rgb(60, 142, 161)', 'Similarly named hero on Glee remains unchanged');
      console.log(`PASS: ${width}px, ${selection}/${os}`);
    } catch (error) { failures++; console.error(`FAIL: ${width}px, ${selection}/${os}: ${error.message}`); }
    await context.close();
  }
} finally { await browser.close(); }
assert.equal(failures, 0, `${failures} Ask surface/text contrast contracts failed`);
