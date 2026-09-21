/**
 * Easy Translator — 本地总验证入口
 *
 *   npm run verify:all
 *
 * 与 CI 的区别：
 *   CI 跑的是 `npm run verify`（结构 + 单测 + 端到端），结果对任何 clone 都成立；
 *   本脚本额外做「本机 / 仓库状态」层面的对账，适合在提交前后本地执行：
 *     ① 结构校验      —— tools/check-structure.mjs
 *     ② 单元测试      —— node --test tests/normalize.test.mjs
 *     ③ 端到端（真机）—— tools/e2e.mjs（本机有 Ollama/视觉模型时含图片取词，缺失则跳过）
 *     ④ 仓库状态      —— 工作区是否干净、HEAD 是否等于 origin/main
 *     ⑤ 远端 CI       —— 该提交在 GitHub Actions 上的 verify 结论（gh 不可用时跳过）
 *
 * 可选参数：
 *   --no-e2e   跳过端到端（快速自查，几秒钟）
 *   --no-ci    跳过远端 CI 查询（离线或未登录 gh 时）
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const skipE2e = argv.includes('--no-e2e');
const skipCi = argv.includes('--no-ci');

const results = [];
const add = (name, ok, detail) => {
  results.push({ name, ok });
  console.log((ok ? '  ✔ ' : '  ✖ ') + name + (detail ? '   [' + detail + ']' : ''));
};
const sh = (cmd, args, opts = {}) =>
  spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8', timeout: 600000, ...opts });

console.log('Easy Translator · 本地总验证\n');

/* ① 结构 */
console.log('① 结构校验');
const check = sh(process.execPath, ['tools/check-structure.mjs']);
add('结构校验', check.status === 0,
  ((check.stdout || '').match(/结构校验：(\d+\/\d+)/) || [])[1] || '见 tools/check-structure.mjs 输出');

/* ② 单元测试 */
console.log('\n② 单元测试');
const unit = sh(process.execPath, ['--test', 'tests/normalize.test.mjs', 'tests/tools.test.mjs']);
const unitOut = (unit.stdout || '') + (unit.stderr || '');
// Node 的 test runner 随环境换 reporter：管道下是「ℹ pass 25」，CI 日志里是「# pass 25」
const pass = Number((unitOut.match(/[#ℹ]\s*pass\s+(\d+)/) || [])[1]);
const fail = Number((unitOut.match(/[#ℹ]\s*fail\s+(\d+)/) || [])[1]);
add('单元测试', unit.status === 0 && fail === 0 && pass > 0, pass + ' 通过 / ' + fail + ' 失败');

/* ③ 端到端 */
console.log('\n③ 端到端（headless 浏览器 + CDP 真实鼠标事件）');
if (skipE2e) {
  console.log('  ⚠ 已按参数跳过（--no-e2e）');
} else {
  const e2e = sh(process.execPath, ['tools/e2e.mjs']);
  const m = e2e.stdout.match(/E2E 结果：(\d+)\/(\d+)/);
  const skipped = [...e2e.stdout.matchAll(/⚠ 跳过(.+)/g)].map((x) => x[1].trim());
  add('端到端', !!m && m[1] === m[2] && e2e.status === 0,
    (m ? m[1] + '/' + m[2] : '未取到结果') + (skipped.length ? '（跳过：' + skipped.join('；') + '）' : ''));
}

/* ④ 仓库状态 */
console.log('\n④ 仓库状态');
const dirty = sh('git', ['status', '--porcelain']).stdout.trim();
add('工作区无未提交改动', dirty === '', dirty.split('\n').slice(0, 3).join(' | '));

const head = sh('git', ['rev-parse', 'HEAD']).stdout.trim();
const origin = sh('git', ['rev-parse', 'origin/main']).stdout.trim();
add('本地 HEAD == origin/main', head === origin && head.length === 40,
  head.slice(0, 7) + (head === origin ? '（一致）' : ' vs ' + origin.slice(0, 7)));

/* ⑤ 远端 CI */
console.log('\n⑤ 远端 CI');
if (skipCi) {
  console.log('  ⚠ 已按参数跳过（--no-ci）');
} else {
  let done = false;
  try {
    const runs = JSON.parse(sh('gh', ['run', 'list', '--limit', '10', '--json', 'headSha,conclusion,name']).stdout);
    const mine = runs.filter((r) => r.headSha === head && r.name === 'verify');
    if (mine.length) {
      done = mine.every((r) => r.conclusion === 'success');
      add('该提交的 Actions verify 为 success', done, mine.map((r) => r.conclusion).join(','));
    } else {
      console.log('  ⚠ 该提交尚无 verify 运行（可能还没推送或还在队列中）');
    }
  } catch (e) {
    console.log('  ⚠ 无法查询远端 CI（gh 未安装/未登录）');
  }
}

const failed = results.filter((r) => !r.ok);
console.log('\n' + '─'.repeat(58));
console.log('总验证：' + (results.length - failed.length) + '/' + results.length + ' 项通过'
  + (results.length < 5 ? '（有跳过的检查）' : ''));
if (failed.length) {
  console.log('失败项：' + failed.map((f) => f.name).join('；'));
  process.exit(1);
}
