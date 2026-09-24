# Easy Translator · 桌面伴生

把「鼠标停在英文上约 5 秒 → 弹出中文释义」从浏览器**扩展到整台电脑**：
记事本、Word、微信、VS Code、PDF 阅读器……任何应用里的英文都能查。
UI 与浏览器扩展同一套设计语言：**白底气泡 + 藏青描边 + 右下角的鲸鱼娘**，
所有释义都装在她的对话气泡里。

## 一步步来（从零开始）

### ① 先把代码放到电脑上

```powershell
cd ~
git clone https://github.com/Fishman-free/easy-translator.git
```

没有 git 也行：在 GitHub 页面点 **Code → Download ZIP**，解压到任意目录。

下面命令里的 `<项目目录>` 都指**你放这份代码的文件夹**，本机示例：

```
C:\Users\21560\Desktop\Easy-translator
```

### ② 启动

**推荐用绝对路径**——不管你现在在哪个目录都能跑对（最不容易出错）：

```powershell
powershell -ExecutionPolicy Bypass -File "<项目目录>\desktop\run.ps1"
```

或者先切进项目目录、再用相对路径：

```powershell
cd "<项目目录>"
powershell -ExecutionPolicy Bypass -File .\desktop\run.ps1
```

首次运行会自动建 `.venv` 并装依赖（Pillow / uiautomation），约需一两分钟；
跑完会打开**设置窗口**并开始监听鼠标。

> ### ⚠️ 最常见的坑（真实案例，一定要看）
>
> ```text
> PS C:\Users\21560> cd ~/desktop
> PS C:\Users\21560\desktop> powershell -ExecutionPolicy Bypass -File desktop\run.ps1
> -File 形式参数的实际参数"desktop\run.ps1"不存在。请提供现有".ps1"文件的路径……
> ```
>
> **原因**：`~/desktop` 是 **Windows 桌面**（`C:\Users\21560\Desktop`），**不是**项目里的
> `desktop` 子目录。此时 `desktop\run.ps1` 被拼成 `C:\Users\21560\Desktop\desktop\run.ps1`
> —— 那儿当然没有这个文件。
>
> **记住两件事**：
> 1. **`Desktop`（大写，你的桌面）≠ 项目里的 `desktop`（小写，子目录）**，别混；
> 2. 直接用 ② 的**绝对路径**写法，无论当前在哪个目录都不会错。

其它两种启动方式：

```powershell
powershell -ExecutionPolicy Bypass -File "<项目目录>\desktop\run.ps1" --settings  # 只改设置、不监听
powershell -ExecutionPolicy Bypass -File "<项目目录>\desktop\run.ps1" --selftest  # 只跑自检后退出
```

### ③ 设置（第一次用建议做这三件事）

启动后弹出的**设置窗口就是这个程序的主界面**，四张卡：

| 卡 | 第一次要做什么 |
|---|---|
| **通用** | 调「**悬停触发时长**」（默认 5 秒）——鼠标在英文上停多久弹卡片；嫌慢就调小 |
| **本地小模型** | *可选*。想用本地模型查词就填端点（默认 Ollama `http://127.0.0.1:11434/v1`），填完点「测试」当场验证 |
| **图片取词** | *可选*。给图片/游戏这类取不到文字的地方用；需要本地视觉模型在跑（没配就静默，不会乱弹） |
| **数据** | 看配置存在哪：`%APPDATA%\EasyTranslator\config.json` |

- 改完**立即生效并自动保存**，不用重启；
- 窗口里还有「**测试文本查词**」按钮，可当场确认引擎通不通；
- 顶部状态行可以**启用/暂停**取词；**底部有「退出桌面取词」按钮**。

### ④ 关闭

三种方式任选：

```powershell
powershell -ExecutionPolicy Bypass -File "<项目目录>\desktop\stop.ps1"   # 命令行（与 run.ps1 对称）
```

| 方式 | 操作 |
|---|---|
| **界面**（最简单） | 设置窗口**底部**的「**退出桌面取词**」按钮，点一下即退出整个进程 |
| **命令行** | `powershell -ExecutionPolicy Bypass -File "<项目目录>\desktop\stop.ps1"` |
| **任务管理器** | 结束 `python` 进程（或 `Stop-Process -Id <PID> -Force`） |

`stop.ps1` 会按 `python -m et_desktop` 找到进程 → 结束 → **二次确认无残留**后才报成功。

### ⑤ 再打开

重复 ② 即可（配置还在，不用重设）。

鼠标停在任意英文单词上达到设定秒数即弹出气泡；移入气泡可钉住，点击复制该词，移开即收起。

## 取词是怎么做到的（优先级与产品铁律）

| 层级 | 手段 | 覆盖 |
|---|---|---|
| ① | **UIA**（Windows 辅助功能 `TextPattern.RangeFromPoint` + `ExpandToEnclosingUnit(Word)`） | 浏览器、记事本、Office、Electron 系（VS Code / 微信 / Discord）等绝大多数应用 |
| ② | **有文字但不是英文 → 就此静默** | 中文、数字、标点上**绝不弹窗**（产品铁律，E2E 钉住） |
| ③ | **视觉模型 OCR 兜底**（本地 Ollama 之类） | 图片、游戏、自绘 UI 等辅助功能拿不到文字的地方 |

②③ 的先后是刻意的：辅助功能说「这里是中文」时就信它、静默；
只有**根本没有文字**才截图去认 —— 否则截图块会把邻行的英文收进来，出现「指中文却弹英文」。

## 引擎

- **有道公开词典**（默认，免 key，一次拿全音标/词性/例句/词形）
- **本地小模型**（任何 OpenAI 兼容端点，默认 Ollama `http://127.0.0.1:11434/v1` + `qwen2.5:1.5b`）
- 视觉兜底默认 `qwen2.5vl:3b`（可关）

配置存 `%APPDATA%\EasyTranslator\config.json`，字段名与扩展的 `lib/settings-core.js` 一致
（`dwellMs`、`examplesCount`、`model.*`、`imageOcr.*`）；老配置的 `dwell`/`showExamples`
读到会自动迁移（秒 → 毫秒）。`tests/test_settings.py` 拿 JS 侧逐键比对防漂移。

## 测试

```powershell
cd desktop
python tests\test_lookup.py      # 纯函数单测（英文判定 / 取词边界 / 归一化）
python tests\test_parity.py      # 与浏览器扩展 lib/normalize.js 逐字段同构性（防两边跑偏）
python -m et_desktop --selftest  # 渲染 + 取词 + 引擎连通
python tools\e2e_desktop.py      # 真机 E2E：起真实 Notepad → 悬停 → 断言（10 项）
```

`test_parity.py` 值得单说：它用 node 跑**浏览器扩展那份 `lib/normalize.js`**，
把输出与 Python 实现逐字段比对。桌面端不是重写一遍逻辑，而是**同一份契约的第二实现**，
任何一边改了口径，这条测试立刻变红。

## 已知边界

- UIA 取词依赖应用提供 `TextPattern`；少数自绘 UI（老式 Java 程序、部分游戏）拿不到 → 交给 OCR 兜底
- OCR 兜底需要本地视觉模型在跑；没有就**静默**（不猜、不硬凑）
- 高 DPI 下已做感知（渲染随 DPI 缩放）；多显示器以物理坐标为准

## 隐私

与浏览器扩展一致：不收集、不上传任何数据。查词直接请求有道公开词典或你自己的本地模型端点，
截图只在 OCR 兜底时截取光标附近一小块、**只发给你配置的那个端点**，不落盘。
