import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { test } from 'node:test';
import { chromium } from 'playwright';

const root = path.resolve(import.meta.dirname, '..');
const pagePath = 'projects/mac-studio-local-ai-workbench/index.html';
const baseline = process.env.MAC_DIAGRAM_BASELINE_REVISION && execFileSync(
  'git', ['show', `${process.env.MAC_DIAGRAM_BASELINE_REVISION}:${pagePath}`], { cwd: root });

test('Mac Studio token routing renders the authored seven-node graph', async () => {
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, 'http://localhost');
    let file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
    try {
      response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
      let payload = baseline && file === path.join(root, pagePath) ? baseline : fs.readFileSync(file);
      if (process.env.MAC_DIAGRAM_FAULT === 'syntax' && file === path.join(root, pagePath)) {
        payload = payload.toString().replace('flowchart TD', 'flowchart ?');
      }
      response.end(payload);
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch();
    const page = await browser.newPage();
    const warnings = [];
    page.on('console', async message => {
      if (message.type() === 'warning') warnings.push(await Promise.all(message.args().map(arg =>
        arg.evaluate(value => typeof value === 'object' ? { message: value?.message, hash: value?.hash } : value))));
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/projects/mac-studio-local-ai-workbench/#how-its-built`);
    const diagram = page.locator('#how-its-built .mermaid').first();
    await diagram.locator('svg').waitFor();
    const errors = await diagram.locator('.error-text').allTextContents();
    assert.deepEqual(errors, [], JSON.stringify(warnings));
    assert.equal(await diagram.locator('g.node').count(), 7);
    const labels = await diagram.locator('.nodeLabel').allTextContents();
    for (const label of ['Input surfaces', 'Token router', 'Ollama', 'LM Studio', 'mlx-lm', 'Cloud frontier', 'Output']) {
      assert.ok(labels.some(text => text.includes(label)), `authored node preserved: ${label}`);
    }
    assert.equal(await diagram.locator('path.flowchart-link').count(), 9);
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
});
