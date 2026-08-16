import katex from "katex";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** 还原 Markdown / HTML 导出残留的实体，避免 KaTeX 把 &gt; 里的 & 当成对齐符。 */
export function decodeHtmlEntities(input: string): string {
  if (!input || !input.includes("&")) return input;
  return input
    .replace(/&amp;/gi, "&")
    .replace(/&nbsp;/gi, " ")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_m, hex: string) =>
      String.fromCodePoint(parseInt(hex, 16)),
    )
    .replace(/&#(\d+);/g, (_m, n: string) => String.fromCodePoint(Number(n)));
}

/**
 * 还原 Markdown / Turndown 对选项与公式的转义：
 * A\. B\. → A. B. ； \$ → $ ；过度转义的 \\( \\) 等。
 */
export function unescapeMarkdownLatexArtifacts(input: string): string {
  if (!input) return input;
  let s = decodeHtmlEntities(input.replace(/＄/g, "$"));

  // 去掉误入公式/正文的 HTML 残片（如 </span>）
  s = s.replace(/<\/?(?:span|div|p|font|em|strong|i|b|u)[^>]*>/gi, "");

  // 选项与题号：A\. B\. C\. D\. / 1\.
  s = s.replace(/([A-Da-d])\\([.．、])/g, "$1$2");
  s = s.replace(/(\d+)\\([.．])/g, "$1$2");

  // 美元符被转义
  s = s.replace(/\\\$/g, "$");

  // 公式定界符被双重转义：\\( \\) \\[ \\]
  s = s.replace(/\\\\([()[\]])/g, "\\$1");

  // 填空题：\_\_\_\_ → ______
  s = s.replace(/(?:\\_){2,}/g, (m) => "_".repeat(m.length / 2));
  s = s.replace(/\\_/g, "_");

  return s;
}

/**
 * 修复常见非法/半残 LaTeX（Word 转换残留）：
 * \left{ → \left\{ ；\right → \right\} ；去掉 HTML 标签等。
 */
