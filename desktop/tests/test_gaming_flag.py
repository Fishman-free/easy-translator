"""打游戏时整条取词链停工的判据（游戏标记文件）。

游戏守护检测到游戏后写 gaming.flag，取词守护读到就**完全停工**：
不查 UIA（单次走控件树约 500ms，而轮询是 60ms 一次 —— 这才是游戏期间的主要开销）、
不打 OCR（还会把视觉模型拉回显存抢显卡）、不弹卡片。

标记查两条路径：环境变量 ET_GAMING_FLAG（start_daemon.vbs 会设）与守护目录旁的
gaming.flag（兜底：手动启动、自愈重启时也能生效）。

跑：python -m pytest tests/test_gaming_flag.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from et_desktop import textgrab as TG          # noqa: E402


def _isolate(monkeypatch, tmp_path):
    """把两条标记路径都指到临时目录，避免被本机真实标记干扰。"""
    monkeypatch.delenv("ET_GAMING_FLAG", raising=False)
    monkeypatch.setattr(TG, "GAMING_FLAG", None)
    monkeypatch.setattr(TG, "GAMING_FLAG_LOCAL", str(tmp_path / "gaming.flag"))


def test_no_flag_means_not_gaming(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert TG.gaming_now() is False


def test_local_flag_means_gaming(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "gaming.flag").write_text("1", encoding="utf-8")
    assert TG.gaming_now() is True


def test_env_var_flag_means_gaming(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    p = tmp_path / "from_env.flag"
    p.write_text("1", encoding="utf-8")
    monkeypatch.setenv("ET_GAMING_FLAG", str(p))
    assert TG.gaming_now() is True


def test_flag_removed_resumes(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    p = tmp_path / "gaming.flag"
    p.write_text("1", encoding="utf-8")
    assert TG.gaming_now() is True
    p.unlink()
    assert TG.gaming_now() is False


def test_bad_paths_never_raise(monkeypatch, tmp_path):
    # 每 60ms 被调用一次，任何异常都会让取词守护带病运行 → 必须永不抛
    monkeypatch.delenv("ET_GAMING_FLAG", raising=False)
    monkeypatch.setattr(TG, "GAMING_FLAG", "")
    monkeypatch.setattr(TG, "GAMING_FLAG_LOCAL", None)
    assert TG.gaming_now() is False
    monkeypatch.setattr(TG, "GAMING_FLAG_LOCAL", "\x00bad\x00path")
    assert TG.gaming_now() in (True, False)      # 只要求不抛
