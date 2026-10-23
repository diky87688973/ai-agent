/* highlight.js 桥接：给渲染出的代码块上色 */
(function (w) {
  "use strict";
  var LANG_MAP = {
    py: "python",
    python: "python",
    js: "javascript",
    javascript: "javascript",
    ts: "typescript",
    typescript: "typescript",
    html: "html",
    css: "css",
    sh: "bash",
    bash: "bash",
    shell: "bash",
    json: "json",
    yaml: "yaml",
    yml: "yaml",
    md: "markdown",
    markdown: "markdown",
    xml: "xml",
    sql: "sql",
    pycon: "python",
    c: "c",
    cpp: "cpp",
    java: "java",
    go: "go",
    rust: "rust",
    diff: "diff",
    patch: "diff",
  };

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function normalizeLang(lang) {
    var k = String(lang || "").toLowerCase().trim();
    return LANG_MAP[k] || k || "";
  }

  function highlightJson(s) {
    var t = String(s || "");
    try {
      var o = JSON.parse(t);
      t = JSON.stringify(o, null, 2);
    } catch (e) {}
    if (w.hljs && w.hljs.getLanguage("json")) {
      try {
        return w.hljs.highlight(t, { language: "json", ignoreIllegals: true }).value;
      } catch (e2) {}
    }
    return t
      .replace(/("(?:\\.|[^"\\])*")\s*:/g, '<span class="hljs-attr">$1</span>:')
      .replace(/:\s*("(?:\\.|[^"\\])*")/g, ':<span class="hljs-string">$1</span>')
      .replace(/:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, ':<span class="hljs-number">$1</span>')
      .replace(/:\s*(true|false|null)/g, ':<span class="hljs-literal">$1</span>');
  }

  function highlightDiff(t) {
    var lines = String(t || "").split("\n");
    return lines
      .map(function (line) {
        var e = escapeHtml(line);
        if (/^---/.test(line) || /^\+\+\+/.test(line)) return '<span class="hljs-meta">' + e + "</span>";
        if (/^@@/.test(line)) return '<span class="hljs-keyword">' + e + "</span>";
        if (/^\+/.test(line)) return '<span class="hljs-string">' + e + "</span>";
        if (/^-/.test(line)) return '<span class="hljs-deletion">' + e + "</span>";
        return e;
      })
      .join("\n");
  }

  function highlightCode(s, lang) {
    var t = String(s || "");
    var langNorm = normalizeLang(lang);
    if (langNorm === "json" || (!lang && /^\s*[\[{]/.test(t))) return highlightJson(t);
    if (langNorm === "diff") return highlightDiff(t);
    if (w.hljs && langNorm && w.hljs.getLanguage(langNorm)) {
      try {
        return w.hljs.highlight(t, { language: langNorm, ignoreIllegals: true }).value;
      } catch (e) {}
    }
    if (w.hljs && !langNorm) {
      try {
        var auto = w.hljs.highlightAuto(t, ["python", "bash", "javascript", "typescript", "json", "sql"]);
        if (auto && auto.value) return auto.value;
      } catch (e2) {}
    }
    return escapeHtml(t);
  }

  function detectScriptLang(code, hint) {
    var h = normalizeLang(hint);
    if (h) return h;
    var t = String(code || "").trim();
    if (/^#!\/.*python/i.test(t)) return "python";
    if (/^#!\/bin\/(ba)?sh/i.test(t)) return "bash";
    if (/\b(import|from)\s+\w+/.test(t)) return "python";
    if (/\b(def|class|async)\s+\w+/.test(t)) return "python";
    if (/\becho\s+/.test(t) || /^\s*(export\s+)?\w+=/.test(t)) return "bash";
    return "python";
  }

  function hljsCodeClass(lang) {
    var L = normalizeLang(lang) || "plaintext";
    return "hljs language-" + L;
  }

  w.codeHighlight = {
    escapeHtml: escapeHtml,
    normalizeLang: normalizeLang,
    highlightCode: highlightCode,
    detectScriptLang: detectScriptLang,
    hljsCodeClass: hljsCodeClass,
    LANG_MAP: LANG_MAP,
  };
})(typeof window !== "undefined" ? window : globalThis);
