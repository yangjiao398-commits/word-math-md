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

const headed = parseMarkdownPaper(`
深圳实验学校高中部2023-2024学年度第一学期第二阶段考试

高一数学

时间：120分钟 满分：150分

考生注意：答题前请认真阅读。

一、选择题（本大题共1小题，每小题5分，共5分）

1. 已知 $a>0$（ ）
A. $1$
B. $2$
【答案】A
`);
assert(
  headed.headerText.includes("深圳实验学校高中部") &&
    headed.headerText.includes("高一数学") &&
    headed.headerText.includes("时间：120分钟"),
  `expected exam masthead, got ${JSON.stringify(headed.headerText)}`,
);
assert(headed.headerHtml.includes("深圳实验学校高中部"), "headerHtml missing school name");
const q1stem = headed.questions[0]?.stemHtml || "";
assert(
  !q1stem.includes("深圳实验学校") && !q1stem.includes("120分钟"),
  `masthead leaked into Q1: ${q1stem}`,
);
assert(q1stem.includes("已知"), `Q1 stem lost: ${q1stem}`);
assert(
  !headed.headerText.includes("一、选择题"),
  `type header should not stay in masthead: ${headed.headerText}`,
);
assert(headed.sections.length === 1, `expected 1 section, got ${headed.sections.length}`);
assert(
  headed.sections[0].title.includes("一、选择题") &&
    headed.sections[0].questionIndexes.includes(1),
  `section mismatch: ${JSON.stringify(headed.sections)}`,
);

const typed = parseMarkdownPaper(`
深圳实验学校高中部2023-2024学年度第一学期第二阶段考试

高一数学

时间：120分钟 满分：150分

一、单项选择题：本题共2小题，每小题5分，共10分.在每小题给出的四个选项中，只有一项是符合题目要求的.

1. 单选题一（ ）
A. $1$
B. $2$
【答案】A
【详解】选 A。

2. 单选题二（ ）
A. $3$
B. $4$
【答案】B
【详解】选 B。

二、多项选择题：本题共2小题，每小题5分，共10分.在每小题给出的选项中，有多项符合题目要求.全部选对的得5分，有选错的得0分，部分选对的得2分.

3. 多选题一（ ）
A. 甲
B. 乙
【答案】AB
【详解】甲乙都对。

4. 多选题二（ ）
A. 丙
B. 丁
【答案】A
【详解】只选丙。

三、填空题：本题共1小题，每小题5分，共5分.

5. 空格填 ______ 。
【答案】$3$

四、解答题:本题共1小题，共10分.解答应写出文字说明、证明过程或演算步骤.

6. 证明：三角形内角和为 $180^\\circ$。
【详解】延长并作平行线。
`);
assert(typed.sections.length === 4, `expected 4 type sections, got ${typed.sections.length}`);
assert(
  typed.sections[0].title.includes("单项选择题") &&
    typed.sections[1].title.includes("多项选择题") &&
    typed.sections[2].title.includes("填空题") &&
    typed.sections[3].title.includes("解答题"),
  `bad section titles: ${typed.sections.map((s) => s.title).join(" || ")}`,
);
function same(a: number[], b: number[]) {
  assert(a.join(",") === b.join(","), `indexes ${a.join(",")} != ${b.join(",")}`);
}
same(typed.sections[0].questionIndexes, [1, 2]);
same(typed.sections[1].questionIndexes, [3, 4]);
same(typed.sections[2].questionIndexes, [5]);
same(typed.sections[3].questionIndexes, [6]);
const q2 = typed.questions.find((q) => q.index === 2)?.stemHtml || "";
const q2detail = typed.questions.find((q) => q.index === 2)?.detailHtml || "";
assert(
  !q2.includes("多项选择题") && !q2detail.includes("多项选择题"),
  `next type header leaked into Q2: ${q2} ${q2detail}`,
);
assert(!(typed.headerText || "").includes("单项选择题"), "type header leaked into masthead");

console.log("ok");
