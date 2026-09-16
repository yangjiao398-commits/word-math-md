"""FastAPI web service for MathDoc Converter (default port 3010)."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from word_math_md import __version__
from word_math_md.core.cleaner import preprocess_docx
from word_math_md.gaokao_docx_convert import (
    convert_docx_like_gaokao,
    parse_markdown_like_gaokao,
)
from word_math_md.inspect import inspect_docx
from word_math_md.ole_to_latex import convert_ole_docx, format_formula_list
from word_math_md.exam_bank import (
    PAPER_EXAM_TYPES,
    PAPER_SEMESTERS,
    exam_bank_configured,
    get_paper_questions,
    get_questions_by_ids,
    import_markdown_file,
    list_animations_for_codes,
    list_animations_for_question,
    list_knowledge_points,
    list_papers,
    list_questions_by_knowledge,
    questions_to_markdown,
    set_question_knowledge_points,
    sync_geogebra_pep_animations,
    update_paper_meta,
)
from word_math_md.knowledge_catalog import (
    bulk_upsert_catalog,
    create_catalog_item,
    delete_catalog_item,
    list_catalog,
    seed_gaokao_catalog,
    update_catalog_item,
)
from word_math_md.knowledge_page import page_html as knowledge_page_html
from word_math_md.practice_page import page_html as practice_page_html

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "3010"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KATEX_DIR = PROJECT_ROOT / "node_modules" / "katex" / "dist"

app = FastAPI(
    title="MathDoc Converter",
    description="Word (OMML / MathType / WMF/EMF) → Markdown + LaTeX",
    version=__version__,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORK = Path(tempfile.gettempdir()) / "word-math-md-uploads"
WORK.mkdir(parents=True, exist_ok=True)
PREVIEWS = WORK / "previews"
PREVIEWS.mkdir(parents=True, exist_ok=True)

# job_id -> absolute directory containing .md + assets/
_PREVIEW_ROOTS: dict[str, Path] = {}


class Health(BaseModel):
    status: str
    version: str
    port: int


def _safe_job(job: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", job or ""):
        # allow simpler ascii job ids only for URL segment
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", job or ""):
            raise HTTPException(400, "Invalid job id")
    return job


def _register_preview_dir(src_dir: Path, job_id: str | None = None) -> str:
    """Copy/link a folder with .md + assets into PREVIEWS and return job id."""
    src_dir = src_dir.resolve()
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Not a directory: {src_dir}")
    mds = list(src_dir.glob("*.md"))
    if not mds:
        raise FileNotFoundError(f"No .md in {src_dir}")

    job = job_id or f"local_{abs(hash(str(src_dir))) % 10_000_000}"
    dest = PREVIEWS / job
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    # copy md + assets (assets may be large; use copytree)
    for md in mds:
        shutil.copy2(md, dest / md.name)
    assets = src_dir / "assets"
    if assets.is_dir():
        shutil.copytree(assets, dest / "assets")

    _PREVIEW_ROOTS[job] = dest
    return job


def _render_markdown_html(md_text: str, job: str) -> str:
    import markdown as mdlib

    def _img_md(match: re.Match) -> str:
        alt, name = match.group(1), match.group(2)
        url = f"/files/{job}/assets/{name}"
        kind = "formula" if re.match(r"(formula|glyph)\d+\.", name, re.I) else "figure"
        # Use HTML so we can tag formula vs figure images.
        return f'<img class="{kind}" src="{url}" alt="{alt}">'

    md_text = re.sub(r"!\[([^\]]*)\]\(assets/([^)]+)\)", _img_md, md_text)
    html = mdlib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    # markdown may wrap bare <img> and also leave unconverted md images
    html = re.sub(
        r"<img(?![^>]*class=)([^>]*src=\"[^\"]*(?:formula|glyph)[^\"]*\"[^>]*)>",
        r'<img class="formula"\1>',
        html,
        flags=re.I,
    )
    html = re.sub(
        r"<img(?![^>]*class=)([^>]*src=\"[^\"]*/image[^\"]*\"[^>]*)>",
        r'<img class="figure"\1>',
        html,
        flags=re.I,
    )
    return html


def _viewer_html(title: str, body_html: str) -> str:
    from html import escape

    safe_title = escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #f6f3ec;
      --paper: #fffdf8;
      --ink: #1c2430;
      --muted: #5c6b7a;
      --line: #e4ddd0;
      --accent: #1f6feb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; color: var(--ink);
      font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "SimSun", Georgia, serif;
      background:
        radial-gradient(1000px 480px at 0% 0%, #e8f0fa 0%, transparent 55%),
        linear-gradient(180deg, #efe9df, var(--bg));
    }}
    header {{
      position: sticky; top: 0; z-index: 5;
      backdrop-filter: blur(10px);
      background: color-mix(in srgb, var(--bg) 82%, white);
      border-bottom: 1px solid var(--line);
      padding: 12px 20px; display: flex; gap: 16px; align-items: center;
    }}
    header .brand {{ font-family: "Segoe UI", sans-serif; font-weight: 700; color: var(--accent); }}
    header a {{ color: var(--muted); text-decoration: none; font-family: "Segoe UI", sans-serif; font-size: 0.9rem; }}
    header .title {{ color: var(--muted); font-family: "Segoe UI", sans-serif; font-size: 0.9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    main {{
      max-width: 920px; margin: 24px auto 80px; padding: 28px 32px 48px;
      background: var(--paper); border: 1px solid var(--line);
      box-shadow: 0 18px 50px rgba(40, 30, 10, 0.08);
    }}
    #content {{ line-height: 1.75; font-size: 1.05rem; }}
    #content h1, #content h2, #content h3 {{ font-family: "Segoe UI", "PingFang SC", sans-serif; line-height: 1.35; }}
    #content p {{ margin: 0.7em 0; }}
    #content img.formula {{
      height: auto; width: auto;
      max-width: 100%;
      vertical-align: -0.12em;
      margin: 0 0.04em;
      background: #fff;
      display: inline;
    }}
    #content img.figure {{
      max-height: none; max-width: 100%; height: auto;
      display: block; margin: 12px auto;
    }}
    #content strong {{ font-weight: 700; }}
    #content hr {{ border: 0; border-top: 1px solid var(--line); margin: 1.4em 0; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">word-math-md</div>
    <a href="/">← 转换工具</a>
    <span class="title">{safe_title}</span>
  </header>
  <main>
    <div id="content">{body_html}</div>
  </main>
  <script>
    (function () {{
      const imgs = Array.from(document.querySelectorAll('#content img'));
      const ready = imgs.map((img) =>
        img.complete && img.naturalHeight
          ? Promise.resolve()
          : new Promise((res) => {{ img.onload = res; img.onerror = res; }})
      );
      Promise.all(ready).then(() => {{
        imgs.forEach((img) => {{
          const w = img.naturalWidth, h = img.naturalHeight;
          if (!h) return;
          // PNGs are rasterized at 2×; show at Word point size (50%).
          const cssH = Math.max(1, Math.round(h / 2));
          const cssW = Math.max(1, Math.round(w / 2));
          const isFormula = img.classList.contains('formula');
          const isInline = isFormula || (cssH <= 42 && cssW <= 220);
          if (isInline) {{
            img.classList.add('formula');
            img.classList.remove('figure');
            img.style.height = cssH + 'px';
            img.style.width = 'auto';
            img.style.display = 'inline';
          }} else {{
            img.classList.add('figure');
            img.classList.remove('formula');
            img.style.height = 'auto';
            img.style.maxWidth = '100%';
          }}
        }});
      }});
    }})();
  </script>
</body>
</html>"""


