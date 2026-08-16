/**
 * 将 Word OMML 粗转为 LaTeX（用于 docx→markdown）。
 * 覆盖分数、根号、上下标等常见结构。
 */
const MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math";
const W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";

function localName(el: Element): string {
  return (el.localName || el.nodeName || "").replace(/^.*:/, "");
}

function childrenOf(el: Element): Element[] {
  return Array.from(el.children) as Element[];
}

function firstChild(el: Element, name: string): Element | undefined {
  return childrenOf(el).find((c) => localName(c) === name);
}

function allChildren(el: Element, name: string): Element[] {
  return childrenOf(el).filter((c) => localName(c) === name);
}

function textOf(el: Element): string {
  return (el.textContent || "").replace(/\u200b/g, "");
}

function mapChar(ch: string): string {
  const map: Record<string, string> = {
    "∑": "\\sum ",
    "∏": "\\prod ",
    "∫": "\\int ",
    "∞": "\\infty ",
    "≤": "\\le ",
    "≥": "\\ge ",
    "≠": "\\ne ",
    "±": "\\pm ",
    "×": "\\times ",
    "÷": "\\div ",
    "·": "\\cdot ",
    "∈": "\\in ",
    "⊂": "\\subset ",
    "∪": "\\cup ",
    "∩": "\\cap ",
    "π": "\\pi ",
    "α": "\\alpha ",
    "β": "\\beta ",
    "θ": "\\theta ",
    "Δ": "\\Delta ",
    "→": "\\to ",
    "⇒": "\\Rightarrow ",
  };
  if (map[ch]) return map[ch];
  if ("#$%&_{}".includes(ch)) return `\\${ch}`;
  return ch;
}

function escapeTextRun(raw: string): string {
  return Array.from(raw).map(mapChar).join("");
}

function convertNode(el: Element): string {
  const name = localName(el);
  switch (name) {
    case "oMath":
    case "oMathPara":
    case "e":
    case "deg":
    case "num":
    case "den":
    case "sub":
    case "sup":
    case "fName":
    case "lim":
      return childrenOf(el).map(convertNode).join("");
    case "r": {
      const t = firstChild(el, "t");
      if (t) return escapeTextRun(textOf(t));
      return childrenOf(el).map(convertNode).join("");
    }
    case "t":
      return escapeTextRun(textOf(el));
    case "f": {
      const num = firstChild(el, "num");
      const den = firstChild(el, "den");
      return `\\dfrac{${num ? convertNode(num) : ""}}{${den ? convertNode(den) : ""}}`;
    }
    case "rad": {
      const deg = firstChild(el, "deg");
      const e = firstChild(el, "e");
      const body = e ? convertNode(e) : "";
      if (deg && textOf(deg).trim()) return `\\sqrt[${convertNode(deg)}]{${body}}`;
      return `\\sqrt{${body}}`;
    }
    case "sSup": {
      const e = firstChild(el, "e");
      const sup = firstChild(el, "sup");
      return `{${e ? convertNode(e) : ""}}^{${sup ? convertNode(sup) : ""}}`;
    }
    case "sSub": {
      const e = firstChild(el, "e");
      const sub = firstChild(el, "sub");
      return `{${e ? convertNode(e) : ""}}_{${sub ? convertNode(sub) : ""}}`;
    }
    case "sSubSup": {
      const e = firstChild(el, "e");
      const sub = firstChild(el, "sub");
      const sup = firstChild(el, "sup");
      return `{${e ? convertNode(e) : ""}}_{${sub ? convertNode(sub) : ""}}^{${sup ? convertNode(sup) : ""}}`;
    }
    case "nary": {
      const naryPr = firstChild(el, "naryPr");
      let op = "\\sum ";
      if (naryPr) {
        const chr = firstChild(naryPr, "chr");
        const val = chr?.getAttribute("m:val") || chr?.getAttribute("val") || "";
        if (val === "∫") op = "\\int ";
        else if (val === "∏") op = "\\prod ";
      }
      const sub = firstChild(el, "sub");
      const sup = firstChild(el, "sup");
      const e = firstChild(el, "e");
      return `${op}_{${sub ? convertNode(sub) : ""}}^{${sup ? convertNode(sup) : ""}}{${e ? convertNode(e) : ""}}`;
    }
    case "d": {
      const inner = allChildren(el, "e").map(convertNode).join(",");
      return `\\left(${inner}\\right)`;
    }
    case "func": {
      const fName = firstChild(el, "fName");
      const e = firstChild(el, "e");
      const nameTex = fName ? convertNode(fName).trim() : "";
      const arg = e ? convertNode(e) : "";
      const fnMap: Record<string, string> = {
        sin: "\\sin",
        cos: "\\cos",
        tan: "\\tan",
        log: "\\log",
        ln: "\\ln",
        lim: "\\lim",
      };
      return `${fnMap[nameTex] || `\\operatorname{${nameTex}}`}{${arg}}`;
    }
    case "limLow": {
      const e = firstChild(el, "e");
      const lim = firstChild(el, "lim");
      return `\\lim_{${lim ? convertNode(lim) : ""}}{${e ? convertNode(e) : ""}}`;
    }
    case "bar": {
      const e = firstChild(el, "e");
      return `\\overline{${e ? convertNode(e) : ""}}`;
    }
    default:
      if (el.children.length) return childrenOf(el).map(convertNode).join("");
      return escapeTextRun(textOf(el));
  }
}

export function ommlElementToLatex(el: Element): string {
  return convertNode(el).replace(/\s+/g, " ").trim();
}

/** 把 document.xml 中的 oMath 换成 $LaTeX$ 文本 */
export function replaceOmmlWithLatexInXml(xml: string): { xml: string; count: number } {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, "application/xml");
  if (doc.getElementsByTagName("parsererror")[0]) {
    return { xml, count: 0 };
  }

  const paras = Array.from(doc.getElementsByTagNameNS(MATH_NS, "oMathPara"));
  const maths = Array.from(doc.getElementsByTagNameNS(MATH_NS, "oMath"));
  const skip = new Set<Element>();
  for (const para of paras) {
    for (const inner of Array.from(para.getElementsByTagNameNS(MATH_NS, "oMath"))) {
      skip.add(inner);
    }
  }

  let count = 0;
  for (const math of [...paras, ...maths.filter((m) => !skip.has(m))]) {
    if (!math.parentNode) continue;
    const isDisplay = localName(math) === "oMathPara";
    const latex = ommlElementToLatex(math);
    if (!latex) {
      math.parentNode.removeChild(math);
      continue;
    }
    const wrapped = isDisplay ? `$$${latex}$$` : `$${latex}$`;
    const run = doc.createElementNS(W_NS, "w:r");
    const t = doc.createElementNS(W_NS, "w:t");
    t.setAttributeNS("http://www.w3.org/XML/1998/namespace", "space", "preserve");
    t.textContent = wrapped;
    run.appendChild(t);
    math.parentNode.replaceChild(run, math);
    count += 1;
  }

  return { xml: new XMLSerializer().serializeToString(doc), count };
}
