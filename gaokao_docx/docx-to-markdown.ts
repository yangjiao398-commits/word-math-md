import JSZip from "jszip";
import mammoth from "mammoth";
import TurndownService from "turndown";
import { wrapBareLatexAfterOptions } from "./latex-to-html";
import { replaceOmmlWithLatexInXml } from "./omml-to-latex";

export interface DocxToMarkdownResult {
  markdown: string;
  fileName: string;
  mathConverted: number;
  imageCount: number;
  vectorImagesConverted: number;
  warnings: string[];
}

export type DocxImageHandler = (info: {
  contentType: string;
  base64: string;
  index: number;
}) => Promise<{ src: string } | { src: "" }>;

export interface ConvertDocxOptions {
  /** 自定义图片落地方式；默认嵌入 data URL */
  imageHandler?: DocxImageHandler;
  /**
   * 预转换好的 WMF/EMF→PNG 映射（sha1 hex → PNG 字节）。
   * 由 CLI（Node）生成后传入；浏览器端不要 import 含 node: 的模块。
   */
  vectorPngBySha1?: Map<string, Uint8Array>;
}

async function sha1Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-1", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function bytesToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== "undefined") {
    return Buffer.from(bytes).toString("base64");
  }
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function preprocessDocx(arrayBuffer: ArrayBuffer): Promise<{
  buffer: ArrayBuffer;
  mathConverted: number;
}> {
  try {
    const zip = await JSZip.loadAsync(arrayBuffer);
    const docEntry = zip.file("word/document.xml");
    if (!docEntry) return { buffer: arrayBuffer, mathConverted: 0 };
    const xml = await docEntry.async("string");
    const { xml: nextXml, count } = replaceOmmlWithLatexInXml(xml);
    if (count === 0) return { buffer: arrayBuffer, mathConverted: 0 };
    zip.file("word/document.xml", nextXml);
    const buffer = await zip.generateAsync({ type: "arraybuffer" });
    return { buffer, mathConverted: count };
  } catch {
    return { buffer: arrayBuffer, mathConverted: 0 };
  }
}

function htmlToMarkdown(html: string): string {
  const turndown = new TurndownService({
    headingStyle: "atx",
    codeBlockStyle: "fenced",
    bulletListMarker: "-",
    emDelimiter: "*",
  });

  turndown.addRule("images", {
    filter: "img",
    replacement: (_content, node) => {
      const el = node as HTMLImageElement;
      const alt = el.getAttribute("alt") || "配图";
      const src = el.getAttribute("src") || "";
      if (!src) return "";
      return `\n\n![${alt}](${src})\n\n`;
    },
  });

  // 保护已有 $...$ / $$...$$，避免 Turndown 转义点号、反斜杠时弄坏选项后的公式
  const latexSlots: string[] = [];
  let protectedHtml = html.replace(
    /\$\$[\s\S]+?\$\$|\$[^$\n]+\$/g,
    (m) => {
      const i = latexSlots.length;
      latexSlots.push(m);
      return `@@LATEX${i}@@`;
    },
  );

  let md = turndown.turndown(protectedHtml);
  md = md.replace(/@@LATEX(\d+)@@/g, (_m, idx: string) => latexSlots[Number(idx)] ?? "");

  md = md
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  // 还原题号 / 选项转义：1\. A\. B\. C\. D\.
  md = md.replace(/(^|\n)([ \t]*)(\d+)\\([.．])/gm, "$1$2$3$4");
  md = md.replace(/([A-Da-d])\\([.．、])/g, "$1$2");
  md = md.replace(/\\\$/g, "$");
  // 清掉误入的 HTML 残片
  md = md.replace(/<\/?(?:span|div|font)[^>]*>/gi, "");
  // 选项后裸 LaTeX 自动加 $
  md = wrapBareLatexAfterOptions(md);

  md = md.replace(/(【答案】|【分析】|【详解】)/g, "\n$1");
  md = md.replace(/(^|\n)(\d+\s*(?:\\[.．]|[.．、]))/g, "\n\n$2");
  // 选项行前适当换行，避免挤在一行导致公式定界混乱
  md = md.replace(/([^\n])\s+([A-Da-d][.．、]\s*)/g, "$1\n$2");

  return md.replace(/\n{3,}/g, "\n\n").trim() + "\n";
}

