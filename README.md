# 铅笔素描绘本教学动画（fredgao-srt-pencil-whiteboard-v0.2）

把一段英文原文或 SRT 字幕做成教学动画 MP4：细铅笔线稿、暖米色纸底、元素逐组落笔、
英文字幕烧进画面、英文旁白按句对齐。成品规格 1080×720 / 60fps。

**自包含**：渲染器和配音脚本都随包在 `vendor/` 里，不依赖另外安装别的 skill。
**零硬编码路径**：包放哪都能跑，解释器由脚本自己找。

**版本**：v0.2 —— 相比 v0.1，把 `srt-whiteboard-animation` 与 `fredgao-text-to-speech`
收进 `vendor/`，并清掉全部写死的路径与解释器位置，做到解压即用。

作者：Fred Gao ｜ 公众号：佛瑞德英语教学

---

## 效果

![课堂独坐](docs/still-classroom-tina.jpg)

![两个新人](docs/still-two-newcomers.jpg)

14 秒动图式片段（落笔过程 + 烧入字幕 + 旁白）：[`docs/demo.mp4`](docs/demo.mp4)

上面两图出自读后续写《Maya 的新办公室》（569 词，9 幕 26 个元素、55 条字幕）；
完整成片 3'51"，1080×720 / 60fps。画面里**不出现任何文字**，文字只在烧制的字幕层。

---

## 一、安装（收到包的人看这里）

### 1. 放到技能目录

从 GitHub 拉取（推荐，方便日后 `git pull` 更新）：

```bash
git clone https://github.com/gaofred/fredgao-srt-pencil-whiteboard.git \
  ~/.workbuddy/skills/fredgao-srt-pencil-whiteboard-v0.2
```

或者解压 zip 后把整个文件夹放进来（目录名保持 `fredgao-srt-pencil-whiteboard-v0.2`）：

```
~/.workbuddy/skills/
```

也可以放任意目录，脚本靠自身位置定位，不认固定安装路径。

### 2. 准备环境（只需一次）

```bash
cd ~/.workbuddy/skills/fredgao-srt-pencil-whiteboard-v0.2
python3 scripts/bootstrap_env.py
```

脚本会：

1. 在包内建 `.venv`（优先用 `uv`，没有则标准库 `venv`）
2. 装 `opencv-python / numpy / av / Pillow / edge-tts / python-docx`
3. 逐项验一遍，**末行打印 `PY=<解释器路径>`**

首次 1–3 分钟，取决于网速。装完再跑 `python3 scripts/check_env.py` 应该全 PASS。

### 3. 系统依赖只有一个：ffmpeg

```bash
brew install ffmpeg          # macOS
winget install Gyan.FFmpeg   # Windows
sudo apt install ffmpeg      # Linux
```

配音拼接和音长探测要用 `ffmpeg` / `ffprobe`。
**不需要** ffmpeg 的 libass / freetype——字幕是 Python 逐帧合成的，不用 `subtitles` 滤镜。

---

## 二、用法速览

```bash
SK=~/.workbuddy/skills/fredgao-srt-pencil-whiteboard-v0.2
PY=$SK/.venv/bin/python          # 或 bootstrap_env.py 打印的那个

python3 $SK/scripts/check_env.py                                  # 0. 体检
python3 $SK/scripts/srt_from_text.py passage.txt -o proj/proj.srt # 1. 原文→暂定字幕
$PY      $SK/scripts/prep_scene.py raw/*.png --outdir .           # 4. 抹水印+纸色对齐
$PY      $SK/scripts/build_narration.py proj --srt proj.srt --voice aria  # 6. 配音
$PY      $SK/scripts/render_scenes.py proj --merge                # 8. 渲染
$PY      $SK/scripts/burn_and_mux.py proj-silent.mp4 proj-v2.srt audio/narration.json proj-final.mp4
```

九步全流程、每步的判断规则、13 个已知坑位见 `SKILL.md` 与 `references/pipeline.md`。

---

## 三、目录结构

