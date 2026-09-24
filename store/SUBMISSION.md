# Microsoft Edge 商店上架清单（Partner Center）

本文把能在本地准备好的**全部内容**都写好了：你只需要登录 Partner Center、上传 `store/easy-translator-1.0.0.zip`、把下面标注「复制」的文本贴进去。

---

## ⚠ 提交前必填项速查（缺任何一项，Submit/Publish 都会被拦住）

| 位置 | 字段 | 值 / 文件 | 类别 |
|---|---|---|---|
| Store listing | **Extension logo** | `store/logo-300.png`（300×300，1:1） | **必填（每种语言各一份）** |
| Store listing | **Description** | 本文第 6 步的中/英文案（**≥250 字符**，短了报错） | **必填（每种语言各一份）** |
| Privacy | Single Purpose Description | 见 5.1 | **必填** |
| Privacy | 每个权限的理由（共 8 项：storage / activeTab / webRequest / **notifications**（v1.0.11 新增） / declarativeNetRequestWithHostAccess / dict.youdao.com / 127.0.0.1+localhost / 可选 &lt;all_urls&gt;） | 见 5.2 | **必填（逐项）** |
| Privacy | Remote code | 选「不使用远程代码」 | **必填** |
| Privacy | Data usage | 勾选「不收集用户数据」 | **必填** |
| Privacy | Privacy policy URL | `https://github.com/Fishman-free/easy-translator/blob/main/PRIVACY.md` | **必填** |
| Properties | Category / Support contact info | Productivity / 你的邮箱 | **必填** |
| Availability | Visibility / Markets | Public / 全部市场 | **必填** |
| Certification notes | 审核测试说明 | 见第 7 步 | **必填** |
| Store listing | 宣传图、截图、搜索词、YouTube | `store/tile-*.png`、`store/screenshots/*.png` | 可选（建议传，利于转化） |

> 常见误会：**商店列表的图标（Extension logo）与包里的 `icons/` 是两回事**。
> 包里的 `icons/` 决定浏览器工具栏图标（已随包上传）；商店页显示的是 Extension logo，
> 必须单独在该语言下上传 `store/logo-300.png`——**它是必填，不传就发不出去**。

---

## 已登记的商店信息（2026-09-21 首次提交）

| 项 | 值 |
|---|---|
| 商店标识（Store ID） | `0RDCKDQS06GH` |
| CRX ID（扩展 ID） | `lnnglikclimokbdcgnpjelpigopdkjeb` |
| 产品 ID（Product ID） | `3965e488-3125-4e63-9a4c-ba326de5e00c` |
| 公钥 | 见 Partner Center「Package」页；已校验：`SHA-256(公钥)` 前 16 字节推导出的 ID 与该 CRX ID **完全一致** |

> 该 CRX ID 一旦发布即固定，**更新时必须沿用**。若希望「本地开发者模式加载的副本」
> 与商店版本使用同一个 ID（便于对照测试），可把 Partner Center 给的公钥加进
> `manifest.json` 的 `"key"` 字段后重新打包上传（本仓库当前未加，因此本地加载的 ID
> 是按路径推导的另一串字符，属正常现象）。

---

## 第 0 步：注册开发者账号（一次性，免费）

1. 打开 **Partner Center** → <https://partner.microsoft.com/dashboard/microsoftedge/>
2. 用你的 Microsoft 账号登录（就是 `Fishman-free` 对应的那个账号）
3. 选择 **Register now** → 注册 **Microsoft Edge program**
4. 按提示填写：国家/地区、开发者名称（会显示为**发布者名称**，建议填 `Fishman-free`）、联系邮箱
5. Edge 扩展的注册**免费**（不同于 Chrome 商店的 5 美元）
6. 等待账号审核通过（通常 1–2 个工作日；通过后即可提交扩展）

> 需要准备的：Microsoft 账号、可收信的邮箱、开发者显示名。
> 只有你能做这一步——它绑定你的账号与身份。

---

## 第 1 步：打包

