# 视觉规格与出图提示词

本 skill 对齐的参照物是一支"铅笔素描绘本"教学视频（学员提供的 `练习15读后续写.mp4`）。
它**不是**上游 `srt-whiteboard-animation` 默认那套"Notion 极简涂鸦 + 握笔手 + ink→color 上色"。
两套的差别逐项列在下面，照错的任何一条，成品气质就不对了。

## 一、目标外观（硬指标）

| 维度 | 值 | 怎么落地 |
|---|---|---|
| 画幅 | 1080×720（3:2） | 出图用 `1536x1024`，渲染时 `--cap-long-edge 1080` 自动落到 1080×720 |
| 画风 | 细铅笔线 + 稀疏平行排线阴影，日式绘本速写 | 提示词里写死 `2B pencil`/`parallel hatching`/`Japanese picture-book` |
| 色彩 | 近黑单色，无任何彩色填充 | 提示词 `monochrome near-black line art`、`no color fill` |
| 背景 | 纯平涂米色，**无纸纹、无边框** | 提示词 `plain flat warm ivory background (#F2EFE0)`、`no paper texture, no border` |
| 后处理纸色 | `#EFECDD` | `prep_scene.py` 逐通道增益对齐（模型直出的纸色一定偏黄偏橘） |
| 笔迹 | **无握笔手**，元素逐组揭示 | 渲染加 `--bare-tip`；提示词里也写 `no hand holding a pen`（双保险） |
| 字幕 | 烧进画面底部，Arial Bold 36px，`#443E2F`，居中，最多两行，底距 57px | `burn_and_mux.py`，字号与底距按画高等比缩放 |
| 结构 | 每幕 2–3 个**相互分离**的图组，横向铺开，留白充足 | 提示词按"左组 / 中组 / 右组"分别描述 |

## 二、为什么图里绝对不能有文字

三条理由，任何一条都足以否掉"顺手加个标语牌"的想法：

1. 上游渲染器的分区揭示按墨迹掩码走，文字笔画细碎，笔迹路径会切得很难看；
2. 字幕是后期烧进去的，图里再出现字就是双重文字，学生会串行；
3. 教学场景要"看图即懂"，画面里冒英文单词等于给读图题加干扰。

所以提示词里必须出现：
`no text, letters, numbers or labels of any kind anywhere in the image`

需要表达"提议""标语""标题"这类概念时，用**图形符号**替代：
灯泡＝灵光一现、围圈＝组队成立、嫩芽＝改变发生、放射线＝阳光/成果。

## 三、提示词骨架（逐字可改的是方括号里的部分）

```
A pencil sketch illustration in a gentle Japanese picture-book style, drawn with fine dark
graphite lines and light parallel hatching for shading, entirely monochrome near-black line
art on a plain flat warm ivory background (#F2EFE0). Absolutely no color fill, no paper
texture, no border, no frame, and no text, letters, numbers or labels of any kind anywhere
in the image. Wide 3:2 landscape canvas with generous empty ivory space, the drawings
arranged as separate small illustration groups on the blank page. Keep the bottom-right
corner completely empty of drawing.

Left group: [左组内容]
Centre group: [中组内容，可省]
Right group: [右组内容]

Style: thin slightly uneven 2B pencil line work, shading only with sparse parallel hatching,
simple faces with minimal features, natural proportions rather than cartoonish, calm and
restrained literary illustration mood. No hand holding a pen, no brush, no drawing tool
anywhere in the frame.
```

三条经验：

- **`Keep the bottom-right corner completely empty`** 必写。那块要压水印，也常被字幕遮挡。
- **每组描述自带动作与情绪**，不要只写名词。图组之间要能读出"谁在干什么"。
- **人物年龄写明** `about thirteen years old`。不写会出成小学生或成年人，跨幕不一致。

## 四、出场人物的跨幕一致性

同一人物要在 8 幕里长得像同一个人，靠**固定外号式描述**，每幕重复一遍：

- 男孩 Max：`a boy of about thirteen with short tousled hair`
- 女孩 Ava：`a girl of about thirteen with a ponytail`
- 男孩 Sam：`a second boy of about thirteen in a hooded top`

不要写名字（模型会把名字画成文字），只写外形标签。

## 五、出图后的四项验收

每张出图必须过这四关，任何一关不过就重出或后处理：

| 关卡 | 判断 | 不过怎么办 |
|---|---|---|
| 零文字 | 画面任何位置有没有字母、数字、招牌 | 重出（后处理擦不干净） |
| 单色 | 有没有彩色填充、暖黄纸纹 | 纸色用 `prep_scene.py` 校；有彩色填充则重出 |
| 分组分离 | 相邻图组之间有没有明显空白列 | 用 `find_regions.py --gap` 粗查；粘在一起就重出或改用显式 region |
| 无手 | 有没有握笔的手、笔杆、画笔 | 提示词已有；仍出现就重出（`--bare-tip` 只能去掉渲染器自加的手） |

## 六、水印

图像服务的右下角常强制压白色半透明水印。特征：**三通道同时比纸色亮 6 级以上**，
集中在角落。`prep_scene.py` 按这个特征检测、膨胀 2 次（7×7 核）后填成纸色，
再整图做逐通道增益。若某张水印跑到别处，用 `--outdir` 单张处理后目视复核一遍
（橡皮擦痕迹在米色平涂上比在线稿区更容易看出来）。
