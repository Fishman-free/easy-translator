/**
 * 极简 CDP 客户端与常用助手（零依赖）
 *
 * 被 tools/e2e.mjs、tools/screenshot.mjs、tools/store-screenshots.mjs 共用。
 * 只需要 Node 22+（内置 WebSocket 与 fetch）。
 */

export class CDP {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.id = 0;
    this.pending = new Map();
    this.handlers = [];
  }

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
    await this.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved', x, y, button: 'none', buttons: 0, clickCount: 0
    });
  }

  close() { try { this.ws.close(); } catch (e) { /* 忽略 */ } }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 取 CDP 的 HTTP 端点（/json/version、/json/list、/json/new…） */
export async function cdpJson(port, pathname, init) {
  const res = await fetch('http://127.0.0.1:' + port + pathname, init);
  return res.json();
}

/** 打开一个新标签页并等待它出现在目标列表里 */
export async function openTarget(port, url, timeoutMs = 12000) {
  await cdpJson(port, '/json/new?' + encodeURIComponent(url), { method: 'PUT' }).catch(() => null);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await sleep(300);
    const list = await cdpJson(port, '/json/list');
    const target = list.find((t) => t.url === url);
    if (target) return target;
  }
  return null;
}

/** 等待浏览器把调试端口开起来；child 若提前退出则立即返回失败 */
export async function waitForCdp(port, { tries = 120, gapMs = 500, child } = {}) {
  for (let i = 0; i < tries; i++) {
    await sleep(gapMs);
    if (child && child.exitCode !== null) return false;
    try {
      await cdpJson(port, '/json/version');
      return true;
    } catch (e) { /* 继续等 */ }
  }
  return false;
}
