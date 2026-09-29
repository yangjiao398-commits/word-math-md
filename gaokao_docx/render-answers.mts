/**
 * Render stored answer markdown to KaTeX HTML.
 * Usage: tsx gaokao_docx/render-answers.mts <input.json> <output.json>
 * input.json: string[]
 */
import { readFileSync, writeFileSync } from "node:fs";

import { replaceLatexWithKatexHtml } from "./latex-to-html.ts";

function usage(): never {
  console.error("Usage: tsx gaokao_docx/render-answers.mts <input.json> <output.json>");
  process.exit(1);
}

function renderOne(raw: string): string {
  const parts = String(raw || "")
    .split("##")
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return "";
  return parts
    .map((part) => replaceLatexWithKatexHtml(part))
    .join(' <span class="ans-or">或</span> ');
}

function main() {
  const input = process.argv[2];
  const output = process.argv[3];
  if (!input || !output) usage();
  const texts = JSON.parse(readFileSync(input, "utf8"));
  if (!Array.isArray(texts)) {
    throw new Error("input must be a JSON array of strings");
  }
  const html = texts.map((item) => renderOne(String(item ?? "")));
  writeFileSync(output, JSON.stringify(html), "utf8");
}

main();
