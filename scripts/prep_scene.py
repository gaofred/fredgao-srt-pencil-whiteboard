#!/usr/bin/env python3
"""场景图后处理：抹掉平台水印 + 把纸张底色对齐目标纸色。

用法：
  <ENV_PY> scripts/prep_scene.py raw/*.png --outdir scene/ [--paper EFECDD]
  <ENV_PY> scripts/prep_scene.py in.png -o out.png            # 单文件

做的事：
  1. 采样纸色（全图高亮像素中位数）；
  2. 在角落区域检测「比纸色更亮的像素」（= 白色半透明水印），膨胀后填成纸色；
  3. 按目标纸色做逐通道增益，把整图色调对齐（线条近黑，几乎不受影响）。

为什么要做：图像模型出的图，纸底往往偏黄偏橘、与参考片对不上；
右下角还会带平台水印。这两件事几乎每张必犯，不处理拼起来会花。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REF_BG_DEFAULT = "EFECDD"      # 参考片纸色
WM_REGIONS = [                 # 水印搜索区（比例）：右下为主，兼顾左下
    (0.60, 0.85, 1.0, 1.0),
    (0.00, 0.85, 0.40, 1.0),
]


def hex2rgb(h: str) -> np.ndarray:
    h = h.strip().lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def paper_color(rgb: np.ndarray) -> np.ndarray:
    flat = rgb.reshape(-1, 3)
    bright = flat[flat.mean(axis=1) > 190]
    if len(bright) < 100:
        bright = flat
    return np.median(bright, axis=0).astype(np.float32)


def erase_watermark(rgb: np.ndarray, paper: np.ndarray, regions=WM_REGIONS) -> int:
    """返回被改写的像素数。水印特征：三通道同时比纸色亮 6 级以上。"""
    h, w, _ = rgb.shape
    touched = 0
    for rx0, ry0, rx1, ry1 in regions:
        x0, y0 = int(w * rx0), int(h * ry0)
        x1, y1 = int(w * rx1), int(h * ry1)
        sub = rgb[y0:y1, x0:x1].astype(np.int16)
        diff = sub - paper.astype(np.int16)
        mask = (diff[:, :, 0] > 6) & (diff[:, :, 1] > 6) & (diff[:, :, 2] > 6)
        if mask.sum() < 30:
            continue
        mask_u8 = (mask.astype(np.uint8)) * 255
        mask_u8 = cv2.dilate(mask_u8, np.ones((7, 7), np.uint8), iterations=2)
        region = rgb[y0:y1, x0:x1]
        region[mask_u8 > 0] = paper.astype(np.uint8)
        rgb[y0:y1, x0:x1] = region
        touched += int((mask_u8 > 0).sum())
    return touched


def process(src: Path, dst: Path, target: np.ndarray, keep_watermark: bool = False):
    rgb = np.array(Image.open(src).convert("RGB"))
    paper = paper_color(rgb)
    n = 0 if keep_watermark else erase_watermark(rgb, paper)
    gain = np.clip(target / np.clip(paper, 1, None), 0.70, 1.35)   # 防拉爆
    out = np.clip(rgb.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(dst)
    return paper, n, out.shape


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="输入图（shell 通配符自行展开）")
    ap.add_argument("-o", "--output", help="单文件模式的输出路径")
    ap.add_argument("--outdir", help="批量模式的输出目录（保持文件名）")
    ap.add_argument("--paper", default=REF_BG_DEFAULT, help="目标纸色，如 EFECDD")
    ap.add_argument("--no-watermark", action="store_true", help="只校色，不抹水印")
    a = ap.parse_args(argv[1:])

    target = hex2rgb(a.paper)
    files = [Path(p) for p in a.inputs]
    for f in files:
        if not f.exists():
            raise SystemExit(f"找不到 {f}")

    if a.output and len(files) == 1:
        pairs = [(files[0], Path(a.output))]
    elif a.outdir:
        pairs = [(f, Path(a.outdir) / f.name) for f in files]
    elif len(files) == 1:
        pairs = [(files[0], files[0].with_name(files[0].stem + "-prep.png"))]
    else:
        raise SystemExit(f"给了 {len(files)} 个输入却只指定了一个 -o："
                         f"批量处理请改用 --outdir <目录>")

    for src, dst in pairs:
        paper, n, shape = process(src, dst, target, a.no_watermark)
        print(f"{src.name}: 纸色 {paper.astype(int)} -> #{a.paper.upper()}  "
              f"水印像素 {n}  -> {dst.name} {shape[1]}x{shape[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
