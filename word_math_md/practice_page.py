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
    .q-actions { margin-top: 12px; }
    .q-actions button { width: auto; font-size: 0.88rem; }
    .q-solution { margin-top: 4px; }
    .q-solution[hidden] { display: none; }
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
    .anim-count { color: #9ecbff; font-size: 0.78rem; }
    .ggb-modal {
      position: fixed; inset: 0; z-index: 40;
      background: rgba(6, 10, 16, 0.72);
      display: flex; align-items: center; justify-content: center;
      padding: 20px;
    }
    .ggb-modal[hidden] { display: none; }
    .ggb-dialog {
      width: min(1440px, calc(100vw - 16px)); height: min(920px, calc(100vh - 16px));
      background: #151c24; border: 1px solid var(--line); border-radius: 14px;
      display: flex; flex-direction: column; overflow: hidden;
    }
    .ggb-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 10px; padding: 12px 14px; border-bottom: 1px solid var(--line);
    }
    .ggb-head h2 { margin: 0; font-size: 1rem; }
    .ggb-head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    #ggbOpen {
      color: var(--accent); text-decoration: none; font-size: 0.88rem; font-weight: 600;
    }
    .ggb-hint { color: var(--muted); font-size: 0.78rem; margin: 0; max-width: 36rem; }
    .ggb-body { flex: 1; display: flex; min-height: 0; }
    .ggb-list {
      width: min(280px, 38%); overflow: auto; border-right: 1px solid var(--line);
      padding: 8px;
    }
    .ggb-item {
      display: block; width: 100%; text-align: left; margin: 0 0 8px;
      background: #1a222c; border: 1px solid var(--line); color: var(--ink);
      padding: 8px 10px; font-weight: 500;
    }
    .ggb-item.active { border-color: var(--accent); background: #203044; }
    .ggb-item small { display: block; color: var(--muted); font-weight: 400; margin-top: 4px; }
    .ggb-stage {
      flex: 1; min-width: 0; min-height: 0; position: relative;
      background: #fff; overflow: hidden;
    }
    .ggb-stage iframe,
    .ggb-stage #ggb-element,
    .ggb-stage article {
      width: 100%; height: 100%; border: 0; display: block;
    }
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
        display: block; height: 297mm; margin-top: 4mm;
      }
    }
  </style>
  <link rel="stylesheet" href="/static/knowledge-courseware.css"/>
