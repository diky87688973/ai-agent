/* 视觉帧工具壳：SSE 到达的帧必须与模型下一次请求使用的那一帧一致。 */
(function () {
  "use strict";

  var PLUGIN = "visual_operator_2";
  var STYLE_ID = "visionFrameStyle";
  var activeModal = null;

  function currentConversationID() {
    var tab = (typeof getActiveTab === "function") ? getActiveTab() : null;
    return String((tab && tab.id) || (typeof getActiveConversationId === "function"
      ? getActiveConversationId() : "") || "");
  }

  function frameSummary(data) {
    var cursor = data && data.cursor || {};
    var scale = Number(data && data.full_scale);
    return "frame=" + String(data.frame_id || "") +
      " · age=" + String(data.age_ms || 0) + "ms" +
      " · cursor=(" + String(cursor.x || 0) + "," + String(cursor.y || 0) + ")" +
      (isFinite(scale) ? " · scale=" + scale.toFixed(2) : "");
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      ".vision-frame-card .vision-frame-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px 0;}",
      ".chat-tool-row--status{border:1px solid rgba(127,127,127,.28);border-radius:8px;background:rgba(127,127,127,.06);margin:8px 0;}",
      ".chat-tool-row--status .chat-tool-head{display:flex;align-items:center;padding:9px 12px;cursor:default;}",
      ".vision-frame-thumb{display:block;width:100%;padding:0;border:1px solid rgba(127,127,127,.35);border-radius:8px;background:#111;overflow:hidden;cursor:zoom-in;text-align:left;color:inherit;}",
      ".vision-frame-thumb img{display:block;width:auto;max-width:100%;height:auto;max-height:260px;object-fit:contain;background:#0b0b0b;}",
      ".vision-frame-thumb span{display:block;padding:6px 8px;font-size:11px;color:#9aa4b2;}",
      ".vision-frame-meta{padding:0 0 10px;font-size:11px;line-height:1.7;color:#9aa4b2;word-break:break-all;}",
      ".vision-frame-modal{position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.82);display:flex;align-items:center;justify-content:center;padding:24px;}",
      ".vision-frame-dialog{width:min(96vw,1500px);max-height:94vh;overflow:auto;background:#151820;border:1px solid rgba(127,127,127,.4);border-radius:12px;padding:14px;color:#e7edf6;}",
      ".vision-frame-dialog-head{display:flex;align-items:center;gap:12px;margin-bottom:10px;}",
      ".vision-frame-dialog-head b{font-size:14px;}",
      ".vision-frame-dialog-head span{font-size:11px;color:#9aa4b2;flex:1;}",
      ".vision-frame-dialog-head button{border:1px solid rgba(127,127,127,.4);background:transparent;color:inherit;border-radius:6px;padding:4px 10px;cursor:pointer;}",
      ".vision-frame-dialog-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start;overflow:auto;}",
      ".vision-frame-dialog figure{margin:0;min-width:0;}",
      ".vision-frame-dialog figcaption{font-size:12px;color:#9aa4b2;margin-bottom:6px;}",
      ".vision-frame-dialog img{display:block;width:auto;height:auto;max-width:none;max-height:none;object-fit:contain;background:#0b0b0b;border-radius:8px;}",
      "@media(max-width:900px){.vision-frame-grid,.vision-frame-dialog-grid{grid-template-columns:1fr;}}"
    ].join("\n");
    (document.head || document.documentElement).appendChild(style);
  }

  function modelSize(size) {
    var pair = Array.isArray(size) ? size : [];
    if (pair.length < 2) return "模型输入尺寸未知";
    return "模型输入 " + String(pair[0]) + "×" + String(pair[1]);
  }

  function makeThumb(src, label, data) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "vision-frame-thumb";
    button.setAttribute("data-vision-frame-open", "1");
    var image = document.createElement("img");
    image.alt = label;
    image.src = String(src || "");
    var caption = document.createElement("span");
    caption.textContent = label + " · " + modelSize(label === "完整图"
      ? data.full_size : (data.focus && data.focus.image_size));
    button.appendChild(image);
    button.appendChild(caption);
    button._visionFrameData = data;
    return button;
  }

  function renderControlReturned(data) {
    if (!data || !data.conversation_id) return;
    if (String(data.conversation_id) !== currentConversationID()) return;
    if (typeof makeChatToolRow !== "function" || typeof appendChatToolRow !== "function") return;
    ensureStyle();
    var row = document.createElement("div");
    row.className = "chat-tool-row chat-tool-row--status";
    var head = document.createElement("div");
    head.className = "chat-tool-head";
    var title = document.createElement("span");
    title.className = "chat-tool-title";
    title.textContent = "已归还用户控制";
    head.appendChild(title);
    row.appendChild(head);
    appendChatToolRow(row);
  }

  function renderFrame(data) {
    if (!data || !data.frame_id || !data.conversation_id) return;
    if (String(data.conversation_id) !== currentConversationID()) return;
    if (typeof makeChatToolRow !== "function" || typeof appendChatToolRow !== "function") return;

    ensureStyle();
    var row = makeChatToolRow("视觉帧", frameSummary(data));
    row.classList.add("vision-frame-card");
    row._visionFrameData = data;

    var meta = document.createElement("div");
    meta.className = "vision-frame-meta";
    var focus = data.focus || {};
    meta.textContent = [
      "screen=" + JSON.stringify(data.screen_size || []),
      "full=" + JSON.stringify(data.full_size || []),
      "full_scale=" + Number(data.full_scale || 0).toFixed(3),
      "focus=(" + Number(focus.x || 0) + "," + Number(focus.y || 0) + "," +
        Number(focus.width || 0) + "," + Number(focus.height || 0) + ")",
      "focus_zoom=" + Number(focus.zoom || 0).toFixed(3),
      "cursor_in_focus=" + String(!!data.cursor_in_focus)
    ].join(" · ");
    row._body.appendChild(meta);

    var grid = document.createElement("div");
    grid.className = "vision-frame-grid";
    grid.appendChild(makeThumb(data.full_image, "完整图", data));
    grid.appendChild(makeThumb(data.focus_image, "聚焦局部图", data));
    row._body.appendChild(grid);
    appendChatToolRow(row);
  }

  function closeModal() {
    if (activeModal && activeModal.parentNode) activeModal.parentNode.removeChild(activeModal);
    activeModal = null;
  }

  function openModal(data) {
    if (!data) return;
    closeModal();
    ensureStyle();
    var overlay = document.createElement("div");
    overlay.className = "vision-frame-modal";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "视觉帧详情");

    var dialog = document.createElement("div");
    dialog.className = "vision-frame-dialog";
    var head = document.createElement("div");
    head.className = "vision-frame-dialog-head";
    var title = document.createElement("b");
    title.textContent = "视觉帧 " + String(data.frame_id || "");
    var summary = document.createElement("span");
    summary.textContent = frameSummary(data);
    var close = document.createElement("button");
    close.type = "button";
    close.setAttribute("data-vision-frame-close", "1");
    close.textContent = "关闭";
    head.appendChild(title);
    head.appendChild(summary);
    head.appendChild(close);
    dialog.appendChild(head);

    var grid = document.createElement("div");
    grid.className = "vision-frame-dialog-grid";
    var full = document.createElement("figure");
    var fullCaption = document.createElement("figcaption");
    fullCaption.textContent = "完整图 · " + modelSize(data.full_size);
    var fullImage = document.createElement("img");
    fullImage.alt = "完整图";
    fullImage.src = String(data.full_image || "");
    full.appendChild(fullCaption);
    full.appendChild(fullImage);
    var focus = document.createElement("figure");
    var focusCaption = document.createElement("figcaption");
    focusCaption.textContent = "聚焦局部图 · " + modelSize(data.focus && data.focus.image_size);
    var focusImage = document.createElement("img");
    focusImage.alt = "聚焦局部图";
    focusImage.src = String(data.focus_image || "");
    focus.appendChild(focusCaption);
    focus.appendChild(focusImage);
    grid.appendChild(full);
    grid.appendChild(focus);
    dialog.appendChild(grid);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    activeModal = overlay;
  }

  function bind() {
    if (document._visionFrameBound) return;
    document._visionFrameBound = true;
    document.addEventListener("ai-agent:plugin-event", function (event) {
      var data = event && event.detail || {};
      if (String(data.plugin || "") !== PLUGIN) return;
      if (String(data.event || "") === "vision_frame") {
        renderFrame(data);
      } else if (String(data.event || "") === "control_returned") {
        renderControlReturned(data);
      }
    });
    document.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      if (target.closest("[data-vision-frame-close]")) {
        event.preventDefault();
        closeModal();
        return;
      }
      var thumb = target.closest("[data-vision-frame-open]");
      if (thumb) {
        event.preventDefault();
        var card = thumb.closest(".vision-frame-card");
        openModal((thumb && thumb._visionFrameData) || (card && card._visionFrameData));
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && activeModal) closeModal();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
