/**
 * Easy Translator — 标准化 + 取词判定（零依赖纯函数，可被 Node 单测直接加载）
 *
 * 职责：
 *  1. 把「有道 jsonapi」与「小模型自由文本」两种来源归一成卡片渲染结构；
 *  2. 提供全项目唯一的「这是不是一个可查的英文单词」判定（isEnglishWord）；
 *  3. 提供从文本节点 + 偏移量提取单词的通用逻辑（extractWordAt）。
 */
(function (root) {
  'use strict';

  var YOUDAO_HOME = 'https://dict.youdao.com/result?word=%s&lang=en';
  var WORD_CHAR = /[A-Za-z''\-]/;
  var CJK = /[\u2e80-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]/;

  function safeStr(v) {
    return typeof v === 'string' ? v : '';
  }

  /**
   * 全项目统一的「可查英文单词」判定。
   * 网页文本、PDF 文本层、视觉模型返回值全部走这一关：
   * 不满足则一律不弹窗（中文、数字、标点、空白、乱码、URL 片段都会被拒）。
   */
  function isEnglishWord(s) {
    if (!s || typeof s !== 'string') return false;
    var w = s.trim();
    if (!w) return false;
    if (w.length < 2 || w.length > 45) return false;
    if (CJK.test(w)) return false;
    if (!/^[A-Za-z][A-Za-z''\-]*[A-Za-z]$/.test(w)) return false;
    if (/[''\-]{2,}/.test(w)) return false;              // 连续撇号/连字符视为噪声
    if (w.length >= 5 && !/[aeiouAEIOUyY]/.test(w)) return false; // 长且无元音 → OCR 噪声
    return true;
  }

  /**
   * 从一段文本 + 字符偏移处向外扩展出一个英文单词。
   *
   * 取向策略（对齐「空白/非英文一律不弹窗」的产品要求）：
   *   · 光标在字母上        → 从该字母向两侧扩展；
   *   · 光标在空白/行尾     → 不取词（词与词之间的缝隙不触发）；
   *   · 光标在标点上但紧贴单词（如 "Hello," 的逗号）→ 归属左侧单词。
   */
  function extractWordAt(text, offset) {
    var empty = { word: '', start: -1, end: -1 };
    if (!text || typeof text !== 'string') return empty;
    var n = Math.max(0, Math.min(typeof offset === 'number' ? offset : 0, text.length));
    var at = text[n];
    var before = n > 0 ? text[n - 1] : '';

    var i;
    if (WORD_CHAR.test(at || '')) {
      i = n;
    } else if (at === undefined || at === '' || /\s/.test(at)) {
      return empty;
    } else if (WORD_CHAR.test(before || '')) {
      i = n - 1;
    } else {
      return empty;
    }

    var start = i;
    var end = i + 1;
    while (start > 0 && WORD_CHAR.test(text[start - 1])) start--;
    while (end < text.length && WORD_CHAR.test(text[end])) end++;

    var raw = text.slice(start, end);
    var word = raw.replace(/^[^A-Za-z]+/, '').replace(/[^A-Za-z]+$/, '').replace(/['']/g, "'");
    if (!isEnglishWord(word)) return empty;
    return { word: word, start: start, end: end };
  }

  /**
   * 枚举一段文本里所有「可查的英文单词」及其字符区间（同样过 isEnglishWord 闸门）。
   * 用途：浏览器 caret 落点解析失败时（中英混排、极小字号、user-select:none 文本），
   * 按矩形就近匹配单词——这条兜底路径需要先知道文本里都有哪些候选词。
   */
  function wordsIn(text) {
    var out = [];
    if (!text || typeof text !== 'string') return out;
    var re = /[A-Za-z][A-Za-z''\-]*[A-Za-z]/g;
    var m;
    while ((m = re.exec(text)) !== null) {
      var w = m[0].replace(/['']/g, "'");
      if (isEnglishWord(w)) out.push({ word: w, start: m.index, end: m.index + m[0].length });
      re.lastIndex = m.index + m[0].length;   // 从本轮结尾继续，避免重叠误配
    }
    return out;
  }

  /** `return-phrase` 可能是字符串，也可能是 {l:{i:"..."}} 结构 */
  function phraseOf(v) {
    if (!v) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'object') {
      var i = v.l && v.l.i;
      if (typeof i === 'string') return i;
      if (Array.isArray(i) && typeof i[0] === 'string') return i[0];
    }
    return '';
  }

  /** 把 `<非正式>`、`<英，旧>` 这类词典标记换成可读的括号 */
  function humanizeMarks(text) {
    return safeStr(text).replace(/<([^<>]{1,12})>/g, '（$1）');
  }

  /**
   * 把一行释义拆成「词性 + 释义」，如 "int. 喂，你好（用于问候…）" →
   * { pos: "int.", meaning: "喂，你好（用于问候…）" }
   */
  function splitPos(line) {
    var text = humanizeMarks(line).trim();
    var m = text.match(/^((?:[a-z]{1,6}\.\s*){1,3})\s*(.+)$/i);
    if (m && m[2] && /[a-z]/.test(m[1])) {
      return { pos: m[1].trim().replace(/\s+/g, ' '), meaning: m[2].trim() };
    }
    return { pos: '', meaning: text };
  }

  /** 有道 jsonapi 响应 → 统一结构；无有效内容返回 null */
  function normalizeYoudao(raw, fallbackWord) {
    if (!raw || typeof raw !== 'object') return null;

    var ecWord = (raw.ec && raw.ec.word && raw.ec.word[0]) || null;
    var simpleWord = (raw.simple && raw.simple.word && raw.simple.word[0]) || null;

    var word = phraseOf(ecWord && ecWord['return-phrase']) ||
      phraseOf(simpleWord && simpleWord['return-phrase']) ||
      safeStr(raw.input) || fallbackWord || '';

    var out = {
      word: word,
      phonetics: {
        uk: safeStr(ecWord && ecWord.ukphone) || safeStr(simpleWord && simpleWord.ukphone),
        us: safeStr(ecWord && ecWord.usphone) || safeStr(simpleWord && simpleWord.usphone)
      },
      poses: [],
      forms: [],
      examples: [],
      source: '有道词典',
      sourceUrl: YOUDAO_HOME.replace('%s', encodeURIComponent(word))
    };

    var trs = (ecWord && ecWord.trs) || [];
    for (var i = 0; i < trs.length; i++) {
      var lines = (trs[i] && trs[i].tr && trs[i].tr[0] && trs[i].tr[0].l && trs[i].tr[0].l.i) || [];
      for (var j = 0; j < lines.length; j++) {
        var line = safeStr(lines[j]).trim();
        if (line) out.poses.push(splitPos(line));
      }
    }

    if (!out.poses.length && raw.fanyi && typeof raw.fanyi.tran === 'string' && raw.fanyi.tran) {
      out.poses.push({ pos: '', meaning: humanizeMarks(raw.fanyi.tran) });
    }

    var wfs = (ecWord && ecWord.wfs) || [];
    for (var k = 0; k < wfs.length; k++) {
      var wf = wfs[k] && wfs[k].wf;
      if (wf && wf.name && wf.value) out.forms.push({ name: wf.name, value: wf.value });
    }

    var pairs = (raw.blng_sents_part && raw.blng_sents_part['sentence-pair']) || [];
    if (Array.isArray(pairs)) {
      for (var n = 0; n < pairs.length; n++) {
        var en = safeStr(pairs[n] && pairs[n].sentence).trim();
        var zh = safeStr(pairs[n] && pairs[n]['sentence-translation']).trim();
        if (en) out.examples.push({ en: en, zh: zh });
      }
    }

    var hasContent = out.poses.length || out.examples.length || out.phonetics.uk || out.phonetics.us;
    return hasContent ? out : null;
  }

  /** 词条里到底有没有「可看的东西」—— 只有音标/词形、没有释义与例句时，
   *  不该弹一个空壳（品牌词、缩写常这样）。桌面端 lookup.has_definition 与它同义。 */
  function hasDefinition(entry) {
    if (!entry || typeof entry !== 'object') return false;
    return !!((entry.poses && entry.poses.length) || (entry.examples && entry.examples.length));
  }

  /** 从模型自由文本里抠出第一个 JSON 对象；容忍代码围栏、尾逗号与常见畸形 */
  function extractJson(text) {
    if (!text) return null;
    var t = String(text).trim();
    t = t.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
    var start = t.indexOf('{');
    var end = t.lastIndexOf('}');
    if (start === -1 || end <= start) return null;
    var slice = t.slice(start, end + 1);

    // 小模型常见畸形：数组里混进键值对，如 ["n.", "meaning": "释义"]
    // → 修成 [{"pos": "n.", "meaning": "释义"}]（注意要把对象闭合括号一起补上）
    var POS_KEY = '"(?:meaning|zh|释义|中文|definition|translation)"';
    var repaired = slice
      // ① 单项且以 ] 收尾
      .replace(
        new RegExp('\\[\\s*"([^"]{1,20})"\\s*,\\s*' + POS_KEY + '\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"\\s*\\]', 'g'),
        '[{"pos":"$1","meaning":"$2"}]'
      )
      // ② 数组开头但后面还有更多项（暂不闭合）
      .replace(
        new RegExp('\\[\\s*"([^"]{1,20})"\\s*,\\s*' + POS_KEY + '\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"', 'g'),
        '[{"pos":"$1","meaning":"$2"}'
      )
      // ③ 后续项以 , … ] 或 } 收尾
      .replace(
        new RegExp(',\\s*"([^"]{1,20})"\\s*,\\s*' + POS_KEY + '\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"(?=\\s*[,\\]}])', 'g'),
        ',{"pos":"$1","meaning":"$2"}'
      );

    var candidates = [
      slice,
      slice.replace(/,\s*([}\]])/g, '$1'),
      repaired,
      repaired.replace(/,\s*([}\]])/g, '$1')
    ];
    for (var i = 0; i < candidates.length; i++) {
      try { return JSON.parse(candidates[i]); } catch (e) { /* 试下一种 */ }
    }
    return null;
  }

  /** 把 "n. 释义；v. 释义" 这类多词性字符串拆成多条 */
  function pushPosLines(out, text) {
    String(text || '').split(/[;；\n]+/).forEach(function (line) {
      var t = line.trim();
      if (t) out.poses.push(splitPos(t));
    });
  }

  /** 模型可能照抄提示词里的占位符，出现这些值一律丢弃 */
  var PLACEHOLDERS = ['英文例句', '例句', '中文翻译', '翻译', '中文释义', '英文句子', '英文释义'];

  /** 从小模型给出的各种例句写法里取出 {en, zh} */
  function examplePair(raw) {
    if (!raw) return null;

    if (typeof raw === 'string') {
      var s = raw.trim();
      return s && PLACEHOLDERS.indexOf(s) === -1 ? { en: s, zh: '' } : null;
    }

    if (Array.isArray(raw)) {
      var arr = raw
        .filter(function (v) { return typeof v === 'string' && v.trim(); })
        .map(function (v) { return v.trim(); })
        .filter(function (v) { return PLACEHOLDERS.indexOf(v) === -1; });
      return arr.length ? { en: arr[0], zh: arr[1] || '' } : null;
    }

    if (typeof raw === 'object') {
      var en = safeStr(raw.en || raw.english || raw.sentence || raw.orig).trim();
      var zh = safeStr(raw.zh || raw.cn || raw.chinese || raw.translation || raw.trans).trim();
      if (PLACEHOLDERS.indexOf(en) !== -1) en = '';
      if (PLACEHOLDERS.indexOf(zh) !== -1) zh = '';
      if (!en) {
        var vals = Object.keys(raw)
          .map(function (k) { return safeStr(raw[k]).trim(); })
          .filter(function (v) { return v && PLACEHOLDERS.indexOf(v) === -1; });
        if (vals.length) {
          en = vals[0];
          if (!zh && vals[1]) zh = vals[1];
        }
      }
      return en ? { en: en, zh: zh } : null;
    }

    return null;
  }

  /** 小模型（文本）返回 → 统一结构 */
  function normalizeModel(rawText, fallbackWord) {
    var j = extractJson(rawText);
    if (!j || typeof j !== 'object') return null;

    var out = {
      word: safeStr(j.word) || fallbackWord || '',
      phonetics: { uk: safeStr(j.phonetic_uk), us: safeStr(j.phonetic_us) },
      poses: [],
      forms: [],
      examples: [],
      source: '本地小模型',
      sourceUrl: ''
    };

    // —— 词性释义：兼容「扁平字符串（新格式）/ 字符串数组 / 对象数组 / 映射对象」 ——
    var pos = j.pos || j.pos_list || j.part_of_speech;
    if (typeof pos === 'string') {
      pushPosLines(out, pos);
    } else if (Array.isArray(pos)) {
      for (var i = 0; i < pos.length; i++) {
        var item = pos[i];
        if (typeof item === 'string') {
          pushPosLines(out, item);
        } else if (item && typeof item === 'object') {
          var meaning = safeStr(item.meaning || item.zh || item.definition || item.translation).trim();
          if (meaning) out.poses.push({ pos: safeStr(item.pos || item.type).trim(), meaning: humanizeMarks(meaning) });
        }
      }
    } else if (pos && typeof pos === 'object') {
      Object.keys(pos).forEach(function (key) {
        var v = pos[key];
        if (typeof v === 'string' && v.trim()) {
          out.poses.push({ pos: key, meaning: humanizeMarks(v.trim()) });
        }
      });
    }

    // —— 例句：兼容多种键名与写法 ——
    var ex = j.examples || j.example || j.sentences;
    if (Array.isArray(ex)) {
      for (var k = 0; k < ex.length; k++) {
        var pair = examplePair(ex[k]);
        if (pair) out.examples.push(pair);
      }
    } else if (ex) {
      var single = examplePair(ex);
      if (single) out.examples.push(single);
    }

    if (typeof j.meaning === 'string' && j.meaning.trim() && !out.poses.length) {
      out.poses.push({ pos: '', meaning: humanizeMarks(j.meaning) });
    }

    var hasContent = out.poses.length || out.examples.length || out.phonetics.uk || out.phonetics.us;
    return hasContent ? out : null;
  }

  /**
   * 视觉模型输出 → 英文单词。
   * 模型按约定应返回 {"word":"..."} 或 {"word":null}；
   * 任何不满足英文单词判定的结果一律返回空串（宁可不弹窗）。
   */
  function pickWordFromVision(rawText) {
    var j = extractJson(rawText);
    if (!j || typeof j !== 'object') return '';
    var w = safeStr(j.word).trim();
    if (!w) return '';
    w = w.replace(/^[^A-Za-z]+/, '').replace(/[^A-Za-z]+$/, '');
    return isEnglishWord(w) ? w : '';
  }

  /** 文本查词的严格 JSON 提示词（含具体示例——小模型对「占位符模板」会照抄，必须给真实内容） */
  function buildModelPrompt(word) {
    var system = [
      '你是一部英汉词典。根据用户给出的英文单词输出词条，只输出一个 JSON 对象。',
      '严格照下面这个例子的字段名和类型输出（不要输出 markdown 代码块，不要任何解释）：',
      '{"word":"example","phonetic_uk":"ɪɡˈzɑːmpl","phonetic_us":"ɪɡˈzæmpl",' +
      '"pos":"n. 例子，实例；v. 把…作为例子",' +
      '"examples":[{"en":"This is a good example.","zh":"这是一个好例子。"}]}',
      '规则：',
      '1. pos 是一个字符串：不同词性用分号分隔，格式如「n. 释义；v. 释义」，最多 3 个词性；',
      '2. examples 是数组，给 2 条简短例句，每条必须同时有 en 和 zh 两个字段；',
      '3. 音标使用 IPA；不确定时填空字符串，不要编造；',
      '4. word 填用户给出的原词。'
    ].join('\n');
    return [
      { role: 'system', content: system },
      { role: 'user', content: '单词：' + word }
    ];
  }

  /** 图片取词提示词（hint 描述光标在裁剪图中的相对位置） */
  function buildVisionPrompt(hint) {
    return [
      '这是一张网页截图的小块裁剪，用于「鼠标指到哪个英文单词」的识别。',
      '用户鼠标停在图中位置：' + (hint || '正中央') + ' 附近。',
      '任务：找出该位置附近的英文单词。',
      '只输出一个 JSON 对象：有英文单词时输出 {"word":"单词"}；',
      '没有可辨认的英文单词（例如只有中文、数字、图形、公式或空白）时输出 {"word":null}。',
      '不要输出任何其他文字，不要解释。'
    ].join('\n');
  }

  root.ETNormalize = {
    isEnglishWord: isEnglishWord,
    extractWordAt: extractWordAt,
    wordsIn: wordsIn,
    normalizeYoudao: normalizeYoudao,
    normalizeModel: normalizeModel,
    pickWordFromVision: pickWordFromVision,
    extractJson: extractJson,
    splitPos: splitPos,
    humanizeMarks: humanizeMarks,
    phraseOf: phraseOf,
    hasDefinition: hasDefinition,
    buildModelPrompt: buildModelPrompt,
    buildVisionPrompt: buildVisionPrompt
  };
})(typeof globalThis !== 'undefined' ? globalThis : self);
