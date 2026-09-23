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
import { pickOwnExtensionId } from './lib/ext-id.mjs';
import {
  CDP, sleep, waitForCdp,
  cdpJson as cdpJsonShared,
  openTarget as openCdpTarget
} from './lib/cdp.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// 被测扩展的来源目录：默认仓库根目录；打包验证时用 ET_EXT_DIR 指向「解压后的商店包」
const EXT_SOURCE = process.env.ET_EXT_DIR ? path.resolve(process.env.ET_EXT_DIR) : ROOT;
const CDP_PORT = 9333;
const HTTP_PORT = 8791;
const ECHO_PORT = 8792;
const DWELL_WAIT_MS = 8500;   // 触发时长(5s) + 查询与渲染余量

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + (detail ? '   [' + detail + ']' : ''));
}

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

/**
 * 回显 Origin 的旁路服务（跑在**另一个端口**上）。
 * 用途：网页从 8791 跨源请求 8792 时，浏览器必然带上 Origin 头；
 * 用它回归验证「DNR 只剥离本扩展的 Origin，没有误伤网页自身的请求」。
 * （同源请求不带 Origin，所以这个端点不能和测试页同端口。）
 */
function startOriginEchoServer() {
  const server = http.createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
    res.end(JSON.stringify({ origin: req.headers.origin || null, ua: (req.headers['user-agent'] || '').slice(0, 40) }));
  });
  return new Promise((resolve) => server.listen(ECHO_PORT, '127.0.0.1', () => resolve(server)));
}

/**
 * 生成一份「已授权」的扩展副本：
 * 把 <all_urls> 从可选权限提升为已授予权限，模拟用户点过弹窗里「授权」之后的状态。
 * 只改测试副本的 manifest，不动仓库里的正式清单。
 */
function prepareExtensionCopy() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'et-ext-'));
  const items = ['manifest.json', 'background.js', 'lib', 'content', 'popup', 'options', 'pdf', 'pdfjs', 'icons', 'assets'];
  for (const item of items) {
    const src = path.join(EXT_SOURCE, item);
    if (fs.existsSync(src)) fs.cpSync(src, path.join(dir, item), { recursive: true });
  }
  const manifestPath = path.join(dir, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  manifest.host_permissions = (manifest.host_permissions || []).concat(['<all_urls>']);
  delete manifest.optional_host_permissions;
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  return dir;
}

/* ---------------- 极简 CDP 客户端 ---------------- */

