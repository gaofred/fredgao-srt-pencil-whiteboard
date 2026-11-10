#!/usr/bin/env python3
"""逐条配音，并按配音实际时长重建时间轴与 SRT。

用法：
  <PY3> scripts/build_narration.py <项目目录> --srt park-cleanup.srt --voice aria
  <PY3> scripts/build_narration.py <项目目录> --voice sonia --speed slow --force

产出（都在项目目录下）：
  audio/cues/cue-NN.mp3    逐条配音
  audio/narration.json     每条的音长 + 新旧时间轴（供 build_annotations.py 用）
  {srt 名}-v2.srt          按配音重排的字幕（供 burn_and_mux.py 用）

为什么必须先配音再定时间轴：
  TTS 不会迁就你手写的字幕窗口。实测 aria 自然语速约 120 词/分，
  一条 4.6s 的字幕窗口要念 5.6s，硬塞会两句叠在一起。
  正确顺序是「文本 → 暂定 SRT → 逐条配音 → 按真实音长重排 → 再排画面」。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import TTS_SCRIPT, tts_python  # noqa: E402

SRT_RE = re.compile(
    r"(\d+)\s*\n(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)\s*\n(.+?)(?=\n\n|\Z)",
    re.S,
)


def to_ms(h, m, s, z) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(z)


def fmt(t: int) -> str:
    return f"{t // 3600000:02d}:{t % 3600000 // 60000:02d}:{t % 60000 // 1000:02d},{t % 1000:03d}"


def parse_srt(path: Path) -> list[dict]:
    cues = []
    for m in SRT_RE.finditer(path.read_text(encoding="utf-8")):
        cues.append({
            "index": int(m.group(1)),
            "startMs": to_ms(*m.group(2, 3, 4, 5)),
            "endMs": to_ms(*m.group(6, 7, 8, 9)),
            "text": m.group(10).strip().replace("\n", " "),
        })
    return cues


def probe_dur(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", help="项目目录")
    ap.add_argument("--srt", required=True, help="暂定字幕（相对项目目录）")
    ap.add_argument("--voice", default="aria", help="音色别名，见 fredgao-text-to-speech")
    ap.add_argument("--speed", default="normal", choices=["slow", "slower", "normal", "fast", "faster"])
    ap.add_argument("--gap", type=float, default=0.30, help="条间静音，秒")
    ap.add_argument("--min-dur", type=float, default=2.0, help="单条最短停留，秒")
    ap.add_argument("--lead-in", type=float, default=0.6, help="片头静默，秒")
    ap.add_argument("--out-srt", help="重排后字幕名（默认 {原名}-v2.srt）")
    ap.add_argument("--force", action="store_true", help="重配已有 mp3")
    a = ap.parse_args()

    if not TTS_SCRIPT.exists():
        raise SystemExit(
            f"找不到配音脚本 {TTS_SCRIPT}\n"
            "  → vendor/text-to-speech/scripts/tts.py 应随包分发，缺了说明包没复制完整"
        )
    py = tts_python()
    root = Path(a.project).resolve()
    srt_in = root / a.srt
    cues = parse_srt(srt_in)
    if not cues:
        raise SystemExit(f"{srt_in} 里没有解析到字幕条")

    out_dir = root / "audio" / "cues"
    out_dir.mkdir(parents=True, exist_ok=True)

    old_total = cues[-1]["endMs"]
    t = int(a.lead_in * 1000)
    made = 0
    for cue in cues:
        mp3 = out_dir / f"cue-{cue['index']:02d}.mp3"
        if a.force or not mp3.exists():
            subprocess.run(
                [py, str(TTS_SCRIPT), "-t", cue["text"], "-o", str(mp3),
                 "--voice", a.voice, "--speed", a.speed],
                check=True, capture_output=True, text=True,
            )
            made += 1
        d = probe_dur(mp3)
        cue["audioMs"] = int(round(d * 1000))
        cue["oldStartMs"] = cue["startMs"]
        cue["oldEndMs"] = cue["endMs"]
        cue["startMs"] = t
        cue["endMs"] = t + max(int(round((d + a.gap) * 1000)), int(a.min_dur * 1000))
        t = cue["endMs"]
        print(f"cue {cue['index']:02d}: 念 {d:5.2f}s  旧窗口 "
              f"{(cue['oldEndMs']-cue['oldStartMs'])/1000:4.1f}s  新 "
              f"{cue['startMs']/1000:6.1f}-{cue['endMs']/1000:6.1f}s  {cue['text'][:38]}")

    total = cues[-1]["endMs"]
    out_srt = root / (a.out_srt or (srt_in.stem + "-v2.srt"))
    out_srt.write_text(
        "".join(f"{c['index']}\n{fmt(c['startMs'])} --> {fmt(c['endMs'])}\n{c['text']}\n\n" for c in cues),
        encoding="utf-8",
    )

    (root / "audio" / "narration.json").write_text(
        json.dumps({"voice": a.voice, "speed": a.speed, "totalMs": total,
                    "oldTotalMs": old_total, "cues": cues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n新配 {made} 条 / 共 {len(cues)} 条")
    print(f"总长 {old_total/1000:.1f}s -> {total/1000:.1f}s（倍率 {total/old_total:.3f}）")
    print(f"字幕 -> {out_srt.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
