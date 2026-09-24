/**
 * Easy Translator — MV3 Service Worker
 *
 * 三条取词通道：
 *   1. 网页文本 / PDF 文本层 —— 内容脚本取词后发来 {type:'lookup', word}
 *   2. 图片内文字         —— 内容脚本发来 {type:'lookup-image', rect...}，
 *                            本文件负责 截图 → 裁剪 → 视觉模型识别 → 查词
 *   3. PDF 探测           —— webRequest 观察 Content-Type，记录哪些标签页是 PDF
 *
 * 原则：任何一条通道拿不到「合法的英文单词」，都返回 ok:false，前端静默不弹窗。
 */
importScripts('lib/settings-core.js', 'lib/normalize.js');

const ONLINE_ENDPOINT = 'https://dict.youdao.com/jsonapi';
const CACHE_KEY = 'lookupCache';
const CACHE_MAX = 500;
const NEG_TTL = 10 * 60 * 1000;      // 图片识别「非英文」负缓存有效期
const VIEWER_PAGE = 'pdf/viewer.html';

const inflight = new Map();          // 同词并发去重
const negImage = new Map();          // 图片负缓存（内存）
const pdfTabs = new Map();           // tabId -> 原始 PDF URL

/* ------------------------------------------------------------------ */
/* 基础工具                                                            */
/* ------------------------------------------------------------------ */