```
fredgao-srt-pencil-whiteboard-v0.2/
├─ SKILL.md                 九步流程 + 三条硬规则（给 AI 读的入口）
├─ README.md                本文件（给人读的安装说明）
├─ requirements.txt         依赖清单
├─ scripts/
│  ├─ paths.py              ★ 所有路径与解释器解析（改脚本前必读）
│  ├─ bootstrap_env.py      ★ 一键建 venv 装依赖
│  ├─ check_env.py          环境体检
│  ├─ srt_from_text.py      原文→暂定 SRT（词序校验）
│  ├─ cues_to_srt.py        手订字幕清单→SRT
│  ├─ prep_scene.py         抹平台水印 + 纸色对齐 #EFECDD
│  ├─ find_regions.py       列投影自动切图组
│  ├─ build_narration.py    逐条配音 + 按真实音长重排时间轴
│  ├─ build_annotations.py  scenes.json → 每幕 annotation.json
│  ├─ render_check.py       区域编号检查图（mac 字体回退）
│  ├─ check_coverage.py     查孤儿笔画
│  ├─ render_scenes.py      批量渲染 + 合并
│  └─ burn_and_mux.py       PIL 烧字幕 + numpy 铺音轨
├─ vendor/                  ★ 随包分发的依赖（见 vendor/README.md）
│  ├─ whiteboard-renderer/  白板渲染器（MIT，原作者江哥是老登啊）
│  └─ text-to-speech/       逐条配音脚本
├─ references/              视觉规范 / 九步全文 / 实战数据 / 示例 scenes.json
└─ templates/scenes.example.json
```

`scripts/` 下所有脚本都可以直接 `python3 xxx.py --help`。

---

## 四、别人拿到的包为什么能直接跑

| 常见交付问题 | 本包怎么处理 |
|---|---|
| 依赖另一个 skill，对方没装 | 渲染器 + 配音脚本复制进 `vendor/` |
| 写死了 `/Users/xxx/...` | 全部改为 `Path(__file__)` 推导，见 `scripts/paths.py` |
| 写死了某台机器的 python 路径 | `paths.py` 按「包内 venv → `$FREDGAO_PY` → 当前解释器 → PATH」逐个探，按依赖齐全度挑 |
| venv 打进包里，换机器就废 | 不带 venv，`bootstrap_env.py` 在对方机器上重建 |
| 缺个模块报一堆 traceback | `check_env.py` 先说缺什么，再给该敲的命令 |
| 上游包更新了怎么办 | `vendor/README.md` 写了覆盖哪几个文件 + 回归测试做法 |

---

## 五、排障

**`check_env.py` 说渲染依赖 FAIL**
→ 跑 `python3 scripts/bootstrap_env.py`。装不上就先装 uv：`curl -LsSf https://astral.sh/uv/install.sh | sh`
（有些机器的 `ensurepip` 是坏的，标准库 `venv` 会 SIGABRT，uv 能绕过。）

**配音报 403**
→ `edge-tts` 版本旧了。`pip install -U edge-tts`，必须 ≥7.3.0（7.3 起改 v2 签名）。

**配音报 `NoAudioReceived`**
→ 这个音色本身下线了，不是环境问题。跑 `$PY vendor/text-to-speech/scripts/check_voices.py --quick` 归因，换同口音别的音色。

**想换音色**
→ `build_narration.py --voice sonia`（英音女）/ `--voice andrew`（美音男）。
完整 59 个音色见 `vendor/text-to-speech/scripts/tts.py --list`。

**想用自己已有的 python 环境**
→ `export FREDGAO_PY=/path/to/python`，`paths.py` 会优先用它（前提是依赖齐全）。

---

## 六、许可

本包采用 **CC BY-NC-SA 4.0**（署名—非商业性使用—相同方式共享），全文见 `LICENSE`。
课堂使用、校内印刷、教研分享、非营利公众号推送，均无需额外授权；商业用途需另行取得授权。

`vendor/whiteboard-renderer/` 是第三方 MIT 组件（原作者：江哥是老登啊），保留原许可，
不受上面的 CC 许可约束。详见 `NOTICE` 与 `vendor/README.md`。