function extFromContentType(contentType: string): string {
  const t = contentType.toLowerCase();
  if (t.includes("jpeg") || t.includes("jpg")) return "jpg";
  if (t.includes("png")) return "png";
  if (t.includes("gif")) return "gif";
  if (t.includes("webp")) return "webp";
  if (t.includes("svg")) return "svg";
  return "bin";
}

/**
 * 将 .docx 二进制转为 Markdown（OMML→LaTeX + mammoth + turndown + 选项公式修复）。
 * 注意：本文件须保持浏览器可打包，禁止 import node:* 模块。
 */
export async function convertDocxBufferToMarkdown(
  arrayBuffer: ArrayBuffer,
  fileName: string,
  options?: ConvertDocxOptions,
): Promise<DocxToMarkdownResult> {
  const warnings: string[] = [];
  const name = fileName.replace(/\.docx$/i, "") || "试卷";

  const { buffer, mathConverted } = await preprocessDocx(arrayBuffer);
  if (mathConverted > 0) {
    warnings.push(`已转换 ${mathConverted} 处 Word 公式为 LaTeX。`);
  }

  let imageCount = 0;
  const customHandler = options?.imageHandler;
  const vectorPngMap = options?.vectorPngBySha1;
  const vectorImagesConverted = vectorPngMap?.size ?? 0;
  if (vectorImagesConverted > 0) {
    warnings.push(`已将 ${vectorImagesConverted} 张 WMF/EMF 公式图转为 PNG。`);
  }

  // Node 端 mammoth 只认 buffer；浏览器端认 arrayBuffer。
  // CLI 会注入 linkedom 的 window，故不能用 typeof window 判断。
  const mammothInput =
    typeof process !== "undefined" && Boolean(process.versions?.node)
      ? { buffer: Buffer.from(new Uint8Array(buffer)) }
      : { arrayBuffer: buffer };

  const result = await mammoth.convertToHtml(mammothInput, {
    convertImage: mammoth.images.imgElement(async (image) => {
      const type = (image.contentType || "image/png").toLowerCase();
      const isVector = type.includes("wmf") || type.includes("emf");

      if (isVector) {
        if (!vectorPngMap || vectorPngMap.size === 0) {
          warnings.push("部分旧版矢量图无法嵌入 Markdown，已跳过。");
          return { src: "" };
        }
        const ab = await image.readAsArrayBuffer();
        const key = await sha1Hex(new Uint8Array(ab));
        const png = vectorPngMap.get(key);
        if (!png) {
          warnings.push("部分旧版矢量图无法嵌入 Markdown，已跳过。");
          return { src: "" };
        }
        imageCount += 1;
        const base64 = bytesToBase64(png);
        if (customHandler) {
          return customHandler({
            contentType: "image/png",
            base64,
            index: imageCount - 1,
          });
        }
        return { src: `data:image/png;base64,${base64}` };
      }

      const base64 = await image.readAsBase64String();
      imageCount += 1;
      if (customHandler) {
        return customHandler({
          contentType: image.contentType || "image/png",
          base64,
          index: imageCount - 1,
        });
      }
      return { src: `data:${image.contentType};base64,${base64}` };
    }),
  });

  for (const msg of result.messages) {
    if (msg.type === "warning" || msg.type === "error") {
      if (/unrecognised element|oMath|v:path|OLEObject|wmf|emf/i.test(msg.message)) {
        continue;
      }
      warnings.push(msg.message);
    }
  }

  // 去重警告（矢量图跳过等会重复很多次）
  const uniqueWarnings = [...new Set(warnings)].slice(0, 8);

  let html = result.value || "";
  html = html.replace(/<img\b[^>]*src=(""|'')[^>]*>/gi, "");

  const markdown = htmlToMarkdown(html);

  return {
    markdown,
    fileName: `${name}.md`,
    mathConverted,
    imageCount,
    vectorImagesConverted,
    warnings: uniqueWarnings,
  };
}

/**
 * 浏览器 File 入口：图片默认以 data URL 嵌入。
 */
export async function convertDocxToMarkdown(
  file: File,
): Promise<DocxToMarkdownResult> {
  return convertDocxBufferToMarkdown(await file.arrayBuffer(), file.name);
}

/** 触发浏览器下载 Markdown 文件（带 UTF-8 BOM，避免 Windows 记事本误判编码） */
export function downloadMarkdownFile(markdown: string, fileName: string): void {
  const withBom = markdown.startsWith("\uFEFF") ? markdown : `\uFEFF${markdown}`;
  const blob = new Blob([withBom], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName.endsWith(".md") ? fileName : `${fileName}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export { extFromContentType };