async function fetchJson(url, init, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs || 12000);
  try {
    const res = await fetch(url, Object.assign({ signal: ctrl.signal }, init || {}));
    const text = await res.text();
    if (!res.ok) {
      throw new Error('HTTP ' + res.status + (text ? ' · ' + text.slice(0, 120) : ''));
    }
    try {
      return JSON.parse(text);
    } catch (e) {
      throw new Error('返回内容不是合法 JSON');
    }
  } catch (e) {
    if (e && e.name === 'AbortError') throw new Error('请求超时');
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function toBase64(bytes) {
  let out = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    out += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(out);
}

async function hasAllUrls() {
  try {
    return await chrome.permissions.contains({ origins: ['<all_urls>'] });
  } catch (e) {
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* 结果缓存（chrome.storage.local，跨会话保留）                          */
/* ------------------------------------------------------------------ */

async function cacheAll() {
  const stored = await chrome.storage.local.get(CACHE_KEY);
  return (stored && stored[CACHE_KEY]) || {};
}

async function cacheGet(word) {
  const all = await cacheAll();
  const hit = all[word];
  return hit && hit.d ? hit.d : null;
}

async function cacheSet(word, data) {
  const all = await cacheAll();
  all[word] = { d: data, t: Date.now() };
  const keys = Object.keys(all);
  if (keys.length > CACHE_MAX) {
    keys.sort((a, b) => (all[a].t || 0) - (all[b].t || 0));
    keys.slice(0, keys.length - CACHE_MAX).forEach((k) => delete all[k]);
  }
  await chrome.storage.local.set({ [CACHE_KEY]: all });
}

async function clearCache() {
  const all = await cacheAll();
  const n = Object.keys(all).length;
  await chrome.storage.local.remove(CACHE_KEY);
  negImage.clear();
  return n;
}

async function cacheStats() {
  const all = await cacheAll();
  return { entries: Object.keys(all).length };
}

/* ------------------------------------------------------------------ */
/* 引擎：在线词典 / 本地小模型                                          */
/* ------------------------------------------------------------------ */

/** auto = 本地优先、失败回退在线；local = 只用本地；online = 只用在线 */
function engineOrder(settings, kind) {
  const cfg = settings.model;
  const localReady = cfg.enabled && (kind === 'vision' ? !!cfg.visionModel : !!cfg.textModel);
  if (settings.engine === 'local') return localReady ? ['local'] : [];
  if (settings.engine === 'online') return ['online'];
  return localReady ? ['local', 'online'] : ['online'];
}

async function queryOnline(word) {
  const url = ONLINE_ENDPOINT + '?q=' + encodeURIComponent(word);
  const raw = await fetchJson(url, { method: 'GET' }, 12000);
  const data = ETNormalize.normalizeYoudao(raw, word);
  if (!data) throw new Error('词典未收录该词');
  return data;
}

async function queryTextModel(word, settings) {
  const target = ETSettings.modelTarget(settings, 'text');
  if (!target.model) throw new Error('未配置文本模型');
  const headers = { 'Content-Type': 'application/json' };
  if (target.apiKey) headers['Authorization'] = 'Bearer ' + target.apiKey;
  const body = {
    model: target.model,
    messages: ETNormalize.buildModelPrompt(word),
    stream: false,
    temperature: 0.2,
    max_tokens: 700
  };
  const json = await fetchJson(target.url, { method: 'POST', headers, body: JSON.stringify(body) }, target.timeoutMs);
  const text = (json && json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content) || '';
  const data = ETNormalize.normalizeModel(text, word);
  if (!data) throw new Error('小模型输出无法解析');
  data.source = '小模型 · ' + target.model;
  return data;
}

async function queryVision(dataUrl, settings, hint) {
  const target = ETSettings.modelTarget(settings, 'vision');
  if (!target.model) throw new Error('未配置视觉模型');
  const headers = { 'Content-Type': 'application/json' };
  if (target.apiKey) headers['Authorization'] = 'Bearer ' + target.apiKey;
  const body = {
    model: target.model,
    messages: [{
      role: 'user',
      content: [
        { type: 'text', text: ETNormalize.buildVisionPrompt(hint) },
        { type: 'image_url', image_url: { url: dataUrl } }
      ]
    }],
    stream: false,
    temperature: 0,
    max_tokens: 120
  };
  const json = await fetchJson(target.url, { method: 'POST', headers, body: JSON.stringify(body) }, target.timeoutMs);
  return (json && json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content) || '';
}

/* ------------------------------------------------------------------ */
/* 文本查词主流程                                                      */
/* ------------------------------------------------------------------ */

async function lookupWord(rawWord, settings) {
  const word = String(rawWord || '').trim();
  if (!ETNormalize.isEnglishWord(word)) return { ok: false, error: 'not-english' };
  if (!settings) settings = await ETSettings.get();
  if (!settings.enabled) return { ok: false, error: 'disabled' };

  const key = word.toLowerCase();
  const cached = await cacheGet(key);
  if (cached) return { ok: true, data: cached, cached: true, engine: cached.source };

  if (inflight.has(key)) return inflight.get(key);

  const task = (async () => {
    const errors = [];
    const order = engineOrder(settings, 'text');
    if (!order.length) return { ok: false, error: '已选择「只用本地小模型」，但小模型尚未启用' };
    for (const engine of order) {
      try {
        const data = engine === 'local'
          ? await queryTextModel(word, settings)
          : await queryOnline(word);
        await cacheSet(key, data);
        return { ok: true, data, cached: false, engine: data.source };
      } catch (e) {
        errors.push((engine === 'local' ? '小模型：' : '在线词典：') + (e && e.message ? e.message : e));
      }
    }
    return { ok: false, error: errors.join('；') };
  })();

  inflight.set(key, task);
  try {
    return await task;
  } finally {
    inflight.delete(key);
  }
}

/* ------------------------------------------------------------------ */
/* 图片取词：截图 → 裁剪 → 视觉模型 → 查词                              */
/* ------------------------------------------------------------------ */

async function cropScreenshot(shotDataUrl, rect, dpr) {
  const blob = await (await fetch(shotDataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  const scale = dpr && dpr > 0 ? dpr : 1;

  let x = Math.max(0, Math.round(rect.x * scale));
  let y = Math.max(0, Math.round(rect.y * scale));
  let w = Math.round(rect.w * scale);
  let h = Math.round(rect.h * scale);
  w = Math.min(w, bitmap.width - x);
  h = Math.min(h, bitmap.height - y);
  if (w <= 4 || h <= 4) throw new Error('裁剪区域无效');

  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, x, y, w, h, 0, 0, w, h);
  const outBlob = await canvas.convertToBlob({ type: 'image/png' });
  const buf = await outBlob.arrayBuffer();
  return { dataUrl: 'data:image/png;base64,' + toBase64(new Uint8Array(buf)), w, h };
}

async function handleImageLookup(msg) {
  const settings = await ETSettings.get();
  if (!settings.enabled) return { ok: false, error: 'disabled' };
  if (!settings.imageOcr.enabled) return { ok: false, error: 'image-ocr-off' };
  if (!settings.model.visionModel) return { ok: false, error: 'need-vision-model' };
  if (!(await hasAllUrls())) return { ok: false, error: 'need-permission' };

  const cellKey = (msg.imageKey || '-') + '|' + (msg.cell || '-');
  const negAt = negImage.get(cellKey);
  if (negAt && Date.now() - negAt < NEG_TTL) return { ok: false, error: 'not-english' };

  const shot = await chrome.tabs.captureVisibleTab(chrome.windows.WINDOW_ID_CURRENT, { format: 'png' });
  const crop = await cropScreenshot(shot, msg.rect, msg.dpr);

  // 告诉模型光标在裁剪图中的相对位置，便于它在多词时选对目标
  const hint = '横向 ' + Math.round((msg.offsetX || 0.5) * 100) + '%、纵向 ' + Math.round((msg.offsetY || 0.5) * 100) + '%';
  const raw = await queryVision(crop.dataUrl, settings, hint);
  const word = ETNormalize.pickWordFromVision(raw);

  if (!word) {
    negImage.set(cellKey, Date.now());
    return { ok: false, error: 'not-english' };
  }
  const result = await lookupWord(word, settings);
  if (result.ok) {
    result.fromImage = true;
    result.recognizedWord = word;
  }
  return result;
}

/* ------------------------------------------------------------------ */
/* 本地模型的 CORS：剥离 Origin 头                                       */
/* ------------------------------------------------------------------ */

/**
 * Ollama 默认只接受白名单来源，浏览器扩展发出的请求带
 * `Origin: chrome-extension://…`，会被 403 拒绝。
 * 这里用 declarativeNetRequest 只对本扩展发往 127.0.0.1 / localhost 的
 * 请求剥掉 Origin 头（Ollama 对无 Origin 的请求直接放行），
 * 从而免去用户配置 OLLAMA_ORIGINS 的步骤。
 * 规则通过 initiatorDomains 限定为本扩展，不影响网页自身的请求。
 */
const CORS_RULE_IDS = [1001, 1002];

async function installLocalModelCorsRule() {
  if (!chrome.declarativeNetRequest || !chrome.declarativeNetRequest.updateDynamicRules) return false;
  const mk = (id, host) => ({
    id: id,
    priority: 1,
    action: {
      type: 'modifyHeaders',
      requestHeaders: [{ header: 'origin', operation: 'remove' }]
    },
    condition: {
      urlFilter: '||' + host,
      resourceTypes: ['xmlhttprequest'],
      initiatorDomains: [chrome.runtime.id]
    }
  });
  try {
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: CORS_RULE_IDS,
      addRules: [mk(1001, '127.0.0.1'), mk(1002, 'localhost')]
    });
    return true;
  } catch (e) {
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* PDF 探测（webRequest 观察，不修改请求）                              */
/* ------------------------------------------------------------------ */

function setPdfBadge(tabId, on) {
  try {
    chrome.action.setBadgeText({ tabId, text: on ? 'PDF' : '' });
    chrome.action.setBadgeBackgroundColor({ tabId, color: '#4f46e5' });
  } catch (e) { /* 标签页可能已关闭 */ }
}

function viewerUrlFor(url) {
  return chrome.runtime.getURL(VIEWER_PAGE) + '?file=' + encodeURIComponent(url);
}

async function maybeAutoOpenPdf(tabId, url) {
  const settings = await ETSettings.get();
  if (!settings.pdf.autoOpen) return;
  if (!(await hasAllUrls())) return;
  if (!/^https?:/i.test(url)) return;
  try {
    await chrome.tabs.update(tabId, { url: viewerUrlFor(url) });
  } catch (e) { /* 忽略 */ }
}

const pdfHeaderWatcher = (details) => {
  if (details.tabId < 0 || details.frameId !== 0) return;
  const headers = details.responseHeaders || [];
  const ct = headers.find((h) => (h.name || '').toLowerCase() === 'content-type');
  const isPdf = !!ct && String(ct.value || '').toLowerCase().includes('application/pdf');
  if (isPdf) {
    pdfTabs.set(details.tabId, details.url);
    setPdfBadge(details.tabId, true);
    maybeAutoOpenPdf(details.tabId, details.url);
    maybePromptPdf(details.tabId, details.url);   // 用户要求：主动「发请求」让人打开阅读器
  } else if (pdfTabs.has(details.tabId)) {
    pdfTabs.delete(details.tabId);
    setPdfBadge(details.tabId, false);
  }
};

/* —— PDF 主动提醒 —— 检测到 PDF 就发一条系统通知，点「用增强阅读器打开」即切换。
   用户实测反馈：商店版「无法自动识别到我打开了 PDF，然后给我发请求打开 PDF 阅读器」——
   此前只有徽标和扩展弹窗里的按钮，都是**被动**的。这里补上主动提醒。
   权限只用 notifications（标准、不触发强警告）；切换用 tabs.update（无需 tabs 权限）。 */
const pendingNotices = new Map();   // 通知 id -> { tabId, url }
const pdfPrompted = new Set();      // 每个标签页只提醒一次（同一 PDF 不重复骚扰）

async function maybePromptPdf(tabId, url) {
  try {
    const settings = await ETSettings.get();
    if (settings.pdf.prompt === false) return;    // 可在设置里关掉
    if (settings.pdf.autoOpen) return;            // 已经自动切换过去了，没必要再提醒
    if (!/^https?:/i.test(url)) return;
    if (pdfPrompted.has(tabId)) return;
    pdfPrompted.add(tabId);
    const nid = 'et-pdf-' + tabId;
    pendingNotices.set(nid, { tabId: tabId, url: url });
    chrome.notifications.create(nid, {
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon128.png'),
      title: 'Easy Translator — 检测到 PDF',
      message: '在增强阅读器里打开就能悬停查词。（也可以点扩展图标里的「用增强阅读器打开」）',
      buttons: [{ title: '用增强阅读器打开' }],
      priority: 0
    }, function () { void chrome.runtime.lastError; });
  } catch (e) { /* 静默：提醒失败不影响查词 */ }
}

async function openViewerFromNotice(nid) {
  const rec = pendingNotices.get(nid);
  pendingNotices.delete(nid);
  try { chrome.notifications.clear(nid); } catch (e) { /* 忽略 */ }
  if (!rec) return;
  try { await chrome.tabs.update(rec.tabId, { url: viewerUrlFor(rec.url) }); } catch (e) { /* 忽略 */ }
}

if (chrome.notifications) {
  chrome.notifications.onButtonClicked.addListener(function (nid) { openViewerFromNotice(nid); });
  chrome.notifications.onClicked.addListener(function (nid) { openViewerFromNotice(nid); });
  chrome.notifications.onClosed.addListener(function (nid) { pendingNotices.delete(nid); });
}
chrome.tabs.onRemoved.addListener(function (tabId) { pdfPrompted.delete(tabId); });

/** 注册内容类型观察器；未授予「所有网站」权限时会失败，静默降级 */
function registerPdfWatcher() {
  try {
    chrome.webRequest.onHeadersReceived.removeListener(pdfHeaderWatcher);
  } catch (e) { /* 尚未注册 */ }
  try {
    chrome.webRequest.onHeadersReceived.addListener(
      pdfHeaderWatcher,
      { urls: ['<all_urls>'], types: ['main_frame'] },
      []
    );
  } catch (e) { /* 权限不足，忽略 */ }
}

chrome.tabs.onRemoved.addListener((tabId) => pdfTabs.delete(tabId));

/* ------------------------------------------------------------------ */
/* 消息路由                                                            */
/* ------------------------------------------------------------------ */

async function handle(msg, sender) {
  switch (msg && msg.type) {
    case 'lookup':
      return lookupWord(msg.word);

    case 'lookup-image':
      return handleImageLookup(msg);

    case 'get-settings':
      return { ok: true, settings: await ETSettings.get() };

    case 'save-settings':
      return { ok: true, settings: await ETSettings.set(msg.patch || {}) };

    case 'clear-cache':
      return { ok: true, cleared: await clearCache() };

    case 'cache-stats':
      return { ok: true, ...(await cacheStats()) };

    case 'permission-state':
      return { ok: true, allUrls: await hasAllUrls() };

    case 'warmup-model': {
      // 冷启动时 Ollama 需要把模型读进内存（CPU 上可能 1-3 分钟），
      // 用一个极短请求触发加载，后续查词就只耗时几百毫秒。
      const settings = await ETSettings.get();
      const target = ETSettings.modelTarget(settings, 'text');
      if (!target.model) return { ok: false, error: '未配置文本模型' };
      const headers = { 'Content-Type': 'application/json' };
      if (target.apiKey) headers['Authorization'] = 'Bearer ' + target.apiKey;
      const started = Date.now();
      const json = await fetchJson(target.url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: target.model,
          messages: [{ role: 'user', content: 'hi' }],
          stream: false,
          max_tokens: 1
        })
      }, Math.max(target.timeoutMs, 300000));
      return { ok: true, elapsed: Date.now() - started, model: target.model, loaded: !!json };
    }

    case 'test-text-model': {
      const settings = await ETSettings.get();
      const started = Date.now();
      const data = await queryTextModel(msg.word || 'serendipity', settings);
      return { ok: true, elapsed: Date.now() - started, data };
    }

    case 'test-vision-model': {
      const settings = await ETSettings.get();
      const started = Date.now();
      const png = await fetch(chrome.runtime.getURL('assets/vision-test.png'));
      const blob = await png.blob();
      const dataUrl = 'data:image/png;base64,' + toBase64(new Uint8Array(await blob.arrayBuffer()));
      const raw = await queryVision(dataUrl, settings, '横向 50%、纵向 50%');
      return {
        ok: true,
        elapsed: Date.now() - started,
        recognized: ETNormalize.pickWordFromVision(raw),
        raw: String(raw).slice(0, 200)
      };
    }

    case 'pdf-state': {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const tab = tabs && tabs[0];
      if (!tab || !tab.id) return { ok: true, isPdf: false };
      const known = pdfTabs.get(tab.id);
      const looksPdf = /\.pdf(\?|#|$)/i.test(tab.url || '');
      const isPdf = !!known || looksPdf;
      return {
        ok: true,
        isPdf,
        url: known || tab.url || '',
        viewerUrl: isPdf ? viewerUrlFor(known || tab.url) : ''
      };
    }

    case 'open-pdf-viewer': {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const tab = tabs && tabs[0];
      if (!tab || !tab.id) return { ok: false, error: '找不到当前标签页' };
      const url = pdfTabs.get(tab.id) || tab.url || '';
      if (!url) return { ok: false, error: '当前标签页没有 URL' };
      await chrome.tabs.update(tab.id, { url: viewerUrlFor(url) });
      return { ok: true };
    }

    default:
      return { ok: false, error: 'unknown message: ' + (msg && msg.type) };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handle(msg, sender)
    .then(sendResponse)
    .catch((e) => sendResponse({ ok: false, error: e && e.message ? e.message : String(e) }));
  return true;   // 异步响应
});

chrome.runtime.onInstalled.addListener(async () => {
  await ETSettings.get();        // 落盘默认设置
  await installLocalModelCorsRule();
  registerPdfWatcher();
});

// Service Worker 每次唤醒时确保规则存在（动态规则本身是持久化的，这里只做幂等兜底）
installLocalModelCorsRule();

chrome.permissions.onAdded.addListener(() => registerPdfWatcher());
