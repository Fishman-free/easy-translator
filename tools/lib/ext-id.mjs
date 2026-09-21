/**
 * 从 CDP /json/list 的目标里挑出「我们自己的」扩展 ID。
 *
 * 为什么单独抽出来：这里踩过一个只在 CI 上间歇触发的坑——
 * 取「第一个 chrome-extension:// 目标」会抓到浏览器内置扩展，于是
 * chrome-extension://<内置ID>/... 全部 ERR_FILE_NOT_FOUND，
 * 表现为 popup/options/PDF 检查莫名其妙失败（而且错误页还能骗过
 * 「有 body + 无 JS 异常」这种弱断言）。
 */

/** 自己的扩展 service worker 在 CDP 目标里的 URL 形状：chrome-extension://<id>/background.js */
const OWN_SW_RE = /^chrome-extension:\/\/([a-p]+)\/background\.js$/;

/**
 * @param {Array<{url?: string}>} targets  /json/list 返回的目标数组
 * @returns {{ id: string|null, foreignCount: number, extTargetCount: number }}
 *          id            我们自己的扩展 ID（没找到时为 null）
 *          foreignCount  被忽略的**其它扩展**数量（按扩展 ID 去重，不含自己）
 *          extTargetCount 列表里 chrome-extension:// 目标总数
 */
export function pickOwnExtensionId(targets) {
  const extTargets = (targets || []).filter((t) => /^chrome-extension:\/\//.test(t.url || ''));
  const own = extTargets.find((t) => OWN_SW_RE.test(t.url || ''));
  const ownId = own ? OWN_SW_RE.exec(own.url)[1] : null;

  const otherIds = new Set();
  for (const t of extTargets) {
    const m = /^chrome-extension:\/\/([a-p]+)\//.exec(t.url || '');
    if (m && m[1] !== ownId) otherIds.add(m[1]);
  }

  return { id: ownId, foreignCount: otherIds.size, extTargetCount: extTargets.length };
}
