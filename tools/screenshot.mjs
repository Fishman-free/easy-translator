/**
 * Easy Translator — 开发用真机截图（加载仓库里的扩展，截图到 docs/）
 *
 *   npm run screenshot
 *
 * 商店上架素材请用 tools/store-screenshots.mjs（1280x800，输出到 store/screenshots/）。
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { findBrowser, headlessFlags } from './lib/browser.mjs';
import { CDP, cdpJson, openTarget, waitForCdp, sleep } from './lib/cdp.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CDP_PORT = 9334;
const HTTP_PORT = 8792;

const MIME = {
  '.html': 'text/html', '.png': 'image/png', '.pdf': 'application/pdf',
  '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.mjs': 'text/javascript'
};

/** 未解压扩展的 ID 由绝对路径推导（仅作兜底；优先从 CDP 目标里读真实 ID） */
function unpackedId(absPath) {
  const hash = crypto.createHash('sha256').update(absPath).digest();
  let id = '';
  for (let i = 0; i < 16; i++) id += String.fromCharCode(97 + (hash[i] >> 4)) + String.fromCharCode(97 + (hash[i] & 0xf));
  return id;
}

function startServer() {
  const server = http.createServer((req, res) => {
    const file = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end(); return;
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Access-Control-Allow-Origin': '*'
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(HTTP_PORT, '127.0.0.1', () => resolve(server)));
}

async function main() {
  const browser = findBrowser();
  if (!browser) {
    console.error('找不到 Chromium 系浏览器（可用 ET_BROWSER 指定路径）');
    process.exit(2);
  }

  const server = await startServer();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'et-shot-'));
  const child = spawn(browser, headlessFlags({
    remoteDebuggingPort: CDP_PORT,
    extensionDir: ROOT,
    windowSize: '1280,860'
  }).concat(['--user-data-dir=' + profile, 'about:blank']), { stdio: ['ignore', 'pipe', 'pipe'] });

  const logs = [];
  const collect = (b) => String(b).split('\n').forEach((l) => l.trim() && logs.push(l.trim()));
  child.stdout.on('data', collect);
  child.stderr.on('data', collect);

  const docs = path.join(ROOT, 'docs');
  fs.mkdirSync(docs, { recursive: true });

  try {
    if (!await waitForCdp(CDP_PORT, { child })) {
      console.error('浏览器未就绪：\n' + logs.slice(-12).join('\n'));
      process.exit(1);
    }

    /* —— 网页卡片 —— */
    const webUrl = 'http://127.0.0.1:' + HTTP_PORT + '/tests/manual-test.html';
    const webTarget = await openTarget(CDP_PORT, webUrl);
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
    const list = await cdpJson(CDP_PORT, '/json/list');
    let extId = null;
    list.forEach((t) => {
      const m = /^chrome-extension:\/\/([a-p]+)\/(.*)$/.exec(t.url || '');
      // 只认我们自己的目标（background service worker），避免误取浏览器内置扩展的 ID
      if (m && !extId && /background\.js$/.test(m[2] || '')) extId = m[1];
    });
    console.log('解析到的扩展 ID：' + (extId || '(未取到，用路径推导)'));
    if (!extId) extId = unpackedId(ROOT);

    const pdfUrl = 'chrome-extension://' + extId + '/pdf/viewer.html?file=' +
      encodeURIComponent('http://127.0.0.1:' + HTTP_PORT + '/tests/fixtures/sample.pdf');
    const pdfTarget = await openTarget(CDP_PORT, pdfUrl);
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
