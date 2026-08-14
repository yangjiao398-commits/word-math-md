"""Conversion configuration."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class CleanLevel(str, Enum):
    NONE = "none"
    BASIC = "basic"
    AGGRESSIVE = "aggressive"


class MathFormat(str, Enum):
    LATEX = "latex"
    MATHML = "mathml"
    ASCIIMATH = "asciimath"


class MathFallback(str, Enum):
    IMAGE = "image"  # keep formula screenshot + note
    CODE = "code"  # keep raw text in fenced code
    PLACEHOLDER = "placeholder"


class ConvertConfig(BaseModel):
    input_path: Path
    output_path: Path
    image_dir: Path = Field(default=Path("assets"))
    math_format: MathFormat = MathFormat.LATEX
    clean_level: CleanLevel = CleanLevel.AGGRESSIVE
    keep_footnotes: bool = True
    remove_textboxes: bool = True
    math_fallback: MathFallback = MathFallback.IMAGE
    debug: bool = False
    debug_dir: Optional[Path] = None
    accept_revisions: bool = True
    table_style: str = "pipe"  # pipe | grid
    backend: str = "auto"  # auto | aspose | foss

    def resolve_paths(self) -> "ConvertConfig":
        data = self.model_copy(deep=True)
        data.input_path = data.input_path.resolve()
        data.output_path = data.output_path.resolve()
        if not data.image_dir.is_absolute():
            data.image_dir = (data.output_path.parent / data.image_dir).resolve()
        if data.debug and data.debug_dir is None:
            data.debug_dir = data.output_path.parent / ".debug"
        if data.debug_dir is not None:
            data.debug_dir = data.debug_dir.resolve()
        return data
