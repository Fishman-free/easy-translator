/**
 * Easy Translator — 内置 PDF 阅读器引导脚本
 *
 * 用 pdf.js 的 TextLayer 把 PDF 文本渲染成真实 DOM 文本，
 * 于是 content/hover-core.js 那套「悬停取词」逻辑可以原样复用
 * （内置的 Chrome PDF 查看器是封闭页面，任何扩展都注入不进去）。
 */
import * as pdfjsLib from '../pdfjs/build/pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL('pdfjs/build/pdf.worker.min.mjs');

const PAGES = document.getElementById('pages');
const STATUS = document.getElementById('status');
const EMPTY = document.getElementById('empty');
const PAGE_INPUT = document.getElementById('pageInput');
const PAGE_COUNT = document.getElementById('pageCount');
const ZOOM_LABEL = document.getElementById('zoomLabel');

const state = {
  doc: null,
  scale: 1.35,
  holders: [],
  rendered: new Set(),
  rendering: new Set(),
  observer: null
};

function setStatus(text, hint) {
  STATUS.innerHTML = '';
  STATUS.textContent = text || '';
  if (hint) {
    const span = document.createElement('span');
    span.className = 'hint';
    span.textContent = ' · ' + hint;
    STATUS.appendChild(span);
  }
}

function cleanup() {
  if (state.observer) state.observer.disconnect();
  state.rendered.clear();
  state.rendering.clear();
  state.holders.forEach((h) => h.remove());
  state.holders = [];
  state.doc = null;
}

/** 记录最近一次失败原因到 window.__pdfError（便于排查；e2e 也会读它做诊断） */
function noteError(where, e) {
  const msg = (e && e.message) ? e.message : String(e);
  window.__pdfError = where + ': ' + msg;
  return msg;
}

async function openDocument(source, label) {
  cleanup();
  EMPTY.style.display = 'none';
  setStatus(label || '正在加载…');

  const params = {
    cMapUrl: chrome.runtime.getURL('pdfjs/cmaps/'),
    cMapPacked: true,
    standardFontDataUrl: chrome.runtime.getURL('pdfjs/standard_fonts/')
  };

  let doc;
  try {
    doc = await pdfjsLib.getDocument(Object.assign(params, source)).promise;
  } catch (e) {
    const msg = noteError('加载文档', e);
    if (/Missing PDF|Unexpected server response|Failed to fetch|NetworkError/i.test(msg)) {
      setStatus('无法读取该 PDF', '若是跨站链接，请在扩展弹窗中授予「所有网站」权限后重试');
    } else {
      setStatus('打开失败：' + msg);
    }
    return;
  }

  state.doc = doc;
  PAGE_COUNT.textContent = '/ ' + doc.numPages;
  document.title = (label || 'PDF') + ' · Easy Translator';

  // 用第一页的尺寸预排所有页，避免加载过程中跳动
  let baseViewport = null;
  try {
    const first = await doc.getPage(1);
    baseViewport = first.getViewport({ scale: state.scale });
  } catch (e) { /* 忽略 */ }

  const w = baseViewport ? Math.floor(baseViewport.width) : 760;
  const h = baseViewport ? Math.floor(baseViewport.height) : 1000;

  for (let i = 1; i <= doc.numPages; i++) {
    const holder = document.createElement('div');
    holder.className = 'page';
    holder.dataset.page = String(i);
    holder.style.width = w + 'px';
    holder.style.height = h + 'px';
    holder.style.setProperty('--scale-factor', String(state.scale));

    const placeholder = document.createElement('div');
    placeholder.className = 'placeholder';
    placeholder.textContent = '第 ' + i + ' 页';
    holder.appendChild(placeholder);
    PAGES.appendChild(holder);
    state.holders.push(holder);
  }

  state.observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        const n = Number(entry.target.dataset.page);
        renderPage(n);
      }
    });
  }, { rootMargin: '600px 0px' });

  state.holders.forEach((h) => state.observer.observe(h));
  setStatus(label || '已加载', doc.numPages + ' 页');

  // 支持 #page=N 直接定位
  const m = /#page=(\d+)/.exec(location.hash);
  if (m) setTimeout(() => goToPage(Number(m[1])), 120);
}

