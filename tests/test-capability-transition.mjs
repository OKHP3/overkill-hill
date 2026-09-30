import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.TRANSITION_TEST_BASE || 'http://127.0.0.1:5000';
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 320]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/');
    const dialog = page.locator('#capability-transition-dialog');
    assert.equal(await dialog.evaluate(el => el.open), true, 'First homepage visit announces transition');
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('aria-label')), 'Close transition announcement');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Continue exploring', 'Native dialog traps keyboard focus');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'No mobile overflow');
    await page.keyboard.press('Escape');
    assert.equal(await dialog.evaluate(el => el.open), false);
    await page.reload();
    assert.equal(await dialog.evaluate(el => el.open), false, 'Dismissal survives same-tab reload');
    await page.getByRole('link', { name: 'Read the transition plan →', exact: true }).click();
    assert.equal(new URL(page.url()).pathname, '/capability-transition/');
    assert.equal(await page.getByRole('heading', { level: 1 }).textContent(), 'The era of Custom GPTs is ending. The work continues.');
    for (const route of ['bfs-framing-intelligent-futures', 'found-ry', 'hometools', 'pathscrib-r', 'un-nocked-truth']) {
      await page.goto(base + '/projects/' + route + '/');
      assert.equal(await page.locator('.capability-transition-notice').count(), 1, route + ' carries notice');
      assert.equal(await page.locator('dialog').count(), 0, 'Project visits are not interrupted by a modal');
    }
    await page.goto(base + '/projects/abrahamic-reference-engine/');
    assert.equal(await page.locator('.capability-transition-notice').count(), 0, 'GPT provenance does not imply retiring application');
    assert.deepEqual(errors, []);
    await context.close();
  }
  const noScript = await browser.newContext({ javaScriptEnabled: false });
  const page = await noScript.newPage();
  await page.goto(base + '/');
  assert.equal(await page.locator('.capability-transition-notice').isVisible(), true, 'Announcement remains readable without JavaScript');
  await noScript.close();
  const deniedStorage = await browser.newContext();
  await deniedStorage.addInitScript(() => {
    Object.defineProperty(window, 'sessionStorage', { get() { throw new DOMException('Blocked', 'SecurityError'); } });
  });
  const deniedPage = await deniedStorage.newPage();
  await deniedPage.goto(base + '/');
  assert.equal(await deniedPage.locator('dialog').evaluate(el => el.open), true, 'Announcement works when storage is blocked');
  await deniedPage.getByRole('button', { name: 'Continue exploring', exact: true }).click();
  assert.equal(await deniedPage.locator('dialog').evaluate(el => el.open), false);
  await deniedStorage.close();
  console.log('PASS: transition modal, keyboard focus, dismissal, responsive layout, route scope, no-JS and blocked-storage fallbacks.');
} finally { await browser.close(); }