@app.get("/view/{job}", response_class=HTMLResponse)
def view_markdown(job: str) -> str:
    job = _safe_job(job)
    root = _PREVIEW_ROOTS.get(job) or (PREVIEWS / job)
    if not root.exists():
        raise HTTPException(404, "Preview not found")
    mds = sorted(root.glob("*.md"))
    if not mds:
        raise HTTPException(404, "No markdown in preview")
    md = mds[0]
    text = md.read_text(encoding="utf-8", errors="ignore")
    body = _render_markdown_html(text, job)
    return _viewer_html(md.stem, body)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>MathDoc Converter</title>
  <style>
    :root {{
      --bg: #0f1419; --panel: #1a222c; --ink: #e8eef5; --muted: #8b9aab;
      --accent: #3d9cf0; --line: #2a3542;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; min-height: 100vh; color: var(--ink);
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(900px 500px at 10% -10%, #1c3a5a 0%, transparent 55%),
        radial-gradient(700px 400px at 100% 0%, #243048 0%, transparent 50%),
        var(--bg);
    }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 48px 20px 80px; }}
    h1 {{ font-size: clamp(1.8rem, 4vw, 2.4rem); letter-spacing: -0.02em; margin: 0 0 8px; font-weight: 650; }}
    .brand {{ color: var(--accent); font-weight: 700; }}
    p.lead {{ color: var(--muted); margin: 0 0 28px; line-height: 1.6; }}
    form {{
      background: color-mix(in srgb, var(--panel) 88%, black);
      border: 1px solid var(--line); border-radius: 14px; padding: 22px;
    }}
    label {{ display: block; font-size: 0.85rem; color: var(--muted); margin: 14px 0 6px; }}
    input[type=file], select, input[type=text] {{
      width: 100%; padding: 10px 12px; border-radius: 8px;
      border: 1px solid var(--line); background: #12181f; color: var(--ink);
    }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .btn-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }}
    #bankForm .btn-row {{ grid-template-columns: 1fr 1fr 1fr; }}
    pre.latex {{
      white-space: pre-wrap; background: #0d1218; border-radius: 8px;
      padding: 10px 12px; margin: 8px 0 14px; color: #d6e4f0;
    }}
    button {{
      width: 100%; padding: 12px 16px; border: 0; border-radius: 10px;
      background: linear-gradient(135deg, #3d9cf0, #2a7fd4); color: white;
      font-weight: 600; font-size: 1rem; cursor: pointer;
    }}
    button.secondary {{
      background: #243140; border: 1px solid var(--line);
    }}
    button:disabled {{ opacity: 0.6; cursor: wait; }}
    #result, #analysis {{
      margin-top: 22px; background: #12181f;
      border: 1px solid var(--line); border-radius: 12px; padding: 16px;
      color: #c5d0dc; font-size: 0.92rem;
    }}
    #result {{ white-space: pre-wrap; min-height: 80px; }}
    #result.paper-view {{ white-space: normal; }}
    table.report {{
      width: 100%; border-collapse: collapse; margin: 10px 0 22px; font-size: 0.86rem;
    }}
    table.report th, table.report td {{
      border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top;
    }}
    table.report th {{ color: #9ecbff; font-weight: 600; }}
    table.report td.num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .yes {{ color: #7dcea0; }}
    .no {{ color: #6b7785; }}
    .tag {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 0.75rem; background: #243140; }}
    .tag.warn {{ background: #3a2a12; color: #f0c674; }}
    h2.sec {{ font-size: 1.05rem; margin: 18px 0 8px; color: var(--ink); }}
    .summary {{ color: #e8eef5; line-height: 1.6; margin-bottom: 8px; }}
    a.dl, p.lead a {{ color: var(--accent); }}
    footer {{ margin-top: 28px; color: var(--muted); font-size: 0.8rem; }}
    #questions {{ margin-top: 22px; }}
    .q-card {{
      background: #12181f; border: 1px solid var(--line); border-radius: 12px;
      padding: 16px; margin-bottom: 14px;
    }}
    .paper-card {{ cursor: default; }}
    .paper-card:hover {{ border-color: var(--accent); }}
    .paper-head {{
      display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
    }}
    .paper-title {{
      flex: 1 1 160px; cursor: pointer; line-height: 1.5;
    }}
    select.paper-meta-btn {{
      width: auto; min-width: 9.5em; padding: 6px 10px;
      font-size: 0.82rem; font-weight: 600; cursor: pointer;
      background: #243140;
    }}
    button.linkish {{
      width: auto; display: inline-block; padding: 8px 14px; margin-bottom: 10px;
      font-size: 0.85rem;
    }}
    .paper-preview-bar {{
      position: sticky; top: 8px; z-index: 15;
      display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
      background: #1a222c; border: 1px solid var(--accent);
      border-radius: 12px; padding: 12px 14px; margin-bottom: 14px;
    }}
    .paper-preview-bar button {{
      width: auto; margin: 0; padding: 10px 18px; font-size: 0.95rem;
    }}
    .print-paper-title {{ font-weight: 650; line-height: 1.5; margin: 0 0 12px; }}
    body.viewing-paper .brand,
    body.viewing-paper h1,
    body.viewing-paper p.lead,
    body.viewing-paper #f,
    body.viewing-paper #bankForm,
    body.viewing-paper #bankStatus,
    body.viewing-paper footer {{
      display: none;
    }}
    body.viewing-paper main {{ padding-top: 20px; }}
    body.viewing-paper #result {{
      min-height: 0; margin-top: 0; margin-bottom: 12px;
    }}
    .kp-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }}
    .kp-row button.linkish {{ margin-bottom: 0; }}
    #kpDialog {{
      position: fixed; inset: 0; z-index: 30;
      display: flex; align-items: center; justify-content: center;
    }}
    #kpDialog[hidden] {{ display: none; }}
    .kp-backdrop {{ position: absolute; inset: 0; background: rgba(0,0,0,0.55); }}
    .kp-panel {{
      position: relative; width: min(720px, 94vw); max-height: 86vh;
      display: flex; flex-direction: column;
      background: #1a222c; border: 1px solid var(--line); border-radius: 14px; padding: 18px 18px 14px;
    }}
    .kp-panel h3 {{ margin: 0 0 10px; font-size: 1.05rem; }}
    .kp-toolbar {{ display: grid; grid-template-columns: 1fr 220px; gap: 8px; margin: 8px 0 10px; }}
    @media (max-width: 700px) {{ .kp-toolbar {{ grid-template-columns: 1fr; }} }}
    .kp-list {{ margin: 0 0 14px; overflow: auto; max-height: 52vh; padding-right: 4px; }}
    .kp-group {{
      color: var(--accent); font-size: 0.82rem; font-weight: 600;
      margin: 12px 0 4px; padding-top: 4px;
    }}
    .kp-item {{
      display: flex; gap: 10px; align-items: flex-start;
      padding: 8px 0; border-bottom: 1px solid var(--line);
    }}
    .kp-item input {{ width: auto; margin-top: 3px; }}
    .kp-item label {{ margin: 0; color: var(--ink); cursor: pointer; }}
    .kp-item .muted {{ color: var(--muted); font-size: 0.82rem; }}
    .kp-actions {{ display: flex; gap: 8px; justify-content: flex-end; align-items: center; }}
    .kp-actions a {{ color: var(--accent); margin-right: auto; font-size: 0.85rem; }}
    .kp-actions button {{ width: auto; padding: 8px 16px; font-size: 0.9rem; }}
    .q-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
    .chip {{
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 0.75rem; background: #243140; color: #c5d0dc;
    }}
    .chip.ok {{ background: #1b3a2a; color: #7dcea0; }}
    .chip.warn {{ background: #3a2a12; color: #f0c674; }}
    .q-card h3 {{ font-size: 0.85rem; color: var(--muted); margin: 0 0 6px; font-weight: 600; }}
    .q-card h4 {{ font-size: 0.85rem; color: var(--accent); margin: 0 0 6px; font-weight: 600; }}
    .q-block {{
      margin-top: 12px; padding: 10px 12px; border-radius: 10px;
      background: #1a222c; border: 1px solid var(--line);
    }}
    .rich-content {{ line-height: 1.75; color: var(--ink); font-size: 0.92rem; }}
    .rich-content img {{
      max-width: 100%; max-height: 12rem; height: auto; display: inline-block;
      vertical-align: middle; border-radius: 6px; border: 1px solid var(--line);
      background: #fff; margin: 4px 0;
    }}
    .rich-content .katex {{ font-size: 1.05em; }}
    .rich-content .katex-display {{ margin: 8px 0; overflow-x: auto; }}
    .rich-content table {{ border-collapse: collapse; width: 100%; font-size: 0.86rem; }}
    .rich-content th, .rich-content td {{
      border: 1px solid var(--line); padding: 6px 8px; text-align: left;
    }}
    @media screen {{
      .print-exam-title, .print-answer-space, .print-q-head {{ display: none; }}
    }}
    @media print {{
      @page {{ size: A4; margin: 16mm; }}
      body.viewing-paper {{
        background: #fff !important;
        color: #111 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }}
      body.viewing-paper .no-print,
      body.viewing-paper .kp-row,
      body.viewing-paper #kpDialog,
      body.viewing-paper #vsDialog,
      body.viewing-paper #result,
      body.viewing-paper .q-meta,
      body.viewing-paper .q-block,
      body.viewing-paper .q-card h3,
      body.viewing-paper .summary,
      body.viewing-paper .print-paper-title,
      body.viewing-paper .paper-preview-bar {{
        display: none !important;
      }}
      body.viewing-paper main {{
        max-width: none; margin: 0; padding: 0;
      }}
      body.viewing-paper #questions {{
        display: block !important;
        background: #fff; border: 0; color: #111;
        margin: 0; padding: 0; min-height: 0;
      }}
      body.viewing-paper .print-exam-title {{
        display: block !important;
        text-align: center;
        font-size: 18pt;
        font-weight: 700;
        margin: 0 0 12mm;
        color: #111;
      }}
      body.viewing-paper .print-q-head {{
        display: block !important;
        font-weight: 700;
        margin: 0 0 2mm;
        color: #111;
      }}
      body.viewing-paper .q-card {{
        background: #fff; border: 0; border-radius: 0;
        padding: 0; margin: 0 0 8mm; color: #111;
        box-shadow: none;
      }}
      body.viewing-paper .print-stem {{
        color: #111; line-height: 1.65;
      }}
      body.viewing-paper .print-stem img,
      body.viewing-paper .rich-content img {{
        max-width: 100% !important;
        max-height: none !important;
        height: auto !important;
        display: block;
        background: #fff;
        border: 0;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      body.viewing-paper .print-answer-space {{
        display: block !important;
        height: 148.5mm;
      }}
      body.viewing-paper #vsDialog {{
        display: none !important;
      }}
    }}
  </style>
  <link rel="stylesheet" href="/vendor/katex/katex.min.css"/>
  <link rel="stylesheet" href="/static/visual-solve.css"/>
</head>
<body>
  <main>
    <div class="brand no-print">word-math-md</div>
    <h1 class="no-print">MathDoc Converter</h1>
    <p class="lead no-print">「word转换md文件」与高考数学助理「选择 Word 并转换为 Markdown」同一套流水线：OMML→LaTeX、mammoth、选项公式修复；图片以 data URL 嵌入并下载 .md。服务端口 {PORT}。独立模块：<a href="/knowledge">维护知识点</a> · <a href="/practice">知识点专项训练</a>。</p>
    <form id="f" class="no-print">
      <label>Word 文件 (.docx)</label>
      <input type="file" name="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required />
      <div class="btn-row">
        <button type="button" class="secondary" id="btnInspect">分析公式与文档结构</button>
        <button type="button" class="secondary" id="btnOle">OLE公式转Latex</button>
        <button type="button" class="secondary" id="btnPreprocess">格式预处理（word元素处理）</button>
        <button type="submit" id="btn">word转换md文件</button>
        <button type="button" class="secondary" id="btnParseMd">上传markdown并显示题目</button>
      </div>
      <input type="file" id="oleFile" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden />
    </form>
    <form id="bankForm" class="no-print" style="margin-top:16px">
      <label>试卷编号（导入题库用，可空则用文件名）</label>
      <input type="text" id="paperCode" placeholder="如 SZ-G1-2024-QM-01" />
      <label>试卷名称</label>
      <input type="text" id="paperTitle" placeholder="如 2024学年高一上学期期末数学" />
      <div class="btn-row">
        <button type="button" class="secondary" id="btnImportMd">导入 Markdown 到题库</button>
        <button type="button" class="secondary" id="btnListPapers">查看已入库试卷</button>
        <button type="button" class="secondary" id="btnKpAdmin">维护知识点</button>
        <button type="button" class="secondary" id="btnPractice">知识点专项训练</button>
      </div>
    </form>
    <input type="file" id="mdFile" accept=".md,.markdown,.mdown,text/markdown,text/plain" hidden />
    <input type="file" id="importMdFile" accept=".md,.markdown,.mdown,text/markdown,text/plain" hidden />
    <p id="bankStatus" class="lead no-print"></p>
    <div id="result">选择 .docx 后可转换或分析。点「上传markdown并显示题目」可预览；「导入 Markdown 到题库」会按题号写入 Supabase。</div>
    <div id="analysis" class="no-print" hidden></div>
    <div id="questions" hidden></div>
    <div id="vsDialog" hidden>
      <div class="vs-backdrop" id="vsBackdrop"></div>
      <div class="vs-panel" role="dialog" aria-labelledby="vsTitle">
        <div class="vs-head">
          <div>
            <h3 id="vsTitle">可视化解题</h3>
            <p class="muted" id="vsSub">动画演示本题的审题、建模与求解思路。</p>
          </div>
          <button type="button" class="vs-close secondary" id="vsClose">关闭</button>
        </div>
        <div class="vs-layout">
          <ul class="vs-phases" id="vsPhases"></ul>
          <div class="vs-stage">
            <svg id="vsCanvas" viewBox="0 0 720 340" role="img" aria-label="解题思路动画"></svg>
          </div>
        </div>
        <div class="vs-step" id="vsStep"></div>
        <div class="vs-controls">
          <button type="button" class="secondary" id="vsPrev">上一步</button>
          <button type="button" id="vsPlay">播放</button>
          <button type="button" class="secondary" id="vsNext">下一步</button>
          <button type="button" class="secondary" id="vsReplay">重播</button>
          <div class="vs-progress"><i id="vsBar"></i></div>
          <span class="vs-count" id="vsCount">0 / 0</span>
        </div>
      </div>
    </div>
    <div id="kpDialog" hidden>
      <div class="kp-backdrop" id="kpBackdrop"></div>
      <div class="kp-panel" role="dialog" aria-labelledby="kpTitle">
        <h3 id="kpTitle">相关知识点</h3>
        <p class="summary" id="kpHint">从课标知识点中多选，可按学期或关键词筛选。</p>
        <div class="kp-toolbar">
          <input type="text" id="kpFilter" placeholder="搜索编号、大类或小类" />
          <select id="kpSemester">
            <option value="">全部学期</option>
          </select>
        </div>
        <div class="kp-list" id="kpList"></div>
        <div class="kp-actions">
          <a href="/knowledge" target="_blank" rel="noopener">维护知识点</a>
          <button type="button" class="secondary" id="kpCancel">取消</button>
          <button type="button" id="kpSave">保存</button>
        </div>
      </div>
    </div>
    <footer class="no-print">API: POST /api/convert · POST /api/parse-markdown · POST /api/exam-bank/import-markdown · GET /api/exam-bank/papers · GET /api/exam-bank/knowledge-points · v{__version__}</footer>
  </main>
  <script>
    const f = document.getElementById('f');
    const result = document.getElementById('result');
    const analysis = document.getElementById('analysis');
    const btn = document.getElementById('btn');
    const btnInspect = document.getElementById('btnInspect');
    const btnPreprocess = document.getElementById('btnPreprocess');
    const btnOle = document.getElementById('btnOle');
    const btnParseMd = document.getElementById('btnParseMd');
    const btnImportMd = document.getElementById('btnImportMd');
    const btnListPapers = document.getElementById('btnListPapers');
    const btnKpAdmin = document.getElementById('btnKpAdmin');
    if (btnKpAdmin) btnKpAdmin.addEventListener('click', () => {{ location.href = '/knowledge'; }});
    const btnPractice = document.getElementById('btnPractice');
    if (btnPractice) btnPractice.addEventListener('click', () => {{ location.href = '/practice'; }});
    const oleFile = document.getElementById('oleFile');
    const mdFile = document.getElementById('mdFile');
    const importMdFile = document.getElementById('importMdFile');
    const questions = document.getElementById('questions');
    function esc(s) {{
      return String(s ?? '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
    }}
    const PAPER_SEMESTERS = {json.dumps(list(PAPER_SEMESTERS), ensure_ascii=False)};
    const PAPER_EXAM_TYPES = {json.dumps(list(PAPER_EXAM_TYPES), ensure_ascii=False)};
    function paperMetaSelect(paperId, field, values, current, placeholder) {{
      return '<select class="paper-meta-btn" data-paper-meta data-paper-id="' + esc(paperId) +
        '" data-field="' + esc(field) + '">' +
        '<option value="">' + esc(placeholder) + '</option>' +
        values.map(v => '<option value="' + esc(v) + '"' +
          (v === current ? ' selected' : '') + '>' + esc(v) + '</option>').join('') +
        '</select>';
    }}
    async function readJson(res) {{
      const raw = await res.text();
      try {{ return JSON.parse(raw); }}
      catch (e) {{
        throw new Error('接口未返回 JSON，请确认打开的是 http://127.0.0.1:3010 （word-math-md）。' + raw.slice(0, 120));
      }}
    }}
    (async () => {{
      const el = document.getElementById('bankStatus');
      try {{
        const res = await fetch('/api/exam-bank/status');
        const data = await readJson(res);
        if (data.configured) {{
          el.textContent = '题库已连接 Supabase，可直接导入 Markdown。';
        }} else {{
          el.textContent = '题库未连接：请确认项目根目录 .env 已填写 SUPABASE_URL 与 SUPABASE_SERVICE_ROLE_KEY，然后重启 3010。';
        }}
      }} catch (err) {{
        el.textContent = '无法检查题库状态。';
      }}
    }})();
    function table(headers, rows, rowFn) {{
      return '<table class="report"><thead><tr>' +
        headers.map(h => '<th>' + esc(h) + '</th>').join('') +
        '</tr></thead><tbody>' + rows.map(rowFn).join('') + '</tbody></table>';
    }}
    f.addEventListener('submit', async (e) => {{
      e.preventDefault();
      const fileInput = f.querySelector('input[name=file]');
      if (!fileInput.files || !fileInput.files[0]) {{
        result.textContent = '请先选择一个 .docx 文件。';
        return;
      }}
      btn.disabled = true; result.textContent = '正在转换…';
      const fd = new FormData();
      fd.append('file', fileInput.files[0]);
      try {{
        const res = await fetch('/api/convert', {{ method: 'POST', body: fd }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        if (data.download_url) {{
          const a = document.createElement('a');
          a.href = data.download_url;
          a.download = data.file_name || 'converted.md';
          document.body.appendChild(a);
          a.click();
          a.remove();
        }}
        let html = '已将 Word 转换为 Markdown，并开始下载：' + esc(data.file_name) + '\\n';
        if (data.math_converted > 0) {{
          html += '其中转换了 ' + data.math_converted + ' 处公式为 LaTeX。\\n';
        }}
        if (data.image_count > 0) {{
          html += '已嵌入 ' + data.image_count + ' 张图片（data URL），打开该 md 即可显示配图。\\n';
        }}
        (data.warnings || []).forEach(w => {{ html += esc(w) + '\\n'; }});
        html += '\\n<a class="dl" href="' + data.download_url + '">再次下载 Markdown</a>';
        if (data.view_url) {{
          html += '\\n<a class="dl" href="' + data.view_url + '">在网页中查看 Markdown</a>';
        }}
        if (data.preview) {{
          html += '\\n\\n<details><summary>文本预览</summary><pre>' + esc(data.preview) + '</pre></details>';
        }}
        result.innerHTML = html;
      }} catch (err) {{
        result.textContent = '错误: ' + err.message;
      }} finally {{
        btn.disabled = false;
      }}
    }});
    btnInspect.addEventListener('click', async () => {{
      const fileInput = f.querySelector('input[type=file]');
      if (!fileInput.files || !fileInput.files[0]) {{
        result.textContent = '请先选择一个 .docx 文件。';
        return;
      }}
      btnInspect.disabled = true;
      analysis.hidden = false;
      analysis.textContent = '正在分析文档…';
      const fd = new FormData();
      fd.append('file', fileInput.files[0]);
      try {{
        const res = await fetch('/api/inspect', {{ method: 'POST', body: fd }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const mathRows = (data.math.types || []);
        const oleRows = (data.math.ole_by_progid || []);
        const stRows = (data.structure.rows || []);
        const impact = (data.impact || []);
        const mediaExt = Object.entries(data.media.by_ext || {{}});
        let html = '<p class="summary"><strong>' + esc(data.file_name) + '</strong> · ' +
          Math.round((data.file_size||0)/1024) + ' KB<br>' + esc(data.summary) + '</p>';
        html += '<h2 class="sec">1. 数学公式类型</h2>';
        html += table(['类型','是否存在','数量','存储方式','对本工具转换的影响','证据'], mathRows, r =>
          '<tr><td>' + esc(r.label) + '</td><td class="' + (r.present?'yes':'no') + '">' +
          (r.present?'有':'无') + '</td><td class="num">' + r.count + '</td><td>' +
          esc(r.how_stored) + '</td><td>' + esc(r.convert_path) + '</td><td>' + esc(r.evidence) + '</td></tr>');
        if (oleRows.length) {{
          html += '<h2 class="sec">OLE ProgID 明细</h2>';
          html += table(['ProgID','含义','数量'], oleRows, r =>
            '<tr><td>' + esc(r.prog_id) + '</td><td>' + esc(r.label) + '</td><td class="num">' + r.count + '</td></tr>');
        }}
        html += '<h2 class="sec">2. 会影响 Markdown 转换的文档元素</h2>';
        html += table(['元素','是否存在','数量','检测细节','转换影响'], stRows, r =>
          '<tr><td>' + esc(r.name) + '</td><td class="' + (r.present?'yes':'no') + '">' +
          esc(r.status) + '</td><td class="num">' + r.count + '</td><td>' + esc(r.detail) +
          '</td><td>' + esc(r.impact) + '</td></tr>');
        html += '<h2 class="sec">3. 媒体文件</h2>';
        html += table(['扩展名','数量'], mediaExt, r =>
          '<tr><td>' + esc(r[0]) + '</td><td class="num">' + r[1] + '</td></tr>');
        if (impact.length) {{
          html += '<h2 class="sec">4. 转换风险摘要</h2>';
          html += table(['级别','项目','说明'], impact, r =>
            '<tr><td><span class="tag warn">' + esc(r.level) + '</span></td><td>' +
            esc(r.item) + '</td><td>' + esc(r.note) + '</td></tr>');
        }}
        analysis.innerHTML = html;
        result.textContent = '分析完成，见下方表格。';
      }} catch (err) {{
        analysis.textContent = '分析失败: ' + err.message;
      }} finally {{
        btnInspect.disabled = false;
      }}
    }});
    btnPreprocess.addEventListener('click', async () => {{
      const fileInput = f.querySelector('input[type=file]');
      if (!fileInput.files || !fileInput.files[0]) {{
        result.textContent = '请先选择一个 .docx 文件。';
        return;
      }}
      btnPreprocess.disabled = true;
      result.textContent = '正在预处理：Tab → 空格，删除页脚，删除空段落…';
      const fd = new FormData();
      fd.append('file', fileInput.files[0]);
      try {{
        const res = await fetch('/api/preprocess', {{ method: 'POST', body: fd }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const s = data.stats || {{}};
        result.innerHTML =
          '预处理完成\\n' +
          'Tab 替换: ' + (s.tabs_replaced || 0) + ' · 页脚清除: ' + (s.footers_cleared || 0) +
          ' · 空段落删除: ' + (s.empty_paragraphs_removed || 0) + '\\n\\n' +
          '<a class="dl" href="' + data.download_url + '">下载预处理后的 Word（.docx）</a>\\n' +
          '可用该文件继续「分析」或「转换」。';
      }} catch (err) {{
        result.textContent = '预处理失败: ' + err.message;
      }} finally {{
        btnPreprocess.disabled = false;
      }}
    }});
    async function runOleConvert(file) {{
      btnOle.disabled = true;
      analysis.hidden = false;
      analysis.textContent = '';
      result.textContent = '正在从 OLE 对象提取 MathML 并转换为 LaTeX…';
      const fd = new FormData();
      fd.append('file', file);
      try {{
        const res = await fetch('/api/ole-to-latex', {{ method: 'POST', body: fd }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const items = data.formulas || [];
        result.innerHTML =
          'OLE 公式转换完成（源文件未修改）\\n' +
          '文件: ' + esc(data.file_name) + ' · 共 ' + items.length + ' 个 OLE 公式\\n\\n' +
          (data.docx_url
            ? '<a class="dl" href="' + data.docx_url + '">下载转换后的 Word（.docx）</a>\\n'
            : '') +
          (data.download_url
            ? '<a class="dl" href="' + data.download_url + '">下载公式输出清单.txt</a>'
            : '');
        if (!items.length) {{
          analysis.innerHTML = '<p class="summary">文档中没有找到 MathType / Equation OLE 对象。</p>';
          return;
        }}
        let html = '<p class="summary">共提取 <strong>' + items.length + '</strong> 个 OLE 公式</p>';
        items.forEach((item, i) => {{
          html += '<h2 class="sec">公式 ' + (i + 1) +
            (item.source ? ' · ' + esc(item.source) : '') + '</h2>';
          html += '<pre class="latex">$' + esc(item.latex || '') + '$</pre>';
        }});
        analysis.innerHTML = html;
      }} catch (err) {{
        result.textContent = 'OLE 转换失败: ' + err.message;
      }} finally {{
        btnOle.disabled = false;
      }}
    }}
    btnOle.addEventListener('click', async () => {{
      const fileInput = f.querySelector('input[name=file]');
      if (fileInput.files && fileInput.files[0]) {{
        await runOleConvert(fileInput.files[0]);
        return;
      }}
      oleFile.value = '';
      oleFile.click();
    }});
    oleFile.addEventListener('change', async () => {{
      if (oleFile.files && oleFile.files[0]) {{
        await runOleConvert(oleFile.files[0]);
      }}
    }});
    let lastPreviewData = null;
    function kpChips(items) {{
      return (items || []).map(kp => {{
        const label = kp.minor_category || kp.major_category || kp.description || '';
        return '<span class="chip">' + esc(kp.code) +
          (label ? ' ' + esc(label) : '') + '</span>';
      }}).join('');
    }}
    function examPrintTitle(paper) {{
      const raw = String((paper && (paper.title || paper.source_filename || paper.paper_code)) || '试卷');
      const cut = raw.split(/[（(]解析版[）)]/)[0]
        .replace(/\\.(?:ole-latex|preprocessed).*$/i, '')
        .replace(/[.\\s]+$/g, '')
        .trim();
      return cut || raw.trim() || '试卷';
    }}
    function questionTypeCode(q) {{
      if (q && q.type_code) return q.type_code;
      const html = String((q && q.stemHtml) || '');
      const text = String((q && q.stemText) || '') + html;
      if (/(?:^|>|\\s)A[\\.．、)]/.test(html) && /(?:^|>|\\s)B[\\.．、)]/.test(html)) {{
        return /多选/.test(text) ? 'multi_choice' : 'single_choice';
      }}
      if (/_{3,}|(?:\\\\_){{3,}}|填空/.test(text)) return 'fill_blank';
      return 'solution';
    }}
    function eagerImages(html) {{
      return String(html || '').replace(/<img\\b([^>]*)>/gi, function(_, attrs) {{
        var a = String(attrs || '');
        a = a.replace(/\\sloading\\s*=\\s*(['"][^'"]*['"])/gi, '');
        a = a.replace(/\\sdecoding\\s*=\\s*(['"][^'"]*['"])/gi, '');
        return '<img loading="eager" decoding="sync"' + a + '>';
      }});
    }}
    function waitForPrintImages() {{
      const imgs = Array.from(document.querySelectorAll('.print-stem img'));
      return Promise.all(imgs.map(function(img) {{
        img.loading = 'eager';
        if (img.complete) return Promise.resolve();
        return new Promise(function(resolve) {{
          const done = function() {{ resolve(); }};
          img.addEventListener('load', done, {{ once: true }});
          img.addEventListener('error', done, {{ once: true }});
        }});
      }}));
    }}
    function renderQuestions(data, paper) {{
      lastPreviewData = data;
      const qs = data.questions || [];
      const notices = data.notices || [];
      let html = '';
      if (paper) {{
        const metaBits = [paper.semester, paper.exam_type].filter(Boolean).join(' · ');
        const heading = esc(paper.title || paper.paper_code || '试卷') +
          (paper.paper_code ? ' · 编号 ' + esc(paper.paper_code) : '') +
          (metaBits ? ' · ' + esc(metaBits) : '') +
          ' · 共 ' + qs.length + ' 题';
        html += '<div class="paper-preview-bar no-print" id="paperPreviewBar">' +
          '<button type="button" class="secondary" id="btnBackPapers">返回试卷列表</button>' +
          '<button type="button" id="btnPrintPaper">打印试卷</button>' +
          '</div>';
        html += '<div class="print-paper-title no-print">' + heading + '</div>';
        html += '<h1 class="print-exam-title">' + esc(examPrintTitle(paper)) + '</h1>';
      }}
      html += notices.map(n => '<p class="summary">' + esc(n.text) + '</p>').join('');
      if (!qs.length) {{
        html += '<p>未能解析出题目，请检查题号与【答案】【分析】【详解】标记。</p>';
        questions.innerHTML = html;
        questions.hidden = false;
        return;
      }}
      html += qs.map((q, qi) => {{
        let card = '<article class="q-card"><div class="q-meta">';
        card += '<span class="chip">第 ' + esc(q.index) + ' 题</span>';
        card += q.answerHtml ? '<span class="chip ok">含答案</span>' : '<span class="chip warn">缺答案</span>';
        if (q.analysisHtml) card += '<span class="chip">含分析</span>';
        if (q.detailHtml) card += '<span class="chip">含详解</span>';
        card += '</div><h3 class="no-print">题干</h3>';
        card += '<div class="print-q-head">' + esc(q.index) + '.</div>';
        card += '<div class="rich-content print-stem">' + eagerImages(q.stemHtml || '') + '</div>';
        if (questionTypeCode(q) === 'solution') {{
          card += '<div class="print-answer-space"></div>';
        }}
        if (q.answerHtml) {{
          card += '<div class="q-block"><h4>【答案】</h4><div class="rich-content">' + q.answerHtml + '</div></div>';
        }}
        if (q.analysisHtml) {{
          card += '<div class="q-block"><h4>【分析】</h4><div class="rich-content">' + q.analysisHtml + '</div></div>';
        }}
        if (q.detailHtml) {{
          card += '<div class="q-block"><h4>【详解】</h4><div class="rich-content">' + q.detailHtml + '</div></div>';
        }}
        if (q.question_id) {{
          card += '<div class="q-block kp-row">';
          card += '<button type="button" class="secondary linkish" data-kp-btn data-question-id="' +
            esc(q.question_id) + '">相关知识点</button>';
          card += '<span data-kp-list="' + esc(q.question_id) + '">' + kpChips(q.knowledge_points) + '</span>';
          card += '</div>';
        }}
        if (paper) {{
          card += '<div class="q-block vs-row no-print">';
          card += '<button type="button" class="vs-open" data-vs-index="' + qi +
            '">可视化解题</button>';
          card += '<span class="muted">动画演示审题、建模与求解思路</span>';
          card += '</div>';
        }}
        card += '</article>';
        return card;
      }}).join('');
      questions.innerHTML = html;
      questions.hidden = false;
    }}
    async function runParseMarkdown(file) {{
      btnParseMd.disabled = true;
      analysis.innerHTML = '';
      analysis.hidden = true;
      questions.hidden = false;
      questions.innerHTML = '';
      result.textContent = '正在解析 Markdown 并渲染题目…';
      const fd = new FormData();
      fd.append('file', file);
      try {{
        const res = await fetch('/api/parse-markdown', {{ method: 'POST', body: fd }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        result.textContent = '已解析 ' + esc(data.file_name) + '，识别到 ' +
          (data.questions || []).length + ' 题。';
        renderQuestions(data);
      }} catch (err) {{
        result.textContent = '解析失败: ' + err.message;
        questions.innerHTML = '';
      }} finally {{
        btnParseMd.disabled = false;
      }}
    }}
    btnParseMd.addEventListener('click', () => {{
      mdFile.value = '';
      mdFile.click();
    }});
    mdFile.addEventListener('change', async () => {{
      if (mdFile.files && mdFile.files[0]) {{
        await runParseMarkdown(mdFile.files[0]);
      }}
    }});
    async function runImportMarkdown(file) {{
      btnImportMd.disabled = true;
      questions.hidden = true;
      result.textContent = '正在解析并写入 Supabase 题库…';
      const fd = new FormData();
      fd.append('file', file);
      const code = document.getElementById('paperCode').value.trim();
      const title = document.getElementById('paperTitle').value.trim();
      if (code) fd.append('paper_code', code);
      if (title) fd.append('paper_title', title);
      try {{
        const res = await fetch('/api/exam-bank/import-markdown', {{ method: 'POST', body: fd }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const qs = data.questions || [];
        result.textContent =
          (data.replaced ? '已覆盖同编号试卷。\\n' : '已新建试卷。\\n') +
          '编号: ' + esc(data.paper_code) + '\\n名称: ' + esc(data.title) +
          '\\n题目: ' + data.question_count + ' · 图片: ' + data.asset_count;
        let html = qs.map(q => {{
          return '<article class="q-card"><div class="q-meta">' +
            '<span class="chip">第 ' + esc(q.question_no) + ' 题</span>' +
            '<span class="chip">' + esc(q.type_code) + '</span>' +
            (q.score != null ? '<span class="chip">' + esc(q.score) + ' 分</span>' : '') +
            '<span class="chip">选项 ' + esc(q.option_count) + '</span>' +
            ((q.knowledge_codes || []).map(code =>
              '<span class="chip">' + esc(code) + '</span>'
            ).join('')) +
            '</div></article>';
        }}).join('');
        questions.innerHTML = html || '';
        questions.hidden = !html;
      }} catch (err) {{
        result.textContent = '入库失败: ' + err.message;
      }} finally {{
        btnImportMd.disabled = false;
      }}
    }}
    btnImportMd.addEventListener('click', () => {{
      importMdFile.value = '';
      importMdFile.click();
    }});
    importMdFile.addEventListener('change', async () => {{
      if (importMdFile.files && importMdFile.files[0]) {{
        await runImportMarkdown(importMdFile.files[0]);
      }}
    }});
    btnListPapers.addEventListener('click', async () => {{
      document.body.classList.remove('viewing-paper');
      result.classList.remove('paper-view');
      btnListPapers.disabled = true;
      try {{
        const res = await fetch('/api/exam-bank/papers');
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const rows = data.papers || [];
        result.textContent = '题库中共 ' + rows.length + ' 套试卷。';
        questions.innerHTML = rows.map(p =>
          '<article class="q-card paper-card">' +
          '<div class="q-meta">' +
          '<span class="chip">' + esc(p.paper_code) + '</span>' +
          '<span class="chip">题目 ' + esc(p.question_count) + '</span>' +
          '<span class="chip">点击名称查看</span></div>' +
          '<div class="paper-head">' +
          '<div class="paper-title rich-content" data-paper-id="' + esc(p.id) +
          '" role="button" tabindex="0">' + esc(p.title) + '</div>' +
          paperMetaSelect(p.id, 'semester', PAPER_SEMESTERS, p.semester || '', '选择学期') +
          paperMetaSelect(p.id, 'exam_type', PAPER_EXAM_TYPES, p.exam_type || '', '选择考试类型') +
          '</div></article>'
        ).join('') || '<p>题库还是空的。</p>';
        questions.hidden = false;
      }} catch (err) {{
        result.textContent = '读取题库失败: ' + err.message;
      }} finally {{
        btnListPapers.disabled = false;
      }}
    }});
    async function openBankPaper(paperId) {{
      btnListPapers.disabled = true;
      analysis.innerHTML = '';
      analysis.hidden = true;
      result.textContent = '正在读取试卷并渲染题目…';
      try {{
        const res = await fetch('/api/exam-bank/papers/' + encodeURIComponent(paperId) + '/preview');
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const paper = data.paper || {{}};
        document.body.classList.add('viewing-paper');
        result.classList.remove('paper-view');
        result.textContent = '已打开试卷，可在题目上方使用「打印试卷」。';
        renderQuestions(data, paper);
        const bar = document.getElementById('paperPreviewBar');
        if (bar) bar.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }} catch (err) {{
        document.body.classList.remove('viewing-paper');
        result.classList.remove('paper-view');
        result.textContent = '读取试卷失败: ' + err.message;
        questions.innerHTML = '';
      }} finally {{
        btnListPapers.disabled = false;
      }}
    }}
    questions.addEventListener('click', (ev) => {{
      const printBtn = ev.target.closest('#btnPrintPaper');
      if (printBtn && questions.contains(printBtn)) {{
        ev.preventDefault();
        ev.stopPropagation();
        printBtn.disabled = true;
        waitForPrintImages().finally(function() {{
          printBtn.disabled = false;
          window.print();
        }});
        return;
      }}
      const backBtn = ev.target.closest('#btnBackPapers');
      if (backBtn && questions.contains(backBtn)) {{
        ev.preventDefault();
        ev.stopPropagation();
        btnListPapers.click();
        return;
      }}
      const vsBtn = ev.target.closest('[data-vs-index]');
      if (vsBtn && questions.contains(vsBtn)) {{
        ev.preventDefault();
        ev.stopPropagation();
        const idx = Number(vsBtn.getAttribute('data-vs-index'));
        const q = ((lastPreviewData && lastPreviewData.questions) || [])[idx];
        if (q && window.VisualSolve) window.VisualSolve.open(q);
        return;
      }}
      const kpBtn = ev.target.closest('[data-kp-btn]');
      if (kpBtn && questions.contains(kpBtn)) {{
        ev.preventDefault();
        ev.stopPropagation();
        openKpDialog(kpBtn.getAttribute('data-question-id'));
        return;
      }}
      if (ev.target.closest('[data-paper-meta]')) return;
      const title = ev.target.closest('.paper-title[data-paper-id]');
      if (!title || !questions.contains(title)) return;
      openBankPaper(title.getAttribute('data-paper-id'));
    }});
    questions.addEventListener('keydown', (ev) => {{
      if (ev.target.closest('[data-paper-meta]')) return;
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      const title = ev.target.closest('.paper-title[data-paper-id]');
      if (!title || !questions.contains(title)) return;
      ev.preventDefault();
      openBankPaper(title.getAttribute('data-paper-id'));
    }});
    questions.addEventListener('change', async (ev) => {{
      const sel = ev.target.closest('select[data-paper-meta]');
      if (!sel || !questions.contains(sel)) return;
      const paperId = sel.getAttribute('data-paper-id');
      const field = sel.getAttribute('data-field');
      const value = sel.value;
      const body = {{}};
      body[field] = value;
      sel.disabled = true;
      try {{
        const res = await fetch('/api/exam-bank/papers/' + encodeURIComponent(paperId), {{
          method: 'PATCH',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(body),
        }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const label = field === 'semester' ? '学期' : '考试类型';
        result.textContent = '已保存' + label + '：' + (value || '未选');
      }} catch (err) {{
        result.textContent = '保存试卷属性失败: ' + err.message;
      }} finally {{
        sel.disabled = false;
      }}
    }});
    const kpDialog = document.getElementById('kpDialog');
    const kpList = document.getElementById('kpList');
    const kpFilter = document.getElementById('kpFilter');
    const kpSemester = document.getElementById('kpSemester');
    let kpQuestionId = '';
    let kpCatalog = [];
    let kpSelected = new Set();
    function updateKpHint() {{
      document.getElementById('kpHint').textContent =
        '已选 ' + kpSelected.size + ' 个。从课标知识点中勾选，可多选。';
    }}
    function fillSemesterOptions() {{
      const current = kpSemester.value;
      const sems = [...new Set(kpCatalog.map(item => item.semester).filter(Boolean))];
      kpSemester.innerHTML = '<option value="">全部学期</option>' +
        sems.map(s => '<option value="' + esc(s) + '">' + esc(s) + '</option>').join('');
      if ([...kpSemester.options].some(opt => opt.value === current)) kpSemester.value = current;
    }}
    function visibleCatalog() {{
      const q = (kpFilter.value || '').trim().toLowerCase();
      const sem = kpSemester.value;
      return kpCatalog.filter(item => {{
        if (sem && item.semester !== sem) return false;
        if (!q) return true;
        const blob = [item.code, item.semester, item.major_category, item.minor_category, item.description]
          .join(' ').toLowerCase();
        return blob.includes(q);
      }});
    }}
    function renderKpList() {{
      updateKpHint();
      if (!kpCatalog.length) {{
        kpList.innerHTML = '<p class="summary">知识点字典为空，请先到 <a href="/knowledge">维护页</a> 导入课标。</p>';
        return;
      }}
      const shown = visibleCatalog();
      if (!shown.length) {{
        kpList.innerHTML = '<p class="summary">没有匹配的知识点。</p>';
        return;
      }}
      let html = '';
      let lastSem = null;
      shown.forEach(item => {{
        if (item.semester !== lastSem) {{
          lastSem = item.semester;
          html += '<div class="kp-group">' + esc(item.semester || '未分学期') + '</div>';
        }}
        const id = 'kp-' + esc(item.code);
        html += '<div class="kp-item"><input type="checkbox" id="' + id + '" value="' +
          esc(item.code) + '"' + (kpSelected.has(item.code) ? ' checked' : '') +
          ' /><label for="' + id + '"><strong>' + esc(item.code) + '</strong>' +
          '<div class="muted">' +
          esc([item.major_category, item.minor_category || item.description].filter(Boolean).join(' · ')) +
          '</div></label></div>';
      }});
      kpList.innerHTML = html;
    }}
    function closeKpDialog() {{
      kpDialog.hidden = true;
      kpQuestionId = '';
    }}
    async function openKpDialog(questionId) {{
      kpQuestionId = questionId;
      kpDialog.hidden = false;
      kpFilter.value = '';
      kpSemester.value = '';
      kpList.innerHTML = '<p class="summary">正在从 knowledge_points 加载…</p>';
      const current = ((lastPreviewData && lastPreviewData.questions) || [])
        .find(q => q.question_id === questionId);
      kpSelected = new Set((current && current.knowledge_points || []).map(k => k.code));
      try {{
        const res = await fetch('/api/exam-bank/knowledge-points');
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        kpCatalog = data.knowledge_points || [];
        fillSemesterOptions();
        renderKpList();
      }} catch (err) {{
        kpList.innerHTML = '<p class="summary">加载失败: ' + esc(err.message) + '</p>';
      }}
    }}
    document.getElementById('kpBackdrop').addEventListener('click', closeKpDialog);
    document.getElementById('kpCancel').addEventListener('click', closeKpDialog);
    kpFilter.addEventListener('input', renderKpList);
    kpSemester.addEventListener('change', renderKpList);
    kpList.addEventListener('change', (ev) => {{
      const el = ev.target;
      if (!el || el.type !== 'checkbox') return;
      if (el.checked) kpSelected.add(el.value);
      else kpSelected.delete(el.value);
      updateKpHint();
    }});
    document.getElementById('kpSave').addEventListener('click', async () => {{
      if (!kpQuestionId) return;
      const codes = [...kpSelected];
      const btn = document.getElementById('kpSave');
      btn.disabled = true;
      try {{
        const res = await fetch('/api/exam-bank/questions/' + encodeURIComponent(kpQuestionId) + '/knowledge-points', {{
          method: 'PUT',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ codes }}),
        }});
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const saved = data.knowledge_points || [];
        if (lastPreviewData && lastPreviewData.questions) {{
          lastPreviewData.questions.forEach(q => {{
            if (q.question_id === kpQuestionId) {{
              q.knowledge_points = saved;
              q.knowledge_codes = saved.map(k => k.code);
            }}
          }});
        }}
        const holder = document.querySelector('[data-kp-list="' + kpQuestionId + '"]');
        if (holder) holder.innerHTML = kpChips(saved);
        closeKpDialog();
      }} catch (err) {{
        document.getElementById('kpHint').textContent = '保存失败: ' + err.message;
      }} finally {{
        btn.disabled = false;
      }}
    }});
  </script>
  <script src="/static/visual-solve.js"></script>
</body>
</html>"""


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version=__version__, port=PORT)


@app.get("/files/{job}/{path:path}")
def preview_file(job: str, path: str):
    job = _safe_job(job)
    root = (_PREVIEW_ROOTS.get(job) or (PREVIEWS / job)).resolve()
    if not root.exists():
        raise HTTPException(404, "Preview not found")
    target = (root / path).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target)


class OpenLocalBody(BaseModel):
    path: str
    job_id: str | None = None


@app.post("/api/open-local")
def open_local(body: OpenLocalBody) -> JSONResponse:
    """Register a local md_out directory for web viewing."""
    try:
        job = _register_preview_dir(Path(body.path), body.job_id)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"ok": True, "job": job, "view_url": f"/view/{job}"})


@app.post("/api/preprocess")
async def api_preprocess(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Please upload a .docx file")
    job = f"prep_{os.getpid()}_{re.sub(r'[^A-Za-z0-9_\\-]+', '_', Path(file.filename).stem)[:40]}"
    dest_dir = WORK / "preprocess" / job
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = dest_dir / "input.docx"
    src.write_bytes(await file.read())
    out_name = Path(file.filename).stem + ".preprocessed.docx"
    out = dest_dir / out_name
    try:
        stats = preprocess_docx(src, out)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse(
        {
            "ok": True,
            "stats": stats,
            "download_url": f"/api/preprocessed/{job}/{quote(out_name)}",
            "file_name": out_name,
        }
    )


@app.get("/api/preprocessed/{job}/{name}")
def download_preprocessed(job: str, name: str):
    job = _safe_job(job)
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Invalid path")
    path = WORK / "preprocess" / job / name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(
        path,
        filename=name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.post("/api/ole-to-latex")
async def api_ole_to_latex(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Please upload a .docx file")
    job = f"ole_{os.getpid()}_{re.sub(r'[^A-Za-z0-9_\\-]+', '_', Path(file.filename).stem)[:40]}"
    dest_dir = WORK / "ole" / job
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = dest_dir / Path(file.filename).name
    src.write_bytes(await file.read())
    out_name = Path(file.filename).stem + ".ole-latex.docx"
    out_docx = dest_dir / out_name
    try:
        formulas = convert_ole_docx(src, out_docx)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    listing_name = "ole-formulas.txt"
    listing = dest_dir / listing_name
    listing.write_text(format_formula_list(formulas), encoding="utf-8")
    return JSONResponse(
        {
            "ok": True,
            "file_name": file.filename,
            "count": len(formulas),
            "formulas": formulas,
            "docx_url": f"/api/ole-to-latex/{job}/{quote(out_name)}",
            "download_url": f"/api/ole-to-latex/{job}/{quote(listing_name)}",
        }
    )


@app.get("/api/ole-to-latex/{job}/{name}")
def download_ole_list(job: str, name: str):
    job = _safe_job(job)
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Invalid path")
    path = WORK / "ole" / job / name
    if not path.exists():
        raise HTTPException(404, "File not found")
    if name.lower().endswith(".docx"):
        return FileResponse(
            path,
            filename=name,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    return FileResponse(path, filename="公式输出清单.txt", media_type="text/plain; charset=utf-8")


@app.post("/api/inspect")
async def api_inspect(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Please upload a .docx file")
    tmp = WORK / f"inspect_{os.getpid()}_{Path(file.filename).name}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(await file.read())
    try:
        data = inspect_docx(tmp)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return JSONResponse(data)


@app.post("/api/convert")
async def api_convert(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Please upload a .docx file")

    job = f"job_{os.getpid()}_{re.sub(r'[^A-Za-z0-9_\\-]+', '_', Path(file.filename).stem)[:40]}"
    dest = PREVIEWS / job
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    src = dest / Path(file.filename).name
    src.write_bytes(await file.read())
    out_md = dest / (src.stem + ".md")

    try:
        meta = convert_docx_like_gaokao(src, out_md)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

    _PREVIEW_ROOTS[job] = dest

    file_name = str(meta.get("fileName") or out_md.name)
    preview = out_md.read_text(encoding="utf-8-sig", errors="ignore")
    if len(preview) > 4000:
        preview = preview[:4000] + "\n…(truncated)"

    return JSONResponse(
        {
            "ok": True,
            "file_name": file_name,
            "math_converted": int(meta.get("mathConverted") or 0),
            "image_count": int(meta.get("imageCount") or 0),
            "warnings": list(meta.get("warnings") or []),
            "job": job,
            "view_url": f"/view/{job}",
            "download_url": f"/api/download/{quote(out_md.name)}?job={job}",
            "preview": preview,
        }
    )


@app.get("/api/download/{name}")
def download(name: str, job: str) -> FileResponse:
    job = _safe_job(job)
    root = _PREVIEW_ROOTS.get(job) or (PREVIEWS / job) or (WORK / job)
    path = Path(root) / name
    if not path.exists():
        path = WORK / job / name
    if not path.exists():
        raise HTTPException(404, "File not found")
    media = (
        "text/markdown; charset=utf-8"
        if name.lower().endswith(".md")
        else "application/zip"
    )
    return FileResponse(path, filename=name, media_type=media)


@app.post("/api/parse-markdown")
async def api_parse_markdown(file: UploadFile = File(...)) -> JSONResponse:
    name = file.filename or ""
    if not re.search(r"\.(md|markdown|mdown)$", name, re.I):
        raise HTTPException(400, "请上传 Markdown 文件（.md）")
    job = f"md_{os.getpid()}_{re.sub(r'[^A-Za-z0-9_\\-]+', '_', Path(name).stem)[:40]}"
    dest = WORK / "parse" / job
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    src = dest / Path(name).name
    src.write_bytes(await file.read())
    try:
        data = parse_markdown_like_gaokao(src)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    data["ok"] = True
    data["file_name"] = name
    return JSONResponse(data)


@app.get("/api/exam-bank/status")
def exam_bank_status() -> JSONResponse:
    return JSONResponse({"ok": True, "configured": exam_bank_configured()})


@app.post("/api/exam-bank/import-markdown")
async def api_import_markdown(
    file: UploadFile = File(...),
    paper_code: str | None = Form(None),
    paper_title: str | None = Form(None),
) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(
            503,
            "未配置 Supabase。请先运行 python scripts/setup_supabase.py，或在 .env 填写 SUPABASE_URL 与 SUPABASE_SERVICE_ROLE_KEY。",
        )
    name = file.filename or ""
    if not re.search(r"\.(md|markdown|mdown)$", name, re.I):
        raise HTTPException(400, "请上传 Markdown 文件（.md）")
    job = f"imp_{os.getpid()}_{re.sub(r'[^A-Za-z0-9_\\-]+', '_', Path(name).stem)[:40]}"
    dest = WORK / "import" / job
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    src = dest / Path(name).name
    src.write_bytes(await file.read())
    try:
        data = import_markdown_file(src, paper_code=paper_code, title=paper_title)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    data["ok"] = True
    data["file_name"] = name
    return JSONResponse(data)


@app.get("/api/exam-bank/papers")
def api_list_papers() -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        papers = list_papers()
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "papers": papers})


class PaperMetaIn(BaseModel):
    semester: str | None = None
    exam_type: str | None = None


@app.patch("/api/exam-bank/papers/{paper_id}")
def api_update_paper_meta(paper_id: str, body: PaperMetaIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", paper_id or ""):
        raise HTTPException(400, "无效的试卷 id")
    try:
        paper = update_paper_meta(
            paper_id,
            semester=body.semester,
            exam_type=body.exam_type,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "paper": paper})


class QuestionsByKnowledgeIn(BaseModel):
    codes: list[str] = []
    match: str = "any"
    type_code: str = ""


class PracticePreviewIn(BaseModel):
    question_ids: list[str] = []


def _parse_questions_markdown(source: str, job: str) -> dict:
    dest = WORK / "preview-bank" / job
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    src = dest / "paper.md"
    src.write_text(source, encoding="utf-8")
    return parse_markdown_like_gaokao(src)


@app.post("/api/exam-bank/questions-by-knowledge")
def api_questions_by_knowledge(body: QuestionsByKnowledgeIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        data = list_questions_by_knowledge(
            body.codes,
            match=body.match,
            type_code=(body.type_code or "").strip(),
        )
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    slim = []
    for q in data.get("questions") or []:
        slim.append(
            {
                "id": q.get("id"),
                "paper_id": q.get("paper_id"),
                "paper_code": q.get("paper_code"),
                "paper_title": q.get("paper_title"),
                "question_no": q.get("question_no"),
                "type_code": q.get("type_code"),
                "stem_text": (q.get("stem_text") or "")[:240],
                "score": q.get("score"),
                "knowledge_points": q.get("knowledge_points") or [],
                "knowledge_codes": q.get("knowledge_codes") or [],
                "matched_codes": q.get("matched_codes") or [],
            }
        )
    return JSONResponse(
        {
            "ok": True,
            "codes": data.get("codes") or [],
            "match": data.get("match") or "any",
            "questions": slim,
        }
    )


@app.post("/api/exam-bank/practice/preview")
def api_practice_preview(body: PracticePreviewIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        rows = get_questions_by_ids(body.question_ids)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    if not rows:
        raise HTTPException(400, "没有可预览的题目，请先选择题目。")
    numbered = []
    for i, row in enumerate(rows, start=1):
        item = dict(row)
        item["question_no"] = i
        numbered.append(item)
    source = questions_to_markdown(numbered)
    if not source.strip():
        raise HTTPException(404, "所选题目没有可显示的内容。")
    try:
        data = _parse_questions_markdown(source, "practice")
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    parsed = data.get("questions") or []
    for i, item in enumerate(parsed):
        dbq = numbered[i] if i < len(numbered) else None
        if not dbq:
            continue
        item["question_id"] = dbq.get("id")
        item["type_code"] = dbq.get("type_code") or ""
        item["knowledge_points"] = dbq.get("knowledge_points") or []
        item["knowledge_codes"] = dbq.get("knowledge_codes") or []
        item["paper_title"] = dbq.get("paper_title") or ""
        item["paper_code"] = dbq.get("paper_code") or ""
        item["source_question_no"] = dbq.get("source_question_no")
    kps = []
    seen_kp: set[str] = set()
    for row in numbered:
        for kp in row.get("knowledge_points") or []:
            code = kp.get("code") or ""
            if code and code not in seen_kp:
                seen_kp.add(code)
                kps.append(code)
    title = "知识点专项训练"
    if kps:
        title = "知识点专项训练（" + "、".join(kps[:8]) + ("…" if len(kps) > 8 else "") + "）"
    data["ok"] = True
    data["title"] = title
    data["questions"] = parsed
    return JSONResponse(data)


@app.get("/knowledge", response_class=HTMLResponse)
def knowledge_admin_page() -> str:
    return knowledge_page_html()


@app.get("/practice", response_class=HTMLResponse)
def practice_page() -> str:
    return practice_page_html()


@app.get("/api/exam-bank/knowledge-points")
def api_list_knowledge_points(with_usage: bool = False) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        points = list_catalog() if with_usage else list_knowledge_points(limit=2000)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "knowledge_points": points})


class KnowledgeCatalogIn(BaseModel):
    code: str
    description: str = ""
    semester: str = ""
    major_category: str = ""
    minor_category: str = ""
    sort_order: int = 0


class KnowledgeCatalogPatchIn(BaseModel):
    description: str = ""
    semester: str | None = None
    major_category: str | None = None
    minor_category: str | None = None
    sort_order: int | None = None


class KnowledgeBulkIn(BaseModel):
    text: str


@app.post("/api/exam-bank/knowledge-points")
def api_create_knowledge_point(body: KnowledgeCatalogIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        item = create_catalog_item(
            body.code,
            body.description,
            body.sort_order,
            semester=body.semester,
            major_category=body.major_category,
            minor_category=body.minor_category,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "knowledge_point": item})


@app.post("/api/exam-bank/knowledge-points/bulk")
def api_bulk_knowledge_points(body: KnowledgeBulkIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        result = bulk_upsert_catalog(body.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    result["ok"] = True
    return JSONResponse(result)


@app.post("/api/exam-bank/knowledge-points/seed-gaokao")
def api_seed_gaokao_knowledge() -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        result = seed_gaokao_catalog()
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    result["ok"] = True
    return JSONResponse(result)


@app.put("/api/exam-bank/knowledge-points/{code}")
def api_update_knowledge_point(code: str, body: KnowledgeCatalogPatchIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        item = update_catalog_item(
            code,
            body.description,
            body.sort_order,
            semester=body.semester,
            major_category=body.major_category,
            minor_category=body.minor_category,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "knowledge_point": item})


@app.delete("/api/exam-bank/knowledge-points/{code}")
def api_delete_knowledge_point(code: str) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        delete_catalog_item(code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True})


@app.get("/api/exam-bank/papers/{paper_id}")
def api_paper_detail(paper_id: str) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        data = get_paper_questions(paper_id)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    data["ok"] = True
    return JSONResponse(data)


@app.get("/api/exam-bank/papers/{paper_id}/preview")
def api_paper_preview(paper_id: str) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", paper_id or ""):
        raise HTTPException(400, "无效的试卷 id")
    try:
        raw = get_paper_questions(paper_id)
        paper = raw.get("paper") or {}
        source = (paper.get("source_md") or "").strip()
        if not source:
            source = questions_to_markdown(raw.get("questions") or [])
        if not source.strip():
            raise HTTPException(404, "该试卷没有可显示的内容。")
        dest = WORK / "preview-bank" / paper_id
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        src = dest / "paper.md"
        src.write_text(source, encoding="utf-8")
        data = parse_markdown_like_gaokao(src)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    data["ok"] = True
    data["paper"] = {
        "id": paper.get("id"),
        "paper_code": paper.get("paper_code"),
        "title": paper.get("title"),
        "source_filename": paper.get("source_filename"),
        "semester": paper.get("semester") or "",
        "exam_type": paper.get("exam_type") or "",
    }
    data["file_name"] = paper.get("source_filename") or paper.get("title")
    by_no = {}
    for row in raw.get("questions") or []:
        try:
            by_no[int(row.get("question_no"))] = row
        except (TypeError, ValueError):
            continue
    for item in data.get("questions") or []:
        try:
            dbq = by_no.get(int(item.get("index")))
        except (TypeError, ValueError):
            dbq = None
        if not dbq:
            continue
        item["question_id"] = dbq.get("id")
        item["type_code"] = dbq.get("type_code") or ""
        item["knowledge_points"] = dbq.get("knowledge_points") or []
        item["knowledge_codes"] = dbq.get("knowledge_codes") or []
    return JSONResponse(data)


class KnowledgeItemIn(BaseModel):
    code: str
    description: str = ""


class SetQuestionKnowledgeIn(BaseModel):
    codes: list[str] | None = None
    items: list[KnowledgeItemIn] = []


@app.get("/api/exam-bank/geogebra/animations")
def api_list_geogebra_animations(codes: str = "") -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    wanted = [part.strip() for part in (codes or "").split(",") if part.strip()]
    try:
        animations = list_animations_for_codes(wanted)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "codes": wanted, "animations": animations})


@app.get("/api/exam-bank/questions/{question_id}/animations")
def api_question_animations(question_id: str) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", question_id or ""):
        raise HTTPException(400, "无效的题目 id")
    try:
        animations = list_animations_for_question(question_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "question_id": question_id, "animations": animations})


@app.post("/api/exam-bank/geogebra/sync")
def api_sync_geogebra_animations() -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    try:
        data = sync_geogebra_pep_animations(live=True)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    data["ok"] = True
    return JSONResponse(data)


@app.put("/api/exam-bank/questions/{question_id}/knowledge-points")
def api_set_question_knowledge(question_id: str, body: SetQuestionKnowledgeIn) -> JSONResponse:
    if not exam_bank_configured():
        raise HTTPException(503, "未配置 Supabase 题库。")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", question_id or ""):
        raise HTTPException(400, "无效的题目 id")
    try:
        payload = body.codes if body.codes is not None else [item.model_dump() for item in body.items]
        saved = set_question_knowledge_points(question_id, payload)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return JSONResponse({"ok": True, "knowledge_points": saved})


if KATEX_DIR.is_dir():
    app.mount("/vendor/katex", StaticFiles(directory=str(KATEX_DIR)), name="katex")

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("word_math_md.server:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
