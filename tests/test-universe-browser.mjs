import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {chromium} from 'playwright';

const root = path.resolve(import.meta.dirname, '..');
const evidenceDir = process.env.W06_FOCUS_EVIDENCE_DIR;
const announcementKey = 'okh-capability-transition-2026-09-29';
const mimeTypes = new Map([
  ['.css', 'text/css; charset=utf-8'],
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.woff2', 'font/woff2'],
]);
const server = http.createServer((request, response) => {
  const route = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  let file = path.resolve(root, '.' + route);
  if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  const type = mimeTypes.get(path.extname(file)) || 'application/octet-stream';
  try { response.setHeader('Content-Type', type); response.end(fs.readFileSync(file)); }
  catch { response.writeHead(404).end(); }
});
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));

function minimumDiagramWidthFor(viewportWidth) {
  return viewportWidth <= 360 ? 0 : 720;
}

async function waitForDiagram(page, index, viewportWidth = null) {
  await page.waitForFunction(({index, viewportWidth}) => {
    const details = document.querySelectorAll('.universe-generated details')[index];
    const diagram = details?.querySelector('.universe-diagram');
    const svg = diagram?.querySelector('svg');
    return details?.open
      && diagram?.dataset.rendered === 'true'
      && Boolean(svg)
      && (viewportWidth === null || Math.abs(
        parseFloat(svg.style.width) - Math.max(viewportWidth <= 360 ? 0 : 720, svg.viewBox.baseVal.width),
      ) < 0.5);
  }, {index, viewportWidth});
}

async function assertNoDocumentOverflow(page, viewportWidth, label) {
  const widths = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    viewport: innerWidth,
  }));
  assert.ok(widths.document <= viewportWidth + 1, `${label}: document width ${widths.document}px exceeds ${viewportWidth}px`);
  assert.ok(widths.body <= viewportWidth + 1, `${label}: body width ${widths.body}px exceeds ${viewportWidth}px`);
  assert.equal(widths.viewport, viewportWidth, `${label}: viewport width changed unexpectedly`);
}

async function focusedNodeGeometry(page) {
  return page.evaluate(() => {
    const anchor = document.activeElement;
    const diagram = anchor?.closest('.universe-diagram');
    if (!diagram || !anchor.matches('svg a[href]')) return null;

    const svg = anchor.closest('svg');
    const rect = anchor.getBoundingClientRect();
    const panel = diagram.getBoundingClientRect();
    const style = getComputedStyle(anchor);
    const outlineWidth = parseFloat(style.outlineWidth) || 0;
    const outlineOffset = parseFloat(style.outlineOffset) || 0;
    const inset = outlineWidth + outlineOffset + 1;
    const panelLeft = panel.left + diagram.clientLeft;
    const panelTop = panel.top + diagram.clientTop;
    const panelRight = panelLeft + diagram.clientWidth;
    const panelBottom = panelTop + diagram.clientHeight;
    const ring = {
      left: rect.left - inset,
      right: rect.right + inset,
      top: rect.top - inset,
      bottom: rect.bottom + inset,
    };
    const labelText = anchor.querySelector('.nodeLabel')?.textContent?.trim() || '';
    const fontSizes = [...anchor.querySelectorAll('.nodeLabel, .nodeLabel p')]
      .map((label) => parseFloat(getComputedStyle(label).fontSize))
      .filter(Number.isFinite);

    return {
      href: anchor.getAttribute('href'),
      ariaLabel: anchor.getAttribute('aria-label') || '',
      labelText,
      focusVisible: anchor.matches(':focus-visible'),
      outlineStyle: style.outlineStyle,
      outlineWidth,
      outlineOffset,
      minimumLabelFontSize: fontSizes.length ? Math.min(...fontSizes) : 0,
      diagramWidth: svg.getBoundingClientRect().width,
      panelScrollWidth: diagram.scrollWidth,
      panelClientWidth: diagram.clientWidth,
      ring,
      panel: {left: panelLeft, right: panelRight, top: panelTop, bottom: panelBottom},
      viewport: {height: innerHeight},
      scrollLeft: diagram.scrollLeft,
    };
  });
}