export function fixBrokenLatex(tex: string): string {
  let s = tex.trim();
  s = s.replace(/<\/?[^>]+>/g, "");
  s = s.replace(/\u00a0/g, " ");

  // \left{ → \left\{ ；\right} → \right\}
  s = s.replace(/\\left\s*\{/g, "\\left\\{");
  s = s.replace(/\\right\s*\}/g, "\\right\\}");

  // Word 残留：\left\{\frac{5}{3},3} \right  （\right 后没有定界符才收多余 }）
  // 分段函数 \left\{ \begin{array}...\end{array} \right. 不能按第一个 } 截断
  s = s.replace(
    /\\left\\\{([\s\S]*?)\}(\s*)\\right(?!\s*[\\()\[\]|.])/g,
    (full, inner: string, ws: string) => {
      if (/\\begin/.test(inner)) return full;
      return `\\left\\{${inner}${ws}\\right`;
    },
  );

  // \right 后缺少定界符
  s = s.replace(/\\right(?!\s*[\\()\[\]|.])/g, "\\right\\}");
  s = s.replace(/\\right\s*$/g, "\\right\\}");

  // \left 后直接跟非定界字符时补 \{
  s = s.replace(/\\left(?!\s*[\\()\[\]|.])/g, "\\left\\{");

  // 集合写法 {a,b} 在 \left \right 外可保持；若出现 \frac 等已是命令则不动

  // Word/MathType：\frac { 1 } { a } → \frac{1}{a}
  s = s.replace(
    /\\(d?frac)\s*\{\s*([^{}]+?)\s*\}\s*\{\s*([^{}]+?)\s*\}/g,
    "\\$1{$2}{$3}",
  );
  s = s.replace(/\{\s+([^{}\s][^{}]*?)\s+\}/g, "{$1}");

  // 多余空白（保留换行，分段 array 靠 \\ 换行）
  s = s.replace(/[ \t]{2,}/g, " ").trim();

  // 双反斜杠命令（不含 array/cases 行分隔 \\）
  if (!/\\begin\{(?:array|cases)/.test(s) && /\\\\[a-zA-Z]+/.test(s)) {
    s = s.replace(/\\\\([a-zA-Z]+)/g, "\\$1");
  }

  return s;
}

/** 规范化从 Markdown 读出的 TeX */
export function normalizeTex(raw: string): string {
  let s = decodeHtmlEntities(raw);
  s = normalizeWordMathArtifacts(s);
  s = fixBrokenLatex(s);
  s = s
    .replace(/＄/g, "$")
    .replace(/（/g, "(")
    .replace(/）/g, ")");
  // Word/TexVC 常见：\rm{\pi } → \mathrm{\pi }
  s = s.replace(/\\rm(?![a-zA-Z])/g, "\\mathrm");
  // {{x}} 多余花括号（未在全文清洗到的残留）
  s = s.replace(/\{\{([^{}]+)\}\}/g, "{$1}");
  // tan\theta → \tan\theta（无反斜杠的常用函数）
  s = s.replace(
    /(?<!\\)\b(sin|cos|tan|cot|sec|csc|log|ln|lim|max|min|exp)\b/g,
    "\\$1",
  );
  // 分段函数 array 再归一一次（fix 后可能仍带 *）
  s = normalizeWordMathArtifacts(s);
  s = repairSetBuilderNotation(s);
  s = foldPiecewiseArrayToCases(s);
  return s;
}

export function renderTexToHtml(tex: string, displayMode: boolean): string {
  const normalized = normalizeTex(tex);
  if (!normalized) return "";
  try {
    return katex.renderToString(normalized, {
      throwOnError: false,
      displayMode,
      strict: "ignore",
      trust: false,
      output: "html",
    });
  } catch {
    return `<code class="tex-fallback">${escapeHtml(normalized)}</code>`;
  }
}

/** Word/MathType 列格式 {*{20}{c}} → {c}；拆开的 lo+g → log */
export function normalizeWordMathArtifacts(input: string): string {
  let s = input;
  s = s.replace(/\{\*\{\d+\}\{([clmr])\}\}/gi, "{$1}");
  s = s.replace(/\{\*\{\d+\}\{([clmr])\}/gi, "{$1");
  // MTEF 空列格式；去掉套空的 array
  s = s.replace(/\\begin\{array\}\s*\{\s*\}/g, "\\begin{array}{l}");
  for (let i = 0; i < 6; i++) {
    s = s.replace(/\\begin\{array\}\{[lcr]*\}\s*\\end\{array\}/g, "");
  }
  // MTEF 旧结果：只有空 array、没有分段内容
  s = s.replace(
    /\\left\s*\\?\{(?:\s*\\begin\{array\}\{[lcr]*\})+\s*\\right\s*\./g,
    "",
  );
  s = s.replace(/\\left\s*\\?\{\s*\\right\s*\./g, "");
  // { \rm{ l } }{ \rm{ o } }{ \rm{ g } }_{ 2 } → \log_{2}
  s = s.replace(
    /\{\s*\\rm\{\s*l\s*\}\s*\}\s*\{\s*\\rm\{\s*o\s*\}\s*\}\s*\{\s*\\rm\{\s*g\s*\}\s*\}\s*_(\s*\{?\s*[0-9n]+\s*\}?)/gi,
    (_m, sub: string) => `\\log_{${sub.replace(/\s+/g, "")}}`,
  );
  s = s.replace(
    /\{\s*\\rm\{\s*l\s*\}\s*\}\s*\{\s*\\rm\{\s*o\s*\}\s*\}\s*\{\s*\\rm\{\s*g\s*\}\s*\}/gi,
    "\\log",
  );
  s = s.replace(
    /\{\s*\\rm\{\s*lo\s*\}\s*\}\s*\{\s*\\rm\{\s*g\s*\}\s*\}/gi,
    "\\log",
  );
  // {{\rm{lo}}{{\rm{g}}_2} → \log_{2}
  s = s.replace(
    /\{\{\\rm\{lo\}\}\{\{\\rm\{g\}\}_(\{?[0-9n]+\}?)\}\}/g,
    "\\log_{$1}",
  );
  s = s.replace(
    /\{\\rm\{lo\}\}\s*\{\{\\rm\{g\}\}_(\{?[0-9n]+\}?)\}/g,
    "\\log_{$1}",
  );
  s = s.replace(/\{\s*\\rm\{\s*\\pi\s*\}\s*\}/gi, "\\pi");
  s = s.replace(/\\sqrt\s*\[\s*\]\s*\{/g, "\\sqrt{");
  // 去掉只包一层的多余 array
  s = s.replace(
    /\\begin\{array\}\{[lcr]+\}(\s*)\\begin\{array\}\{[lcr]+\}([\s\S]*?)\\end\{array\}(\s*)\\end\{array\}/g,
    "\\begin{array}{l}$2\\end{array}",
  );
  return s;
}

/** 修好 \begin{cases} 与 \end{array} 错配，条件挪到 cases 外面。 */
function repairCasesArray(input: string): string {
  let s = input;
  s = s.replace(
    /\\begin\{cases\}([\s\S]*?)\\end\{array\}([\s\S]*?)\\end\{cases\}/g,
    (_m, body: string, trail: string) => {
      const cond = trail.trim();
      return cond
        ? `\\begin{cases}${body}\\end{cases} ${cond}`
        : `\\begin{cases}${body}\\end{cases}`;
    },
  );
  s = s.replace(
    /\\begin\{cases\}\s*\\begin\{array\}\{[lcr]*\}([\s\S]*?)\\end\{array\}\s*\\end\{cases\}/g,
    "\\begin{cases}$1\\end{cases}",
  );
  s = s.replace(
    /\\begin\{cases\}\s*\\begin\{array\}\{[lcr]*\}([\s\S]*?)\\end\{cases\}/g,
    "\\begin{cases}$1\\end{cases}",
  );
  // \end{cases} ... \end{array}：折 cases 后多出来的 array 收尾
  s = s.replace(
    /(\\end\{cases\}(?:(?!\\begin\{array\}).)*?)\\end\{array\}/g,
    "$1",
  );
  s = stripUnmatchedArrayDelimiters(s);
  return s;
}

function stripUnmatchedArrayDelimiters(input: string): string {
  const begins = (input.match(/\\begin\{array\}/g) || []).length;
  const ends = (input.match(/\\end\{array\}/g) || []).length;
  if (ends <= begins) return input;
  let extra = ends - begins;
  return input.replace(/\\end\{array\}/g, (m) => {
    if (extra > 0) {
      extra -= 1;
      return "";
    }
    return m;
  });
}

/** 从 `{` 起取出配对的花括号内容，避免 \sqrt{x+3} 的 } 截断集合条件。 */
function takeBalancedBrace(src: string, openIdx: number): [string, number] | null {
  if (src[openIdx] !== "{") return null;
  let depth = 0;
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") {
      depth -= 1;
      if (depth === 0) return [src.slice(openIdx + 1, i), i + 1];
    }
  }
  return null;
}

/** 集合 { x | y=… } 被误折成 cases 后，还原为 \left\{ x \mid … \right\} */
function normalizeSetBuilderBody(body: string): string {
  let b = body;
  const re = /\\left\s*\|\s*\{/g;
  let out = "";
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(b))) {
    out += b.slice(last, m.index);
    const braceAt = m.index + m[0].length - 1;
    const taken = takeBalancedBrace(b, braceAt);
    if (!taken) {
      out += m[0];
      last = m.index + m[0].length;
      continue;
    }
    const [inner, next] = taken;
    const right = b.slice(next).match(/^\s*\\right\s*\./);
    out += `\\mid ${inner.trim()} `;
    last = next + (right ? right[0].length : 0);
    re.lastIndex = last;
  }
  out += b.slice(last);
  b = out.replace(/\\left\s*\|/g, "\\mid ");
  b = b.replace(/\\right\s*\./g, "");
  return b.trim();
}

function looksLikeSetBuilder(body: string): boolean {
  return /\\left\s*\|/.test(body) || /\\mid/.test(body);
}

function repairSetBuilderNotation(input: string): string {
  let s = input;
  // 已折坏：\begin{cases} x\left | { y=… } \end{cases} \right \}
  s = s.replace(
    /\\begin\{cases\}([\s\S]*?)\\end\{cases\}\s*\\right\s*\\?\}/g,
    (_m, body: string) =>
      `\\left\\{${normalizeSetBuilderBody(body)}\\right\\}`,
  );
  // 单行花括号 + 竖线：\left\{ \begin{array}{l} x \left| … \right. \end{array} \right\}
  s = s.replace(
    /\\left\s*\\?\{\s*\\begin\{array\}\{[lcr]*\}([\s\S]*?)\\end\{array\}\s*\\right\s*\\?\}/g,
    (full, body: string) => {
      if (!looksLikeSetBuilder(body) && /\\\\/.test(body)) return full;
      return `\\left\\{${normalizeSetBuilderBody(body)}\\right\\}`;
    },
  );
  return s;
}

/** \left\{ \begin{array}{l} ... \end{array} \right. → \begin{cases}...\end{cases} */
function foldPiecewiseArrayToCases(input: string): string {
  let s = input;
  for (let i = 0; i < 4; i++) {
    s = s.replace(
      /\\begin\{array\}\{[lcr]+\}(\s*)\\begin\{array\}\{[lcr]+\}([\s\S]*?)\\end\{array\}(\s*)\\end\{array\}/g,
      "\\begin{array}{l}$2\\end{array}",
    );
  }
  s = s.replace(
    /\\left\s*\\?\{\s*\\begin\{array\}\{[lcr]*\}([\s\S]*?)\\end\{array\}([\s\S]*?)\\right\s*\./g,
    (full, body: string, after: string) => {
      if (looksLikeSetBuilder(body)) return full;
      const cond = after.trim();
      return cond
        ? `\\begin{cases}${body}\\end{cases} ${cond}`
        : `\\begin{cases}${body}\\end{cases}`;
    },
  );
  // 缺 \end{array} 的分段；不能把集合内侧 \right. 当成外层收尾
  s = s.replace(
    /\\left\s*\\?\{\s*\\begin\{array\}\{[lcr]*\}([\s\S]*?)\\right\s*\.(?!\s*\\end\{array\})/g,
    (full, body: string) => {
      if (looksLikeSetBuilder(body) || !/\\\\/.test(body)) return full;
      return `\\begin{cases}${body}\\end{cases}`;
    },
  );
  return repairCasesArray(s);
}

function looksLikeLatexBody(tex: string): boolean {
  if (
    /\\(?:begin|end|left|right|frac|dfrac|sqrt|mathrm|mathbf|rm|array|cases|log)/.test(
      tex,
    )
  ) {
    return true;
  }
  if (/\\\\/.test(tex) && /[{}^_]/.test(tex)) return true;
  return (tex.match(/\\[a-zA-Z]+/g) || []).length >= 2;
}

function isBadCrossLineDollarMatch(tex: string): boolean {
  if (/(?:^|\n)\s*[A-Da-d][.．、]/.test(tex)) return true;
  const cjk = (tex.match(/[\u4e00-\u9fff]/g) || []).length;
  return cjk > 8 && !looksLikeLatexBody(tex);
}

/**
 * 替换 $...$。同一行照常配对；含换行时仅当内部像 LaTeX（如 \begin{array}）才配对，
 * 避免「$\\nA. $公式$」把选项字母吃进公式。
 */
export function replaceInlineDollarMath(
  input: string,
  replacer: (tex: string) => string,
): string {
  let out = "";
  let i = 0;
  while (i < input.length) {
    if (input[i] !== "$") {
      out += input[i];
      i += 1;
      continue;
    }

    // 完整 $$...$$ 交给外层；未闭合的 $$\frac...$ 不能把前两个 $ 当空公式跳过
    if (input[i + 1] === "$") {
      const close = input.indexOf("$$", i + 2);
      if (close !== -1) {
        out += "$$";
        i += 2;
        continue;
      }
    }

    let searchFrom = i + 1;
    if (
      input[i + 1] === "$" &&
      looksLikeLatexBody(input.slice(i + 2, Math.min(input.length, i + 80)))
    ) {
      searchFrom = i + 2;
    }

    let found = -1;
    for (let j = searchFrom; j < input.length && j - i < 8000; j++) {
      if (input[j] !== "$") continue;
      if (input[j + 1] === "$") {
        j++;
        continue;
      }
      const inner = input.slice(searchFrom, j);
      if (!inner.trim()) {
        if (input[j + 1] === "$") j++;
        continue;
      }
      // $a$$b$：第一个公式在 $$ 处结束，不能把 $$ 当 display 跳过
      if (!inner.includes("\n")) {
        found = j;
        break;
      }
      if (looksLikeLatexBody(inner) && !isBadCrossLineDollarMatch(inner)) {
        found = j;
        break;
      }
    }
    if (found > i) {
      out += replacer(input.slice(searchFrom, found));
      i = found + 1;
      continue;
    }

    out += input[i];
    i += 1;
  }
  return out;
}

const RECOVER_SLOT = /%%RK(\d+)%%/g;

/**
 * x\in $$\left(...  （display 开了却没收尾）合成 $x\in \left...$
 * 也处理 $x\in$$\left...$
 */
export function repairInFollowedByDisplayDollars(input: string): string {
  if (!input || !input.includes("$$")) return input;
  let s = input;
  s = s.replace(
    /\$([^$\n]*\\in)\s*\$\$\s*(\\left[\s\S]*?)(?:\$\$|\$)(?!\$)/g,
    (_m, head: string, rest: string) =>
      `$${head.trim()} ${rest.replace(/\$$/, "").trim()}$`,
  );
  s = s.replace(
    /(^|[^$])([A-Za-z]\s*\\in)\s*\$\$\s*(\\left[\s\S]*?)(?:\$\$|\$)?(?=$|[\n\r。；;]|【)/gm,
    (_m, pre: string, inn: string, rest: string) =>
      `${pre}$${inn} ${rest.replace(/\$$/, "").trim()}$`,
  );
  // 仍残留的未闭合 $$\left / $$\frac
  s = s.replace(
    /\$\$(\s*\\(?:left|frac|dfrac|begin)[\s\S]*)$/gm,
    (_m, body: string) => `$${body.trim()}$`,
  );
  return s;
}

/** $a$$b$ → $a$ $b$，避免相邻行内公式粘成 $$ 被当成 display。 */
export function splitAdjacentInlineDollars(input: string): string {
  if (!input || !input.includes("$$")) return input;
  return input.replace(
    /\$([^$\n]+?)\$\$([^$\n]+?)\$/g,
    (full, a: string, b: string) => {
      if (looksLikeLatexBody(a) && looksLikeLatexBody(b)) return `$${a}$ $${b}$`;
      return full;
    },
  );
}

function stripRecoverArtifacts(input: string): string {
  return input
    .replace(/\u0000R\d+\u0000/g, "")
    .replace(/%%RK\d+%%/g, "")
    .replace(/\)R\d+(?=\\left)/g, ")");
}

/** 补全 $$\frac...$ 或丢失开头 $ 的 \frac...$；已配对的 $...$ 不拆开。 */
export function recoverDanglingDollarLatex(input: string): string {
  if (!input) return input;
  let s = stripRecoverArtifacts(repairInFollowedByDisplayDollars(input));
  if (!s.includes("$")) {
    if (looksLikeBareLatex(s) && /\\(?:frac|left|begin)/.test(s)) return `$${s}$`;
    return s;
  }

  const slots: string[] = [];
  const park = (text: string) => {
    const i = slots.length;
    slots.push(text);
    return `%%RK${i}%%`;
  };

  // 先保护完整 $$...$$ / $...$，避免把 $\frac{1}{a}+\frac{9}{b}$ 从第二个 \frac 切开
  s = splitAdjacentInlineDollars(s);
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (m) => park(m));
  s = replaceInlineDollarMath(s, (tex) => park(`$${tex}$`));

  s = s.replace(
    /\$\$((?:\\(?:frac|dfrac|sqrt|left|right|sum|int|mathrm|mathbf|log|sin|cos|tan|begin)|[^$])+)\$/g,
    (_m, tex: string) => `$${tex}$`,
  );
  s = s.replace(
    /(^|[^$\\])((?:\\(?:frac|dfrac|sqrt|left|sum|int|mathrm|mathbf|log|sin|cos|tan)[^$\n]*))\$/g,
    (full, pre: string, tex: string) => {
      if (looksLikeLatexBody(tex)) return `${pre}$${tex}$`;
      return full;
    },
  );

  s = s.replace(RECOVER_SLOT, (_m, idx: string) => slots[Number(idx)] ?? "");
  // 旧版 \0R0\0 泄漏，以及 )R0\left 这类残片
  s = s.replace(/\u0000R(\d+)\u0000/g, "");
  s = s.replace(/%%RK\d+%%/g, "");
  s = s.replace(/\)R\d+(?=\\left)/g, ")");
  return splitAdjacentInlineDollars(s);
}

