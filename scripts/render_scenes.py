#!/usr/bin/env python3
"""按 scenes.json 批量渲染各幕，可选自动合并。

用法：
  <ENV_PY> scripts/render_scenes.py <项目目录>
  <ENV_PY> scripts/render_scenes.py <项目目录> --only scene-02 --merge
  <ENV_PY> scripts/render_scenes.py <项目目录> --with-hand --fps 30   # 要握笔手

默认参数就是"铅笔素描绘本"那一套：--bare-tip（无握笔手）+ --ink-path skeleton
（骨架追踪，线稿清晰的插画笔迹更贴合）+ 60fps。单幕约 25–60 秒出片。
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import (  # noqa: E402
    DRAWING_HAND,
    MERGE_SCRIPT,
    PKG_ROOT,
    RENDER_SCRIPT,
    render_python,
)

UP = PKG_ROOT / "vendor" / "whiteboard-renderer"
UP_PY = render_python()
RENDER = RENDER_SCRIPT
MERGE = MERGE_SCRIPT
HAND = DRAWING_HAND


def run(cmd: list[str]) -> int:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stdout[-1500:] + p.stderr[-1500:])
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--only", action="append", help="只渲染指定 sceneId，可重复")
    ap.add_argument("--image-dir", default=".")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--cap-long-edge", type=int, default=1080)
    ap.add_argument("--fps-preview", action="store_true", help="快速预览：30fps + 长边 720")
    ap.add_argument("--with-hand", action="store_true", help="叠加握笔手（默认不叠）")
    ap.add_argument("--color-fill", default="contour-wipe", choices=["contour-wipe", "brush"])
    ap.add_argument("--merge", action="store_true", help="渲染完自动合并为无声片")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not RENDER.exists():
        raise SystemExit(
            f"找不到渲染器 {RENDER}\n  → vendor/ 没复制完整；先跑 scripts/check_env.py 看缺什么"
        )
    if not HAND.exists() and a.with_hand:
        raise SystemExit(f"找不到握笔图 {HAND}（不加 --with-hand 就不需要它）")
    root = Path(a.project).resolve()
    plan_path = root / "scenes.json"
    if not plan_path.exists():
        raise SystemExit(
            f"缺少 {plan_path}\n"
            "  → 按包内 templates/scenes.example.json 写一份（文件里有字段注释）"
        )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    img_dir = root / a.image_dir
    fps = 30 if a.fps_preview else a.fps
    cap = 720 if a.fps_preview else a.cap_long_edge

    scenes = plan["scenes"]
    if a.only:
        scenes = [s for s in scenes if s["id"] in set(a.only)]

    outputs: list[Path] = []
    for sc in scenes:
        img = img_dir / sc["image"]
        ann = img.with_suffix(".annotation.json")
        if not ann.exists():
            raise SystemExit(f"{sc['id']} 缺 {ann.name}，先跑 build_annotations.py")
        out = root / f"{img.stem}-whiteboard.mp4"
        outputs.append(out)
        cmd = [str(UP_PY), str(RENDER), str(img), str(ann), str(out),
               "--ink-path", "skeleton", "--fps", str(fps),
               "--cap-long-edge", str(cap), "--color-fill", a.color_fill]
        if a.with_hand and HAND.exists():
            cmd.append(str(HAND))
        else:
            cmd.append("--bare-tip")
        if a.dry_run:
            print(" ".join(cmd))
            continue
        t0 = time.time()
        print(f"=== {sc['id']} ({img.name}) ===", flush=True)
        if run(cmd) != 0:
            raise SystemExit(f"{sc['id']} 渲染失败")
        print(f"    {time.time()-t0:.0f}s -> {out.name}", flush=True)

    if a.dry_run or not a.merge:
        if not a.dry_run and len(outputs) > 1:
            print("\n合并命令：")
            print("  " + " ".join(
                shlex.quote(x) for x in
                [UP_PY, str(MERGE), "--inputs"] + [p.name for p in outputs]
                + ["--output", f"{plan.get('project', 'video')}-silent.mp4"]
            ))
        return 0

    silent = root / f"{plan.get('project', 'video')}-silent.mp4"
    print(f"\n=== 合并 {len(outputs)} 幕 -> {silent.name} ===", flush=True)
    cmd = [str(UP_PY), str(MERGE), "--inputs"] + [str(p) for p in outputs] + ["--output", str(silent)]
    if run(cmd) != 0:
        raise SystemExit("合并失败")
    print(f"完成 {silent}")
    print("\n下一步：")
    print("  " + " ".join(shlex.quote(x) for x in [
        sys.executable, str(PKG_ROOT / "scripts" / "burn_and_mux.py"), str(silent),
        "<重排后.srt>", "audio/narration.json", f"{plan.get('project','video')}-final.mp4",
    ]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
