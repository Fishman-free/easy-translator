/**
 * Easy Translator — 打包成可提交 Edge / Chrome 商店的 .zip
 *
 *   npm run build:store              # 打包 + 结构自检（含 Partner Center 要求逐条核对）
 *   npm run build:store -- --smoke   # 额外把「解压后的这份包」真机跑一遍端到端
 *
 * ZIP 读写用自建实现（tools/lib/zip.mjs），不依赖外部工具：
 *   - PowerShell 的 Compress-Archive 会把条目名写成反斜杠，商店上传会报「找不到清单文件」；
 *   - Windows 上 `tar` 可能解析到 Git 自带的 GNU tar，而 GNU tar 读不了 zip，
 *     会让「解压后冒烟」这种验证在部分环境下变成假阳性。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { writeZip, readZip } from './lib/zip.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STORE_DIR = path.join(ROOT, 'store');

// 只放扩展运行时需要的文件；开发用的 tools/tests/docs/.github/package.json 不进包
const INCLUDE = ['manifest.json', 'background.js', 'lib', 'content', 'popup', 'options', 'pdf', 'pdfjs', 'icons', 'assets'];

function collect(dir, base, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    const rel = base ? base + '/' + entry.name : entry.name;
    if (entry.isDirectory()) collect(full, rel, out);
    else if (entry.isFile()) out.push({ name: rel, data: fs.readFileSync(full) });
  }
  return out;
}

const results = [];
const add = (name, ok, detail) => {
  results.push({ name, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + (detail ? '   [' + detail + ']' : ''));
};

/* ---------------- 打包 ---------------- */

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.json'), 'utf8'));
const version = manifest.version;
fs.mkdirSync(STORE_DIR, { recursive: true });
const zipPath = path.join(STORE_DIR, `easy-translator-${version}.zip`);

const entries = [];
for (const item of INCLUDE) {
  const full = path.join(ROOT, item);
  if (!fs.existsSync(full)) {
    console.error('✖ 缺少必需路径：' + item);
    process.exit(1);
  }
  if (fs.statSync(full).isDirectory()) collect(full, item, entries);
  else entries.push({ name: item, data: fs.readFileSync(full) });
}
entries.sort((a, b) => (a.name < b.name ? -1 : 1));

fs.writeFileSync(zipPath, writeZip(entries));

console.log('打包：' + path.relative(ROOT, zipPath) + '\n');

/* ---------------- 自检 ---------------- */

// 读回磁盘上的 zip 来核对（而不是复用内存里的数组，避免"自己验证自己"）
const readBack = readZip(fs.readFileSync(zipPath));
const names = new Set(readBack.map((e) => e.name));
const manifestInZip = JSON.parse(readBack.find((e) => e.name === 'manifest.json').data.toString('utf8'));

console.log('【Partner Center 要求逐条核对】');
add('包内包含清单文件 manifest.json（且在包根目录）', names.has('manifest.json'));
add('清单含 name', typeof manifestInZip.name === 'string' && manifestInZip.name.length > 0, manifestInZip.name);
add('清单含 version', typeof manifestInZip.version === 'string' && manifestInZip.version.length > 0, 'v' + manifestInZip.version);
add('清单含 short description', typeof manifestInZip.description === 'string' && manifestInZip.description.length > 0,
  (manifestInZip.description || '').slice(0, 46) + '…（' + (manifestInZip.description || '').length + ' 字符）');
add('清单含 permissions', Array.isArray(manifestInZip.permissions),
  (manifestInZip.permissions || []).join(', '));
add('清单含 default language（default_locale 或明确的语言声明）',
  typeof manifestInZip.default_locale === 'string' || (manifestInZip.content_scripts || []).length > 0,
  manifestInZip.default_locale || '未用 _locales，界面语言内置于代码（content_scripts 已声明）');
add('图片等扩展所需文件齐全', ['icons/icon16.png', 'icons/icon128.png', 'pdfjs/build/pdf.min.mjs', 'content/card.css']
  .every((f) => names.has(f)), '图标 · pdf.js 运行时 · 卡片样式');

console.log('\n【打包结构自检】');
add('zip 可被重新读回（结构有效）', readBack.length === entries.length, readBack.length + ' 个文件 · ' +
  (fs.statSync(zipPath).size / 1024 / 1024).toFixed(2) + ' MB');
