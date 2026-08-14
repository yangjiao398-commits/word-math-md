"""CLI entry: word-math-md input.docx -o output.md --image-dir assets"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from word_math_md.config import CleanLevel, ConvertConfig, MathFallback, MathFormat
from word_math_md.pipeline import convert_batch, convert_docx_to_markdown

app = typer.Typer(
    name="word-math-md",
    help="MathDoc Converter — Word (OMML / MathType / WMF/EMF) → Markdown + LaTeX",
    add_completion=False,
    invoke_without_command=True,
)
console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    input_path: Optional[Path] = typer.Argument(None, help="Input .docx file or directory"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output .md path or directory"),
    image_dir: str = typer.Option("assets", "--image-dir", "-i", help="Image export directory"),
    math_format: MathFormat = typer.Option(MathFormat.LATEX, "--math-format"),
    clean_level: CleanLevel = typer.Option(CleanLevel.AGGRESSIVE, "--clean-level"),
    keep_footnotes: bool = typer.Option(True, "--keep-footnotes/--no-keep-footnotes"),
    remove_textboxes: bool = typer.Option(True, "--remove-textboxes/--keep-textboxes"),
    math_fallback: MathFallback = typer.Option(MathFallback.IMAGE, "--math-fallback"),
    backend: str = typer.Option("auto", "--backend", help="auto | aspose | foss"),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Convert a Word document (or folder) to Markdown."""
    if input_path is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

    if input_path.is_dir():
        out_dir = output or (input_path / "md_out")
        paths = convert_batch(
            input_path,
            out_dir,
            recursive=recursive,
            image_dir_name=image_dir,
            math_format=math_format,
            clean_level=clean_level,
            keep_footnotes=keep_footnotes,
            remove_textboxes=remove_textboxes,
            math_fallback=math_fallback,
            backend=backend,
            debug=debug,
        )
        console.print(f"[green]Converted {len(paths)} file(s) → {out_dir}[/green]")
        return

    if not input_path.exists():
        console.print(f"[red]Not found:[/red] {input_path}")
        raise typer.Exit(1)

    out = output or input_path.with_suffix(".md")
    img_path = Path(image_dir)
    if not img_path.is_absolute():
        img_path = out.parent / image_dir

    cfg = ConvertConfig(
        input_path=input_path,
        output_path=out,
        image_dir=img_path,
        math_format=math_format,
        clean_level=clean_level,
        keep_footnotes=keep_footnotes,
        remove_textboxes=remove_textboxes,
        math_fallback=math_fallback,
        backend=backend,
        debug=debug,
    )
    ir = convert_docx_to_markdown(cfg)
    console.print(f"[green]OK[/green] {out}")
    console.print(f"  formulas: {len(ir.formulas)}  images: {len(ir.images)}")


if __name__ == "__main__":
    app()
