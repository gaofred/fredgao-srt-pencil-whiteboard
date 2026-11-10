#!/usr/bin/env python3
"""把整段英文原文切成分幕字幕（草稿），并按配音语速给出暂定时间轴。

用法：
  python3 scripts/srt_from_text.py passage.txt -o project/passage.srt
  python3 scripts/srt_from_text.py passage.txt -o out.srt --voice-check aria

输出：
  .srt 文件（UTF-8，无 BOM）
  逐条清单打印到终端（词数 / 时长 / 文本）

⚠️ 这是**草稿**。原文措辞一字不改（教学材料要能跟读），但切点一定有人工判断：
   作者有意断句的地方（如 "But as they stepped into the park, their heart sank."）
   机器可能并成一句。切完必须过一眼。

时间轴是暂定的：真实时长以 TTS 念完为准（下一步 build_narration.py 会重排），
所以这里的数字只要量级对就行，不必精修。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 实测校准（park-cleanup 案例，57 条字幕 / 480 词 / 成片 239.6s）
#   词数 4–14，均值 8.4；aria 朗读净语速约 2.2 词/秒，条间另留 0.3s
#   （含间隔的等效语速是 2.0 词/秒——两个口径别混用）
WPS = 2.2
GAP = 0.30
MIN_DUR = 2.6

SENT_END = re.compile(r"(?<=[.!?])(?=\s)|(?<=[.!?][\"'\u2019\u201d])(?=\s)")
# 只在「标点 + 空白」处断；写成零宽断言会把 "difference,\"" 拆成 "difference," + "\""
# 多切出一个孤立词元，词序校验随即失败、整段回退成一条。
SOFT_BREAK = re.compile(r"(?<=[,;\u2014:])\s+")
# 切不动时的次选切点：在这些词**前面**断，保住的都是完整短语
CONNECTORS = {
    "and", "but", "or", "so", "yet", "then", "as", "because", "while", "when",
    "which", "that", "who", "whose", "where", "for", "with", "without",
    "after", "before", "until", "though", "although", "if", "since", "once",
}


def normalize(text: str) -> str:
    """只压空白，不动标点与用词。"""
    text = text.replace("\r\n", "\n").replace("\u00a0", " ")
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("\n")]
    return "\n".join(p for p in paras if p)


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        for s in SENT_END.split(para.strip()):
            s = s.strip()
            if s:
                out.append(s)
    return out


def _nearest(opts: list[tuple[int, int]], mid: float) -> int:
    """opts = [(词位置, 切点值)]，取词位置最靠中线的那个切点。"""
    return min(opts, key=lambda t: abs(t[0] - mid))[1]


def split_long(sentence: str, max_words: int, depth: int = 0) -> list[str]:
    """超长句逐级劈开：先在逗号/分号处切，切不动再退到连接词前，最后才硬劈。"""
    words = sentence.split()
    n = len(words)
    if n <= max_words or depth > 6:
        return [sentence]

    # 一级：软停顿（逗号 / 分号 / 破折号 / 冒号）。cum 是词位置，i+1 是 part 序号，
    # 两者不能混用——拿 part 序号去比词中线，选出来的切点会离谱。
    parts = [p.strip() for p in SOFT_BREAK.split(sentence) if p and p.strip()]
    if len(parts) > 1:
        cum, opts = 0, []
        for i in range(len(parts) - 1):
            cum += len(parts[i].split())
            opts.append((cum, i + 1))
        k = _nearest(opts, n / 2)
        left, right = " ".join(parts[:k]), " ".join(parts[k:])
        if left and right:
            return (split_long(left, max_words, depth + 1)
                    + split_long(right, max_words, depth + 1))

    # 二级：连接词前断（"…wrapped up, / and the first days…" 就是这一刀）
    cands = [i for i in range(1, n) if words[i].lower().strip('"\u201c\u201d,;:') in CONNECTORS]
    if cands:
        k = _nearest([(i, i) for i in cands], n / 2)
        return (split_long(" ".join(words[:k]), max_words, depth + 1)
                + split_long(" ".join(words[k:]), max_words, depth + 1))

    # 三级：确实无处可断，按词数中线硬劈
    k = n // 2
    return (split_long(" ".join(words[:k]), max_words, depth + 1)
            + split_long(" ".join(words[k:]), max_words, depth + 1))


def merge_short(chunks: list[str], min_words: int, max_words: int) -> list[str]:
    """收拾短碎片：先并进前一块；仍过短的（如姓名列表 "Max,"）并进后一块。

    两条细节：
      · 以逗号收尾的碎片是列表项，必须向后并，向前并会把 "…them, Max, Ava," 拼成一句；
      · 容许超上限 2 词（15–16 词），否则 "Max, Ava, and Sam had … park." 这种
        14 词的完整句永远并不进去，只能拆得七零八落。
    """
    if not chunks:
        return []
    cap = max_words + 2

    out: list[str] = []
    for c in chunks:
        nc = len(c.split())
        if (nc < min_words and out and not c.rstrip().endswith(",")
                and len(out[-1].split()) + nc <= cap):
            out[-1] = out[-1] + " " + c
        else:
            out.append(c)

    j = 0
    while j < len(out) - 1:
        if len(out[j].split()) < min_words and len(out[j].split()) + len(out[j + 1].split()) <= cap:
            out[j + 1] = out[j] + " " + out[j + 1]
            out.pop(j)
        else:
            j += 1
    return out


def fmt(t: int) -> str:
    return f"{t // 3600000:02d}:{t % 3600000 // 60000:02d}:{t % 60000 // 1000:02d},{t % 1000:03d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", help="原文 .txt")
    ap.add_argument("-o", "--out", required=True, help="输出 .srt")
    ap.add_argument("--max-words", type=int, default=14)
    ap.add_argument("--min-words", type=int, default=4)
    ap.add_argument("--wps", type=float, default=WPS, help="暂定语速，词/秒")
    ap.add_argument("--gap", type=float, default=GAP, help="条间静音，秒")
    ap.add_argument("--lead-in", type=float, default=0.0, help="片头静默，秒")
    a = ap.parse_args()

    raw = Path(a.text).read_text(encoding="utf-8")
    norm = normalize(raw)

    cues: list[str] = []
    for sent in split_sentences(norm):
        cues.extend(merge_short(split_long(sent, a.max_words), a.min_words, a.max_words))

    # 校验：把带标点原文压缩成纯词序列，和切分结果比对，确保一个字都没丢
    def words(s: str) -> list[str]:
        return re.findall(r"\S+", s)

    src, got = words(norm), words(" ".join(cues))
    if src != got:
        print("[warn] 切分后词序列与原文不一致，已回退为整段单条", file=sys.stderr)
        cues = [norm.replace("\n", " ")]

    t = int(a.lead_in * 1000)
    lines: list[str] = []
    stats = []
    for i, c in enumerate(cues, 1):
        n = len(c.split())
        dur = max(MIN_DUR, n / a.wps + a.gap)
        end = t + int(round(dur * 1000))
        lines.append(f"{i}\n{fmt(t)} --> {fmt(end)}\n{c}\n")
        stats.append((i, n, dur, t / 1000, c))
        t = end

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(lines), encoding="utf-8")

    ns = [s[1] for s in stats]
    ds = [s[2] for s in stats]
    print(f"{a.out}  {len(cues)} 条  总长 {t/1000:.1f}s")
    print(f"词数 {min(ns)}–{max(ns)}（均值 {sum(ns)/len(ns):.1f}）  "
          f"每条 {min(ds):.1f}–{max(ds):.1f}s\n")
    for i, n, dur, start, c in stats:
        print(f"  {i:3d}  {start:6.1f}s +{dur:4.1f}s  {n:2d}词  {c}")
    print("\n下一步：人工过一遍切点（作者刻意断句处常被机器并句），再跑 build_narration.py。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
