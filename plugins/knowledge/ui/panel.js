/* 知识库面板逻辑。
   属于 knowledge 插件：面板 HTML、样式、脚本都由插件提供，壳层只按 `_asset` 路由送达。
   取数走**插件自己的端点**（`/api/plugin/knowledge/*`）——
   经 `aiAgentPlugins` 客户端拿地址，插件不必知道自己的 URL 前缀。
*/
(function () {
  "use strict";

  var api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent || "knowledge");

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* 当前会话 id：勾选是**按会话**记的，所以每次取数都要带上它。
     壳层把会话 id 放在 `#cid` 上（前 8 位是显示用的，完整值在 dataset 或全局变量里），
     这里优先用壳层暴露的取值函数，取不到再退回读 `#cid`。 */
  function currentCid() {
    try {
      if (typeof getActiveConversationId === "function") return getActiveConversationId();
    } catch (e) {}
    var el = document.getElementById("cid");
    return el && el.textContent ? el.textContent.trim() : "";
  }

  function persist(cid) {
    var checked = [];
    document.querySelectorAll("#kbBody .kb-cb.checked").forEach(function (cb) {
      var p = cb.getAttribute("data-path");
      if (p) checked.push(p);
    });
    api.put("checked", { conversation_id: cid, checked: checked })
      .then(function (res) {
        var j = res && res.data;
        if (!j || !j.ok || !Array.isArray(j.checked)) return;
        /* 以服务端接受的为准回填：越界或已消失的文件会被拒，界面要跟着纠正 */
        var set = {};
        j.checked.forEach(function (p) { set[p] = true; });
        document.querySelectorAll("#kbBody .kb-cb").forEach(function (cb) {
          var p = cb.getAttribute("data-path");
          var row = cb.closest(".kb-file-row");
          if (!row) return;
          if (set[p]) { cb.classList.add("checked"); row.classList.add("checked"); }
          else { cb.classList.remove("checked"); row.classList.remove("checked"); }
        });
      })
      .catch(function () {});
  }

  function renderList(container, files, checkedSet, cid) {
    var html =
      '<div class="kb-hint-bar">💡 共 ' + files.length +
      " 个文件；勾选的文件将作为当前会话的上下文参考内容</div>" +
      '<div class="kb-list">';
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      var on = checkedSet[f.path] ? " checked" : "";
      html += '<label class="kb-file-row' + on + '">';
      html += '<span class="kb-cb' + on + '" data-path="' + esc(f.path) + '"></span>';
      html += '<span class="kb-fpath">' + esc(f.path) + "</span>";
      html += "</label>";
    }
    html += "</div>";
    container.innerHTML = html;
    container.querySelectorAll(".kb-file-row").forEach(function (row) {
      row.addEventListener("click", function () {
        var cb = row.querySelector(".kb-cb");
        if (!cb) return;
        if (cb.classList.contains("checked")) {
          cb.classList.remove("checked");
          row.classList.remove("checked");
        } else {
          cb.classList.add("checked");
          row.classList.add("checked");
        }
        persist(cid);
      });
    });
  }

  function render() {
    var body = document.getElementById("kbBody");
    if (!body) return;
    body.innerHTML = '<div class="kb-loading">📂 加载知识库…</div>';
    api.get("files")
      .then(function (res) {
        var data = (res && res.data) || {};
        if (!data.ok || !data.enabled) {
          body.innerHTML =
            '<div class="kb-empty">⚠️ 知识库未启用' +
            '<br><span class="kb-hint">在 config.ini 的 [knowledge] 节配置 dir</span></div>';
          return;
        }
        var files = data.files || [];
        if (!files.length) {
          body.innerHTML = '<div class="kb-empty">📭 知识库目录为空</div>';
          return;
        }
        var cid = currentCid();
        api.get("checked", { conversation_id: cid })
          .then(function (r2) {
            var sd = (r2 && r2.data) || {};
            var cs = {};
            if (sd.ok && sd.checked) sd.checked.forEach(function (p) { cs[p] = true; });
            renderList(body, files, cs, cid);
          })
          .catch(function () { renderList(body, files, {}, cid); });
      })
      .catch(function (err) {
        body.innerHTML =
          '<div class="kb-empty">❌ 加载失败: ' + esc(err && err.message ? err.message : err) + "</div>";
      });
  }

  window.aiAgentKnowledgePanel = { render: render };

  /* 勾选是**按会话**记的，所以会话一切换就要重取。
     壳层广播通用事件（`ai-agent:conversation-changed`），插件自己订阅 ——
     壳层不点名任何插件，插件也不要求壳层认识自己。 */
  document.addEventListener("ai-agent:conversation-changed", function () {
    if (document.getElementById("kbBody")) render();
  });

  render();
})();
