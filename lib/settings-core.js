/**
 * Easy Translator — 设置模块（零依赖）
 *
 * 同一份文件被三种环境加载：
 *   1. Service Worker  —— importScripts()
 *   2. popup / options —— <script src>
 *   3. content script  —— manifest content_scripts.js
 * 因此不使用 ES module 语法，统一挂载到 globalThis.ETSettings。
 */
(function (root) {
  'use strict';

  var KEY = 'settings';

  var DEFAULTS = {
    enabled: true,
    dwellMs: 5000,          // 悬停触发时长（毫秒）
    engine: 'auto',         // auto | online | local
    examplesCount: 3,       // 卡片展示例句条数
    showSpeak: true,        // 显示发音按钮

    // —— 小模型（OpenAI 兼容端点，默认 Ollama）——
    model: {
      enabled: false,                        // 默认关闭：开箱即用走在线词典
      baseUrl: 'http://127.0.0.1:11434/v1',
      apiKey: '',
      textModel: 'qwen2.5:1.5b',             // 文本查词
      visionModel: 'qwen2.5vl:3b',           // 图片取词（需另 pull 一个视觉模型）
      timeoutMs: 45000                       // CPU 冷启动可能要加载模型，留足时间
    },

    // —— 图片取词（OCR 走本地视觉小模型，不依赖外网）——
    imageOcr: {
      enabled: true,        // 注意：还需授予「所有网站」可选权限才真正生效
      dwellMs: 1500,        // 图片上驻留多久开始识别（比文字短，因为识别本身有耗时）
      cropW: 460,           // 截图裁剪宽（CSS 像素，以光标为中心）
      cropH: 140,
      hint: true            // 识别期间在光标旁显示一个极小的「识别中」提示点
    },

    // —— PDF 增强阅读器 ——
    pdf: {
      autoOpen: false       // 打开 .pdf 链接时自动切换到内置阅读器
    }
  };

  function clampInt(value, min, max, fallback) {
    var n = parseInt(value, 10);
    if (isNaN(n)) return fallback;
    return Math.min(max, Math.max(min, n));
  }

  /** 把任意来源的设置对象补齐、裁边，保证下游永远拿到完整结构 */
  function normalize(raw) {
    var s = Object.assign({}, DEFAULTS, raw || {});
    s.model = Object.assign({}, DEFAULTS.model, (raw && raw.model) || {});
    s.imageOcr = Object.assign({}, DEFAULTS.imageOcr, (raw && raw.imageOcr) || {});
    s.pdf = Object.assign({}, DEFAULTS.pdf, (raw && raw.pdf) || {});

    s.enabled = !!s.enabled;
    s.showSpeak = !!s.showSpeak;
    s.dwellMs = clampInt(s.dwellMs, 1000, 15000, DEFAULTS.dwellMs);
    s.examplesCount = clampInt(s.examplesCount, 0, 5, DEFAULTS.examplesCount);

    s.model.enabled = !!s.model.enabled;
    s.model.timeoutMs = clampInt(s.model.timeoutMs, 2000, 180000, DEFAULTS.model.timeoutMs);
    s.model.baseUrl = cleanBaseUrl(s.model.baseUrl);
    s.model.textModel = cleanText(s.model.textModel, DEFAULTS.model.textModel);
    s.model.visionModel = cleanText(s.model.visionModel, '');
    s.model.apiKey = typeof s.model.apiKey === 'string' ? s.model.apiKey : '';

    s.imageOcr.enabled = !!s.imageOcr.enabled;
    s.imageOcr.hint = !!s.imageOcr.hint;
    s.imageOcr.dwellMs = clampInt(s.imageOcr.dwellMs, 500, 8000, DEFAULTS.imageOcr.dwellMs);
    s.imageOcr.cropW = clampInt(s.imageOcr.cropW, 200, 900, DEFAULTS.imageOcr.cropW);
    s.imageOcr.cropH = clampInt(s.imageOcr.cropH, 80, 500, DEFAULTS.imageOcr.cropH);

    s.pdf.autoOpen = !!s.pdf.autoOpen;

    if (['auto', 'online', 'local'].indexOf(s.engine) === -1) s.engine = DEFAULTS.engine;
    return s;
  }

  function cleanBaseUrl(v) {
    var s = typeof v === 'string' && v.trim() ? v.trim() : DEFAULTS.model.baseUrl;
    return s.replace(/\/+$/, '');
  }

  function cleanText(v, fallback) {
    return typeof v === 'string' && v.trim() ? v.trim() : fallback;
  }

  /** 小模型端点整理成一次 chat/completions 请求所需参数 */
  function modelTarget(settings, kind) {
    var cfg = settings.model || {};
    return {
      url: cleanBaseUrl(cfg.baseUrl) + '/chat/completions',
      model: kind === 'vision' ? (cfg.visionModel || '') : (cfg.textModel || DEFAULTS.model.textModel),
      apiKey: cfg.apiKey || '',
      timeoutMs: cfg.timeoutMs || DEFAULTS.model.timeoutMs
    };
  }

  async function get() {
    try {
      var stored = await chrome.storage.local.get(KEY);
      return normalize(stored && stored[KEY]);
    } catch (e) {
      return normalize(null);
    }
  }

  async function set(patch) {
    var current = await get();
    var next = normalize(merge(current, patch || {}));
    await chrome.storage.local.set({ settings: next });
    return next;
  }

  function merge(base, patch) {
    var out = Object.assign({}, base);
    Object.keys(patch).forEach(function (k) {
      if (['model', 'imageOcr', 'pdf'].indexOf(k) !== -1 && patch[k] && typeof patch[k] === 'object') {
        out[k] = Object.assign({}, base[k], patch[k]);
      } else {
        out[k] = patch[k];
      }
    });
    return out;
  }

  function onChange(handler) {
    chrome.storage.onChanged.addListener(function (changes, area) {
      if (area === 'local' && changes[KEY]) handler(normalize(changes[KEY].newValue));
    });
  }

  root.ETSettings = {
    KEY: KEY,
    DEFAULTS: DEFAULTS,
    normalize: normalize,
    modelTarget: modelTarget,
    get: get,
    set: set,
    onChange: onChange
  };
})(typeof globalThis !== 'undefined' ? globalThis : self);
