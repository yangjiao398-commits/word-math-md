/* 入库试卷：可视化解题动画 */
(function () {
  const PHASES = [
    { id: "read", label: "审题" },
    { id: "model", label: "建模" },
    { id: "compute", label: "演算" },
    { id: "conclude", label: "结论" },
  ];
  const W = 720;
  const H = 340;
  const PAD = 42;

  const state = {
    steps: [],
    index: 0,
    playing: false,
    timer: 0,
    raf: 0,
    t0: 0,
    question: null,
    scene: "board",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function htmlToText(html) {
    const d = document.createElement("div");
    d.innerHTML = html || "";
    return (d.textContent || "").replace(/\s+/g, " ").trim();
  }

  function splitBlocks(html) {
    if (!html) return [];
    const wrap = document.createElement("div");
    wrap.innerHTML = html;
    const chunks = [];
    const kids = [...wrap.children];
    if (!kids.length) {
      const t = wrap.innerHTML.trim();
      return t ? [t] : [];
    }
    kids.forEach((el) => {
      if (el.tagName === "OL" || el.tagName === "UL") {
        [...el.children].forEach((li) => {
          const inner = li.innerHTML.trim();
          if (inner) chunks.push(inner);
        });
        return;
      }
      const inner = el.innerHTML.trim();
      if (inner) chunks.push(inner);
    });
    const out = [];
    chunks.forEach((block) => {
      const parts = block.split(/(?=(?:<(?:p|div|br)[^>]*>)?\s*[\(（][1-9]\d*[\)）])/);
      parts.forEach((p) => {
        const s = p.trim();
        if (s && htmlToText(s).length > 1) out.push(s);
      });
    });
    return out.slice(0, 10);
  }

  function parseNum(s) {
    const n = Number(String(s).replace(/−/g, "-").replace(/^\+/, ""));
    return Number.isFinite(n) ? n : null;
  }

  function extractPoints(text) {
    const pts = [];
    const re =
      /(?:([A-Ha-h])\s*)?[\(（]\s*([-−+]?\d+(?:\.\d+)?)\s*[,，]\s*([-−+]?\d+(?:\.\d+)?)\s*[\)）]/g;
    let m;
    while ((m = re.exec(text))) {
      const x = parseNum(m[2]);
      const y = parseNum(m[3]);
      if (x == null || y == null) continue;
      pts.push({ x, y, label: m[1] ? m[1].toUpperCase() : "" });
    }
    const uniq = [];
    pts.forEach((p) => {
      if (!uniq.some((q) => q.x === p.x && q.y === p.y && q.label === p.label)) uniq.push(p);
    });
    return uniq.slice(0, 8);
  }

  function compilePoly(raw) {
    if (!raw) return null;
    let e = String(raw)
      .replace(/²/g, "^2")
      .replace(/³/g, "^3")
      .replace(/\\left|\\right/g, "")
      .replace(/\\times|\\cdot|×/g, "*")
      .replace(/\\,/g, "")
      .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "(($1)/($2))")
      .replace(/\^{2}/g, "^2")
      .replace(/\^\{(\d+)\}/g, "^$1")
      .replace(/\{/g, "(")
      .replace(/\}/g, ")")
      .replace(/(\d)\s*x/g, "$1*x")
      .replace(/x\s*\^\s*(\d+)/g, "Math.pow(x,$1)")
      .replace(/\^/g, "**")
      .replace(/−/g, "-")
      .replace(/\s+/g, "");
    e = e.replace(/(\))(\()/g, "$1*$2");
    if (/[^0-9x+\-*/().,Mathpow]/.test(e)) return null;
    try {
      const fn = new Function("x", "return (" + e + ");");
      const y0 = fn(0);
      const y1 = fn(1);
      if (!Number.isFinite(y0) && !Number.isFinite(y1)) return null;
      return fn;
    } catch {
      return null;
    }
  }

  function extractFunctions(text) {
    const fns = [];
    const re = /(?:f\s*\(\s*x\s*\)|y)\s*=\s*([^\n。；;，,<]{2,48})/gi;
    let m;
    while ((m = re.exec(text))) {
      const fn = compilePoly(m[1].replace(/\$/g, "").replace(/\\mathrm\{[^}]+\}/g, ""));
      if (fn) fns.push({ expr: m[0], fn });
    }
    return fns.slice(0, 3);
  }

  function extractInterval(text) {
    const m1 = text.match(
      /([x𝑥])\s*([<>≤≥＜＞⩽⩾]|\\le|\\ge|\\lt|\\gt)\s*([-−+]?\d+(?:\.\d+)?)/
    );
    if (m1) {
      const op = m1[2];
      const v = parseNum(m3Safe(m1[3]));
      if (v == null) return null;
      const ge = /[≥⩾]|\\ge/.test(op);
      const gt = /[>＞]|\\gt/.test(op);
      const le = /[≤⩽]|\\le/.test(op);
      if (gt || ge) return { from: v, to: v + 6, openLeft: gt, openRight: true, unbounded: "right" };
      return { from: v - 6, to: v, openLeft: true, openRight: !le, unbounded: "left" };
    }
    const m2 = text.match(
      /[\(\[（]\s*([-−+]?\d+(?:\.\d+)?)\s*[,，]\s*([-−+]?\d+(?:\.\d+)?)\s*[\)\]）]/
    );
    if (m2) {
      const a = parseNum(m2[1]);
      const b = parseNum(m2[2]);
      if (a == null || b == null) return null;
      return {
        from: Math.min(a, b),
        to: Math.max(a, b),
        openLeft: /^[\(（]/.test(m2[0]),
        openRight: /[\)）]$/.test(m2[0]),
      };
    }
    return null;
  }

  function m3Safe(s) {
    return s;
  }

  function detectScene(blob) {
    if (/二次|抛物线|奇函数|偶函数|单调|函数图像|f\s*\(\s*x\s*\)/.test(blob)) return "function";
    if (/不等式|区间|数轴/.test(blob) && /x/.test(blob)) return "numberline";
    if (/三角|圆|向量|直线|坐标|平行四边/.test(blob)) return "geometry";
    if (/概率|排列|组合|树状/.test(blob)) return "flow";
    return "board";
  }

  function phaseOf(i, n, html) {
    if (i === 0) return "read";
    if (i === n - 1) return "conclude";
    const t = htmlToText(html);
    if (/设|令|记|构造|建立|换元/.test(t)) return "model";
    return "compute";
  }

  function buildSteps(q) {
    const blob =
      htmlToText(q.stemHtml) +
      " " +
      htmlToText(q.analysisHtml) +
      " " +
      htmlToText(q.detailHtml);
    const scene = detectScene(blob);
    const points = extractPoints(blob);
    const fns = extractFunctions(blob.replace(/<[^>]+>/g, " "));
    const interval = extractInterval(blob);
    const blocks = [...splitBlocks(q.analysisHtml), ...splitBlocks(q.detailHtml)];
    const steps = [];
    const img = (String(q.stemHtml || "").match(/<img[^>]*>/i) || [""])[0];
    steps.push({
      phase: "read",
      title: "审题：已知条件与所求",
      html:
        (img ? '<div class="vs-stem-img">' + img + "</div>" : "") +
        "<p>" +
        (q.stemText || htmlToText(q.stemHtml).slice(0, 180) || "先读题，标出已知量和目标。") +
        (htmlToText(q.stemHtml).length > 180 ? "…" : "") +
        "</p>",
      op: "intro",
    });
    if (!blocks.length) {
      const type = q.type_code || "";
      if (type === "single_choice" || type === "multi_choice") {
        steps.push({
          phase: "model",
          title: "建模：把选项当成待检验的结论",
          html: "<p>选择题优先用特殊值、图像或定义排除明显错误选项，再验证剩余选项。</p>",
          op: "model",
        });
        steps.push({
          phase: "compute",
          title: "演算：逐项对照",
          html: "<p>把题干条件代入或画出草图，看哪个选项同时满足全部条件。</p>",
          op: "draw",
        });
      } else if (type === "fill_blank") {
        steps.push({
          phase: "model",
          title: "建模：列出等量关系",
          html: "<p>填空题通常只需关键中间式。先写出定义或公式，再化到可填的值。</p>",
          op: "model",
        });
        steps.push({
          phase: "compute",
          title: "演算：化简到结果",
          html: "<p>按定义、性质或配方把式子化到最简，注意定义域与取值范围。</p>",
          op: "draw",
        });
      } else {
        steps.push({
          phase: "model",
          title: "建模：把文字翻译成式子或图形",
          html: "<p>解答题先拆小问。每一问只解决一个目标：作图、求值、或证明。</p>",
          op: "model",
        });
        steps.push({
          phase: "compute",
          title: "演算：由已知推向所求",
          html: "<p>每一步只做一件事：代换、配方、分类讨论或数形结合，并检查是否用全条件。</p>",
          op: "draw",
        });
      }
    } else {
      blocks.forEach((html, i) => {
        const t = htmlToText(html);
        let op = "note";
        if (/设|令|记|构造/.test(t)) op = "model";
        else if (/图像|数轴|坐标|点|函数/.test(t)) op = "draw";
        else if (/所以|因此|故|综上|得/.test(t)) op = "conclude-bit";
        else op = "compute";
        steps.push({
          phase: i < blocks.length - 1 ? (op === "model" ? "model" : "compute") : "compute",
          title: op === "model" ? "建模" : op === "draw" ? "数形结合" : "演算",
          html,
          op,
        });
      });
    }
    steps.push({
      phase: "conclude",
      title: "结论：回到题目所问",
      html: q.answerHtml
        ? q.answerHtml
        : "<p>本题解析未给出标准答案，请对照演算结果自检。</p>",
      op: "answer",
    });
    steps.forEach((s, i) => {
      s.phase = phaseOf(i, steps.length, s.html);
    });
    return { scene, points, fns, interval, steps };
  }

  function niceRange(vals, pad) {
    if (!vals.length) return { min: -4, max: 4 };
    let min = Math.min(...vals);
    let max = Math.max(...vals);
    if (min === max) {
      min -= 2;
      max += 2;
    }
    const span = max - min;
    return { min: min - span * (pad || 0.25), max: max + span * (pad || 0.25) };
  }

  function sx(x, xr) {
    return PAD + ((x - xr.min) / (xr.max - xr.min || 1)) * (W - PAD * 2);
  }
  function sy(y, yr) {
    return H - PAD - ((y - yr.min) / (yr.max - yr.min || 1)) * (H - PAD * 2);
  }

  function sampleFn(fn, xr) {
    const pts = [];
    for (let i = 0; i <= 80; i++) {
      const x = xr.min + ((xr.max - xr.min) * i) / 80;
      let y;
      try {
        y = fn(x);
      } catch {
        continue;
      }
      if (Number.isFinite(y) && Math.abs(y) < 1e6) pts.push([x, y]);
    }
    return pts;
  }

  function pathFrom(pts, xr, yr) {
    return pts
      .map((p, i) => (i ? "L" : "M") + sx(p[0], xr).toFixed(1) + " " + sy(p[1], yr).toFixed(1))
      .join(" ");
  }

  function drawFrame(pack, stepIndex, localT) {
    const svg = $("vsCanvas");
    if (!svg) return;
    const t = Math.max(0, Math.min(1, localT));
    const scene = pack.scene;
    const pts = pack.points;
    const reveal = (stepIndex + t) / Math.max(1, pack.steps.length - 1);
    const xs = pts.map((p) => p.x).concat([-1, 1]);
    const ys = pts.map((p) => p.y).concat([-1, 1]);
    pack.fns.forEach((f) => {
      sampleFn(f.fn, { min: -4, max: 4 }).forEach((p) => {
        xs.push(p[0]);
        ys.push(p[1]);
      });
    });
    if (pack.interval) {
      xs.push(pack.interval.from, pack.interval.to);
    }
    const xr = niceRange(xs, 0.2);
    const yr = niceRange(ys, 0.25);
    if (xr.min > 0) xr.min = 0;
    if (xr.max < 0) xr.max = 0;
    if (yr.min > 0) yr.min = 0;
    if (yr.max < 0) yr.max = 0;

    const ox = sx(0, xr);
    const oy = sy(0, yr);
    let inner = "";
    inner += `<rect x="0" y="0" width="${W}" height="${H}" fill="#f7faf8"/>`;
    inner += `<text x="16" y="24" fill="#5f7266" font-size="12">${escapeXml(sceneLabel(scene))}</text>`;

    if (scene === "numberline") {
      const y = H * 0.55;
      const x0 = PAD;
      const x1 = W - PAD;
      const axisLen = x0 + (x1 - x0) * Math.min(1, t * 1.2 + (stepIndex > 0 ? 1 : 0));
      inner += `<line x1="${x0}" y1="${y}" x2="${Math.min(x1, axisLen)}" y2="${y}" stroke="#5f7266" stroke-width="2"/>`;
      inner += `<polygon points="${Math.min(x1, axisLen)},${y} ${Math.min(x1, axisLen) - 10},${y - 5} ${Math.min(x1, axisLen) - 10},${y + 5}" fill="#5f7266"/>`;
      const iv = pack.interval;
      const mapX = (v) => {
        const a = iv ? iv.from - 2 : xr.min;
        const b = iv ? iv.to + 2 : xr.max;
        return x0 + ((v - a) / (b - a || 1)) * (x1 - x0);
      };
      if (iv && stepIndex >= 1) {
        const left = mapX(iv.from);
        const right = mapX(iv.from + (iv.to - iv.from) * t);
        inner += `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}" stroke="#2f6f4e" stroke-width="8" stroke-linecap="round" opacity="0.55"/>`;
        inner += circle(left, y, iv.openLeft);
        if (t > 0.85) inner += circle(mapX(iv.to), y, iv.openRight);
        inner += `<text x="${left}" y="${y + 28}" text-anchor="middle" fill="#2f6f4e" font-size="13">${iv.from}</text>`;
        inner += `<text x="${mapX(iv.to)}" y="${y + 28}" text-anchor="middle" fill="#2f6f4e" font-size="13">${iv.to}</text>`;
      }
    } else if (scene === "flow") {
      const boxes = ["全部可能", "分类计数", "求概率"];
      boxes.forEach((lab, i) => {
        const x = 70 + i * 210;
        const on = reveal * 3 > i;
        const op = on ? Math.min(1, (reveal * 3 - i) * 1.4) : 0.15;
        inner += `<rect x="${x}" y="120" width="160" height="64" rx="12" fill="#e8f3ec" stroke="#2f6f4e" opacity="${op}"/>`;
        inner += `<text x="${x + 80}" y="158" text-anchor="middle" fill="#2f6f4e" font-size="16" opacity="${op}">${lab}</text>`;
        if (i < 2) {
          inner += `<line x1="${x + 160}" y1="152" x2="${x + 210}" y2="152" stroke="#3d9cf0" stroke-width="2" opacity="${on ? 1 : 0.2}"/>`;
        }
      });
    } else {
      const axisT = scene === "board" && stepIndex === 0 ? t : 1;
      inner += `<line x1="${PAD}" y1="${oy}" x2="${PAD + (W - PAD * 2) * axisT}" y2="${oy}" stroke="#5f7266" stroke-width="1.6"/>`;
      inner += `<line x1="${ox}" y1="${H - PAD}" x2="${ox}" y2="${H - PAD - (H - PAD * 2) * axisT}" stroke="#5f7266" stroke-width="1.6"/>`;
      inner += `<text x="${W - 28}" y="${oy - 8}" fill="#5f7266" font-size="12">x</text>`;
      inner += `<text x="${ox + 8}" y="${28}" fill="#5f7266" font-size="12">y</text>`;

      pack.fns.forEach((f, fi) => {
        const samples = sampleFn(f.fn, xr);
        const d = pathFrom(samples, xr, yr);
        const shown = stepIndex >= 1 ? t : 0;
        inner += `<path d="${d}" fill="none" stroke="${fi ? "#b85c38" : "#2f6f4e"}" stroke-width="2.4" pathLength="1" stroke-dasharray="1" stroke-dashoffset="${1 - shown}"/>`;
      });

      const nShow = Math.floor(pts.length * Math.min(1, (stepIndex + t) / Math.max(1, pack.steps.length - 2)));
      pts.slice(0, Math.max(stepIndex >= 1 ? 1 : 0, nShow)).forEach((p, i) => {
        const cx = sx(p.x, xr);
        const cy = sy(p.y, yr);
        const grow = i === nShow - 1 ? 3 + 3 * t : 5;
        inner += `<circle cx="${cx}" cy="${cy}" r="${grow}" fill="#3d6ea8"/>`;
        if (p.label) {
          inner += `<text x="${cx + 8}" y="${cy - 8}" fill="#1a222c" font-size="13" font-weight="700">${escapeXml(p.label)}</text>`;
        }
      });

      if (!pack.fns.length) {
        const labels = ["已知", "转化", "求解"];
        labels.forEach((lab, i) => {
          const x = 90 + i * 200;
          const on = stepIndex >= i;
          const op = on ? 0.35 + 0.65 * (i === stepIndex ? t : 1) : 0.12;
          inner += `<rect x="${x}" y="118" width="150" height="70" rx="14" fill="#e7eef6" stroke="#3d9cf0" opacity="${op}"/>`;
          inner += `<text x="${x + 75}" y="160" text-anchor="middle" fill="#1a3a5c" font-size="18" opacity="${op}">${lab}</text>`;
          if (i < 2) {
            inner += `<path d="M${x + 150} 153 L${x + 200} 153" stroke="#3d9cf0" stroke-width="2" marker-end="url(#vsArrow)" opacity="${stepIndex > i ? 1 : 0.2}"/>`;
          }
        });
      }
    }

    if (pack.steps[stepIndex] && pack.steps[stepIndex].op === "answer") {
      inner += `<rect x="200" y="12" width="320" height="36" rx="8" fill="#2f6f4e" opacity="${0.15 + 0.55 * t}"/>`;
      inner += `<text x="360" y="36" text-anchor="middle" fill="#2f6f4e" font-size="14" font-weight="700" opacity="${t}">回到所问，核对答案</text>`;
    }

    svg.innerHTML =
      `<defs><marker id="vsArrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#3d9cf0"/></marker></defs>` +
      inner;
  }

  function circle(x, y, hollow) {
    if (hollow) return `<circle cx="${x}" cy="${y}" r="7" fill="#f7faf8" stroke="#2f6f4e" stroke-width="2"/>`;
    return `<circle cx="${x}" cy="${y}" r="6" fill="#2f6f4e"/>`;
  }

  function sceneLabel(scene) {
    return (
      {
        function: "函数图像：先坐标系，再描点/作图",
        numberline: "数轴：把不等式翻译成区间",
        geometry: "坐标几何：点 → 线 → 关系",
        flow: "计数/概率：分类后汇总",
        board: "思维链：已知 → 转化 → 求解",
      }[scene] || "解题思路"
    );
  }

  function escapeXml(s) {
    return String(s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  function renderPhase(phase) {
    const ul = $("vsPhases");
    ul.innerHTML = PHASES.map((p) => {
      const cls = p.id === phase ? "active" : PHASES.findIndex((x) => x.id === phase) > PHASES.findIndex((x) => x.id === p.id) ? "done" : "";
      return "<li class=\"" + cls + "\">" + p.label + "</li>";
    }).join("");
  }

  function showStep(i, animateCanvas) {
    const pack = state.pack;
    if (!pack) return;
    state.index = Math.max(0, Math.min(pack.steps.length - 1, i));
    const step = pack.steps[state.index];
    renderPhase(step.phase);
    const box = $("vsStep");
    box.classList.remove("enter");
    void box.offsetWidth;
    box.innerHTML =
      '<p class="vs-kicker">' +
      (state.index + 1) +
      " / " +
      pack.steps.length +
      " · " +
      step.title +
      "</p><div class=\"rich-content\">" +
      step.html +
      "</div>";
    box.classList.add("enter");
    $("vsCount").textContent = state.index + 1 + " / " + pack.steps.length;
    $("vsBar").style.width = ((state.index + 1) / pack.steps.length) * 100 + "%";
    state.t0 = performance.now();
    if (state.raf) cancelAnimationFrame(state.raf);
    const tick = (now) => {
      const local = Math.min(1, (now - state.t0) / 900);
      drawFrame(pack, state.index, animateCanvas === false ? 1 : local);
      if (local < 1 && animateCanvas !== false) state.raf = requestAnimationFrame(tick);
    };
    state.raf = requestAnimationFrame(tick);
  }

  function stopTimer() {
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = 0;
    }
    state.playing = false;
    const btn = $("vsPlay");
    if (btn) btn.textContent = "播放";
  }

  function scheduleNext() {
    if (!state.playing) return;
    const html = state.pack.steps[state.index].html || "";
    const wait = Math.min(6500, 2200 + htmlToText(html).length * 18);
    state.timer = setTimeout(() => {
      if (state.index >= state.pack.steps.length - 1) {
        stopTimer();
        return;
      }
      showStep(state.index + 1);
      scheduleNext();
    }, wait);
  }

  function play() {
    if (!state.pack) return;
    if (state.index >= state.pack.steps.length - 1) showStep(0);
    state.playing = true;
    $("vsPlay").textContent = "暂停";
    scheduleNext();
  }

  function open(question) {
    if (!question) return;
    state.question = question;
    state.pack = buildSteps(question);
    const dlg = $("vsDialog");
    $("vsTitle").textContent = "第 " + (question.index || "") + " 题 · 可视化解题";
    $("vsSub").textContent = "用动画把审题、建模、演算串起来，对照下方步骤看“这一步在想什么”。";
    dlg.hidden = false;
    stopTimer();
    showStep(0);
    play();
  }

  function close() {
    stopTimer();
    if (state.raf) cancelAnimationFrame(state.raf);
    $("vsDialog").hidden = true;
  }

  function bind() {
    const dlg = $("vsDialog");
    if (!dlg || dlg.dataset.bound) return;
    dlg.dataset.bound = "1";
    $("vsClose").addEventListener("click", close);
    $("vsBackdrop").addEventListener("click", close);
    $("vsPlay").addEventListener("click", () => {
      if (state.playing) stopTimer();
      else play();
    });
    $("vsPrev").addEventListener("click", () => {
      stopTimer();
      showStep(state.index - 1);
    });
    $("vsNext").addEventListener("click", () => {
      stopTimer();
      showStep(state.index + 1);
    });
    $("vsReplay").addEventListener("click", () => {
      stopTimer();
      showStep(0);
      play();
    });
    document.addEventListener("keydown", (ev) => {
      if ($("vsDialog").hidden) return;
      if (ev.key === "Escape") close();
      if (ev.key === "ArrowRight") {
        stopTimer();
        showStep(state.index + 1);
      }
      if (ev.key === "ArrowLeft") {
        stopTimer();
        showStep(state.index - 1);
      }
      if (ev.key === " ") {
        ev.preventDefault();
        if (state.playing) stopTimer();
        else play();
      }
    });
  }

  window.VisualSolve = { open, close, bind };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
