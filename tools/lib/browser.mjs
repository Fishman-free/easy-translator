/**
 * 浏览器发现与无头启动参数（e2e / screenshot 等工具共用）
 *
 * 覆盖 Windows / macOS / Linux（GitHub Actions 的 ubuntu runner 预装 Chrome 与 Edge）。
 * 也可用环境变量显式指定：ET_BROWSER=/path/to/chrome
 */
import fs from 'node:fs';

const CANDIDATES = [
  process.env.ET_BROWSER,
  // Windows
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  // macOS
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  // Linux
  '/usr/bin/microsoft-edge',
  '/usr/bin/microsoft-edge-stable',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser'
].filter(Boolean);

/** 找到可用的 Chromium 系浏览器；找不到返回 null */
export function findBrowser() {
  return CANDIDATES.find((p) => {
    try { return fs.existsSync(p); } catch (e) { return false; }
  }) || null;
}

/**
 * 无头启动参数。
 * headless=new 从 Chrome/Edge 112 起支持加载扩展；
 * CI（root 或受限 /dev/shm 环境）额外关掉沙箱与共享内存。
 */
export function headlessFlags({ remoteDebuggingPort, extensionDir, windowSize } = {}) {
  const flags = [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-component-update',
    '--disable-background-networking'
  ];
  if (process.env.CI) {
    flags.push('--no-sandbox', '--disable-dev-shm-usage');
  }
  if (remoteDebuggingPort) flags.push('--remote-debugging-port=' + remoteDebuggingPort);
  if (extensionDir) {
    flags.push('--disable-extensions-except=' + extensionDir, '--load-extension=' + extensionDir);
  }
  if (windowSize) flags.push('--window-size=' + windowSize);
  return flags;
}
