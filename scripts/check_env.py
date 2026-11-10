#!/usr/bin/env python3
"""环境自检：包内脚本、虚拟环境依赖、配音、ffmpeg、字体。

用法：
  python3 scripts/check_env.py             # 体检
  python3 scripts/check_env.py --quiet     # 只打印失败项
  python3 scripts/bootstrap_env.py         # 缺依赖时用它装（本脚本不装东西）

退出码：0 全通；1 有关键项缺失（末尾给修复命令）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import (  # noqa: E402
    CHECK_VOICES,
    DRAWING_HAND,
    MERGE_SCRIPT,
    PARSE_SRT_SCRIPT,
    PKG_ROOT,
    RENDER_MODULES,
    RENDER_SCRIPT,
    SCRIPTS,
    TTS_MODULES,
    TTS_SCRIPT,
    VENV_PY,
    has_render_deps,
    has_tts_deps,
    render_python,
    tts_python,
)

FONT_LATIN = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
FONT_CJK = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

rows: list[tuple[str, bool, bool, str]] = []   # (项目, 通过, 关键, 说明)


def add(item: str, ok: bool, detail: str, critical: bool = True) -> None:
    rows.append((item, ok, critical, detail))


def first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if Path(p).exists():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="只打印失败项")
    a = ap.parse_args()

    # 1) 包内文件（vendor 副本）
    add("包目录", PKG_ROOT.exists(), str(PKG_ROOT))
    add("渲染器 render_stream_whiteboard.py", RENDER_SCRIPT.exists(),
        RENDER_SCRIPT.relative_to(PKG_ROOT).as_posix())
    add("合并器 merge_scenes.py", MERGE_SCRIPT.exists(),
        MERGE_SCRIPT.relative_to(PKG_ROOT).as_posix())
    add("字幕解析 parse_srt.py", PARSE_SRT_SCRIPT.exists(),
        PARSE_SRT_SCRIPT.relative_to(PKG_ROOT).as_posix())
    add("握笔图 drawing-hand.png", DRAWING_HAND.exists(),
        DRAWING_HAND.relative_to(PKG_ROOT).as_posix(), critical=False)
    add("配音脚本 tts.py", TTS_SCRIPT.exists(),
        TTS_SCRIPT.relative_to(PKG_ROOT).as_posix())
    add("音色自检 check_voices.py", CHECK_VOICES.exists(),
        CHECK_VOICES.relative_to(PKG_ROOT).as_posix(), critical=False)

    # 2) 渲染依赖
    rp = render_python()
    add(f"渲染依赖 {', '.join(RENDER_MODULES)}", has_render_deps(rp), rp)

    # 3) 配音依赖
    tp = tts_python()
    add(f"配音依赖 {', '.join(TTS_MODULES)}", has_tts_deps(tp), tp)
    if rp != tp:
        add("两个角色共用解释器", False,
            "当前分开跑也能用；想统一就跑 scripts/bootstrap_env.py", critical=False)

    # 4) ffmpeg / ffprobe
    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    add("ffmpeg", bool(ff), ff or "未找到", critical=False)
    add("ffprobe", bool(fp), fp or "未找到")
    if ff:
        v = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True).stdout
        head = v.splitlines()[0] if v else "?"
        filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        has_subs = " subtitles " in filters
        add("ffmpeg 字幕滤镜（本 skill 不需要）", True,
            f"{head} · subtitles={has_subs}"
            + ("（缺 libass 属正常，字幕由 Python 合成）" if not has_subs else ""),
            critical=False)

    # 5) 字体
    latin = first_existing(FONT_LATIN)
    cjk = first_existing(FONT_CJK)
    add("拉丁字幕字体", bool(latin), latin or "未找到 Arial 系")
    add("中文字体（检查图用）", bool(cjk), cjk or "未找到中文字体", critical=False)

    if not a.quiet:
        w = max(len(r[0]) for r in rows) + 2
        print("=" * (w + 8))
        for item, ok, critical, detail in rows:
            if a.quiet and ok:
                continue
            mark = "PASS" if ok else ("FAIL" if critical else "WARN")
            print(f"{item:<{w}} {mark}  {detail}")
        print("=" * (w + 8))

    bad = [r for r in rows if not r[1] and r[2]]
    if not bad:
        print("环境就绪，可以开工。")
        return 0

    print(f"\n{len(bad)} 项关键缺失：")
    for item, _, _, _ in bad:
        print(f"  - {item}")
    print("\n修复参考（脚本在本包 scripts/ 下，用系统 python3 跑）：")
    if not (RENDER_SCRIPT.exists() and TTS_SCRIPT.exists()):
        print("  # vendor/ 里的脚本不齐 → 重新解压整个技能包")
    if not has_render_deps(rp) or not has_tts_deps(tp):
        print(f"  python3 {SCRIPTS / 'bootstrap_env.py'}          # 建包内 .venv 并装依赖")
        print(f"  python3 {SCRIPTS / 'bootstrap_env.py'} --check   # 装完再验一遍")
        print("  # 本机 ensurepip 坏掉时先装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh")
    if not fp:
        print("  ffprobe：mac  brew install ffmpeg ｜ win  winget install Gyan.FFmpeg")
    if not latin:
        print("  # 拉丁字体缺失：装 Arial / DejaVu，或改 burn_and_mux.py 里的 FONT_CANDIDATES")
    return 1


if __name__ == "__main__":
    sys.exit(main())
