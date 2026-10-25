/* 无边框窗口交互：拖动、双击最大化、控件、服务守护。 */
(function () {
  function init() {
    if (!window.pywebview || !window.pywebview.api) return false;
    if (document.querySelector(".window-controls")) return true;
    var header = document.querySelector("header");
    var actions = header && header.querySelector(".hdr-actions");
    if (!header || !actions) return false;

    document.documentElement.classList.add("pywebview-shell");
    var controls = document.createElement("span");
    controls.className = "window-controls";
    controls.innerHTML =
      '<button type="button" class="window-btn" data-window-action="minimize" title="最小化" aria-label="最小化">–</button>' +
      '<button type="button" class="window-btn" data-window-action="maximize" title="最大化" aria-label="最大化">□</button>' +
      '<button type="button" class="window-btn window-close" data-window-action="close" title="关闭" aria-label="关闭">×</button>';
    actions.appendChild(controls);

    var maximized = false;
    var maxButton = controls.querySelector('[data-window-action="maximize"]');
    function toggleMaximize() {
      maximized = !maximized;
      window.pywebview.api.toggle_maximize(maximized);
      maxButton.textContent = maximized ? "❐" : "□";
      maxButton.setAttribute("aria-label", maximized ? "还原" : "最大化");
      maxButton.setAttribute("title", maximized ? "还原" : "最大化");
    }

    controls.addEventListener("mousedown", function (event) { event.stopPropagation(); });
    controls.addEventListener("click", function (event) {
      var button = event.target.closest("[data-window-action]");
      if (!button) return;
      var action = button.getAttribute("data-window-action");
      if (action === "minimize") window.pywebview.api.minimize();
      else if (action === "close") window.pywebview.api.close();
      else if (action === "maximize") toggleMaximize();
    });

    var resizing = null;
    var resizeEdge = null;

    function edgeAt(event) {
      var margin = 7;
      var w = window.innerWidth || document.documentElement.clientWidth || 0;
      var h = window.innerHeight || document.documentElement.clientHeight || 0;
      if (w < 2 || h < 2) return null;
      var left = event.clientX <= margin;
      var right = event.clientX >= w - margin;
      var top = event.clientY <= margin;
      var bottom = event.clientY >= h - margin;
      if (!left && !right && !top && !bottom) return null;
      return { left: left, right: right, top: top, bottom: bottom };
    }

    function setEdgeCursor(edge) {
      var cursor = "";
      var klass = "";
      if (edge) {
        if ((edge.left && edge.top) || (edge.right && edge.bottom)) {
          cursor = "nwse-resize";
          klass = "edge-nwse";
        } else if ((edge.right && edge.top) || (edge.left && edge.bottom)) {
          cursor = "nesw-resize";
          klass = "edge-nesw";
        } else if (edge.left || edge.right) {
          cursor = "ew-resize";
          klass = "edge-ew";
        } else if (edge.top || edge.bottom) {
          cursor = "ns-resize";
          klass = "edge-ns";
        }
      }
      var root = document.documentElement;
      root.classList.remove("edge-ew", "edge-ns", "edge-nwse", "edge-nesw");
      if (klass) root.classList.add(klass);
      root.style.cursor = cursor;
      if (document.body) document.body.style.cursor = cursor;
    }

    document.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || maximized) return;
      var edge = edgeAt(event);
      if (!edge) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      window.pywebview.api.window_position().then(function (pos) {
        return window.pywebview.api.window_size().then(function (size) {
          if (!pos || !size || event.button !== 0) return;
          resizing = {
            sx: event.screenX,
            sy: event.screenY,
            x: pos[0],
            y: pos[1],
            w: size[0],
            h: size[1],
            edge: edge
          };
        });
      }).catch(function () {});
    }, true);

    document.addEventListener("mousemove", function (event) {
      if (resizing) {
        var dx = event.screenX - resizing.sx;
        var dy = event.screenY - resizing.sy;
        var width = resizing.w;
        var height = resizing.h;
        var x = resizing.x;
        var y = resizing.y;
        if (resizing.edge.right) width += dx;
        if (resizing.edge.left) { width -= dx; x += dx; }
        if (resizing.edge.bottom) height += dy;
        if (resizing.edge.top) { height -= dy; y += dy; }
        if (width < 640) {
          if (resizing.edge.left) x += width - 640;
          width = 640;
        }
        if (height < 480) {
          if (resizing.edge.top) y += height - 480;
          height = 480;
        }
        window.pywebview.api.resize_window(width, height, x, y);
        event.preventDefault();
        return;
      }
      if (press) return;
      setEdgeCursor(edgeAt(event));
    }, true);

    document.addEventListener("mouseup", function () {
      if (!resizing) return;
      resizing = null;
      setEdgeCursor(null);
    });

    var press = null;
    var raf = 0;
    var pending = null;
    var moving = false;
    var normalSize = { w: window.outerWidth || 1440, h: window.outerHeight || 900 };
    function pumpMove() {
      if (moving || raf) return;
      raf = requestAnimationFrame(function () {
        raf = 0;
        if (moving || !pending) return;
        var point = pending;
        pending = null;
        moving = true;
        window.pywebview.api.move_window(point.x, point.y).then(function () {
          moving = false;
          if (pending) pumpMove();
        }).catch(function () {
          moving = false;
        });
      });
    }

    header.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || event.target.closest("button, .hdr-actions, .window-controls")) return;
      event.preventDefault();
      press = { sx: event.screenX, sy: event.screenY, moved: false, origin: null };
      window.pywebview.api.window_position().then(function (pos) {
        if (press && !press.origin && pos && pos.length === 2) press.origin = { x: pos[0], y: pos[1] };
      });
    });
    document.addEventListener("mousemove", function (event) {
      if (!press || press.origin === null) return;
      if (!press.moved && Math.abs(event.screenX - press.sx) < 8 && Math.abs(event.screenY - press.sy) < 8) return;
      press.moved = true;
      if (maximized) {
        var maxWidth = window.outerWidth || normalSize.w;
        var maxLeft = window.screenX || 0;
        var ratio = maxWidth > 0 ? (event.screenX - maxLeft) / maxWidth : 0.5;
        ratio = Math.min(1, Math.max(0, ratio));
        toggleMaximize();
        press.origin = {
          x: Math.round(event.screenX - ratio * normalSize.w),
          y: Math.round(event.screenY - 14)
        };
        press.sx = event.screenX;
        press.sy = event.screenY;
        window.pywebview.api.move_window(press.origin.x, press.origin.y);
        return;
      }
      if (!press.origin) return;
      pending = { x: press.origin.x + event.screenX - press.sx, y: press.origin.y + event.screenY - press.sy };
      pumpMove();
    });
    document.addEventListener("mouseup", function () {
      if (!press) return;
      press = null;
      pending = null;
    });
    header.addEventListener("dblclick", function (event) {
      if (!event.target.closest("button, .hdr-actions, .window-controls")) {
        toggleMaximize();
      }
    });
    return true;
  }

  function boot() {
    if (init()) return;
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      if (init() || tries >= 50) clearInterval(timer);
    }, 100);
  }

  boot();
  window.addEventListener("pywebviewready", init);
  setInterval(function () {
    if (!window.pywebview || !window.pywebview.api) return;
    if (typeof window.pywebview.api.ensure_server !== "function") return;
    window.pywebview.api.ensure_server().then(function (restarted) {
      if (restarted) window.location.reload();
    }).catch(function () {});
  }, 1500);
})();
