import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = resolve(root, "dist");
const sourceHtml = resolve(dist, "console.dev.html");
const outputHtml = resolve(root, "console.html");
const outputDistHtml = resolve(dist, "console.html");
let html = await readFile(sourceHtml, "utf8");
let inlinedScript = false;
let inlinedStyle = false;

function assetPath(url) {
  const relativeUrl = decodeURIComponent(url).replace(/^\.\//, "");
  const path = resolve(dist, relativeUrl);
  if (path !== dist && !path.startsWith(dist + sep)) {
    throw new Error(`Build asset escapes the dist directory: ${url}`);
  }
  return path;
}

const scriptTag = /<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>\s*<\/script>/i;
const scriptMatch = html.match(scriptTag);
if (!scriptMatch) throw new Error("Vite output did not contain the Console entry script");
const script = (await readFile(assetPath(scriptMatch[1]), "utf8"))
  .replace(/<\/script/gi, "<\\/script");
html = html.replace(scriptTag, () => `<script type="module">${script}\n</script>`);
inlinedScript = true;

const styleTag = /<link\b(?=[^>]*\brel=["']stylesheet["'])[^>]*\bhref=["']([^"']+)["'][^>]*>/i;
const styleMatch = html.match(styleTag);
if (styleMatch) {
  const style = (await readFile(assetPath(styleMatch[1]), "utf8"))
    .replace(/<\/style/gi, "<\\/style");
  html = html.replace(styleTag, () => `<style>${style}</style>`);
  inlinedStyle = true;
}

// Ignore strings inside the bundled JavaScript when checking generated HTML.
const htmlTagsOnly = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "<script>...</script>");
if (
  !inlinedScript ||
  /<script\b[^>]*\bsrc=/.test(htmlTagsOnly) ||
  /<link\b(?=[^>]*\brel=["']stylesheet["'])[^>]*\bhref=/.test(htmlTagsOnly)
) {
  throw new Error("Console bundle still depends on an external script or stylesheet");
}

await writeFile(outputHtml, html.replace(/\r\n/g, "\n"), "utf8");
await writeFile(outputDistHtml, html.replace(/\r\n/g, "\n"), "utf8");
console.log(`Wrote self-contained FastAPI Console: ${outputHtml} (script inlined, stylesheet ${inlinedStyle ? "inlined" : "not emitted"})`);
