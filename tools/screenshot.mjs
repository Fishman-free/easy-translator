/**
 * Easy Translator — 真机截图工具
 *
 * 加载扩展 → 打开测试页 → 悬停英文单词 → 截屏；再打开内置 PDF 阅读器截图。
 * 产物：docs/screenshot-web.png、docs/screenshot-pdf.png
 *
 * 用法： node tools/screenshot.mjs
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
].find((p) => fs.existsSync(p));

const CDP_PORT = 9334;
const HTTP_PORT = 8792;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CDP {
  constructor(wsUrl) { this.wsUrl = wsUrl; this.id = 0; this.pending = new Map(); }
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
        }
      };
      ws.onopen = resolve;
      ws.onerror = (e) => reject(new Error('ws error ' + (e.message || '')));
    });
  }
  send(method, params) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params: params || {} }));
    return new Promise((res, rej) => this.pending.set(id, { resolve: res, reject: rej }));
  }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    return r.result.value;
  }
  async mouseMove(x, y) {
    await this.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none', buttons: 0, clickCount: 0 });
  }
  close() { try { this.ws.close(); } catch (e) { /* 忽略 */ } }
}

const j = (p, init) => fetch('http://127.0.0.1:' + CDP_PORT + p, init).then((r) => r.json());

async function main() {
  const mime = { '.html': 'text/html', '.png': 'image/png', '.pdf': 'application/pdf', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.mjs': 'text/javascript' };
  const server = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Access-Control-Allow-Origin': '*' });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((r) => server.listen(HTTP_PORT, '127.0.0.1', r));

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'et-shot-'));
  const child = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--user-data-dir=' + profile, '--remote-debugging-port=' + CDP_PORT,
    '--disable-extensions-except=' + ROOT, '--load-extension=' + ROOT,
    '--window-size=1280,860', 'about:blank'
  ], { stdio: 'ignore' });

  const docs = path.join(ROOT, 'docs');
  fs.mkdirSync(docs, { recursive: true });

  try {
    for (let i = 0; i < 60; i++) { await sleep(500); try { await j('/json/version'); break; } catch (e) { /* 继续 */ } }

    const open = async (url) => {
      await j('/json/new?' + encodeURIComponent(url), { method: 'PUT' }).catch(() => null);
      for (let i = 0; i < 40; i++) {
        await sleep(300);
        const l = await j('/json/list');
        const t = l.find((x) => x.url === url);
        if (t) return t;
      }
      return null;
    };

    /* —— 网页卡片 —— */
    const webUrl = 'http://127.0.0.1:' + HTTP_PORT + '/tests/manual-test.html';
    const webTarget = await open(webUrl);
    const page = new CDP(webTarget.webSocketDebuggerUrl);
    await page.connect();
    await page.send('Runtime.enable');
    await page.send('Page.enable');
    await page.send('Page.bringToFront').catch(() => null);
    await sleep(1500);

    const pt = await page.evaluate(`(() => {
      const el = document.getElementById('en-word');
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
    })()`);
    await page.mouseMove(pt.x - 60, pt.y - 40);
    await sleep(300);
    await page.mouseMove(pt.x, pt.y);
    await sleep(9000);

    const shot1 = await page.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(docs, 'screenshot-web.png'), Buffer.from(shot1.data, 'base64'));
    const cardSeen = await page.evaluate(`(() => {
      const h = document.querySelector('[data-easy-translator="card"]');
      return h ? { state: h.dataset.etState, word: h.dataset.etWord } : null;
    })()`);
    console.log('已保存 docs/screenshot-web.png · 卡片状态：' + JSON.stringify(cardSeen));
    page.close();

    /* —— PDF 阅读器卡片 —— */
    const list = await j('/json/list');
    let extId = null;
    list.forEach((t) => {
      const m = /^chrome-extension:\/\/([a-p]+)\/(.*)$/.exec(t.url || '');
      // 只认我们自己的目标（background service worker），避免误取浏览器内置扩展的 ID
      if (m && !extId && /background\.js$/.test(m[2] || '')) extId = m[1];
    });
    console.log('解析到的扩展 ID：' + (extId || '(未取到，将用路径推导)'));
    if (!extId) {
      console.log('当前目标：' + list.map((t) => t.type + ' ' + t.url).join(' | '));
    }
    if (!extId) {
      // 未解压扩展的 ID 由绝对路径的 SHA-256 推导（前 16 字节映射到 a–p）
      const hash = crypto.createHash('sha256').update(ROOT).digest();
      extId = '';
      for (let i = 0; i < 16; i++) extId += String.fromCharCode(97 + (hash[i] >> 4)) + String.fromCharCode(97 + (hash[i] & 0xf));
      console.log('未从目标列表取到扩展 ID，改用路径推导：' + extId);
    }
    const pdfUrl = 'chrome-extension://' + extId + '/pdf/viewer.html?file=' +
      encodeURIComponent('http://127.0.0.1:' + HTTP_PORT + '/tests/fixtures/sample.pdf');
    const pdfTarget = await open(pdfUrl);
    if (pdfTarget) {
      const pdf = new CDP(pdfTarget.webSocketDebuggerUrl);
      await pdf.connect();
      await pdf.send('Runtime.enable');
      await pdf.send('Page.enable');
      await pdf.send('Page.bringToFront').catch(() => null);   // 后台标签页不渲染，必须置前
      let wp = null;
      for (let i = 0; i < 60 && !wp; i++) {
        await sleep(500);
        wp = await pdf.evaluate(`(() => {
          const spans = Array.from(document.querySelectorAll('.textLayer span'));
          for (const span of spans) {
            const t = span.textContent || '';
            const idx = t.toLowerCase().indexOf('quick');
            if (idx === -1) continue;
            const node = span.firstChild;
            if (!node || node.nodeType !== 3) continue;
            const range = document.createRange();
            range.setStart(node, idx);
            range.setEnd(node, idx + 5);
            const r = range.getClientRects()[0];
            if (!r) continue;
            return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
          }
          return null;
        })()`).catch(() => null);
      }
      if (wp) {
        await pdf.mouseMove(wp.x + 80, wp.y + 60);
        await sleep(300);
        await pdf.mouseMove(wp.x, wp.y);
        await sleep(9000);
        const shot2 = await pdf.send('Page.captureScreenshot', { format: 'png' });
        fs.writeFileSync(path.join(docs, 'screenshot-pdf.png'), Buffer.from(shot2.data, 'base64'));
        console.log('已保存 docs/screenshot-pdf.png');
      } else {
        const diag = await pdf.evaluate(`(() => ({
          spans: document.querySelectorAll('.textLayer span').length,
          canvases: document.querySelectorAll('canvas').length,
          status: (document.getElementById('status') || {}).textContent || '',
          bodyHead: (document.body.innerText || '').slice(0, 160)
        }))()`).catch(() => null);
        console.log('PDF 文本层未就绪，跳过 PDF 截图。诊断：' + JSON.stringify(diag));
      }
      pdf.close();
    }
  } finally {
    try { child.kill(); } catch (e) { /* 忽略 */ }
    try { server.close(); } catch (e) { /* 忽略 */ }
    await sleep(500);
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) { /* 忽略 */ }
  }
}

main().catch((e) => { console.error('截图失败：' + (e && e.message)); process.exit(1); });
