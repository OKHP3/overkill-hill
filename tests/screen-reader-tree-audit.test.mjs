import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium } from "playwright";
import { checkMermaidDiagrams, dismissTransitionAnnouncement } from "../scripts/screen-reader-tree-audit.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true }); });
after(async () => { await browser?.close(); });

async function openAnnouncement(markup) {
  const page = await browser.newPage();
  await page.setContent(`<main><h1>Page</h1></main>${markup}`);
  await page.locator("#capability-transition-dialog").evaluate(dialog => dialog.showModal());
  return page;
}

async function exposedMainCount(page) {
  const client = await page.context().newCDPSession(page);
  try {
    await client.send("Accessibility.enable");
    const { nodes } = await client.send("Accessibility.getFullAXTree");
    return nodes.filter(node => !node.ignored && node.role?.value === "main").length;
  } finally { await client.detach(); }
}

test("a named first-visit announcement closes before page landmarks are exposed", async () => {
  const page = await openAnnouncement('<dialog id="capability-transition-dialog" aria-label="Transition update"><button>Close</button></dialog>');
  try {
    assert.equal(await exposedMainCount(page), 0, "modal hides background landmark");
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), true);
    assert.deepEqual(failures, []);
    assert.equal(await exposedMainCount(page), 1, "landmark is exposed after native close");
  } finally { await page.close(); }
});

test("an unnamed announcement fails even if another named dialog exists", async () => {
  const page = await openAnnouncement('<dialog id="capability-transition-dialog"><div role="dialog" aria-label="Other dialog">Nested dialog</div><button>Close</button></dialog>');
  try {
    assert.equal(await page.getByRole("dialog", { name: "Other dialog" }).count(), 1);
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), true);
    assert.deepEqual(failures, ["transition announcement has no accessible dialog name"]);
    assert.equal(await page.locator("#capability-transition-dialog").evaluate(dialog => dialog.open), false);
  } finally { await page.close(); }
});

test("an announcement that rejects Escape fails rather than auditing a hidden page", async () => {
  const page = await openAnnouncement('<dialog id="capability-transition-dialog" aria-label="Transition update"><button>Close</button></dialog>');
  try {
    await page.locator("#capability-transition-dialog").evaluate(dialog => {
      dialog.addEventListener("cancel", event => event.preventDefault());
    });
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), false);
    assert.deepEqual(failures, ["transition announcement did not close after Escape"]);
    assert.equal(await page.locator("#capability-transition-dialog").evaluate(dialog => dialog.open), true);
    assert.equal(await exposedMainCount(page), 0);
  } finally { await page.close(); }
});

test("an absent or already dismissed announcement does not block the audit", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<main><h1>Page</h1></main><dialog id="capability-transition-dialog"></dialog>');
    const failures = [];
    assert.equal(await dismissTransitionAnnouncement(page, failures), true);
    assert.deepEqual(failures, []);
    assert.equal(await exposedMainCount(page), 1);
  } finally { await page.close(); }
});

test("named static carriers and standalone SVGs are each inspected once", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<div class="mermaid" role="img" aria-label="First diagram"><svg role="img" aria-label="Diagram nested"></svg></div><svg role="img" aria-label="Diagram standalone"></svg>');
    assert.deepEqual(await checkMermaidDiagrams(page), []);
  } finally { await page.close(); }
});

test("a marked standalone SVG remains in scope when its name or role is missing", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<svg data-diagram-label="Standalone diagram" role="img" aria-label="Diagram standalone"></svg>');
    const diagram = page.locator("svg");
    assert.deepEqual(await checkMermaidDiagrams(page), []);
    await diagram.evaluate((node) => node.removeAttribute("aria-label"));
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1: accessible image needs a name of at least 8 characters"]);
    await diagram.evaluate((node) => node.removeAttribute("role"));
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1: expected its own accessible image, found 0"]);
  } finally { await page.close(); }
});

test("a named carrier without a rendered SVG fails even with other named images", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<img alt="Unrelated image"><div class="mermaid" role="img" aria-label="Pending diagram">flowchart TD</div>');
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1: no rendered SVG found"]);
  } finally { await page.close(); }
});

