/* 消息图片点击预览大图 + 剪贴板取图辅助。 */
(function (global) {
  var AIA = global.AIA || (global.AIA = {});

  function attachmentUrl(cid, id) {
    return (
      "/api/chat/attachment?" +
      new URLSearchParams({
        conversation_id: String(cid || "").trim(),
        id: String(id || "").trim(),
      }).toString()
    );
  }

  function ensureLightbox() {
    var el = document.getElementById("cwaImgLightbox");
    if (el && el.querySelector(".img-lightbox-stage") && el.querySelector(".img-lightbox-tools")) {
      return el;
    }
    if (el) el.remove();
    el = document.createElement("div");
    el.id = "cwaImgLightbox";
    el.className = "img-lightbox hidden";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.innerHTML =
      '<div class="img-lightbox-backdrop" title="关闭"></div>' +
      '<div class="img-lightbox-stage"></div>' +
      '<div class="img-lightbox-tools">' +
      '<button type="button" class="img-lightbox-mode" data-mode="fit">铺满屏幕</button>' +
      '<button type="button" class="img-lightbox-mode" data-mode="pixel">1:1 像素</button>' +
      '<span class="img-lightbox-meta"></span>' +
      "</div>" +
      '<button type="button" class="img-lightbox-close" aria-label="关闭">×</button>';
    document.body.appendChild(el);
    el._cwaMode = "pixel";
    function close() {
      el.classList.add("hidden");
      var stage = el.querySelector(".img-lightbox-stage");
      if (stage) {
        stage.innerHTML = "";
        stage.scrollTop = 0;
        stage.scrollLeft = 0;
      }
      var meta = el.querySelector(".img-lightbox-meta");
      if (meta) meta.textContent = "";
      el._cwaImg = null;
    }
    el.querySelector(".img-lightbox-backdrop").addEventListener("click", close);
    el.querySelector(".img-lightbox-close").addEventListener("click", close);
    var stage = el.querySelector(".img-lightbox-stage");
    stage.addEventListener("click", function (ev) {
      if (ev.target === stage) close();
    });
    el.querySelectorAll(".img-lightbox-mode").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        el._cwaMode = btn.getAttribute("data-mode") || "fit";
        syncModeButtons(el);
        applyLightboxSize(el);
      });
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && !el.classList.contains("hidden")) close();
    });
    window.addEventListener("resize", function () {
      if (!el.classList.contains("hidden")) applyLightboxSize(el);
    });
    el._cwaClose = close;
    return el;
  }

  function syncModeButtons(el) {
    var mode = el._cwaMode || "fit";
    el.querySelectorAll(".img-lightbox-mode").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-mode") === mode);
    });
  }

  function applyLightboxSize(el) {
    var img = el._cwaImg;
    var stage = el.querySelector(".img-lightbox-stage");
    var meta = el.querySelector(".img-lightbox-meta");
    if (!img || !stage) return;
    var iw = img.naturalWidth | 0;
    var ih = img.naturalHeight | 0;
    if (!iw || !ih) return;
    var mode = el._cwaMode || "pixel";
    var pad = 8;
    var sw = Math.max(1, stage.clientWidth - pad * 2);
    var sh = Math.max(1, stage.clientHeight - pad * 2);
    if (mode === "pixel") {
      /* 1:1 只改“是否缩放”，不改“在哪”。
         图片比视口小时四周有富余，用 auto 外边距把它推出居中位置；
         比视口大时富余为负，auto 退化为 0，自然回到可滚动起点。
         一条规则同时管住两种情形，不必分两套定位。 */
      img.style.width = iw + "px";
      img.style.height = ih + "px";
      img.style.margin = "auto";
      stage.classList.add("is-pixel");
      stage.classList.remove("is-fit");
      centerLightboxStage(el);
      if (meta) {
        var scrollable = iw > sw || ih > sh;
        meta.textContent =
          "实际像素 " + iw + "×" + ih + (scrollable ? " · 1:1 可滚动" : " · 1:1");
      }
      return;
    }
    /* 铺满：等比放大/缩小，至少顶满宽或高，消除四周大块留白 */
    var scale = Math.min(sw / iw, sh / ih);
    var dw = Math.max(1, Math.round(iw * scale));
    var dh = Math.max(1, Math.round(ih * scale));
    img.style.width = dw + "px";
    img.style.height = dh + "px";
    img.style.margin = "0";
    stage.classList.add("is-fit");
    stage.classList.remove("is-pixel");
    stage.scrollTop = 0;
    stage.scrollLeft = 0;
    if (meta) {
      meta.textContent =
        "实际像素 " + iw + "×" + ih + " · 显示 " + dw + "×" + dh + "（铺满）";
    }
  }

  /* 把可滚动容器滚到正中。
     只写 margin:auto 不够：容器若先因为上一次大图滚到过中间，
     换成小图后 scrollLeft 仍停在旧值，看上去就偏了。这里显式归中。 */
  function centerLightboxStage(el) {
    var stage = el.querySelector(".img-lightbox-stage");
    if (!stage) return;
    stage.scrollLeft = Math.max(0, (stage.scrollWidth - stage.clientWidth) / 2);
    stage.scrollTop = Math.max(0, (stage.scrollHeight - stage.clientHeight) / 2);
  }

  function openImageLightbox(url) {
    var src = String(url || "").trim();
    if (!src) return;
    var el = ensureLightbox();
    var stage = el.querySelector(".img-lightbox-stage");
    var meta = el.querySelector(".img-lightbox-meta");
    stage.innerHTML = "";
    stage.scrollTop = 0;
    stage.scrollLeft = 0;
    if (meta) meta.textContent = "加载中…";
    el._cwaMode = "pixel";
    syncModeButtons(el);
    var img = document.createElement("img");
    img.className = "img-lightbox-img";
    img.alt = "预览";
    el._cwaImg = img;
    img.onload = function () {
      applyLightboxSize(el);
    };
    img.src = src;
    stage.appendChild(img);
    el.classList.remove("hidden");
    if (img.complete) applyLightboxSize(el);
  }

  function bindThumbClick(img) {
    if (!img || img._cwaLbBound) return;
    img._cwaLbBound = true;
    img.classList.add("msg-attach-thumb");
    img.title = img.title || "点击预览（默认 1:1 实际像素）";
    img.style.cursor = "zoom-in";
  }

  /* 缩略图是后画进对话区的。点在图上冒泡到 document，这里收一次再开预览。 */
  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    var img = t.closest(".msg-attach-thumb");
    if (!img) return;
    ev.preventDefault();
    openImageLightbox(img.currentSrc || img.src);
  });

  function buildMsgAttachStrip(cid, attachments, localItems) {
    var wrap = document.createElement("div");
    wrap.className = "attach-strip msg-attach-strip";
    var server = Array.isArray(attachments) ? attachments : [];
    var local = Array.isArray(localItems) ? localItems : [];
    var n = Math.max(server.length, local.length);
    for (var i = 0; i < n; i++) {
      var a = server[i];
      var loc = local[i];
      var img = document.createElement("img");
      img.alt = (a && a.name) || (loc && loc.name) || "图片";
      if (a && a.id && cid) {
        img.src = attachmentUrl(cid, a.id);
      } else if (loc) {
        if (loc.data_base64) {
          img.src =
            "data:" +
            (loc.mime || "image/png") +
            ";base64," +
            String(loc.data_base64);
        } else if (loc.previewUrl) {
          img.src = loc.previewUrl;
        }
      }
      if (!img.src) continue;
      bindThumbClick(img);
      wrap.appendChild(img);
    }
    return wrap;
  }

  function appendHadImagesLostTip(mount) {
    if (!mount) return;
    var tip = document.createElement("div");
    tip.className = "attach-lost-tip";
    tip.textContent = "图片预览已失效；若需再看请重新粘贴后发送。";
    mount.appendChild(tip);
  }

  function measureImageFile(file) {
    return new Promise(function (resolve) {
      if (!file) {
        resolve({ file: file, w: 0, h: 0, area: 0 });
        return;
      }
      var url = URL.createObjectURL(file);
      var im = new Image();
      im.onload = function () {
        var w = im.naturalWidth | 0;
        var h = im.naturalHeight | 0;
        URL.revokeObjectURL(url);
        resolve({ file: file, w: w, h: h, area: w * h });
      };
      im.onerror = function () {
        URL.revokeObjectURL(url);
        resolve({ file: file, w: 0, h: 0, area: 0 });
      };
      im.src = url;
    });
  }

  function preferLargestImageFiles(files) {
    files = Array.prototype.slice.call(files || []).filter(Boolean);
    if (files.length <= 1) return Promise.resolve(files);
    return Promise.all(files.map(measureImageFile)).then(function (rows) {
      rows.sort(function (a, b) {
        return b.area - a.area;
      });
      return rows[0] && rows[0].file ? [rows[0].file] : files.slice(0, 1);
    });
  }

  function filesFromPasteEvent(clipboardData) {
    var items = clipboardData && clipboardData.items;
    if (!items) return [];
    var files = [];
    var seen = {};
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (!it || !it.type || it.type.indexOf("image/") !== 0) continue;
      var f = it.getAsFile();
      if (!f) continue;
      var key = String(f.type || "") + ":" + String(f.size || 0);
      if (seen[key]) continue;
      seen[key] = 1;
      files.push(f);
    }
    return files;
  }

  function readClipboardImagesAsync() {
    if (!navigator.clipboard || typeof navigator.clipboard.read !== "function") {
      return Promise.resolve([]);
    }
    return navigator.clipboard
      .read()
      .then(function (items) {
        var tasks = [];
        (items || []).forEach(function (item) {
          var types = (item && item.types) || [];
          var imgTypes = types.filter(function (t) {
            return String(t).indexOf("image/") === 0;
          });
          imgTypes.sort(function (a, b) {
            var ap = String(a).indexOf("png") >= 0 ? 0 : 1;
            var bp = String(b).indexOf("png") >= 0 ? 0 : 1;
            return ap - bp;
          });
          imgTypes.forEach(function (t) {
            tasks.push(
              item.getType(t).then(function (blob) {
                var ext = String(t).split("/")[1] || "png";
                return new File([blob], "paste." + ext, { type: t });
              })
            );
          });
        });
        return Promise.all(tasks);
      })
      .catch(function () {
        return [];
      });
  }

  function collectPasteImageFiles(clipboardData) {
    var fromEvent = filesFromPasteEvent(clipboardData);
    return readClipboardImagesAsync().then(function (fromAsync) {
      var all = fromEvent.concat(fromAsync || []);
      return preferLargestImageFiles(all);
    });
  }

  AIA.attachmentUrl = attachmentUrl;
  AIA.openImageLightbox = openImageLightbox;
  AIA.bindThumbClick = bindThumbClick;
  AIA.buildMsgAttachStrip = buildMsgAttachStrip;
  AIA.appendHadImagesLostTip = appendHadImagesLostTip;
  AIA.collectPasteImageFiles = collectPasteImageFiles;
  AIA.preferLargestImageFiles = preferLargestImageFiles;
  global.openImageLightbox = openImageLightbox;
})(window);