</head>
<body>
  <main>
    <div class="brand no-print">word-math-md</div>
    <h1 class="page-title no-print">知识点专项训练</h1>
    <p class="lead no-print">
      按知识点从不同试卷中选题，可多选后预览打印。题目需先在题库中勾选知识点。
      人教配套 GeoGebra 动画已按知识点对照，做题时可直接打开。
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
          <button type="button" class="secondary" id="btnKpAnim">查看所选知识点动画</button>
          <button type="button" class="secondary" id="btnKpPpt">浏览所选知识点 PPT</button>
          <button type="button" class="secondary" id="btnSyncAnim">同步人教动画对照</button>
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
    <div id="ggbModal" class="ggb-modal" hidden>
      <div class="ggb-dialog">
        <div class="ggb-head">
          <div>
            <h2 id="ggbTitle">人教配套动画</h2>
            <p class="ggb-hint">人教配套册多为无声交互课件。各作品原始画布尺寸不同，这里会按窗口缩放；可用全屏或到 GeoGebra 原页查看。</p>
          </div>
          <div class="ggb-head-actions">
            <a class="muted" id="ggbOpen" href="#" target="_blank" rel="noreferrer">在 GeoGebra 打开</a>
            <button type="button" class="secondary" id="btnGgbClose">关闭</button>
          </div>
        </div>
        <div class="ggb-body">
          <div id="ggbList" class="ggb-list"></div>
          <div class="ggb-stage" id="ggbStage"></div>
        </div>
      </div>
    </div>
  </main>
  <script src="https://www.geogebra.org/apps/deployggb.js"></script>
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
          const anim = r.animation_count
            ? ' <span class="anim-count">动画 ' + esc(r.animation_count) + '</span>'
            : '';
          return '<label class="kp-item"><input type="checkbox" value="' + esc(r.code) +
            '"/> <span>' + esc(label) +
            ' <span class="count">(' + esc(r.question_count || 0) + ' 题)</span>' +
            anim + '</span></label>';
        }).join('');
        return '<div class="kp-group"><h3>' + esc(g) + '</h3>' + items + '</div>';
      }).join('');
    }
    function qidOf(q) {
      return q.question_id || q.id;
    }
    function renderFound() {
      if (!found.length) {
        qList.innerHTML = '<p class="muted">没有找到题目。请确认已给题目勾选知识点。</p>';
        return;
      }
      qList.innerHTML = found.map(q => {
        const qid = qidOf(q);
        const on = selected.has(qid) ? ' picked' : '';
        const kps = (q.knowledge_points || []).map(k =>
          '<span class="chip">' + esc(k.code) + ' ' + esc(k.minor_category || k.description || '') + '</span>'
        ).join('');
        const stem = q.stemHtml
          ? '<div class="rich-content print-stem">' + q.stemHtml + '</div>'
          : '<div class="stem-preview">' + esc(q.stem_text || '') + '</div>';
        let sol = '';
        if (q.answerHtml) sol += '<div class="q-block"><h4>【答案】</h4><div class="rich-content">' + q.answerHtml + '</div></div>';
        if (q.analysisHtml) sol += '<div class="q-block"><h4>【分析】</h4><div class="rich-content">' + q.analysisHtml + '</div></div>';
        if (q.detailHtml) sol += '<div class="q-block"><h4>【详解】</h4><div class="rich-content">' + q.detailHtml + '</div></div>';
        if (!sol) sol = '<p class="muted">本题暂无答案或解析。</p>';
        return '<article class="q-card' + on + '">' +
          '<label class="q-meta"><input type="checkbox" data-qid="' + esc(qid) + '"' +
          (selected.has(qid) ? ' checked' : '') + '/>' +
          '<span class="chip">' + esc(TYPE_LABEL[q.type_code] || q.type_code) + '</span>' +
          '<span class="chip">' + esc(q.paper_title || q.paper_code) + '</span>' +
          '<span class="chip">原第 ' + esc(q.source_question_no || q.question_no) + ' 题</span>' +
          kps + '</label>' +
          stem +
          '<div class="q-actions no-print">' +
          '<button type="button" class="secondary" data-sol-btn>查看答案与解析</button> ' +
          '<button type="button" class="secondary" data-anim-btn="' + esc(qid) + '">查看知识点动画</button>' +
          '</div>' +
          '<div class="q-solution" hidden>' + sol + '</div></article>';
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
        const slim = data.questions || [];
        selected.clear();
        slim.forEach(q => selected.add(q.id));
        if (!slim.length) {
          found = [];
          renderFound();
          status.textContent = '没有找到题目。请确认已给题目勾选知识点。';
          return;
        }
        status.textContent = '找到 ' + slim.length + ' 题，正在渲染题干…';
        const prev = await fetch('/api/exam-bank/practice/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_ids: slim.map(q => q.id) }),
        });
        const rendered = await readJson(prev);
        if (!prev.ok) throw new Error(rendered.detail || JSON.stringify(rendered));
        found = (rendered.questions || []).map(q => Object.assign({}, q, {
          id: q.question_id || q.id,
          source_question_no: q.source_question_no || q.question_no,
        }));
        renderFound();
        status.textContent = '找到 ' + found.length + ' 题。题干已列出，可点每题后的按钮查看答案与解析。';
      } catch (err) {
        status.textContent = '查找失败: ' + err.message;
      }
    });
    const ggbModal = document.getElementById('ggbModal');
    const ggbList = document.getElementById('ggbList');
    const ggbStage = document.getElementById('ggbStage');
    const ggbTitle = document.getElementById('ggbTitle');
    const ggbOpen = document.getElementById('ggbOpen');
    let ggbApi = null;
    function fitGgb() {
      if (!ggbApi || typeof ggbApi.setSize !== 'function') return;
      const w = ggbStage.clientWidth;
      const h = ggbStage.clientHeight;
      if (w > 40 && h > 40) ggbApi.setSize(w, h);
    }
    if (window.ResizeObserver) {
      new ResizeObserver(fitGgb).observe(ggbStage);
    }
    function ggbEmbedUrl(materialId) {
      const w = Math.max(480, ggbStage.clientWidth || 960);
      const h = Math.max(320, ggbStage.clientHeight || 540);
      return 'https://www.geogebra.org/material/iframe/id/' + encodeURIComponent(materialId) +
        '/width/' + w + '/height/' + h +
        '/border/ffffff/sfsb/true/sdz/true/szb/true/sri/true/ctl/true?embed=1';
    }
    function unloadGgb() {
      ggbApi = null;
      ggbStage.innerHTML = '';
    }
    function loadGgb(materialId, viewUrl) {
      unloadGgb();
      ggbOpen.href = viewUrl || ('https://www.geogebra.org/m/' + encodeURIComponent(materialId || ''));
      ggbOpen.hidden = !materialId;
      if (!materialId) return;
      const host = document.createElement('div');
      host.id = 'ggb-element';
      ggbStage.appendChild(host);
      if (typeof GGBApplet === 'function') {
        const applet = new GGBApplet({
          appName: 'classic',
          material_id: materialId,
          width: Math.max(480, ggbStage.clientWidth || 960),
          height: Math.max(320, ggbStage.clientHeight || 540),
          scaleContainerClass: 'ggb-stage',
          allowUpscale: true,
          autoHeight: false,
          showFullscreenButton: true,
          showZoomButtons: true,
          showResetIcon: true,
          showAnimationButton: true,
          enableShiftDragZoom: true,
          language: 'zh',
          preventFocus: true,
          borderColor: '#ffffff',
          appletOnLoad: function(api) {
            ggbApi = api;
            fitGgb();
            setTimeout(fitGgb, 300);
          },
        }, true);
        applet.inject('ggb-element');
        return;
      }
      const frame = document.createElement('iframe');
      frame.title = 'GeoGebra 动画';
      frame.allowFullscreen = true;
      frame.setAttribute('allow', 'autoplay; fullscreen; speaker');
      frame.src = ggbEmbedUrl(materialId);
      ggbStage.appendChild(frame);
    }
    function showAnimations(items, heading) {
      const animations = items || [];
      ggbTitle.textContent = heading || '人教配套动画';
      if (!animations.length) {
        ggbList.innerHTML = '<p class="muted">这些知识点还没有对照到人教配套动画。</p>';
        unloadGgb();
        ggbOpen.hidden = true;
        ggbModal.hidden = false;
        return;
      }
      ggbList.innerHTML = animations.map((a, i) =>
        '<button type="button" class="ggb-item' + (i === 0 ? ' active' : '') +
        '" data-material="' + esc(a.material_id || a.page_id) +
        '" data-view="' + esc(a.view_url || '') + '">' + esc(a.title || a.page_id) +
        '<small>' + esc((a.chapter_title || '') + ' · ' + (a.page_id || '')) +
        ((a.knowledge_codes || []).length ? ' · ' + esc((a.knowledge_codes || []).join('、')) : '') +
        '</small></button>'
      ).join('');
      ggbModal.hidden = false;
      const first = animations[0];
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          loadGgb(first.material_id || first.page_id, first.view_url);
        });
      });
    }
    async function openAnimationsByCodes(codes, heading) {
      if (!codes.length) {
        status.textContent = '请先勾选知识点。';
        return;
      }
      status.textContent = '正在加载人教配套动画…';
      const res = await fetch('/api/exam-bank/geogebra/animations?codes=' + encodeURIComponent(codes.join(',')));
      const data = await readJson(res);
      if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
      showAnimations(data.animations || [], heading);
      status.textContent = '已对照 ' + (data.animations || []).length + ' 个动画。';
    }
    qList.addEventListener('click', (ev) => {
      const animBtn = ev.target.closest('[data-anim-btn]');
      if (animBtn && qList.contains(animBtn)) {
        ev.preventDefault();
        const qid = animBtn.getAttribute('data-anim-btn');
        status.textContent = '正在按本题知识点加载动画…';
        fetch('/api/exam-bank/questions/' + encodeURIComponent(qid) + '/animations')
          .then(async res => {
            const data = await readJson(res);
            if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
            return data;
          })
          .then(data => {
            showAnimations(data.animations || [], '本题知识点动画');
            status.textContent = '本题对照到 ' + (data.animations || []).length + ' 个动画。';
          })
          .catch(err => { status.textContent = '加载动画失败: ' + err.message; });
        return;
      }
      const btn = ev.target.closest('[data-sol-btn]');
      if (!btn || !qList.contains(btn)) return;
      ev.preventDefault();
      const card = btn.closest('.q-card');
      const box = card && card.querySelector('.q-solution');
      if (!box) return;
      const open = box.hidden;
      box.hidden = !open;
      btn.textContent = open ? '收起答案与解析' : '查看答案与解析';
    });
    ggbList.addEventListener('click', (ev) => {
      const item = ev.target.closest('.ggb-item');
      if (!item) return;
      ggbList.querySelectorAll('.ggb-item').forEach(el => el.classList.toggle('active', el === item));
      loadGgb(item.getAttribute('data-material'), item.getAttribute('data-view'));
    });
    document.getElementById('btnGgbClose').addEventListener('click', () => {
      ggbModal.hidden = true;
      unloadGgb();
    });
    document.getElementById('btnKpAnim').addEventListener('click', async () => {
      try { await openAnimationsByCodes(pickedCodes(), '所选知识点动画'); }
      catch (err) { status.textContent = '加载动画失败: ' + err.message; }
    });
    document.getElementById('btnKpPpt').addEventListener('click', () => {
      const codes = pickedCodes();
      if (!codes.length) {
        status.textContent = '请先勾选知识点。';
        return;
      }
      if (!window.KnowledgeCourseware) {
        status.textContent = '课件组件未加载。';
        return;
      }
      window.KnowledgeCourseware.openForCodes(codes, '所选知识点 PPT 课件').catch(err => {
        status.textContent = '加载课件失败: ' + err.message;
      });
    });
    document.getElementById('btnSyncAnim').addEventListener('click', async () => {
      status.textContent = '正在从 GeoGebra 人教配套册同步对照关系…';
      try {
        const res = await fetch('/api/exam-bank/geogebra/sync', { method: 'POST' });
        const data = await readJson(res);
        if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
        status.textContent = '已同步 ' + (data.pages || 0) + ' 个动画、' +
          (data.links || 0) + ' 条知识点对照。';
        await loadCatalog();
      } catch (err) {
        status.textContent = '同步失败: ' + err.message;
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
          if (q.score != null && q.score !== '') card += '<span class="chip">' + esc(q.score) + ' 分</span>';
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
  <script src="/static/knowledge-courseware.js"></script>
</body>
</html>
"""


def page_html() -> str:
    return PAGE_HTML
