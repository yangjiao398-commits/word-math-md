"""Markdown post-processing."""

from __future__ import annotations

import re

from word_math_md.config import ConvertConfig


def postprocess_markdown(markdown: str, config: ConvertConfig) -> str:
    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    # Remove trailing spaces/tabs (but keep two-space markdown line breaks? — strip all for cleanliness)
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))

    # Normalize headings: ensure space after #
    text = re.sub(r"^(#{1,6})([^#\s])", r"\1 \2", text, flags=re.M)

    # Ensure blank line around headings
    text = re.sub(r"([^\n])\n(#{1,6} )", r"\1\n\n\2", text)
    text = re.sub(r"(#{1,6} .+)\n([^\n#])", r"\1\n\n\2", text)

    # Images on their own paragraph
    text = re.sub(r"([^\n])\n(!\[[^\]]*\]\([^)]+\))", r"\1\n\n\2", text)
    text = re.sub(r"(!\[[^\]]*\]\([^)]+\))\n([^\n])", r"\1\n\n\2", text)

    # Collapse 3+ blank lines → 2 (one empty line between blocks)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Avoid escaping $ for math — undo common over-escaping
    text = text.replace("\\$", "$")
    # But keep currency-like rare cases alone; exam papers mostly math

    # Normalize $$ blocks spacing
    text = re.sub(r"\$\$\s*\n\s*", "$$\n", text)
    text = re.sub(r"\s*\n\s*\$\$", "\n$$", text)

    # Footnotes: leave as-is if already markdown style
    if not config.keep_footnotes:
        text = re.sub(r"\[\^[^\]]+\]", "", text)
        text = re.sub(r"^\[\^[^\]]+\]:.*$", "", text, flags=re.M)

    return text.strip() + "\n"
