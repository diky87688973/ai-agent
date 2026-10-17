/* Skills 在上下文视图里的外观声明。

   Skills **没有界面交互**（面板、按钮都没有），唯一对外可见的就是上下文分层里那两段
   （清单 / 常驻正文）—— 段色与段名由插件自己声明，壳层只按段 key 取用。

   为什么要有这个文件：不声明时壳层对**任何**未注册的插件段一律给 violet，
   两个装在一起就撞色，而且撞了也看不出来（不是报错，只是两段同色）。
*/
(function () {
  "use strict";

  if (window.aiAgentPlugins && window.aiAgentPlugins.ctxSegments) {
    window.aiAgentPlugins.ctxSegments.register("skills", {
      // 色名而不是定值：壳层按当前主题取深/浅两套里的那一套，
      // 分段条与浮层都走同一个取色函数，两处必然同色。
      color: "plum",
      label: "Skills",
    });
  }
})();