```bash
npm run build:store            # 生成 store/easy-translator-<version>.zip
npm run build:store -- --smoke # 额外把「解压后的这份包」真机跑一遍端到端
```

自检会确认：manifest 在包根目录、引用的文件齐全、**未混入** tools/tests/docs/.github/package.json、
条目名使用正斜杠（PowerShell 的 `Compress-Archive` 会写成反斜杠，导致商店报「找不到清单」）、版本号写入包名。

---

## 第 2 步：新建扩展 → 上传包

1. Partner Center → **Microsoft Edge** → **New extension**
2. 上传 `store/easy-translator-1.0.0.zip`
3. 包里的 `manifest.json` 会自动带出**扩展名称**与**简短描述**（就是商店列表顶部那两行），
   改了之后需要**重新打包上传**

---

## 第 3 步：可用性（Availability）

| 字段 | 建议填写 |
|---|---|
| Visibility | Public（公开） |
| Markets | 全部市场（或按需排除） |

---

## 第 4 步：属性（Properties）

| 字段 | 建议填写 |
|---|---|
| Category | **Productivity**（生产力） |
| Support contact info | 你的邮箱（建议填一个能长期收信的） |
| Website（可选） | `https://github.com/Fishman-free/easy-translator` |
| Mature content | No |

---

## 第 5 步：隐私信息（Privacy）—— 审核最容易卡的地方

官方强调：这里的内容必须**与扩展真实行为一致**，否则可能被拒。以下文本是按本扩展的实际行为写的。

### 5.1 Single Purpose Description（单一用途）

> **复制：**
> 在浏览英文网页、PDF 和图片时，鼠标悬停英文单词即可查看中文释义、音标、词性与例句。

### 5.2 权限说明（逐个权限填写理由）

> **storage**
> 在本机保存用户设置（触发时长、引擎选择）与查词缓存，用于加速重复查询。不离开用户设备。

> **activeTab**
> 仅当用户点击扩展图标时，读取当前标签页地址，用于判断是否为 PDF 并提供「用内置阅读器打开」按钮。

> **webRequest**
> 以只读方式观察主文档响应头中的 Content-Type，用于识别页面是否为 PDF（在扩展图标上显示 PDF 标记）。不修改、不阻断、不记录任何请求。

> **declarativeNetRequestWithHostAccess**
> 仅对本扩展自身发往 127.0.0.1 / localhost 的请求移除 Origin 请求头，以便访问用户本机运行的 Ollama 模型服务（该服务默认拒绝浏览器扩展来源）。规则通过 initiatorDomains 限定为本扩展，不影响任何网页自身的请求。

> **主机权限 dict.youdao.com**
> 调用有道公开词典接口查询被悬停英文单词的中文释义。请求中只包含该单词本身，不包含页面内容或浏览记录。

> **主机权限 127.0.0.1 / localhost（可选，需用户授权）**
> 访问用户本机运行的 OpenAI 兼容模型服务（默认 Ollama）。仅在用户启用本地小模型时使用。

> **可选权限 &lt;all_urls&gt;（需用户在扩展弹窗中点击「授权」）**
> ① 图片取词：截取屏幕中鼠标周边的小块区域交给本机模型识别英文单词；
> ② 内置 PDF 阅读器：读取用户打开的 PDF 链接并渲染文本层，以便在 PDF 中悬停取词。
> 未授权时，网页文本取词与在线词典功能完全正常。

#### 5.2 补充 · notifications（**v1.0.11 新增**，逐字复制进 Partner Center 的权限理由框）

> **notifications**：仅用于「检测到 PDF 时，提醒你可以把它切换到内置增强阅读器」这一件事。
> 通知的标题与正文都是**固定文案**，不含任何用户数据；点击通知或其按钮只是把当前 PDF 标签页
> 切换到内置阅读器。该提醒**每个标签页只出现一次**，且可在设置里关闭（`pdf.prompt`）。
> **不用于**推送、营销、更新提醒或任何其它用途。

