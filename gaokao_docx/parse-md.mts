/**
 * CLI used by POST /api/parse-markdown — same parser as
 * gaokao-math-assistant「上传 Markdown 并显示题目」.
 *
 * Usage: npx tsx gaokao_docx/parse-md.mts <input.md> <output.json>
 */
import { readFileSync, writeFileSync } from "node:fs";
import { parseHTML } from "linkedom";

function installDomPolyfill() {
  const { window, document, DOMParser, XMLSerializer } = parseHTML(
    "<!DOCTYPE html><html><body></body></html>",
  );
  const g = globalThis as Record<string, unknown>;
  g.window = window;
  g.document = document;
  g.DOMParser = DOMParser;
  g.XMLSerializer = XMLSerializer;
  g.Node = window.Node;
  g.HTMLElement = window.HTMLElement;
  g.DocumentFragment = window.DocumentFragment;
}

function usage(): never {
  console.error("Usage: tsx gaokao_docx/parse-md.mts <input.md> <output.json>");
  process.exit(1);
}

async function main() {
  const input = process.argv[2];
  const output = process.argv[3];
  if (!input || !output) usage();

  installDomPolyfill();
  const { parseMarkdownPaper } = await import("./markdown-paper-parser.ts");
  const text = readFileSync(input, "utf8");
  const result = parseMarkdownPaper(text);
  writeFileSync(output, JSON.stringify(result), "utf8");
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : err);
  process.exit(1);
});
