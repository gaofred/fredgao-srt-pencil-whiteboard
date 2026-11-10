---
name: fredgao-srt-pencil-whiteboard-v0-2
description: （v0.2）把一段英文原文或 SRT 字幕，做成铅笔素描绘本风的教学动画 MP4——细铅笔线稿、暖米色平涂纸底、元素逐组落笔（分镜遮罩揭示）、英文字幕烧进画面、英文旁白按句对齐。专为读后续写范文、课文、故事类语篇的视频化设计，成品对标"练习15读后续写"那类教学片：1080×720、无握笔手、单色近黑、日式绘本速写。本包自包含（渲染器与配音脚本随包在 vendor/，首次跑 bootstrap_env.py 装依赖），放任何目录都能运行。触发词：做成白板动画、铅笔素描视频、读后续写做成视频、把这篇范文做成动画、生成教学视频、SRT 转动画、绘本风动画、逐句画出来、配旁白的教学片、课文视频化、续写范文配画。当用户给出英文原文/故事并要求"像那个视频一样的风格"时使用。与 srt-whiteboard-animation 的区别：那个是通用白板涂鸦（含握笔手、上色），本 skill 是铅笔素描教学片风格（无手、单色、烧字幕、配音反推时间轴）。｜作者：Fred Gao｜公众号：佛瑞德英语教学
agent_created: true
---

# 铅笔素描绘本教学动画 v0.2（原文/SRT → MP4）

> 版本：**v0.2**（自包含 + 零硬编码路径）。目录名 `fredgao-srt-pencil-whiteboard-v0.2`；
> `name` 字段因技能规范只允许小写字母/数字/连字符，写作 `-v0-2`。

把英文原文变成一支"逐句画出来"的教学片：句子念到哪，画面就画到哪，
字幕烧在底部，旁白顺着句子走。

## 包内已有的两半能力（不用另装 skill）

| 在 `vendor/` 里 | 提供什么 | 本 skill 补什么 |
|---|---|---|
| `whiteboard-renderer/`（上游 `srt-whiteboard-animation` 的脚本副本，MIT） | 分区遮罩揭示 + 骨架笔迹渲染器 + SRT 解析 | 铅笔素描视觉规格、无握笔手参数、批量编排 |
| `text-to-speech/`（`fredgao-text-to-speech` 的脚本副本） | 逐条 TTS（59 音色，Edge TTS 免密钥） | 配音反推时间轴、按句锚定元素起笔 |

**路径规则：本文件所在目录就是包根，记作 `$SK`。**
包内一律用它拼路径，不要写 `~/.workbuddy/skills/...`，也不要假设 python 在哪。

## 两条路，先认清楚

- **已有 SRT**（自己切好的字幕）→ 从第 6 步进（配音）。
- **只有一段英文原文**（最常见：读后续写范文）→ 从第 1 步进。

## 环境（首次一次性）

```bash
SK=<本 skill 目录，即 SKILL.md 所在目录>
python3 "$SK/scripts/bootstrap_env.py"   # 建包内 .venv 并装依赖，末行打印 PY=<路径>
PY=<上一步打印的路径>                     # 通常是 $SK/.venv/bin/python
python3 "$SK/scripts/check_env.py"       # 全 PASS 才开工
```

- 依赖清单在 `requirements.txt`（opencv / numpy / av / Pillow / edge-tts / python-docx）。
- 系统只要有 `ffmpeg`（拼接配音、探音长）。**不需要** libass/freetype。
- 想用自己已有的解释器：`export FREDGAO_PY=/path/to/python`，`scripts/paths.py` 会优先用它。
- 路径全部从 `Path(__file__)` 推出；包放在哪都能跑，也支持 Windows（venv 路径自动切换）。
- 想单独确认路径解析：`python3 "$SK/scripts/paths.py"`，会列出每个文件 OK/MISS 和两个解释器。

`$PY` 里是渲染依赖，`srt_from_text.py` / `cues_to_srt.py` / `build_narration.py`
用系统 `python3` 也能跑（后两者只依赖 ffprobe 和配音脚本）。

## 九步流程

三处**必须停下来等用户点头**，标了 🚦。

| # | 做什么 | 命令 / 要点 |
|---|---|---|
| 0 | 环境体检 | `python3 "$SK/scripts/check_env.py"` |
| 1 | 原文 → 暂定字幕 | `python3 "$SK/scripts/srt_from_text.py" passage.txt -o proj/proj.srt`，**人工过切点** |
| 1.5 | 手订字幕 → SRT | 把终稿写成一行一条的 `cues.txt`，`python3 "$SK/scripts/cues_to_srt.py" cues.txt -o proj/proj.srt`（改切点不再碰时间码） |
| 2 | 分幕 | 按叙事节拍切，一幕 22–38s、2–3 个图组；🚦 分幕表给用户确认 |
| 3 | 出图 | 一幕一图 `1536x1024`，提示词见 `references/style-spec.md`；🚦 先出第 1 幕定调 |
| 4 | 后处理 | `$PY "$SK/scripts/prep_scene.py" raw/*.png --outdir .`（抹水印 + 纸色对齐 `#EFECDD`） |
| 5 | 测区域 | `$PY "$SK/scripts/find_regions.py" x.png --gap 40`，把 `x0/x1` 填进 `scenes.json` |
| 6 | 配音 | `$PY "$SK/scripts/build_narration.py" proj --srt proj.srt --voice aria`（顺带重排时间轴）。用户要挑音色：先 `present_files` 打开 `vendor/text-to-speech/assets/voices.html`（45 音色试听，离线可用），别刷音色列表 |
| 7 | 标注 + 检查图 | `$PY "$SK/scripts/build_annotations.py" proj` → `$PY "$SK/scripts/render_check.py" …`；🚦 逐张看框 |
| 7.5 | 覆盖率校验 | `$PY "$SK/scripts/check_coverage.py" proj` —— 必跑，漏画笔画在检查图上看不出来 |
| 8 | 渲染合并 | `$PY "$SK/scripts/render_scenes.py" proj --merge` |
| 9 | 烧字幕混音 | `$PY "$SK/scripts/burn_and_mux.py" proj-silent.mp4 proj-v2.srt audio/narration.json proj-final.mp4` |

