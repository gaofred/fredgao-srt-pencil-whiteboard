#!/usr/bin/env python3
"""手订字幕清单 → SRT（按暂定语速排时间轴）。

srt_from_text.py 出的是机器切分草稿；人工过切点后，把最终每条字幕
写成一个 txt（一行一条），用本脚本排时间轴。两段分开的好处：
改切点只动纯文本，不碰时间码，也不会再被自动切分二次打乱。

用法：
  python3 scripts/cues_to_srt.py cues.txt -o project/project.srt
  python3 scripts/cues_to_srt.py cues.txt -o out.srt --wps 2.2 --gap 0.3

cues.txt 约定：
  · 一行一条字幕，行内不换行
  · 空行忽略
  · 以 # 开头的行是注释

时间轴是暂定的——真实时长以 TTS 念完为准，下一步 build_narration.py 会重排。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

WPS = 2.2
GAP = 0.30
MIN_DUR = 2.6


def fmt(t: int) -> str:
    return f"{t // 3600000:02d}:{t % 3600000 // 60000:02d}:{t % 60000 // 1000:02d},{t % 1000:03d}"


def read_cues(path: Path) -> list[str]:
    out: list[str] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cues", help="手订字幕清单 .txt（一行一条）")
    ap.add_argument("-o", "--out", required=True, help="输出 .srt")
    ap.add_argument("--wps", type=float, default=WPS, help="暂定语速，词/秒")
    ap.add_argument("--gap", type=float, default=GAP, help="条间静音，秒")
    ap.add_argument("--lead-in", type=float, default=0.0, help="片头静默，秒")
    a = ap.parse_args()

    cues = read_cues(Path(a.cues))
    if not cues:
        print("字幕清单为空", file=sys.stderr)
        return 1

    t = int(a.lead_in * 1000)
    lines: list[str] = []
    stats = []
    for i, c in enumerate(cues, 1):
        n = len(c.split())
        dur = max(MIN_DUR, n / a.wps + a.gap)
        end = t + int(round(dur * 1000))
        lines.append(f"{i}\n{fmt(t)} --> {fmt(end)}\n{c}\n")
        stats.append((i, n, dur, t / 1000, c))
        t = end

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")

    ns = [s[1] for s in stats]
    ds = [s[2] for s in stats]
    total_words = sum(ns)
    print(f"{a.out}  {len(cues)} 条  {total_words} 词  暂定总长 {t/1000:.1f}s")
    print(f"词数 {min(ns)}–{max(ns)}（均值 {total_words/len(ns):.1f}）  "
          f"每条 {min(ds):.1f}–{max(ds):.1f}s")

    short = [(i, n, c) for i, n, _, _, c in stats if n < 5]
    if short:
        print(f"\n[warn] {len(short)} 条少于 5 词，检查是否切碎：")
        for i, n, c in short:
            print(f"        #{i}  {n}词  {c}")
    long = [(i, n, c) for i, n, _, _, c in stats if n > 16]
    if long:
        print(f"\n[warn] {len(long)} 条超过 16 词，可能压到三行：")
        for i, n, c in long:
            print(f"        #{i}  {n}词  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
