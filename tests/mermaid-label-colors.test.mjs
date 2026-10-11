import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { test } from 'node:test';
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';

const root = path.resolve(import.meta.dirname, '..');
const baselineCss = process.env.MERMAID_BASELINE_REVISION
  ? execFileSync('git', ['show', `${process.env.MERMAID_BASELINE_REVISION}:assets/css/theme.css`], { cwd: root, encoding: 'utf8' })
  : null;
const diagram = `flowchart LR
  subgraph Workbench
    A["<strong>Dark node</strong><br/><em>Emphasis</em><br/><span>Light text</span><br/><span style='color:#f0c26a!important'>Accent</span>"] -->|Route| B["Light node<br/>Dark text"]
  end
  classDef dark fill:#18212b,color:#f7f9fb,stroke:#c46a2c;
  classDef light fill:#f3f5f7,color:#1d2530,stroke:#c46a2c;
  class A dark;
  class B light;`;

function contrast(foreground, background) {
  const luminance = color => {
    const channels = color.match(/[\d.]+/g).slice(0, 3).map(Number).map(value => {
      const channel = value / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test('Mermaid HTML labels retain their assigned colors across page palettes', async () => {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    if (baselineCss && url.pathname === '/assets/css/theme.css') {
      response.setHeader('Content-Type', 'text/css'); response.end(baselineCss); return;
    }
    if (url.pathname === '/label-fixture.html') {
      const theme = url.searchParams.get('theme') === 'light' ? 'light' : 'dark';
      const shell = url.searchParams.has('shell') ? 'okh-mermaid-shell' : '';
      response.setHeader('Content-Type', 'text/html; charset=utf-8');
      const escaped = diagram.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
      response.end(`<!doctype html><html data-theme="${theme}"><head><link rel="stylesheet" href="/assets/css/theme.css"></head><body><main class="article-body ${shell}"><pre class="mermaid">${escaped}</pre></main><script type="module" src="/assets/js/mermaid-init.js"></script></body></html>`);
      return;
    }
    let file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
    try { response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream'); response.end(fs.readFileSync(file)); }
    catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  const observations = [];
  try {
    browser = await chromium.launch();
    for (const theme of ['dark', 'light']) {
      for (const shell of [false, true]) {
        const page = await browser.newPage();
        await page.goto(`${base}/label-fixture.html?theme=${theme}${shell ? '&shell=1' : ''}`);
        await page.locator('.mermaid svg').waitFor();
        await page.locator('.mermaid g.node').first().waitFor();
        const labels = await page.locator('.mermaid foreignObject p').evaluateAll(elements => elements.map(p => {
          const carrier = p.closest('.nodeLabel, .edgeLabel');
          const node = p.closest('g.node, g.cluster');
          const shape = node?.querySelector('rect, polygon, circle, path');
          return { text: p.textContent, foreground: getComputedStyle(p).color, assigned: carrier && getComputedStyle(carrier).color, fill: shape ? getComputedStyle(shape).fill : getComputedStyle(p).backgroundColor, emphasis: [...p.querySelectorAll('strong, em, span:not([style])')].map(e => getComputedStyle(e).color), explicit: [...p.querySelectorAll('span[style]')].map(e => ({color: getComputedStyle(e).color, inline: e.getAttribute('style')})) };
        }));
        assert.ok(labels.length >= 3, `${theme}/${shell}: node and edge paragraphs rendered: ${JSON.stringify(labels)}`);
        const clusters = await page.locator('.cluster-label').evaluateAll(elements => elements.map(e => ({text: e.textContent, color: getComputedStyle(e.querySelector('p, span') || e).color, fill: getComputedStyle(e.closest('.cluster').querySelector('rect')).fill})));
        assert.equal(clusters.length, 1, 'cluster label rendered');
        for (const cluster of clusters) assert.ok(contrast(cluster.color, cluster.fill) >= 4.5, 'cluster label contrast');
        for (const label of labels) {
          assert.equal(label.foreground, label.assigned, `${theme}/${shell}: ${label.text} paragraph preserves assigned color`);
          for (const color of label.emphasis) assert.equal(color, label.assigned, 'emphasis preserves label color');
          for (const color of label.explicit) assert.equal(color.color, 'rgb(240, 194, 106)', `explicit inline color preserved: ${JSON.stringify(color)}`);
          if (label.fill) assert.ok(contrast(label.foreground, label.fill) >= 4.5, `${label.text}: visible text contrast`);
        }
        const nodes = labels.filter(label => label.fill);
        assert.ok(nodes.some(label => label.explicit.length > 0), 'inline preservation check is nonempty');
        assert.ok(nodes.some(label => label.foreground === 'rgb(247, 249, 251)'), 'light foreground preserved');
        assert.ok(nodes.some(label => label.foreground === 'rgb(29, 37, 48)'), 'dark foreground preserved');
        observations.push({ theme, shell, labels, clusters });
        await page.close();
      }
    }
    for (const theme of ['dark', 'light']) {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      await page.addInitScript(theme => localStorage.setItem('okh-theme', theme), theme);
      await page.goto(`${base}/projects/mac-studio-local-ai-workbench/#how-its-built`);
      assert.equal(await page.locator('html').getAttribute('data-theme'), theme, 'requested theme is active');
      const diagrams = page.locator('.mermaid');
      assert.equal(await diagrams.count(), 3, 'all three architecture families present');
      for (let index = 0; index < 3; index++) {
        await diagrams.nth(index).scrollIntoViewIfNeeded();
        await diagrams.nth(index).locator('svg').waitFor();
      }
      await diagrams.nth(2).locator('svg[aria-roledescription="architecture"] text').first().waitFor();
      const labels = await diagrams.locator('.nodeLabel p, .edgeLabel p').evaluateAll(elements => elements.map(p => {
        const shape = p.closest('g.node, g.cluster')?.querySelector('rect, polygon, circle, path');
        return { text: p.textContent, foreground: getComputedStyle(p).color, assigned: getComputedStyle(p.closest('.nodeLabel, .edgeLabel')).color, fill: shape ? getComputedStyle(shape).fill : getComputedStyle(p).backgroundColor };
      }));
      assert.ok(labels.length > 20, 'actual nested project labels are checked');
      for (const label of labels) {
        assert.equal(label.foreground, label.assigned, `${theme}: ${label.text} follows its label carrier`);
        if (label.fill) assert.ok(contrast(label.foreground, label.fill) >= 4.5, `${theme}: ${label.text} has readable text/background contrast`);
      }
      const architecture = await diagrams.nth(2).locator('svg text').evaluateAll(elements => elements.map(e => ({text: e.textContent, fill: getComputedStyle(e).fill})));
      assert.ok(architecture.length >= 30, 'architecture SVG text path rendered');
      assert.ok(architecture.every(label => label.fill !== 'rgb(0, 0, 0)'), 'architecture text retains its assigned foreground');
      await page.locator('.theme-toggle').click();
      const switched = await page.locator('html').getAttribute('data-theme');
      assert.equal(switched, theme === 'light' ? 'dark' : 'light', 'theme switch works after rendering');
      const switchedPairs = await diagrams.locator('.nodeLabel p, .edgeLabel p').evaluateAll(elements => elements.map(p => {
        const shape = p.closest('g.node, g.cluster')?.querySelector('rect, polygon, circle, path');
        return { foreground: getComputedStyle(p).color, fill: shape ? getComputedStyle(shape).fill : getComputedStyle(p).backgroundColor };
      }));
      assert.deepEqual(switchedPairs, labels.map(({foreground, fill}) => ({foreground, fill})), 'rendered text/background pairs stay intact after theme switch');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'phone document has no overflow');
      observations.push({ theme, page: 'Mac Studio', labels, architecture, switched, switchedPairs });
      await page.close();
    }
    // FoundRy was selected after the first candidate freeze and exposed a
    // separate authored palette conflict. It is now regression coverage,
    // not a protected holdout.
    for (const theme of ['dark', 'light']) {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
      await page.addInitScript(theme => localStorage.setItem('okh-theme', theme), theme);
      await page.goto(`${base}/projects/found-ry/`);
      await page.locator('.mermaid g.node').first().waitFor();
      assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
      const pairs = await page.locator('.mermaid .nodeLabel p, .mermaid .edgeLabel p').evaluateAll(elements => elements.map(p => {
        const shape = p.closest('g.node')?.querySelector('rect, polygon, circle, path');
        return {text: p.textContent, foreground: getComputedStyle(p).color, fill: shape ? getComputedStyle(shape).fill : getComputedStyle(p).backgroundColor};
      }));
      assert.equal(pairs.length, 9, 'all FoundRy node and edge labels rendered');
      for (const label of pairs) assert.ok(contrast(label.foreground, label.fill) >= 4.5, `${theme}: FoundRy ${label.text} contrast`);
      await page.locator('summary').filter({hasText: 'Status and source'}).click();
      assert.equal(await page.locator('details').filter({has: page.locator('summary').filter({hasText: 'Status and source'})}).getAttribute('open'), '', 'status disclosure opens');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'FoundRy phone document has no overflow');
      await page.locator('.theme-toggle').click();
      const switchedPairs = await page.locator('.mermaid .nodeLabel p, .mermaid .edgeLabel p').evaluateAll(elements => elements.map(p => {
        const shape = p.closest('g.node')?.querySelector('rect, polygon, circle, path');
        return {text: p.textContent, foreground: getComputedStyle(p).color, fill: shape ? getComputedStyle(shape).fill : getComputedStyle(p).backgroundColor};
      }));
      assert.equal(await page.locator('html').getAttribute('data-theme'), theme === 'light' ? 'dark' : 'light', 'FoundRy theme switch is active');
      assert.deepEqual(switchedPairs, pairs, 'FoundRy text/backing pairs survive theme switch');
      observations.push({theme, page: 'FoundRy', pairs, switchedPairs});
      await page.close();
    }
    if (process.env.MERMAID_COLOR_REPORT) fs.writeFileSync(process.env.MERMAID_COLOR_REPORT, JSON.stringify({ observations }, null, 2));
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
});
