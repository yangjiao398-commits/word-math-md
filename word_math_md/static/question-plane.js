/* Plane solution scenes attached to stored exam questions. */
(function () {
  const lessons = {
    "ac94d186-2233-4a03-ae46-88e390073595": {
      title: "第1题 · 全称命题的否定",
      href: "/static/plane-sz-q1.html?embed=1",
    },
    "c9a09c8c-1e42-4907-9f4a-80770c2048a5": {
      title: "第2题 · 分段函数求值",
      href: "/static/plane-sz-q2.html?embed=1",
    },
    "4129cbd6-c865-4b57-8d48-3c1b6a0ab0c8": {
      title: "第7题 · 奇函数与基本不等式",
      href: "/static/plane-sz-q7.html?embed=1&v=2",
    },
  };

  function ensureDialog() {
    let dlg = document.getElementById("planeSolveDialog");
    if (dlg) return dlg;
    dlg = document.createElement("div");
    dlg.id = "planeSolveDialog";
    dlg.hidden = true;
    dlg.style.cssText = "position:fixed;inset:0;z-index:90;display:none;background:#10161d;";
    dlg.innerHTML =
      '<div role="dialog" aria-labelledby="planeSolveTitle" style="position:absolute;inset:0;display:flex;flex-direction:column;box-sizing:border-box;padding:10px 12px 12px;">' +
      '<div id="planeSolveBar">' +
      '<h3 id="planeSolveTitle">解题过程</h3>' +
      '<a id="planeSolveOpen" href="#" target="_blank" rel="noopener">在新页面打开</a>' +
      '<button type="button" id="planeSolveClose">关闭</button>' +
      "</div>" +
      '<iframe id="planeSolveFrame" title="解题过程动画" allowfullscreen></iframe>' +
      "</div>";
    document.body.appendChild(dlg);
    document.getElementById("planeSolveBar").style.cssText =
      "display:flex;align-items:center;gap:12px;flex:none;margin:0 0 8px;color:#e8eef5;";
    document.getElementById("planeSolveTitle").style.cssText =
      "margin:0;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:1.05rem;font-weight:680;";
    const openLink = document.getElementById("planeSolveOpen");
    openLink.style.cssText = "flex:none;white-space:nowrap;color:#8ebff5;";
    document.getElementById("planeSolveClose").style.cssText =
      "flex:none;width:auto;white-space:nowrap;padding:8px 14px;border-radius:8px;border:0;background:#2a3542;color:#e8eef5;cursor:pointer;";
    document.getElementById("planeSolveFrame").style.cssText =
      "flex:1;width:100%;height:100%;min-height:0;border:0;border-radius:10px;background:#f4f6f8;";
    document.getElementById("planeSolveClose").addEventListener("click", close);
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") close();
    });
    return dlg;
  }

  function close() {
    const dlg = document.getElementById("planeSolveDialog");
    if (!dlg || dlg.hidden) return;
    if (document.fullscreenElement === dlg && document.exitFullscreen) {
      document.exitFullscreen().catch(function () {});
    }
    dlg.hidden = true;
    dlg.style.display = "none";
    const frame = document.getElementById("planeSolveFrame");
    if (frame) frame.src = "about:blank";
  }

  function open(questionId) {
    const lesson = lessons[questionId];
    if (!lesson) return;
    const dlg = ensureDialog();
    document.getElementById("planeSolveTitle").textContent = lesson.title || "解题过程";
    const frame = document.getElementById("planeSolveFrame");
    const link = document.getElementById("planeSolveOpen");
    frame.src = lesson.href;
    link.href = lesson.href.split("?")[0];
    dlg.hidden = false;
    dlg.style.display = "block";
    if (dlg.requestFullscreen) dlg.requestFullscreen().catch(function () {});
  }

  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest("[data-plane-q]");
    if (!btn) return;
    ev.preventDefault();
    open(btn.getAttribute("data-plane-q") || "");
  });

  window.QuestionPlane = { lessons: lessons, open: open, close: close };
})();
