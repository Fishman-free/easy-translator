/**
 * Easy Translator — 生成商店上架用的截图（官方要求 1280x800 或 640x480）
 *
 *   npm run store:screenshots
 *
 * 产物：
 *   store/screenshots/1-web.png       普通网页悬停取词（用 store/demo-page.html 呈现真实阅读场景）
 *   store/screenshots/2-pdf.png       内置 PDF 阅读器里悬停取词
 *   store/screenshots/3-settings.png  设置页（展示双引擎 / 图片取词 / PDF 选项）
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { findBrowser, headlessFlags } from './lib/browser.mjs';
import { CDP, cdpJson, openTarget, waitForCdp, sleep } from './lib/cdp.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT_DIR = path.join(ROOT, 'store', 'screenshots');
const CDP_PORT = 9335;
const HTTP_PORT = 8793;
const WIDTH = 1280;
const HEIGHT = 800;
const DWELL_WAIT = 9000;   // 触发(5s) + 查询渲染余量

const MIME = {
  '.html': 'text/html', '.png': 'image/png', '.pdf': 'application/pdf',
  '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.mjs': 'text/javascript'
};

function startServer() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split('?')[0]);
    const file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end('not found'); return;
    }
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Access-Control-Allow-Origin': '*'
    });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(HTTP_PORT, '127.0.0.1', () => resolve(server)));
}

const CARD_STATE_JS = `(() => {
  const host = document.querySelector('[data-easy-translator="card"]');
  return host ? { exists: true, state: host.dataset.etState, word: host.dataset.etWord } : { exists: false };
})()`;

/** 悬停到页面上第一个含指定单词的位置，等卡片出现 */
async function hoverWord(session, word, { budgetMs = 30000 } = {}) {
  const point = await session.evaluate(`(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const text = node.textContent || '';
      const idx = text.toLowerCase().indexOf(${JSON.stringify(word)});
      if (idx === -1) continue;
      const range = document.createRange();
      range.setStart(node, idx);
      range.setEnd(node, idx + ${word.length});
      const rects = Array.from(range.getClientRects()).filter((r) => r.width > 1);
      if (!rects.length) continue;
      const r = rects[0];
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
    }
    return null;
  })()`);
  if (!point) return null;
  await session.mouseMove(point.x + 90, point.y + 70);
  await sleep(300);
  await session.mouseMove(point.x, point.y);

  const deadline = Date.now() + budgetMs;
  while (Date.now() < deadline) {
    await sleep(1000);
    const state = await session.evaluate(CARD_STATE_JS).catch(() => null);
    if (state && state.state === 'result') return state;
  }
  return null;
}

/** 从 PNG 文件头读出真实宽高（不靠脚本自报数字） */
function pngSize(file) {
  const buf = fs.readFileSync(file);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

/** 把视口精确固定为商店要求的尺寸（captureScreenshot 截的是视口，不是窗口） */
async function setStoreViewport(session) {
  await session.send('Emulation.setDeviceMetricsOverride', {
    width: WIDTH,
    height: HEIGHT,
    deviceScaleFactor: 1,
    mobile: false
  });
  await sleep(400);   // 等重排
}

async function shoot(session, name) {
  const shot = await session.send('Page.captureScreenshot', { format: 'png' });
  const file = path.join(OUT_DIR, name);
  fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));

  const size = pngSize(file);
  const ok = size.width === WIDTH && size.height === HEIGHT;
  sizes.push({ name, ...size, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + '   ' + size.width + 'x' + size.height +
    '   ' + (fs.statSync(file).size / 1024).toFixed(0) + ' KB');
  if (!ok) console.log('     ↑ 尺寸不符合商店要求（需要 ' + WIDTH + 'x' + HEIGHT + '）');
}

const sizes = [];