async function assertFocusedNodeVisible(page, label) {
  const geometry = await focusedNodeGeometry(page);
  assert.ok(geometry, `${label}: focus is not on an SVG node link`);
  assert.ok(geometry.focusVisible, `${label}: SVG link is not :focus-visible`);
  assert.notEqual(geometry.outlineStyle, 'none', `${label}: visible focus outline is missing`);
  assert.ok(geometry.outlineWidth >= 2, `${label}: focus outline is thinner than 2px`);
  assert.ok(geometry.minimumLabelFontSize >= 12, `${label}: rendered node label is too small (${geometry.minimumLabelFontSize}px)`);
  assert.ok(geometry.ariaLabel.length > 0, `${label}: accessible node label is missing`);
  assert.ok(
    geometry.ring.left >= geometry.panel.left - 0.5 && geometry.ring.right <= geometry.panel.right + 0.5,
    `${label}: node and focus ring are clipped horizontally; ring=${JSON.stringify(geometry.ring)}, panel=${JSON.stringify(geometry.panel)}`,
  );
  assert.ok(
    geometry.ring.top >= Math.max(geometry.panel.top, 0) - 0.5
      && geometry.ring.bottom <= Math.min(geometry.panel.bottom, geometry.viewport.height) + 0.5,
    `${label}: node or focus ring is clipped vertically; ring=${JSON.stringify(geometry.ring)}, panel=${JSON.stringify(geometry.panel)}, viewport=${geometry.viewport.height}px`,
  );
  return geometry;
}

async function resizeWithNodeFocused(page, currentWidth, height, mapIndex, expectedHref, label) {
  const otherWidth = currentWidth === 320 ? 1280 : 320;
  for (const width of [otherWidth, currentWidth]) {
    await page.setViewportSize({width, height});
    await waitForDiagram(page, mapIndex, width);
    await page.waitForTimeout(30);
    const active = await page.evaluate(() => ({
      href: document.activeElement?.getAttribute('href') || '',
      isSvgLink: Boolean(document.activeElement?.matches('.universe-diagram svg a[href]')),
      focusVisible: document.activeElement?.matches(':focus-visible') || false,
    }));
    assert.deepEqual(active, {href: expectedHref, isSvgLink: true, focusVisible: true}, `${label}: focused node was lost after resize to ${width}px`);
    await assertFocusedNodeVisible(page, `${label} after resize to ${width}px`);
    await assertNoDocumentOverflow(page, width, `${label} after resize to ${width}px`);
  }
}

async function rerenderWithNodeFocused(page, mapIndex, viewportWidth, expectedHref, scheme) {
  await page.evaluate((value) => document.documentElement.setAttribute('data-color-scheme', value), scheme);
  await page.waitForFunction(({mapIndex, viewportWidth, expectedHref, scheme}) => {
    const details = document.querySelectorAll('.universe-generated details')[mapIndex];
    const diagram = details?.querySelector('.universe-diagram');
    const svg = diagram?.querySelector('svg');
    const active = document.activeElement;
    return document.documentElement.getAttribute('data-color-scheme') === scheme
      && diagram?.dataset.rendered === 'true'
      && Boolean(svg)
      && Math.abs(
        parseFloat(svg.style.width) - Math.max(viewportWidth <= 360 ? 0 : 720, svg.viewBox.baseVal.width),
      ) < 0.5
      && active?.getAttribute('href') === expectedHref
      && active.matches('.universe-diagram svg a[href]')
      && active.matches(':focus-visible');
  }, {mapIndex, viewportWidth, expectedHref, scheme});
  await assertFocusedNodeVisible(page, `${viewportWidth}px node after ${scheme} theme rerender`);
}

