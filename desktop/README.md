# Easy Translator · 桌面伴生

把「鼠标停在英文上约 5 秒 → 弹出中文释义」从浏览器**扩展到整台电脑**：
记事本、Word、微信、VS Code、PDF 阅读器……任何应用里的英文都能查。
UI 与浏览器扩展同一套设计语言：**白底气泡 + 藏青描边 + 两颗尾点 + 右下角的鲸鱼娘**，
所有释义都装在她的对话气泡里。

## 用法

```powershell
# 首次运行会自动建 .venv 并装依赖（Pillow / uiautomation）
powershell -ExecutionPolicy Bypass -File run.ps1            # 启动（带控制面板）
powershell -ExecutionPolicy Bypass -File run.ps1 --selftest # 只跑自检
```

控制面板：启用/停用、驻留秒数（2–10 秒可调）、退出。
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

配置存 `%APPDATA%\EasyTranslator\config.json`。

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
