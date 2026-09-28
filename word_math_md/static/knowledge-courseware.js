/* Browse PPT courseware linked to knowledge-point codes. */
(function () {
  function esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  async function readJson(res) {
    const raw = await res.text();
    try {
      return JSON.parse(raw);
    } catch (e) {
      throw new Error(raw.slice(0, 180) || "接口未返回 JSON");
    }
  }

  function formatSize(n) {
    const v = Number(n) || 0;
    if (v < 1024) return v + " B";
    if (v < 1024 * 1024) return (v / 1024).toFixed(1) + " KB";
    return (v / (1024 * 1024)).toFixed(1) + " MB";
  }

  function ensureDialog() {
    let dlg = document.getElementById("cwDialog");
    if (dlg) return dlg;
    dlg = document.createElement("div");
    dlg.id = "cwDialog";
    dlg.hidden = true;
    dlg.innerHTML =
      '<div class="kp-backdrop" id="cwBackdrop"></div>' +
      '<div class="kp-panel cw-panel" role="dialog" aria-labelledby="cwTitle">' +
      '<h3 id="cwTitle">知识点课件</h3>' +
      '<p class="summary" id="cwHint"></p>' +
      '<div class="cw-layout">' +
      '<ul class="cw-list" id="cwList"></ul>' +
      '<div class="cw-view">' +
      '<iframe id="cwFrame" title="PPT 预览" allowfullscreen></iframe>' +
      '<p class="muted" id="cwViewHint">选择左侧课件在线预览（Office Online）。也可下载到本地用 PowerPoint 打开。</p>' +
      "</div></div>" +
      '<div class="kp-actions">' +
      '<a id="cwDownload" href="#" target="_blank" rel="noopener">下载当前课件</a>' +
      '<button type="button" class="secondary" id="cwClose">关闭</button>' +
      "</div></div>";
    document.body.appendChild(dlg);
    document.getElementById("cwBackdrop").addEventListener("click", close);
    document.getElementById("cwClose").addEventListener("click", close);
    return dlg;
  }

  function close() {
    const dlg = document.getElementById("cwDialog");
    if (!dlg) return;
    dlg.hidden = true;
    const frame = document.getElementById("cwFrame");
    if (frame) frame.src = "about:blank";
  }

  function showItem(item) {
    const frame = document.getElementById("cwFrame");
    const dl = document.getElementById("cwDownload");
    const hint = document.getElementById("cwViewHint");
    if (!item) {
      if (frame) frame.src = "about:blank";
      if (dl) dl.href = "#";
      return;
    }
    const view = item.office_view_url || item.public_url || "";
    if (frame) frame.src = view || "about:blank";
    if (dl) {
      dl.href = item.public_url || "#";
      dl.textContent = "下载：" + (item.filename || item.title || "课件");
    }
    if (hint) {
      hint.textContent = view
        ? "正在通过 Office Online 预览。若无法显示，请用右侧下载链接在本地打开。"
        : "暂无预览地址。";
    }
    document.querySelectorAll(".cw-list li").forEach((li) => {
      li.classList.toggle("active", li.dataset.id === item.id);
    });
  }

  async function deleteItem(id, onDone) {
    if (!confirm("确定删除这份课件？")) return;
    const res = await fetch("/api/exam-bank/knowledge-courseware/" + encodeURIComponent(id), {
      method: "DELETE",
    });
    const data = await readJson(res);
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    if (onDone) onDone();
  }

  async function openForCodes(codes, title, options) {
    options = options || {};
    const cleaned = [...new Set((codes || []).map((c) => String(c || "").trim()).filter(Boolean))];
    if (!cleaned.length) {
      alert("没有关联的知识点编号。");
      return;
    }
    ensureDialog();
    const dlg = document.getElementById("cwDialog");
    const listEl = document.getElementById("cwList");
    document.getElementById("cwTitle").textContent = title || "知识点 PPT 课件";
    document.getElementById("cwHint").textContent = "知识点：" + cleaned.join("、");
    listEl.innerHTML = "<li class=\"muted\">加载中…</li>";
    dlg.hidden = false;
    const res = await fetch(
      "/api/exam-bank/knowledge-courseware?codes=" + encodeURIComponent(cleaned.join(","))
    );
    const data = await readJson(res);
    if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
    const grouped = data.by_code || {};
    const items = [];
    cleaned.forEach((code) => {
      (grouped[code] || []).forEach((row) => items.push(row));
    });
    if (!items.length) {
      listEl.innerHTML =
        '<li class="muted">这些知识点还没有上传 PPT。请到 <a href="/knowledge">知识点维护</a> 页面上传。</li>';
      showItem(null);
      return;
    }
    listEl.innerHTML = items
      .map(
        (row) =>
          '<li data-id="' +
          esc(row.id) +
          '"><div class="cw-row-top"><button type="button" class="cw-pick">' +
          esc(row.knowledge_code) +
          " · " +
          esc(row.title || row.filename) +
          '</button>' +
          (options.manage
            ? '<button type="button" class="secondary cw-del" style="width:auto;padding:4px 8px;font-size:0.75rem">删除</button>'
            : "") +
          '</div><span class="muted">' +
          esc(formatSize(row.byte_size)) +
          "</span></li>"
      )
      .join("");
    listEl.querySelectorAll(".cw-pick").forEach((btn, i) => {
      btn.addEventListener("click", () => showItem(items[i]));
    });
    if (options.manage) {
      listEl.querySelectorAll(".cw-del").forEach((btn, i) => {
        btn.addEventListener("click", async (ev) => {
          ev.stopPropagation();
          try {
            await deleteItem(items[i].id, () =>
              openForCodes(cleaned, title, options).catch((err) => alert(err.message))
            );
          } catch (err) {
            alert("删除失败: " + err.message);
          }
        });
      });
    }
    showItem(items[0]);
  }

  window.KnowledgeCourseware = { openForCodes, close };
})();
