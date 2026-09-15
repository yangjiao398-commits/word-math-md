"""Cross-paper practice by knowledge point: multi-select questions and print."""

from __future__ import annotations

PAGE_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>知识点专项训练 · word-math-md</title>
  <link rel="stylesheet" href="/vendor/katex/katex.min.css"/>
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
    main { max-width: 1120px; margin: 0 auto; padding: 40px 20px 80px; }
    h1 { font-size: clamp(1.5rem, 3vw, 2rem); margin: 0 0 8px; font-weight: 650; }
    .brand { color: var(--accent); font-weight: 700; }
    p.lead { color: var(--muted); margin: 0 0 20px; line-height: 1.6; }
    a { color: var(--accent); }
    .panel {
      background: color-mix(in srgb, var(--panel) 88%, black);
      border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px;
      margin-bottom: 14px;
    }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
    input[type=text], select {
      padding: 9px 12px; border-radius: 8px;
      border: 1px solid var(--line); background: #12181f; color: var(--ink);
    }
    input[type=text] { min-width: 220px; flex: 1; }
    button {
      padding: 9px 14px; border: 0; border-radius: 10px;
      background: linear-gradient(135deg, #3d9cf0, #2a7fd4); color: white;
      font-weight: 600; cursor: pointer;
    }
    button.secondary { background: #243140; border: 1px solid var(--line); }
    button:disabled { opacity: 0.55; cursor: wait; }
    .kp-groups { max-height: 280px; overflow: auto; margin-top: 10px; }
    .kp-group { margin: 10px 0 14px; }
    .kp-group h3 { margin: 0 0 6px; font-size: 0.85rem; color: #9ecbff; font-weight: 600; }
    .kp-item {
      display: flex; gap: 8px; align-items: flex-start;
      padding: 4px 0; font-size: 0.9rem; cursor: pointer;
    }
    .kp-item input { margin-top: 3px; }
    .count { color: var(--muted); font-size: 0.8rem; }
    .q-card {
      border: 1px solid var(--line); border-radius: 12px;
      padding: 12px 14px; margin: 10px 0; background: #151c24;
    }
    .q-card.picked { border-color: #3d9cf0; }
    .q-meta { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 8px; align-items: center; }
    .chip {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 0.75rem; background: #243140; color: #c5d0dc;
    }
    .stem-preview { color: #d5dee8; font-size: 0.92rem; line-height: 1.55; }
    .rich-content { line-height: 1.75; font-size: 0.92rem; }
    .rich-content .katex { font-size: 1.05em; }
    .rich-content img {
      max-width: 100%; max-height: 12rem; height: auto; display: inline-block;
      vertical-align: middle; border-radius: 6px; border: 1px solid var(--line);
      background: #fff; margin: 4px 0;
    }
    .q-block {
      margin-top: 12px; padding: 10px 12px; border-radius: 10px;
      background: #1a222c; border: 1px solid var(--line);
    }
    .q-block h4 { font-size: 0.85rem; color: var(--accent); margin: 0 0 6px; }
    .status { color: #c5d0dc; font-size: 0.92rem; min-height: 1.3em; }
    .muted { color: var(--muted); }
    .print-exam-title { display: none; }
    .print-q-head { display: none; }
    .print-answer-space { display: none; }
    .paper-preview-bar { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
    body.viewing-paper .brand,
    body.viewing-paper h1.page-title,
    body.viewing-paper p.lead,
    body.viewing-paper #picker {
      display: none;
    }
    body.viewing-paper main { padding-top: 16px; }
    @media print {
      body.viewing-paper {
        background: #fff !important; color: #111;
        font-family: "Times New Roman", "SimSun", serif;
      }
      body.viewing-paper .no-print,
      body.viewing-paper #picker,
      body.viewing-paper .q-meta,
      body.viewing-paper .q-block,
      body.viewing-paper .paper-preview-bar,
      body.viewing-paper .status { display: none !important; }
      body.viewing-paper.print-with-answers .q-block { display: block !important; }
      body.viewing-paper main { max-width: none; padding: 12mm 14mm; }
      body.viewing-paper .print-exam-title {
        display: block; text-align: center; font-size: 18pt; font-weight: 700;
        margin: 0 0 10mm; color: #111;
      }
      body.viewing-paper .print-q-head {
        display: block; float: left; font-weight: 700; margin-right: 0.4em; color: #111;
      }
      body.viewing-paper .q-card {
        background: transparent; border: 0; padding: 0; margin: 0 0 8mm;
        break-inside: avoid;
      }
      body.viewing-paper .print-stem { overflow: visible; color: #111; }
      body.viewing-paper .print-stem img { max-height: none; border: 0; }
      body.viewing-paper .print-answer-space {
        display: block; height: 148.5mm; margin-top: 4mm;
      }
    }
  </style>
</head>
<body>
  <main>
    <div class="brand no-print">word-math-md</div>
    <h1 class="page-title no-print">知识点专项训练</h1>
    <p class="lead no-print">
      按知识点从不同试卷中选题，可多选后预览打印。题目需先在题库中勾选知识点。
      <a href="/">返回首页</a> · <a href="/knowledge">维护知识点</a>
    </p>

    <div id="picker" class="no-print">
      <section class="panel">
        <div class="toolbar">
          <input type="text" id="kpFilter" placeholder="搜索编号、大类或小类" />
          <select id="kpSemester"><option value="">全部学期</option></select>
          <select id="matchMode">
            <option value="any">包含任一所选知识点</option>
            <option value="all">同时包含全部所选知识点</option>
          </select>
          <select id="typeFilter">
            <option value="">全部题型</option>
            <option value="single_choice">单选题</option>
            <option value="multi_choice">多选题</option>
            <option value="fill_blank">填空题</option>
            <option value="solution">解答题</option>
          </select>
          <button type="button" id="btnSearch">查找题目</button>
        </div>
        <div id="kpGroups" class="kp-groups">加载知识点…</div>
      </section>
      <section class="panel">
        <div class="toolbar">
          <button type="button" class="secondary" id="btnAll">全选本页</button>
          <button type="button" class="secondary" id="btnNone">取消全选</button>
          <label class="muted"><input type="checkbox" id="printAnswers"/> 打印时附答案/解析</label>
          <button type="button" id="btnPreview">预览并打印所选</button>
        </div>
        <p class="status" id="status">请先勾选知识点，再查找题目。</p>
        <div id="qList"></div>
      </section>
    </div>
    <div id="preview" hidden></div>
  </main>
  <script>
    const TYPE_LABEL = {
      single_choice: '单选', multi_choice: '多选',
      fill_blank: '填空', solution: '解答'
    };
    const kpGroups = document.getElementById('kpGroups');
    const qList = document.getElementById('qList');
    const status = document.getElementById('status');
    const preview = document.getElementById('preview');
    let catalog = [];
    let found = [];
    const selected = new Set();

    function esc(s) {
      return String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    }
    async function readJson(res) {
      const raw = await res.text();
      try { return JSON.parse(raw); }
      catch (e) { throw new Error(raw.slice(0, 180) || '接口未返回 JSON'); }
    }
    function pickedCodes() {
      return Array.from(document.querySelectorAll('#kpGroups input[type=checkbox]:checked'))
        .map(el => el.value);
    }
    function renderCatalog() {
      const q = document.getElementById('kpFilter').value.trim().toLowerCase();
      const sem = document.getElementById('kpSemester').value;
      const shown = catalog.filter(r => {
        if (sem && (r.semester || '') !== sem) return false;
        if (!q) return true;
        const blob = [r.code, r.semester, r.major_category, r.minor_category, r.description]
          .join(' ').toLowerCase();
        return blob.includes(q);
      });
      const groups = [];
      const map = new Map();
      shown.forEach(r => {
        const key = r.semester || '未分类学期';
        if (!map.has(key)) { map.set(key, []); groups.push(key); }
        map.get(key).push(r);
      });
      if (!shown.length) {
        kpGroups.innerHTML = '<p class="muted">没有匹配的知识点。可先到维护页导入课标。</p>';
        return;
      }
      kpGroups.innerHTML = groups.map(g => {
        const items = map.get(g).map(r => {
          const label = [r.code, r.minor_category || r.description || r.major_category]
            .filter(Boolean).join(' ');
          return '<label class="kp-item"><input type="checkbox" value="' + esc(r.code) +
            '"/> <span>' + esc(label) +
            ' <span class="count">(' + esc(r.question_count || 0) + ' 题)</span></span></label>';
        }).join('');
        return '<div class="kp-group"><h3>' + esc(g) + '</h3>' + items + '</div>';
      }).join('');
    }
    function renderFound() {
      if (!found.length) {
        qList.innerHTML = '<p class="muted">没有找到题目。请确认已给题目勾选知识点。</p>';
        return;
      }
      qList.innerHTML = found.map(q => {
        const on = selected.has(q.id) ? ' picked' : '';
        const kps = (q.knowledge_points || []).map(k =>
          '<span class="chip">' + esc(k.code) + ' ' + esc(k.minor_category || k.description || '') + '</span>'
        ).join('');
        return '<article class="q-card' + on + '">' +
          '<label class="q-meta"><input type="checkbox" data-qid="' + esc(q.id) + '"' +
          (selected.has(q.id) ? ' checked' : '') + '/>' +
          '<span class="chip">' + esc(TYPE_LABEL[q.type_code] || q.type_code) + '</span>' +
          '<span class="chip">' + esc(q.paper_title || q.paper_code) + '</span>' +
          '<span class="chip">原第 ' + esc(q.question_no) + ' 题</span>' +
          kps + '</label>' +
          '<div class="stem-preview">' + esc((q.stem_text || '').slice(0, 180)) + '</div></article>';
      }).join('');
    }
    async function loadCatalog() {
      const res = await fetch('/api/exam-bank/knowledge-points?with_usage=1');
      const data = await readJson(res);
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      catalog = data.knowledge_points || [];
      const sems = [...new Set(catalog.map(r => r.semester).filter(Boolean))];
      const sel = document.getElementById('kpSemester');
      sel.innerHTML = '<option value="">全部学期</option>' +
        sems.map(s => '<option value="' + esc(s) + '">' + esc(s) + '</option>').join('');
      renderCatalog();
      status.textContent = '课标共 ' + catalog.length + ' 条知识点。勾选后点「查找题目」。';
    }
    document.getElementById('kpFilter').addEventListener('input', renderCatalog);
    document.getElementById('kpSemester').addEventListener('change', renderCatalog);
    document.getElementById('btnSearch').addEventListener('click', async () => {
      const codes = pickedCodes();
      if (!codes.length) {
        status.textContent = '请至少勾选一个知识点。';
        return;
      }
      status.textContent = '正在按知识点查找…';
      try {
        const res = await fetch('/api/exam-bank/questions-by-knowledge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            codes,
            match: document.getElementById('matchMode').value,
            type_code: document.getElementById('typeFilter').value,
          }),
        });
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        found = data.questions || [];
        selected.clear();
        found.forEach(q => selected.add(q.id));
        renderFound();
        status.textContent = '找到 ' + found.length + ' 题，已默认全选。可取消不需要的题目后再预览打印。';
      } catch (err) {
        status.textContent = '查找失败: ' + err.message;
      }
    });
    qList.addEventListener('change', (ev) => {
      const box = ev.target.closest('input[data-qid]');
      if (!box) return;
      const qid = box.getAttribute('data-qid');
      if (box.checked) selected.add(qid);
      else selected.delete(qid);
      renderFound();
    });
    document.getElementById('btnAll').addEventListener('click', () => {
      found.forEach(q => selected.add(q.id));
      renderFound();
    });
    document.getElementById('btnNone').addEventListener('click', () => {
      selected.clear();
      renderFound();
    });
    function eagerImages(html) {
      return String(html || '').replace(/<img\b([^>]*?)>/gi, function(_m, attrs) {
        let a = attrs.replace(/\sloading\s*=\s*(['"][^'"]*['"])/gi, '');
        a = a.replace(/\sdecoding\s*=\s*(['"][^'"]*['"])/gi, '');
        return '<img loading="eager" decoding="sync"' + a + '>';
      });
    }
    function waitForPrintImages() {
      const imgs = Array.from(document.querySelectorAll('.print-stem img'));
      return Promise.all(imgs.map(function(img) {
        img.loading = 'eager';
        if (img.complete) return Promise.resolve();
        return new Promise(function(resolve) {
          const done = function() { resolve(); };
          img.addEventListener('load', done, { once: true });
          img.addEventListener('error', done, { once: true });
        });
      }));
    }
    document.getElementById('btnPreview').addEventListener('click', async () => {
      const ids = found.map(q => q.id).filter(id => selected.has(id));
      if (!ids.length) {
        status.textContent = '请至少选择一道题。';
        return;
      }
      status.textContent = '正在生成训练卷…';
      try {
        const res = await fetch('/api/exam-bank/practice/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_ids: ids }),
        });
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        const qs = data.questions || [];
        const title = data.title || '知识点专项训练';
        let html = '<div class="paper-preview-bar no-print">' +
          '<button type="button" class="secondary" id="btnBack">返回选题</button>' +
          '<button type="button" id="btnPrint">打印训练卷</button></div>';
        html += '<h1 class="print-exam-title">' + esc(title) + '</h1>';
        html += qs.map(q => {
          let card = '<article class="q-card"><div class="q-meta no-print">';
          card += '<span class="chip">第 ' + esc(q.index) + ' 题</span>';
          if (q.paper_title) card += '<span class="chip">' + esc(q.paper_title) + '</span>';
          (q.knowledge_points || []).forEach(k => {
            card += '<span class="chip">' + esc(k.code) + '</span>';
          });
          card += '</div><div class="print-q-head">' + esc(q.index) + '.</div>';
          card += '<div class="rich-content print-stem">' + eagerImages(q.stemHtml || '') + '</div>';
          if (q.type_code === 'solution') card += '<div class="print-answer-space"></div>';
          if (q.answerHtml) card += '<div class="q-block"><h4>【答案】</h4><div class="rich-content">' + q.answerHtml + '</div></div>';
          if (q.analysisHtml) card += '<div class="q-block"><h4>【分析】</h4><div class="rich-content">' + q.analysisHtml + '</div></div>';
          if (q.detailHtml) card += '<div class="q-block"><h4>【详解】</h4><div class="rich-content">' + q.detailHtml + '</div></div>';
          card += '</article>';
          return card;
        }).join('');
        preview.innerHTML = html;
        preview.hidden = false;
        document.body.classList.add('viewing-paper');
        document.body.classList.toggle('print-with-answers', document.getElementById('printAnswers').checked);
        status.textContent = '已生成 ' + qs.length + ' 题训练卷。';
        preview.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (err) {
        status.textContent = '预览失败: ' + err.message;
      }
    });
    preview.addEventListener('click', (ev) => {
      if (ev.target.closest('#btnBack')) {
        document.body.classList.remove('viewing-paper', 'print-with-answers');
        preview.hidden = true;
        preview.innerHTML = '';
        return;
      }
      const printBtn = ev.target.closest('#btnPrint');
      if (printBtn) {
        printBtn.disabled = true;
        waitForPrintImages().finally(function() {
          printBtn.disabled = false;
          window.print();
        });
      }
    });
    loadCatalog().catch(err => {
      kpGroups.innerHTML = '<p>加载失败: ' + esc(err.message) + '</p>';
    });
  </script>
</body>
</html>
"""


def page_html() -> str:
    return PAGE_HTML
