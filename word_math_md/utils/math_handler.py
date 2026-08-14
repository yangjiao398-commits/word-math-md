"""OMML / MathType formula handling."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from word_math_md.config import ConvertConfig, MathFallback
from word_math_md.core.parser import FormulaRef
from word_math_md.utils.image_handler import (
    batch_convert_vectors_to_png,
    parse_shape_pt,
    pt_to_px,
    sha1_bytes,
)

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

OLE_PROG_IDS = {
    "Equation.DSMT4",
    "Equation.DSMT3",
    "Equation.3",
    "Equation.2",
    "MathType.Equation",
}

CHAR_MAP = {
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
}


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag.split(":")[-1]


def _children(el: ET.Element) -> list[ET.Element]:
    return list(el)


def _first(el: ET.Element, name: str) -> Optional[ET.Element]:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _all(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _text(el: ET.Element) -> str:
    return "".join(el.itertext()).replace("\u200b", "")


def _map_char(ch: str) -> str:
    if ch in CHAR_MAP:
        return CHAR_MAP[ch]
    if ch in "#$%&_{}":
        return f"\\{ch}"
    return ch


def _escape_text(raw: str) -> str:
    return "".join(_map_char(c) for c in raw)


def omml_element_to_latex(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", _convert_node(el)).strip()


def _convert_node(el: ET.Element) -> str:
    name = _local(el.tag)
    if name in {"oMath", "oMathPara", "e", "deg", "num", "den", "sub", "sup", "fName", "lim"}:
        return "".join(_convert_node(c) for c in _children(el))

    if name == "r":
        t = _first(el, "t")
        if t is not None:
            return _escape_text(_text(t))
        return "".join(_convert_node(c) for c in _children(el))

    if name == "t":
        return _escape_text(_text(el))

    if name == "f":
        num = _first(el, "num")
        den = _first(el, "den")
        return (
            f"\\dfrac{{{_convert_node(num) if num is not None else ''}}}"
            f"{{{_convert_node(den) if den is not None else ''}}}"
        )

    if name == "rad":
        deg = _first(el, "deg")
        e = _first(el, "e")
        body = _convert_node(e) if e is not None else ""
        if deg is not None and _text(deg).strip():
            return f"\\sqrt[{_convert_node(deg)}]{{{body}}}"
        return f"\\sqrt{{{body}}}"

    if name == "sSup":
        e = _first(el, "e")
        sup = _first(el, "sup")
        return f"{{{_convert_node(e) if e is not None else ''}}}^{{{_convert_node(sup) if sup is not None else ''}}}"

    if name == "sSub":
        e = _first(el, "e")
        sub = _first(el, "sub")
        return f"{{{_convert_node(e) if e is not None else ''}}}_{{{_convert_node(sub) if sub is not None else ''}}}"

    if name == "sSubSup":
        e = _first(el, "e")
        sub = _first(el, "sub")
        sup = _first(el, "sup")
        return (
            f"{{{_convert_node(e) if e is not None else ''}}}"
            f"_{{{_convert_node(sub) if sub is not None else ''}}}"
            f"^{{{_convert_node(sup) if sup is not None else ''}}}"
        )

    if name == "nary":
        nary_pr = _first(el, "naryPr")
        op = "\\sum "
        if nary_pr is not None:
            chr_el = _first(nary_pr, "chr")
            if chr_el is not None:
                val = chr_el.get(f"{{{MATH_NS}}}val") or chr_el.get("val") or ""
                if val == "∫":
                    op = "\\int "
                elif val == "∏":
                    op = "\\prod "
        sub = _first(el, "sub")
        sup = _first(el, "sup")
        e = _first(el, "e")
        return (
            f"{op}_{{{_convert_node(sub) if sub is not None else ''}}}"
            f"^{{{_convert_node(sup) if sup is not None else ''}}}"
            f"{{{_convert_node(e) if e is not None else ''}}}"
        )

    if name == "d":
        inner = ",".join(_convert_node(e) for e in _all(el, "e"))
        return f"\\left({inner}\\right)"

    if name == "func":
        f_name = _first(el, "fName")
        e = _first(el, "e")
        name_tex = _convert_node(f_name).strip() if f_name is not None else ""
        arg = _convert_node(e) if e is not None else ""
        fn_map = {"sin": "\\sin", "cos": "\\cos", "tan": "\\tan", "log": "\\log", "ln": "\\ln", "lim": "\\lim"}
        return f"{fn_map.get(name_tex, f'\\operatorname{{{name_tex}}}')}{{{arg}}}"

    if name == "limLow":
        e = _first(el, "e")
        lim = _first(el, "lim")
        return f"\\lim_{{{_convert_node(lim) if lim is not None else ''}}}{{{_convert_node(e) if e is not None else ''}}}"

    if name == "bar":
        e = _first(el, "e")
        return f"\\overline{{{_convert_node(e) if e is not None else ''}}}"

    if name == "acc":
        e = _first(el, "e")
        return f"\\hat{{{_convert_node(e) if e is not None else ''}}}"

    if name == "eqArr":
        rows = [_convert_node(e) for e in _all(el, "e")]
        return "\\begin{aligned}" + " \\\\ ".join(rows) + "\\end{aligned}"

    if list(el):
        return "".join(_convert_node(c) for c in _children(el))
    return _escape_text(_text(el))


def placeholder_for(formula_id: str) -> str:
    # Compact token; survives mammoth HTML better than markdown links
    return f"⟦MT:{formula_id}⟧"


def replace_omml_with_placeholders(docx_path: Path, config: ConvertConfig) -> tuple[Path, dict[str, FormulaRef]]:
    """Rewrite document.xml: OMML/MathType → placeholders; export MathType WMF→PNG."""
    formulas: dict[str, FormulaRef] = {}
    if config.debug and config.debug_dir:
        config.debug_dir.mkdir(parents=True, exist_ok=True)
        out = config.debug_dir / "math_placeholders.docx"
    else:
        out = docx_path.parent / f".{docx_path.stem}_math.docx"

    config.image_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(docx_path, "r") as zin:
        rels_map = _load_image_rels(zin)
        media_cache: dict[str, bytes] = {}
        pending_wmf: list[tuple[str, bytes, int | None, int | None]] = []

        doc_xml = zin.read("word/document.xml")
        new_xml, formulas, pending_wmf = _rewrite_document_xml(
            doc_xml, formulas, config, rels_map, zin, media_cache
        )

        # Batch convert MathType preview images at Word layout size
        if pending_wmf:
            blobs = [b for _, b, _, _ in pending_wmf]
            sizes: dict[str, tuple[int, int]] = {}
            for _fid, blob, w_px, h_px in pending_wmf:
                if w_px and h_px:
                    sizes[sha1_bytes(blob)] = (w_px, h_px)
            png_map = batch_convert_vectors_to_png(blobs, sizes)
            for fid, blob, _w, _h in pending_wmf:
                key = sha1_bytes(blob)
                png = png_map.get(key)
                out_path = config.image_dir / f"formula{fid}.png"
                if png:
                    out_path.write_bytes(png)
                    formulas[fid].image_path = out_path
                else:
                    # keep wmf as last resort
                    wmf_path = config.image_dir / f"formula{fid}.wmf"
                    wmf_path.write_bytes(blob)
                    formulas[fid].image_path = wmf_path

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                name = item.filename.replace("\\", "/")
                if name == "word/document.xml":
                    zout.writestr(item, new_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))

    return out, formulas


def _load_image_rels(zf: zipfile.ZipFile) -> dict[str, str]:
    """rId -> word/media/..."""
    path = "word/_rels/document.xml.rels"
    if path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(path))
    out: dict[str, str] = {}
    for rel in root:
        rid = rel.get("Id")
        target = rel.get("Target")
        if not rid or not target:
            continue
        target = target.replace("\\", "/")
        if target.startswith("/"):
            media = target.lstrip("/")
        elif target.startswith("media/"):
            media = "word/" + target
        else:
            media = "word/" + target
        out[rid] = media
    return out


def _rewrite_document_xml(
    data: bytes,
    formulas: dict[str, FormulaRef],
    config: ConvertConfig,
    rels_map: dict[str, str],
    zin: zipfile.ZipFile,
    media_cache: dict[str, bytes],
) -> tuple[bytes, dict[str, FormulaRef], list[tuple[str, bytes, int | None, int | None]]]:
    from lxml import etree

    root = etree.fromstring(data)
    ns = {"m": MATH_NS, "w": W_NS, "v": V_NS, "o": O_NS, "r": R_NS}
    counter = [len(formulas) + 1]
    pending_wmf: list[tuple[str, bytes, int | None, int | None]] = []

    def next_id() -> str:
        fid = f"{counter[0]:03d}"
        counter[0] += 1
        return fid

    def make_run(text: str):
        run = etree.Element(f"{{{W_NS}}}r")
        t = etree.SubElement(run, f"{{{W_NS}}}t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text
        return run

    # OMML
    paras = root.xpath("//m:oMathPara", namespaces=ns)
    maths = root.xpath("//m:oMath", namespaces=ns)
    skip = set()
    for para in paras:
        for inner in para.xpath(".//m:oMath", namespaces=ns):
            skip.add(inner)

    for math in list(paras) + [m for m in maths if m not in skip]:
        fid = next_id()
        display = _local(math.tag) == "oMathPara"
        latex = omml_element_to_latex(math)
        ph = placeholder_for(fid)
        formulas[fid] = FormulaRef(
            formula_id=fid,
            latex=latex or None,
            display=display,
            source="omml",
            placeholder=ph,
        )
        parent = math.getparent()
        if parent is not None:
            parent.replace(math, make_run(ph))

    # MathType OLE → keep preview WMF as formula image
    for obj in root.xpath("//w:object", namespaces=ns):
        prog = _detect_ole_prog(obj)
        if not prog or not any(p.lower() in prog.lower() for p in OLE_PROG_IDS):
            continue
        fid = next_id()
        ph = placeholder_for(fid)
        ref = FormulaRef(
            formula_id=fid,
            latex=None,
            display=False,
            source="mathtype",
            placeholder=ph,
        )
        formulas[fid] = ref

        rid = None
        w_px = h_px = None
        for shape in obj.xpath(".//v:shape", namespaces=ns):
            pts = parse_shape_pt(shape.get("style") or "")
            if pts:
                w_px, h_px = pt_to_px(pts[0]), pt_to_px(pts[1])
                break
        for im in obj.xpath(".//v:imagedata", namespaces=ns):
            rid = im.get(f"{{{R_NS}}}id") or im.get("r:id")
            if rid:
                break
        if rid and rid in rels_map:
            media_path = rels_map[rid]
            try:
                if media_path not in media_cache:
                    media_cache[media_path] = zin.read(media_path)
                blob = media_cache[media_path]
                pending_wmf.append((fid, blob, w_px, h_px))
            except KeyError:
                pass

        parent = obj.getparent()
        if parent is not None:
            parent.replace(obj, make_run(ph))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8"), formulas, pending_wmf


def _detect_ole_prog(obj) -> str:
    for el in obj.iter():
        for key, val in el.attrib.items():
            if key.endswith("ProgID") or key == "ProgID":
                return val
            if isinstance(val, str) and "Equation" in val:
                return val
    return ""


def apply_formula_placeholders(markdown: str, formulas: dict[str, FormulaRef], config: ConvertConfig) -> str:
    """Replace placeholders with $...$ / $$...$$ or formula images."""
    img_dir = config.image_dir.name

    def wrap(ref: FormulaRef) -> str:
        if ref.latex:
            body = ref.latex.strip()
            return f"$${body}$$" if ref.display else f"${body}$"
        if ref.image_path is not None:
            rel = f"{img_dir}/{ref.image_path.name}".replace("\\", "/")
            return f"![{ref.formula_id}]({rel})"
        if config.math_fallback == MathFallback.CODE:
            return f"```\n[formula {ref.formula_id} / {ref.source}]\n```"
        return f"`[公式 {ref.formula_id} 待处理]`"

    out = markdown
    for fid, ref in formulas.items():
        ph = ref.placeholder or placeholder_for(fid)
        replacement = wrap(ref)
        patterns = [
            re.escape(ph),
            # HTML-escaped variants
            re.escape(ph.replace("⟦", "[[").replace("⟧", "]]")),
            rf"\[FORMULA_{fid}\]\([^\)]*FORMULA_{fid}[^\)]*\)",
            rf"\[FORMULA_{fid}\]",
            rf"⟦MT:{fid}⟧",
        ]
        for pat in patterns:
            if re.search(pat, out):
                out = re.sub(pat, lambda _m, r=replacement: r, out, count=1)
                break
    return out
