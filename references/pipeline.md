# 流水线与坑位

九个步骤，顺序不能换。三处必须停下来让用户点头：**分幕确认 → 首幕风格定调 → 区域检查图确认**。

```
0 体检 → 1 字幕 → 2 分幕 → 3 出图 → 4 后处理 → 5 测区域
      → 6 配音（重排时间轴） → 7 标注 → 8 渲染合并 → 9 烧字幕混音
```

项目目录约定（示例名 `park-cleanup`）：

```
<项目>/
  scenes.json                     分镜计划，唯一真相源
  <project>.srt                   暂定字幕（第 1 步）
  <project>-v2.srt                按配音重排（第 6 步自动生成）
  raw/                            出图原件（带水印）
  scene-01-xxx.png                后处理后的场景图（与 .annotation.json 同名同目录）
  scene-01-xxx.annotation.json    标注（第 7 步生成）
  scene-01-xxx-whiteboard.mp4     单幕成片
  <project>-silent.mp4            合并无声片
  <project>-final.mp4             交付成片
  audio/cues/cue-01.mp3 …         逐条配音
  audio/narration.json            音长与新旧时间轴
```

## 0. 环境体检

```bash
python3 scripts/check_env.py
```

要看到全部 `PASS`。关键依赖是上游渲染器的 `.venv`（opencv/numpy/av/Pillow）与配音环境（edge-tts）。

## 1. 文本 → 暂定字幕

```bash
python3 scripts/srt_from_text.py passage.txt -o park-cleanup/park-cleanup.srt
```

规则：按句切，超 14 词在逗号/分号处拆，短于 4 词与前块合并；词序与原文**逐字一致**（脚本末尾会比对词序列，丢字直接回退）。

产出是**草稿**，必须人工过一遍切点：作者刻意断句的地方（`But as they stepped into the park, / their heart sank.`）机器常并成一句，并了就失掉了停顿的戏剧性。

时间轴只是暂定的，第 6 步会整个重排，所以现在不必精修。

## 2. 分幕

按叙事节拍切，**不要按秒数切**。每幕一条 `cues` 区间（首条号–末条号），一个叙事功能，2–3 个图组。

- 幕长 22–38s，均值约 30s；8–10 句原文大约能切 8 幕。
- 一刀下去不能切在句子半腰（"…sending it flying" 单独起一幕，画面接不上）。
- 序幕（交代时间地点）和尾声（主题升华）各留一幕。
- 一幕超过 40s 就要拆：观众注意力撑不住，而且单个 annotation 的时间轴容易挤。

分幕表连同"每幕画面主体"一起给用户看，确认了再出图（出图要花额度）。

## 3. 出图

一景一图，`1536x1024`，提示词见 `references/style-spec.md`。

**先出第 1 幕一张定调**，让用户看风格，通过了再铺其余。8 张一次出是浪费额度。

每组图描述三件事：**谁 / 在做什么 / 什么情绪**。只写名词会得到一张静物图。

## 4. 后处理

```bash
$PY scripts/prep_scene.py raw/*.png --outdir .        # 抹水印 + 纸色对齐 #EFECDD
```

`$PY` = 包内 venv 解释器（`python3 scripts/bootstrap_env.py` 末行打印的 `PY=`；
通常是 `<包根>/.venv/bin/python`，Windows 是 `.venv\Scripts\python.exe`）。
不确定就 `python3 scripts/paths.py` 看一眼。
下文的 `scripts/` 都相对包根，即 `SKILL.md` 所在目录。

处理完抽一张看：水印有没有残留、纸面有没有补丁色差。米色平涂上任何方块痕迹都很显眼。

## 5. 测区域

```bash
$PY scripts/find_regions.py scene-01-summer-park.png --gap 40
```

列投影自动切组，给出每组的 `x/y/w/h`。把 `x0`（列区间左端）和 `x1`（右端）填进 `scenes.json` 的 `region`。

- `--gap` 从 40 起调：切得太碎（一组被拆成几个）就调大，两组粘成一组就调小。
- 自动切不准时（图组在水平方向交错，如"指向垃圾的手"横跨滑梯右缘），改用显式 `{x,y,width,height}`：裁一小块放大看，量准了直接写死。

## 6. 配音（顺带把时间轴定下来）

```bash
$PY scripts/build_narration.py park-cleanup --srt park-cleanup.srt --voice aria
```

产出逐条 mp3 + `narration.json` + `<srt>-v2.srt`（按真实音长重排）。

**这一步必须排在标注之前。** TTS 不迁就手写的字幕窗口，实测 aria 自然语速约 2.0 词/秒（含 0.3s 条间静音），一条 4.6s 的窗口要念 5.6s。先排画面再配音，就会出现两句叠音、或字幕与画面错位。

换音色、改语速都用 `--voice` / `--speed`；改完 `--force` 重配。

