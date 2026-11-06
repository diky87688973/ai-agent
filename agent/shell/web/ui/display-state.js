/* 本浏览器的面板视图状态；与业务事实分开，跨设备不共享。 */
(function () {
  "use strict";
  function key(cid, doc) { return "aiAgent.displayView.v1/" + encodeURIComponent(cid) + "/" + encodeURIComponent(doc.id); }
  window.aiAgentShell.displays.state = {
    load: function (cid, doc) {
      try {
        var raw = localStorage.getItem(key(cid, doc)); if (!raw) return {value: null};
        var item = JSON.parse(raw);
        if (item.version !== 1) return {value: null, error: "显示设置版本不受支持，可重置显示"};
        if (item.revision !== doc.revision) return {value: null};
        return {value: item.value};
      } catch (_error) { return {value: null, error: "显示设置无法恢复，可重置显示"}; }
    },
    save: function (cid, doc, value) {
      var raw = JSON.stringify({version: 1, revision: doc.revision, value: value});
      if (raw.length > 12000) throw new Error("面板显示设置过大");
      localStorage.setItem(key(cid, doc), raw);
    }
  };
})();
