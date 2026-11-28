import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.TRANSITION_TEST_BASE || 'http://127.0.0.1:5000';
const launchOptions = { headless: true };
if (process.env.CHROMIUM_PATH) launchOptions.executablePath = process.env.CHROMIUM_PATH;
const browser = await chromium.launch(launchOptions);
try {
  for (const route of ['/', '/en-gb/', '/es-mx/']) {
    for (const width of [1440, 320]) {
      for (const blockedStorage of [false, true]) {
        const context = await browser.newContext({ viewport: { width, height: 900 } });
        if (blockedStorage) {
          await context.addInitScript(() => {
            Object.defineProperty(window, 'sessionStorage', {
              get() { throw new DOMException('Blocked', 'SecurityError'); },
            });
          });
        }
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(base + route);
        const label = `${route}, ${width}px, ${blockedStorage ? 'blocked' : 'normal'} storage`;
        assert.equal(await page.locator('#capability-transition-dialog').count(), 0, `${label}: no transition modal`);
        assert.equal(await page.locator('.capability-transition-notice').isVisible(), true, `${label}: transition notice remains visible`);
        assert.equal(await page.locator('dialog[open]').count(), 0, `${label}: no open dialog`);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${label}: no horizontal overflow`);
        await page.reload();
        assert.equal(await page.locator('#capability-transition-dialog').count(), 0, `${label}: modal stays absent after reload`);
        assert.deepEqual(errors, [], `${label}: no page errors`);
        await context.close();
      }
    }
  }

  for (const width of [1440, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    await page.goto(base + '/');
    const skip = page.locator('.okh-skip-link');
    const initial = await skip.evaluate(el => ({
      focused: el === document.activeElement,
      clipped: getComputedStyle(el).clip !== 'auto',
    }));
    assert.deepEqual(initial, { focused: false, clipped: true }, `${width}px: skip link starts visually hidden`);
    await page.keyboard.press('Tab');
    await page.waitForFunction(() => {
      const link = document.querySelector('.okh-skip-link');
      return link === document.activeElement && getComputedStyle(link).clip === 'auto'
        && link.getBoundingClientRect().top >= 0;
    });
    assert.equal(await skip.evaluate(el => el.matches(':focus-visible')), true, `${width}px: keyboard focus is visible`);
    await page.keyboard.press('Enter');
    assert.equal(new URL(page.url()).hash, '#main', `${width}px: skip link targets main content`);
    assert.equal(await page.evaluate(() => document.activeElement === document.getElementById('main')), true,
      `${width}px: activation moves focus to main content`);
    await page.goto(base + '/about/');
    await page.goto(base + '/');
    const returned = await skip.evaluate(el => ({
      focused: el === document.activeElement,
      clipped: getComputedStyle(el).clip !== 'auto',
    }));
    assert.deepEqual(returned, { focused: false, clipped: true }, `${width}px: normal navigation does not focus the skip link`);
    await context.close();
  }

  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(base + '/');
  await page.getByRole('link', { name: 'Read the transition plan →', exact: true }).click();
  assert.equal(new URL(page.url()).pathname, '/capability-transition/');
  assert.equal(await page.getByRole('heading', { level: 1 }).textContent(), 'The era of Custom GPTs is ending. The work continues.');
  assert.equal(await page.locator('#transition-acknowledgment').textContent(), "I'm aware of the change, and I'm working on it.");
  assert.doesNotMatch(await page.locator('main').innerText(), /\u00e2\u20ac|\u00c2\u00b7/, 'Transition copy has no garbled punctuation');
  for (const route of ['bfs-framing-intelligent-futures', 'found-ry', 'hometools', 'pathscrib-r', 'un-nocked-truth']) {
    await page.goto(base + '/projects/' + route + '/');
    assert.equal(await page.locator('.capability-transition-notice').count(), 1, route + ' carries notice');
    assert.equal(await page.locator('dialog').count(), 0, 'Project visits are not interrupted by a modal');
  }
  await page.goto(base + '/projects/abrahamic-reference-engine/');
  assert.equal(await page.locator('.capability-transition-notice').count(), 0, 'GPT provenance does not imply retiring application');
  await context.close();

  const noScript = await browser.newContext({ javaScriptEnabled: false });
  const noScriptPage = await noScript.newPage();
  await noScriptPage.goto(base + '/');
  assert.equal(await noScriptPage.locator('.capability-transition-notice').isVisible(), true, 'Announcement remains readable without JavaScript');
  assert.equal(await noScriptPage.locator('#capability-transition-dialog').count(), 0, 'Modal remains absent without JavaScript');
  await noScript.close();
  // CSS-only fixture for the existing Glee native-dialog contract. Real sibling
  // runtime acceptance is separate; this prevents future stylesheet regression.
  for (const width of [320, 1280]) for (const reducedMotion of ['reduce', 'no-preference']) {
    const context = await browser.newContext({ viewport: { width, height: 480 }, reducedMotion });
    const page = await context.newPage();
    await page.route('**/glee-transition-style-fixture', route => route.fulfill({
      contentType: 'text/html',
      body: `<!doctype html><html><head><link rel="stylesheet" href="/assets/css/theme.css"></head>
        <body class="glee-main"><main><aside class="glee-transition-notice">
        <p class="glee-transition-title">Transition information</p>
        <div class="glee-transition-actions"><a href="#content">Read the plan</a>
        <button class="glee-transition-reopen" hidden>Show notice</button></div></aside>
        <h1 id="content">Preserved content</h1></main>
        <div class="construction-overlay">Legacy notice</div>
        <dialog class="glee-transition-dialog"><div class="glee-transition-dialog-content">
        <h2>Existing transition</h2>${'<p>Keep the information available.</p>'.repeat(12)}
        <div class="glee-transition-actions"><a class="btn" href="#content">Read the plan</a>
        <button class="btn" autofocus>Continue browsing</button></div></div></dialog></body></html>`,
    }));
    await page.goto(base + '/glee-transition-style-fixture');
    const label = `Glee styles, ${width}px, ${reducedMotion}`;
    assert.equal(await page.locator('.glee-transition-reopen').isVisible(), false, `${label}: unavailable reopen stays hidden`);
    assert.equal(await page.locator('.construction-overlay').isVisible(), false, `${label}: native notice replaces the legacy overlay`);
    assert.equal(await page.locator('dialog').isVisible(), false, `${label}: closed dialog stays hidden`);
    await page.locator('dialog').evaluate(el => el.showModal());
    const layout = await page.locator('dialog').evaluate(el => {
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      return { x: r.x, y: r.y, right: r.right, bottom: r.bottom,
        padding: getComputedStyle(el.firstElementChild).paddingTop,
        border: s.borderTopWidth, overflow: s.overflowY, animation: s.animationName,
        scrollable: el.scrollHeight > el.clientHeight,
        target: [...el.querySelectorAll('a,button')].map(e => e.getBoundingClientRect().height) };
    });
    assert.ok(layout.x >= 15 && layout.right <= width - 15, `${label}: horizontal margin`);
    assert.ok(layout.y >= 15 && layout.bottom <= 465, `${label}: short viewport margin`);
    assert.ok(parseFloat(layout.padding) >= 20, `${label}: readable content padding`);
    assert.equal(layout.border, '2px', `${label}: existing modal border`);
    assert.equal(layout.overflow, 'auto', `${label}: tall content can scroll`);
    assert.equal(layout.scrollable, true, `${label}: overflow is actually exercised`);
    assert.equal(layout.animation, 'none', `${label}: dialog adds no motion`);
    assert.ok(layout.target.every(h => h >= 44), `${label}: minimum control height`);
    const focused = await page.locator('dialog button').evaluate(el => {
      const r = el.getBoundingClientRect(), parent = el.closest('dialog').getBoundingClientRect();
      return document.activeElement === el && r.top >= parent.top && r.bottom <= parent.bottom;
    });
    assert.equal(focused, true, `${label}: autofocus scrolls the final control into view`);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('dialog').isVisible(), false, `${label}: Escape closes the dialog`);
    assert.equal(await page.locator('.glee-transition-notice').isVisible(), true, `${label}: static notice remains`);
    await page.locator('.glee-transition-reopen').evaluate(el => { el.hidden = false; });
    assert.equal(await page.locator('.glee-transition-reopen').isVisible(), true, `${label}: available reopen appears`);
    await page.locator('.glee-transition-reopen').evaluate(el => { el.hidden = true; });
    assert.equal(await page.locator('.glee-transition-reopen').isVisible(), false, `${label}: hidden is reapplied`);
    await page.locator('dialog').evaluate(el => el.remove());
    assert.equal(await page.locator('.construction-overlay').isVisible(), true, `${label}: unrelated legacy overlay remains`);
    await page.locator('body').evaluate(el => el.className = '');
    await page.locator('body').evaluate(el => {
      const dialog = document.createElement('dialog');
      dialog.className = 'glee-transition-dialog';
      el.append(dialog);
    });
    assert.equal(await page.locator('.construction-overlay').isVisible(), true, `${label}: overlay outside Glee remains`);
    await context.close();
  }
  console.log('PASS: primary transition behavior and four Glee stylesheet viewport/motion contracts.');
} finally { await browser.close(); }