// CDP 客户端与常用助手来自共享模块（tools/lib/cdp.mjs），这里只绑定本文件使用的端口
const cdpJson = (pathname, init) => cdpJsonShared(CDP_PORT, pathname, init);

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
  console.log('扩展目录：' + EXT_SOURCE + (EXT_SOURCE === ROOT ? '' : '（ET_EXT_DIR 指定：商店打包产物）') + '\n');

  const server = await startServer();
  const echoServer = await startOriginEchoServer();
  const extDir = prepareExtensionCopy();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'et-e2e-'));
  const pageUrl = 'http://127.0.0.1:' + HTTP_PORT + '/tests/manual-test.html';

  const child = spawn(browser, headlessFlags({
    remoteDebuggingPort: CDP_PORT,
    extensionDir: extDir
  }).concat(['about:blank']), { stdio: ['ignore', 'pipe', 'pipe'] });

  // 收集浏览器输出：启动失败时这是唯一的诊断线索（headless 下没人看得到窗口）
  const browserLog = [];
  const collect = (buf) => {
    String(buf).split('\n').forEach((line) => {
      const t = line.trim();
      if (t) browserLog.push(t);
    });
    while (browserLog.length > 40) browserLog.shift();
  };
  if (child.stdout) child.stdout.on('data', collect);
  if (child.stderr) child.stderr.on('data', collect);

  const cleanup = () => {
    try { child.kill(); } catch (e) { /* 忽略 */ }
    try { server.close(); } catch (e) { /* 忽略 */ }
    try { echoServer.close(); } catch (e) { /* 忽略 */ }
    try { fs.rmSync(extDir, { recursive: true, force: true }); } catch (e) { /* 忽略 */ }
  };

  try {
    // 等待 CDP 就绪（CI 冷启动可能较慢；进程提前退出则立刻报错并打印浏览器输出）
    const ready = await waitForCdp(CDP_PORT, { child });
    if (!ready) {
      console.error('浏览器未能启动（exitCode=' + child.exitCode + '）。浏览器输出：');
      console.error(browserLog.slice(-15).join('\n') || '(无输出)');
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

    /** 指定容器内某个英文单词的中心点（用于中英混排 / 小字号 / 不可选中文本的灵敏度用例）
     *  先把容器滚入视口中央再取坐标——否则目标在首屏之外时，坐标会落到视口外（悬停必然打偏）。 */
    const centerOfWordIn = async (selector, word) => {
      await page.evaluate(`(() => {
        const host = document.querySelector(${JSON.stringify(selector)});
        if (host) host.scrollIntoView({ block: 'center', behavior: 'instant' });
      })()`);
      await sleep(600);   // 等滚动落定：滚动会收起卡片，且坐标要以新位置为准
      return page.evaluate(`(() => {
        const host = document.querySelector(${JSON.stringify(selector)});
        if (!host) return null;
        const w = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
        while (w.nextNode()) {
          const node = w.currentNode;
          const t = node.textContent || '';
          const i = t.toLowerCase().indexOf(${JSON.stringify(word.toLowerCase())});
          if (i === -1) continue;
          const range = document.createRange();
          range.setStart(node, i);
          range.setEnd(node, i + ${word.length});
          const box = Array.from(range.getClientRects()).filter((x) => x.width > 1)[0];
          if (!box) continue;
          return {
            x: Math.round(box.left + box.width / 2),
            y: Math.round(box.top + box.height / 2),
            // 贴缝点：词右边缘外 2px（真人手势很难正好压在词心，实测这里最容易「取到旁边的词」或「不弹窗」）
            gapX: Math.round(box.right + 2),
            inViewport: box.top >= 0 && box.bottom <= innerHeight && box.left >= 0 && box.right <= innerWidth,
            fontPx: Math.round(box.height)
          };
        }
        return null;
      })()`);
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

    /* —— 场景 3a：卡片出现后光标继续漂移，卡片必须还在 —— */
    // 真实鼠标永远不会完全静止（手抖 / 高轮询率鼠标）。曾在真实使用中出现：
    // 卡片被视口顶到光标下方 → 鼠标蹭进卡片再出来 → 收起后因为「目标词没变」不再重排，
    // 表现为「卡片消失且再也不回来」。这里用抖动序列把这一类钉住。
    for (let i = 0; i < 30; i++) {
      await page.mouseMove(enPt.x + ((i % 3) - 1), enPt.y + (((i / 3) | 0) % 3) - 1);
      await sleep(80);
    }
    st = await cardState();
    check('光标小幅漂移后卡片仍在（真实鼠标手抖）', st.exists && st.state === 'result', JSON.stringify(st));

    // 死锁路径：卡片的收起来源很多（窗口失焦、文档级 mouseleave、滚动…），
    // 这些收起不会改变 current（仍指向同一个词）。修复前同一目标直接 return，
    // 于是「卡片收起后，光标还停在词上也永远不会再出现」。这里用「窗口失焦」这条
    // 确定性路径把该状态钉住。
    await page.evaluate("window.dispatchEvent(new Event('blur'))");
    await sleep(1500);                                // 越过 900ms 收起宽限
    const afterBlur = await cardState();
    check('失焦后卡片收起（预期行为）', !afterBlur.exists || afterBlur.state !== 'result', JSON.stringify(afterBlur));

    let recovered = null;
    for (let i = 0; i < 30 && !recovered; i++) {      // 像真实鼠标一样持续微动，等待重新计时
      await page.mouseMove(enPt.x + ((i % 3) - 1), enPt.y + (((i / 3) | 0) % 3) - 1);
      await sleep(400);
      const s = await cardState();
      if (s.exists && s.state === 'result' && String(s.word).toLowerCase() === 'serendipity') recovered = s;
    }
    check('同词上卡片被收起后能自行恢复（不再卡死）', !!recovered,
      JSON.stringify(recovered || afterBlur));

    /* —— 场景 3c：取词灵敏度（中英混排 / 极小字号 / user-select:none）—— */
    // 用户实测反馈的三类「鼠标在词上却取不到词」。这里逐个钉住，
    // 兜底路径（多点探测 + 矩形就近）失效时应当立刻变红。
    const sensitivity = [
      ['#mixed', '中英混排无分隔符（紧贴中文）'],
      ['#tiny', '极小字号（9px）'],
      ['#noselect', 'user-select:none 文本']
    ];
    for (const [sel, label] of sensitivity) {
      const pt = await centerOfWordIn(sel, 'serendipity');
      if (!pt) { check('灵敏度：' + label, false, '测试页缺少 ' + sel); continue; }
      if (!pt.inViewport) { check('灵敏度：' + label, false, '滚入视口后坐标仍越界：' + JSON.stringify(pt)); continue; }

      for (const [where, x] of [['词心', pt.x], ['贴缝（右边缘外 2px）', pt.gapX]]) {
        await page.mouseMove(Math.max(4, pt.x - 80), pt.y);
        await sleep(250);
        await page.mouseMove(x, pt.y);
        await sleep(DWELL_WAIT_MS + 2500);
        st = await cardState();
        check('灵敏度：' + label + ' @ ' + where + ' → 取到正确词',
          st.exists && st.state === 'result' && String(st.word).toLowerCase() === 'serendipity',
          JSON.stringify(st) + ' 命中点=' + x + ',' + pt.y + ' 词高=' + pt.fontPx + 'px');
        await page.mouseMove(4, 4);
        await sleep(400);
      }
    }

    /* —— 场景 3e：可编辑区与表单控件（鼠标是「工」字形光标时也必须能查词）—— */
    // 用户实测：ChatGPT 的消息框是 contentEditable，鼠标一进输入区（工字形光标）就查不到词 ——
    // 根因是旧版把「可编辑区」整块跳过；而 textarea/input 的 value 根本不是 DOM 文本节点。
    // 这里把三类输入区都钉住：任何光标状态、任何文本，查词都必须有效。
    const ptCE = await centerOfWordIn('#composer', 'serendipity');
    if (!ptCE) {
      check('可编辑区 contentEditable', false, '测试页缺少 #composer');
    } else {
      await page.mouseMove(Math.max(4, ptCE.x - 80), ptCE.y);
      await sleep(250);
      await page.mouseMove(ptCE.x, ptCE.y);
      await sleep(DWELL_WAIT_MS + 2500);
      st = await cardState();
      check('可编辑区 contentEditable（ChatGPT 消息框同类）→ 取到正确词',
        st.exists && st.state === 'result' && String(st.word).toLowerCase() === 'serendipity', JSON.stringify(st));
      await page.mouseMove(4, 4);
      await sleep(400);
    }

    // 每条用例各自把目标滚入视口、当场读矩形 —— 一次性读多个元素会被最后一次滚动作废
    const ctrlCases = [
      ['msgbox', 30, 0.25, 'textarea 上半行（第 1 行）', 'curiosity'],
      ['msgbox', 30, 0.75, 'textarea 下半行（第 2 行）', 'serendipity'],
      ['findbox', 30, 0.5, 'input（value 里的词）', 'serendipity']
    ];
    for (const [id, dx, fy, label, want] of ctrlCases) {
      const box = await page.evaluate(`(() => {
        const el = document.getElementById(${JSON.stringify(id)});
        if (!el) return null;
        el.scrollIntoView({ block: 'center', behavior: 'instant' });
        const r = el.getBoundingClientRect();
        return { left: r.left, top: r.top, w: r.width, h: r.height };
      })()`);
      if (!box) { check('表单控件：' + label, false, '测试页缺少 #' + id); continue; }
      const cx = Math.round(box.left + dx), cy = Math.round(box.top + box.h * fy);
      await page.mouseMove(Math.max(4, cx - 80), cy);
      await sleep(250);
      await page.mouseMove(cx, cy);
      await sleep(DWELL_WAIT_MS + 2500);
      st = await cardState();
      check('表单控件：' + label + ' → 取到正确词',
        st.exists && st.state === 'result' && String(st.word).toLowerCase() === want,
        JSON.stringify(st) + ' 命中点=' + cx + ',' + cy
          + ' 取词路径=' + await page.evaluate(`document.documentElement.getAttribute('data-et-trace')`));
      await page.mouseMove(4, 4);
      await sleep(400);
    }

    /* —— 场景 3f：滚动中的输入框 & 自动换行长句（消息框打长文的真实形态）—— */
    // 滚动后同一片区域必须取到「新露出那一行」的词：镜像层若拿旧矩形/旧下标就会取错行。
    const readBox = (id) => page.evaluate(`(() => {
      const el = document.getElementById(${JSON.stringify(id)});
      if (!el) return null;
      el.scrollIntoView({ block: 'center', behavior: 'instant' });
      const r = el.getBoundingClientRect();
      return { left: r.left, top: r.top, w: r.width, h: r.height };
    })()`);
    const hoverWord = async (x, y, wantSet, label) => {
      await page.mouseMove(Math.max(4, x - 80), y);
      await sleep(220);
      await page.mouseMove(x, y);
      await sleep(DWELL_WAIT_MS + 2500);
      st = await cardState();
      const word = String(st.word || '').toLowerCase();
      check(label, st.exists && st.state === 'result' && wantSet.includes(word),
        JSON.stringify(st) + ' 命中点=' + x + ',' + y
          + ' 取词路径=' + await page.evaluate(`document.documentElement.getAttribute('data-et-trace')`));
      await page.mouseMove(4, 4);
      await sleep(500);
    };

    const sb = await readBox('scrollbox');
    if (!sb) {
      check('滚动输入框', false, '测试页缺少 #scrollbox');
    } else {
      const sx = Math.round(sb.left + 30);
      await hoverWord(sx, Math.round(sb.top + sb.h * 0.2), ['alpha'], '滚动输入框：未滚动时上部取到第 1 行的词');
      await page.evaluate(`(() => { const el = document.getElementById('scrollbox'); el.scrollTop = el.scrollHeight; })()`);
      await sleep(350);
      await hoverWord(sx, Math.round(sb.top + sb.h * 0.5), ['foxtrot', 'golf', 'hotel'],
        '滚动输入框：滚动到底后取到末几行的词（不是旧矩形里的 alpha）');
    }

    const wb = await readBox('wrapbox');
    if (!wb) {
      check('换行长句', false, '测试页缺少 #wrapbox');
    } else {
      const wx = Math.round(wb.left + 15);
      await hoverWord(wx, Math.round(wb.top + 6), ['curiosity'], '换行长句：上缘取到首词');
      st = null;
      await hoverWord(wx, Math.round(wb.top + wb.h - 5),
        ['the', 'good', 'always', 'returns', 'serendipity', 'a', 'and', 'dictionary', 'patient', 'mind', 'rewards'],
        '换行长句：下缘取到值里的词（且不是首词 —— 纵向按视觉行映射）');
    }

    /* —— 场景 3d：DNR 作用域回归（网页自身的跨源请求不应被剥离 Origin）—— */
    const echo = await page.evaluate(
      `fetch('http://127.0.0.1:${ECHO_PORT}/__echo-origin').then(r => r.json()).catch(e => ({ error: String(e) }))`
    );
    check('网页跨源请求仍带 Origin（DNR 未误伤网页）',
      !!echo && echo.origin === 'http://127.0.0.1:' + HTTP_PORT, JSON.stringify(echo));

    /* —— 扩展 ID：只能认「我们自己的」service worker 目标 —— */
    // 陷阱：/json/list 里还有浏览器内置扩展的目标，取第一个 chrome-extension:// 会抓错 ID，
    // 于是 chrome-extension://<错的ID>/... 全部 ERR_FILE_NOT_FOUND（曾在 CI 上间歇性发生）。
    // 自己的 SW 注册的是 background.js，URL 以 /background.js 结尾；SW 懒启动，故带重试。
    let extId = null;
    let foreign = 0;
    for (let i = 0; i < 30 && !extId; i++) {
      const picked = pickOwnExtensionId(await cdpJson('/json/list'));
      extId = picked.id;
      foreign = Math.max(foreign, picked.foreignCount);
      if (!extId) await sleep(500);
    }
    if (!extId) extId = unpackedId(extDir);   // 兜底：按「实际加载的那个目录」推导
    check('解出扩展 ID', !!extId, extId + (foreign ? '｜同时忽略 ' + foreign + ' 个其它扩展目标' : ''));

    const openTarget = (url) => openCdpTarget(CDP_PORT, url);

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
      // 必须确认这是「真正的扩展页面」：加载失败时浏览器会渲染错误页，
      // 它同样有 body、同样没有 JS 异常——只看这两项会假通过（踩过）
      const isExtPage = await c
        .evaluate("typeof chrome !== 'undefined' && !!chrome.runtime && !!chrome.runtime.id && location.protocol === 'chrome-extension:'")
        .catch(() => false);
      check(pageName + ' 正常渲染且无 JS 异常', hasBody && isExtPage && errs.length === 0,
        (title ? '标题=' + title + ' ' : '') + (isExtPage ? '' : '不是有效的扩展页面 ') + (errs.slice(0, 1).join(' ') || ''));
      if (pageName.indexOf('options') !== -1) globalThis.__optionsWs = target.webSocketDebuggerUrl;
      c.close();
    }

    /* —— 场景 5：内置 PDF 阅读器里悬停取词 —— */
    const pdfPageUrl = 'chrome-extension://' + extId + '/pdf/viewer.html?file=' +
      encodeURIComponent('http://127.0.0.1:' + HTTP_PORT + '/tests/fixtures/sample.pdf');
    const pdfTarget = await openTarget(pdfPageUrl);
    const pdfIsExtPage = pdfTarget
      ? await (async () => {
          const probe = new CDP(pdfTarget.webSocketDebuggerUrl);
          await probe.connect();
          const ok = await probe
            .evaluate("location.protocol === 'chrome-extension:' && !!document.querySelector('#pages')")
            .catch(() => false);
          probe.close();
          return ok;
        })()
      : false;
    check('内置 PDF 阅读器页面已打开', !!pdfTarget && pdfIsExtPage,
      pdfTarget ? (pdfIsExtPage ? '' : '打开的是错误页（扩展 ID 可能不对）') : '未找到标签页');
    if (pdfTarget) {
      const pdf = new CDP(pdfTarget.webSocketDebuggerUrl);
      await pdf.connect();
      await pdf.send('Runtime.enable');
      let pt = null;
      let lastErr = null;
      // 窗口给到 45s：CI runner 负载高时 pdf.js 渲染明显变慢（曾在 30s 窗口边界偶发失败）
      for (let i = 0; i < 90 && !pt; i++) {
        await sleep(500);
        pt = await pdf.evaluate(findWordJs('quick')).catch((e) => { lastErr = e && e.message; return null; });
      }
      // 失败时给出诊断，而不是只说「未找到」
      const pdfDiag = pt ? null : await pdf.evaluate(`(() => ({
        spans: document.querySelectorAll('.textLayer span').length,
        canvases: document.querySelectorAll('canvas').length,
        text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 80),
        err: window.__pdfError || null
      }))()`).catch((e) => '诊断也失败：' + (e && e.message));
      check('PDF 文本层渲染出可悬停文本', !!pt,
        pt ? 'x=' + pt.x + ', y=' + pt.y
           : '未找到 quick｜' + JSON.stringify(pdfDiag) + (lastErr ? '｜最后错误：' + lastErr : ''));
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
      //     规则由 background service worker 启动时写入；SW 是懒启动的，所以这里给一个重试窗口
      let rules = null;
      let rulesErr = null;
      for (let i = 0; i < 20; i++) {
        rules = await opts.evaluate(
          'chrome.declarativeNetRequest.getDynamicRules().then(r => r.map(x => ({ id: x.id, headers: (x.action.requestHeaders || []).map(h => h.header) })))'
        ).catch((e) => { rulesErr = e && e.message; return null; });
        if (Array.isArray(rules) && rules.length >= 2) break;
        await sleep(700);
      }
      check('已注册「剥离 Origin」的 DNR 规则', Array.isArray(rules) && rules.length >= 2,
        JSON.stringify(rules) + (rulesErr ? '｜错误：' + rulesErr : ''));

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

      // 6c. 图片取词：需要视觉模型（扩展副本已预授权「所有网站」）
      const tags = await fetch('http://127.0.0.1:11434/api/tags').then((r) => r.json()).catch(() => null);
      const hasVision = !!tags && (tags.models || []).some((m) => String(m.name || '').startsWith('qwen2.5vl'));
      if (!hasVision) {
        console.log('  ⚠ 跳过图片取词测试：本机没有视觉模型（ollama pull qwen2.5vl:3b）');
      } else {
        // 图片取词靠 captureVisibleTab（截当前激活标签页），
        // 前面的 PDF 场景把激活标签切走了，这里必须先切回测试页
        await page.send('Page.bringToFront').catch(() => null);
        await sleep(600);

        const pointOf = async (id) => page.evaluate(`(() => {
          const el = document.getElementById(${JSON.stringify(id)});
          if (!el) return null;
          el.scrollIntoView({ block: 'center' });
          const r = el.getBoundingClientRect();
          return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
        })()`);

        const waitForCard = async (wantResult, budgetMs) => {
          const deadline = Date.now() + budgetMs;
          let last = null;
          while (Date.now() < deadline) {
            await sleep(1000);
            last = await page.evaluate(CARD_STATE_JS).catch(() => null);
            if (wantResult && last && last.state === 'result') return last;
            if (!wantResult && last && last.state === 'result') return last;   // 不该出现却出现了，立即返回
          }
          return wantResult ? null : last;
        };

        // 正样本先跑：把视觉模型加载进内存，负样本才有意义（否则冷启动会被误判为"没弹窗"）
        // —— 图片中的 Hello → 应识别并查词
        const enPt = await pointOf('img-en');
        if (enPt) {
          await sleep(500);
          await page.mouseMove(enPt.x, enPt.y);
          const posState = await waitForCard(true, 60000);
          check('图片中的英文可识别并查词', !!posState && /hello/i.test(String(posState.word)), JSON.stringify(posState));
        } else {
          check('图片中的英文可识别并查词', false, '找不到 #img-en');
        }

        // —— 只有中文的图片 → 不应弹窗
        const cnPt = await pointOf('img-cn');
        if (cnPt) {
          await sleep(500);
          await page.mouseMove(cnPt.x, cnPt.y);
          const negState = await waitForCard(false, 22000);
          check('图片中没有英文时不弹窗', !negState || negState.state !== 'result', JSON.stringify(negState));
        } else {
          check('图片中没有英文时不弹窗', false, '找不到 #img-cn');
        }
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
