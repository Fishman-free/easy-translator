/**
 * Easy Translator — 扩展弹窗逻辑
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var settings = null;

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

  async function save(patch) {
    settings = await ETSettings.set(patch);
    return settings;
  }

  function render() {
    $('enabled').checked = !!settings.enabled;
    $('dwell').value = String(Math.round(settings.dwellMs / 1000));
    $('dwellVal').textContent = Math.round(settings.dwellMs / 1000) + ' 秒';
    $('engine').value = settings.engine;
    $('imageOcr').checked = !!settings.imageOcr.enabled;
    $('visionModelName').textContent = settings.model.visionModel
      ? '模型：' + settings.model.visionModel
      : '未配置视觉模型';
    $('footNote').textContent = settings.enabled ? '' : '已暂停：鼠标悬停不会触发查词';
  }

  async function refreshState() {
    var perm = await send({ type: 'permission-state' });
    var granted = !!(perm && perm.allUrls);
    $('permCard').classList.toggle('hidden', granted);

    var stats = await send({ type: 'cache-stats' });
    $('cacheInfo').textContent = '缓存词条：' + ((stats && stats.entries) || 0);

    var pdf = await send({ type: 'pdf-state' });
    $('pdfCard').classList.toggle('hidden', !(pdf && pdf.isPdf));

    if (!settings.model.enabled && settings.engine === 'local') {
      $('footNote').textContent = '注意：未启用小模型，本地模式无法查词';
      $('footNote').className = 'foot';
    }
  }

  function bind() {
    $('enabled').addEventListener('change', async function (ev) {
      await save({ enabled: ev.target.checked });
      render();
    });

    $('dwell').addEventListener('input', function (ev) {
      $('dwellVal').textContent = ev.target.value + ' 秒';
    });
    $('dwell').addEventListener('change', async function (ev) {
      await save({ dwellMs: Number(ev.target.value) * 1000 });
    });

    $('engine').addEventListener('change', async function (ev) {
      await save({ engine: ev.target.value });
      refreshState();
    });

    $('imageOcr').addEventListener('change', async function (ev) {
      await save({ imageOcr: { enabled: ev.target.checked } });
      if (ev.target.checked) {
        var perm = await send({ type: 'permission-state' });
        if (!(perm && perm.allUrls)) await requestPermission();
      }
      refreshState();
    });

    $('grant').addEventListener('click', async function () {
      await requestPermission();
      refreshState();
    });

    $('openPdf').addEventListener('click', async function () {
      await send({ type: 'open-pdf-viewer' });
      window.close();
    });

    $('clearCache').addEventListener('click', async function () {
      var res = await send({ type: 'clear-cache' });
      $('footNote').className = 'foot ok';
      $('footNote').textContent = '已清空 ' + ((res && res.cleared) || 0) + ' 条缓存';
      refreshState();
    });

    $('openOptions').addEventListener('click', function (ev) {
      ev.preventDefault();
      chrome.runtime.openOptionsPage();
    });
  }

  async function requestPermission() {
    try {
      var granted = await chrome.permissions.request({ origins: ['<all_urls>'] });
      $('footNote').className = granted ? 'foot ok' : 'foot';
      $('footNote').textContent = granted ? '已授权：图片取词与 PDF 增强可用' : '未授权';
      return granted;
    } catch (e) {
      $('footNote').textContent = '授权失败：' + e.message;
      return false;
    }
  }

  ETSettings.get().then(function (s) {
    settings = s;
    render();
    bind();
    refreshState();
  });
})();
