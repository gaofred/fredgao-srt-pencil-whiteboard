#!/usr/bin/env python3
"""按列投影自动切出场景图中的独立图组，输出原图像素坐标。

用法：
  <ENV_PY> tools/find_regions.py <图片> [--gap 40] [--pad 14] [--drop 28] [--json]

原理：纸色是均匀亮色，凡明显暗于纸色的像素记为墨迹；对墨迹按列求和，
相邻墨迹列之间若空白超过 --gap 像素就视为两组，再取每组的行范围。
--drop 控制"多暗才算墨"，切不开时加严到 55/70。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def ink_mask(rgb: np.ndarray, drop: int = 28) -> np.ndarray:
    flat = rgb.reshape(-1, 3)
    paper = np.median(flat[flat.mean(axis=1) > 190], axis=0)
    return (rgb.astype(np.int16).mean(axis=2) < paper.mean() - drop)


def groups(mask: np.ndarray, gap: int, pad: int, min_ink: int) -> list[dict]:
    h, w = mask.shape
    cols = mask.sum(axis=0) > 0
    runs: list[list[int]] = []
    start = None
    for x in range(w):
        if cols[x] and start is None:
            start = x
        elif not cols[x] and start is not None:
            runs.append([start, x - 1])
            start = None
    if start is not None:
        runs.append([start, w - 1])
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= gap:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    out = []
    for x0, x1 in merged:
        sub = mask[:, x0 : x1 + 1]
        rows = np.where(sub.any(axis=1))[0]
        if len(rows) == 0:
            continue
        n_ink = int(sub.sum())
        if n_ink < min_ink:
            continue
        y0, y1 = int(rows[0]), int(rows[-1])
        bx0 = max(0, x0 - pad)
        by0 = max(0, y0 - pad)
        bx1 = min(w, x1 + 1 + pad)
        by1 = min(h, y1 + 1 + pad)
        out.append(
            {
                "x": bx0,
                "y": by0,
                "width": bx1 - bx0,
                "height": by1 - by0,
                "ink": n_ink,
            }
        )
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--gap", type=int, default=40)
    ap.add_argument("--pad", type=int, default=14)
    ap.add_argument("--min-ink", type=int, default=400)
    ap.add_argument("--drop", type=int, default=28,
                    help="墨迹阈值：比纸色暗多少才算墨。默认 28 偏松，组间浅排线会被算成墨迹而粘成一组；"
                         "切不开时逐级加严（55 / 70），但要复查 check_coverage.py 有无漏笔画")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv[1:])
    rgb = np.array(Image.open(a.image).convert("RGB"))
    gs = groups(ink_mask(rgb, a.drop), a.gap, a.pad, a.min_ink)
    if a.json:
        print(json.dumps({"canvas": {"width": rgb.shape[1], "height": rgb.shape[0]}, "regions": gs}, ensure_ascii=False))
        return 0
    print(f"{Path(a.image).name}  画布 {rgb.shape[1]}x{rgb.shape[0]}  组数 {len(gs)}")
    for i, g in enumerate(gs, 1):
        print(f"  {i}: x={g['x']:4d} y={g['y']:4d} w={g['width']:4d} h={g['height']:4d}  ink={g['ink']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