## 7. 标注 + 检查图

```bash
$PY scripts/build_annotations.py park-cleanup             # 写 .annotation.json
$PY scripts/build_annotations.py park-cleanup --dry-run    # 只看时间表
$PY scripts/render_check.py scene-01-x.png scene-01-x.annotation.json check/s1.png
```

区域坐标由脚本按墨迹实测（连通域去噪 + 行/列双向收边），时间锚定到 `anchorCue` 那条字幕的起点。

检查图要逐张看：**每个框紧贴自己的图组、没切到人物、框内没有大片空白、框外没有漏掉的笔画**。

## 8. 渲染 + 合并

```bash
$PY scripts/render_scenes.py park-cleanup --merge
```

默认 `--bare-tip --ink-path skeleton --fps 60`。单幕 25–60 秒。加 `--fps-preview` 出 30fps/720 长边的快速预览。

`--merge` 会调上游 `merge_scenes.py` 拼成 `<project>-silent.mp4`（严格按 `scenes.json` 顺序）。

## 9. 烧字幕 + 混音

```bash
$PY scripts/burn_and_mux.py park-cleanup-silent.mp4 park-cleanup-v2.srt \
    audio/narration.json park-cleanup-final.mp4
```

4 分钟的片子约 3–5 分钟（全片解码 + alpha 合成 + 重编码）。

收工前抽 6–7 个时间点（含每幕开头和交界处）拼一张检查图，逐格核对**字幕内容与画面进度是否对得上**——特别是"字幕说到某物、该物已画出来"这一条。

## 坑位表

| 现象 | 原因 | 处置 |
|---|---|---|
| `prepare_env.py` 卡住或 SIGABRT | 本机 WorkBuddy 自带 Python 3.13 的 `ensurepip` 挂了 | 不用它，改 `uv venv .venv --python 3.13` + `uv pip install --python .venv/bin/python opencv-python numpy av Pillow` |
| `subtitles`/`drawtext` 滤镜不存在 | 本机 ffmpeg 没编进 libass/freetype | 不依赖 ffmpeg 滤镜，用 `burn_and_mux.py`（PIL 贴图逐帧合成）；ffmpeg 只用来探时长 |
| 两句配音叠在一起 | 先排画面后配音，字幕窗口短于朗读时长 | 改成配音先行，`build_narration.py` 重排时间轴后再标注 |
| 字幕出了、画面还没画到 | 各幕元素按幕长等比缩放，句内分布被拉平 | 元素起点锚到 `anchorCue` 的起始时间，不用等比缩放 |
| 幕首黑屏一两秒 | 首元素锚点落在该幕第 3 条字幕上 | `build_annotations.py` 已强制首元素 ≤0.4s 起笔 |
| 只有一只悬空的前臂/手 | 手臂单独成区域，身体锚在后面几条字幕 | 两段锚到**同一条**字幕（`anchorCue` 相同），身体紧接手臂画 |
| 区域框大出一大块空白 | 纸面零散灰点被当成墨迹，把 bbox 撑开 | `clean_mask` 连通域过滤（面积 <14 丢弃）+ `tight_region` 行/列各需 ≥2 墨点 |
| 前一组被后一组"吃掉"一角 | 后区区域会从前面区域的允许掩码里扣掉 | 拆小区域，或给前区加 `protectedRegions`；`build_annotations.py` 重叠 >12% 会告警 |
| 相邻两组粘成一个框 | 列投影间隔小于 `--gap` | 调小 `--gap`，或改用显式 region |
| 纸底偏黄/偏橘 | 图像模型直出的米色不稳定 | `prep_scene.py` 逐通道增益对齐 `#EFECDD`（增益限幅 0.70–1.35，防拉爆） |
| 右下角白色水印 | 图像服务强制加的半透明字 | `prep_scene.py` 检测"三通道同时比纸色亮 6 级"，膨胀后填纸色 |
| 检查图脚本报字体错误 | 上游脚本写死 `C:/Windows/Fonts/msyh.ttc` | 用 skill 内的 `render_check.py`（已加 mac/linux 字体回退），不要改上游文件 |
| 跨幕人物长得不像 | 每幕提示词对人物描述不一致 | 固定外形标签，逐幕原样重复（见 style-spec 第四节） |

## 时间与成本

| 环节 | 单次耗时 | 备注 |
|---|---|---|
| 出图 | 每张 20–60s | 8 张约 40–80 credits，先出 1 张定调 |
| 单幕渲染 | 25–60s | 60fps、长边 1080；`--fps-preview` 减半 |
| 配音 | 每条 1–2s | 57 条约 1 分钟 |
| 烧字幕混音 | 3–5 min | 4 分钟片，全片重编码 |

一部 4 分钟、8 幕、57 条字幕的片子，全流程约 40–60 分钟（不含人工审阅）。