async function main() {
  const browser = findBrowser();
  if (!browser) {
    console.error('找不到 Chromium 系浏览器（可用 ET_BROWSER 指定）');
    process.exit(2);
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log('浏览器：' + browser);

  const server = await startServer();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'et-shots-'));
  const child = spawn(browser, headlessFlags({
    remoteDebuggingPort: CDP_PORT,
    extensionDir: ROOT,
    windowSize: WIDTH + ',' + HEIGHT
  }).concat(['--user-data-dir=' + profile, 'about:blank']), { stdio: ['ignore', 'pipe', 'pipe'] });

  const logs = [];
  const collect = (b) => String(b).split('\n').forEach((l) => l.trim() && logs.push(l.trim()));
  child.stdout.on('data', collect);
  child.stderr.on('data', collect);

  try {
    if (!await waitForCdp(CDP_PORT, { child })) {
      console.error('浏览器未就绪：\n' + logs.slice(-12).join('\n'));
      process.exit(1);
    }

    /* 1. 网页取词 */
    const webUrl = 'http://127.0.0.1:' + HTTP_PORT + '/store/demo-page.html';
    const webTarget = await openTarget(CDP_PORT, webUrl);
    const web = new CDP(webTarget.webSocketDebuggerUrl);
    await web.connect();
    await web.send('Runtime.enable');
    await web.send('Page.enable');
    await web.send('Page.bringToFront').catch(() => null);
    await setStoreViewport(web);
    await sleep(1200);
    const webState = await hoverWord(web, 'serendipity');
    if (!webState) console.log('  ⚠ 网页卡片未出现，仍截图（检查提示词/网络）');
    await sleep(600);
    await shoot(web, '1-web.png');
    web.close();

    /* 2. PDF 取词 */
    const list = await cdpJson(CDP_PORT, '/json/list');
    let extId = null;
    list.forEach((t) => {
      const m = /^chrome-extension:\/\/([a-p]+)\/(.*)$/.exec(t.url || '');
      if (m && !extId && /background\.js$/.test(m[2] || '')) extId = m[1];
    });
    if (extId) {
      const pdfUrl = 'chrome-extension://' + extId + '/pdf/viewer.html?file=' +
        encodeURIComponent('http://127.0.0.1:' + HTTP_PORT + '/store/demo.pdf');
      const pdfTarget = await openTarget(CDP_PORT, pdfUrl);
      if (pdfTarget) {
        const pdf = new CDP(pdfTarget.webSocketDebuggerUrl);
        await pdf.connect();
        await pdf.send('Runtime.enable');
        await pdf.send('Page.enable');
        await pdf.send('Page.bringToFront').catch(() => null);
        await setStoreViewport(pdf);
        let ok = null;
        for (let i = 0; i < 60 && !ok; i++) {
          await sleep(500);
          ok = await hoverWord(pdf, 'dictionary', { budgetMs: 12000 }).catch(() => null);
        }
        if (!ok) console.log('  ⚠ PDF 卡片未出现，仍截图');
        await sleep(600);
        await shoot(pdf, '2-pdf.png');
        pdf.close();
      } else {
        console.log('  ⚠ 打不开 PDF 阅读器，跳过 2-pdf.png');
      }
    } else {
      console.log('  ⚠ 未取到扩展 ID，跳过 2-pdf.png');
    }

    /* 3. 设置页 */
    if (extId) {
      const optUrl = 'chrome-extension://' + extId + '/options/options.html';
      const optTarget = await openTarget(CDP_PORT, optUrl);
      if (optTarget) {
        const opt = new CDP(optTarget.webSocketDebuggerUrl);
        await opt.connect();
        await opt.send('Page.enable');
        await opt.send('Page.bringToFront').catch(() => null);
        await setStoreViewport(opt);
        await sleep(700);
        await shoot(opt, '3-settings.png');
        opt.close();
      }
    }

    const bad = sizes.filter((s) => !s.ok);
    if (bad.length) {
      console.error('\n有 ' + bad.length + ' 张截图尺寸不符合商店要求：' + bad.map((b) => b.name).join('；'));
      process.exit(1);
    }
  } finally {
    try { child.kill(); } catch (e) { /* 忽略 */ }
    try { server.close(); } catch (e) { /* 忽略 */ }
    await sleep(500);
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) { /* 忽略 */ }
  }
}

main().catch((e) => {
  console.error('生成商店截图失败：' + (e && e.message));
  process.exit(1);
});
