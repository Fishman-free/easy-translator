/**
 * Easy Translator — 悬停引擎 + 结果卡片（网页内容脚本与内置 PDF 阅读器共用）
 *
 * 触发规则（对齐产品要求）：
 *   · 只对「合法的英文单词」弹窗；中文、数字、标点、空白、乱码一律静默；
 *   · 鼠标在同一目标上驻留超过设定时长才触发（默认 5s，图片 1.5s）；
 *   · 目标变化 / 滚动 / Esc / 点击空白处 → 立即收起；
 *   · 鼠标移到卡片上不收起（可复制、可点发音）。
 *
 * 依赖（需在这份脚本之前加载）：ETSettings、ETNormalize
 */
(function (root) {
  'use strict';

  var ET = root.ETNormalize;
  var ES = root.ETSettings;
  if (!ET || !ES) return;

  var CARD_MARGIN = 12;
  var OFFSET_X = 14;
  var OFFSET_Y = 18;
  var MOVE_THROTTLE = 110;
  var HIDE_GRACE = 900;
  var IMAGE_CELL = 40;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function createEngine(opts) {
    var doc = opts.doc || document;
    var win = opts.win || window;

    var settings = null;
    var token = 0;
    var timer = null;
    var hideTimer = null;
    var current = null;       // { key, kind, word, x, y, image }
    var lastMoveAt = 0;
    var card = null;          // { host, shadow, root }
    var hintEl = null;        // 「识别中」小脉冲
    var pinned = false;       // 鼠标停在卡片上
    var warned = {};          // 会话内一次性提示去重
    var stopped = false;

    /* ---------------- 卡片 ---------------- */

    function ensureCard() {
      if (card && card.host && card.host.isConnected) return card;
      var host = doc.createElement('div');
      host.setAttribute('data-easy-translator', 'card');
      host.style.cssText = 'all: initial; position: fixed; top: 0; left: 0; width: 0; height: 0; z-index: 2147483647; pointer-events: none;';
      var shadow = host.attachShadow({ mode: 'closed' });
      var link = doc.createElement('link');
      link.rel = 'stylesheet';
      link.href = chrome.runtime.getURL('content/card.css');
      shadow.appendChild(link);
      var box = el('div', 'et-card');
      box.style.display = 'none';
      box.style.pointerEvents = 'auto';

      // 鲸鱼娘的对话气泡：释义全部装进气泡内，她本人站在卡片右下角
      var bubble = el('div', 'et-bubble');
      box.appendChild(bubble);
      // 尾点已按用户要求去掉（DOM 不再造它 —— 之前 CSS 删了、DOM 还在造，是死元素）
      var mascot = doc.createElement('img');
      mascot.className = 'et-mascot';
      mascot.alt = '鲸鱼娘';
      mascot.draggable = false;
      mascot.src = chrome.runtime.getURL('assets/mascot.png');
      box.appendChild(mascot);
      shadow.appendChild(box);

      box.addEventListener('mouseenter', function () {
        pinned = true;
        if (hideTimer) { win.clearTimeout(hideTimer); hideTimer = null; }
      });
      box.addEventListener('mouseleave', function () {
        pinned = false;
        scheduleHide();
      });

      (doc.body || doc.documentElement).appendChild(host);
      card = { host: host, shadow: shadow, root: box, bubble: bubble };
      return card;
    }

    function clearNode(node) {
      while (node.firstChild) node.removeChild(node.firstChild);
    }

    /**
     * 把当前状态写到宿主元素的 data-* 上。
     * 卡片内部使用 closed shadow DOM（与页面彻底隔离），
     * 这里对外暴露最小可观测状态，便于用户排查与自动化测试。
     */
    function setState(state, word, source) {
      if (!card || !card.host) return;
      var ds = card.host.dataset;
      ds.etState = state || '';
      if (word !== undefined) ds.etWord = word || '';
      if (source !== undefined) ds.etSource = source || '';
    }

    function positionCard(anchor) {
      if (!card) return;
      var vw = doc.documentElement.clientWidth;
      var vh = doc.documentElement.clientHeight;
      var rect = card.root.getBoundingClientRect();
      var w = rect.width || 340;
      var h = rect.height || 160;
      var left = anchor.x + OFFSET_X;
      var top = anchor.y + OFFSET_Y;
      if (left + w + CARD_MARGIN > vw) left = Math.max(CARD_MARGIN, vw - w - CARD_MARGIN);
      if (top + h + CARD_MARGIN > vh) {
        var above = anchor.y - h - OFFSET_Y;
        top = above >= CARD_MARGIN ? above : Math.max(CARD_MARGIN, vh - h - CARD_MARGIN);
      }
      // 卡片不要压住光标本身：压住会让鼠标"钻进"卡片、来回触发 mouseenter/mouseleave，
      // 表现为卡片忽隐忽现（曾经因此出现「卡片再也不回来」的观感）。放不下时改放左侧。
      var covers = anchor.x >= left && anchor.x <= left + w && anchor.y >= top && anchor.y <= top + h;
      if (covers) {
        var above2 = anchor.y - h - OFFSET_Y;
        var leftOfCursor = anchor.x - w - OFFSET_X;
        if (above2 >= CARD_MARGIN) top = above2;
        else if (leftOfCursor >= CARD_MARGIN) left = leftOfCursor;
      }
      card.root.style.left = Math.round(left) + 'px';
      card.root.style.top = Math.round(top) + 'px';
    }

    function hideCard(force) {
      if (!card) return;
      if (pinned && !force) return;
      card.root.style.display = 'none';
      clearNode(card.root);
      setState('hidden');
      cancelHint();
    }

    function scheduleHide() {
      if (hideTimer) win.clearTimeout(hideTimer);
      hideTimer = win.setTimeout(function () {
        hideTimer = null;
        hideCard(false);
      }, HIDE_GRACE);
    }

    /* ---------------- 「识别中」提示 ---------------- */

    function showHint(x, y) {
      if (!settings || !settings.imageOcr || !settings.imageOcr.hint) return;
      var c = ensureCard();
      if (!hintEl) {
        hintEl = el('div', 'et-hint');
      }
      hintEl.style.left = Math.round(x + 12) + 'px';
      hintEl.style.top = Math.round(y + 12) + 'px';
      if (!hintEl.isConnected) c.shadow.appendChild(hintEl);
    }

    function cancelHint() {
      if (hintEl && hintEl.isConnected) hintEl.remove();
    }

    /* ---------------- 卡片内容 ---------------- */

    function speak(text, lang) {
      try {
        if (!win.speechSynthesis) return;
        win.speechSynthesis.cancel();
        var u = new SpeechSynthesisUtterance(text);
        u.lang = lang;
        u.rate = 0.95;
        var voices = win.speechSynthesis.getVoices() || [];
        for (var i = 0; i < voices.length; i++) {
          if (voices[i].lang && voices[i].lang.toLowerCase().indexOf(lang.slice(0, 2).toLowerCase()) === 0) {
            u.voice = voices[i];
            break;
          }
        }
        win.speechSynthesis.speak(u);
      } catch (e) { /* 部分页面禁用语音，忽略 */ }
    }

    function slash(p) {
      var s = String(p || '').trim();
      if (!s) return '';
      if (s.charAt(0) === '/' || s.charAt(0) === '[') return s;
      return '/' + s + '/';
    }

    function copyText(text, btn) {
      var done = function () {
        var old = btn.textContent;
        btn.textContent = '已复制';
        win.setTimeout(function () { btn.textContent = old; }, 1200);
      };
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { /* 忽略 */ });
        } else {
          var ta = doc.createElement('textarea');
          ta.value = text;
          ta.style.cssText = 'position:fixed;opacity:0;';
          doc.body.appendChild(ta);
          ta.select();
          doc.execCommand('copy');
          ta.remove();
          done();
        }
      } catch (e) { /* 忽略 */ }
    }

    function buildCardText(data) {
      var lines = [data.word];
      var ph = [];
      if (data.phonetics && data.phonetics.uk) ph.push('英 ' + slash(data.phonetics.uk));
      if (data.phonetics && data.phonetics.us) ph.push('美 ' + slash(data.phonetics.us));
      if (ph.length) lines.push(ph.join('  '));
      (data.poses || []).forEach(function (p) {
        lines.push((p.pos ? p.pos + ' ' : '') + p.meaning);
      });
      (data.examples || []).slice(0, 2).forEach(function (ex) {
        lines.push('· ' + ex.en + (ex.zh ? '  ' + ex.zh : ''));
      });
      return lines.join('\n');
    }

    function renderResult(data, meta, anchor) {
      var c = ensureCard();
      var r = c.bubble;
      clearNode(r);
      r.className = 'et-bubble';
      cancelHint();

      // 头部
      var head = el('div', 'et-head');
      var title = el('div', 'et-title');
      title.appendChild(el('span', 'et-word', data.word));
      if (meta.fromImage) title.appendChild(el('span', 'et-badge', '图中识别'));
      if (meta.cached) title.appendChild(el('span', 'et-badge et-badge-dim', '缓存'));
      head.appendChild(title);

      var tools = el('div', 'et-tools');
      var ph = data.phonetics || {};
      if (settings.showSpeak && (ph.uk || ph.us)) {
        if (ph.uk) tools.appendChild(speakBtn('英', data.word, 'en-GB'));
        if (ph.us) tools.appendChild(speakBtn('美', data.word, 'en-US'));
      }
      var copyBtn = el('button', 'et-btn', '复制');
      copyBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        copyText(buildCardText(data), copyBtn);
      });
      tools.appendChild(copyBtn);
      var closeBtn = el('button', 'et-btn et-btn-close', '✕');
      closeBtn.title = '关闭 (Esc)';
      closeBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        hideCard(true);
      });
      tools.appendChild(closeBtn);
      head.appendChild(tools);
      r.appendChild(head);

      // 音标
      var phText = [];
      if (ph.uk) phText.push('英 ' + slash(ph.uk));
      if (ph.us) phText.push('美 ' + slash(ph.us));
      if (phText.length) r.appendChild(el('div', 'et-phonetic', phText.join('   ')));

      // 释义
      var poses = (data.poses || []).slice(0, 8);
      if (poses.length) {
        var list = el('div', 'et-poses');
        poses.forEach(function (p) {
          var row = el('div', 'et-pos-row');
          if (p.pos) row.appendChild(el('span', 'et-pos', p.pos));
          row.appendChild(el('span', 'et-meaning', p.meaning));
          list.appendChild(row);
        });
        r.appendChild(list);
      }

      // 例句
      var maxEx = settings.examplesCount || 0;
      var exs = (data.examples || []).slice(0, maxEx);
      if (exs.length) {
        var wrap = el('div', 'et-examples');
        wrap.appendChild(el('div', 'et-section-title', '例句'));
        exs.forEach(function (ex) {
          var item = el('div', 'et-example');
          item.appendChild(el('div', 'et-ex-en', ex.en));
          if (ex.zh) item.appendChild(el('div', 'et-ex-zh', ex.zh));
          wrap.appendChild(item);
        });
        r.appendChild(wrap);
      }

      // 词形变化
      if (data.forms && data.forms.length) {
        var forms = data.forms.slice(0, 5).map(function (f) { return f.name + ' ' + f.value; }).join(' · ');
        r.appendChild(el('div', 'et-forms', forms));
      }

      // 底部
      var foot = el('div', 'et-foot');
      foot.appendChild(el('span', 'et-source', meta.engine || data.source || ''));
      if (data.sourceUrl) {
        var linkBtn = el('a', 'et-link', '词典页');
        linkBtn.href = data.sourceUrl;
        linkBtn.target = '_blank';
        linkBtn.rel = 'noreferrer noopener';
        foot.appendChild(linkBtn);
      }
      r.appendChild(foot);

      c.root.style.display = 'block';
      positionCard(anchor);
      setState('result', data.word, meta.engine || data.source || '');
    }

    function speakBtn(label, text, lang) {
      var b = el('button', 'et-btn et-btn-speak', label);
      b.title = '朗读（' + (lang.indexOf('GB') !== -1 ? '英式' : '美式') + '）';
      b.addEventListener('click', function (ev) {
        ev.stopPropagation();
        speak(text, lang);
      });
      return b;
    }

    function showMessage(title, text, anchor, kind) {
      var c = ensureCard();
      var r = c.bubble;
      clearNode(r);
      r.className = 'et-bubble' + (kind === 'tip' ? ' et-bubble-tip' : '');
      var head = el('div', 'et-head');
      head.appendChild(el('span', 'et-word', title));
      var closeBtn = el('button', 'et-btn et-btn-close', '✕');
      closeBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        hideCard(true);
      });
      head.appendChild(closeBtn);
      r.appendChild(head);
      var body = el('div', 'et-message', text);
      r.appendChild(body);
      c.root.style.display = 'block';
      positionCard(anchor || { x: 80, y: 80 });
      setState(kind === 'tip' ? 'tip' : 'message', title);
    }

    /* ---------------- 取词 ---------------- */

    /** 文本节点内 [start,end) 的首个可见矩形（跨行时取第一段） */
    function rectIn(node, start, end) {
      try {
        var r = doc.createRange();
        r.setStart(node, start);
        r.setEnd(node, end);
        var rects = r.getClientRects();
        for (var i = 0; i < rects.length; i++) {
          if (rects[i].width > 0.5) return rects[i];
        }
      } catch (e) { /* 忽略 */ }
      return null;
    }

    /** 单点：caret 落点 → 单词（原逻辑；命中最准，作为第一优先） */
    function wordFromCaret(x, y) {
      var range = null;
      try {
        if (doc.caretRangeFromPoint) {
          range = doc.caretRangeFromPoint(x, y);
        } else if (doc.caretPositionFromPoint) {
          var pos = doc.caretPositionFromPoint(x, y);
          if (pos && pos.offsetNode) {
            range = doc.createRange();
            range.setStart(pos.offsetNode, pos.offset);
          }
        }
      } catch (e) { return null; }
      if (!range) return null;

      var node = range.startContainer;
      if (!node || node.nodeType !== 3) return null;
      if (card && card.host && (node === card.host || card.host.contains(node))) return null;

      var found = ET.extractWordAt(node.textContent || '', range.startOffset);
      if (!found.word) return null;
      return { node: node, word: found.word, start: found.start, end: found.end };
    }

    /* 落点微调表：caret 在中英混排、极小字号下常落到相邻字符上（鼠标明明在词里却没取到词）。
       横向给到 ±4px（字符边界错位主要发生在横向），纵向只 ±2px，避免跨到相邻行。 */
    var PROBES = [[0, 0], [-2, 0], [2, 0], [0, -2], [0, 2], [-4, 0], [4, 0]];

    function wordByProbing(x, y) {
      for (var i = 0; i < PROBES.length; i++) {
        var hit = wordFromCaret(x + PROBES[i][0], y + PROBES[i][1]);
        if (hit) return hit;
      }
      return null;
    }

    /* 几何兜底：caret 不可用、或 caret 吸到了相邻词时，按矩形就近匹配。
       容差 3px——空白处与中文上依旧不触发；缝隙处左偏置（与「紧贴标点归属左侧单词」一致）。 */
    var GEOM_TOL = 3;
    var GEOM_MAX_NODES = 80;
    var LEFT_BIAS = 1.5;

    /** 落点是否真的落在该词的矩形内（caret 结果的可信度判据） */
    function containsPoint(x, y, hit) {
      var box = rectIn(hit.node, hit.start, hit.end);
      if (!box) return false;
      return x >= box.left - 0.5 && x <= box.right + 0.5 && y >= box.top - 0.5 && y <= box.bottom + 0.5;
    }

    function wordByGeometry(x, y) {
      var el = null;
      try { el = doc.elementFromPoint(x, y); } catch (e) { return null; }
      if (!el) return null;
      if (card && card.host && (el === card.host || card.host.contains(el))) return null;

      var best = null;
      var bestDist = Infinity;
      var scanned = 0;
      var walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
      var node;
      while ((node = walker.nextNode()) && scanned < GEOM_MAX_NODES) {
        var text = node.textContent || '';
        if (!text || !/[A-Za-z]/.test(text)) continue;
        var words = ET.wordsIn(text);
        if (!words.length) continue;
        scanned++;
        for (var i = 0; i < words.length; i++) {
          var box = rectIn(node, words[i].start, words[i].end);
          if (!box) continue;
          var dx = Math.max(box.left - x, 0, x - box.right);
          var dy = Math.max(box.top - y, 0, y - box.bottom);
          if (dx > GEOM_TOL || dy > GEOM_TOL) continue;
          var dist = dx + dy * 2 + (box.left >= x ? LEFT_BIAS : 0);   // 竖向偏离更贵；缝隙处左偏置
          if (dist < bestDist) {
            bestDist = dist;
            best = { word: words[i].word, start: words[i].start, end: words[i].end };
          }
        }
      }
      return best;
    }

    /* ---------------- 表单控件里的文字（textarea / input） ----------------
       控件的 value 不是 DOM 文本节点，caret 落点法拿不到 —— 而输入框恰恰都是这类
       （ChatGPT 的消息框、搜索框……）。做法：按同样的字体与盒模型把 value 拆成
       「一字一 span」铺在控件正上方的隐藏层里，读每个 span 的矩形找落点字符下标。
       不用 hit-test（visibility:hidden 也能读矩形），故不受 pointer-events / 层叠影响。 */
    var mcFor = null, mcVal = null, mcScroll = '', mcBox = null, mcSpans = null;
    var TEXTY_INPUTS = { text: 1, search: 1, url: 1, tel: 1, password: 1, email: 1 };

    function textControlOf(el) {
      for (var i = 0; i < 3 && el; i++) {
        var tag = (el.tagName || '').toUpperCase();
        if (tag === 'TEXTAREA') return el;
        if (tag === 'INPUT') {
          return TEXTY_INPUTS[(el.type || 'text').toLowerCase()] ? el : null;
        }
        if (tag === 'SELECT') return null;
        el = el.parentElement;
      }
      return null;
    }

    function controlMirror(el) {
      var key = el.scrollTop + ',' + el.scrollLeft;
      if (mcFor === el && mcVal === el.value && mcScroll === key && mcBox && mcBox.offsetWidth === el.offsetWidth) {
        return mcSpans;
      }
      if (mcBox && mcBox.parentNode) mcBox.parentNode.removeChild(mcBox);
      mcFor = el; mcVal = el.value; mcScroll = key;
      var cs = win.getComputedStyle(el);
      var r = el.getBoundingClientRect();
      var box = doc.createElement('div');
      var st = box.style;
      st.position = 'fixed';
      st.left = r.left + 'px';
      st.top = r.top + 'px';
      st.width = el.offsetWidth + 'px';
      st.height = el.offsetHeight + 'px';
      st.visibility = 'hidden';
      st.pointerEvents = 'none';
      st.overflow = 'hidden';
      st.boxSizing = cs.boxSizing;
      st.whiteSpace = ((el.tagName || '').toUpperCase() === 'INPUT') ? 'pre' : 'pre-wrap';
      st.overflowWrap = 'break-word';
      st.wordBreak = 'normal';
      var props = ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'fontVariant', 'letterSpacing',
        'lineHeight', 'textTransform', 'textAlign', 'textIndent', 'wordSpacing', 'tabSize',
        'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
        'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth'];
      for (var i = 0; i < props.length; i++) st[props[i]] = cs[props[i]];
      var spans = [];
      var val = mcVal;
      for (var j = 0; j < val.length; j++) {
        var sp = doc.createElement('span');
        sp.textContent = val.charAt(j);
        box.appendChild(sp);
        spans.push(sp);
      }
      doc.body.appendChild(box);
      box.scrollTop = el.scrollTop;
      box.scrollLeft = el.scrollLeft;
      mcBox = box;
      mcSpans = spans;
      return spans;
    }

    function wordFromControl(el, x, y) {
      var idx = -1, tag = '', n = 0;
      try {
        el = textControlOf(el);
        if (!el || typeof el.value !== 'string' || !el.value) return null;
        tag = (el.tagName || '').toUpperCase();
        var spans = controlMirror(el);
        n = spans.length;
        var near = -1, nearD = 1e9;
        for (var i = 0; i < spans.length; i++) {
          var b = spans[i].getBoundingClientRect();
          if (b.width === 0 && b.height === 0) continue;
          if (x >= b.left - 0.5 && x <= b.right + 0.5 && y >= b.top - 0.5 && y <= b.bottom + 0.5) { idx = i; break; }
          var d = Math.max(b.left - x, 0, x - b.right) + Math.max(b.top - y, 0, y - b.bottom);
          if (d < nearD) { nearD = d; near = i; }
        }
        if (idx < 0 && nearD <= 8) idx = near;          // 兜底：贴着最近的字符（跨度稍有偏差时）
        if (idx >= 0) {
          var found = ET.extractWordAt(el.value, idx);
          trace({ path: 'control', tag: tag, n: n, idx: idx, nearD: Math.round(nearD), word: found.word || '' });
          return found.word ? { word: found.word, start: found.start, end: found.end } : null;
        }
      } catch (e) { trace({ path: 'control', error: String(e) }); return null; }
      trace({ path: 'control', tag: tag, n: n, idx: idx, word: '' });
      return null;
    }

    /** 取词路径诊断（跨世界可见：写在 <html> 的 data 属性上，E2E/排查时可读） */
    function trace(obj) {
      try { doc.documentElement.setAttribute('data-et-trace', JSON.stringify(obj)); } catch (e) { /* 忽略 */ }
    }

    /**
     * 落点 → 单词。
     * ① 表单控件（textarea/input）：value 不在 DOM 里，走镜像层量下标
     * ② caret 落点解析：仅在「落点确实在词内」时采信——极小字号下 caret 会吸到相邻词上，
     *    那种结果比不弹窗更糟（用户会看到另一个词的释义）。
     * ③ ±2/±4px 多点探测：caret 落在缝隙/标点上时，从邻近点把它捞回来。
     * ④ 按矩形就近匹配：caret 完全不可用（user-select:none、无插入点的光标上下文）时的兜底。
     */
    function wordAtPoint(x, y) {
      var el = null;
      try { el = doc.elementFromPoint(x, y); } catch (e) { el = null; }
      var ctrlHit = el ? wordFromControl(el, x, y) : null;
      if (ctrlHit) return ctrlHit;
      var caretHit = wordByProbing(x, y);
      var hit = (caretHit && containsPoint(x, y, caretHit)) ? caretHit : (wordByGeometry(x, y) || caretHit);
      return hit ? { word: hit.word, start: hit.start, end: hit.end } : null;
    }

    function elementLooksTextless(node) {
      var t = (node.textContent || '').trim();
      return t.length === 0;
    }

    function describeImage(node, tag) {
      var src = '';
      try {
        if (tag === 'IMG') {
          src = node.currentSrc || node.src || '';
        } else if (tag === 'BG') {
          var bg = win.getComputedStyle(node).backgroundImage || '';
          var m = /url\(["']?([^"')]+)/.exec(bg);
          src = m ? m[1] : '';
        } else {
          src = tag + '#' + (node.id || '');
        }
      } catch (e) { /* 忽略 */ }
      return { node: node, tag: tag, src: String(src).slice(-140) };
    }

    function imageAtPoint(x, y) {
      var node = null;
      try { node = doc.elementFromPoint(x, y); } catch (e) { return null; }
      if (!node) return null;
      if (card && card.host && (node === card.host || card.host.contains(node))) return null;

      var tag = (node.tagName || '').toUpperCase();
      if (tag === 'IMG' || tag === 'CANVAS' || tag === 'VIDEO' || tag === 'PICTURE' || tag === 'SVG' || tag === 'OBJECT') {
        return describeImage(node, tag);
      }
      if (elementLooksTextless(node)) {
        try {
          var bg = win.getComputedStyle(node).backgroundImage || '';
          if (bg.indexOf('url(') !== -1) return describeImage(node, 'BG');
        } catch (e) { /* 忽略 */ }
      }
      return null;
    }

    /* ---------------- 状态机 ---------------- */

    function clearTimer() {
      if (timer) { win.clearTimeout(timer); timer = null; }
    }

    function setTarget(info) {
      if (current && current.key === info.key) {
        current.x = info.x;
        current.y = info.y;
        // 同一目标微动：保持计时不打断。但如果此刻没有任何可见内容
        // （卡片已被收起、或还没显示出来），必须重新计时——
        // 否则会进入「卡片消失后再也不回来」的死状态：
        // 例如光标蹭到卡片又移回同一个词，或者卡片被视口顶到光标下方。
        if (!cardVisible() && !timer) scheduleFire(info);
        return;
      }
      clearTimer();
      current = info;
      if (card && !pinned) hideCard(false);
      cancelHint();
      scheduleFire(info);
    }

    /** 卡片当前是否有可见内容（loading / result / message 都算） */
    function cardVisible() {
      return !!(card && card.root && card.root.style.display !== 'none' && card.root.firstChild);
    }

    function clearTarget() {
      clearTimer();
      current = null;
      cancelHint();
      if (card && !pinned) hideCard(false);
    }

    function scheduleFire(info) {
      clearTimer();   // 防止遗留计时器：同一目标重新计时时必须丢掉旧的
      var delay = info.kind === 'image'
        ? ((settings.imageOcr && settings.imageOcr.dwellMs) || 1500)
        : (settings.dwellMs || 5000);
      timer = win.setTimeout(function () {
        timer = null;
        if (stopped || !current || current.key !== info.key) return;
        fire(info);
      }, delay);
    }

    function fire(info) {
      var myToken = ++token;
      if (info.kind === 'text') {
        // 期间滚动过的话，落点下可能已经换了词 —— 触发前再核一次：
        // 宁可不弹，也不弹一个不在光标下的词（弹错词比不弹更糟）。
        if (info.staleAt) {
          var again = wordAtPoint(info.x, info.y);
          if (!again || String(again.word).toLowerCase() !== String(info.word).toLowerCase()) {
            if (again) setTarget({ key: 't:' + again.word, kind: 'text', word: again.word, x: info.x, y: info.y });
            else clearTarget();
            return;
          }
        }
        lookupText(info.word, info, myToken);
      } else {
        lookupImage(info, myToken);
      }
    }

    function sendMessage(payload, cb) {
      try {
        chrome.runtime.sendMessage(payload, function (res) {
          if (chrome.runtime.lastError) {
            cb({ ok: false, error: chrome.runtime.lastError.message });
            return;
          }
          cb(res);
        });
      } catch (e) {
        cb({ ok: false, error: '扩展已更新，请刷新页面' });
      }
    }

    function lookupText(word, info, myToken) {
      // 用户：「不要先弹一个空白方框」—— 查到内容之前**完全不显示**，
      // 只记状态（加载壳曾是 et-loading 的空白卡片，看着像空方框）。
      setState('loading', word);
      sendMessage({ type: 'lookup', word: word }, function (res) {
        if (myToken !== token) return;
        if (!res || !res.ok) { handleFailure(res, info); return; }
        var d = res.data;
        // 只有音标、没有释义/例句（品牌词、缩写时会出现）→ 不弹空壳，给一句话说明
        if (!ET.hasDefinition(d)) {
          showMessage('没有查到释义', '『' + word + '』在词典里没有中文释义（品牌词/缩写常这样）。', info, 'tip');
          return;
        }
        renderResult(d, {
          engine: res.engine,
          cached: res.cached
        }, info);
      });
    }

    function lookupImage(info, myToken) {
      var cfg = settings.imageOcr || {};
      showHint(info.x, info.y);

      var vw = doc.documentElement.clientWidth;
      var vh = doc.documentElement.clientHeight;
      var w = cfg.cropW || 460;
      var h = cfg.cropH || 140;
      var rect = { x: info.x - w / 2, y: info.y - h / 2, w: w, h: h };
      if (rect.x < 0) rect.x = 0;
      if (rect.y < 0) rect.y = 0;
      if (rect.x + rect.w > vw) rect.x = Math.max(0, vw - rect.w);
      if (rect.y + rect.h > vh) rect.y = Math.max(0, vh - rect.h);

      sendMessage({
        type: 'lookup-image',
        rect: rect,
        dpr: win.devicePixelRatio || 1,
        imageKey: (info.image && info.image.src) || '',
        cell: info.key,
        offsetX: (info.x - rect.x) / rect.w,
        offsetY: (info.y - rect.y) / rect.h
      }, function (res) {
        cancelHint();
        if (myToken !== token) return;
        if (!res || !res.ok) { handleFailure(res, info); return; }
        renderResult(res.data, {
          engine: res.engine,
          cached: res.cached,
          fromImage: true
        }, info);
      });
    }

    function handleFailure(res, info) {
      var err = (res && res.error) || '未知错误';
      if (err === 'not-english' || err === 'disabled' || err === 'image-ocr-off') {
        // 静默不打扰，但**必须把 loading 卡收掉** —— 否则只留一个空白气泡挂在屏幕上
        hideCard(true);
        return;
      }
      if (err === 'need-permission') {
        if (!warned.permission) {
          warned.permission = true;
          showMessage('需要授权', '首次使用图片取词需要在扩展弹窗中点击「启用图片/PDF 能力」授予「所有网站」权限。', info, 'tip');
        }
        return;
      }
      if (err === 'need-vision-model') {
        if (!warned.vision) {
          warned.vision = true;
          showMessage('未配置视觉模型', '图片取词需要本地视觉模型。可执行：ollama pull qwen2.5vl:3b，然后在扩展设置里填写模型名。', info, 'tip');
        }
        return;
      }
      showMessage('查询失败', err, info, 'error');
    }

    /* ---------------- 事件 ---------------- */

    function onMouseMove(ev) {
      if (stopped || !settings || !settings.enabled) return;
      var now = Date.now();
      if (now - lastMoveAt < MOVE_THROTTLE) return;
      lastMoveAt = now;

      var x = ev.clientX;
      var y = ev.clientY;

      var found = wordAtPoint(x, y);
      if (found && found.word) {
        setTarget({ key: 't:' + found.word, kind: 'text', word: found.word, x: x, y: y });
        return;
      }

      if (settings.imageOcr && settings.imageOcr.enabled) {
        var img = imageAtPoint(x, y);
        if (img) {
          var cell = Math.round(x / IMAGE_CELL) + ',' + Math.round(y / IMAGE_CELL);
          setTarget({
            key: 'i:' + img.tag + ':' + img.src + ':' + cell,
            kind: 'image',
            image: img,
            x: x,
            y: y
          });
          return;
        }
      }

      clearTarget();
    }

    function onScroll(ev) {
      if (card && card.root && ev.target && ev.target.contains && ev.target.contains(card.root)) return;
      hideCard(true);            // 卡片位置会过时，先收起
      // 但鼠标多半仍停在同一个词上（滚动时人不会挪鼠标）——重新计时，
      // 否则「滚一下就再也不弹」，与「停在词上约 5 秒必弹」的承诺相悖。
      if (current) {
        current.staleAt = Date.now();
        scheduleFire(current);
      } else {
        clearTimer();
      }
    }

    function onKeyDown(ev) {
      if (ev.key === 'Escape') {
        hideCard(true);
        clearTimer();
        current = null;
      }
    }

    function onMouseDown(ev) {
      if (card && card.host && (ev.target === card.host || card.host.contains(ev.target))) return;
      hideCard(true);
    }

    function onDocLeave() {
      scheduleHide();
    }

    function onSelectionChange() {
      try {
        var sel = doc.getSelection();
        if (sel && !sel.isCollapsed) {
          clearTimer();
          current = null;
        }
      } catch (e) { /* 忽略 */ }
    }

    /* ---------------- 生命周期 ---------------- */

    function bind() {
      doc.addEventListener('mousemove', onMouseMove, { passive: true, capture: true });
      doc.addEventListener('scroll', onScroll, { passive: true, capture: true });
      doc.addEventListener('keydown', onKeyDown, true);
      doc.addEventListener('mousedown', onMouseDown, true);
      doc.addEventListener('selectionchange', onSelectionChange, true);
      doc.documentElement.addEventListener('mouseleave', onDocLeave);
      win.addEventListener('blur', function () { scheduleHide(); });
      ES.onChange(function (next) {
        settings = next;
        if (!next.enabled) hideCard(true);
      });
    }

    function start() {
      ES.get().then(function (s) {
        settings = s;
      });
      bind();
    }

    function stop() {
      stopped = true;
      clearTimer();
      hideCard(true);
    }

    return { start: start, stop: stop, getSettings: function () { return settings; } };
  }

  root.ETHover = {
    start: function (options) {
      var engine = createEngine(options || {});
      engine.start();
      return engine;
    }
  };
})(typeof globalThis !== 'undefined' ? globalThis : self);
