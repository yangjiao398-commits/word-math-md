"""Extract MathType / Equation OLE objects from a .docx and convert them to LaTeX.

Primary path: Equation Native (MTEF). Fallback: MathML stream if present.
Writes a *new* .docx with OLE replaced by $LaTeX$; the source file is never modified.
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from lxml import etree
from olefile import OleFileIO

from word_math_md.mtef import ole_bytes_to_latex

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag.split(":")[-1]


def _r_id(el) -> str | None:
    direct = el.get(f"{{{R_NS}}}id")
    if direct:
        return direct
    for key, val in el.attrib.items():
        if key in {"r:id", "id"} or str(key).endswith("}id"):
            return val
    return None


def _load_rels(rel_path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not rel_path.is_file():
        return mapping
    root = ET.parse(rel_path).getroot()
    for rel in root.iter():
        if _local(rel.tag) != "Relationship":
            continue
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            mapping[rid] = target.replace("\\", "/")
    return mapping


def extract_mathml_from_ole(ole_data: bytes) -> str | None:
    try:
        ole = OleFileIO(ole_data)
        try:
            streams = ole.listdir()
            mathml_data = None
            for stream in streams:
                joined = "/".join(stream)
                if "MathML" in joined or "mathml" in joined.lower():
                    mathml_data = ole.openstream(stream).read()
                    break
            if mathml_data:
                text = mathml_data.decode("utf-8", errors="ignore")
                start = text.find("<math")
                if start >= 0:
                    end = text.rfind("</math>")
                    return text[start : end + 7] if end > start else text[start:]
                return text
        finally:
            ole.close()
    except Exception:
        pass

    raw = ole_data.decode("utf-8", errors="ignore")
    start = raw.find("<math")
    if start >= 0:
        end = raw.rfind("</math>")
        if end > start:
            return raw[start : end + 7]
    return None


def mathml_to_latex(mathml: str) -> str:
    try:
        from mathml2latex import mathml2latex as convert_fn

        if callable(convert_fn):
            return str(convert_fn(mathml))
    except Exception:
        pass

    from bs4 import BeautifulSoup
    from mathml2latex.mathml import process_mathml

    soup = BeautifulSoup(mathml, "lxml-xml")
    if soup.find("math") is None:
        soup = BeautifulSoup(mathml, "html.parser")
    latex = process_mathml(soup)
    if not latex or not str(latex).strip():
        raise ValueError("MathML 转换结果为空")
    return str(latex).strip()


def _unicode_to_latex(text: str) -> str:
    repl = {
        "≤": r"\le ",
        "≥": r"\ge ",
        "≠": r"\ne ",
        "±": r"\pm ",
        "×": r"\times ",
        "÷": r"\div ",
        "·": r"\cdot ",
        "∞": r"\infty ",
        "π": r"\pi ",
        "α": r"\alpha ",
        "β": r"\beta ",
        "θ": r"\theta ",
        "Δ": r"\Delta ",
        "∈": r"\in ",
        "⊂": r"\subset ",
        "∪": r"\cup ",
        "∩": r"\cap ",
        "→": r"\to ",
        "⇒": r"\Rightarrow ",
        "∑": r"\sum ",
        "∏": r"\prod ",
        "∫": r"\int ",
        "∠": r"\angle ",
        "∴": r"\therefore ",
        "∵": r"\because ",
        "≈": r"\approx ",
        "≡": r"\equiv ",
        "⊆": r"\subseteq ",
        "⊇": r"\supseteq ",
        "∉": r"\notin ",
        "∀": r"\forall ",
        "∃": r"\exists ",
        "∂": r"\partial ",
        "∇": r"\nabla ",
        "√": r"\sqrt ",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return _cleanup_mtef_latex(text)


def _cleanup_mtef_latex(text: str) -> str:
    s = text
    s = re.sub(r"\\begin\{array\}\s*\{\s*\}", r"\\begin{array}{l}", s)
    s = re.sub(
        r"\{\s*\\rm\{\s*l\s*\}\s*\}\s*\{\s*\\rm\{\s*o\s*\}\s*\}\s*\{\s*\\rm\{\s*g\s*\}\s*\}\s*_(\s*\{?\s*[0-9n]+\s*\}?)",
        lambda m: r"\log_{%s}" % re.sub(r"\s+", "", m.group(1)),
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\{\s*\\rm\{\s*l\s*\}\s*\}\s*\{\s*\\rm\{\s*o\s*\}\s*\}\s*\{\s*\\rm\{\s*g\s*\}\s*\}",
        r"\\log",
        s,
        flags=re.I,
    )
    s = re.sub(r"\{\s*\\rm\{\s*\\pi\s*\}\s*\}", r"\\pi", s, flags=re.I)
    s = re.sub(r"\\sqrt\s*\[\s*\]\s*\{", r"\\sqrt{", s)
    return s


def ole_to_latex(ole_bin: bytes) -> str:
    """Convert a MathType OLE compound file to a LaTeX body (no wrapping $)."""
    try:
        latex = ole_bytes_to_latex(ole_bin)
        if latex and latex.strip():
            return _unicode_to_latex(latex.strip())
    except Exception:
        pass
    mathml = extract_mathml_from_ole(ole_bin)
    if mathml:
        return _unicode_to_latex(mathml_to_latex(mathml))
    raise ValueError("no MTEF or MathML")


def _convert_ole_bytes(ole_bin: bytes, source_name: str) -> dict[str, str | None]:
    mathml = extract_mathml_from_ole(ole_bin)
    try:
        latex_code = ole_to_latex(ole_bin)
        return {"mathml": mathml, "latex": latex_code, "source": source_name}
    except Exception:
        if mathml:
            return {"mathml": mathml, "latex": "【MathML转LaTeX失败】", "source": source_name}
        return {"mathml": None, "latex": "【无法提取】", "source": source_name}


def _word_part(target: str) -> str:
    path = Path("word") / target.replace("\\", "/")
    return path.as_posix()


def _make_latex_text(latex: str):
    el = etree.Element(f"{{{W_NS}}}t")
    el.set(f"{{{XML_NS}}}space", "preserve")
    el.text = f"${latex}$"
    return el


def _replace_ole_in_xml(
    doc_xml: bytes,
    rels: dict[str, str],
    zin: zipfile.ZipFile,
) -> tuple[bytes, list[dict[str, str | None]], set[str], set[str]]:
    root = etree.fromstring(doc_xml)
    formulas: list[dict[str, str | None]] = []
    drop_rids: set[str] = set()
    drop_parts: set[str] = set()

    for ole_obj in list(root.iter()):
        if _local(ole_obj.tag) != "OLEObject":
            continue
        r_id = _r_id(ole_obj)
        if not r_id:
            continue
        target = rels.get(r_id)
        if not target or "embeddings/" not in target:
            continue
        part = _word_part(target)
        try:
            ole_bin = zin.read(part)
        except KeyError:
            continue
        item = _convert_ole_bytes(ole_bin, Path(part).name)
        formulas.append(item)

        replace = ole_obj
        cur = ole_obj
        while cur is not None:
            if _local(cur.tag) == "object":
                replace = cur
                break
            cur = cur.getparent()

        for node in replace.iter():
            rid = _r_id(node)
            if rid:
                drop_rids.add(rid)
                tgt = rels.get(rid)
                if tgt and "embeddings/" in tgt:
                    drop_parts.add(_word_part(tgt))

        parent = replace.getparent()
        if parent is not None:
            parent.replace(replace, _make_latex_text(str(item.get("latex") or "")))

    return (
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
        formulas,
        drop_rids,
        drop_parts,
    )


def _strip_rels(rels_xml: bytes, drop_rids: set[str]) -> bytes:
    root = etree.fromstring(rels_xml)
    for rel in list(root):
        if rel.get("Id") in drop_rids:
            parent = rel.getparent()
            if parent is not None:
                parent.remove(rel)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def convert_ole_docx(
    src: str | os.PathLike[str],
    dest: str | os.PathLike[str],
) -> list[dict[str, str | None]]:
    """Convert OLE formulas to $LaTeX$ and write a new docx.

    The source file is only read; dest must be a different path.
    """
    src = Path(src).resolve()
    dest = Path(dest).resolve()
    if dest == src:
        raise ValueError("输出路径不能与源文件相同，源文件不会被修改")
    dest.parent.mkdir(parents=True, exist_ok=True)

    rels_name = "word/_rels/document.xml.rels"
    with zipfile.ZipFile(src, "r") as zin:
        names = set(zin.namelist())
        if "word/document.xml" not in names:
            dest.write_bytes(src.read_bytes())
            return []
        rels_xml = zin.read(rels_name) if rels_name in names else None
        rels = {}
        if rels_xml:
            rel_root = etree.fromstring(rels_xml)
            for rel in rel_root.iter():
                if _local(rel.tag) != "Relationship":
                    continue
                rid, target = rel.get("Id"), rel.get("Target")
                if rid and target:
                    rels[rid] = target.replace("\\", "/")

        new_doc, formulas, drop_rids, drop_parts = _replace_ole_in_xml(
            zin.read("word/document.xml"), rels, zin
        )
        new_rels = _strip_rels(rels_xml, drop_rids) if rels_xml is not None else None

        tmp = dest.with_suffix(dest.suffix + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in drop_parts:
                    continue
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_doc)
                elif item.filename == rels_name and new_rels is not None:
                    zout.writestr(item, new_rels)
                else:
                    zout.writestr(item, zin.read(item.filename))
        tmp.replace(dest)
    return formulas


def docx_extract_mt_formulas(docx_path: str | os.PathLike[str]) -> list[dict[str, str | None]]:
    """Read-only extraction; does not write the source file."""
    src = Path(docx_path)
    with zipfile.ZipFile(src, "r") as zin:
        if "word/document.xml" not in zin.namelist():
            return []
        rels_name = "word/_rels/document.xml.rels"
        rels: dict[str, str] = {}
        if rels_name in zin.namelist():
            rel_root = etree.fromstring(zin.read(rels_name))
            for rel in rel_root.iter():
                if _local(rel.tag) != "Relationship":
                    continue
                rid, target = rel.get("Id"), rel.get("Target")
                if rid and target:
                    rels[rid] = target.replace("\\", "/")
        _new_doc, formulas, _rids, _parts = _replace_ole_in_xml(
            zin.read("word/document.xml"), rels, zin
        )
        if formulas:
            return formulas
        embeddings = [n for n in zin.namelist() if n.startswith("word/embeddings/") and not n.endswith("/")]
        return [_convert_ole_bytes(zin.read(name), Path(name).name) for name in sorted(embeddings)]


def format_formula_list(formulas: list[dict[str, str | None]]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(formulas, 1):
        lines.append(f"===== 公式 {idx} =====")
        lines.append(f"LaTeX:\n${item.get('latex')}$")
        lines.append("")
    return "\n".join(lines)
