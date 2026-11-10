#!/usr/bin/env python3
"""一键准备运行环境：在包内建 `.venv` 并装齐依赖。

为什么需要它：本包要的是 opencv / numpy / av / Pillow / edge-tts 五样东西，
别人的机器上不一定有；而且**不能**把 venv 打进包发出去——venv 里的绝对路径
换台机器就废。所以正确做法是「发脚本、收到的人自己建」。

用法：
  python3 scripts/bootstrap_env.py --check     # 只探测，不装（几十毫秒）
  python3 scripts/bootstrap_env.py             # 建 .venv 并装依赖（首次约 1–3 分钟）
  python3 scripts/bootstrap_env.py --force     # 删了重建（依赖打架时用）

末行永远打印 `PY=<解释器绝对路径>`，其它脚本和文档都可以照这个取值。
退出码：0 就绪；1 没搞定（会打印下一步该敲什么）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import (  # noqa: E402
    PKG_ROOT,
    REQUIREMENTS,
    RENDER_MODULES,
    RENDER_SCRIPT,
    TTS_MODULES,
    TTS_SCRIPT,
    VENV,
    VENV_PY,
    has_render_deps,
    has_tts_deps,
)


def say(msg: str = "") -> None:
    print(msg, flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    say("  $ " + " ".join(cmd))
    return subprocess.run(cmd, text=True, **kw)


def find_uv() -> str | None:
    return shutil.which("uv")


def base_pythons() -> list[str]:
    """能拿来建 venv 的候选。uv 场景下用不到，但没 uv 时得靠它。"""
    cand: list[str] = [sys.executable]
    for name in ("python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        w = shutil.which(name)
        if w:
            cand.append(w)
    seen: set[str] = set()
    return [c for c in cand if c and not (c in seen or seen.add(c))]


def venv_ok() -> bool:
    return VENV_PY.exists() and has_render_deps(VENV_PY) and has_tts_deps(VENV_PY)


def create_venv(force: bool) -> bool:
    """建 .venv。优先 uv（不依赖本机 python 完整，ensurepip 坏掉也能用）。"""
    if VENV.exists():
        if not force:
            say(f"· 复用已有 venv：{VENV}")
            return True
        say(f"· --force：删掉旧 venv {VENV}")
        shutil.rmtree(VENV)

    uv = find_uv()
    if uv:
        say("· 用 uv 建 venv（推荐，不碰 ensurepip）")
        for ver in ("3.13", "3.12", "3.11"):
            p = run([uv, "venv", str(VENV), "--python", ver],
                    capture_output=True)
            if p.returncode == 0 and VENV_PY.exists():
                say(f"  完成：python {ver}")
                return True
            say(f"  {ver} 不可用，试下一个")
        say("  uv 建 venv 失败，回退标准库 venv")
    else:
        say("· 没装 uv，用标准库 venv")

    for py in base_pythons():
        p = run([py, "-m", "venv", str(VENV)], capture_output=True)
        if p.returncode == 0 and VENV_PY.exists():
            say(f"  完成：{py}")
            return True
        tail = (p.stderr or p.stdout or "").strip().splitlines()
        say(f"  {py} 建 venv 失败" + (f"：{tail[-1]}" if tail else ""))
    return False


def install_deps() -> bool:
    if not REQUIREMENTS.exists():
        say(f"✗ 缺少依赖清单 {REQUIREMENTS}")
        return False
    uv = find_uv()
    if uv:
        p = run([uv, "pip", "install", "--python", str(VENV_PY), "-r", str(REQUIREMENTS)])
    else:
        p = run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"],
                capture_output=True)
        p = run([str(VENV_PY), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    return p.returncode == 0


def report() -> int:
    def verify(checker) -> bool:
        # 刚装完的瞬间，个别包的 .pyc/动态库可能还没落盘，误报 FAIL 会让人以为装挂了。
        for attempt in range(2):
            if checker(VENV_PY):
                return True
            if attempt == 0:
                time.sleep(2)
        return False

    ok_render = verify(has_render_deps)
    ok_tts = verify(has_tts_deps)
    say()
    say(f"渲染依赖 {', '.join(RENDER_MODULES):<28} {'PASS' if ok_render else 'FAIL'}")
    say(f"配音依赖 {', '.join(TTS_MODULES):<28} {'PASS' if ok_tts else 'FAIL'}")
    say(f"ffmpeg   {'PASS' if shutil.which('ffmpeg') else 'FAIL'}  {shutil.which('ffmpeg') or '未找到（配音拼接、时长探测要用）'}")
    say(f"ffprobe  {'PASS' if shutil.which('ffprobe') else 'FAIL'}  {shutil.which('ffprobe') or '未找到（探音长要用）'}")
    say()
    say(f"渲染器  {'PASS' if RENDER_SCRIPT.exists() else 'FAIL'}  {RENDER_SCRIPT}")
    say(f"配音脚本 {'PASS' if TTS_SCRIPT.exists() else 'FAIL'}  {TTS_SCRIPT}")

    good = ok_render and ok_tts and RENDER_SCRIPT.exists() and TTS_SCRIPT.exists()
    say()
    if good:
        say(f"PY={VENV_PY}")
        return 0

    say("还差东西。下一步：")
    if not VENV_PY.exists():
        say(f"  {sys.executable} {Path(__file__).resolve()}          # 建 venv")
    elif not (ok_render and ok_tts):
        say(f"  {sys.executable} {Path(__file__).resolve()} --force   # 重建 venv")
        if not find_uv():
            say("  装不上依赖时先装 uv（本机 ensurepip 可能坏）：")
            say("  curl -LsSf https://astral.sh/uv/install.sh | sh")
    if not shutil.which("ffmpeg"):
        say("  ffmpeg：mac  brew install ffmpeg ｜ win  winget install Gyan.FFmpeg")
    if not (RENDER_SCRIPT.exists() and TTS_SCRIPT.exists()):
        say("  vendor/ 里的脚本不齐，说明包复制不完整，重新解压整个技能包")
    say(f"PY={VENV_PY}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只探测，不安装")
    ap.add_argument("--force", action="store_true", help="删掉 venv 重建")
    a = ap.parse_args()

    say(f"包目录：{PKG_ROOT}")
    say(f"平台  ：{sys.platform}  自带 python：{sys.version.split()[0]}")
    say()

    if a.check:
        return report()

    if venv_ok() and not a.force:
        say("· 包内 venv 已就绪，跳过安装（要重建加 --force）")
        return report()

    if not create_venv(a.force):
        say()
        say("✗ 建 venv 失败。最省事的解法是装 uv 后重跑本脚本：")
        say("  curl -LsSf https://astral.sh/uv/install.sh | sh")
        say(f"  {sys.executable} {Path(__file__).resolve()} --force")
        say(f"PY={VENV_PY}")
        return 1

    say()
    say("· 安装依赖（首次 1–3 分钟，看网速）")
    if not install_deps():
        say("✗ 依赖安装失败。检查网络/代理，或手动：")
        say(f"  {VENV_PY} -m pip install -r {REQUIREMENTS}")
        say(f"PY={VENV_PY}")
        return 1

    return report()


if __name__ == "__main__":
    sys.exit(main())
