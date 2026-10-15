import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.TRANSITION_TEST_BASE || 'http://127.0.0.1:5000';
const launchOptions = { headless: true };
if (process.env.CHROMIUM_PATH) launchOptions.executablePath = process.env.CHROMIUM_PATH;
const browser = await chromium.launch(launchOptions);
const dismissalKey = 'okh-capability-transition-2026-09-29';

async function assertSkipLinkFallback(page, label) {
  const focus = await page.evaluate(() => {
    const active = document.activeElement;
    const style = active ? getComputedStyle(active) : null;
    return {
      isSkipLink: active?.matches('.okh-skip-link') || false,
      visible: Boolean(active && active.getClientRects().length && style.visibility !== 'hidden'),
      focusVisible: active?.matches(':focus-visible') || false,
      outline: style?.outlineStyle || '',
      outlineWidth: style?.outlineWidth || '',
    };
  });
  assert.equal(focus.isSkipLink, true, `${label}: focus falls back to the page skip link`);
  assert.equal(focus.visible, true, `${label}: fallback focus is visible`);
  assert.equal(focus.focusVisible, true, `${label}: fallback uses keyboard-visible focus`);
  assert.notEqual(focus.outline, 'none', `${label}: fallback has a visible outline`);
  assert.notEqual(focus.outlineWidth, '0px', `${label}: fallback outline has width`);
}

try {
  for (const width of [1440, 320]) {
    for (const blockedStorage of [false, true]) {
      for (const action of ['continue', 'close', 'escape']) {
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
        await page.goto(base + '/');
        const dialog = page.locator('#capability-transition-dialog');
        const label = `${action}, ${width}px, ${blockedStorage ? 'blocked' : 'normal'} storage`;
        assert.equal(await dialog.evaluate(el => el.open), true, `${label}: first homepage visit announces transition`);
        assert.equal(
          await page.evaluate(() => document.activeElement.getAttribute('aria-label')),
          'Close transition announcement',
          `${label}: dialog receives initial focus`,
        );
        if (width === 320) {
          assert.equal(
            await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
            true,
            `${label}: no mobile overflow`,
          );
        }

        // Native close notification is queued independently of dialog.open.
        // Observe that event before checking the existing focus contract.
        await dialog.evaluate(el => {
          el.__testCloseObserved = false;
          el.addEventListener('close', () => { el.__testCloseObserved = true; }, { once: true });
        });
        await page.keyboard.press('Shift+Tab');
        assert.equal(
          await page.evaluate(() => document.activeElement.textContent.trim()),
          'Continue exploring',
          `${label}: keyboard focus wraps within the dialog`,
        );
        if (action === 'continue') {
          await page.keyboard.press('Enter');
        } else if (action === 'close') {
          await page.keyboard.press('Tab');
          assert.equal(
            await page.evaluate(() => document.activeElement.getAttribute('aria-label')),
            'Close transition announcement',
            `${label}: forward Tab wraps to Close`,
          );
          await page.keyboard.press('Enter');
        } else {
          await page.keyboard.press('Escape');
        }

        assert.equal(await dialog.evaluate(el => el.open), false, `${label}: dialog closes`);
        await page.waitForFunction(() =>
          document.getElementById('capability-transition-dialog').__testCloseObserved === true);
        if (blockedStorage) {
          assert.equal(
            await page.evaluate(() => {
              try {
                sessionStorage.getItem('okh-capability-transition-2026-09-29');
                return false;
              } catch (error) {
                return error.name === 'SecurityError';
              }
            }),
            true,
            `${label}: storage remains blocked`,
          );
        } else {
          await page.waitForFunction(key => sessionStorage.getItem(key) === 'dismissed', dismissalKey);
        }
        await assertSkipLinkFallback(page, label);
        await page.keyboard.press('Tab');
        const nextFocus = await page.evaluate(() => ({
          inHeader: Boolean(document.activeElement?.closest('header')),
          ariaLabel: document.activeElement?.getAttribute('aria-label') || '',
          focusVisible: document.activeElement?.matches(':focus-visible') || false,
        }));
        assert.equal(nextFocus.inHeader, true, `${label}: next Tab proceeds into the header`);
        assert.equal(nextFocus.ariaLabel, 'OverKill Hill P³ home', `${label}: next Tab reaches the header home control`);
        assert.equal(nextFocus.focusVisible, true, `${label}: header focus remains visible`);

        if (width === 1440 && !blockedStorage && action === 'escape') {
          await page.reload();
          assert.equal(await dialog.evaluate(el => el.open), false, 'Dismissal survives same-tab reload');
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
        }
        assert.deepEqual(errors, []);
        await context.close();
      }
    }
  }

  const priorControlContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await priorControlContext.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      document.querySelector('header a[aria-label="OverKill Hill P³ home"]')?.focus();
    }, { once: true });
  });
  const priorControlPage = await priorControlContext.newPage();
  await priorControlPage.goto(base + '/');
  await priorControlPage.waitForFunction(() => document.getElementById('capability-transition-dialog')?.open);
  await priorControlPage.keyboard.press('Enter');
  await priorControlPage.waitForFunction(key => sessionStorage.getItem(key) === 'dismissed', dismissalKey);
  const restoredPriorControl = await priorControlPage.evaluate(() => ({
    isHeaderControl: document.activeElement?.matches('header a[aria-label="OverKill Hill P³ home"]') || false,
    isSkipLink: document.activeElement?.matches('.okh-skip-link') || false,
    focusVisible: document.activeElement?.matches(':focus-visible') || false,
  }));
  assert.equal(restoredPriorControl.isHeaderControl, true, 'A valid pre-dialog page control is restored');
  assert.equal(restoredPriorControl.isSkipLink, false, 'A valid prior control is not replaced by the skip link');
  assert.equal(restoredPriorControl.focusVisible, true, 'Restored prior control has visible keyboard focus');
  await priorControlContext.close();

  const noScript = await browser.newContext({ javaScriptEnabled: false });
  const page = await noScript.newPage();
  await page.goto(base + '/');
  assert.equal(await page.locator('.capability-transition-notice').isVisible(), true, 'Announcement remains readable without JavaScript');
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
