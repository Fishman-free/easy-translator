/**
 * Easy Translator — 端到端测试（headless Edge + CDP，零依赖）
 *
 * 用真实的 Edge 加载扩展、派发真实鼠标事件，验证四件事：
 *   1. 扩展能加载，内容脚本注入成功；
 *   2. 悬停中文 → 不弹窗；
 *   3. 悬停空白 → 不弹窗；
 *   4. 悬停英文单词 5 秒 → 卡片出现，且经由有道词典拿到真实释义；
 *   5. 扩展的 popup / options 页面无 JS 异常。
 *
 * 用法： node tools/e2e.mjs
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { findBrowser, headlessFlags } from './lib/browser.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CDP_PORT = 9333;
const HTTP_PORT = 8791;
const DWELL_WAIT_MS = 8500;   // 触发时长(5s) + 查询与渲染余量

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + (detail ? '   [' + detail + ']' : ''));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------------- 静态服务器（内容脚本不会注入 file:// 页面） ---------------- */

function startServer() {
  const mime = { '.html': 'text/html', '.png': 'image/png', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.mjs': 'text/javascript' };
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]);
    const file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end('not found'); return;
    }
    res.writeHead(200, {
      'Content-Type': mime[path.extname(file)] || 'application/octet-stream',
      'Access-Control-Allow-Origin': '*'
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(HTTP_PORT, '127.0.0.1', () => resolve(server)));
}

/* ---------------- 极简 CDP 客户端 ---------------- */

class CDP {
  constructor(wsUrl) { this.wsUrl = wsUrl; this.id = 0; this.pending = new Map(); this.handlers = []; }

  connect() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.wsUrl);
      this.ws = ws;
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve: res, reject: rej } = this.pending.get(msg.id);
          this.pending.delete(msg.id);
          msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
        } else if (msg.method) {
          this.handlers.forEach((h) => h(msg));
        }
      };
      ws.onopen = () => resolve();
      ws.onerror = (e) => reject(new Error('WebSocket 连接失败: ' + (e.message || 'unknown')));
    });
  }

  on(fn) { this.handlers.push(fn); }

  send(method, params) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  async evaluate(expression, contextId) {
    const params = { expression, returnByValue: true, awaitPromise: true };
    if (contextId) params.contextId = contextId;
    const res = await this.send('Runtime.evaluate', params);
    if (res.exceptionDetails) {
      throw new Error('页面异常: ' + (res.exceptionDetails.exception?.description || res.exceptionDetails.text));
    }
    return res.result.value;
  }

  async mouseMove(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none', buttons: 0, clickCount: 0 });
  }

  close() { try { this.ws.close(); } catch (e) { /* 忽略 */ } }
}

async function cdpJson(pathname, init) {
  const res = await fetch('http://127.0.0.1:' + CDP_PORT + pathname, init);
  return res.json();
}

/* ---------------- 扩展 ID ---------------- */

function unpackedId(absPath) {
  const hash = crypto.createHash('sha256').update(absPath).digest();
  let id = '';
  for (let i = 0; i < 16; i++) id += String.fromCharCode(97 + (hash[i] >> 4)) + String.fromCharCode(97 + (hash[i] & 0xf));
  return id;
}

/* ---------------- 主流程 ---------------- */

