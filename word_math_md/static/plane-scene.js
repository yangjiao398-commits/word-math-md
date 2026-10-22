/* Plane scene player. Renders a version-1 scene: axes, one preset curve, intervals, and point pairs. */
(function () {
  const TONE = {
    down: "#c2413a",
    up: "#0f7a4a",
    neutral: "#2a6fdb",
  };

  function compileFn(spec) {
    if (spec.preset === "square") return function (x) { return x * x; };
    if (spec.preset === "quadratic") {
      const q = spec.quadratic || {};
      const a = Number(q.a);
      const b = Number(q.b);
      const c = Number(q.c);
      return function (x) { return a * x * x + b * x + c; };
    }
    if (spec.preset === "exponential") {
      const base = Number(spec.base);
      const add = Number(spec.add || 0);
      if (!(base > 0) || base === 1) throw new Error("指数函数的底数必须大于 0 且不等于 1");
      return function (x) { return Math.pow(base, x) + add; };
    }
    if (spec.preset === "reciprocal") {
      const r = spec.reciprocal || {};
      const h = Number(r.h);
      const k = Number(r.k);
      if (!Number.isFinite(h) || !Number.isFinite(k) || k === 0) {
        throw new Error("反比例型函数需要有限的平移和不为 0 的系数");
      }
      return function (x) { return k / (x - h); };
    }
    if (spec.preset === "fraction-exp") {
      const base = Number(spec.base);
      if (!(base > 0) || base === 1) throw new Error("指数型分式的底数必须大于 0 且不等于 1");
      return function (x) {
        const p = Math.pow(base, x);
        return (p - 1) / (p + 1);
      };
    }
    if (spec.preset === "linear-reciprocal") {
      const q = spec.linearReciprocal || {};
      const a = Number(q.a);
      const k = Number(q.k);
      if (!Number.isFinite(a) || !Number.isFinite(k) || k === 0) {
        throw new Error("一次加反比例需要有限系数，且反比例系数不为 0");
      }
      return function (x) { return a * x + k / x; };
    }
    throw new Error("未知的平面函数预设：" + spec.preset);
  }

  function buildCurves(scene) {
    if (Array.isArray(scene.curves) && scene.curves.length) {
      return scene.curves.map(function (spec) {
        return {
          id: spec.id,
          fn: compileFn(spec),
          color: spec.color || "#2457d6",
          label: spec.label || "",
          labelAt: spec.labelAt,
          labelCorner: spec.labelCorner,
          domain: spec.domain || null,
        };
      });
    }
    return [{
      id: "f",
      fn: compileFn(scene),
      color: "#2457d6",
      label: scene.curveLabel || "f(x) = x²",
      labelAt: null,
    }];
  }

  function formatNum(n) {
    const v = Math.round(n * 100) / 100;
    if (Object.is(v, -0)) return "0";
    return String(v);
  }

  function relation(y1, y2) {
    if (y1 > y2 + 1e-9) return ">";
    if (y1 < y2 - 1e-9) return "<";
    return "=";
  }

  function mount(root, scene, options) {
    const autoplay = !!(options && options.autoplay);
    const curves = buildCurves(scene);
    let view = scene.view;
    root.innerHTML =
      '<div class="plane">' +
      '<canvas aria-hidden="true"></canvas>' +
      '<div class="plane-readout" aria-live="polite"></div>' +
      '<div class="plane-title"></div>' +
      '<p class="plane-caption"></p>' +
      '<div class="plane-formula"></div>' +
      '<div class="plane-controls">' +
      '<button type="button" data-act="prev">上一步</button>' +
      '<button type="button" class="primary" data-act="replay">重播这一步</button>' +
      '<button type="button" data-act="next">下一步</button>' +
      '<button type="button" data-act="auto">从头播放</button>' +
      '<span class="plane-count"></span>' +
      "</div>" +
      '<div class="plane-jumps"></div>' +
      "</div>";

    const canvas = root.querySelector("canvas");
    const readout = root.querySelector(".plane-readout");
    const titleEl = root.querySelector(".plane-title");
    const captionEl = root.querySelector(".plane-caption");
    const formulaEl = root.querySelector(".plane-formula");
    const countEl = root.querySelector(".plane-count");
    const jumps = root.querySelector(".plane-jumps");
    const ctx = canvas.getContext("2d");
    const steps = scene.steps;
    let index = 0;
    let token = 0;
    let auto = autoplay;
    let timer = 0;
    let frameState = { reveal: 0, pair: 0 };

    steps.forEach(function (step, i) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = i + 1 + " " + step.title;
      btn.addEventListener("click", function () {
        auto = false;
        go(i);
      });
      jumps.appendChild(btn);
    });

    root.querySelector('[data-act="prev"]').addEventListener("click", function () {
      auto = false;
      go(index - 1);
    });
    root.querySelector('[data-act="next"]').addEventListener("click", function () {
      auto = false;
      go(index + 1);
    });
    root.querySelector('[data-act="replay"]').addEventListener("click", function () {
      auto = false;
      go(index);
    });
    root.querySelector('[data-act="auto"]').addEventListener("click", function () {
      auto = !auto;
      if (auto) go(0);
      else stopMotion();
      paintControls();
    });

    function stopMotion() {
      token += 1;
      window.clearTimeout(timer);
    }

    function paintControls() {
      root.querySelector('[data-act="prev"]').disabled = index === 0;
      root.querySelector('[data-act="next"]').disabled = index === steps.length - 1;
      root.querySelector('[data-act="auto"]').textContent = auto ? "暂停" : "从头播放";
      countEl.textContent = "第 " + (index + 1) + " / " + steps.length + " 步";
      jumps.querySelectorAll("button").forEach(function (btn, i) {
        if (i === index) btn.setAttribute("aria-current", "true");
        else btn.removeAttribute("aria-current");
      });
    }

    function plotRect() {
      const pad = { l: 52, r: 22, t: 26, b: 42 };
      return {
        x: pad.l,
        y: pad.t,
        w: canvas.clientWidth - pad.l - pad.r,
        h: canvas.clientHeight - pad.t - pad.b,
      };
    }

    function toPx(x, y) {
      const plot = plotRect();
      const sx = plot.w / (view.xMax - view.xMin);
      const sy = plot.h / (view.yMax - view.yMin);
      return [plot.x + (x - view.xMin) * sx, plot.y + (view.yMax - y) * sy];
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const bw = Math.max(1, Math.round(w * dpr));
      const bh = Math.max(1, Math.round(h * dpr));
      if (canvas.width !== bw || canvas.height !== bh) {
        canvas.width = bw;
        canvas.height = bh;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function drawFrame(progress) {
      frameState = progress;
      if (canvas.clientWidth < 40) return;
      resize();
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const step = steps[index];
      view = (step && step.view) || scene.view;
      ctx.clearRect(0, 0, w, h);
      const markers = markersAt(step, progress.pair);

      (step.intervals || []).forEach(function (interval) {
        const top = toPx(interval.from, view.yMax);
        const bot = toPx(interval.to, view.yMin);
        ctx.fillStyle = interval.tone === "up" ? "rgba(15,122,74,0.10)" : "rgba(194,65,58,0.10)";
        ctx.fillRect(top[0], top[1], bot[0] - top[0], bot[1] - top[1]);
      });

      ctx.save();
      ctx.beginPath();
      const clipA = toPx(view.xMin, view.yMax);
      const clipB = toPx(view.xMax, view.yMin);
      ctx.rect(clipA[0], clipA[1], clipB[0] - clipA[0], clipB[1] - clipA[1]);
      ctx.clip();
      drawGrid();
      drawAxes();
      drawGuides(step);
      drawCurve(progress.reveal, step);
      drawSecants(markers);
      drawVertex(step, markers);
      drawMarkers(markers);
      ctx.restore();
      drawIntervalLabels(step);
      writeReadout(markers);
    }

    function drawGrid() {
      ctx.save();
      ctx.strokeStyle = "#e6ebf2";
      ctx.lineWidth = 1;
      ctx.font = "12px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.fillStyle = "#8b97a6";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      for (let x = Math.ceil(view.xMin); x <= Math.floor(view.xMax); x += 1) {
        const p = toPx(x, 0);
        const top = toPx(x, view.yMax);
        const bot = toPx(x, view.yMin);
        ctx.beginPath();
        ctx.moveTo(top[0], top[1]);
        ctx.lineTo(bot[0], bot[1]);
        ctx.stroke();
        if (x !== 0) ctx.fillText(String(x), p[0], p[1] + 6);
      }
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      for (let y = Math.ceil(view.yMin); y <= Math.floor(view.yMax); y += 1) {
        if (y === 0) continue;
        const left = toPx(view.xMin, y);
        const right = toPx(view.xMax, y);
        const p = toPx(0, y);
        ctx.beginPath();
        ctx.moveTo(left[0], left[1]);
        ctx.lineTo(right[0], right[1]);
        ctx.stroke();
        ctx.fillText(String(y), p[0] - 8, p[1]);
      }
      ctx.restore();
    }

    function drawAxes() {
      const origin = toPx(0, 0);
      const xEnd = toPx(view.xMax, 0);
      const yEnd = toPx(0, view.yMax);
      const xStart = toPx(view.xMin, 0);
      const yStart = toPx(0, view.yMin);
      ctx.save();
      ctx.strokeStyle = "#1c2430";
      ctx.fillStyle = "#1c2430";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(xStart[0], origin[1]);
      ctx.lineTo(xEnd[0] - 8, origin[1]);
      ctx.moveTo(origin[0], yStart[1]);
      ctx.lineTo(origin[0], yEnd[1] + 8);
      ctx.stroke();
      arrowHead(xEnd[0] - 2, origin[1], 0);
      arrowHead(origin[0], yEnd[1] + 2, -Math.PI / 2);
      ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("x", xEnd[0] - 14, origin[1] + 8);
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      ctx.fillText("y", origin[0] - 8, yEnd[1] + 16);
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("O", origin[0] + 4, origin[1] + 4);
      ctx.restore();
    }

    function arrowHead(x, y, angle) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - 8 * Math.cos(angle - 0.4), y - 8 * Math.sin(angle - 0.4));
      ctx.lineTo(x - 8 * Math.cos(angle + 0.4), y - 8 * Math.sin(angle + 0.4));
      ctx.closePath();
      ctx.fill();
    }

    function curveById(id) {
      for (let i = 0; i < curves.length; i += 1) {
        if (curves[i].id === id) return curves[i];
      }
      return curves[0];
    }

    function visibleCurves(step) {
      const ids = step.curves;
      if (!ids || !ids.length) return curves;
      return ids.map(curveById);
    }

    function fn(x) {
      const step = steps[index];
      const id = step && (step.curve || (step.curves && step.curves[0]));
      return curveById(id).fn(x);
    }

    function drawCurve(reveal, step) {
      const n = 240;
      const shown = visibleCurves(step);
      const last = Math.max(1, Math.floor(n * reveal));
      shown.forEach(function (curve) {
        ctx.save();
        ctx.strokeStyle = curve.color;
        ctx.lineWidth = 2.4;
        ctx.lineJoin = "round";
        ctx.beginPath();
        let started = false;
        for (let i = 0; i <= last; i += 1) {
          const x = view.xMin + ((view.xMax - view.xMin) * i) / n;
          const y = curve.fn(x);
          const domain = curve.domain;
          const outside = domain && (
            (typeof domain.from === "number" && x < domain.from) ||
            (typeof domain.to === "number" && x > domain.to)
          );
          if (outside || !Number.isFinite(y)) {
            started = false;
            continue;
          }
          const p = toPx(x, y);
          if (!started) {
            ctx.moveTo(p[0], p[1]);
            started = true;
          } else ctx.lineTo(p[0], p[1]);
        }
        ctx.stroke();
        if (reveal > 0.92 && curve.label && !(step.intervals || []).length) {
          ctx.fillStyle = curve.color;
          ctx.font = "14px Segoe UI, Microsoft YaHei, sans-serif";
          if (curve.labelCorner === "left" || curve.labelCorner === "right") {
            const onRight = curve.labelCorner === "right";
            const corner = toPx(onRight ? view.xMax : view.xMin, view.yMax);
            ctx.textAlign = onRight ? "right" : "left";
            ctx.textBaseline = "top";
            ctx.fillText(curve.label, corner[0] + (onRight ? -10 : 10), corner[1] + 8);
          } else if (typeof curve.labelAt === "number") {
            const at = toPx(curve.labelAt, curve.fn(curve.labelAt));
            ctx.textAlign = curve.labelAt >= 0 ? "left" : "right";
            ctx.textBaseline = "bottom";
            ctx.fillText(curve.label, at[0] + (curve.labelAt >= 0 ? 8 : -8), at[1] - 8);
          } else if (shown.length === 1) {
            const onRight = scene.curveLabelAnchor === "right";
            const corner = toPx(onRight ? view.xMax : view.xMin, view.yMax);
            ctx.textAlign = onRight ? "right" : "left";
            ctx.textBaseline = "top";
            ctx.fillText(curve.label, corner[0] + (onRight ? -10 : 10), corner[1] + 8);
          }
        }
        ctx.restore();
      });
    }

    function drawGuides(step) {
      (step.guides || []).forEach(function (guide) {
        if (typeof guide.y === "number" && typeof guide.x !== "number") {
          const left = toPx(view.xMin, guide.y);
          const right = toPx(view.xMax, guide.y);
          ctx.save();
          ctx.fillStyle = "#1c2430";
          ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
          ctx.textAlign = "right";
          ctx.textBaseline = "bottom";
          if (Math.abs(guide.y) > 0.05) {
            ctx.strokeStyle = "#5c6b7a";
            ctx.lineWidth = 1.25;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(left[0], left[1]);
            ctx.lineTo(right[0], right[1]);
            ctx.stroke();
            ctx.setLineDash([]);
          }
          ctx.fillText(guide.label || "", right[0] - 18, right[1] - 6);
          ctx.restore();
          return;
        }
        const top = toPx(guide.x, view.yMax);
        const bot = toPx(guide.x, view.yMin);
        const mid = toPx(guide.x, (view.yMin + view.yMax) / 2);
        ctx.save();
        ctx.strokeStyle = "#5c6b7a";
        ctx.fillStyle = "#1c2430";
        ctx.lineWidth = 1.25;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(top[0], top[1]);
        ctx.lineTo(bot[0], bot[1]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(guide.label, mid[0] + 8, mid[1]);
        ctx.restore();
      });
    }

    function drawVertex(step, markers) {
      if (!step.vertex) return;
      const x = step.vertex.x;
      const y = fn(x);
      const p = toPx(x, y);
      const covered = markers.some(function (marker) {
        return Math.abs(marker.x - x) < 0.05;
      });
      ctx.save();
      ctx.fillStyle = "#2457d6";
      ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "bottom";
      if (!covered) {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 5.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#fff";
        ctx.stroke();
      }
      ctx.fillText(step.vertex.label, p[0] + 10, p[1] - 10);
      ctx.restore();
    }

    function drawSecants(markers) {
      for (let i = 0; i + 1 < markers.length; i += 2) {
        const a = markers[i];
        const b = markers[i + 1];
        const p1 = toPx(a.x, fn(a.x));
        const p2 = toPx(b.x, fn(b.x));
        ctx.save();
        ctx.strokeStyle = TONE[a.tone] || TONE.neutral;
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(p1[0], p1[1]);
        ctx.lineTo(p2[0], p2[1]);
        ctx.stroke();
        ctx.restore();
      }
    }

    function drawMarkers(markers) {
      markers.forEach(function (marker, i) {
        const y = fn(marker.x);
        const onCurve = toPx(marker.x, y);
        const onAxis = toPx(marker.x, 0);
        const color = TONE[marker.tone] || TONE.neutral;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(onCurve[0], onCurve[1]);
        ctx.lineTo(onAxis[0], onAxis[1]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.arc(onCurve[0], onCurve[1], 5.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#fff";
        ctx.stroke();
        ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
        ctx.textAlign = i % 2 === 0 ? "right" : "left";
        ctx.textBaseline = "middle";
        const lift = Math.abs(y) < 0.55 ? -16 : 0;
        ctx.fillText(marker.name, onCurve[0] + (i % 2 === 0 ? -10 : 10), onCurve[1] + lift);
        ctx.restore();
      });
    }

    function drawIntervalLabels(step) {
      ctx.save();
      ctx.font = "13px Segoe UI, Microsoft YaHei, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      (step.intervals || []).forEach(function (interval) {
        let midX = (interval.from + interval.to) / 2;
        if (Math.abs(midX) < 0.85) midX = midX < 0 ? interval.from + 0.55 : interval.to - 0.55;
        const mid = toPx(midX, view.yMax);
        ctx.fillStyle = TONE[interval.tone] || TONE.neutral;
        ctx.fillText(interval.label, mid[0], mid[1] + 18);
      });
      ctx.restore();
    }

    function markersAt(step, t) {
      if (step.motion && step.motion.type === "pair") {
        const motion = step.motion;
        const x1 = motion.x1From + (motion.x1To - motion.x1From) * t;
        return [
          { x: x1, name: "x₁", tone: motion.tone },
          { x: x1 + motion.gap, name: "x₂", tone: motion.tone },
        ];
      }
      return step.markers || [];
    }

    function writeReadout(markers) {
      if (markers.length < 2) {
        readout.textContent = "";
        return;
      }
      const parts = [];
      for (let i = 0; i + 1 < markers.length; i += 2) {
        const a = markers[i];
        const b = markers[i + 1];
        const y1 = fn(a.x);
        const y2 = fn(b.x);
        parts.push(
          a.name + " = " + formatNum(a.x) + "，" + b.name + " = " + formatNum(b.x) +
          "，f(" + a.name + ") = " + formatNum(y1) + "，f(" + b.name + ") = " + formatNum(y2) +
          "，f(" + a.name + ") " + relation(y1, y2) + " f(" + b.name + ")"
        );
      }
      readout.textContent = parts.join("；");
    }

    function renderCopy(step) {
      titleEl.textContent = step.title;
      captionEl.textContent = step.caption;
      formulaEl.innerHTML = "";
      (step.formula || []).forEach(function (latex) {
        const line = document.createElement("div");
        line.className = "line";
        formulaEl.appendChild(line);
        if (window.katex) {
          window.katex.render(latex, line, { throwOnError: false, displayMode: true });
        } else {
          line.textContent = latex;
        }
      });
    }

    function go(nextIndex) {
      index = Math.max(0, Math.min(steps.length - 1, nextIndex));
      stopMotion();
      const my = token;
      const step = steps[index];
      renderCopy(step);
      paintControls();
      const motion = step.motion;
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduce) {
        drawFrame({ reveal: 1, pair: 1 });
        queueAuto(my, 1800);
        return;
      }
      if (step.draw) animate(900, function (t) { drawFrame({ reveal: ease(t), pair: 0 }); }, my);
      else if (motion) animate(2800, function (t) { drawFrame({ reveal: 1, pair: ease(t) }); }, my);
      else {
        drawFrame({ reveal: 1, pair: 0 });
        queueAuto(my, 2200);
      }
    }

    function ease(t) {
      return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    }

    function animate(ms, frame, my) {
      const t0 = performance.now();
      function tick(now) {
        if (my !== token) return;
        const t = Math.min(1, (now - t0) / ms);
        frame(t);
        if (t < 1) requestAnimationFrame(tick);
        else queueAuto(my, 800);
      }
      requestAnimationFrame(tick);
    }

    function queueAuto(my, wait) {
      if (!auto || index >= steps.length - 1) {
        if (index >= steps.length - 1) auto = false;
        paintControls();
        return;
      }
      const caption = (steps[index] && steps[index].caption) || "";
      const read = Math.min(6400, 1400 + caption.length * 32);
      timer = window.setTimeout(function () {
        if (my !== token || !auto) return;
        go(index + 1);
      }, Math.max(wait, read));
    }

    new ResizeObserver(function () {
      drawFrame(frameState);
    }).observe(canvas);

    go(0);
  }

  window.PlanePlayer = { mount: mount };
})();
