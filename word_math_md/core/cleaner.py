"""Document cleaner — strip comments, revisions, headers/footers, etc."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from word_math_md.config import CleanLevel, ConvertConfig

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}

ET.register_namespace("w", W_NS)
ET.register_namespace("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")
ET.register_namespace("m", "http://schemas.openxmlformats.org/officeDocument/2006/math")
ET.register_namespace("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
ET.register_namespace("a", "http://schemas.openxmlformats.org/drawingml/2006/main")
ET.register_namespace("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture")
ET.register_namespace("v", "urn:schemas-microsoft-com:vml")
ET.register_namespace("o", "urn:schemas-microsoft-com:office:office")


def _qn(tag: str) -> str:
    prefix, local = tag.split(":")
    return f"{{{NSMAP[prefix]}}}{local}"


def _has_aspose() -> bool:
    try:
        import aspose.words  # noqa: F401

        return True
    except ImportError:
        return False


def clean_document(docx_path: Path, config: ConvertConfig) -> Path:
    """Clean a docx and return path to cleaned file."""
    if config.clean_level == CleanLevel.NONE:
        return docx_path

    backend = config.backend
    if backend == "auto":
        backend = "aspose" if _has_aspose() else "foss"
    if backend == "aspose" and _has_aspose():
        return _clean_with_aspose(docx_path, config)
    return _clean_with_foss(docx_path, config)


def _clean_with_aspose(docx_path: Path, config: ConvertConfig) -> Path:
    import aspose.words as aw

    lic = Path(__file__).resolve().parents[2] / "Aspose.Words.lic"
    lic_env = os.environ.get("ASPOSE_WORDS_LICENSE")
    if lic_env and Path(lic_env).exists():
        aw.License().set_license(lic_env)
    elif lic.exists():
        aw.License().set_license(str(lic))

    doc = aw.Document(str(docx_path))

    if config.accept_revisions:
        doc.accept_all_revisions()
    else:
        doc.reject_all_revisions()

    doc.comments.clear()

    for section in doc.sections:
        section.headers_footers.clear()

    if config.clean_level == CleanLevel.AGGRESSIVE:
        shapes = list(doc.get_child_nodes(aw.NodeType.SHAPE, True))
        for shape in shapes:
            try:
                if config.remove_textboxes and shape.shape_type == aw.drawing.ShapeType.TEXT_BOX:
                    shape.remove()
            except Exception:
                continue

        paragraphs = list(doc.get_child_nodes(aw.NodeType.PARAGRAPH, True))
        for p in paragraphs:
            if not p.to_string(aw.SaveFormat.TEXT).strip():
                if p.get_ancestor(aw.NodeType.CELL) is None:
                    p.remove()

        cleanup = aw.CleanupOptions()
        cleanup.unused_styles = True
        cleanup.unused_lists = True
        doc.cleanup(cleanup)

    out = _debug_or_temp(docx_path, config, "clean.docx")
    doc.save(str(out))
    return out


def _clean_with_foss(docx_path: Path, config: ConvertConfig) -> Path:
    out = _debug_or_temp(docx_path, config, "clean.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            name = item.filename.replace("\\", "/")

            if name == "word/document.xml":
                data = _clean_document_xml(data, config)
            elif name.startswith("word/header") or name.startswith("word/footer"):
                if config.clean_level in (CleanLevel.BASIC, CleanLevel.AGGRESSIVE):
                    if "header" in name:
                        data = (
                            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                            b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
                        )
                    else:
                        data = (
                            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                            b'<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
                        )
            elif name == "word/comments.xml" and config.clean_level != CleanLevel.NONE:
                continue
            zout.writestr(item, data)
    return out


def _clean_document_xml(data: bytes, config: ConvertConfig) -> bytes:
    root = ET.fromstring(data)

    for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
        for el in list(root.iter(_qn(f"w:{tag}"))):
            parent = _parent_map(root).get(el)
            if parent is not None:
                parent.remove(el)

    parent_map = _parent_map(root)
    for el in list(root.iter(_qn("w:del"))):
        parent = parent_map.get(el)
        if parent is not None:
            parent.remove(el)

    parent_map = _parent_map(root)
    for el in list(root.iter(_qn("w:ins"))):
        parent = parent_map.get(el)
        if parent is None:
            continue
        idx = list(parent).index(el)
        for i, child in enumerate(list(el)):
            parent.insert(idx + i, child)
        parent.remove(el)

    if config.clean_level == CleanLevel.AGGRESSIVE:
        parent_map = _parent_map(root)
        for br in list(root.iter(_qn("w:br"))):
            if br.get(_qn("w:type")) == "page":
                parent = parent_map.get(br)
                if parent is not None:
                    parent.remove(br)

        parent_map = _parent_map(root)
        for r in list(root.iter(_qn("w:r"))):
            rpr = r.find(_qn("w:rPr"))
            if rpr is not None and rpr.find(_qn("w:vanish")) is not None:
                parent = parent_map.get(r)
                if parent is not None:
                    parent.remove(r)

        parent_map = _parent_map(root)
        math_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
        draw_ns = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
        for p in list(root.iter(_qn("w:p"))):
            text = "".join(t.text or "" for t in p.iter(_qn("w:t"))).strip()
            has_math = any(True for _ in p.iter(f"{math_ns}oMath"))
            has_draw = any(True for _ in p.iter(f"{draw_ns}inline")) or any(
                True for _ in p.iter("{urn:schemas-microsoft-com:vml}imagedata")
            )
            has_ole = any(True for _ in p.iter(_qn("w:object")))
            if not text and not has_math and not has_draw and not has_ole:
                parent = parent_map.get(p)
                if parent is not None and parent.tag != _qn("w:tc"):
                    parent.remove(p)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _parent_map(root: ET.Element) -> dict:
    return {c: p for p in root.iter() for c in p}


def _debug_or_temp(docx_path: Path, config: ConvertConfig, name: str) -> Path:
    if config.debug and config.debug_dir:
        config.debug_dir.mkdir(parents=True, exist_ok=True)
        return config.debug_dir / name
    return docx_path.parent / f".{docx_path.stem}_{name}"


XML_NS = "http://www.w3.org/XML/1998/namespace"
TAB_AS_SPACES = "    "


def preprocess_docx(src: Path, dest: Path) -> dict:
    """Replace tabs with spaces, remove footers, drop empty paragraphs.

    Returns a stats dict. Writes a new .docx to dest.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    stats = {"tabs_replaced": 0, "footers_cleared": 0, "empty_paragraphs_removed": 0}

    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            name = item.filename.replace("\\", "/")
            if name == "word/document.xml":
                data, n_tab, n_empty = _preprocess_document_xml(data)
                stats["tabs_replaced"] = n_tab
                stats["empty_paragraphs_removed"] = n_empty
            elif name.startswith("word/footer") and name.endswith(".xml"):
                data = (
                    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    b'<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
                )
                stats["footers_cleared"] += 1
            zout.writestr(item, data)
    return stats


