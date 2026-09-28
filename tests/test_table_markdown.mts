/**
 * Word tables must stay as GFM tables, not flattened cell text.
 * Run: npx tsx tests/test_table_markdown.mts
 */
import { htmlToMarkdown } from "../gaokao_docx/docx-to-markdown.ts";
import { markdownFragmentToHtml } from "../gaokao_docx/markdown-paper-parser.ts";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

const mammothLike = `
<p>下表给出了部分对应值</p>
<table>
  <tbody>
    <tr>
      <td><p>$x$</p></td>
      <td><p>10</p></td>
      <td><p>15</p></td>
      <td><p>20</p></td>
      <td><p>25</p></td>
      <td><p>30</p></td>
      <td><p></p></td>
    </tr>
    <tr>
      <td><p>$Q(x)$</p></td>
      <td><p>50</p></td>
      <td><p>55</p></td>
      <td><p>60</p></td>
      <td><p>55</p></td>
      <td><p>50</p></td>
      <td><p></p></td>
    </tr>
  </tbody>
</table>
`;

const md = htmlToMarkdown(mammothLike);
assert(md.includes("|"), `expected GFM table, got:\n${md}`);
assert(
  /\|[^|\n]*x[^|\n]*\|/.test(md) && md.includes("| 10 |") && md.includes("| 30 |"),
  `header row missing values:\n${md}`,
);
assert(
  md.includes("Q(x)") && md.includes("| 50 |") && md.includes("| 60 |"),
  `data row missing values:\n${md}`,
);
assert(
  !/^x\s*$/m.test(md.split("下表")[1] || md),
  `table flattened to a lone x line:\n${md}`,
);

const html = markdownFragmentToHtml(md);
assert(/<table\b/i.test(html), `expected HTML table, got:\n${html}`);
assert(
  html.includes("10") && html.includes("60") && html.includes("katex"),
  `table cells lost:\n${html}`,
);
assert(/<th[^>]*>10<\/th>/.test(html) && /<td[^>]*>60<\/td>/.test(html), `grid broken:\n${html}`);
const beforeTable = html.split(/<table/i)[0];
assert(!/>60</.test(beforeTable), `table values leaked outside table:\n${html}`);

const spanned = htmlToMarkdown(`
<table>
  <tr>
    <td colspan="2">合计</td>
    <td>100</td>
  </tr>
  <tr>
    <td>甲</td>
    <td>乙</td>
    <td>100</td>
  </tr>
</table>
`);
assert(
  /<table[\s\S]*colspan="2"[\s\S]*合计[\s\S]*<\/table>/i.test(spanned),
  `spanned table should stay HTML:\n${spanned}`,
);

console.log("ok");