async function main() {
  const browser = findBrowser();
  if (!browser) {
    console.error('找不到 Chromium 系浏览器（Edge/Chrome/Chromium）。可用环境变量 ET_BROWSER 显式指定路径。');
    process.exit(2);
  }
  console.log('浏览器：' + browser);
  console.log('扩展目录：' + ROOT + '\n');

  const server = await startServer();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'et-e2e-'));
  const pageUrl = 'http://127.0.0.1:' + HTTP_PORT + '/tests/manual-test.html';

  const child = spawn(browser, headlessFlags({
    remoteDebuggingPort: CDP_PORT,
    extensionDir: ROOT
  }).concat(['about:blank']), { stdio: 'ignore' });

  const cleanup = () => {
    try { child.kill(); } catch (e) { /* 忽略 */ }
    try { server.close(); } catch (e) { /* 忽略 */ }
  };

  try {
    // 等待 CDP 就绪
    let ready = false;
    for (let i = 0; i < 60 && !ready; i++) {
      await sleep(500);
      try { await cdpJson('/json/version'); ready = true; } catch (e) { /* 继续等 */ }
    }
    check('浏览器调试端口就绪', ready);
    if (!ready) throw new Error('CDP 未就绪');

    // 打开测试页
    await cdpJson('/json/new?' + encodeURIComponent(pageUrl), { method: 'PUT' }).catch(async () => {
      return cdpJson('/json/new?' + pageUrl, { method: 'PUT' });
    });

    let pageTarget = null;
    for (let i = 0; i < 40 && !pageTarget; i++) {
      await sleep(300);
      const list = await cdpJson('/json/list');
      pageTarget = list.find((t) => t.type === 'page' && t.url.indexOf('manual-test.html') !== -1);
    }
    check('测试页已打开', !!pageTarget);
    if (!pageTarget) throw new Error('测试页未打开');

    const page = new CDP(pageTarget.webSocketDebuggerUrl);
    await page.connect();

    const contexts = [];
    const pageErrors = [];
    page.on((msg) => {
      if (msg.method === 'Runtime.executionContextCreated') contexts.push(msg.params.context);
      if (msg.method === 'Runtime.exceptionThrown') {
        pageErrors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
      }
    });
    await page.send('Runtime.enable');
    await page.send('Page.enable');

    // 等页面加载完成
    for (let i = 0; i < 40; i++) {
      const state = await page.evaluate('document.readyState');
      if (state === 'complete') break;
      await sleep(250);
    }
    await sleep(1200);   // 留出 document_idle 注入时间

    const isolated = contexts.filter((c) => c.auxData && c.auxData.type === 'isolated');
    check('内容脚本注入（隔离世界已创建）', isolated.length > 0,
      isolated.map((c) => c.name).join(', ') || 'none');

    const centerOf = async (selector) => {
      const json = await page.evaluate(`(() => {
        const el = document.querySelector(${JSON.stringify(selector)});
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(el);
        const rects = Array.from(range.getClientRects()).filter(t => t.width > 1);
        const pick = rects.length ? rects[0] : r;
        return { x: Math.round(pick.left + Math.min(3, pick.width / 2)), y: Math.round(pick.top + pick.height / 2) };
      })()`);
      return json;
    };

    const cardState = () => page.evaluate(`(() => {
      const host = document.querySelector('[data-easy-translator="card"]');
      if (!host) return { exists: false };
      return { exists: true, state: host.dataset.etState, word: host.dataset.etWord, source: host.dataset.etSource };
    })()`);

    /* —— 场景 1：中文不弹窗 —— */
    const cnPt = await centerOf('#cn');
    await page.mouseMove(cnPt.x, cnPt.y);
    await sleep(DWELL_WAIT_MS);
    let st = await cardState();
    check('悬停中文：不弹窗', !st.exists || st.state === 'hidden', JSON.stringify(st));

    /* —— 场景 2：空白不弹窗 —— */
    const blankPt = await centerOf('#blank');
    await page.mouseMove(blankPt.x, blankPt.y);
    await sleep(DWELL_WAIT_MS);
    st = await cardState();
    check('悬停空白：不弹窗', !st.exists || st.state === 'hidden', JSON.stringify(st));

    /* —— 场景 3：英文单词 5 秒 → 弹窗并拿到真实释义 —— */
    const enPt = await centerOf('#en-word');
    await page.mouseMove(enPt.x - 40, enPt.y - 30);   // 先离开，避免复用上一个目标
    await sleep(200);
    await page.mouseMove(enPt.x, enPt.y);
    await sleep(DWELL_WAIT_MS + 4000);
    st = await cardState();
    check('悬停英文：弹出卡片', st.exists && st.state === 'result', JSON.stringify(st));
    check('卡片词条正确', st.exists && String(st.word).toLowerCase() === 'serendipity', String(st.word));
    check('经在线词典取得释义', st.exists && /有道/.test(String(st.source)), String(st.source));

    check('页面无 JS 异常', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

    /* —— 扩展 ID 与打开标签页的工具 —— */
    const listAll = await cdpJson('/json/list');
    let extId = null;
    listAll.forEach((t) => {
      const m = /^chrome-extension:\/\/([a-p]+)\//.exec(t.url || '');
      if (m && !extId) extId = m[1];
    });
    if (!extId) extId = unpackedId(ROOT);
    check('解出扩展 ID', !!extId, extId);

    const openTarget = async (url) => {
      await cdpJson('/json/new?' + encodeURIComponent(url), { method: 'PUT' }).catch(() => null);
      for (let i = 0; i < 40; i++) {
        await sleep(300);
        const l = await cdpJson('/json/list');
        const t = l.find((x) => x.url === url);
        if (t) return t;
      }
      return null;
    };

    const CARD_STATE_JS = `(() => {
      const host = document.querySelector('[data-easy-translator="card"]');
      if (!host) return { exists: false };
      return { exists: true, state: host.dataset.etState, word: host.dataset.etWord, source: host.dataset.etSource };
    })()`;

    const findWordJs = (word) => `(() => {
      const spans = Array.from(document.querySelectorAll('.textLayer span'));
      for (const span of spans) {
        const t = span.textContent || '';
        const idx = t.toLowerCase().indexOf(${JSON.stringify(word)});
        if (idx === -1) continue;
        const node = span.firstChild;
        if (!node || node.nodeType !== 3) continue;
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + ${word.length});
        const r = range.getClientRects()[0];
        if (!r) continue;
        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
      }
      return null;
    })()`;

    /* —— 场景 4：扩展自身页面无异常 —— */
    for (const pageName of ['popup/popup.html', 'options/options.html']) {
      const url = 'chrome-extension://' + extId + '/' + pageName;
      const target = await openTarget(url);
      if (!target) { check('打开 ' + pageName, false, '未找到标签页'); continue; }
      const c = new CDP(target.webSocketDebuggerUrl);
      await c.connect();
      const errs = [];
      c.on((msg) => {
        if (msg.method === 'Runtime.exceptionThrown') {
          errs.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
        }
      });
      await c.send('Runtime.enable');
      await sleep(700);
      const title = await c.evaluate('document.title').catch(() => '');
      const hasBody = await c.evaluate('!!document.body && document.body.children.length > 0').catch(() => false);
      check(pageName + ' 正常渲染且无 JS 异常', hasBody && errs.length === 0,
        (title ? '标题=' + title + ' ' : '') + (errs.slice(0, 1).join(' ') || ''));
      if (pageName.indexOf('options') !== -1) globalThis.__optionsWs = target.webSocketDebuggerUrl;
      c.close();
    }

    /* —— 场景 5：内置 PDF 阅读器里悬停取词 —— */
    const pdfPageUrl = 'chrome-extension://' + extId + '/pdf/viewer.html?file=' +
      encodeURIComponent('http://127.0.0.1:' + HTTP_PORT + '/tests/fixtures/sample.pdf');
    const pdfTarget = await openTarget(pdfPageUrl);
    check('内置 PDF 阅读器页面已打开', !!pdfTarget);
    if (pdfTarget) {
      const pdf = new CDP(pdfTarget.webSocketDebuggerUrl);
      await pdf.connect();
      await pdf.send('Runtime.enable');
      let pt = null;
      for (let i = 0; i < 60 && !pt; i++) {
        await sleep(500);
        pt = await pdf.evaluate(findWordJs('quick')).catch(() => null);
      }
      check('PDF 文本层渲染出可悬停文本', !!pt, pt ? 'x=' + pt.x + ', y=' + pt.y : '未找到 quick');
      if (pt) {
        await pdf.mouseMove(pt.x + 80, pt.y + 60);
        await sleep(300);
        await pdf.mouseMove(pt.x, pt.y);
        await sleep(DWELL_WAIT_MS + 4000);
        const pst = await pdf.evaluate(CARD_STATE_JS).catch(() => ({ exists: false }));
        check('PDF 中悬停英文单词可查词', pst.exists && pst.state === 'result' && String(pst.word).toLowerCase() === 'quick',
          JSON.stringify(pst));
      }
      pdf.close();
    }

    /* —— 场景 6：DNR 规则 + 小模型链路 —— */
    if (globalThis.__optionsWs) {
      const opts = new CDP(globalThis.__optionsWs);
      await opts.connect();
      await opts.send('Runtime.enable');

      // 6a. DNR 规则必须始终注册成功：它是「免配置访问本机模型」的前提（CI 上也要验）
      const rules = await opts.evaluate(
        'chrome.declarativeNetRequest.getDynamicRules().then(r => r.map(x => ({ id: x.id, headers: (x.action.requestHeaders || []).map(h => h.header) })))'
      ).catch(() => null);
      check('已注册「剥离 Origin」的 DNR 规则', Array.isArray(rules) && rules.length >= 2, JSON.stringify(rules));

      // 6b. 小模型查词链路：需要本机 Ollama，缺失则跳过（不判失败）
      const ollamaUp = await fetch('http://127.0.0.1:11434/api/version').then((r) => r.ok).catch(() => false);
      if (!ollamaUp) {
        console.log('  ⚠ 跳过小模型查词链路测试：本机 11434 端口没有 Ollama');
      } else {
        await opts.evaluate(`(async () => {
          const cur = (await chrome.storage.local.get('settings')).settings || {};
          const s = Object.assign({}, cur, { engine: 'local' });
          s.model = Object.assign({}, cur.model, { enabled: true, baseUrl: 'http://127.0.0.1:11434/v1', textModel: 'qwen2.5:1.5b', timeoutMs: 90000 });
          await chrome.storage.local.set({ settings: s });
          return true;
        })()`).catch(() => null);

        const t0 = Date.now();
        const res = await opts.evaluate("chrome.runtime.sendMessage({type:'test-text-model', word:'hello'})")
          .catch((e) => ({ ok: false, error: e.message }));
        if (res && res.ok) {
          const first = (res.data && res.data.poses && res.data.poses[0] && res.data.poses[0].meaning) || '';
          check('小模型查词链路打通（浏览器内 200，说明 DNR 生效）', true,
            Math.round((Date.now() - t0) / 1000) + 's · ' + first.slice(0, 24));
        } else {
          check('小模型查词链路打通（浏览器内 200，说明 DNR 生效）', false, String(res && res.error));
        }

        // 还原设置，避免影响后续手动使用
        await opts.evaluate(`(async () => {
          const cur = (await chrome.storage.local.get('settings')).settings || {};
          const s = Object.assign({}, cur, { engine: 'auto' });
          s.model = Object.assign({}, cur.model, { enabled: false });
          await chrome.storage.local.set({ settings: s });
          return true;
        })()`).catch(() => null);
      }
      opts.close();
    }
  } finally {
    cleanup();
    await sleep(600);
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) { /* 忽略 */ }
  }

  const failed = results.filter((r) => !r.ok);
  console.log('\n' + '─'.repeat(58));
  console.log('E2E 结果：' + (results.length - failed.length) + '/' + results.length + ' 项通过');
  if (failed.length) {
    console.log('失败项：' + failed.map((f) => f.name).join('；'));
    process.exit(1);
  }
}

main().catch((e) => {
  console.error('\nE2E 运行失败：' + (e && e.message ? e.message : e));
  process.exit(1);
});