def _preprocess_document_xml(data: bytes) -> tuple[bytes, int, int]:
    root = ET.fromstring(data)
    n_tab = 0

    # Tab characters inside text runs
    for t in list(root.iter(_qn("w:t"))):
        if t.text and "\t" in t.text:
            n_tab += t.text.count("\t")
            t.text = t.text.replace("\t", TAB_AS_SPACES)
            t.set(f"{{{XML_NS}}}space", "preserve")
        if t.tail and "\t" in t.tail:
            n_tab += t.tail.count("\t")
            t.tail = t.tail.replace("\t", TAB_AS_SPACES)

    parent_map = _parent_map(root)
    for tag in ("tab", "ptab"):
        for el in list(root.iter(_qn(f"w:{tag}"))):
            parent = parent_map.get(el)
            if parent is None:
                continue
            t = ET.Element(_qn("w:t"))
            t.set(f"{{{XML_NS}}}space", "preserve")
            t.text = TAB_AS_SPACES
            idx = list(parent).index(el)
            parent.insert(idx, t)
            parent.remove(el)
            n_tab += 1
            parent_map = _parent_map(root)

    # Drop footer references so Word does not keep page-footer association
    for sect in list(root.iter(_qn("w:sectPr"))):
        for el in list(sect):
            if el.tag == _qn("w:footerReference"):
                sect.remove(el)

    math_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    draw_ns = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    n_empty = 0
    parent_map = _parent_map(root)
    for p in list(root.iter(_qn("w:p"))):
        text = "".join((t.text or "") + (t.tail or "") for t in p.iter(_qn("w:t"))).strip()
        has_math = any(True for _ in p.iter(f"{math_ns}oMath"))
        has_draw = any(True for _ in p.iter(f"{draw_ns}inline")) or any(
            True for _ in p.iter("{urn:schemas-microsoft-com:vml}imagedata")
        )
        has_ole = any(True for _ in p.iter(_qn("w:object")))
        has_drawing = any(True for _ in p.iter(_qn("w:drawing")))
        if text or has_math or has_draw or has_ole or has_drawing:
            continue
        parent = parent_map.get(p)
        if parent is None:
            continue
        if parent.tag == _qn("w:tc"):
            paras = [c for c in list(parent) if c.tag == _qn("w:p")]
            if len(paras) <= 1:
                continue
        parent.remove(p)
        n_empty += 1
        parent_map = _parent_map(root)

    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml, n_tab, n_empty
