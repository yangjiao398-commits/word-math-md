(function () {
  const params = new URLSearchParams(location.search);
  const questionId = params.get("question") || "";
  const statusEl = document.getElementById("status");
  const sourceEl = document.getElementById("source");
  const titleEl = document.getElementById("sceneTitle");
  const presetEl = document.getElementById("preset");
  const paramsEl = document.getElementById("params");
  const stepsEl = document.getElementById("steps");
  const stage = document.getElementById("stage");
  let scene = null;
  let keepCurves = false;

  const fields = {
    quadratic: [["a", "a", "1"], ["b", "b", "0"], ["c", "c", "0"]],
    exponential: [["base", "底数", "2"], ["add", "平移", "0"]],
    reciprocal: [["h", "h", "0"], ["k", "k", "1"]],
    "fraction-exp": [["base", "底数", "2"]],
    "linear-reciprocal": [["a", "a", "1"], ["k", "k", "1"]],
    square: [],
  };

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function curveSpec() {
    const preset = presetEl.value;
    const spec = { id: "f", preset: preset, color: "#2457d6", label: "", labelCorner: "left" };
    const box = {};
    paramsEl.querySelectorAll("input").forEach(function (input) {
      box[input.name] = Number(input.value);
    });
    if (preset === "quadratic") {
      spec.quadratic = { a: box.a, b: box.b, c: box.c };
      spec.label = "y = " + box.a + "x² + " + box.b + "x + " + box.c;
    } else if (preset === "exponential") {
      spec.base = box.base;
      spec.add = box.add;
      spec.label = "y = " + box.base + "^x + " + box.add;
    } else if (preset === "reciprocal") {
      spec.reciprocal = { h: box.h, k: box.k };
      spec.label = "y = " + box.k + "/(x - " + box.h + ")";
    } else if (preset === "fraction-exp") {
      spec.base = box.base;
      spec.label = "y = (" + box.base + "^x - 1)/(" + box.base + "^x + 1)";
    } else if (preset === "linear-reciprocal") {
      spec.linearReciprocal = { a: box.a, k: box.k };
      spec.label = "y = " + box.a + "x + " + box.k + "/x";
    } else {
      spec.label = "y = x²";
    }
    return spec;
  }

  function paintParams(curve) {
    const preset = (curve && curve.preset) || presetEl.value;
    presetEl.value = fields[preset] ? preset : "quadratic";
    paramsEl.innerHTML = "";
    fields[presetEl.value].forEach(function (item) {
      const key = item[0];
      const label = document.createElement("label");
      label.textContent = item[1];
      const input = document.createElement("input");
      input.name = key;
      input.type = "number";
      input.step = "any";
      let value = item[2];
      if (curve) {
        const bag = curve.quadratic || curve.reciprocal || curve.linearReciprocal || curve;
        if (bag[key] != null) value = bag[key];
      }
      input.value = value;
      label.appendChild(input);
      paramsEl.appendChild(label);
    });
  }

  function generatedKeepsCurves(next) {
    const curves = (next && next.curves) || [];
    return curves.length > 1 || curves.some(function (curve) { return curve.domain; });
  }

  function readSteps() {
    return Array.from(stepsEl.querySelectorAll(".step-card")).map(function (card, index) {
      const formulas = card.querySelector("[data-formula]").value
        .split("\n")
        .map(function (line) { return line.trim(); })
        .filter(Boolean);
      const original = (scene && scene.steps && scene.steps[index]) || {};
      const next = Object.assign({}, original);
      next.id = original.id || ("step-" + (index + 1));
      next.title = card.querySelector("[data-title]").value.trim() || ("第 " + (index + 1) + " 步");
      next.caption = card.querySelector("[data-caption]").value.trim();
      next.formula = formulas;
      return next;
    }).filter(function (step) { return step.caption; });
  }

  function paintSteps() {
    stepsEl.innerHTML = "";
    (scene.steps || []).forEach(function (step, index) {
      const card = document.createElement("article");
      card.className = "step-card";
      card.innerHTML =
        "<h3>第 " + (index + 1) + " 步</h3>" +
        '<label>标题<input data-title type="text"></label>' +
        '<label>说明<textarea data-caption></textarea></label>' +
        '<label>公式（每行一条 LaTeX）<textarea data-formula></textarea></label>';
      card.querySelector("[data-title]").value = step.title || "";
      card.querySelector("[data-caption]").value = step.caption || "";
      card.querySelector("[data-formula]").value = (step.formula || []).join("\n");
      stepsEl.appendChild(card);
    });
  }

  function buildScene() {
    const next = Object.assign({}, scene || {});
    next.version = 1;
    next.engine = "plane";
    next.title = titleEl.value.trim() || "解题过程";
    next.view = next.view || { xMin: -4, xMax: 4, yMin: -4, yMax: 4 };
    next.steps = readSteps();
    if (!keepCurves) next.curves = [curveSpec()];
    return next;
  }

  function preview() {
    const next = buildScene();
    if (!next.steps.length) {
      setStatus("至少写一步说明。");
      return;
    }
    stage.textContent = "";
    stage.className = "editor-stage";
    window.PlanePlayer.mount(stage, next);
    setStatus("正在预览 " + next.steps.length + " 步。确认后点保存。");
  }

  async function draft() {
    const res = await fetch("/api/plane-scenes/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: sourceEl.value, title: titleEl.value.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "生成草稿失败");
    scene = data.scene;
    keepCurves = generatedKeepsCurves(scene);
    titleEl.value = scene.title || titleEl.value;
    paintParams(scene.curves && scene.curves[0]);
    paintSteps();
    document.getElementById("curveBox").hidden = keepCurves;
    preview();
    const labels = (scene.curves || []).map(function (curve) { return curve.label; }).filter(Boolean);
    setStatus(
      "已根据题干、分析和详解生成 " + scene.steps.length + " 步。"
      + (labels.length ? " 曲线：" + labels.join("、") + "。" : "")
    );
  }

  async function save() {
    if (!questionId) {
      setStatus("缺少题目 id，请从试卷里的「制作解题动画」进入。");
      return;
    }
    const next = buildScene();
    const res = await fetch("/api/plane-scenes/" + encodeURIComponent(questionId), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: next.title, scene: next }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "保存失败");
    setStatus("已保存。回到试卷刷新后，该题会显示「解题过程」。");
  }

  presetEl.addEventListener("change", function () {
    keepCurves = false;
    paintParams(null);
  });
  document.getElementById("draftBtn").addEventListener("click", function () {
    draft().catch(function (err) { setStatus(err.message); });
  });
  document.getElementById("previewBtn").addEventListener("click", preview);
  document.getElementById("saveBtn").addEventListener("click", function () {
    save().catch(function (err) { setStatus(err.message); });
  });

  async function boot() {
    paintParams(null);
    if (!questionId) {
      setStatus("从试卷题目上的「制作解题动画」进入后，会带上题目和详解。");
      scene = {
        title: "解题过程",
        view: { xMin: -4, xMax: 4, yMin: -4, yMax: 4 },
        curves: [curveSpec()],
        steps: [],
      };
      return;
    }
    const res = await fetch("/api/plane-scenes/" + encodeURIComponent(questionId) + "/source");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "读取题目失败");
    document.getElementById("heading").textContent =
      "第 " + (data.question_no || "") + " 题 · 制作解题动画";
    document.getElementById("stem").textContent = data.stem_text || "";
    sourceEl.value = data.source_text || data.solution_text || "";
    titleEl.value = data.lesson && data.lesson.title ? data.lesson.title : ("第 " + (data.question_no || "") + " 题");
    const stale = data.scene && data.scene.meta === "按详解生成的草稿";
    if (data.scene && !stale) {
      scene = data.scene;
      keepCurves = generatedKeepsCurves(scene);
      titleEl.value = scene.title || titleEl.value;
      paintParams(scene.curves && scene.curves[0]);
      paintSteps();
      document.getElementById("curveBox").hidden = keepCurves;
      preview();
      setStatus("已载入保存过的动画。点「根据题目生成动画」会按题干、分析和详解重做。");
    } else if ((sourceEl.value || "").trim()) {
      await draft();
    } else {
      setStatus("还没有题目原文。把题干、分析和详解贴到左侧后再生成。");
    }
  }

  boot().catch(function (err) { setStatus(err.message); });
})();
