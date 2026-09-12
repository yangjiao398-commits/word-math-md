"""Standalone page for maintaining the knowledge-point catalog."""

from __future__ import annotations

PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>知识点维护 · word-math-md</title>
  <style>
    :root {
      --bg: #0f1419; --panel: #1a222c; --ink: #e8eef5; --muted: #8b9aab;
      --accent: #3d9cf0; --line: #2a3542;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; min-height: 100vh; color: var(--ink);
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(900px 500px at 10% -10%, #1c3a5a 0%, transparent 55%),
        radial-gradient(700px 400px at 100% 0%, #243048 0%, transparent 50%),
        var(--bg);
    }
    main { max-width: 1080px; margin: 0 auto; padding: 48px 20px 80px; }
    h1 { font-size: clamp(1.6rem, 3vw, 2.1rem); margin: 0 0 8px; font-weight: 650; }
    .brand { color: var(--accent); font-weight: 700; }
    p.lead { color: var(--muted); margin: 0 0 22px; line-height: 1.6; }
    a { color: var(--accent); }
    .panel {
      background: color-mix(in srgb, var(--panel) 88%, black);
      border: 1px solid var(--line); border-radius: 14px; padding: 18px 18px 14px;
      margin-bottom: 16px;
    }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin: 12px 0 6px; }
    input[type=text], textarea {
      width: 100%; padding: 10px 12px; border-radius: 8px;
      border: 1px solid var(--line); background: #12181f; color: var(--ink);
    }
    textarea { min-height: 140px; resize: vertical; font-family: inherit; }
    .row { display: grid; grid-template-columns: 120px 1fr 1fr 1fr auto; gap: 10px; align-items: end; }
    @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
    button {
      padding: 10px 16px; border: 0; border-radius: 10px;
      background: linear-gradient(135deg, #3d9cf0, #2a7fd4); color: white;
      font-weight: 600; cursor: pointer;
    }
    button.secondary { background: #243140; border: 1px solid var(--line); }
    button.danger { background: #5a2a2a; border: 1px solid #7a3a3a; }
    button:disabled { opacity: 0.6; cursor: wait; }
    #status { color: #c5d0dc; font-size: 0.92rem; margin: 8px 0 0; min-height: 1.4em; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }
    th { color: #9ecbff; font-weight: 600; }
    .muted { color: var(--muted); }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .actions button { padding: 6px 10px; font-size: 0.8rem; width: auto; }
    #filter { margin-bottom: 10px; }
  </style>
</head>
<body>
  <main>
    <div class="brand">word-math-md</div>
    <h1>高中数学知识点维护</h1>
    <p class="lead">
      知识点字典在 <code>knowledge_points</code>：编号、学期、大类、小类。
      给题目勾选后才写入关联表 <code>question_knowledge_points</code>。
      <a href="/">返回转换首页</a>
    </p>

    <section class="panel">
      <h2 style="margin:0 0 8px;font-size:1.05rem;">导入高中课标目录</h2>
      <p class="muted">写入高一至高三共 89 条（已存在的编号会更新学期/大类/小类）。</p>
      <button type="button" id="btnSeed">导入课标知识点</button>
    </section>

    <section class="panel">
      <h2 style="margin:0 0 8px;font-size:1.05rem;">单条录入</h2>
      <div class="row">
        <div>
          <label>编号</label>
          <input type="text" id="code" placeholder="如 1.1" />
        </div>
        <div>
          <label>学期</label>
          <input type="text" id="semester" placeholder="如 高一上（必修第一册）" />
        </div>
        <div>
          <label>知识点大类</label>
          <input type="text" id="major" placeholder="如 集合与常用逻辑用语" />
        </div>
        <div>
          <label>知识点小类</label>
          <input type="text" id="minor" placeholder="如 集合的概念与表示" />
        </div>
        <button type="button" id="btnAdd">保存</button>
      </div>
    </section>

    <section class="panel">
      <h2 style="margin:0 0 8px;font-size:1.05rem;">批量录入</h2>
      <label>每行一条：编号 + 空格 + 小类描述</label>
      <textarea id="bulk" placeholder="1.1 集合的概念与表示&#10;1.2 集合间的基本关系"></textarea>
      <div style="margin-top:10px">
        <button type="button" id="btnBulk">批量写入</button>
      </div>
    </section>

    <section class="panel">
      <h2 style="margin:0 0 8px;font-size:1.05rem;">已有知识点</h2>
      <input type="text" id="filter" placeholder="按编号或描述筛选" />
      <div id="tableWrap">加载中…</div>
    </section>
    <p id="status"></p>
  </main>
  <script>
    const status = document.getElementById('status');
    const tableWrap = document.getElementById('tableWrap');
    let rows = [];
    function esc(s) {
      return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    }
    async function readJson(res) {
      const raw = await res.text();
      try { return JSON.parse(raw); }
      catch (e) { throw new Error(raw.slice(0, 180) || '接口未返回 JSON'); }
    }
    function setStatus(msg) { status.textContent = msg || ''; }
    function renderTable() {
      const q = document.getElementById('filter').value.trim().toLowerCase();
      const shown = rows.filter(r => {
        if (!q) return true;
        const blob = [r.code, r.semester, r.major_category, r.minor_category, r.description]
          .join(' ').toLowerCase();
        return blob.includes(q);
      });
      if (!shown.length) {
        tableWrap.innerHTML = '<p class="muted">没有匹配的知识点。</p>';
        return;
      }
      tableWrap.innerHTML = '<table><thead><tr><th>编号</th><th>学期</th><th>大类</th><th>小类</th><th>被题引用</th><th></th></tr></thead><tbody>' +
        shown.map(r => '<tr data-code="' + esc(r.code) + '"><td>' + esc(r.code) +
          '</td><td>' + esc(r.semester || '') + '</td><td>' + esc(r.major_category || '') +
          '</td><td>' + esc(r.minor_category || '') +
          '</td><td>' + esc(r.question_count || 0) +
          '</td><td class="actions">' +
          '<button type="button" class="secondary" data-edit>修改</button>' +
          '<button type="button" class="danger" data-del>删除</button></td></tr>'
        ).join('') + '</tbody></table>';
    }
    async function reload() {
      tableWrap.textContent = '加载中…';
      const res = await fetch('/api/exam-bank/knowledge-points?with_usage=1');
      const data = await readJson(res);
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      rows = data.knowledge_points || [];
      renderTable();
      setStatus('共 ' + rows.length + ' 条知识点。');
    }
    document.getElementById('filter').addEventListener('input', renderTable);
    document.getElementById('btnAdd').addEventListener('click', async () => {
      const code = document.getElementById('code').value.trim();
      const semester = document.getElementById('semester').value.trim();
      const major_category = document.getElementById('major').value.trim();
      const minor_category = document.getElementById('minor').value.trim();
      try {
        const res = await fetch('/api/exam-bank/knowledge-points', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, semester, major_category, minor_category }),
        });
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        ['code','semester','major','minor'].forEach(id => document.getElementById(id).value = '');
        await reload();
        setStatus('已保存 ' + code + '。');
      } catch (err) {
        setStatus('保存失败: ' + err.message);
      }
    });
    document.getElementById('btnSeed').addEventListener('click', async () => {
      if (!confirm('导入高中课标 89 条知识点？已有编号会被更新。')) return;
      try {
        const res = await fetch('/api/exam-bank/knowledge-points/seed-gaokao', { method: 'POST' });
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        await reload();
        setStatus('课标导入完成：新增 ' + data.inserted + '，更新 ' + data.updated + '。');
      } catch (err) {
        setStatus('课标导入失败: ' + err.message);
      }
    });
    document.getElementById('btnBulk').addEventListener('click', async () => {
      const text = document.getElementById('bulk').value;
      try {
        const res = await fetch('/api/exam-bank/knowledge-points/bulk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        });
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        document.getElementById('bulk').value = '';
        await reload();
        setStatus('批量完成：新增 ' + data.inserted + '，更新 ' + data.updated + '。');
      } catch (err) {
        setStatus('批量失败: ' + err.message);
      }
    });
    tableWrap.addEventListener('click', async (ev) => {
      const tr = ev.target.closest('tr[data-code]');
      if (!tr) return;
      const code = tr.getAttribute('data-code');
      const row = rows.find(r => r.code === code);
      if (ev.target.closest('[data-edit]')) {
        const semester = prompt('学期', row ? (row.semester || '') : '');
        if (semester == null) return;
        const major_category = prompt('知识点大类', row ? (row.major_category || '') : '');
        if (major_category == null) return;
        const minor_category = prompt('知识点小类', row ? (row.minor_category || row.description || '') : '');
        if (minor_category == null) return;
        try {
          const res = await fetch('/api/exam-bank/knowledge-points/' + encodeURIComponent(code), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ semester, major_category, minor_category }),
          });
          const data = await readJson(res);
          if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
          await reload();
          setStatus('已更新 ' + code + '。');
        } catch (err) {
          setStatus('更新失败: ' + err.message);
        }
      }
      if (ev.target.closest('[data-del]')) {
        if (!confirm('确定删除知识点 ' + code + '？已被题目引用的不能删。')) return;
        try {
          const res = await fetch('/api/exam-bank/knowledge-points/' + encodeURIComponent(code), {
            method: 'DELETE',
          });
          const data = await readJson(res);
          if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
          await reload();
          setStatus('已删除 ' + code + '。');
        } catch (err) {
          setStatus('删除失败: ' + err.message);
        }
      }
    });
    reload().catch(err => {
      tableWrap.innerHTML = '<p>加载失败: ' + esc(err.message) + '</p>';
    });
  </script>
</body>
</html>
"""


def page_html() -> str:
    return PAGE_HTML
