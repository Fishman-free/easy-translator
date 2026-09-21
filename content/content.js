/**
 * Easy Translator — 网页内容脚本入口
 *
 * 只做一件事：把悬停引擎挂到当前文档。
 * 每个 iframe 会各自注入一份，卡片出现在鼠标所在的 frame 内。
 */
(function () {
  'use strict';
  try {
    if (window.__easyTranslatorHooked) return;
    window.__easyTranslatorHooked = true;
    if (typeof ETHover === 'undefined') return;
    ETHover.start({ doc: document, win: window });
  } catch (e) {
    /* 静默：绝不因为取词脚本影响宿主页面 */
  }
})();
