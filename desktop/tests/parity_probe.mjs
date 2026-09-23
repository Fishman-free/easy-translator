/**
 * 同构性探针：把 lib/normalize.js（浏览器扩展那份）在 Node 里跑起来，输出 JSON，
 * 供 desktop/tests/test_parity.py 与 Python 实现逐字段比对 —— 保证两边不会跑偏。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const jsPath = path.join(here, '..', '..', 'lib', 'normalize.js');
const src = fs.readFileSync(jsPath, 'utf8');
new Function('window', 'self', 'globalThis', src)(globalThis, globalThis, globalThis);
const ET = globalThis.ETNormalize;

const cases = {
  isEnglishWord: ['hello', 'serendipity', 'a', 'xzqwt', "can't--t", '中文', 'test', "don't", 'COVID', 'ab', '', 'x1y'],
  wordsIn: ['这是test词，中文hello世界', 'The quick brown fox', 'COVID-19 与 abc', 'hello, world!', '这是一段纯中文', ''],
  extractWordAt: [
    ['这是test词', 2], ['这是test词', 3], ['中文hello世界', 4], ['The quick brown fox', 5],
    ['abc 中文', 3], ['中文 abc', 1], ['...test...', 4], ['a', 0],
  ],
  splitPos: ['int. 喂，你好', 'n. 名词', 'vt. 及物动词', 'plain text without pos', '<非正式> 旧用法'],
  humanizeMarks: ['这是<英，旧>标记', 'no marks', '<a><b>'],
};

const out = {
  isEnglishWord: cases.isEnglishWord.map((s) => [s, ET.isEnglishWord(s)]),
  wordsIn: cases.wordsIn.map((t) => [t, ET.wordsIn(t)]),
  extractWordAt: cases.extractWordAt.map(([t, o]) => [t, o, ET.extractWordAt(t, o)]),
  splitPos: cases.splitPos.map((s) => [s, ET.splitPos(s)]),
  humanizeMarks: cases.humanizeMarks.map((s) => [s, ET.humanizeMarks(s)]),
  normalizeYoudao: ET.normalizeYoudao({
    ec: { word: [{ 'return-phrase': 'hello', ukphone: 'həˈləʊ', usphone: 'həˈloʊ',
      trs: [{ tr: [{ l: { i: ['int. 喂', 'n. 打招呼'] } }] }],
      wfs: [{ wf: { name: '复数', value: 'hellos' } }] }] },
    blng_sents_part: { 'sentence-pair': [
      { sentence: 'Hello there!', 'sentence-translation': '你好！' }] },
    input: 'hello',
  }, 'hello'),
  extractJson: [
    ['{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}]}', ET.extractJson('{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}]}')],
    ['```json 围栏', ET.extractJson('```json\n{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}]}\n```')],
    ['尾逗号', ET.extractJson('{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"},]}')],
    ['数组混键值对', ET.extractJson('{"word":"hi","poses":["n.","meaning":"嗨"]}')],
    ['漏右括号（应 null）', ET.extractJson('{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}')],
    ['无 JSON（应 null）', ET.extractJson('这里没有 JSON，只有说明文字')],
  ],
  normalizeModel: [
    ET.normalizeModel('```json\n{"word":"hi","uk":"/haɪ/","poses":[{"pos":"int.","meaning":"嗨"}],'
      + '"examples":[{"en":"Hi there.","zh":"嗨。"}]}\n```', 'hi'),
    ET.normalizeModel('{"word":"x"}', 'x'),
    ET.normalizeModel('nonsense', 'x'),
  ],
};

console.log(JSON.stringify(out, null, 0));
