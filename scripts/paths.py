#!/usr/bin/env python3
"""统一路径与解释器解析——本包不假设安装位置，也不假设 python 在哪。

设计原则（改脚本前先读这一段）：
1. 所有包内路径一律从本文件的 `__file__` 推出。**不要**写 `Path.home()/...`、
   不要写 `/Users/xxx`、不要写 `~/.workbuddy/skills/xxx`——别人把包放在任何目录都得能跑。
2. 解释器不写死。优先用包内 `.venv`（由 `bootstrap_env.py` 建），其次外部指定
   （环境变量 `FREDGAO_PY`）、当前解释器、PATH 上的 python3，**按依赖是否齐全挑**。
3. 依赖（上游渲染器 / 配音脚本）是包内 `vendor/` 的副本，不是兄弟 skill。
   上游包没装也能跑。

作为模块用：
    from paths import PKG_ROOT, render_python, tts_python, RENDER_SCRIPT
命令行用（打印所有路径，排障时最快）：
    python3 scripts/paths.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- 包内路径
PKG_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PKG_ROOT / "scripts"
VENDOR = PKG_ROOT / "vendor"

# 上游白板渲染器（srt-whiteboard-animation 的脚本副本）
RENDER_DIR = VENDOR / "whiteboard-renderer"
RENDER_SCRIPT = RENDER_DIR / "scripts" / "render_stream_whiteboard.py"
MERGE_SCRIPT = RENDER_DIR / "scripts" / "merge_scenes.py"
PARSE_SRT_SCRIPT = RENDER_DIR / "scripts" / "parse_srt.py"
DRAWING_HAND = RENDER_DIR / "assets" / "drawing-hand.png"

# 配音（fredgao-text-to-speech 的脚本副本）
TTS_DIR = VENDOR / "text-to-speech"
TTS_SCRIPT = TTS_DIR / "scripts" / "tts.py"
CHECK_VOICES = TTS_DIR / "scripts" / "check_voices.py"

# 包内虚拟环境
VENV = PKG_ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQUIREMENTS = PKG_ROOT / "requirements.txt"

RENDER_MODULES = ["cv2", "numpy", "av", "PIL"]
TTS_MODULES = ["edge_tts"]


# ---------------------------------------------------------------- 解释器
def _importable(py: str | Path, modules: list[str]) -> bool:
    """这个解释器能不能 import 全部模块。跑子进程，慢但可靠。"""
    py = str(py)
    if not (Path(py).exists() or shutil.which(py)):
        return False
    code = "import " + ", ".join(modules)
    try:
        p = subprocess.run([py, "-c", code], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


def _candidates() -> list[str]:
    """解释器候选，按优先级。去重但保序。"""
    cand: list[str] = []
    env = os.environ.get("FREDGAO_PY")
    if env:
        cand.append(env)
    cand.append(str(VENV_PY))
    cand.append(sys.executable)
    for name in ("python3.13", "python3.12", "python3.11", "python3", "python"):
        w = shutil.which(name)
        if w:
            cand.append(w)
    seen: set[str] = set()
    out: list[str] = []
    for c in cand:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def pick_python(modules: list[str], fallback: str | None = None) -> str:
    """按模块齐全度挑解释器；都不齐全则返回 fallback（默认当前解释器）。"""
    for py in _candidates():
        if _importable(py, modules):
            return py
    return fallback or sys.executable


def render_python() -> str:
    """跑渲染/后处理脚本的解释器（要 opencv/numpy/av/Pillow）。"""
    return pick_python(RENDER_MODULES)


def tts_python() -> str:
    """跑配音脚本的解释器（要 edge-tts）。"""
    return pick_python(TTS_MODULES)


def has_render_deps(py: str | Path | None = None) -> bool:
    return _importable(py or render_python(), RENDER_MODULES)


def has_tts_deps(py: str | Path | None = None) -> bool:
    return _importable(py or tts_python(), TTS_MODULES)


def require(path: Path, what: str, hint: str = "") -> Path:
    """包内文件缺失时给一句人话，而不是抛 FileNotFoundError。"""
    if not path.exists():
        msg = f"缺少{what}：{path}"
        if hint:
            msg += f"\n  → {hint}"
        raise SystemExit(msg)
    return path


# ---------------------------------------------------------------- 自述
def main() -> int:
    def mark(p: Path) -> str:
        return "OK  " if p.exists() else "MISS"

    rows = [
        ("包根", PKG_ROOT),
        ("渲染器", RENDER_SCRIPT),
        ("合并器", MERGE_SCRIPT),
        ("字幕解析", PARSE_SRT_SCRIPT),
        ("握笔图", DRAWING_HAND),
        ("配音脚本", TTS_SCRIPT),
        ("音色自检", CHECK_VOICES),
        ("venv 解释器", VENV_PY),
        ("requirements", REQUIREMENTS),
    ]
    w = max(len(n) for n, _ in rows)
    for name, p in rows:
        print(f"{name:<{w}} {mark(p)}  {p}")

    rp = render_python()
    tp = tts_python()
    print()
    print(f"渲染用 PY  : {rp}")
    print(f"  依赖齐全 : {has_render_deps(rp)}  ({', '.join(RENDER_MODULES)})")
    print(f"配音用 PY  : {tp}")
    print(f"  依赖齐全 : {has_tts_deps(tp)}  ({', '.join(TTS_MODULES)})")
    if rp != tp:
        print("\n提示：两个 PY 不同。想统一成包内一个 venv，跑 scripts/bootstrap_env.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
