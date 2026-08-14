#!/usr/bin/env python
"""Top-level CLI shim: python cli.py input.docx -o out.md"""

from word_math_md.cli import app

if __name__ == "__main__":
    app()