每步的细节、判断规则、命令原文都在 `references/pipeline.md`；
模板 `scenes.json` 见 `templates/scenes.example.json`（照抄改字段即可）。

## 三条硬规则

**一、画面里零文字。** 字幕是后期烧的，图里再出字就是双重文字。
需要表达"提议/标语/成果"时用图形符号：灯泡＝灵光、围圈＝组队、嫩芽＝改变、放射线＝阳光。
提示词必须带 `no text, letters, numbers or labels of any kind anywhere in the image`。

**二、配音先行，时间轴跟着配音走。** 不要先排画面再配音。
实测 TTS 念得比手写窗口慢（4.6s 窗口念 5.6s），硬塞会叠音；
按幕长等比缩放也不行（句内语速不均匀，"说到某物"时该物常还没画出来）。
正确顺序：逐条配音 → 按真实音长重排 SRT → 元素起点锚到 `anchorCue`。

**三、时序三条约束缺一不可**（`build_annotations.py` 已内置）：
起点锚字幕、首元素 ≤0.4s 起笔、串行顺延且末元素不越幕尾。

## 脚本清单

| 脚本 | 作用 | 解释器 |
|---|---|---|
| `bootstrap_env.py` | 建包内 venv 装依赖，末行打印 `PY=` | `python3` |
| `paths.py` | 路径与解释器解析（排障先跑它） | `python3` |
| `check_env.py` | 依赖体检，缺什么给修复命令 | `python3` |
| `srt_from_text.py` | 原文 → 暂定 SRT（词序逐字校验，丢字自动回退） | `python3` |
| `cues_to_srt.py` | 手订字幕清单（一行一条）→ SRT，人工过切点后用 | `python3` |
| `prep_scene.py` | 抹平台水印 + 纸色对齐目标色 | `$PY` |
| `find_regions.py` | 列投影自动切图组，输出像素坐标 | `$PY` |
| `build_narration.py` | 逐条 TTS + 按真实音长重排 SRT 与时间轴 | 自动挑带 edge_tts 的 |
| `build_annotations.py` | 读 `scenes.json` → 每幕 `annotation.json` | `$PY` |
| `render_check.py` | 区域编号/方向检查图（已修 mac 字体回退） | `$PY` |
| `check_coverage.py` | 查"孤儿笔画"：墨迹落在所有区域之外 → 末帧会缺线 | `$PY` |
| `render_scenes.py` | 批量渲染，`--merge` 自动合并无声片 | 自动挑带 cv2/av 的 |
| `burn_and_mux.py` | PIL 烧字幕 + numpy 铺音轨，一次编码出片 | `$PY` |

`build_narration.py` 与 `render_scenes.py` 会自己调 `paths.py` 挑解释器，
所以用 `python3` 启动它们也不会因为缺模块而崩 —— 但前提是依赖确实装在某个解释器里。

## 交付前自检

- [ ] 抽 6–7 个时间点拼图，逐格核对字幕与画面进度一致（尤其"说到某物、该物已画出"）
- [ ] 每幕开头无黑屏空等；末元素收笔在幕尾之前
- [ ] 字幕不超两行、不被裁切、不压住关键笔画
- [ ] 成片规格：`ffprobe` 看 1080×720 / 60fps / 有音轨；音轨峰值归一到 0.89
- [ ] 跨幕人物外形一致（对照 style-spec 第四节的固定标签）

## 已知限制

- 上游渲染器逐区域落墨，**同一区域内的元素无法再做先后**；需要更细的先后就拆区域。
- `burn_and_mux.py` 要走全片解码 + 重编码，4 分钟片 3–5 分钟，别指望秒出。
- 系统 ffmpeg 若无 libass/freetype，**不要试图用 `subtitles`/`drawtext` 滤镜**，本 skill 也不依赖它们。
- 图像服务的右下角水印必须后处理，出图时提示"右下角留空"只是减少干扰，不能替代擦除。

## 参考

- `README.md` — 安装、分发、排障（给人看的入口）
- `vendor/README.md` — 随包依赖的来源、许可、升级做法
- `references/style-spec.md` — 视觉硬指标、提示词骨架、出图四项验收
- `references/pipeline.md` — 九步全文、13 条坑位表、耗时成本
- `references/worked-example.md` — park-cleanup 实战数据（480 词原文 → 3'59" 成片）
- `references/example-park-cleanup-scenes.json` — 8 幕 21 元素的完整 `scenes.json`，可当模板或回归测试
- `templates/scenes.example.json` — 带字段注释的最小样例
