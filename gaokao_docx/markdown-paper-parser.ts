import type { ImportedQuestion } from "./types";
import {
  replaceLatexWithKatexHtml,
  prepareMarkdownMath,
  replaceInlineDollarMath,
  recoverDanglingDollarLatex,
  splitAdjacentInlineDollars,
  normalizeWordMathArtifacts,
} from "./latex-to-html";

const SECTION_MARKERS = ["【答案】", "【解析】", "【分析】", "【详解】"] as const;

type SectionKey = "stem" | "answer" | "analysis" | "detail";

const MARKER_TO_KEY: Record<(typeof SECTION_MARKERS)[number], SectionKey> = {
  "【答案】": "answer",
  "【解析】": "analysis",
  "【分析】": "analysis",
  "【详解】": "detail",
};

/** 本地图片资源：规范化路径/文件名 → data URL */
export type ImageAssetMap = Map<string, string>;

export interface ParseNotice {
  level: "ok" | "tip" | "warn";
  text: string;
}

export interface ParseMarkdownResult {
  questions: ImportedQuestion[];
  notices: ParseNotice[];
  warnings: string[];
  unresolvedImages: string[];
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function stripTags(html: string): string {
  return html
    .replace(/<img[^>]*>/gi, "[图]")
    .replace(/<span[^>]*class="katex[\s\S]*?<\/span>/gi, "[公式]")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const COMMON_IMAGE_DIRS = [
  "image",
  "images",
  "img",
  "imgs",
  "media",
  "assets",
  "pic",
  "pics",
  "static",
  "figures",
  "figure",
];

function normalizePathKey(path: string): string {
  return path
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.?\//, "")
    .replace(/^file:\/\//i, "")
    .toLowerCase();
}

function basenameKey(path: string): string {
  const norm = normalizePathKey(path);
  const parts = norm.split("/");
  return parts[parts.length - 1] || norm;
}

/** 为同一张图登记多种相对路径键，便于匹配 image/xxx.jpg */
function registerAssetKeys(
  map: ImageAssetMap,
  pathLike: string,
  dataUrl: string,
): void {
  const norm = normalizePathKey(pathLike);
  if (!norm) return;

  map.set(norm, dataUrl);
  map.set(`./${norm}`, dataUrl);

  const base = basenameKey(norm);
  map.set(base, dataUrl);

  const parts = norm.split("/").filter(Boolean);
  for (let i = 0; i < parts.length; i++) {
    const suffix = parts.slice(i).join("/");
    map.set(suffix, dataUrl);
    map.set(`./${suffix}`, dataUrl);
  }

  // 即使只选中了文件本身，也登记常见子目录相对路径
  for (const dir of COMMON_IMAGE_DIRS) {
    map.set(`${dir}/${base}`, dataUrl);
    map.set(`./${dir}/${base}`, dataUrl);
  }
}

export function isImageFile(file: File): boolean {
  const name = file.name.toLowerCase();
  if (/\.(jpe?g|png|gif|webp|bmp|svg)$/i.test(name)) return true;
  return /^image\//i.test(file.type);
}

export function isMarkdownFileName(name: string): boolean {
  const n = name.toLowerCase();
  return n.endsWith(".md") || n.endsWith(".markdown") || n.endsWith(".mdown");
}

export async function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

/** 从用户选中的图片文件构建资源表（支持 image/xxx.jpg 等相对路径） */
export async function buildImageAssetMap(files: File[]): Promise<ImageAssetMap> {
  const map: ImageAssetMap = new Map();
  for (const file of files) {
    if (!isImageFile(file)) continue;
    const dataUrl = await fileToDataUrl(file);
    const rel =
      (file as File & { webkitRelativePath?: string }).webkitRelativePath ||
      file.name;

    registerAssetKeys(map, file.name, dataUrl);
    registerAssetKeys(map, rel, dataUrl);

    // 若相对路径含多层目录，额外按「最后两级」登记：image/a.jpg
    const parts = normalizePathKey(rel).split("/").filter(Boolean);
    if (parts.length >= 2) {
      registerAssetKeys(map, parts.slice(-2).join("/"), dataUrl);
    }
  }
  return map;
}

function parseMdImageTarget(raw: string): string {
  let t = raw.trim();
  const withTitle = t.match(/^(.*?)\s+("([^"]*)"|'([^']*)')\s*$/);
  if (withTitle) t = withTitle[1].trim();
  if (t.startsWith("<") && t.endsWith(">")) t = t.slice(1, -1).trim();
  if (
    (t.startsWith('"') && t.endsWith('"')) ||
    (t.startsWith("'") && t.endsWith("'"))
  ) {
    t = t.slice(1, -1).trim();
  }
  return t;
}

function resolveImageSrc(
  src: string,
  assets: ImageAssetMap | undefined,
  unresolved: string[],
): string {
  const trimmed = src.trim().replace(/\\/g, "/");
  if (!trimmed) return trimmed;

  if (/^(https?:|data:|blob:)/i.test(trimmed)) {
    try {
      return encodeURI(decodeURI(trimmed));
    } catch {
      return trimmed;
    }
  }

  if (!assets || assets.size === 0) {
    unresolved.push(trimmed);
    return trimmed;
  }

  const candidates = new Set<string>();
  const add = (p: string) => {
    const n = normalizePathKey(p);
    if (n) {
      candidates.add(n);
      candidates.add(`./${n}`);
    }
  };

  add(trimmed);
  add(basenameKey(trimmed));
  try {
    add(decodeURIComponent(trimmed));
    add(basenameKey(decodeURIComponent(trimmed)));
  } catch {
    /* ignore */
  }

  // image/../image/a.jpg 归一
  add(trimmed.replace(/\/\.\//g, "/"));

  for (const key of candidates) {
    const hit = assets.get(key);
    if (hit) return hit;
  }

  const base = basenameKey(trimmed);
  for (const [key, url] of assets) {
    if (key === base || key.endsWith("/" + base) || basenameKey(key) === base) {
      return url;
    }
  }

  unresolved.push(trimmed);
  return trimmed;
}

function imgTag(src: string, alt: string): string {
  return `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt || "题目配图")}" loading="lazy" />`;
}

function renderMarkdownTable(block: string): string {
  const lines = block
    .trim()
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) return escapeHtml(block);

  const splitRow = (line: string) => {
    let s = line.replace(/^\|/, "").replace(/\|$/, "");
    return s.split("|").map((c) => c.trim());
  };

  const header = splitRow(lines[0]!);
  const sep = lines[1]!;
  if (!/^\|?[\s:|-]+\|?$/.test(sep) || !sep.includes("-")) {
    return escapeHtml(block).replace(/\n/g, "<br/>");
  }

  const bodyLines = lines.slice(2);
  const th = header
    .map((c) => `<th>${escapeHtml(c)}</th>`)
    .join("");
  const rows = bodyLines
    .map((line) => {
      const cells = splitRow(line);
      while (cells.length < header.length) cells.push("");
      return `<tr>${cells
        .slice(0, header.length)
        .map((c) => `<td>${escapeHtml(c)}</td>`)
        .join("")}</tr>`;
    })
    .join("");

  return `<div class="md-table-wrap"><table><thead><tr>${th}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

/**
 * 将题目片段中的 Markdown 转为可展示 HTML。
 * LaTeX 渲染为 KaTeX；本地相对路径图片通过 assets 转为 data URL。
 */
export function markdownFragmentToHtml(
  md: string,
  assets?: ImageAssetMap,
  unresolved?: string[],
): string {
  const trimmed = md.trim();
  if (!trimmed) return "";

  const missing = unresolved ?? [];
  const slots: string[] = [];
  const park = (html: string) => {
    const i = slots.length;
    slots.push(html);
    return `%%MD${i}%%`;
  };

  let s = prepareMarkdownMath(
    trimmed.replace(/\r\n/g, "\n").replace(/＄/g, "$"),
  );
  s = normalizeWordMathArtifacts(s);
  s = recoverDanglingDollarLatex(s);
  s = splitAdjacentInlineDollars(s);

  // 0) MinerU / 导出占位图
  s = s.replace(/<!--\s*image\s*-->/gi, () =>
    park(
      `<span class="md-image-missing" title="原 PDF 中的配图未嵌入">[配图]</span>`,
    ),
  );

  // 1) 公式：先 park，避免 {*{20}{c}} 里的 * 被当成 Markdown 斜体
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_m, tex: string) =>
    park(replaceLatexWithKatexHtml(`$$${tex}$$`)),
  );
  s = s.replace(/\\\[([\s\S]+?)\\\]/g, (_m, tex: string) =>
    park(replaceLatexWithKatexHtml(`\\[${tex}\\]`)),
  );
  s = s.replace(/\\\(([\s\S]+?)\\\)/g, (_m, tex: string) =>
    park(replaceLatexWithKatexHtml(`\\(${tex}\\)`)),
  );
  s = replaceInlineDollarMath(s, (tex) =>
    park(replaceLatexWithKatexHtml(`$${tex}$`)),
  );
  // 配对失败留下的孤立 $（保留 )$ 以便兜底识别公式）
  s = s.replace(/(^|[\s（）])\$(?=[\s）]|$)/gm, "$1");
  s = s.replace(/(?:\\_){2,}/g, (m) => "_".repeat(m.length / 2));
  s = s.replace(/\\_/g, "_");

  // 2) Obsidian/部分导出：![[image.jpg]]
  s = s.replace(/!\[\[([^\]]+)\]\]/g, (_m, raw: string) => {
    const src = resolveImageSrc(raw.trim().split("|")[0].trim(), assets, missing);
    return park(imgTag(src, "题目配图"));
  });

  // 3) 标准 Markdown 图片（允许空格路径、<>、title）
  s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_m, alt: string, rawTarget: string) => {
    const parsed = parseMdImageTarget(rawTarget);
    const src = resolveImageSrc(parsed, assets, missing);
    return park(imgTag(src, alt));
  });

  // 4) 安全保留常见 HTML 块（MinerU 表格等），并改写相对路径 img
  s = s.replace(
    /<(table|thead|tbody|tr|td|th|div|p|ul|ol|li|br|hr|span|sup|sub|section)\b[^>]*>[\s\S]*?<\/\1>/gi,
    (block) => {
      const fixed = block.replace(/<img\b([^>]*)>/gi, (tag, attrs: string) => {
        const srcMatch =
          attrs.match(/\bsrc\s*=\s*"([^"]*)"/i) ||
          attrs.match(/\bsrc\s*=\s*'([^']*)'/i) ||
          attrs.match(/\bsrc\s*=\s*([^\s>]+)/i);
        if (!srcMatch) return tag;
        const rawSrc = srcMatch[1];
        const resolved = resolveImageSrc(rawSrc, assets, missing);
        return tag.replace(srcMatch[0], `src="${escapeHtml(resolved)}"`);
      });
      return park(fixed);
    },
  );
  s = s.replace(/<img\b([^>]*)>/gi, (tag, attrs: string) => {
    const srcMatch =
      attrs.match(/\bsrc\s*=\s*"([^"]*)"/i) ||
      attrs.match(/\bsrc\s*=\s*'([^']*)'/i) ||
      attrs.match(/\bsrc\s*=\s*([^\s>]+)/i);
    if (!srcMatch) return park(tag);
    const rawSrc = srcMatch[1];
    const resolved = resolveImageSrc(rawSrc, assets, missing);
    const nextAttrs = attrs.replace(srcMatch[0], `src="${escapeHtml(resolved)}"`);
    return park(`<img${nextAttrs}>`);
  });
  s = s.replace(/<br\s*\/?>/gi, () => park("<br/>"));

  // 5) GFM 表格
  s = s.replace(/(?:^|\n)((?:\|[^\n]*\|\n)+)/g, (full, tableBlock: string) => {
    const prefix = full.startsWith("\n") ? "\n" : "";
    return prefix + park(renderMarkdownTable(tableBlock));
  });

  // 6) 标题（标题内公式已 park）
  s = s.replace(/^(#{1,4})\s+(.+)$/gm, (_m, hashes: string, title: string) => {
    const level = Math.min(hashes.length + 2, 6);
    return park(`<h${level} class="md-h">${escapeHtml(title)}</h${level}>`);
  });

  // 7) 行内代码 / 粗体 / 斜体
  s = s.replace(/`([^`]+)`/g, (_m, code: string) =>
    park(`<code>${escapeHtml(code)}</code>`),
  );
  s = s.replace(/\*\*([^*]+)\*\*/g, (_m, t: string) =>
    park(`<strong>${escapeHtml(t)}</strong>`),
  );
  s = s.replace(/\*([^*]+)\*/g, (_m, t: string) =>
    park(`<em>${escapeHtml(t)}</em>`),
  );

  // 8) 选项行尽量换行保留：A./B. 前补换行感
  s = s.replace(/(?<!\n)([ \t]+)([A-Da-d][.．、])/g, "\n$2");

  s = escapeHtml(s).replace(/\n/g, "<br/>");
  // 多层 park（标题/表格内含公式）需展开多次
  for (let i = 0; i < 32 && /%%MD\d+%%/.test(s); i++) {
    s = s.replace(/%%MD(\d+)%%/g, (_m, idx: string) => slots[Number(idx)] ?? "");
  }
  return s;
}

function findSectionCuts(
  block: string,
): Array<{ key: SectionKey; start: number; markerLen: number }> {
  const cuts: Array<{ key: SectionKey; start: number; markerLen: number }> = [];
  for (const marker of SECTION_MARKERS) {
    let from = 0;
    while (from < block.length) {
      const idx = block.indexOf(marker, from);
      if (idx < 0) break;
      cuts.push({
        key: MARKER_TO_KEY[marker],
        start: idx,
        markerLen: marker.length,
      });
      from = idx + marker.length;
    }
  }
  cuts.sort((a, b) => a.start - b.start);
  return cuts;
}

function splitSections(block: string): {
  stem: string;
  answer: string;
  analysis: string;
  detail: string;
} {
  const cuts = findSectionCuts(block);
  if (cuts.length === 0) {
    return { stem: block.trim(), answer: "", analysis: "", detail: "" };
  }

  const stem = block.slice(0, cuts[0].start).trim();
  const buckets: Record<Exclude<SectionKey, "stem">, string> = {
    answer: "",
    analysis: "",
    detail: "",
  };

  for (let i = 0; i < cuts.length; i++) {
    const cut = cuts[i];
    const contentStart = cut.start + cut.markerLen;
    const contentEnd = i + 1 < cuts.length ? cuts[i + 1].start : block.length;
    const content = block.slice(contentStart, contentEnd).trim();
    if (cut.key !== "stem") {
      buckets[cut.key] = buckets[cut.key]
        ? `${buckets[cut.key]}\n${content}`
        : content;
    }
  }

  return { stem, ...buckets };
}

function normalizeMarkdown(raw: string): string {
  return prepareMarkdownMath(
    raw
      .replace(/^\uFEFF/, "")
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .replace(/\u00a0/g, " "),
  ).trim();
}

/**
 * 按大题题号拆分。
 * 只用「1. / 1． / 1、 / 第1题 / ## 1.」，不用「（1）」——后者是小题，误用会丢掉答案/详解。
 */
function splitByQuestionNumber(
  text: string,
): Array<{ index: number; body: string }> {
  // 大题：1. / 1\. / 1． / 1、 / 第1题 / 第 1 题
  // 不用 （1）/(1)，避免把解答题小题当成新大题
  const re =
    /(?:^|\n)\s*(?:#{1,6}\s*)?(?:第\s*(\d+)\s*题|(\d+)\s*(?:\\[.．]|[.．、]))(?:\s+|(?=\S))/g;
  const hits: Array<{ index: number; start: number; bodyStart: number }> = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    hits.push({
      index: Number(m[1] || m[2]),
      start: m.index + (m[0].startsWith("\n") ? 1 : 0),
      bodyStart: m.index + m[0].length,
    });
  }
  if (hits.length === 0) return [];

  /** 取从 startExpect 起的连续题号链 */
  const takeChain = (startExpect: number) => {
    const chain: typeof hits = [];
    let expect = startExpect;
    for (const hit of hits) {
      if (hit.index === expect) {
        chain.push(hit);
        expect += 1;
      }
    }
    return chain;
  };

  // 优先 1,2,3…；否则取文档中最长的连续大题链（如 PDF 节选从 16. 起）
  let filtered = takeChain(1);
  if (filtered.length === 0) {
    let best: typeof hits = [];
    const seenStarts = new Set<number>();
    for (const hit of hits) {
      if (seenStarts.has(hit.index)) continue;
      seenStarts.add(hit.index);
      const chain = takeChain(hit.index);
      if (chain.length > best.length) best = chain;
    }
    filtered = best;
  }
  if (filtered.length === 0) return [];

  const out: Array<{ index: number; body: string }> = [];
  for (let i = 0; i < filtered.length; i++) {
    const end = i + 1 < filtered.length ? filtered[i + 1].start : text.length;
    let body = text.slice(filtered[i].bodyStart, end).trim();
    // 卷首残留（上一题尾巴）并入第 1 道识别到的题之前：仅当这是链首且前面还有内容
    if (i === 0 && filtered[i].start > 0) {
      const preamble = text.slice(0, filtered[i].start).trim();
      // 短卷首（页眉等）忽略；较长残片并入本题，避免信息丢失
      if (preamble.length >= 40 && !/^学科网|^机密|^注意事项/.test(preamble)) {
        body = `${preamble}\n\n${body}`.trim();
      }
    }
    if (body) out.push({ index: filtered[i].index, body });
  }
  return out;
}

/**
 * 从 Markdown 试卷文本中提取题目。
 */
export function parseMarkdownPaper(
  raw: string,
  assets?: ImageAssetMap,
): ParseMarkdownResult {
  const notices: ParseNotice[] = [];
  const unresolvedImages: string[] = [];
  const text = normalizeMarkdown(raw);

  if (!text) {
    notices.push({ level: "warn", text: "文件内容为空。" });
    return {
      questions: [],
      notices,
      warnings: notices.map((n) => n.text),
      unresolvedImages,
    };
  }

  const chunks = splitByQuestionNumber(text);
  if (chunks.length === 0) {
    notices.push({
      level: "warn",
      text: "未识别到大题题号。请确认题号在段首，格式如：1.  / 1． / 1、 / 第1题（小题（1）不会当作大题）。",
    });
    return {
      questions: [],
      notices,
      warnings: notices.map((n) => n.text),
      unresolvedImages,
    };
  }

  let formulaHint = 0;
  let imageHint = 0;

  const toHtml = (md: string) => markdownFragmentToHtml(md, assets, unresolvedImages);

  const questions: ImportedQuestion[] = chunks.map((chunk) => {
    const sections = splitSections(chunk.body);
    if (!sections.answer && !sections.analysis && !sections.detail) {
      notices.push({
        level: "tip",
        text: `第 ${chunk.index} 题未找到【答案】/【分析】/【详解】标记。`,
      });
    }

    const allMd = [
      sections.stem,
      sections.answer,
      sections.analysis,
      sections.detail,
    ].join("\n");
    if (/\$[^$]+\$|\$\$[\s\S]+?\$\$/.test(allMd)) formulaHint += 1;
    if (
      /!\[[^\]]*\]\([^)]+\)|!\[\[[^\]]+\]\]|<img\b/i.test(allMd)
    ) {
      imageHint += 1;
    }

    const stemHtml = toHtml(sections.stem);
    return {
      id: uid(`imp-q-${chunk.index}`),
      index: chunk.index,
      stemHtml,
      answerHtml: toHtml(sections.answer),
      analysisHtml: toHtml(sections.analysis),
      detailHtml: toHtml(sections.detail),
      stemText: stripTags(stemHtml).slice(0, 200),
    };
  });

  questions.sort((a, b) => a.index - b.index);

  notices.unshift({
    level: "ok",
    text: `成功从 Markdown 识别 ${questions.length} 道题。`,
  });
  if (formulaHint > 0) {
    notices.push({
      level: "ok",
      text: `其中 ${formulaHint} 题含 LaTeX 公式，已用 KaTeX 渲染。`,
    });
  }
  if (imageHint > 0) {
    const resolved =
      imageHint > 0 && assets && assets.size > 0
        ? `已匹配本地图片 ${assets.size} 个。`
        : "";
    notices.push({
      level: "ok",
      text: `其中 ${imageHint} 题含图片引用。${resolved}`,
    });
  }

  const uniqueMissing = [...new Set(unresolvedImages)];
  if (uniqueMissing.length > 0) {
    notices.push({
      level: "tip",
      text: `有 ${uniqueMissing.length} 张图片未加载成功（多为相对路径）。请在选择文件时同时选中 .md 与对应的 .jpg/.png 等图片文件。例如：${uniqueMissing.slice(0, 3).join("、")}`,
    });
  }

  return {
    questions,
    notices,
    warnings: notices.map((n) => n.text),
    unresolvedImages: uniqueMissing,
  };
}

/** 读取用户选中的 Markdown（可附带图片文件）并解析 */
export async function parseMarkdownFiles(
  files: File[] | FileList,
): Promise<ParseMarkdownResult> {
  const list = Array.from(files);
  const mdCandidates = list.filter(
    (f) => isMarkdownFileName(f.name) || /markdown/i.test(f.type),
  );
  mdCandidates.sort((a, b) => {
    const pa =
      (a as File & { webkitRelativePath?: string }).webkitRelativePath || a.name;
    const pb =
      (b as File & { webkitRelativePath?: string }).webkitRelativePath || b.name;
    const da = pa.split(/[/\\]/).length;
    const db = pb.split(/[/\\]/).length;
    return da - db || pa.localeCompare(pb);
  });
  const mdFile = mdCandidates[0];

  if (!mdFile) {
    return {
      questions: [],
      notices: [
        {
          level: "warn",
          text: "未找到 Markdown 文件。请选择含 .md 的试卷文件夹（需包含 image 子目录）。",
        },
      ],
      warnings: ["未找到 Markdown 文件"],
      unresolvedImages: [],
    };
  }

  const imageFiles = list.filter((f) => isImageFile(f));
  const assets = await buildImageAssetMap(imageFiles);
  const text = await mdFile.text();
  const result = parseMarkdownPaper(text, assets);

  if (imageFiles.length > 0) {
    result.notices.push({
      level: "ok",
      text: `已载入 ${imageFiles.length} 张本地图片，并支持匹配 image/文件名.jpg 相对路径。`,
    });
  } else if (result.unresolvedImages.length > 0) {
    result.notices.push({
      level: "warn",
      text: `有 ${result.unresolvedImages.length} 处图片未加载（如 image/...）。请用「选择试卷文件夹」选中含 image 子目录的整夹；若 Markdown 已内嵌 data URL 配图则可忽略。`,
    });
  } else {
    result.notices.push({
      level: "tip",
      text: "未载入任何图片文件。若配图在 image/ 目录，请用「选择整个试卷文件夹」导入。",
    });
  }

  result.warnings = result.notices.map((n) => n.text);
  return result;
}

/** @deprecated 请使用 parseMarkdownFiles，支持同时传入图片 */
export async function parseMarkdownFile(file: File): Promise<ParseMarkdownResult> {
  return parseMarkdownFiles([file]);
}
