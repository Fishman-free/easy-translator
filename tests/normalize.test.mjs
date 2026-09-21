/**
 * Easy Translator — 纯逻辑单元测试
 *
 * 运行：node --test tests/
 * 覆盖：英文词判定、取词边界、有道响应归一化、模型输出容错、设置归一化。
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

// 两个库文件都是「挂到 globalThis」的经典脚本，导入即完成挂载
// 注意：Windows 上动态 import 必须传 file:// URL，不能传裸盘符路径
await import(pathToFileURL(path.join(here, '..', 'lib', 'normalize.js')).href);
await import(pathToFileURL(path.join(here, '..', 'lib', 'settings-core.js')).href);

const ET = globalThis.ETNormalize;
const ES = globalThis.ETSettings;

const youdaoHello = JSON.parse(fs.readFileSync(path.join(here, 'fixtures', 'youdao-hello.json'), 'utf8'));

/* ------------------------------------------------------------------ */
/* isEnglishWord：全项目唯一的弹窗准入判定                              */
/* ------------------------------------------------------------------ */

test('isEnglishWord 接受常见英文写法', () => {
  ['hello', 'Hello', "don't", 'well-known', 'XML', 'rhythm', 'my', "it's", 'e-mail', 'up-to-date']
    .forEach((w) => assert.equal(ET.isEnglishWord(w), true, w + ' 应被接受'));
});

test('isEnglishWord 拒绝中文 / 空白 / 数字 / 乱码', () => {
  ['', '   ', 'a', '中文', '英文 text', 'hello1', '123', 'xkjhgf', 'hello.', '.hello',
   "''", '--', 'a'.repeat(46), null, undefined, 'café', '日本語']
    .forEach((w) => assert.equal(ET.isEnglishWord(w), false, JSON.stringify(w) + ' 应被拒绝'));
});

/* ------------------------------------------------------------------ */
/* extractWordAt：取词与边界                                           */
/* ------------------------------------------------------------------ */

test('extractWordAt 在字母上向外扩展成完整单词', () => {
  const text = 'Hello, world!';
  assert.equal(ET.extractWordAt(text, 1).word, 'Hello');
  assert.equal(ET.extractWordAt(text, 4).word, 'Hello');
  assert.equal(ET.extractWordAt(text, 8).word, 'world');
});

test('extractWordAt 紧邻标点归属左侧单词', () => {
  const text = 'Hello, world!';
  assert.equal(ET.extractWordAt(text, 5).word, 'Hello');   // 逗号
  assert.equal(ET.extractWordAt(text, 12).word, 'world');  // 感叹号
});

test('extractWordAt 空白处绝不取词（保证不误弹窗）', () => {
  const text = 'Hello, world!';
  assert.equal(ET.extractWordAt(text, 6).word, '');        // 词间空格
  assert.equal(ET.extractWordAt('hello   ', 5).word, '');  // 词尾空格
  assert.equal(ET.extractWordAt('中文测试', 1).word, '');
  assert.equal(ET.extractWordAt('12345', 2).word, '');
  assert.equal(ET.extractWordAt('', 0).word, '');
});

test('extractWordAt 支持撇号 / 连字符', () => {
  assert.equal(ET.extractWordAt("don't stop", 3).word, "don't");
  assert.equal(ET.extractWordAt('well-known fact', 6).word, 'well-known');
});

/* ------------------------------------------------------------------ */
/* 有道响应归一化                                                       */
/* ------------------------------------------------------------------ */

test('normalizeYoudao 解析真实响应的音标 / 词性 / 释义 / 例句', () => {
  const data = ET.normalizeYoudao(youdaoHello, 'hello');
  assert.ok(data, '应解析出结果');
  assert.equal(data.word, 'hello');
  assert.ok(data.phonetics.uk.includes('ə'), '英式音标应含 IPA 字符：' + data.phonetics.uk);
  assert.ok(data.phonetics.us.length > 0);
  assert.ok(data.poses.length >= 3, '应有多个词性条目');
  assert.equal(data.poses[0].pos, 'int.');
  assert.ok(data.poses[0].meaning.includes('你好'));
  assert.ok(data.examples.length >= 2);
  assert.ok(data.examples[0].en.includes('Hello'));
  assert.ok(data.examples[0].zh.length > 0);
  assert.equal(data.source, '有道词典');
});

