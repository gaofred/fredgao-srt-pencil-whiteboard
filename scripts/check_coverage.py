#!/usr/bin/env python3
"""检查"孤儿笔画"：有没有墨迹落在所有区域之外。

上游渲染器逐区域落墨，落在任何区域之外的笔画永远不会被画出来，
表现为成片末帧与原图不一致（少几条线），且检查图上看不出问题。

用法：
  <ENV_PY> scripts/check_coverage.py <项目目录>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_regions import ink_mask  # noqa: E402
from build_annotations import clean_mask  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    plan_path = root / "scenes.json"
    if not plan_path.exists():
        raise SystemExit(f"缺少 {plan_path}，先按 templates/scenes.example.json 写一份")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    bad = 0
    for sc in plan["scenes"]:
        img = root / sc["image"]
        ann = img.with_suffix(".annotation.json")
        if not ann.exists():
            print(f"{sc['id']}  缺 annotation.json，先跑 build_annotations.py")
            bad += 1
            continue
        doc = json.loads(ann.read_text(encoding="utf-8"))
        rgb = np.array(Image.open(img).convert("RGB"))
        mask = clean_mask(ink_mask(rgb))
        h, w = mask.shape
        cover = np.zeros((h, w), dtype=bool)
        for e in doc["elements"]:
            r = e["region"]
            cover[r["y"]: r["y"] + r["height"], r["x"]: r["x"] + r["width"]] = True
        orphan = mask & ~cover
        total = int(mask.sum())
        n = int(orphan.sum())
        if n == 0:
            print(f"{sc['id']}  OK      墨点 {total}，全部落在区域内")
            continue
        bad += 1
        ys, xs = np.where(orphan)
        print(f"{sc['id']}  漏 {n} 点（{n/total*100:.2f}%）  "
              f"范围 x {xs.min()}-{xs.max()}  y {ys.min()}-{ys.max()}")
        # 给出成簇的漏点位置，便于扩框
        ys_q, xs_q = ys // 40, xs // 40
        cells = {}
        for a, b in zip(ys_q, xs_q):
            cells[(a, b)] = cells.get((a, b), 0) + 1
        top = sorted(cells.items(), key=lambda kv: -kv[1])[:4]
        for (a, b), c in top:
            print(f"        簇 ({b*40}-{b*40+40}, {a*40}-{a*40+40})  {c} 点")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