test("unrelated named images cannot hide a diagram without its own name", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<img alt="Unrelated first image"><img alt="Unrelated second image"><div class="mermaid" role="img"><svg></svg></div>');
    const client = await page.context().newCDPSession(page);
    try {
      await client.send("Accessibility.enable");
      const { nodes } = await client.send("Accessibility.getFullAXTree");
      const namedImages = nodes.filter((node) => !node.ignored && node.role?.value === "image" && (node.name?.value || "").trim().length >= 8);
      assert.ok(namedImages.length >= 1, "the former global count would accept this one-diagram fixture");
    } finally { await client.detach(); }
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1: accessible image needs a name of at least 8 characters"]);
  } finally { await page.close(); }
});

test("each carrier is checked even when another has the same name", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<div class="mermaid" role="img" aria-label="Shared diagram"><svg></svg></div><div class="mermaid" role="img" aria-label="Shared diagram"><svg></svg></div>');
    assert.deepEqual(await checkMermaidDiagrams(page), []);
    await page.locator(".mermaid").nth(1).evaluate((node) => node.removeAttribute("aria-label"));
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 2: accessible image needs a name of at least 8 characters"]);
  } finally { await page.close(); }
});

test("an ignored carrier cannot be replaced by a similarly named image", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<img alt="Shared diagram"><div class="mermaid" role="img" aria-label="Shared diagram" aria-hidden="true"><svg></svg></div>');
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1: expected its own accessible image, found 0"]);
  } finally { await page.close(); }
});

test("interactive diagrams expose their named group and each named link", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<div class="mermaid" role="group" aria-label="Linked diagram"><svg role="group"><a href="#one" aria-label="First destination"><text>One</text></a><a href="#two" aria-label="Second destination"><text>Two</text></a></svg></div>');
    assert.deepEqual(await checkMermaidDiagrams(page), []);
    await page.locator("svg a").nth(1).evaluate((node) => node.setAttribute("aria-hidden", "true"));
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1 link 2: expected its own accessible link in the diagram"]);
  } finally { await page.close(); }
});

test("an unnamed interactive link fails despite other named links", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<div class="mermaid" role="group" aria-label="Linked diagram"><svg role="group"><a href="#one" aria-label="First destination"><text>One</text></a><a href="#two"><rect width="1" height="1"></rect></a></svg></div>');
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1 link 2: accessible link has no name"]);
  } finally { await page.close(); }
});

test("an interactive standalone SVG can expose graphics-document semantics", async () => {
  const page = await browser.newPage();
  try {
    await page.setContent('<svg data-diagram-label="Standalone diagram" role="graphics-document document" aria-label="Linked diagram"><a href="#one" aria-label="First destination"><text>One</text></a></svg>');
    assert.deepEqual(await checkMermaidDiagrams(page), []);
    await page.locator("svg a").evaluate((node) => node.setAttribute("aria-hidden", "true"));
    assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1 link 1: expected its own accessible link in the diagram"]);
  } finally { await page.close(); }
});

test("changing diagram identities are reported instead of silently skipped", async () => {
  let documentCalls = 0;
  let detached = false;
  const client = {
    async send(method) {
      if (method === "DOM.getDocument") {
        documentCalls += 1;
        return { root: { nodeName: "DIV", attributes: ["class", "mermaid"], backendNodeId: documentCalls } };
      }
      if (method === "Accessibility.getFullAXTree") return { nodes: [] };
      return {};
    },
    async detach() { detached = true; },
  };
  const page = { context: () => ({ newCDPSession: async () => client }) };
  assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram identities changed during accessibility inspection"]);
  assert.equal(documentCalls, 4);
  assert.equal(detached, true);
});

test("a carrier without a backend identity cannot match an unrelated AX node", async () => {
  const client = {
    async send(method) {
      if (method === "DOM.getDocument") return { root: { nodeName: "DIV", attributes: ["class", "mermaid"], children: [{ nodeName: "svg", backendNodeId: 1 }] } };
      if (method === "Accessibility.getFullAXTree") return { nodes: [{ nodeId: "1", role: { value: "image" }, name: { value: "Other diagram" } }] };
      return {};
    },
    async detach() {},
  };
  const page = { context: () => ({ newCDPSession: async () => client }) };
  assert.deepEqual(await checkMermaidDiagrams(page), ["Mermaid diagram 1: missing DOM backend identity"]);
});
