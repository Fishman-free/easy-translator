#!/usr/bin/env node
/**
 * tools/diagnose.mjs —— 「我的电脑跑的是最新吗 / 为什么没反应」三层判定
 *
 *   ① 仓库是否与 origin/main 一致
 *   ② 桌面伴生（鲸鱼娘卡片）是否在跑
 *   ③ Edge 里是否装了扩展且启用（悬停卡片）；若装了，加载副本与仓库代码是否逐字节一致
 *
 * 任何一层不满足，就是「没反应」的直接原因。只打印扩展相关字段，不碰其它隐私。
 * 用法：npm run diagnose
 */
import { execSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const EXT_ID = 'lnnglikclimokbdcgnpjelpigopdkjeb';           // 商店 CRX ID
const results = [];
const check = (name, ok, detail = '') => {
  results.push([name, !!ok]);
  console.log((ok ? '  ✔ ' : '  ✘ ') + name + (detail ? `   [${detail}]` : ''));
};
// Windows 上 spawnSync('git') 会 ENOENT（.exe 解析）—— 走 shell 最稳
const sh = (cmd) => execSync(cmd, { cwd: ROOT, encoding: 'utf8', timeout: 60_000 }).trim();
const md5 = (p) => createHash('md5').update(fs.readFileSync(p)).digest('hex');

console.log('Easy Translator · 环境诊断\n');

console.log('== ① 仓库 ==');
try { sh('git fetch -q origin'); } catch { /* 离线也照常比对本地 */ }
const head = sh('git rev-parse --short HEAD');
const origin = sh('git rev-parse --short origin/main');
check('仓库 HEAD == origin/main', head === origin, `${head} vs ${origin}`);

console.log('\n== ② 桌面伴生 ==');
const ps = sh('powershell -NoProfile -Command ' +
  '"Get-CimInstance Win32_Process -Filter \\"Name like \'python%\'\\" | ' +
  "Where-Object { $_.CommandLine -like '*et_desktop*' } | " +
  'Select-Object -ExpandProperty ProcessId"');
check('桌面伴生进程在跑', !!ps, `PID ${ps || '（无）'}`);

console.log('\n== ③④ Edge 里的扩展 ==');
// Edge 把扩展设置存在 **Secure Preferences**（Preferences 里常为空 —— 读错文件会误判成「没装」）
const ud = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default');
let exts = {};
for (const f of ['Secure Preferences', 'Preferences']) {
  const p = path.join(ud, f);
  if (!fs.existsSync(p)) continue;
  try {
    const s = JSON.parse(fs.readFileSync(p, 'utf8')).extensions?.settings || {};
    exts = { ...exts, ...s };
  } catch { /* 文件被占用/半写：换下一个 */ }
}
const mine = Object.entries(exts).filter(([id, m]) =>
  String(m?.manifest?.name || '').includes('Easy') || id === EXT_ID ||
  /Easy-translator/i.test(String(m?.path || '')) ||
  (m?.path && String(m.path).includes('Easy-translator')));
check('Edge 里装了 Easy Translator', mine.length > 0, `配置档共 ${Object.keys(exts).length} 个扩展`);

for (const [id, meta] of mine) {
  check('扩展处于启用状态（state=1）', meta.state === 1, `state=${meta.state}`);
  let loaded = meta.path ? path.join(meta.path, 'content', 'hover-core.js') : '';
  if (!loaded || !fs.existsSync(loaded)) {
    // 商店安装：path 为空，实际文件在 Extensions\<id>\<ver>\
    const base = path.join(os.homedir(), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data',
      'Default', 'Extensions', id);
    const vers = fs.existsSync(base) ? fs.readdirSync(base).sort() : [];
    loaded = vers.length ? path.join(base, vers.at(-1), 'content', 'hover-core.js') : '';
  }
  if (fs.existsSync(loaded)) {
    check('浏览器加载的就是仓库最新代码',
      md5(loaded) === md5(path.join(ROOT, 'content', 'hover-core.js')),
      path.basename(path.dirname(path.dirname(loaded))));
  } else {
    check('读到加载副本的 hover-core.js', false, loaded || '（无 path）');
  }
}

const failed = results.filter(([, ok]) => !ok);
console.log('-'.repeat(58));
console.log(`诊断：${results.length - failed.length}/${results.length} 项通过`);
if (failed.length) {
  console.log('未通过：' + failed.map(([n]) => n).join('；') + ' ← 这就是「没反应」的直接原因');
  process.exit(1);
}
console.log('三层齐全：代码最新、桌面在跑、扩展已装且与仓库一致 ✓');