test('normalizeYoudao 对空响应/无效词返回 null', () => {
  assert.equal(ET.normalizeYoudao(null, 'x'), null);
  assert.equal(ET.normalizeYoudao({ input: 'asdfghjkl' }, 'asdfghjkl'), null);
  assert.equal(ET.normalizeYoudao({ ec: { word: [] } }, 'x'), null);
});

test('splitPos 拆分词性并保留无词性的释义', () => {
  assert.deepEqual(ET.splitPos('int. 喂，你好'), { pos: 'int.', meaning: '喂，你好' });
  assert.deepEqual(ET.splitPos('n. 招呼，问候'), { pos: 'n.', meaning: '招呼，问候' });
  assert.deepEqual(ET.splitPos('打招呼'), { pos: '', meaning: '打招呼' });
});

test('humanizeMarks 把词典标记转成可读括号', () => {
  assert.equal(ET.humanizeMarks('<非正式>嘿'), '（非正式）嘿');
  assert.equal(ET.humanizeMarks('<英，旧>嗨'), '（英，旧）嗨');
});

/* ------------------------------------------------------------------ */
/* 模型输出容错                                                        */
/* ------------------------------------------------------------------ */

test('extractJson 容忍代码围栏、前后噪声与尾逗号', () => {
  assert.deepEqual(ET.extractJson('```json\n{"a":1}\n```'), { a: 1 });
  assert.deepEqual(ET.extractJson('好的：{"a":1,} 完毕'), { a: 1 });
  assert.equal(ET.extractJson('没有 JSON'), null);
  assert.equal(ET.extractJson(''), null);
});

test('extractJson 修复小模型「数组里混进键值对」的畸形 JSON', () => {
  // 这是 qwen2.5:1.5b 真实产生过的畸形输出
  const broken = '{"word":"serendipity","pos":["n.", "meaning": "偶然发现好东西的愉快"]}';
  const fixed = ET.extractJson(broken);
  assert.ok(fixed, '应能修复并解析');
  assert.equal(fixed.word, 'serendipity');
  assert.equal(fixed.pos[0].pos, 'n.');
  assert.equal(fixed.pos[0].meaning, '偶然发现好东西的愉快');
});

test('normalizeModel 解析小模型的扁平 pos 字符串', () => {
  const raw = '{"word":"example","phonetic_uk":"ɪɡˈzɑːmpl","pos":"n. 例子，实例；v. 把…作为例子",' +
    '"examples":[{"en":"This is a good example.","zh":"这是一个好例子。"}]}';
  const data = ET.normalizeModel(raw, 'example');
  assert.ok(data);
  assert.equal(data.poses.length, 2);
  assert.equal(data.poses[0].pos, 'n.');
  assert.equal(data.poses[1].pos, 'v.');
  assert.equal(data.examples[0].en, 'This is a good example.');
  assert.equal(data.examples[0].zh, '这是一个好例子。');
});

test('normalizeModel 兼容模型写错键名/照抄占位符的例句', () => {
  const raw = '{"word":"hello","pos":"int. 你好",' +
    '"examples":[{"en":"英文例句","中文翻译":"Hello, how are you?"},{"sentence":"Hi there.","translation":"你好呀。"}]}';
  const data = ET.normalizeModel(raw, 'hello');
  assert.ok(data);
  assert.equal(data.examples.length, 2);
  assert.equal(data.examples[0].en, 'Hello, how are you?', '占位符应被丢弃，真实句子当英文例句');
  assert.equal(data.examples[1].en, 'Hi there.');
  assert.equal(data.examples[1].zh, '你好呀。');
});

