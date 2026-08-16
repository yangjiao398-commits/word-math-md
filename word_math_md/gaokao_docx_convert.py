"""Run the gaokao-math-assistant Word→Markdown pipeline (same as the bank button)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONVERT_SCRIPT = ROOT / "gaokao_docx" / "convert.mts"
PARSE_SCRIPT = ROOT / "gaokao_docx" / "parse-md.mts"


def _run_tsx(script: Path, *args: str, timeout: int = 180) -> None:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("未找到 node，无法运行高考数学助理的转换/解析。")
    tsx_cli = ROOT / "node_modules" / "tsx" / "dist" / "cli.mjs"
    if not tsx_cli.is_file():
        raise RuntimeError(
            "未安装 Node 依赖。请在 word-math-md 目录执行 npm install。"
        )
    proc = subprocess.run(
        [node, str(tsx_cli), str(script), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "command failed").strip()
        raise RuntimeError(detail[-2000:] or "命令执行失败")


def convert_docx_like_gaokao(src: Path, dest_md: Path) -> dict:
    """Convert .docx to Markdown with data-URL images; write dest_md and return meta."""
    dest_md.parent.mkdir(parents=True, exist_ok=True)
    _run_tsx(CONVERT_SCRIPT, str(src), str(dest_md))
    meta_path = Path(str(dest_md) + ".meta.json")
    if not dest_md.is_file():
        raise RuntimeError("转换完成但未生成 Markdown 文件")
    meta: dict = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("fileName", dest_md.name)
    meta.setdefault("mathConverted", 0)
    meta.setdefault("imageCount", 0)
    meta.setdefault("warnings", [])
    return meta


def parse_markdown_like_gaokao(src: Path) -> dict:
    """Parse a Markdown paper into questions (same as the bank upload button)."""
    out_json = Path(str(src) + ".parse.json")
    _run_tsx(PARSE_SCRIPT, str(src), str(out_json), timeout=120)
    if not out_json.is_file():
        raise RuntimeError("解析完成但未生成结果")
    data = json.loads(out_json.read_text(encoding="utf-8"))
    data.setdefault("questions", [])
    data.setdefault("notices", [])
    data.setdefault("warnings", [])
    data.setdefault("unresolvedImages", [])
    return data
