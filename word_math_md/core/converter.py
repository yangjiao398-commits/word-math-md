"""Convert cleaned docx (with formula placeholders) to Markdown."""

from __future__ import annotations

import os
import re
from pathlib import Path

import mammoth

from word_math_md.config import ConvertConfig
from word_math_md.core.parser import DocumentIR, ImageRef
from word_math_md.utils.image_handler import collect_hash_pixel_sizes, convert_vector_to_png, sha1_bytes


def _has_aspose() -> bool:
    try:
        import aspose.words  # noqa: F401

        return True
    except ImportError:
        return False


def convert_to_markdown(docx_path: Path, config: ConvertConfig, ir: DocumentIR | None = None) -> DocumentIR:
    if ir is None:
        ir = DocumentIR(source_path=docx_path)

    backend = config.backend
    if backend == "auto":
        backend = "aspose" if _has_aspose() else "foss"

    if backend == "aspose" and _has_aspose():
        ir.raw_markdown = _convert_aspose(docx_path, config)
        return ir

    raw, images = _convert_mammoth(docx_path, config)
    ir.raw_markdown = raw
    for k, v in images.items():
        ir.images.setdefault(k, v)
    return ir


def _convert_aspose(docx_path: Path, config: ConvertConfig) -> str:
    import aspose.words as aw

    lic = Path(__file__).resolve().parents[2] / "Aspose.Words.lic"
    lic_env = os.environ.get("ASPOSE_WORDS_LICENSE")
    if lic_env and Path(lic_env).exists():
        aw.License().set_license(lic_env)
    elif lic.exists():
        aw.License().set_license(str(lic))

    doc = aw.Document(str(docx_path))
    if config.debug and config.debug_dir:
        config.debug_dir.mkdir(parents=True, exist_ok=True)
        out = config.debug_dir / "raw.md"
    else:
        out = docx_path.parent / f".{docx_path.stem}_raw.md"

    options = aw.saving.MarkdownSaveOptions()
    options.images_folder = str(config.image_dir)
    options.images_folder_alias = config.image_dir.name
    doc.save(str(out), options)
    return out.read_text(encoding="utf-8", errors="ignore")


def _convert_mammoth(docx_path: Path, config: ConvertConfig) -> tuple[str, dict[str, ImageRef]]:
    config.image_dir.mkdir(parents=True, exist_ok=True)
    counter = {"n": 1}
    images: dict[str, ImageRef] = {}
    size_by_hash = collect_hash_pixel_sizes(docx_path)

    def convert_image(image):
        content_type = image.content_type or "image/png"
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/x-emf": ".emf",
            "image/emf": ".emf",
            "image/x-wmf": ".wmf",
            "image/wmf": ".wmf",
            "application/x-emf": ".emf",
            "application/x-msmetafile": ".wmf",
        }
        ext = ext_map.get(content_type, ".png")
        image_id = f"{counter['n']:03d}"
        counter["n"] += 1
        with image.open() as f:
            raw = f.read()

        if ext in {".wmf", ".emf"}:
            out_path = config.image_dir / f"glyph{image_id}.png"
            pixel_size = size_by_hash.get(sha1_bytes(raw))
            if not convert_vector_to_png(raw, ext, out_path, pixel_size):
                out_path = config.image_dir / f"glyph{image_id}{ext}"
                out_path.write_bytes(raw)
        else:
            out_path = config.image_dir / f"image{image_id}{ext}"
            out_path.write_bytes(raw)

        images[image_id] = ImageRef(
            image_id=image_id,
            path=out_path,
            original_name=out_path.name,
        )
        rel = f"{config.image_dir.name}/{out_path.name}".replace("\\", "/")
        return {"src": rel}

    with open(docx_path, "rb") as f:
        result = mammoth.convert_to_html(f, convert_image=mammoth.images.img_element(convert_image))

    html = result.value
    md = _html_to_markdown(html)

    if config.debug and config.debug_dir:
        config.debug_dir.mkdir(parents=True, exist_ok=True)
        (config.debug_dir / "raw.html").write_text(html, encoding="utf-8")
        (config.debug_dir / "raw.md").write_text(md, encoding="utf-8")

    return md, images


def _html_to_markdown(html: str) -> str:
    text = html
    for i in range(6, 0, -1):
        text = re.sub(
            rf"<h{i}[^>]*>(.*?)</h{i}>",
            lambda m, level=i: "\n\n" + ("#" * level) + " " + _strip_tags(m.group(1)).strip() + "\n\n",
            text,
            flags=re.I | re.S,
        )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>\s*<p[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.I | re.S)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.I | re.S)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.I | re.S)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.I | re.S)
    text = re.sub(
        r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*/?>',
        r"![\2](\1)",
        text,
        flags=re.I,
    )
    text = re.sub(
        r'<img[^>]*alt="([^"]*)"[^>]*src="([^"]+)"[^>]*/?>',
        r"![\1](\2)",
        text,
        flags=re.I,
    )
    text = re.sub(r'<img[^>]*src="([^"]+)"[^>]*/?>', r"![](\1)", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.I)
    text = re.sub(r"</li>", "", text, flags=re.I)
    text = re.sub(r"</?ul[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</?ol[^>]*>", "\n", text, flags=re.I)
    text = _tables_to_pipe(text)
    text = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.I | re.S)
    text = re.sub(r"<hr\s*/?>", "\n\n---\n\n", text, flags=re.I)
    text = _strip_tags(text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )
    return text


def _tables_to_pipe(html: str) -> str:
    def convert_table(match: re.Match) -> str:
        table_html = match.group(0)
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S)
        md_rows = []
        for i, row in enumerate(rows):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.I | re.S)
            cells = [_strip_tags(c).replace("\n", " ").strip() for c in cells]
            if not cells:
                continue
            md_rows.append("| " + " | ".join(cells) + " |")
            if i == 0:
                md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
        return "\n\n" + "\n".join(md_rows) + "\n\n"

    return re.sub(r"<table[^>]*>.*?</table>", convert_table, html, flags=re.I | re.S)


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)