test('normalizeModel 兼容对象数组形态的 pos（旧格式）', () => {
  const raw = '{"word":"hello","pos":[{"pos":"int.","meaning":"喂，你好"},{"pos":"n.","meaning":"招呼"}],' +
    '"examples":[{"en":"Hello!","zh":"你好！"}]}';
  const data = ET.normalizeModel(raw, 'hello');
  assert.equal(data.poses.length, 2);
  assert.equal(data.poses[1].meaning, '招呼');
});

test('normalizeModel 解析小模型返回', () => {
  const raw = '```json\n{"word":"serendipity","phonetic_uk":"/ˌserənˈdɪpəti/",' +
    '"pos":[{"pos":"n.","meaning":"意外发现珍奇事物的运气"}],' +
    '"examples":[{"en":"A serendipity moment.","zh":"一个意外惊喜的时刻。"}]}\n```';
  const data = ET.normalizeModel(raw, 'serendipity');
  assert.ok(data);
  assert.equal(data.word, 'serendipity');
  assert.equal(data.poses.length, 1);
  assert.equal(data.examples[0].en, 'A serendipity moment.');
  assert.equal(data.source, '本地小模型');
});

test('normalizeModel 对垃圾输出返回 null', () => {
  assert.equal(ET.normalizeModel('抱歉，我不知道', 'x'), null);
  assert.equal(ET.normalizeModel('{"word":"x"}', 'x'), null);   // 无任何可用内容
});

test('pickWordFromVision 只放行合法英文单词', () => {
  assert.equal(ET.pickWordFromVision('{"word":"example"}'), 'example');
  assert.equal(ET.pickWordFromVision('```json\n{"word":"Hello!"}\n```'), 'Hello');
  assert.equal(ET.pickWordFromVision('{"word":null}'), '');
  assert.equal(ET.pickWordFromVision('{"word":"中文"}'), '');
  assert.equal(ET.pickWordFromVision('我看到了 hello'), '');
  assert.equal(ET.pickWordFromVision(''), '');
});

test('提示词包含要点与具体示例', () => {
  const msgs = ET.buildModelPrompt('test');
  assert.equal(msgs.length, 2);
  assert.ok(msgs[1].content.includes('test'));
  assert.ok(msgs[0].content.includes('JSON'));
  assert.ok(msgs[0].content.includes('"pos":"n.'), '必须给出具体示例而不是占位符模板');
  assert.ok(msgs[0].content.includes('"en":"This is a good example."'));
  assert.ok(ET.buildVisionPrompt('横向 50%、纵向 50%').includes('JSON'));
});

/* ------------------------------------------------------------------ */
/* 设置归一化                                                          */
/* ------------------------------------------------------------------ */

test('ETSettings.normalize 补全并裁剪非法值', () => {
  const s = ES.normalize({
    dwellMs: 999999,
    examplesCount: -3,
    engine: 'bogus',
    model: { baseUrl: 'http://127.0.0.1:11434/v1/', timeoutMs: 1 }
  });
  assert.equal(s.dwellMs, 15000);
  assert.equal(s.examplesCount, 0);
  assert.equal(s.engine, 'auto');
  assert.equal(s.model.baseUrl, 'http://127.0.0.1:11434/v1');
  assert.equal(s.model.timeoutMs, 2000);
  assert.equal(s.enabled, true);
});

test('modelTarget 拼出 OpenAI 兼容地址与模型名', () => {
  const s = ES.normalize({ model: { baseUrl: 'http://127.0.0.1:11434/v1', textModel: 'qwen2.5:1.5b', visionModel: 'qwen2.5vl:3b' } });
  assert.equal(ES.modelTarget(s, 'text').url, 'http://127.0.0.1:11434/v1/chat/completions');
  assert.equal(ES.modelTarget(s, 'text').model, 'qwen2.5:1.5b');
  assert.equal(ES.modelTarget(s, 'vision').model, 'qwen2.5vl:3b');
});
