/* Open plane-engine lessons attached to a knowledge-point code. */
(function () {
  function esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function ensureDialog() {
    let dlg = document.getElementById("animDialog");
    if (dlg) return dlg;
    dlg = document.createElement("div");
    dlg.id = "animDialog";
    dlg.hidden = true;
    dlg.style.cssText = "position:fixed;inset:0;z-index:80;display:none;align-items:center;justify-content:center;";
    dlg.innerHTML =
      '<div class="kp-backdrop" id="animBackdrop"></div>' +
      '<div class="anim-panel" role="dialog" aria-labelledby="animTitle">' +
      '<h3 id="animTitle">动画演示</h3>' +
      '<p class="summary" id="animHint"></p>' +
      '<div class="cw-layout">' +
      '<ul class="cw-list" id="animList"></ul>' +
      '<div class="cw-view">' +
      '<iframe id="animFrame" title="知识点动画演示"></iframe>' +
      "</div></div>" +
      '<div class="anim-actions">' +
      '<a id="animOpen" href="#" target="_blank" rel="noopener">在新页面打开</a>' +
      '<button type="button" class="secondary" id="animClose">关闭</button>' +
      "</div></div>";
    document.body.appendChild(dlg);
    const backdrop = document.getElementById("animBackdrop");
    backdrop.style.cssText = "position:absolute;inset:0;background:rgba(0,0,0,.55);";
    dlg.querySelector(".anim-panel").style.cssText =
      "position:relative;z-index:1;width:min(1080px,96vw);max-height:92vh;overflow:auto;" +
      "background:#1a222c;color:#e8eef5;border:1px solid #2a3542;border-radius:14px;padding:16px;";
    document.getElementById("animFrame").style.cssText =
      "width:100%;height:68vh;min-height:420px;border:0;border-radius:10px;background:#f4f6f8;";
    backdrop.addEventListener("click", close);
    document.getElementById("animClose").addEventListener("click", close);
    return dlg;
  }

  function close() {
    const dlg = document.getElementById("animDialog");
    if (!dlg) return;
    dlg.hidden = true;
    dlg.style.display = "none";
    const frame = document.getElementById("animFrame");
    if (frame) frame.src = "about:blank";
  }

  function showLesson(lesson) {
    const frame = document.getElementById("animFrame");
    const open = document.getElementById("animOpen");
    const href = lesson && typeof lesson.href === "string" ? lesson.href : "";
    if (frame) frame.src = href || "about:blank";
    if (open) {
      open.href = href || "#";
      open.textContent = href ? "在新页面打开" : "在新页面打开";
    }
    document.querySelectorAll("#animList li").forEach(function (li) {
      li.classList.toggle("active", li.dataset.id === (lesson && lesson.id));
    });
  }

  function open(code, lessons) {
    const dlg = ensureDialog();
    const items = Array.isArray(lessons) ? lessons : [];
    document.getElementById("animTitle").textContent = code + " · 动画演示";
    document.getElementById("animHint").textContent =
      "选择一段演示。画面按步骤播放，可以前进、后退和重播。";
    const list = document.getElementById("animList");
    list.innerHTML = items
      .map(function (lesson, i) {
        return (
          '<li data-id="' + esc(lesson.id || String(i)) + '">' +
          '<button type="button" class="cw-pick" data-anim-pick="' + i + '">' +
          esc(lesson.title || "演示") +
          "</button></li>"
        );
      })
      .join("");
    list.querySelectorAll("[data-anim-pick]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showLesson(items[Number(btn.getAttribute("data-anim-pick"))]);
      });
    });
    dlg.hidden = false;
    dlg.style.display = "flex";
    showLesson(items[items.length - 1] || null);
  }

  window.KnowledgeAnimations = { open: open, close: close };
})();
