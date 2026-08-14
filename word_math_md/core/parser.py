"""Intermediate representation and light structural parse."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from word_math_md.config import ConvertConfig


class BlockType(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    FOOTNOTE = "footnote"
    HORIZONTAL_RULE = "hr"
    RAW_HTML = "raw_html"


@dataclass
class FormulaRef:
    formula_id: str
    latex: Optional[str] = None
    display: bool = False
    source: str = "omml"  # omml | mathtype | ocr | unknown
    image_path: Optional[Path] = None
    placeholder: str = ""


@dataclass
class ImageRef:
    image_id: str
    path: Path
    alt: str = ""
    original_name: str = ""


@dataclass
class Block:
    type: BlockType
    text: str = ""
    level: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentIR:
    blocks: list[Block] = field(default_factory=list)
    formulas: dict[str, FormulaRef] = field(default_factory=dict)
    images: dict[str, ImageRef] = field(default_factory=dict)
    footnotes: dict[str, str] = field(default_factory=dict)
    raw_markdown: str = ""
    source_path: Optional[Path] = None


def parse_document(docx_path: Path, config: ConvertConfig) -> DocumentIR:
    """Create an empty IR bound to the source path.

    Heavy lifting (formulas/images) is done in utils + converter; this keeps a
    shared container for the pipeline.
    """
    return DocumentIR(source_path=docx_path)