const refs = [
  manifest.background && manifest.background.service_worker,
  ...(manifest.content_scripts || []).flatMap((c) => c.js || []),
  ...(manifest.web_accessible_resources || []).flatMap((w) => w.resources || []),
  manifest.action && manifest.action.default_popup,
  manifest.options_page,
  ...Object.values(manifest.icons || {})
].filter(Boolean);
const missing = refs.filter((f) => !names.has(f));
add('manifest 引用的 ' + refs.length + ' 个文件都在包里', missing.length === 0, missing.join(', '));
const devLeak = [...names].filter((n) =>
  n.startsWith('tools/') || n.startsWith('tests/') || n.startsWith('docs/') ||
  n.startsWith('.github/') || n.startsWith('store/') || n === 'package.json' || n === 'README.md');
add('未混入开发文件（tools/tests/docs/store/.github/package.json）', devLeak.length === 0, devLeak.slice(0, 5).join(', '));
add('条目名使用正斜杠（商店上传要求）', readBack.every((e) => !e.name.includes('\\')));
add('版本号已写入包名', zipPath.includes(version), 'v' + version);

/* ---------------- 可选：真机冒烟（解压这份包并用它跑端到端） ---------------- */

if (process.argv.includes('--smoke')) {
  const extractDir = fs.mkdtempSync(path.join(os.tmpdir(), 'et-store-'));
  let extracted = 0;
  for (const e of readBack) {
    const dest = path.join(extractDir, e.name);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, e.data);
    extracted++;
  }
  // 防止「解压其实没产出任何文件」被下游静默吞掉（曾因 tar 环境差异出现过这类假阳性）
  add('解压产出文件（不是空目录）',
    extracted === readBack.length && fs.existsSync(path.join(extractDir, 'manifest.json')) &&
    fs.existsSync(path.join(extractDir, 'background.js')),
    extracted + ' 个文件');
  console.log('\n已解压到 ' + extractDir + '（自建解压，不依赖 tar），并用它跑端到端…');

  const e2e = spawnSync(process.execPath, ['tools/e2e.mjs'], {
    cwd: ROOT,
    encoding: 'utf8',
    env: Object.assign({}, process.env, { ET_EXT_DIR: extractDir }),
    timeout: 600000
  });
  const m = (e2e.stdout || '').match(/E2E 结果：(\d+)\/(\d+)/);
  add('打包产物真机端到端通过', !!m && m[1] === m[2] && e2e.status === 0, m ? m[1] + '/' + m[2] : '未取到结果');
  if (!m) console.error((e2e.stdout || '').slice(-1500) + (e2e.stderr || '').slice(-500));
  fs.rmSync(extractDir, { recursive: true, force: true });
}

console.log('\n【商店素材规格核对（官方硬性尺寸）】');
const ASSETS = [
  ['store/logo-300.png', 'Extension logo（必填·1:1，推荐 300x300）', (s) => s.width === s.height && s.width >= 128],
  ['store/tile-440x280.png', 'Small promotional tile（可选·440x280）', (s) => s.width === 440 && s.height === 280],
  ['store/tile-1400x560.png', 'Large promotional tile（可选·1400x560）', (s) => s.width === 1400 && s.height === 560],
  ['store/screenshots/1-web.png', '截图（可选·最多 6 张，1280x800 或 640x480）', (s) => s.width === 1280 && s.height === 800],
  ['store/screenshots/2-pdf.png', '截图', (s) => s.width === 1280 && s.height === 800],
  ['store/screenshots/3-settings.png', '截图', (s) => s.width === 1280 && s.height === 800]
];
for (const [rel, label, valid] of ASSETS) {
  const file = path.join(ROOT, rel);
  if (!fs.existsSync(file)) {
    add('素材 ' + rel, false, '文件缺失');
    continue;
  }
  const head = fs.readFileSync(file).subarray(0, 24);
  const size = { width: head.readUInt32BE(16), height: head.readUInt32BE(20) };
  add(size.width + 'x' + size.height + '  ' + rel, valid(size), label);
}

const failed = results.filter((r) => !r.ok);
console.log('\n' + '─'.repeat(58));
console.log('打包自检：' + (results.length - failed.length) + '/' + results.length + ' 项通过');
if (failed.length) {
  console.log('失败项：' + failed.map((f) => f.name).join('；'));
  process.exit(1);
}
console.log('\n上传这个文件：' + zipPath);
console.log('提交步骤见：store/SUBMISSION.md');