async function runKeyboardJourney(browser, width, height) {
  const context = await browser.newContext({viewport: {width, height}, deviceScaleFactor: 1});
  await context.addInitScript((key) => {
    try { sessionStorage.setItem(key, 'dismissed'); } catch {}
  }, announcementKey);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });

  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/universe/`, {waitUntil: 'load'});
    const details = page.locator('.universe-generated details');
    const total = await details.count();
    assert.equal(total, 6, 'the page should retain all six native disclosures');
    await waitForDiagram(page, 0);

    const firstSummary = details.nth(0).locator('summary');
    let firstSummaryReached = false;
    for (let guard = 0; guard < 100; guard += 1) {
      await page.keyboard.press('Tab');
      if (await firstSummary.evaluate((element) => element === document.activeElement)) {
        firstSummaryReached = true;
        break;
      }
    }
    assert.ok(firstSummaryReached, `${width}px: sequential Tab did not reach the first native summary`);

    let focusStops = 0;
    for (let mapIndex = 0; mapIndex < total; mapIndex += 1) {
      const disclosure = details.nth(mapIndex);
      const summary = disclosure.locator('summary');
      assert.ok(await summary.evaluate((element) => element === document.activeElement), `${width}px map ${mapIndex + 1}: focus is not on its summary`);

      const wasOpen = await disclosure.evaluate((element) => element.open);
      await page.keyboard.press('Enter');
      await page.waitForFunction(({mapIndex, expectedOpen}) => (
        document.querySelectorAll('.universe-generated details')[mapIndex]?.open === expectedOpen
      ), {mapIndex, expectedOpen: !wasOpen});
      if (wasOpen) {
        await page.keyboard.press('Enter');
        await page.waitForFunction((index) => document.querySelectorAll('.universe-generated details')[index]?.open, mapIndex);
      }
      await waitForDiagram(page, mapIndex);
      if (width === 320 && mapIndex === 0) {
        const panel = await disclosure.locator('.universe-diagram').evaluate((element) => ({
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
        }));
        assert.ok(panel.scrollWidth > panel.clientWidth, '320px: the complete diagram should remain horizontally scrollable inside its panel');
      }

      const svgLinks = disclosure.locator('.universe-diagram svg a[href]');
      const outlineLinks = disclosure.locator('ul a[href]');
      const svgCount = await svgLinks.count();
      const outlineCount = await outlineLinks.count();
      assert.ok(svgCount > 0, `${width}px map ${mapIndex + 1}: no keyboard-operable SVG links were rendered`);
      assert.equal(svgCount, outlineCount, `${width}px map ${mapIndex + 1}: SVG links and text-outline links differ`);

      const outlinePreserved = await disclosure.evaluate((element) => {
        const svgLabels = [...element.querySelectorAll('.universe-diagram svg a[href]')]
          .map((anchor) => [anchor.getAttribute('href'), anchor.getAttribute('aria-label')]);
        const textLinks = [...element.querySelectorAll('ul li')].map((item) => {
          const anchor = item.querySelector('a[href]');
          return {
            href: anchor?.getAttribute('href') || '',
            label: anchor?.textContent?.trim() || '',
            hasDescription: Boolean(anchor) && item.textContent.trim().length > anchor.textContent.trim().length,
          };
        });
        return {
          labelsMatch: JSON.stringify(svgLabels) === JSON.stringify(textLinks.map(({href, label}) => [href, label])),
          descriptionsPresent: textLinks.every(({hasDescription}) => hasDescription),
        };
      });
      assert.ok(outlinePreserved.labelsMatch, `${width}px map ${mapIndex + 1}: SVG labels no longer match the text outline`);
      assert.ok(outlinePreserved.descriptionsPresent, `${width}px map ${mapIndex + 1}: a page description is missing`);

      const orderedTargets = [];
      for (let index = 0; index < svgCount; index += 1) orderedTargets.push(svgLinks.nth(index));
      for (let index = 0; index < outlineCount; index += 1) orderedTargets.push(outlineLinks.nth(index));

      for (let targetIndex = 0; targetIndex < orderedTargets.length; targetIndex += 1) {
        const target = orderedTargets[targetIndex];
        await page.keyboard.press('Tab');
        assert.ok(
          await target.evaluate((element) => element === document.activeElement),
          `${width}px map ${mapIndex + 1}: Tab order changed at link ${targetIndex + 1}`,
        );
        focusStops += 1;

        if (mapIndex === 0 && targetIndex === 0) {
          const geometry = await focusedNodeGeometry(page);
          if (evidenceDir) {
            fs.mkdirSync(evidenceDir, {recursive: true});
            fs.writeFileSync(
              path.join(evidenceDir, `focus-${width}-first-svg-node.json`),
              `${JSON.stringify({viewport: {width, height}, geometry}, null, 2)}\n`,
            );
            await page.screenshot({
              path: path.join(evidenceDir, `focus-${width}-first-svg-node.png`),
              animations: 'disabled',
            });
          }
          assert.ok(geometry, `${width}px: first focused target is not an SVG node`);
          assert.ok(geometry.focusVisible, `${width}px: first SVG node is not :focus-visible`);
          await assertFocusedNodeVisible(page, `${width}px first SVG node`);
          await resizeWithNodeFocused(page, width, height, mapIndex, geometry.href, `${width}px first SVG node`);
          await rerenderWithNodeFocused(page, mapIndex, width, geometry.href, 'light');
          await rerenderWithNodeFocused(page, mapIndex, width, geometry.href, 'dark');
        } else {
          const active = await page.evaluate(() => ({
            focusVisible: document.activeElement?.matches(':focus-visible') || false,
            isAnchor: document.activeElement?.matches('a[href]') || false,
          }));
          assert.deepEqual(active, {focusVisible: true, isAnchor: true}, `${width}px map ${mapIndex + 1}: anchor focus is not visible`);
          if (targetIndex < svgCount) {
            await assertFocusedNodeVisible(page, `${width}px map ${mapIndex + 1} SVG link ${targetIndex + 1}`);
          }
        }
      }

      await page.keyboard.press('Tab');
      const boundary = await page.evaluateHandle(() => document.activeElement);
      const boundaryInfo = await boundary.evaluate((element, mapIndex) => ({
        insideCurrentMap: element.closest('.universe-generated details')
          === document.querySelectorAll('.universe-generated details')[mapIndex],
        isNextSummary: element.tagName === 'SUMMARY',
        href: element.getAttribute('href') || '',
        summaryText: element.tagName === 'SUMMARY' ? element.textContent.trim() : '',
      }), mapIndex);
      assert.equal(boundaryInfo.insideCurrentMap, false, `${width}px map ${mapIndex + 1}: Tab is trapped inside the map`);
      if (mapIndex + 1 < total) {
        assert.ok(boundaryInfo.isNextSummary, `${width}px map ${mapIndex + 1}: Tab did not reach the next native summary`);
        assert.ok(
          await details.nth(mapIndex + 1).locator('summary').evaluate((element) => element === document.activeElement),
          `${width}px map ${mapIndex + 1}: focus order skipped the next summary`,
        );
      } else {
        assert.equal(boundaryInfo.isNextSummary, false, `${width}px: the last map did not exit to the following page link`);
        assert.ok(boundaryInfo.href, `${width}px: Tab did not exit the last map onto a page link`);
        assert.equal(await page.evaluate(() => Boolean(document.activeElement.closest('.universe-generated details'))), false);
      }

      await page.keyboard.press('Shift+Tab');
      assert.ok(
        await orderedTargets.at(-1).evaluate((element) => element === document.activeElement),
        `${width}px map ${mapIndex + 1}: Shift+Tab did not return to the last outline link`,
      );
      await page.keyboard.press('Tab');
      assert.ok(
        await boundary.evaluate((element) => element === document.activeElement),
        `${width}px map ${mapIndex + 1}: forward Tab did not return to the boundary`,
      );
    }

    await assertNoDocumentOverflow(page, width, `${width}px keyboard journey`);

    for (const scheme of ['light', 'dark']) {
      await page.evaluate((value) => document.documentElement.setAttribute('data-color-scheme', value), scheme);
      await page.waitForFunction(({total, minimumWidth}) => {
        const open = [...document.querySelectorAll('.universe-generated details')].filter((item) => item.open);
        return open.length === total && open.every((item) => {
          const diagram = item.querySelector('.universe-diagram');
          const svg = diagram?.querySelector('svg');
          return diagram?.dataset.rendered === 'true'
            && Boolean(svg)
            && Math.abs(parseFloat(svg.style.width) - Math.max(minimumWidth, svg.viewBox.baseVal.width)) < 0.5
            && diagram.querySelectorAll('svg a[href]').length === item.querySelectorAll('ul a[href]').length;
        });
      }, {total, minimumWidth: minimumDiagramWidthFor(width)});
    }
    assert.deepEqual(errors, [], `${width}px browser errors`);
    await context.close();
    return {focusStops, errors};
  } catch (error) {
    await context.close();
    throw error;
  }
}

async function runNoJavaScriptCheck(browser) {
  const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 320, height: 874}});
  try {
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${server.address().port}/universe/`, {waitUntil: 'load'});
    assert.ok(await page.locator('.universe-generated li a[href]').count() >= 31);
    assert.equal(await page.locator('.universe-generated details').count(), 6);
    assert.equal(await page.locator('.universe-diagram:visible').count(), 0);
  } finally {
    await context.close();
  }
}

let browser;
try {
  const launchOptions = {headless: true, args: ['--no-sandbox']};
  if (process.env.REPLIT_PLAYWRIGHT_CHROMIUM_EXECUTABLE) {
    launchOptions.executablePath = process.env.REPLIT_PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  }
  browser = await chromium.launch(launchOptions);
  let focusStops = 0;
  for (const [width, height] of [[320, 874], [1280, 900]]) {
    const result = await runKeyboardJourney(browser, width, height);
    focusStops += result.focusStops;
  }
  await runNoJavaScriptCheck(browser);
  console.log(`PASS: six native disclosures; ${focusStops} sequential Tab stops at 320px and 1280px; visible node focus and rings; resize, light/dark rerender, descriptions, no-JavaScript fallback`);
} finally {
  if (browser) await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