> 权限变更提示：这一版（1.0.11）相对 1.0.10 只新增 `notifications` 一个权限，
> 其余权限与用途完全不变。若 Partner Center 在更新表单里重新索要全部权限理由，
> 仍可整段复制 5.2 原有内容 + 本条。

### 5.3 Remote code（远程代码）

> **选择：不使用远程代码（No, I am not using remote code）**
> 所有 JavaScript 均随扩展包分发；本地 `pdfjs/` 为 pdf.js 官方构建产物，非远程加载。

### 5.4 数据使用（Data usage）

> 勾选「不收集用户数据」相关选项。补充说明（如有文本框）：
> **复制：** 本扩展不收集、不存储、不出售任何用户数据，不包含遥测与广告。查词时仅将用户悬停的英文单词本身发送至公开词典接口；图片取词时的裁剪图仅发送至用户本机的模型服务。

### 5.5 Privacy policy URL

> **复制（本仓库内的隐私声明，公开可访问）：**
> https://github.com/Fishman-free/easy-translator/blob/main/PRIVACY.md

---

## 第 6 步：商店列表（Store listing）

需要为每种语言分别填写。建议至少填 **中文（简体）** 与 **English (United States)**。

### 6.1 中文（简体）

> **详细描述（复制，≥250 字符）：**
> 鼠标在英文单词上停留约 5 秒，即可弹出释义卡片：中文释义、英美音标、词性、双语例句，并可一键朗读。
>
> 核心设计原则：识别不到英文就绝不弹窗。中文、数字、空白、乱码一律静默，不打断你的阅读。
>
> 支持的取词场景
> • 网页文本：精确到字符的取词，微动不打断、词间空白不触发
> • PDF：内置基于 pdf.js 的阅读器（Edge 自带的 PDF 阅读器是封闭页面，任何扩展都无法注入）；检测到 PDF 会发一条通知，点「用增强阅读器打开」即可切换
> • 图片中的文字：截屏裁剪光标周边区域，交由本机视觉模型识别，识别不到英文则不显示任何弹窗
>
> 双引擎
> • 在线词典：免 API Key、国内直连，零配置开箱即用
> • 本地小模型：兼容任何 OpenAI 兼容端点（默认 Ollama），可完全离线、隐私优先；支持一键预热模型
>
> 轻量与隐私
> • 无构建、无依赖、无框架，扩展本体不到 100 KB
> • 查词结果只缓存在本机，可一键清空
> • 无账号、无遥测、无广告；图片识别全程在本机模型完成，不外传
>
> 适用人群：备考、读论文、看英文文档、日常浏览外文网站的学习者。

> **搜索词（复制）：** 翻译 词典 划词 悬停查词 英文 单词 释义 音标 例句 学习 英汉词典 阅读辅助

### 6.2 English (en-US)

> **Detailed description (copy, ≥250 chars):**
> Hover over an English word for about five seconds and a card appears with its Chinese definition, UK/US phonetics, part of speech, bilingual example sentences, and pronunciation.
>
> Design principle: if it is not English, nothing pops up. Chinese text, numbers, blank areas, and unrecognized content stay silent, so your reading is never interrupted.
>
> Where it works
> • Web pages: character-accurate word detection; small mouse movements do not reset the timer, and the gaps between words never trigger a popup
> • PDFs: a built-in pdf.js reader, because the browser's native PDF viewer is a closed surface that no extension can reach
> • Text inside images: a small region around the cursor is captured and sent to a local vision model; if no English word is recognized, nothing is shown
>
> Two engines
> • Online dictionary: no API key, works out of the box
> • Local small model: any OpenAI-compatible endpoint (Ollama by default) for fully offline, privacy-first lookups, with a one-click model warm-up
>
> Lightweight and private
> • Zero build step, zero dependencies, under 100 KB; the PDF reader bundles the pdf.js runtime
> • Lookup results are cached only on your machine and can be cleared at any time
> • No account, no telemetry, no ads; image recognition runs entirely on your local model
>
> For learners reading papers, documentation, and foreign-language websites.

> **Search terms (copy):** translate dictionary hover word lookup english chinese reading vocabulary phonetics

---

