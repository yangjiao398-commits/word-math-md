/**
 * CLI used by POST /api/convert — same pipeline as
 * gaokao-math-assistant「选择 Word 并转换为 Markdown」.
 *
 * Usage: npx tsx gaokao_docx/convert.mts <input.docx> <output.md>
 */
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
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
  console.error("Usage: tsx gaokao_docx/convert.mts <input.docx> <output.md>");
  process.exit(1);
}

async function main() {
  const input = process.argv[2];
  const output = process.argv[3];
  if (!input || !output) usage();

  installDomPolyfill();
  const { convertDocxBufferToMarkdown } = await import("./docx-to-markdown.ts");

  const buf = readFileSync(input);
  const arrayBuffer = buf.buffer.slice(
    buf.byteOffset,
    buf.byteOffset + buf.byteLength,
  );
  const result = await convertDocxBufferToMarkdown(
    arrayBuffer,
    path.basename(input),
  );
  const markdown = result.markdown.startsWith("\uFEFF")
    ? result.markdown
    : `\uFEFF${result.markdown}`;
  writeFileSync(output, markdown, "utf8");
  writeFileSync(
    `${output}.meta.json`,
    JSON.stringify({
      fileName: result.fileName,
      mathConverted: result.mathConverted,
      imageCount: result.imageCount,
      vectorImagesConverted: result.vectorImagesConverted,
      warnings: result.warnings,
    }),
  );
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : err);
  process.exit(1);
});
