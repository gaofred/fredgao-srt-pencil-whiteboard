#!/usr/bin/env python3
"""按 scenes.json 生成每幕的 annotation.json：区域按墨迹实测，时序锚定到对应字幕条。

用法：
  <ENV_PY> scripts/build_annotations.py <项目目录>
  <ENV_PY> scripts/build_annotations.py <项目目录> --dry-run   # 只打印时间表
  <ENV_PY> scripts/build_annotations.py <项目目录> --scene scene-03

项目目录下必须有 scenes.json；若存在 audio/narration.json，则时间轴锚定配音。

时序规则（三条，缺一不可）：
  1. 元素起点 = 该元素 anchorCue 那条字幕的新起点 − 本幕起点（句子念到哪，笔就落到哪）；
  2. 首元素强制在 0.4s 内起笔，否则开幕空等两秒；
  3. 串行顺延：后一元素不早于前一元素收笔 +0.1s；末元素收笔不越幕尾（留 0.35s 收气）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_regions import ink_mask  # noqa: E402

PAD_Y = 12
PAD_X = 10
TAIL_MS = 350


def clean_mask(mask: np.ndarray, min_area: int = 14) -> np.ndarray:
    """去掉孤立噪点：纸面有零星灰点会被算成墨迹，把 bbox 撑出一大片空白。"""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, dtype=bool)
    for i in range(1, n):
        keep[i] = stats[i, cv2.CC_STAT_AREA] >= min_area
    return keep[labels]


def tight_region(mask: np.ndarray, x0: int, x1: int, thr: int = 2) -> dict:
    """在 [x0,x1) 列窗口内按墨迹收边。thr=2：该行至少 2 个墨点才算数。"""
    h, w = mask.shape
    x0, x1 = max(0, min(w, x0)), max(0, min(w, x1))
    sub = mask[:, x0:x1]
    rows = np.where(sub.sum(axis=1) >= thr)[0]
    cols = np.where(sub.sum(axis=0) >= thr)[0]
    if len(rows) == 0 or len(cols) == 0:
        raise SystemExit(f"x 区间 {x0}-{x1} 无墨迹：检查 region.x0/x1 是否落在图组上")
    y0 = max(0, int(rows[0]) - PAD_Y)
    y1 = min(h, int(rows[-1]) + 1 + PAD_Y)
    rx0 = max(0, x0 + int(cols[0]) - PAD_X)
    rx1 = min(w, x0 + int(cols[-1]) + 1 + PAD_X)
    return {"x": int(rx0), "y": int(y0), "width": int(rx1 - rx0), "height": int(y1 - y0)}


def resolve_region(region: dict, mask: np.ndarray) -> dict:
    if "x" in region and "width" in region:          # 显式给定
        return {k: int(region[k]) for k in ("x", "y", "width", "height")}
    return tight_region(mask, int(region["x0"]), int(region["x1"]))


def ink_loss(mask: np.ndarray, a: dict, b: dict) -> float:
    """a 的墨迹有多大比例落在 b 的区域里。

    上游渲染器会把「后续区域的矩形」从前面区域的允许掩码里扣掉，
    所以一旦 a 的主体笔画压在 b 上，a 就会画不全（缺一角、断线）。
    按 bbox 面积算重叠会误报（手臂嵌在身体框里很常见但不影响），
    按墨迹算才准。
    """
    ax0, ay0 = a["x"], a["y"]
    ax1, ay1 = ax0 + a["width"], ay0 + a["height"]
    sub = mask[ay0:ay1, ax0:ax1]
    total = int(sub.sum())
    if total == 0:
        return 0.0
    ix0, iy0 = max(ax0, b["x"]), max(ay0, b["y"])
    ix1 = min(ax1, b["x"] + b["width"])
    iy1 = min(ay1, b["y"] + b["height"])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    lost = int(sub[iy0 - ay0 : iy1 - ay0, ix0 - ax0 : ix1 - ax0].sum())
    return lost / total


def timeline(scene: dict, cues: dict[int, dict]) -> tuple[int, int, list[int], list[int]]:
    """返回 (scene_start, scene_dur, starts, durs)。"""
    els = scene["elements"]
    design = [int(e.get("designMs", 6000)) for e in els]

    if cues:
        c0, c1 = scene["cues"]
        scene_start = cues[c0]["startMs"]
        scene_end = cues[c1]["endMs"]
        old = cues[c1]["oldEndMs"] - cues[c0]["oldStartMs"]
        scene_dur = scene_end - scene_start
        factor = scene_dur / old if old > 0 else 1.0
    else:
        scene_start = 0
        factor = 1.0
        scene_dur = sum(design) + 400

    starts, durs = [], []
    for i, e in enumerate(els):
        durs.append(max(900, int(design[i] * factor)))
        anchor = e.get("anchorCue")
        if cues and anchor in cues:
            s = cues[anchor]["startMs"] - scene_start
        else:
            s = i * 5000
        if i == 0:
            s = min(s, 400)                       # 开幕立刻起笔
        starts.append(max(300, s))

    for i in range(1, len(starts)):               # 串行顺延
        starts[i] = max(starts[i], starts[i - 1] + durs[i - 1] + 100)

    over = starts[-1] + durs[-1] - (scene_dur - TAIL_MS)
    if over > 0:                                  # 末元素收笔不越幕
        durs[-1] = max(1200, durs[-1] - over)
        over = starts[-1] + durs[-1] - (scene_dur - TAIL_MS)
        if over > 0:
            durs[-1] = max(900, int(durs[-1] * (scene_dur - TAIL_MS - starts[-1]) / durs[-1]))
    return scene_start, scene_dur, starts, durs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", help="项目目录（含 scenes.json）")
    ap.add_argument("--dry-run", action="store_true", help="只打印时间表，不写文件")
    ap.add_argument("--scene", help="只处理某一幕（sceneId）")
    ap.add_argument("--image-dir", default=".", help="场景图所在子目录（默认项目根）")
    a = ap.parse_args()

    root = Path(a.project).resolve()
    plan_path = root / "scenes.json"
    if not plan_path.exists():
        raise SystemExit(f"缺少 {plan_path}，先按 templates/scenes.example.json 写一份")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    img_dir = root / a.image_dir

    cues: dict[int, dict] = {}
    narr = root / plan.get("narration", "audio/narration.json")
    if narr.exists():
        meta = json.loads(narr.read_text(encoding="utf-8"))
        cues = {c["index"]: c for c in meta["cues"]}
    else:
        print("[warn] 没有 narration.json，按设计时长排时间（不锚定配音）")

    scenes = plan["scenes"]
    if a.scene:
        scenes = [s for s in scenes if s["id"] == a.scene]
        if not scenes:
            raise SystemExit(f"scenes.json 里没有 {a.scene}")

    for sc in scenes:
        img_path = img_dir / sc["image"]
        if not img_path.exists():
            raise SystemExit(f"找不到场景图 {img_path}")
        rgb = np.array(Image.open(img_path).convert("RGB"))
        h, w = rgb.shape[:2]
        mask = clean_mask(ink_mask(rgb))
        scene_start, scene_dur, starts, durs = timeline(sc, cues)

        elements, regions = [], []
        for seq, (e, s, d) in enumerate(zip(sc["elements"], starts, durs), 1):
            region = resolve_region(e["region"], mask)
            if region["x"] + region["width"] > w or region["y"] + region["height"] > h:
                print(f"  [warn] {e['id']} 区域越界，已裁到画布内")
                region["x"] = max(0, min(region["x"], w - 2))
                region["y"] = max(0, min(region["y"], h - 2))
                region["width"] = min(region["width"], w - region["x"])
                region["height"] = min(region["height"], h - region["y"])
            regions.append(region)
            elements.append(
                {
                    "id": e["id"],
                    "label": e.get("label", e["id"]),
                    "sequence": seq,
                    "narrativeRole": e.get("role", ""),
                    "subtitle": e.get("subtitle", ""),
                    "anchorCue": e.get("anchorCue"),
                    "type": e.get("type", "figure"),
                    "region": region,
                    "reveal": {
                        "direction": e.get("direction", "left_to_right"),
                        "startMs": int(s),
                        "durationMs": int(d),
                        "maskPaddingPx": int(e.get("maskPaddingPx", 18)),
                        "protectedRegions": e.get("protectedRegions", []),
                    },
                    "handPath": {
                        "start": [region["x"], region["y"]],
                        "end": [region["x"] + region["width"], region["y"] + region["height"]],
                        "easing": "easeInOut",
                    },
                }
            )

        # 区域互压提醒：后一区域会从前面区域的允许掩码里扣掉，压到主体笔画就会画不全。
        # 但如果两组紧挨着画（间隔 <0.8s），缺的那块下一刻就由后一组补上，不必告警；
        # 真正的故障是"前一组缺一角、后一组要等一两秒才画"——悬空的前臂就是这么来的。
        for i in range(len(regions)):
            for j in range(i + 1, len(regions)):
                r = ink_loss(mask, regions[i], regions[j])
                gap = starts[j] - (starts[i] + durs[i])
                if r > 0.15 and gap > 800:
                    print(f"  [warn] {elements[i]['id']} 有 {r*100:.0f}% 的笔画落在 "
                          f"{elements[j]['id']} 区域里，且要等 {gap/1000:.1f}s 才补上 —— "
                          f"这中间会缺一块：把两段锚到同一条字幕，或缩小后一区域")

        last = max(e["reveal"]["startMs"] + e["reveal"]["durationMs"] for e in elements)
        print(f"{sc['id']}: 幕 {scene_dur/1000:5.1f}s  "
              + " | ".join(f"{e['id']} {e['reveal']['startMs']/1000:.1f}+{e['reveal']['durationMs']/1000:.1f}s"
                           for e in elements)
              + f"  -> 收笔 {last/1000:.1f}s")

        if a.dry_run:
            continue
        doc = {
            "sceneId": sc["id"],
            "canvas": {"width": w, "height": h},
            "storyBasis": sc.get("storyBasis", ""),
            "sceneDurationMs": int(scene_dur),
            "sceneWindow": {"startMs": int(scene_start), "endMs": int(scene_start + scene_dur)},
            "elements": elements,
        }
        out = img_path.with_suffix(".annotation.json")
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
