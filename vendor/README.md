# vendor —— 随包分发的依赖（不要单独改这里的渲染器）

这个目录的存在只为一件事：**把本技能包发给别人，别人解压就能跑**，
不必先去装另外两个 skill。

| 子目录 | 来源 | 许可证 | 放了什么 |
|---|---|---|---|
| `whiteboard-renderer/` | [srt-whiteboard-animation](https://github.com/geeklee/srt-whiteboard-animation)（作者：江哥是老登啊） | MIT，见 `whiteboard-renderer/LICENSE` | 渲染器与字幕解析脚本 + 握笔图 |
| `text-to-speech/` | fredgao-text-to-speech（作者：Fred Gao｜公众号：佛瑞德英语教学） | 随本包 | 逐条配音脚本、音色自检、**45 音色试听页** |

## 只复制了用得到的部分

`srt-whiteboard-animation` 原包含 12MB 演示素材和一份 212MB 的 `.venv`。
这里只保留运行时真正被调用的脚本：

```
whiteboard-renderer/
  scripts/render_stream_whiteboard.py   逐幕渲染主程序
  scripts/stream_render.py              笔迹生成核心（被上面 import）
  scripts/merge_scenes.py               多幕合并
  scripts/parse_srt.py                  SRT 解析 + 建议分镜
  assets/drawing-hand.png               握笔手（默认 --bare-tip 不叠，留着备用）
  LICENSE                               MIT 原文，必须随包保留
```

**没有复制 `.venv`**。venv 里全是绝对路径，换机器必然失效；
正确做法是收到包后跑一次 `python3 scripts/bootstrap_env.py`，在包内重建。
也没有复制 `examples/`（11MB 的 gif/mp4 演示），它们跟运行无关。

`text-to-speech/assets/voices.html` 保留了：1.9MB 的单文件试听页，音频 base64 内嵌、
不联网也能听，45 个音色同一句横向对比。用户要挑音色时直接 `present_files` 打开它，
比刷 59 行音色列表有用。`last_check.json` 是最近一次全量自检的时间戳。

## 改上游代码的原则

本包对 vendor 只做了一处改动：`text-to-speech/scripts/tts.py` 的
`_find_ffmpeg()` 去掉了写死的机器路径，改为「环境变量 → 包内 bin/ → PATH」。
渲染器脚本**一行没改**——它们本来就靠 `__file__` 自定位，天然可移植。

升级上游时的做法：把新版 `render_stream_whiteboard.py` / `stream_render.py` /
`merge_scenes.py` 覆盖过来，重跑一次 `references/worked-example.md` 里的回归测试
（同一份 scenes.json 应产出逐字节一致的 annotation）。
