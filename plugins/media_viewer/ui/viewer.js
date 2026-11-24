/* 媒体实例只拥有自己的面板、请求与原生播放资源。 */
(function () {
  "use strict";
  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function duration(value) {
    if (!Number.isFinite(value) || value < 0) return "不可获取";
    var seconds = Math.floor(value), hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60);
    return (hours ? hours + " 小时 " : "") + (minutes ? minutes + " 分 " : "") + seconds % 60 + " 秒";
  }
  function open(context) {
    var controller = new AbortController(), disposed = false, failed = false, media = null;
    var body = context.body;
    body.className = "pane-body media-viewer";
    var status = element("div", "media-viewer-status", "正在读取媒体信息…");
    status.setAttribute("role", "status");
    body.replaceChildren(status);
    function pause() { if (media && typeof media.pause === "function") media.pause(); }
    function dispose() {
      if (disposed) return;
      disposed = true;
      controller.abort(); pause();
      if (media) {
        media.removeAttribute("src");
        if (typeof media.load === "function") media.load();
      }
      context.signal.removeEventListener("abort", dispose);
      body.replaceChildren();
    }
    context.signal.addEventListener("abort", dispose, {once: true});
    function showError(message) { failed = true; status.textContent = message; status.hidden = false; }
    function render(data) {
      var stage = element("div", "media-viewer-stage media-viewer-" + data.kind);
      media = element(data.kind === "image" ? "img" : data.kind, "media-viewer-resource");
      if (data.kind === "image") media.alt = data.name;
      else {
        media.controls = true; media.preload = "metadata";
        if (data.kind === "video") media.setAttribute("playsinline", "");
      }
      stage.appendChild(media);
      var identity = element("div", "media-viewer-identity");
      identity.append(element("div", "media-viewer-name", data.name),
        element("div", "media-viewer-location", data.path));
      var details = element("dl", "media-viewer-details");
      function field(label, value) {
        var item = element("dd", "", value);
        var fact = element("div", "media-viewer-fact");
        fact.append(element("dt", "", label), item);
        details.appendChild(fact); return item;
      }
      field("类型", ({image: "图片", video: "视频", audio: "音频"})[data.kind] + " · " + data.name.split(".").pop().toUpperCase());
      field("大小", context.formatSize(data.size_bytes));
      var dimensions = field("尺寸", data.kind === "audio" ? "不适用" : "读取中");
      var time = data.kind === "image" ? null : field("时长", "读取中");
      body.replaceChildren(stage, identity, details, status);
      status.hidden = true;
      media.addEventListener(data.kind === "image" ? "load" : "loadedmetadata", function () {
        var width = data.kind === "image" ? media.naturalWidth : media.videoWidth;
        var height = data.kind === "image" ? media.naturalHeight : media.videoHeight;
        if (data.kind !== "audio") dimensions.textContent = width && height ? width + " × " + height + " px" : "不可获取";
        if (time) time.textContent = duration(media.duration);
      }, {signal: controller.signal});
      media.addEventListener("error", function () {
        if (time) time.textContent = "不可获取";
        if (data.kind !== "audio") dimensions.textContent = "不可获取";
        var code = media.error && media.error.code;
        showError(code === 2 ? "媒体传输中断，请重新打开文件" : code === 3 ? "媒体解码失败，文件可能已损坏" : "当前浏览器无法显示或播放此媒体编码");
      }, {signal: controller.signal});
      media.src = "/api/media?path=" + encodeURIComponent(data.path);
    }
    fetch("/api/media/info?path=" + encodeURIComponent(context.path), {signal: controller.signal})
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            var messages = {403: "该文件不在允许预览的目录内", 404: "文件不存在或已移动", 401: "登录已失效，请重新登录", 415: "不支持此媒体类型", 503: "媒体预览插件不可用"};
            throw new Error(messages[response.status] || "媒体信息读取失败");
          }
          if (data.version !== 1 || ["image", "video", "audio"].indexOf(data.kind) < 0) throw new Error("媒体信息格式无效");
          return data;
        });
      }).then(function (data) { if (!disposed) render(data); })
      .catch(function (error) { if (!disposed && error.name !== "AbortError") showError(error.message); });
    return {activate: function () {}, deactivate: pause, dispose: dispose,
      canReuse: function () { return !disposed && !failed; }};
  }
  window.aiAgentClassicComponents.register("app/shell/web-ui/file-viewers/media", {open: open});
})();