async function renderPage(n) {
  if (!state.doc || state.rendered.has(n) || state.rendering.has(n)) return;
  state.rendering.add(n);
  const holder = state.holders[n - 1];
  try {
    const page = await state.doc.getPage(n);
    const viewport = page.getViewport({ scale: state.scale });
    const outputScale = Math.min(window.devicePixelRatio || 1, 2);

    holder.style.width = Math.floor(viewport.width) + 'px';
    holder.style.height = Math.floor(viewport.height) + 'px';
    holder.style.setProperty('--scale-factor', String(state.scale));

    let canvas = holder.querySelector('canvas');
    if (!canvas) {
      canvas = document.createElement('canvas');
      holder.appendChild(canvas);
    }
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = Math.floor(viewport.width) + 'px';
    canvas.style.height = Math.floor(viewport.height) + 'px';

    const ctx = canvas.getContext('2d');
    const renderTask = page.render({
      canvasContext: ctx,
      viewport,
      transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null
    });
    await renderTask.promise;

    let textDiv = holder.querySelector('.textLayer');
    if (!textDiv) {
      textDiv = document.createElement('div');
      textDiv.className = 'textLayer';
      holder.appendChild(textDiv);
    }
    textDiv.replaceChildren();
    textDiv.style.setProperty('--scale-factor', String(state.scale));

    const textLayer = new pdfjsLib.TextLayer({
      textContentSource: await page.getTextContent(),
      container: textDiv,
      viewport
    });
    await textLayer.render();

    const ph = holder.querySelector('.placeholder');
    if (ph) ph.remove();
    state.rendered.add(n);
  } catch (e) {
    noteError('渲染第 ' + n + ' 页', e);
    const ph = holder.querySelector('.placeholder');
    if (ph) ph.textContent = '第 ' + n + ' 页渲染失败';
  } finally {
    state.rendering.delete(n);
  }
}

function rerenderAll() {
  state.rendered.clear();
  state.rendering.clear();
  state.holders.forEach((holder) => {
    holder.querySelectorAll('canvas, .textLayer').forEach((n) => n.remove());
  });
  const visible = new IntersectionObserver((entries, obs) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) renderPage(Number(entry.target.dataset.page));
    });
    obs.disconnect();
  });
  state.holders.forEach((h) => visible.observe(h));
  setTimeout(() => visible.disconnect(), 1500);
}

function goToPage(n) {
  const page = Math.min(Math.max(1, n), state.holders.length || 1);
  const holder = state.holders[page - 1];
  if (holder) holder.scrollIntoView({ block: 'start' });
  PAGE_INPUT.value = String(page);
}

function currentPage() {
  const y = window.scrollY + 120;
  for (let i = state.holders.length - 1; i >= 0; i--) {
    if (state.holders[i].offsetTop <= y) return i + 1;
  }
  return 1;
}

function setScale(next) {
  state.scale = Math.min(4, Math.max(0.4, Math.round(next * 100) / 100));
  ZOOM_LABEL.textContent = Math.round(state.scale / 1.35 * 100) + '%';
  rerenderAll();
}

/* ---------------- 工具栏 ---------------- */

document.getElementById('prev').addEventListener('click', () => goToPage(currentPage() - 1));
document.getElementById('next').addEventListener('click', () => goToPage(currentPage() + 1));
document.getElementById('zoomIn').addEventListener('click', () => setScale(state.scale + 0.2));
document.getElementById('zoomOut').addEventListener('click', () => setScale(state.scale - 0.2));
PAGE_INPUT.addEventListener('change', () => goToPage(Number(PAGE_INPUT.value)));
document.getElementById('openLocal').addEventListener('click', () => {
  document.getElementById('fileInput').click();
});

document.getElementById('fileInput').addEventListener('change', async (ev) => {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const buf = await file.arrayBuffer();
  const doc = { data: new Uint8Array(buf) };
  const hash = '#page=1';
  history.replaceState(null, '', location.pathname + hash);
  openDocument(doc, file.name);
});

window.addEventListener('scroll', () => {
  PAGE_INPUT.value = String(currentPage());
}, { passive: true });

/* ---------------- 拖放本地文件 ---------------- */

['dragenter', 'dragover'].forEach((type) => {
  window.addEventListener(type, (ev) => {
    ev.preventDefault();
    document.body.classList.add('drop-active');
  });
});
['dragleave', 'drop'].forEach((type) => {
  window.addEventListener(type, (ev) => {
    ev.preventDefault();
    if (type === 'drop' || ev.relatedTarget === null) document.body.classList.remove('drop-active');
  });
});
window.addEventListener('drop', async (ev) => {
  const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
  if (!file) return;
  const buf = await file.arrayBuffer();
  openDocument({ data: new Uint8Array(buf) }, file.name);
});

/* ---------------- 启动 ---------------- */

// 悬停取词引擎（与网页共用同一实现）
if (window.ETHover) {
  window.ETHover.start({ doc: document, win: window });
}

// 从 ?file= 打开远程 PDF
const fileParam = new URLSearchParams(location.search).get('file');
if (fileParam) {
  openDocument({ url: fileParam }, decodeURIComponent(fileParam.split('/').pop() || 'PDF'));
} else {
  setStatus('等待打开文件');
}
