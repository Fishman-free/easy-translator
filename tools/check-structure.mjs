/**
 * Easy Translator — 交付物结构校验
 *
 * 检查项：
 *   1. manifest.json 合法且是 MV3；
 *   2. manifest 引用的每个文件都真实存在；
 *   3. 首方 JS 全部通过语法检查（跳过第三方 pdfjs）；
 *   4. 关键资源（字典卡片样式、pdf.js 运行时、图标）体积不为 0。
 *
 * 用法： node tools/check-structure.mjs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SKIP_DIRS = new Set(['.git', 'node_modules', 'pdfjs']);
const results = [];
const add = (name, ok, detail) => {
  results.push({ name, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + (detail ? '   [' + detail + ']' : ''));
};

/* 1 & 2. manifest */
let manifest = null;
try {
  manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.json'), 'utf8'));
  add('manifest.json 可解析且为 MV3', manifest.manifest_version === 3, manifest.name);
} catch (e) {
  add('manifest.json 可解析且为 MV3', false, e.message);
}

if (manifest) {
  const refs = [
    manifest.background && manifest.background.service_worker,
    ...(manifest.content_scripts || []).flatMap((c) => c.js || []),
    ...(manifest.web_accessible_resources || []).flatMap((w) => w.resources || []),
    manifest.action && manifest.action.default_popup,
    manifest.options_page,
    ...Object.values(manifest.icons || {})
  ].filter(Boolean);
  const missing = refs.filter((f) => !fs.existsSync(path.join(ROOT, f)));
  add('manifest 引用的 ' + refs.length + ' 个文件全部存在', missing.length === 0, missing.join(', '));

  const perms = manifest.permissions || [];
  const heavy = perms.filter((p) => p === 'tabs' || p === 'history' || p === '<all_urls>');
  add('未申请会触发强警告的权限', heavy.length === 0, perms.join(', '));
}

/* 3. 首方 JS 语法 */
const walk = (dir, out = []) => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out);
    else if (/\.(js|mjs)$/.test(entry.name)) out.push(p);
  }
  return out;
};

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'et-check-'));
const jsFiles = walk(ROOT);
const bad = [];
for (const file of jsFiles) {
  const text = fs.readFileSync(file, 'utf8');
  const isEsm = /^\s*import\s/m.test(text);
  let target = file;
  if (isEsm) {
    // .js 默认按 CommonJS 解析，含 import 的文件需以 .mjs 交给 Node
    target = path.join(tmp, 'chk-' + path.basename(file, path.extname(file)) + '.mjs');
    fs.copyFileSync(file, target);
  }
  const r = spawnSync(process.execPath, ['--check', target], { encoding: 'utf8' });
  if (r.status !== 0) bad.push(path.relative(ROOT, file) + ' → ' + (r.stderr || '').split('\n')[0]);
}
add('首方 JS 语法检查（' + jsFiles.length + ' 个文件）', bad.length === 0, bad.join(' | '));
try { fs.rmSync(tmp, { recursive: true, force: true }); } catch (e) { /* 忽略 */ }

/* 4. 关键资源非空 */
const essentials = [
  'content/card.css',
  'pdf/viewer.html',
  'pdf/viewer.js',
  'pdfjs/build/pdf.min.mjs',
  'pdfjs/build/pdf.worker.min.mjs',
  'assets/vision-test.png',
  'icons/icon128.png'
];
const empty = essentials.filter((f) => {
  const p = path.join(ROOT, f);
  return !fs.existsSync(p) || fs.statSync(p).size === 0;
});
add('关键资源存在且非空（' + essentials.length + ' 项）', empty.length === 0, empty.join(', '));

const failed = results.filter((r) => !r.ok);
console.log('\n结构校验：' + (results.length - failed.length) + '/' + results.length + ' 项通过');
if (failed.length) process.exit(1);
