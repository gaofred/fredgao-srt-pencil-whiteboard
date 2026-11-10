#!/usr/bin/env python3
"""把字幕烧进画面并把逐条配音混成音轨，一次编码输出成片。

用法：
  <ENV_PY> scripts/burn_and_mux.py <无声mp4> <重排后.srt> <narration.json> <输出mp4>
  <ENV_PY> scripts/burn_and_mux.py in.mp4 in-v2.srt audio/narration.json out.mp4 \\
      --font-size 34 --color 443E2F --bottom 55

为什么不用 ffmpeg 的 subtitles/drawtext 滤镜：
  本机 ffmpeg 编译时没带 libass 也没带 freetype，这两个滤镜根本不存在。
  所以字幕由 PIL 预渲染成透明贴图、逐帧 alpha 合成；音轨用 numpy 按 cue 起点铺。
  好处是不依赖 ffmpeg 编译选项，坏处是要跑一遍全片解码+重编码（4 分钟片约 3–5 分钟）。

规格（对齐参考片）：Arial Bold、暖深灰 #443E2F、居中、最多两行、底部留 57px（720p）。
字号与底距按画面高度等比缩放，换画幅不用改代码。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
REF_H = 720          # 下列数值都是在 720p 上定的基准
REF_SIZE = 36
REF_BOTTOM = 57
LINE_GAP = 8
SR = 24000

SRT_RE = re.compile(
    r"(\d+)\s*\n(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)\s*\n(.+?)(?=\n\n|\Z)",
    re.S,
)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def find_font() -> str:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("找不到可用的拉丁字体，用 --font 指定一个 .ttf")


def to_ms(h, m, s, z) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(z)


def parse_srt(p: Path) -> list[dict]:
    out = []
    for m in SRT_RE.finditer(p.read_text(encoding="utf-8")):
        out.append({
            "startMs": to_ms(*m.group(2, 3, 4, 5)),
            "endMs": to_ms(*m.group(6, 7, 8, 9)),
            "text": m.group(10).strip().replace("\n", " "),
        })
    return out


def wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_strip(text: str, w: int, font_path: str, size: int, color, max_w: int):
    font = ImageFont.truetype(font_path, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines = wrap(probe, text, font, max_w)
    while len(lines) > 2 and size > 20:          # 最多两行，超了缩字号
        size -= 2
        font = ImageFont.truetype(font_path, size)
        lines = wrap(probe, text, font, max_w)
    asc, desc = font.getmetrics()
    line_h = asc + desc + LINE_GAP
    strip = Image.new("RGBA", (w, line_h * len(lines) - LINE_GAP + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(strip)
    for i, ln in enumerate(lines):
        tw = d.textlength(ln, font=font)
        d.text(((w - tw) / 2, i * line_h), ln, font=font, fill=(*color, 255))
    return strip


def build_audio(meta: dict, base_ms: int, total_ms: int, cue_dir: Path) -> np.ndarray:
    n = int(total_ms / 1000 * SR) + SR
    track = np.zeros(n, dtype=np.float32)
    for c in meta["cues"]:
        mp3 = cue_dir / f"cue-{int(c['index']):02d}.mp3"
        if not mp3.exists():
            print(f"  [warn] 缺 {mp3.name}，该条静音")
            continue
        with av.open(str(mp3)) as ctx:
            res = av.AudioResampler(format="flt", layout="mono", rate=SR)
            chunks = []
            for fr in ctx.decode(audio=0):
                for rf in res.resample(fr):
                    chunks.append(rf.to_ndarray().reshape(-1))
            for rf in res.resample(None):
                chunks.append(rf.to_ndarray().reshape(-1))
        clip = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        start = max(0, int((c["startMs"] - base_ms) / 1000 * SR))
        end = min(start + len(clip), n)
        if end > start:
            track[start:end] += clip[: end - start]
    peak = float(np.max(np.abs(track))) or 1.0
    if peak > 0.89:
        track *= 0.89 / peak
    return track


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("srt")
    ap.add_argument("narration")
    ap.add_argument("output")
    ap.add_argument("--font")
    ap.add_argument("--font-size", type=int, help="720p 基准字号，默认 36（按画高缩放）")
    ap.add_argument("--color", default="443E2F")
    ap.add_argument("--bottom", type=int, help="720p 基准底距，默认 57（按画高缩放）")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--progress", type=int, default=600, help="每 N 帧报一次进度")
    a = ap.parse_args(argv[1:])

    src, srt_path = Path(a.video), Path(a.srt)
    narr_path, dst = Path(a.narration), Path(a.output)
    cues = parse_srt(srt_path)
    meta = json.loads(narr_path.read_text(encoding="utf-8"))
    if not cues:
        raise SystemExit(f"{srt_path} 没有解析到字幕")

    # 视频第 0 帧对应第 1 条字幕的起点，整体左移这段前导静默
    base = cues[0]["startMs"]
    for c in cues:
        c["startMs"] -= base
        c["endMs"] -= base
    total_ms = meta["totalMs"] - base

    with av.open(str(src)) as probe:
        vs = probe.streams.video[0]
        w, h, fps = vs.codec_context.width, vs.codec_context.height, float(vs.average_rate)

    scale = h / REF_H
    size = a.font_size or max(18, round(REF_SIZE * scale))
    bottom = a.bottom or round(REF_BOTTOM * scale)
    font_path = a.font or find_font()
    color = hex_rgb(a.color)
    print(f"输入 {w}x{h} @ {fps:.0f}fps | 字幕 {len(cues)} 条 | 总长 {total_ms/1000:.1f}s")
    print(f"字幕 {Path(font_path).name} {size}px #{a.color.upper()} 底距 {bottom}px")

    strips = {}
    for idx, c in enumerate(cues):
        s = make_strip(c["text"], w, font_path, size, color, int(w * 0.88))
        strips[idx] = (s, h - bottom - s.height)

    audio = build_audio(meta, base, total_ms, narr_path.parent / "cues")
    print(f"音轨 {len(audio)/SR:.1f}s，峰值归一化完成")

    out = av.open(str(dst), "w")
    ov = out.add_stream("libx264", rate=int(round(fps)))
    ov.width, ov.height, ov.pix_fmt = w, h, "yuv420p"
    ov.options = {"crf": str(a.crf), "preset": "medium"}
    oa = out.add_stream("aac", rate=SR)
    oa.layout = "mono"

    buf = None
    idx = 0
    written = 0
    with av.open(str(src)) as inp:
        for frame in inp.decode(video=0):
            t_ms = float(frame.pts * frame.time_base) * 1000
            while idx < len(cues) - 1 and t_ms >= cues[idx]["endMs"]:
                idx += 1
            show = None
            for j in (idx, idx - 1):
                if 0 <= j < len(cues) and cues[j]["startMs"] <= t_ms < cues[j]["endMs"]:
                    show = strips.get(j)
                    break
            img = frame.to_image()
            if show is not None:
                if buf is None:
                    buf = Image.new("RGBA", img.size, (0, 0, 0, 0))
                buf.paste((0, 0, 0, 0), (0, 0, w, h))
                buf.paste(show[0], (0, show[1]))
                img = Image.alpha_composite(img.convert("RGBA"), buf).convert("RGB")
            for pkt in ov.encode(frame.from_image(img).reformat(format="yuv420p")):
                out.mux(pkt)
            written += 1
            if a.progress and written % a.progress == 0:
                print(f"  {written} 帧 / {t_ms/1000:.0f}s", flush=True)

    fstep = int(SR / fps)
    pos = 0
    while pos < len(audio):
        seg = audio[pos : pos + fstep]
        pos += fstep
        if len(seg) < fstep:
            seg = np.pad(seg, (0, fstep - len(seg)))
        af = av.AudioFrame.from_ndarray((seg.reshape(1, -1) * 32767).astype(np.int16),
                                       format="s16", layout="mono")
        af.sample_rate = SR
        for pkt in oa.encode(af):
            out.mux(pkt)
    for pkt in ov.encode(None):
        out.mux(pkt)
    for pkt in oa.encode(None):
        out.mux(pkt)
    out.close()
    print(f"完成 {written} 帧 -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
