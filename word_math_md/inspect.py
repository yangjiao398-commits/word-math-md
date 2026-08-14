"""Inspect a .docx: math formula formats and conversion-affecting structure."""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V = "urn:schemas-microsoft-com:vml"
O = "urn:schemas-microsoft-com:office:office"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"

MATHTYPE_PROG = {
    "Equation.DSMT4": "MathType OLE (Equation.DSMT4)",
    "Equation.DSMT3": "MathType OLE (Equation.DSMT3)",
    "Equation.DSMT": "MathType OLE (Equation.DSMT)",
    "MathType.Equation": "MathType OLE (MathType.Equation)",
    "Equation.3": "Microsoft Equation 3.0 OLE",
    "Equation.2": "Microsoft Equation 2.0 OLE",
}


def _qn(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _count_tag(root: ET.Element, ns: str, local: str) -> int:
    return sum(1 for _ in root.iter(_qn(ns, local)))


def _text_of(el: ET.Element) -> str:
    return "".join(el.itertext())


def _xml(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    if name not in zf.namelist():
        return None
    try:
        return ET.fromstring(zf.read(name))
    except ET.ParseError:
        return None


def _parts(zf: zipfile.ZipFile, prefix: str) -> list[str]:
    return [n for n in zf.namelist() if n.replace("\\", "/").startswith(prefix)]


def inspect_docx(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))

    with zipfile.ZipFile(path) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        doc = _xml(zf, "word/document.xml")
        if doc is None:
            raise ValueError("Invalid docx: missing word/document.xml")
        raw_doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")

        math = _inspect_math(zf, doc, raw_doc, names)
        structure = _inspect_structure(zf, doc, raw_doc, names)
        media = _inspect_media(zf, names)

    impact = _impact_rows(math, structure, media)
    return {
        "file_name": path.name,
        "file_size": path.stat().st_size,
        "summary": _summary(math, structure),
        "math": math,
        "structure": structure,
        "media": media,
        "impact": impact,
    }


def _inspect_math(zf: zipfile.ZipFile, doc: ET.Element, raw: str, names: list[str]) -> dict[str, Any]:
    o_math = _count_tag(doc, M, "oMath")
    o_math_para = _count_tag(doc, M, "oMathPara")
    nested = set()
    for para in doc.iter(_qn(M, "oMathPara")):
        for inner in para.iter(_qn(M, "oMath")):
            nested.add(id(inner))
    inline_omml = sum(1 for el in doc.iter(_qn(M, "oMath")) if id(el) not in nested)

    ole_prog: Counter[str] = Counter()
    ole_total = 0
    for obj in doc.iter(_qn(W, "object")):
        ole_total += 1
        prog = ""
        for el in obj.iter():
            for key, val in el.attrib.items():
                if key.endswith("ProgID") or key == "ProgID":
                    prog = val
                    break
            if prog:
                break
            if isinstance(el.attrib.get("ProgID"), str):
                prog = el.attrib["ProgID"]
                break
        ole_prog[prog or "(unknown OLE)"] += 1

    mathtype = 0
    ms_eq = 0
    other_ole = 0
    ole_rows = []
    for prog, n in ole_prog.most_common():
        label = MATHTYPE_PROG.get(prog)
        if label is None:
            if "DSMT" in prog or "MathType" in prog:
                label = f"MathType OLE ({prog})"
                mathtype += n
            elif prog.startswith("Equation."):
                label = f"Equation OLE ({prog})"
                ms_eq += n
            else:
                label = f"其他 OLE ({prog})"
                other_ole += n
        else:
            if "MathType" in label:
                mathtype += n
            else:
                ms_eq += n
        ole_rows.append({"prog_id": prog or "—", "label": label, "count": n})

    vml_imagedata = _count_tag(doc, V, "imagedata")
    drawings = _count_tag(doc, WP, "inline") + _count_tag(doc, WP, "anchor")
    blips = _count_tag(doc, A, "blip")

    media = [n for n in names if n.startswith("word/media/") and not n.endswith("/")]
    by_ext = Counter(Path(n).suffix.lower() or "(none)" for n in media)
    wmf = by_ext.get(".wmf", 0)
    emf = by_ext.get(".emf", 0)
    raster = sum(by_ext[e] for e in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff") if e in by_ext)

    embeddings = [n for n in names if n.startswith("word/embeddings/") and not n.endswith("/")]
    emb_ext = Counter(Path(n).suffix.lower() or "(none)" for n in embeddings)

    dollar = len(re.findall(r"(?<!\\)\$(?!\$)[^$\n]{1,80}\$", raw))
    display_tex = len(re.findall(r"\\\[.+?\\\]|\$\$[^$]+\$\$", raw, re.S))
    latex_cmd = len(re.findall(r"\\(frac|dfrac|sqrt|sum|int|alpha|beta|theta|cdot|times)\b", raw))

    types: list[dict[str, Any]] = []

    def add(kind: str, label: str, count: int, how: str, convert: str, evidence: str = ""):
        types.append(
            {
                "kind": kind,
                "label": label,
                "count": count,
                "present": count > 0,
                "how_stored": how,
                "convert_path": convert,
                "evidence": evidence,
            }
        )

    add(
        "omml_display",
        "OfficeMath 独立公式 (oMathPara)",
        o_math_para,
        "Word 原生 OMML 段落公式",
        "可转 LaTeX（$$...$$）",
        "m:oMathPara",
    )
    add(
        "omml_inline",
        "OfficeMath 行内公式 (oMath)",
        inline_omml,
        "Word 原生 OMML 行内公式",
        "可转 LaTeX",
        "m:oMath",
    )
    add(
        "mathtype_ole",
        "MathType OLE（Equation.DSMT）",
        mathtype,
        "OLE 嵌入对象 + 通常附带 WMF 预览图",
        "无 SDK 时降级为公式 PNG；有 SDK 可转 LaTeX",
        ", ".join(f"{p}×{n}" for p, n in ole_prog.items() if "DSMT" in p or "MathType" in p) or "—",
    )
    add(
        "ms_equation_ole",
        "Microsoft Equation 3.0/2.0 OLE",
        ms_eq,
        "旧版公式编辑器 OLE",
        "通常只能导出预览图，难还原 LaTeX",
        ", ".join(f"{p}×{n}" for p, n in ole_prog.items() if p.startswith("Equation.") and "DSMT" not in p) or "—",
    )
    add(
        "other_ole",
        "其他 OLE 对象",
        other_ole,
        "非公式或未知 ProgID 的嵌入对象",
        "可能丢失或变成图片/占位",
        ", ".join(f"{p}×{n}" for p, n in ole_prog.items() if p not in MATHTYPE_PROG and "DSMT" not in p and not p.startswith("Equation."))
        or "—",
    )
    add(
        "wmf_emf",
        "WMF/EMF 矢量图（含公式预览）",
        wmf + emf,
        "word/media 中的元文件，常作为 MathType 预览",
        "转为 PNG 后以 ![]() 写入 Markdown",
        f"wmf={wmf}, emf={emf}, v:imagedata={vml_imagedata}",
    )
    add(
        "raster",
        "栅格图片 PNG/JPG/GIF/BMP",
        raster,
        "普通插图或公式截图",
        "导出到 assets，Markdown 引用",
        ", ".join(f"{k}={v}" for k, v in sorted(by_ext.items()) if k in {".png", ".jpg", ".jpeg", ".gif", ".bmp"}),
    )
    add(
        "drawingml",
        "DrawingML 图片 (wp:inline / wp:anchor)",
        drawings,
        "新版 Word 绘图/图片框",
        "浮动图可能错位；需按版式决定行内或块级",
        f"inline+anchor={drawings}, a:blip={blips}",
    )
    add(
        "latex_text",
        "正文中的 LaTeX 文本痕迹",
        dollar + display_tex + (1 if latex_cmd else 0),
        "文档 XML 文本里出现 $...$ / \\frac 等",
        "需避免二次转义；可能与真实公式重复",
        f"$行内约 {dollar}，$$/\\[\\] {display_tex}，LaTeX 命令 {latex_cmd}",
    )

    primary = "none"
    if mathtype:
        primary = "mathtype_ole"
    elif o_math or o_math_para:
        primary = "omml"
    elif wmf + emf:
        primary = "wmf_emf"
    elif raster:
        primary = "raster"
    elif ms_eq:
        primary = "ms_equation_ole"

    return {
        "primary": primary,
        "types": types,
        "ole_by_progid": ole_rows,
        "counts": {
            "oMath": o_math,
            "oMathPara": o_math_para,
            "ole_objects": ole_total,
            "mathtype": mathtype,
            "ms_equation": ms_eq,
            "vml_imagedata": vml_imagedata,
            "drawings": drawings,
            "wmf": wmf,
            "emf": emf,
            "raster": raster,
            "embeddings": len(embeddings),
        },
        "embeddings_by_ext": dict(emb_ext),
        "media_by_ext": dict(by_ext),
    }


def _header_footer_info(zf: zipfile.ZipFile, names: list[str]) -> dict[str, Any]:
    headers = [n for n in names if "/header" in n and n.endswith(".xml")]
    footers = [n for n in names if "/footer" in n and n.endswith(".xml")]
    nonempty_h = 0
    nonempty_f = 0
    has_page_field = False
    samples = []
    for n in headers + footers:
        root = _xml(zf, n)
        if root is None:
            continue
        text = "".join(root.itertext()).strip()
        has_img = any(True for _ in root.iter(_qn(V, "imagedata"))) or any(
            True for _ in root.iter(_qn(A, "blip"))
        )
        raw = ET.tostring(root, encoding="unicode")
        if "PAGE" in raw or "NUMPAGES" in raw:
            has_page_field = True
        if text or has_img:
            if n in headers:
                nonempty_h += 1
            else:
                nonempty_f += 1
            if len(samples) < 4:
                samples.append({"part": n, "preview": (text[:40] + "…") if len(text) > 40 else text or "(含图片/域)"})
    return {
        "header_parts": len(headers),
        "footer_parts": len(footers),
        "nonempty_headers": nonempty_h,
        "nonempty_footers": nonempty_f,
        "page_number_fields": has_page_field,
        "samples": samples,
    }


def _inspect_structure(zf: zipfile.ZipFile, doc: ET.Element, raw: str, names: list[str]) -> dict[str, Any]:
    comments_xml = "word/comments.xml" in names
    comment_marks = _count_tag(doc, W, "commentRangeStart") + _count_tag(doc, W, "commentReference")

    ins = _count_tag(doc, W, "ins")
    dels = _count_tag(doc, W, "del")
    rpr_change = _count_tag(doc, W, "rPrChange")
    ppr_change = _count_tag(doc, W, "pPrChange")
    revisions = ins + dels + rpr_change + ppr_change

    hf = _header_footer_info(zf, names)

    sect = list(doc.iter(_qn(W, "sectPr")))
    sect_types: Counter[str] = Counter()
    for s in sect:
        st = s.find(_qn(W, "type"))
        val = (st.get(_qn(W, "val")) if st is not None else None) or "nextPage(default)"
        sect_types[val] += 1

    page_br = 0
    for br in doc.iter(_qn(W, "br")):
        if br.get(_qn(W, "type")) == "page":
            page_br += 1
    last_rendered = _count_tag(doc, W, "lastRenderedPageBreak")

    empty_p = 0
    total_p = 0
    consecutive_empty = 0
    max_empty_run = 0
    for p in doc.iter(_qn(W, "p")):
        # skip paragraphs inside tbl? still count — empty rows matter less
        total_p += 1
        text = "".join(t.text or "" for t in p.iter(_qn(W, "t"))).strip()
        has_obj = any(True for _ in p.iter(_qn(W, "object"))) or any(
            True for _ in p.iter(_qn(M, "oMath"))
        ) or any(True for _ in p.iter(_qn(WP, "inline"))) or any(
            True for _ in p.iter(_qn(V, "imagedata"))
        )
        if not text and not has_obj:
            empty_p += 1
            consecutive_empty += 1
            max_empty_run = max(max_empty_run, consecutive_empty)
        else:
            consecutive_empty = 0

    vanish = 0
    for vanish_el in doc.iter(_qn(W, "vanish")):
        vanish += 1

    textboxes = _count_tag(doc, W, "txbxContent") + _count_tag(doc, V, "textbox")
    footnotes = 1 if "word/footnotes.xml" in names else 0
    endnotes = 1 if "word/endnotes.xml" in names else 0
    fn_root = _xml(zf, "word/footnotes.xml")
    en_root = _xml(zf, "word/endnotes.xml")
    fn_count = 0
    if fn_root is not None:
        fn_count = sum(
            1
            for el in fn_root.iter(_qn(W, "footnote"))
            if el.get(_qn(W, "type")) not in {"separator", "continuationSeparator"}
        )
    en_count = 0
    if en_root is not None:
        en_count = sum(
            1
            for el in en_root.iter(_qn(W, "endnote"))
            if el.get(_qn(W, "type")) not in {"separator", "continuationSeparator"}
        )

    tables = _count_tag(doc, W, "tbl")
    sdt = _count_tag(doc, W, "sdt")
    hyper = _count_tag(doc, W, "hyperlink")
    bookmark = _count_tag(doc, W, "bookmarkStart")
    tabs = _count_tag(doc, W, "tab")
    fields = raw.count("<w:fldChar") + raw.count("w:instrText")
    toc = len(re.findall(r"TOC\\", raw)) + raw.count("TOC ")
    page_fields = len(re.findall(r"\bPAGE\b|\bNUMPAGES\b", raw))
    numbering = "word/numbering.xml" in names
    alt_content = raw.count("mc:AlternateContent")
    wrap = _count_tag(doc, WP, "anchor")  # floating
    smartart = raw.lower().count("dgm:relids") + raw.count("wps:wsp")
    frames = _count_tag(doc, W, "framePr")
    watermark = "watermark" in raw.lower() or "POWERPLUSWATERMARK" in raw
    hidden_sect = any("word/header" in n or "word/footer" in n for n in names)

    styles = []
    heading_p = 0
    for p in doc.iter(_qn(W, "p")):
        ppr = p.find(_qn(W, "pPr"))
        if ppr is None:
            continue
        ps = ppr.find(_qn(W, "pStyle"))
        if ps is not None:
            val = ps.get(_qn(W, "val")) or ""
            if val.lower().startswith("heading") or "标题" in val:
                heading_p += 1

    rows = [
        _row("修订 / 跟踪更改", revisions > 0, revisions, f"插入 {ins}，删除 {dels}，属性更改 {rpr_change + ppr_change}", "未接受修订时正文会混入删改痕迹"),
        _row("批注", comments_xml or comment_marks > 0, comment_marks, f"comments.xml={'有' if comments_xml else '无'}，标记 {comment_marks}", "批注标记会变成杂讯或断开句子"),
        _row("页眉", hf["nonempty_headers"] > 0, hf["nonempty_headers"], f"{hf['header_parts']} 个页眉部件，非空 {hf['nonempty_headers']}", "Markdown 无页眉，应删除以免混入正文"),
        _row("页脚", hf["nonempty_footers"] > 0, hf["nonempty_footers"], f"{hf['footer_parts']} 个页脚部件，非空 {hf['nonempty_footers']}", "同上，页脚文字不应进入正文"),
        _row("页码域", hf["page_number_fields"] or page_fields > 0, page_fields + (1 if hf["page_number_fields"] else 0), "PAGE / NUMPAGES 域（正文或页眉页脚）", "页码对 Markdown 无意义，可能变成裸数字"),
        _row("分节符", len(sect) > 1, len(sect), "类型: " + (", ".join(f"{k}×{v}" for k, v in sect_types.items()) or "—"), "分节常用于换页/栏，Markdown 中应忽略或变成分隔线"),
        _row("分页符", page_br > 0, page_br, f"显式分页 {page_br}，渲染分页标记 {last_rendered}", "分页在 Markdown 中无对应结构"),
        _row("空段落", empty_p > 0, empty_p, f"共 {total_p} 段，空段 {empty_p}，最长连续空段 {max_empty_run}", "产生多余空行，需后处理合并"),
        _row("隐藏文字", vanish > 0, vanish, "w:vanish", "隐藏文字可能泄漏进 Markdown 或造成空白"),
        _row("文本框 / 文本框内容", textboxes > 0, textboxes, "txbxContent / v:textbox", "文本框内容可能丢失或出现在错误位置"),
        _row("浮动图形 (anchor)", wrap > 0, wrap, "wp:anchor", "环绕排版无法保留，图片可能跑到段末"),
        _row("脚注", fn_count > 0, fn_count, "word/footnotes.xml", "需转为 Markdown 脚注 [^n]"),
        _row("尾注", en_count > 0, en_count, "word/endnotes.xml", "需转为文末注释"),
        _row("表格", tables > 0, tables, "w:tbl", "复杂合并单元格可能变成错位 pipe table"),
        _row("内容控件 (SDT)", sdt > 0, sdt, "w:sdt", "控件外壳应去掉，只保留显示文本"),
        _row("超链接", hyper > 0, hyper, "w:hyperlink", "应转为 [text](url)，域代码需展开"),
        _row("书签", bookmark > 0, bookmark, "w:bookmarkStart", "交叉引用可能变成残留书签名"),
        _row("制表符", tabs > 0, tabs, "w:tab", "对齐用 Tab 在 Markdown 中会乱，需改空格/表格"),
        _row("域 (含目录等)", fields > 0, fields, f"fldChar/instrText，TOC 痕迹 {toc}", "未展开的域会留下乱码或重复目录"),
        _row("编号/列表定义", numbering, 1 if numbering else 0, "word/numbering.xml", "多级列表缩进可能不准"),
        _row("标题样式段落", heading_p > 0, heading_p, "Heading / 标题样式", "用于生成 # / ##，样式丢失则全成普通段"),
        _row("AlternateContent 兼容包装", alt_content > 0, alt_content, "mc:AlternateContent", "可能重复导出新旧两套图形"),
        _row("图文框 framePr", frames > 0, frames, "w:framePr", "绝对定位框无法映射"),
        _row("水印", watermark, 1 if watermark else 0, "header 水印/VML", "可能被当成背景图导出"),
        _row("SmartArt / 形状", smartart > 0, smartart, "drawingML 形状", "多转为图片，结构丢失"),
    ]

    return {
        "rows": rows,
        "header_footer": hf,
        "counts": {
            "revisions": revisions,
            "insertions": ins,
            "deletions": dels,
            "comments": comment_marks,
            "sections": len(sect),
            "page_breaks": page_br,
            "empty_paragraphs": empty_p,
            "paragraphs": total_p,
            "max_empty_run": max_empty_run,
            "textboxes": textboxes,
            "tables": tables,
            "footnotes": fn_count,
            "endnotes": en_count,
            "headings": heading_p,
        },
    }


def _row(name: str, present: bool, count: int, detail: str, impact: str) -> dict[str, Any]:
    return {
        "name": name,
        "present": bool(present),
        "count": int(count),
        "detail": detail,
        "impact": impact,
        "status": "有" if present else "无",
    }


def _inspect_media(zf: zipfile.ZipFile, names: list[str]) -> dict[str, Any]:
    media = [n for n in names if n.startswith("word/media/") and not n.endswith("/")]
    by_ext = Counter(Path(n).suffix.lower() or "(none)" for n in media)
    embeddings = [n for n in names if n.startswith("word/embeddings/") and not n.endswith("/")]
    return {
        "media_count": len(media),
        "by_ext": dict(sorted(by_ext.items(), key=lambda x: (-x[1], x[0]))),
        "embeddings": len(embeddings),
        "sample": [Path(n).name for n in media[:12]],
    }


def _impact_rows(math: dict, structure: dict, media: dict) -> list[dict[str, str]]:
    rows = []
    primary = math.get("primary")
    if primary == "mathtype_ole":
        rows.append({"level": "高", "item": "主体公式是 MathType OLE", "note": "默认会导出为 PNG，而不是 LaTeX。"})
    elif primary == "omml":
        rows.append({"level": "中", "item": "主体公式是 OMML", "note": "可转 LaTeX，复杂结构仍可能有缺口。"})
    elif primary == "wmf_emf":
        rows.append({"level": "高", "item": "公式主要是 WMF/EMF 图", "note": "只能当图片，无法得到可编辑 LaTeX。"})

    for r in structure["rows"]:
        if r["present"] and r["name"] in {
            "修订 / 跟踪更改",
            "批注",
            "页眉",
            "页脚",
            "文本框 / 文本框内容",
            "浮动图形 (anchor)",
            "分页符",
            "空段落",
        }:
            rows.append({"level": "中", "item": r["name"], "note": r["impact"]})
    if media["media_count"] > 200:
        rows.append({"level": "中", "item": "媒体文件很多", "note": f"{media['media_count']} 个 media，转换和预览会较慢。"})
    return rows


def _summary(math: dict, structure: dict) -> str:
    c = math["counts"]
    s = structure["counts"]
    bits = []
    if c["mathtype"]:
        bits.append(f"MathType {c['mathtype']} 个")
    if c["oMath"] or c["oMathPara"]:
        bits.append(f"OMML {c['oMathPara']} 段+{c['oMath']} 个")
    if c["wmf"] or c["emf"]:
        bits.append(f"WMF/EMF {c['wmf'] + c['emf']} 张")
    if s["revisions"]:
        bits.append("含修订")
    if s["comments"]:
        bits.append("含批注")
    if not bits:
        return "未发现明显公式对象，请检查是否为纯文本或图片试卷。"
    return "；".join(bits) + "。"