function looksLikeBareLatex(text: string): boolean {
  return /\\(?:left|right|frac|dfrac|sqrt|sum|int|cdot|times|div|leq|geq|neq|in|subset|cup|cap|overline|begin|end|mathrm|mathbf|text|[a-zA-Z]+)|[\^_]\{/.test(
    text,
  );
}

/** 只清洗已有定界符内部，绝不在外层再包一层 $ */
function cleanExistingMathDelimiters(body: string): string {
  return body
    .replace(/\$([^$\n]+)\$/g, (_m, tex: string) => `$${fixBrokenLatex(tex)}$`)
    .replace(/\\\[([^\n[\]]{1,400})\\\]/g, (_m, tex: string) => `$${fixBrokenLatex(tex)}$`)
    .replace(/\\\(([^\n]{1,400})\\\)/g, (_m, tex: string) => `$${fixBrokenLatex(tex)}$`);
}

/**
 * 将选项 A./B./C./D. 后未加 $ 的裸 LaTeX 自动包上 $...$，并先做残片修复。
 * 仅处理同一行内的选项，避免最后一个选项贪婪吞掉后文（【答案】/下一题）。
 * 「向右平移$\frac{\pi}{4}$」这类中文+已有公式不得再包 $，否则会变成
 * `$向右平移$\frac{\pi}{4}$$`，美元符错配后 KaTeX 报 Can't use function '$'。
 */
export function wrapBareLatexAfterOptions(input: string): string {
  if (!input) return input;

  return input.replace(
    /(^|[\n\t ])([A-Da-d][.．、]\s*)([^\n]*?)(?=(?:[ \t]+[A-Da-d][.．、])|\n|$)/g,
    (full, pre: string, opt: string, rest: string) => {
      const body = rest.trim();
      if (!body) return full;
      const trailingWs = rest.match(/\s*$/)?.[0] ?? "";

      // 选项内任意位置已有 $ / \[ / \(：只清洗内部，禁止整段再包 $
      if (/\$|\\\(|\\\[/.test(body)) {
        return `${pre}${opt}${cleanExistingMathDelimiters(body)}${trailingWs}`;
      }

      // 纯数字/极短选项不是公式（如 D. 20）
      if (/^[A-Da-d\d\s.．、]+$/.test(body)) return full;
      if (!looksLikeBareLatex(body)) return full;
      // 含题干中文标记则不是选项公式
      if (/【|答案|解析|详解|分析/.test(body)) return full;

      // 中文说明 + 裸公式：只包裹公式部分
      const latexAt = body.search(
        /\\(?:left|right|frac|dfrac|sqrt|sum|int|cdot|times|mathrm|mathbf|rm|pi|lg|log|sin|cos|tan)/,
      );
      if (latexAt > 0) {
        const prefix = body.slice(0, latexAt);
        const latex = fixBrokenLatex(body.slice(latexAt));
        return `${pre}${opt}${prefix}$${latex}$${trailingWs}`;
      }

      const cleaned = fixBrokenLatex(body);
      return `${pre}${opt}$${cleaned}$${trailingWs}`;
    },
  );
}


/**
 * 把文本中的 LaTeX 分隔符替换为 KaTeX HTML。
 * 分段公式等可跨行的 $...$ 仅在内部像 LaTeX 时才配对。
 */
export function replaceLatexWithKatexHtml(input: string): string {
  if (!input) return input;

  let s = unescapeMarkdownLatexArtifacts(input);
  s = normalizeWordMathArtifacts(s);
  s = recoverDanglingDollarLatex(s);
  s = splitAdjacentInlineDollars(s);
  s = wrapBareLatexAfterOptions(s);

  // 先处理 display：$$...$$ 与 \[...\]（可多行）
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_m, tex: string) =>
    renderTexToHtml(tex, true),
  );
  s = s.replace(/\\\[([\s\S]+?)\\\]/g, (_m, tex: string) =>
    renderTexToHtml(tex, true),
  );

  s = s.replace(/\\\(([\s\S]+?)\\\)/g, (_m, tex: string) =>
    renderTexToHtml(tex, false),
  );
  s = replaceInlineDollarMath(s, (tex) => renderTexToHtml(tex, false));

  // 去掉配对失败留下的孤立 $（不删 )$ ，避免把公式收尾 $ 吃掉）
  s = s.replace(/(^|[\s（）])\$(?=[\s）]|$)/gm, "$1");

  return s;
}

/**
 * 导入前整段清洗：转义还原 + Word array 列格式 + 选项后裸公式包裹 + TexVC 归一。
 */
export function prepareMarkdownMath(input: string): string {
  let s = unescapeMarkdownLatexArtifacts(input);
  s = normalizeWordMathArtifacts(s);
  s = recoverDanglingDollarLatex(s);
  s = splitAdjacentInlineDollars(s);
  // TexVC / MediaWiki：{{x}^{2}} → {x}^{2}
  s = s.replace(/\{\{([^{}]+)\}\}/g, "{$1}");
  // 相邻 \]\[ 先拆开，避免转成 $...$$...$ 粘成 display
  s = s.replace(/\\\]\s*\\\[/g, "\\] \\[");
  // 行内误用 \[...\]（无换行、较短）改为 $...$
  s = s.replace(/\\\[([^\n[\]]{1,120})\\\]/g, (_m, tex: string) => `$${tex}$`);
  s = wrapBareLatexAfterOptions(s);
  return s;
}
