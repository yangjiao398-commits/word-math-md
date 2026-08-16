"""FastAPI web service for MathDoc Converter (default port 3010)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
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
    a.dl {{ color: var(--accent); }}
    footer {{ margin-top: 28px; color: var(--muted); font-size: 0.8rem; }}
    #questions {{ margin-top: 22px; }}
    .q-card {{
      background: #12181f; border: 1px solid var(--line); border-radius: 12px;
      padding: 16px; margin-bottom: 14px;
    }}
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
  </style>
  <link rel="stylesheet" href="/vendor/katex/katex.min.css"/>
</head>
<body>
  <main>
    <div class="brand">word-math-md</div>
    <h1>MathDoc Converter</h1>
    <p class="lead">「word转换md文件」与高考数学助理「选择 Word 并转换为 Markdown」同一套流水线：OMML→LaTeX、mammoth、选项公式修复；图片以 data URL 嵌入并下载 .md。服务端口 {PORT}。</p>
    <form id="f">
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
    <input type="file" id="mdFile" accept=".md,.markdown,.mdown,text/markdown,text/plain" hidden />
    <div id="result">选择 .docx 后可转换或分析。点「上传markdown并显示题目」可预览试卷题目（与高考数学助理题库相同）。</div>
    <div id="analysis" hidden></div>
    <div id="questions" hidden></div>
    <footer>API: POST /api/convert · POST /api/parse-markdown · POST /api/inspect · POST /api/ole-to-latex · GET /view/&lt;job&gt; · v{__version__}</footer>
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
    const oleFile = document.getElementById('oleFile');
    const mdFile = document.getElementById('mdFile');
    const questions = document.getElementById('questions');
    function esc(s) {{
      return String(s ?? '').replace(/[&<>]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
    }}
    async function readJson(res) {{
      const raw = await res.text();
      try {{ return JSON.parse(raw); }}
      catch (e) {{
        throw new Error('接口未返回 JSON，请确认打开的是 http://127.0.0.1:3010 （word-math-md）。' + raw.slice(0, 120));
      }}
    }}
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
    function renderQuestions(data) {{
      const qs = data.questions || [];
      const notices = data.notices || [];
      let html = notices.map(n => '<p class="summary">' + esc(n.text) + '</p>').join('');
      if (!qs.length) {{
        html += '<p>未能解析出题目，请检查题号与【答案】【分析】【详解】标记。</p>';
        questions.innerHTML = html;
        questions.hidden = false;
        return;
      }}
      html += qs.map(q => {{
        let card = '<article class="q-card"><div class="q-meta">';
        card += '<span class="chip">第 ' + esc(q.index) + ' 题</span>';
        card += q.answerHtml ? '<span class="chip ok">含答案</span>' : '<span class="chip warn">缺答案</span>';
        if (q.analysisHtml) card += '<span class="chip">含分析</span>';
        if (q.detailHtml) card += '<span class="chip">含详解</span>';
        card += '</div><h3>题干</h3><div class="rich-content">' + (q.stemHtml || '') + '</div>';
        if (q.answerHtml) {{
          card += '<div class="q-block"><h4>【答案】</h4><div class="rich-content">' + q.answerHtml + '</div></div>';
        }}
        if (q.analysisHtml) {{
          card += '<div class="q-block"><h4>【分析】</h4><div class="rich-content">' + q.analysisHtml + '</div></div>';
        }}
        if (q.detailHtml) {{
          card += '<div class="q-block"><h4>【详解】</h4><div class="rich-content">' + q.detailHtml + '</div></div>';
        }}
        card += '</article>';
        return card;
      }}).join('');
      questions.innerHTML = html;
      questions.hidden = false;
    }}
    async function runParseMarkdown(file) {{
      btnParseMd.disabled = true;
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
  </script>
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


if KATEX_DIR.is_dir():
    app.mount("/vendor/katex", StaticFiles(directory=str(KATEX_DIR)), name="katex")


def run() -> None:
    import uvicorn

    uvicorn.run("word_math_md.server:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    run()
