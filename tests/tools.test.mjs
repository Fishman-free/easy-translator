/**
 * 工具链纯逻辑测试（不启动浏览器）
 *   node --test tests/tools.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extId = await import(pathToFileURL(path.join(ROOT, 'tools', 'lib', 'ext-id.mjs')).href);

/* —— 复现 CI 上的真实失败场景 —— */

test('CI 场景：列表里混入浏览器内置扩展目标时，必须挑出我们自己的 ID', () => {
  // 这两条是 CI 失败日志里的真实情况：内置扩展目标排在前面，
  // 旧逻辑（取第一个 chrome-extension://）会返回内置扩展的 ID。
  const targets = [
    { url: 'chrome-extension://ncbjelpjchkpbikbpkcchkhkblodoama/edge_addons_page.html' },
    { url: 'chrome-extension://dkhlnmkbnjolgnhmaadfkdcbmbhblngf/background.html' },
    { url: 'http://127.0.0.1:8791/tests/manual-test.html' },
    { url: 'chrome-extension://bmoifajkkmgicblcaghffkjbakidfcom/background.js' },
    { url: 'chrome-extension://bmoifajkkmgicblcaghffkjbakidfcom/popup/popup.html' }
  ];

  const result = extId.pickOwnExtensionId(targets);
  assert.equal(result.id, 'bmoifajkkmgicblcaghffkjbakidfcom');
  assert.equal(result.foreignCount, 2, '应报告并忽略 2 个「其它扩展」（自己扩展的多个页面不算）');
  assert.equal(result.extTargetCount, 4);

  // 旧逻辑：取第一个 chrome-extension:// 目标 —— 正是导致 ERR_FILE_NOT_FOUND 的那一步
  const legacyUrl = targets.find((t) => /^chrome-extension:\/\//.test(t.url)).url;
  const legacy = /^chrome-extension:\/\/([a-p]+)\//.exec(legacyUrl)[1];
  assert.notEqual(legacy, result.id, '旧逻辑确实会取错（否则这个回归测试就没有意义）');
});

test('只有内置扩展、没有自己的 SW 目标时返回 null（交给兜底逻辑）', () => {
  const result = extId.pickOwnExtensionId([
    { url: 'chrome-extension://ncbjelpjchkpbikbpkcchkhkblodoama/page.html' }
  ]);
  assert.equal(result.id, null);
  assert.equal(result.foreignCount, 1);
});

test('空列表与缺字段不抛异常', () => {
  assert.equal(extId.pickOwnExtensionId([]).id, null);
  assert.equal(extId.pickOwnExtensionId(null).id, null);
  assert.equal(extId.pickOwnExtensionId([{}, { url: null }]).id, null);
});

test('不会把别的扩展的 background.js 误判成自己的', () => {
  // 形状相同但那是别人的 SW：URL 不以 /background.js 结尾的都不该被选中
  const result = extId.pickOwnExtensionId([
    { url: 'chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/other.js' }
  ]);
  assert.equal(result.id, null);
  assert.equal(result.foreignCount, 1);
});
