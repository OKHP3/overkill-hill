import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '..');
const revision = process.env.FOUNDRY_BASELINE_REVISION;
const baseline = revision && execFileSync('git', ['show', `${revision}:projects/found-ry/index.html`], { cwd: root });
const expectedNodes = ['Raw prompt the ore', 'Prompt Forge heat and pressure', 'Found-Ry nine stations on the anvil', 'Test matrix and audit the quench', "Ship and govern the maker's mark", 'Skillz Forge the shelf', 'GitHub the record'];
const observations = [];

test('FoundRy diagram remains readable and meaningfully described', async () => {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    if (baseline && url.pathname === '/projects/found-ry/') {
      response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(baseline); return;
    }
    let file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
    try { response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream'); response.end(fs.readFileSync(file)); }
    catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = process.env.FOUNDRY_LIVE_ORIGIN || `http://127.0.0.1:${server.address().port}`;
  let browser;
  const failures = [];
  const check = (condition, message) => { if (!condition) failures.push(message); };
  try {
    browser = await chromium.launch();
    for (const width of [1280, 390, 320]) {
      for (const theme of ['dark', 'light']) {
        const page = await browser.newPage({ viewport: { width, height: 844 } });
        await page.addInitScript(value => localStorage.setItem('okh-theme', value), theme);
        await page.goto(`${base}/projects/found-ry/`);
        await page.locator('#ecosystem .mermaid g.node').first().waitFor();
        await page.evaluate(() => document.fonts.ready);
        if (process.env.FOUNDRY_DIAGRAM_FAULT) await page.locator('#ecosystem .mermaid').evaluate((diagram, fault) => {
          const label = diagram.querySelector('.nodeLabel p');
          if (fault === 'hidden') label.style.visibility = 'hidden';
          if (fault === 'scaled') label.style.transform = 'scale(.5)';
          if (fault === 'clipped') label.closest('foreignObject').setAttribute('height', '1');
          if (fault === 'hidden-return') diagram.querySelector('[id$="L_D_C_0"]').style.display = 'none';
          if (fault === 'swapped') {
            diagram.querySelector('[data-id="L_D_C_0"] p').textContent = 'passes the gate';
            diagram.querySelector('[data-id="L_D_E_0"] p').textContent = 'fails the gate';
          }
        }, process.env.FOUNDRY_DIAGRAM_FAULT);
        const inspect = () => page.locator('#ecosystem .mermaid').evaluate(diagram => {
          const normalize = value => value.replace(/\\n/g, ' ').replace(/\s+/g, ' ').trim();
          const labelText = element => {
            const copy = element.cloneNode(true);
            copy.querySelectorAll('br').forEach(br => br.replaceWith(' '));
            return normalize(copy.textContent);
          };
          const labels = [...diagram.querySelectorAll('.nodeLabel p, .edgeLabel p')].map(p => {
            const carrier = p.closest('foreignObject');
            const matrix = carrier.getScreenCTM();
            const box = p.getBoundingClientRect();
            const frame = carrier.getBoundingClientRect();
            const svg = diagram.querySelector('svg').getBoundingClientRect();
            const shape = p.closest('g.node')?.querySelector('rect')?.getBoundingClientRect();
            const inside = outer => box.left >= outer.left - 1 && box.right <= outer.right + 1 && box.top >= outer.top - 1 && box.bottom <= outer.bottom + 1;
            const scale = Math.hypot(matrix.c, matrix.d);
            const htmlAncestors = [];
            for (let element = p; element && element !== carrier; element = element.parentElement) htmlAncestors.push(element);
            return { text: labelText(p), edge: p.closest('[data-id]')?.getAttribute('data-id') || null, effectivePx: parseFloat(getComputedStyle(p).fontSize) * scale, width: box.width, height: box.height,
              unclipped: inside(frame) && inside(svg) && (!shape || inside(shape)),
              visible: htmlAncestors.every(e => getComputedStyle(e).visibility === 'visible' && getComputedStyle(e).display !== 'none' && Number(getComputedStyle(e).opacity) > 0),
              untransformed: htmlAncestors.every(e => getComputedStyle(e).transform === 'none') };
          });
          const ids = diagram.querySelector('svg')?.getAttribute('aria-describedby') || '';
          return {
            labels,
            nodes: [...diagram.querySelectorAll('g.node .nodeLabel')].map(labelText),
            edges: [...diagram.querySelectorAll('.flowchart-link')].map(e => {
              const style = getComputedStyle(e);
              const markerId = e.getAttribute('marker-end')?.match(/#([^\)]+)/)?.[1];
              const marker = markerId && document.getElementById(markerId)?.querySelector('path');
              const markerStyle = marker && getComputedStyle(marker);
              const length = e.getTotalLength();
              const start = e.getPointAtLength(0), end = e.getPointAtLength(length);
              const bounds = e.getBoundingClientRect();
              return { id: e.id, visible: style.display !== 'none' && style.visibility === 'visible' && Number(style.opacity) > 0 && Number(style.strokeOpacity) > 0 && style.stroke !== 'none' && parseFloat(style.strokeWidth) > 0 && bounds.height > 0,
                markerVisible: !!markerStyle && markerStyle.display !== 'none' && markerStyle.visibility === 'visible' && Number(markerStyle.opacity) > 0 && markerStyle.fill !== 'none',
                length, direction: end.y > start.y ? 'down' : end.y < start.y ? 'up' : 'horizontal' };
            }),
            role: diagram.getAttribute('role'), name: diagram.getAttribute('aria-label'),
            description: (diagram.getAttribute('aria-describedby') || ids).split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' '),
            overflow: document.documentElement.scrollWidth - innerWidth,
            svgHeight: diagram.querySelector('svg').getBoundingClientRect().height,
            theme: document.documentElement.dataset.theme
          };
        });
        for (const phase of ['initial', 'switched']) {
          if (phase === 'switched') await page.locator('.theme-toggle').click();
          const result = await inspect(); observations.push({ width, theme, phase, ...result });
          check(result.theme === (phase === 'initial' ? theme : theme === 'dark' ? 'light' : 'dark'), `${width}/${theme}/${phase}: active theme`);
          check(result.labels.length === 9 && result.labels.every(label => label.effectivePx >= 14 && label.width > 0 && label.height > 0 && label.visible && label.unclipped && label.untransformed), `${width}/${theme}/${phase}: nine visible unclipped labels at least 14px without unmeasured HTML transforms: ${JSON.stringify(result.labels)}`);
          check(JSON.stringify(result.nodes) === JSON.stringify(expectedNodes), `${width}/${theme}/${phase}: seven stages preserved`);
          const expectedEdges = ['A_B', 'B_C', 'C_D', 'D_C', 'D_E', 'E_F', 'F_G'];
          check(result.edges.length === 7 && expectedEdges.every(edge => result.edges.some(value => value.id.includes(edge))), `${width}/${theme}/${phase}: directed path and failure return preserved: ${JSON.stringify(result.edges)}`);
          check(result.edges.every(edge => edge.visible && edge.markerVisible && edge.length > 0 && edge.direction === (edge.id.includes('D_C') ? 'up' : 'down')), `${width}/${theme}/${phase}: visible connectors and arrowheads retain forward and return direction: ${JSON.stringify(result.edges)}`);
          check(result.labels.some(label => label.text === 'fails the gate') && result.labels.some(label => label.text === 'passes the gate'), 'both gate outcomes preserved');
          check(result.labels.some(label => label.edge === 'L_D_C_0' && label.text === 'fails the gate') && result.labels.some(label => label.edge === 'L_D_E_0' && label.text === 'passes the gate'), 'gate labels attached to the correct return and delivery edges');
          check(result.role === 'img' && result.name === 'The Forge Path', `${width}/${theme}/${phase}: authored image name`);
          check(/fails[\s\S]*Found-Ry/.test(result.description) && /passes[\s\S]*Ship and govern[\s\S]*Skillz Forge[\s\S]*GitHub/.test(result.description), `${width}/${theme}/${phase}: meaningful return and delivery description`);
          check(!/themeVariables|#[0-9a-f]{6}|-->|%%\{|\] E/.test(`${result.name} ${result.description}`), 'description excludes configuration and source fragments');
          check(result.overflow <= 1, `${width}/${theme}/${phase}: no document overflow`);
          const session = await page.context().newCDPSession(page);
          const tree = await session.send('Accessibility.getFullAXTree');
          const image = tree.nodes.find(node => !node.ignored && node.role?.value === 'image' && node.name?.value === 'The Forge Path');
          check(image?.description?.value === result.description, `${width}/${theme}/${phase}: browser accessibility tree exposes complete authored image description`);
          observations.push({ width, theme, phase, accessibleImage: image ? { role: image.role.value, name: image.name.value, description: image.description?.value } : null });
          await session.detach();
        }
        await page.close();
      }
    }
    for (const mode of ['no-javascript', 'renderer-blocked']) {
      const context = await browser.newContext({ javaScriptEnabled: mode !== 'no-javascript', viewport: { width: 390, height: 844 } });
      const page = await context.newPage();
      if (mode === 'renderer-blocked') await page.route('**/assets/vendor/mermaid/**', route => route.abort());
      await page.goto(`${base}/projects/found-ry/`);
      const alternative = page.locator('#forge-path-description');
      check(await alternative.count() === 1 && await alternative.isVisible(), `${mode}: visible text alternative`);
      const text = await alternative.count() ? await alternative.textContent() : '';
      for (const stage of ['Raw prompt', 'Prompt Forge', 'Found-Ry', 'Test matrix and audit', 'Ship and govern', 'Skillz Forge', 'GitHub']) check(text.includes(stage), `${mode}: ${stage} in alternative`);
      check(/fails[\s\S]*Found-Ry/.test(text) && /passes/.test(text), `${mode}: both gate outcomes in alternative`);
      observations.push({ mode, text });
      await context.close();
    }
    assert.deepEqual(failures, [], failures.join('\n'));
  } finally {
    if (process.env.FOUNDRY_DIAGRAM_REPORT) fs.writeFileSync(process.env.FOUNDRY_DIAGRAM_REPORT, JSON.stringify({ revision: revision || null, origin: base, observedAt: new Date().toISOString(), observations, failures }, null, 2));
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
});
