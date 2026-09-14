/**
 * Word/MathType 集合公式清洗与 KaTeX 渲染。
 * Run: npx tsx tests/test_latex_normalize.mts
 */
import {
  normalizeTex,
  recoverDanglingDollarLatex,
  replaceLatexWithKatexHtml,
  splitAdjacentInlineDollars,
} from "../gaokao_docx/latex-to-html.ts";
import {
  markdownFragmentToHtml,
  parseMarkdownPaper,
} from "../gaokao_docx/markdown-paper-parser.ts";

const brokenSet =
  "已知集合$M＝\\left  \\begin{array}{l} \\left ( { x,y } \\right ){ \\rm{ \\| } }x+y\\le 1,x\\in  \\end{array} \\right.\\|x ^ { 2 } +y ^ { 2 } \\le 2$}";
const danglingSet = brokenSet.replace(/\$\}$/, "}");

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

function assertRendered(html: string, label: string) {
  assert(html.includes("katex"), `${label}: expected KaTeX HTML`);
  assert(!html.includes("katex-error"), `${label}: KaTeX parse error`);
  assert(!html.includes("tex-fallback"), `${label}: fell back to raw TeX`);
  assert(!/已知集合\$/.test(html), `${label}: leftover raw $…$`);
}

const recovered = recoverDanglingDollarLatex(danglingSet);
assert(
  recovered.startsWith("已知集合$") && recovered.trim().endsWith("$"),
  `dangling $ was not closed: ${JSON.stringify(recovered)}`,
);

const norm = normalizeTex(
  "M＝\\left  \\begin{array}{l} \\left ( { x,y } \\right ){ \\rm{ \\| } }x+y\\le 1,x\\in  \\end{array} \\right.\\|x ^ { 2 } +y ^ { 2 } \\le 2",
);
assert(/\\left\\\{/.test(norm), `expected set braces, got ${norm}`);
assert(/\\mid/.test(norm), `expected \\mid, got ${norm}`);
assert(/\\right\\\}/.test(norm), `expected \\right\\}, got ${norm}`);

assertRendered(replaceLatexWithKatexHtml(brokenSet), "replace closed");
assertRendered(replaceLatexWithKatexHtml(danglingSet), "replace dangling");
assertRendered(markdownFragmentToHtml(brokenSet), "fragment closed");
assertRendered(markdownFragmentToHtml(danglingSet), "fragment dangling");

const glued = splitAdjacentInlineDollars(
  "所选是$\\therefore $$0 < a < 1$是真子集，\n\n故选：BD\n\n12. 下一题$\\because$$A\\cap B=A$",
);
assert(!glued.includes("$$"), `adjacent $ not split: ${JSON.stringify(glued)}`);
assert(glued.includes("12. "), `question 12 eaten: ${JSON.stringify(glued)}`);

const paper = parseMarkdownPaper(`
11. 多选题（ ）
A. $1$
B. $2$
【答案】BD
【详解】$\\therefore $$0 < a < 1$是正确选项的一个真子集，

故选：BD

12. 填空题
【答案】AC

13. 解答题
【答案】（1）$[0,1]$；（2）$7+4\\sqrt{3}$

【详解】见解析。

1.参变分离法，将不等式恒成立问题转化为函数求最值问题；
`);
const idxs = paper.questions.map((q) => q.index);
assert(
  idxs.includes(11) && idxs.includes(12) && idxs.includes(13),
  `expected Q11-13, got ${idxs.join(",")}`,
);
const q11 = paper.questions.find((q) => q.index === 11);
assert(q11, "missing Q11");
const q11ans = q11.answerHtml.replace(/<[^>]+>/g, "").trim();
assert(
  q11ans === "BD",
  `Q11 answer should be BD, got ${JSON.stringify(q11.answerHtml)}`,
);
assert(
  !/0,1/.test(q11.answerHtml) && !/7\+4/.test(q11.answerHtml),
  `Q11 answer swallowed later questions: ${q11.answerHtml}`,
);

console.log("ok");
