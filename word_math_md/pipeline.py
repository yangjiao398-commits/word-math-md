"""End-to-end conversion pipeline."""

from __future__ import annotations

from pathlib import Path

from word_math_md.config import ConvertConfig
from word_math_md.core.cleaner import clean_document
from word_math_md.core.converter import convert_to_markdown
from word_math_md.core.parser import DocumentIR, parse_document
from word_math_md.core.postprocess import postprocess_markdown
from word_math_md.utils.image_handler import extract_and_convert_images, rewrite_markdown_images
from word_math_md.utils.math_handler import apply_formula_placeholders, replace_omml_with_placeholders


def convert_docx_to_markdown(config: ConvertConfig) -> DocumentIR:
    """Run Cleaner → math rewrite → images → Converter → PostProcessor."""
    config = config.resolve_paths()
    if not config.input_path.exists():
        raise FileNotFoundError(f"Input not found: {config.input_path}")
    if config.input_path.suffix.lower() not in {".docx"}:
        raise ValueError("Only .docx is supported in v0.1")

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.image_dir.mkdir(parents=True, exist_ok=True)
    if config.debug and config.debug_dir:
        config.debug_dir.mkdir(parents=True, exist_ok=True)

    # 1) Clean
    cleaned = clean_document(config.input_path, config)

    # 2) Parse IR shell
    ir = parse_document(cleaned, config)

    # 3) Formulas: OMML/MathType → placeholders + latex map
    math_docx, formulas = replace_omml_with_placeholders(cleaned, config)
    ir.formulas = formulas

    # 4) Convert structure → markdown (mammoth/aspose extracts & converts images)
    ir = convert_to_markdown(math_docx, config, ir)

    # 5) If converter produced no images, fall back to zip media extraction
    if not ir.images:
        ir.images.update(extract_and_convert_images(math_docx, config))

    # 6) Apply formula placeholders → $LaTeX$
    md = apply_formula_placeholders(ir.raw_markdown, ir.formulas, config)

    # 7) Normalize image paths
    md = rewrite_markdown_images(md, ir.images, config.image_dir.name)

    # 8) Postprocess
    md = postprocess_markdown(md, config)
    ir.raw_markdown = md

    config.output_path.write_text(md, encoding="utf-8")

    # Cleanup temp files unless debug
    if not config.debug:
        for p in {cleaned, math_docx}:
            if p != config.input_path and p.exists() and p.name.startswith("."):
                try:
                    p.unlink()
                except OSError:
                    pass
        raw_tmp = config.input_path.parent / f".{config.input_path.stem}_raw.md"
        if raw_tmp.exists():
            try:
                raw_tmp.unlink()
            except OSError:
                pass

    return ir


def convert_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    recursive: bool = False,
    image_dir_name: str = "assets",
    **kwargs,
) -> list[Path]:
    """Convert all .docx under input_dir."""
    pattern = "**/*.docx" if recursive else "*.docx"
    outputs: list[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for docx in sorted(input_dir.glob(pattern)):
        if docx.name.startswith("~$"):
            continue
        rel = docx.relative_to(input_dir) if recursive else Path(docx.name)
        out_md = output_dir / rel.with_suffix(".md")
        out_md.parent.mkdir(parents=True, exist_ok=True)
        img_dir = out_md.parent / image_dir_name
        cfg = ConvertConfig(
            input_path=docx,
            output_path=out_md,
            image_dir=img_dir,
            **kwargs,
        )
        convert_docx_to_markdown(cfg)
        outputs.append(out_md)
    return outputs
