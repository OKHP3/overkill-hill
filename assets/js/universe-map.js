// Generated maps use strict Mermaid rendering and links from the visible outline.
import mermaid from "/assets/vendor/mermaid/mermaid.esm.min.mjs";

const diagrams = [...document.querySelectorAll(".universe-diagram")];
const sources = new Map(diagrams.map((element) => [element, element.textContent]));
const compactViewport = window.matchMedia("(max-width: 360px)");
let sequence = 0;
let pending = Promise.resolve();

async function nodeId(url) {
  const bytes = new TextEncoder().encode(url);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return "n" + [...new Uint8Array(hash)].map((value) => value.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

function configure() {
  const styles = getComputedStyle(document.documentElement);
  const token = (key, fallback) => styles.getPropertyValue(key).trim() || fallback;
  mermaid.initialize({
    layout: "dagre",
    look: "classic",
    startOnLoad: false,
    securityLevel: "strict",
    theme: "base",
    themeVariables: {
      primaryColor: token("--mermaid-primary-color", "#111827"),
      primaryTextColor: token("--mermaid-primary-text-color", "#e5e7eb"),
      primaryBorderColor: token("--mermaid-primary-border-color", "#c46a2c"),
      lineColor: token("--mermaid-line-color", "#c46a2c"),
    },
    flowchart: {useMaxWidth: true, htmlLabels: false, wrappingWidth: 180},
  });
}

function applyDiagramWidth(element, view = element.querySelector("svg")) {
  if (!view) return;
  const minimumWidth = compactViewport.matches ? 0 : 720;
  view.style.width = Math.max(minimumWidth, view.viewBox.baseVal.width) + "px";
}

async function renderVisible() {
  configure();
  for (const element of diagrams) {
    if (!element.closest("details")?.open || element.dataset.rendered) continue;
    try {
      const focusedLink = document.activeElement?.closest(".universe-diagram svg a[href]");
      const restoreFocus = focusedLink && element.contains(focusedLink)
        ? {href: focusedLink.getAttribute("href"), label: focusedLink.getAttribute("aria-label")}
        : null;
      const {svg} = await mermaid.render("universe-render-" + sequence++, sources.get(element));
      element.innerHTML = svg;
      const view = element.querySelector("svg");
      view.setAttribute("aria-label", element.closest("details").querySelector("summary").textContent);
      // Preserve readable labels on phones; the diagram scrolls inside its panel.
      element.style.overflowX = "auto";
      element.style.maxWidth = "100%";
      applyDiagramWidth(element, view);
      view.style.maxWidth = "none";
      view.style.height = "auto";
      for (const link of element.closest("details").querySelectorAll("li a[href]")) {
        const target = new URL(link.getAttribute("href"), "https://overkillhill.com/");
        if (target.origin !== "https://overkillhill.com" || target.username || target.password) continue;
        const id = await nodeId(target.href);
        const node = [...view.querySelectorAll("g.node")].find((item) => item.id.includes("flowchart-" + id + "-"));
        if (!node) continue;
        const anchor = document.createElementNS("http://www.w3.org/2000/svg", "a");
        anchor.setAttribute("href", target.pathname + target.hash);
        anchor.setAttribute("aria-label", link.textContent);
        anchor.setAttribute("tabindex", "0");
        anchor.style.scrollMargin = "6px";
        while (node.firstChild) anchor.append(node.firstChild);
        node.append(anchor);
      }
      element.dataset.rendered = "true";
      element.hidden = false;
      if (restoreFocus) {
        const replacement = [...view.querySelectorAll("a[href]")].find((anchor) => (
          anchor.getAttribute("href") === restoreFocus.href
          && anchor.getAttribute("aria-label") === restoreFocus.label
        ));
        if (replacement) {
          replacement.focus({preventScroll: true});
          replacement.scrollIntoView({behavior: "instant", block: "nearest", inline: "nearest"});
        }
      }
    } catch (error) {
      element.textContent = "The diagram is unavailable. Use the page links below.";
      element.hidden = false;
      console.error("Universe diagram rendering failed", error);
    }
  }
}

function enqueue() {
  pending = pending.then(renderVisible).catch((error) => {
    console.error("Universe diagram queue failed", error);
  });
}
document.querySelector(".universe-generated")?.addEventListener("focusin", (event) => {
  const link = event.target.closest?.(".universe-diagram svg a[href]");
  link?.scrollIntoView({behavior: "instant", block: "nearest", inline: "nearest"});
});
compactViewport.addEventListener("change", () => {
  diagrams.forEach((element) => applyDiagramWidth(element));
  const focusedLink = document.activeElement?.closest(".universe-diagram svg a[href]");
  focusedLink?.scrollIntoView({behavior: "instant", block: "nearest", inline: "nearest"});
});
document.querySelectorAll(".universe-generated details").forEach((details) => details.addEventListener("toggle", enqueue));
new MutationObserver(() => {
  diagrams.forEach((element) => { element.removeAttribute("data-rendered"); });
  enqueue();
}).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme", "data-color-scheme"]});
enqueue();