## 第 7 步：认证测试说明（Certification notes）—— 给审核员看

> **复制：**
> Thank you for reviewing. Quick test guide:
>
> 1. Install the extension. No configuration is required. Hover the cursor over any English word on any web page (for example https://en.wikipedia.org/wiki/Serendipity) and hold it still for about 5 seconds. A card with the Chinese definition, phonetics, part of speech, and example sentences appears. Move the mouse away or press Esc to dismiss it.
> 2. Chinese text, numbers, and blank areas intentionally do NOT trigger anything — this is by design, please verify it does not pop up there.
> 3. PDF: navigate to any .pdf URL, click the extension icon, and choose "用增强阅读器打开 / Open in enhanced reader" to use the built-in pdf.js reader, where the same hover behavior works.
> 4. Image OCR is an optional feature that requires the optional <all_urls> permission, granted by clicking "授权 / Grant" in the extension popup. It is NOT required for the main functionality — please review and use the extension without granting it. If you do grant it: hover over an image containing English text for ~1.5s. It sends a crop around the cursor to a LOCAL model endpoint (127.0.0.1, Ollama) which is not running during review, so this feature will simply show nothing; the code path is inert without a local model.
> 5. Network use: hovering a word sends only that single word to the public dictionary endpoint https://dict.youdao.com/jsonapi to fetch its Chinese definition. No page content, URLs, or browsing history are transmitted. There is no remote code, no analytics, and no account system.
> 6. The default engine works without any local service, so the extension is fully testable in a clean environment.

---

## 第 8 步：提交与审核

1. 检查无误后点击 **Publish**（提交审核）
2. 审核通常 **1–7 个工作日**；期间状态可在 Partner Center 查看
3. 被拒时 Partner Center 会给出具体条款与理由，按提示修改后重新提交即可

### 常见被拒原因与我们的预防措施

| 常见问题 | 本项目的处理 |
|---|---|
| 清单文件路径/结构错误 | 自建 ZIP 写入器，条目名用正斜杠；`npm run build:store` 有结构自检 |
| 权限与功能不匹配 | 每个权限都在隐私页写明用途；重权限（截屏/跨站读取）走**可选权限**，默认不索取 |
| 存在远程代码 | 全程本地打包，无远程脚本；pdf.js 为随包分发的官方构建 |
| 隐私声明与实际行为不一致 | `PRIVACY.md` 与代码行为逐条对应；数据使用勾选「不收集」 |
| 描述与实际功能不符 | 描述只写已实现的功能，并如实说明图片取词需本地模型 |

---

## 素材规格（官方硬性要求）

| 素材 | 要求 | 本项目文件 |
|---|---|---|
| 扩展名称 | ≤ 45 字符，来自 manifest `name` | `Easy Translator — 悬停查词` |
| 简短描述 | 来自 manifest `description` | 见 `manifest.json` |
| 详细描述 | 每种语言 ≥ 250 字符（上限 10,000） | 见本文第 6 步 |
| 扩展图标 | 1:1，推荐 **300×300**，最小 128×128 | `store/logo-300.png` |
| 小宣传图（可选） | **440×280** | `store/tile-440x280.png` |
| 大宣传图（可选） | **1400×560** PNG | `store/tile-1400x560.png` |
| 截图（可选，最多 6） | **1280×800** 或 640×480 | `store/screenshots/1-web.png`、`2-pdf.png`、`3-settings.png` |
| 隐私政策 URL | 公开可访问 | `PRIVACY.md` 的 GitHub 链接 |

重新生成素材：

```bash
python tools/make-store-assets.py    # 图标 + 宣传图
npm run store:screenshots            # 三张 1280x800 截图（会校验真实尺寸，不达标直接失败）
```

---

## 上架之后

- 每次发版：改 `manifest.json` 的 `version` → `npm run build:store -- --smoke` → 在 Partner Center 上传新包
- 商店页链接形如 `https://microsoftedge.microsoft.com/addons/detail/<id>`，拿到后可补进 README
- 更新审核通常比首次快；涉及权限变更会被重新审核
