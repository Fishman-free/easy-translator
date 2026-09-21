/**
 * Easy Translator — 打包为 Edge / Chrome 商店可提交的 .zip
 *
 *   npm run build:store          # 生成 store/easy-translator-<version>.zip 并做结构自检
 *   npm run build:store -- --smoke   # 额外把「解压后的这份包」真机跑一遍端到端
 *
 * 为什么自己写 ZIP 而不是用 Compress-Archive：
 *   PowerShell 的 Compress-Archive 会把条目名写成反斜杠（dir\file.js），
 *   浏览器商店上传时会报「清单文件不存在」这类错误。这里按 ZIP 规范写正斜杠。
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STORE_DIR = path.join(ROOT, 'store');

/* ---------------- 最小 ZIP 写入器 ---------------- */

const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function dosDateTime(date) {
  const time = ((date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2)) & 0xffff;
  const day = (((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()) & 0xffff;
  return { time, day };
}

/** entries: [{ name, data }]，name 使用正斜杠 */
function makeZip(entries) {
  const chunks = [];
  const central = [];
  let offset = 0;
  const now = dosDateTime(new Date());

  for (const entry of entries) {
    const nameBuf = Buffer.from(entry.name, 'utf8');
    const raw = entry.data;
    const compressed = zlib.deflateRawSync(raw, { level: 9 });
    const useDeflate = compressed.length < raw.length;
    const payload = useDeflate ? compressed : raw;
    const method = useDeflate ? 8 : 0;
    const crc = crc32(raw);
    const flags = /^[\x20-\x7e]*$/.test(entry.name) ? 0 : 0x800;   // 非 ASCII 名称置 UTF-8 位

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);            // version needed
    local.writeUInt16LE(flags, 6);
    local.writeUInt16LE(method, 8);
    local.writeUInt16LE(now.time, 10);
    local.writeUInt16LE(now.day, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(payload.length, 18);
    local.writeUInt32LE(raw.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    local.writeUInt16LE(0, 28);            // extra length
    chunks.push(local, nameBuf, payload);

    const cen = Buffer.alloc(46);
    cen.writeUInt32LE(0x02014b50, 0);
    cen.writeUInt16LE(20, 4);              // version made by
    cen.writeUInt16LE(20, 6);              // version needed
    cen.writeUInt16LE(flags, 8);
    cen.writeUInt16LE(method, 10);
    cen.writeUInt16LE(now.time, 12);
    cen.writeUInt16LE(now.day, 14);
    cen.writeUInt32LE(crc, 16);
    cen.writeUInt32LE(payload.length, 20);
    cen.writeUInt32LE(raw.length, 24);
    cen.writeUInt16LE(nameBuf.length, 28);
    cen.writeUInt16LE(0, 30);              // extra
    cen.writeUInt16LE(0, 32);              // comment
    cen.writeUInt16LE(0, 34);              // disk
    cen.writeUInt16LE(0, 36);              // internal attrs
    cen.writeUInt32LE(0, 38);              // external attrs
    cen.writeUInt32LE(offset, 42);         // local header offset
    central.push(Buffer.concat([cen, nameBuf]));

    offset += local.length + nameBuf.length + payload.length;
  }

  const centralBuf = Buffer.concat(central);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralBuf.length, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([...chunks, centralBuf, eocd]);
}

/* ---------------- 收集要打包的文件 ---------------- */

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

/* ---------------- 主流程 ---------------- */

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.json'), 'utf8'));
const version = manifest.version;
const outDir = STORE_DIR;
fs.mkdirSync(outDir, { recursive: true });
const zipPath = path.join(outDir, `easy-translator-${version}.zip`);

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

const zip = makeZip(entries);
fs.writeFileSync(zipPath, zip);

/* ---------------- 自检 ---------------- */

const names = new Set(entries.map((e) => e.name));
const results = [];
const add = (name, ok, detail) => {
  results.push({ name, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + (detail ? '   [' + detail + ']' : ''));
};

console.log('打包：' + path.relative(ROOT, zipPath) + '\n');
add('zip 已生成', fs.existsSync(zipPath) && fs.statSync(zipPath).size > 0,
  entries.length + ' 个文件 · ' + (zip.length / 1024 / 1024).toFixed(2) + ' MB');

add('manifest.json 位于包根目录', names.has('manifest.json'));

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
  n.startsWith('.github/') || n === 'package.json' || n === 'README.md');
add('未混入开发文件（tools/tests/docs/.github/package.json）', devLeak.length === 0, devLeak.slice(0, 5).join(', '));

add('条目名使用正斜杠（商店上传要求）', entries.every((e) => !e.name.includes('\\')));
add('pdf.js 运行时完整', names.has('pdfjs/build/pdf.min.mjs') && names.has('pdfjs/build/pdf.worker.min.mjs'));
add('版本号已写入包名', zipPath.includes(version), 'v' + version);

/* ---------------- 可选：真机冒烟（加载解压后的这份包） ---------------- */

if (process.argv.includes('--smoke')) {
  const extractDir = fs.mkdtempSync(path.join(os.tmpdir(), 'et-store-'));
  console.log('\n解压到 ' + extractDir + ' 并用真机跑端到端…');
  // 不引第三方依赖：用 tar 解压（Windows 10+ 自带 bsdtar，Linux/macOS 亦有）
  const tar = spawnSync('tar', ['-xf', zipPath, '-C', extractDir], { encoding: 'utf8' });
  if (tar.status !== 0) {
    console.error('解压失败：' + (tar.stderr || ''));
    process.exit(1);
  }
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

const failed = results.filter((r) => !r.ok);
console.log('\n' + '─'.repeat(58));
console.log('打包自检：' + (results.length - failed.length) + '/' + results.length + ' 项通过');
if (failed.length) {
  console.log('失败项：' + failed.map((f) => f.name).join('；'));
  process.exit(1);
}
console.log('\n下一步：见 store/SUBMISSION.md（Partner Center 提交清单）');
