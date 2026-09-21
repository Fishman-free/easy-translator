/**
 * Easy Translator — 设置页逻辑
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var settings = null;
  var saveTimer = null;

  function send(payload) {
    return new Promise(function (resolve) {
      chrome.runtime.sendMessage(payload, function (res) {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(res || { ok: false, error: '无响应' });
      });
    });
  }

  function render() {
    $('dwell').value = String(Math.round(settings.dwellMs / 1000));
    $('dwellVal').textContent = Math.round(settings.dwellMs / 1000) + ' 秒';
    $('examplesCount').value = String(settings.examplesCount);
    $('showSpeak').checked = !!settings.showSpeak;

    $('modelEnabled').checked = !!settings.model.enabled;
    $('baseUrl').value = settings.model.baseUrl;
    $('apiKey').value = settings.model.apiKey || '';
    $('textModel').value = settings.model.textModel;
    $('visionModel').value = settings.model.visionModel || '';
    $('timeoutMs').value = String(settings.model.timeoutMs);

    $('ocrEnabled').checked = !!settings.imageOcr.enabled;
    $('ocrDwell').value = String(settings.imageOcr.dwellMs);
    $('ocrDwellVal').textContent = (settings.imageOcr.dwellMs / 1000).toFixed(1) + ' 秒';
    $('cropW').value = String(settings.imageOcr.cropW);
    $('cropH').value = String(settings.imageOcr.cropH);
    $('ocrHint').checked = !!settings.imageOcr.hint;

    $('pdfAutoOpen').checked = !!settings.pdf.autoOpen;
  }

  async function refreshCache() {
    var stats = await send({ type: 'cache-stats' });
    $('cacheInfo').textContent = '缓存词条：' + ((stats && stats.entries) || 0);
  }

  function setResult(id, text, cls) {
    var node = $(id);
    node.textContent = text;
    node.className = 'result' + (cls ? ' ' + cls : '');
  }

  async function save(patch) {
    settings = await ETSettings.set(patch);
  }

  function saveSoon(patch, ms) {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { save(patch); }, ms || 400);
  }

  function bind() {
    $('dwell').addEventListener('input', function (ev) {
      $('dwellVal').textContent = ev.target.value + ' 秒';
    });
    $('dwell').addEventListener('change', function (ev) {
      save({ dwellMs: Number(ev.target.value) * 1000 });
    });

    $('examplesCount').addEventListener('change', function (ev) {
      save({ examplesCount: Number(ev.target.value) });
    });
    $('showSpeak').addEventListener('change', function (ev) {
      save({ showSpeak: ev.target.checked });
    });

    $('modelEnabled').addEventListener('change', function (ev) {
      save({ model: { enabled: ev.target.checked } });
    });
    $('baseUrl').addEventListener('input', function (ev) {
      saveSoon({ model: { baseUrl: ev.target.value } });
    });
    $('apiKey').addEventListener('input', function (ev) {
      saveSoon({ model: { apiKey: ev.target.value } });
    });
    $('textModel').addEventListener('input', function (ev) {
      saveSoon({ model: { textModel: ev.target.value } });
    });
    $('visionModel').addEventListener('input', function (ev) {
      saveSoon({ model: { visionModel: ev.target.value } });
    });
    $('timeoutMs').addEventListener('change', function (ev) {
      save({ model: { timeoutMs: Number(ev.target.value) } });
    });

    $('ocrEnabled').addEventListener('change', function (ev) {
      save({ imageOcr: { enabled: ev.target.checked } });
    });
    $('ocrDwell').addEventListener('input', function (ev) {
      $('ocrDwellVal').textContent = (Number(ev.target.value) / 1000).toFixed(1) + ' 秒';
    });
    $('ocrDwell').addEventListener('change', function (ev) {
      save({ imageOcr: { dwellMs: Number(ev.target.value) } });
    });
    $('cropW').addEventListener('change', function (ev) {
      save({ imageOcr: { cropW: Number(ev.target.value) } });
    });
    $('cropH').addEventListener('change', function (ev) {
      save({ imageOcr: { cropH: Number(ev.target.value) } });
    });
    $('ocrHint').addEventListener('change', function (ev) {
      save({ imageOcr: { hint: ev.target.checked } });
    });

    $('pdfAutoOpen').addEventListener('change', function (ev) {
      save({ pdf: { autoOpen: ev.target.checked } });
    });

    $('testText').addEventListener('click', async function () {
      setResult('modelResult', '查询中…');
      var res = await send({ type: 'test-text-model', word: 'serendipity' });
      if (!res || !res.ok) {
        setResult('modelResult', '失败：' + ((res && res.error) || '未知错误'), 'err');
        return;
      }
      var d = res.data || {};
      var first = (d.poses && d.poses[0] && d.poses[0].meaning) || '（无释义）';
      setResult('modelResult', '成功 ' + res.elapsed + 'ms · ' + first.slice(0, 40), 'ok');
    });

    $('testVision').addEventListener('click', async function () {
      setResult('modelResult', '识别中…');
      var res = await send({ type: 'test-vision-model' });
      if (!res || !res.ok) {
        setResult('modelResult', '失败：' + ((res && res.error) || '未知错误'), 'err');
        return;
      }
      var got = res.recognized ? '识别到「' + res.recognized + '」' : '未识别到英文';
      setResult('modelResult', '成功 ' + res.elapsed + 'ms · ' + got, 'ok');
    });

    $('warmup').addEventListener('click', async function () {
      setResult('modelResult', '正在加载模型（首次可能 1–3 分钟）…');
      var res = await send({ type: 'warmup-model' });
      if (!res || !res.ok) {
        setResult('modelResult', '失败：' + ((res && res.error) || '未知错误'), 'err');
        return;
      }
      setResult('modelResult', '模型已就绪 · 耗时 ' + Math.round(res.elapsed / 1000) + ' 秒', 'ok');
    });

    $('clearCache').addEventListener('click', async function () {
      var res = await send({ type: 'clear-cache' });
      await refreshCache();
      setResult('cacheInfo', '已清空 ' + ((res && res.cleared) || 0) + ' 条', 'ok');
      setTimeout(refreshCache, 1500);
    });

    $('reset').addEventListener('click', async function () {
      settings = await ETSettings.set(Object.assign({}, ETSettings.DEFAULTS));
      render();
      setResult('cacheInfo', '已恢复默认设置', 'ok');
    });
  }

  ETSettings.get().then(function (s) {
    settings = s;
    render();
    bind();
    refreshCache();
  });
})();
