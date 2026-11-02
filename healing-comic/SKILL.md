---
name: healing-comic
description: 把长文 / PDF / 指南转成小红书式「一二布布」可爱治愈简笔情侣漫画套图（3:4 竖版、6–9 页、原创双角色、中文由脚本后期合成）。当用户说「把这份资料做成治愈漫画」「改成小红书一二布布那种简单的漫画」「文章转多格漫画」「把 20 张文字卡改成漫画」时使用。
---

# healing-comic：把长文压成一套可爱治愈漫画

一个 SKILL.md + 一个 Pillow 脚本，不需要 MCP、不需要排版服务、不需要把中文交给生图模型。

**核心原则：一页 = 一个动作 + 一句台词 + 两个角色。** 治愈感来自「少」，不是来自画得多。想塞进去的内容一律删掉，留到下一篇。

## 何时用 / 何时别用

- 用：长文、指南、PDF、课程笔记 → 小红书 6–9 页漫画套图；已有 20 张文字卡想换风格；想做轻 IP 连载。
- 别用：要精确数据表格、法律/医疗条款原文、需要逐字保留的长文；那种用知识卡片 skill，不要漫画化。
- 别用：需要 20 格以上连载剧情、复杂分镜、多角色换装。见 `references/github-skills.md` 里的条漫 / 小说转漫画方案。

## 输出契约

```
<project>/
├── storyboard.md          # 分镜表（人读、可改）
├── spec.json              # 排版输入（机器读）
├── art/00-cover.png …     # 无字底图，永不覆盖
└── pages/
    ├── 01.png …           # 1080×1440 成品
    ├── preview.html       # 整套预览（浏览器打开）
    └── preview.jpg        # 拼版缩略图（查缩略图可读性）
```

`art/` 是原件，`pages/` 是派生物。**绝不把文字直接画回 `art/`**，改文案只需重跑 compose.py。

## 固定视觉规格（一次定死，全套不换）

| 项 | 值 |
|---|---|
| 画布 | 1080×1440（3:4 竖版，小红书信息流最优） |
| 角色 A（一二） | 白色小熊猫：纯白圆身、实心黑圆耳、黑色熊猫眼罩、小眼睛、黑蝴蝶领结、白色短手、黑色小脚 |
| 角色 B（布布） | 奶茶棕小熊：略大一圈、圆耳、奶白口鼻、黑点眼、小鼻子；原作不戴围巾，别加 |
| 线条 | 细而干净的近黑描边，无渐层、无阴影、无纹理 |
| 色板 | 奶油底 #FFF8EE、蜜桃 #F6C9B4、焦糖 #D9A066、雾蓝 #A9C6D9、芥末 #E8B44A、字 #4A3B32 |
| 构图 | 角色居中偏下，**上 1/3 与下 1/4 必须留白**给标题和气泡；文字全部左对齐，共享 72px 左边线 |
| 版式 | **无页眉小标签、无页码、无装饰下划线**（eyebrow / index numbering / 装饰线，taste-skill 明令删除）；出处信息全部并入页脚 |
| 字号 | 一个超大 + 一个小：大标题 80px Medium（带奶油描边光环）、支持句 42px、台词 46px Medium（气泡内**左对齐**）、页脚 26px |
| 标题 | 大标题 ≤8 字一行；副标题 ≤14 字；台词 ≤18 字 × 最多 3 行；页脚一行 ≤36 字 |

> ⚠️ **版权**：「一二和布布」是黄小 B 于 2018 年创作的受保护 IP。本技能提供两种模式：**高相似版**（`examples/art/`，按原作特征重绘，个人笔记可用，注意署名与平台 AI 标识）与**原创版**（`examples/art-original/` 的「白团子 + 阿棕」，商用 / 长期做号请用这套）。

## 工作流（7 步，别跳步）

### 1. 选最小可用主题
不要「把整本书做成漫画」。13 章 104 条 → 一次只讲 **4–8 个点**。先问：读者看完这一套能记住哪一句？写不出这句话就换角度。
产出：一句「钩子」+ 4–8 个页码标题。

### 2. 建角色卡（一致性核心）
把上表两行**一字不差**写进每一页的生图 prompt。描述越具体越稳；「黑色圆耳、蝴蝶结、围巾」是三个识别锚点，任何一页都不能漏。
**先生成封面（同时挂 1–3 张一二布布原图做参考），后续每页挂「新封面 + 1 张原图」**，比纯文字重复描述稳得多。

### 3. 写分镜表
每页一行，字段固定：

| page | 源文出处 | 一个动作 | 顶部标题 ≤12字 | 气泡台词 ≤18字 | 底部金句 ≤24字 |
|---|---|---|---|---|---|

把原文的「判断 / 第一句 / 两种回应 / 红线 / 依据」压成「一个画面 + 一句能说出口的话」。**原文的长句只进正文配文，不进画面。**

### 4. 生图提示词（复制改 SCENE 即可）

```
Use the two characters and the exact art style from the reference images
(attach 1-3 一二布布 original pictures as design reference).
CHARACTER 1 (white panda cub): small chubby pure-white round body, two solid
black round ears, two black oval panda eye patches, small simple eyes, a small
black bow tie, short white stubby arms, little black feet.
CHARACTER 2 (brown bear cub): slightly bigger chubby milk-tea-brown round
body, small round ears, pale cream muzzle, small black dot eyes, tiny nose,
short stubby limbs, no scarf.
Thin clean dark outlines, completely flat coloring, plain warm-white
background, soft pastel accents, no gradients, no shading, no texture, simple
rounded shapes, cozy warm, vertical portrait 3:4, one single scene,
no panel borders.

SCENE: <一个动作、一个情绪、最多两个道具，写具体>

LARGE clean empty cream space across the top third and the bottom quarter for
later text overlay. CRITICAL: absolutely no text, no Chinese characters, no
letters, no numbers, no captions, no speech balloons, no speech bubbles,
no watermark, no logo.
```

### 5. 只生成「无字底图」
**所有中文一律不交给图片模型。** 生图模型写中文必然错字、糊字、伪字；连「123」「①」都别让它画。气泡也用脚本画，别指望模型留出可用空白。
每页一个连续画面，不要 2×2 四格（格子越多角色越容易漂移）。

### 6. 后期合成中文
```sh
python3 scripts/compose.py spec.json \
  --font ~/fonts/LXGWWenKai-Regular.ttf \
  --font-medium ~/fonts/LXGWWenKai-Medium.ttf \
  --outdir pages --html --contact-sheet   # 渲染后自动 gate：超宽/超行直接报错
```
脚本画：顶部小标签 + 大标题 + 手绘下划线 + 白色圆角气泡（带小尾巴）+ 页脚出处。自动按中文折行、字号自适应、保留 `art/` 原图。
没有中文字体时先跑 `scripts/fetch_font.sh`，或设 `COMIC_FONT=/path/to/font.ttf`。

### 7. 交付前四查 + 发布
- **缩略图查**：把 `preview.jpg` 缩到 200px 宽，标题还认得出吗？认不出就加粗加短。
- **角色查**：6 页里蝴蝶结 / 围巾 / 耳朵有没有丢？丢的那页用封面作参考重生成。
- **字数查**：台词 ≤18 字、标题 ≤20 字、配文 ≤1000 字、图片 ≤18 张（推荐 6–9 张）。
- **合规查**：勾选平台「AI 生成合成内容」标识；署名原书 + 许可证；保留原书「不是心理治疗 / 危机先转介」免责句。
  小红书 2026-02 起要求 AI 图文主动标识，未标识会限制分发（见 `references/cases.md`）。

## 版式依据（taste-skill 审校）

排版规则对照 [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill)（108k★，anti-slop 设计品味 skill）逐条审过：删 eyebrow 与页码、全左对齐、一个超大一个小、无渐变无阴影无细线、标题两行以内、图片上的文字用中性描边光环（其唯一允许的例外）、渲染后用 gate 实测字宽行数（inspect 的本地等价物）。对网页规则不适用的两条按媒介惯例保留：对话气泡的描边（漫画的语义元素，不是 UI 分隔线）与气泡尾巴。

## 复刻模式（--layout xhs）

对参考帖 8 张原图先做逐像素测量再复刻：1080×1440 **满版插画**（左右底画到边缘，无白框、无页码、无页脚）、顶部 12% 干净纸条放**居中**标题（内容页 54px / 封面 76px 两行）、气泡画在画面中部 35–55% 的干净带、色板 纸 `#F5F1E8` / 蜜桃 `#F0D1C0` / 棕 `#A48476` / 墨 `#301412` / 灰蓝 `#BCCAD0`。底图生成时把参考帖原图直接挂给生图模型（最强风格锚点），提示词固定要求「顶部 12% 留白 + 35–55% 高度留干净带 + 画到四边」。合成后用同一把尺子自检：顶条亮度、四边是否满版、主色是否贴近。测量数据与自检结果见 `references/copy-复刻版-8件事.md`。

## 风格为什么好抄（一二布布类漫画的量化拆解）

| 特征 | 做法 | 省掉了什么 |
|---|---|---|
| 两个圆形角色 | 头身比 1:1，只靠耳朵 / 围巾区分 | 表情演技、人体、透视 |
| 三色平涂 | 白 + 棕 + 一个点缀色 | 上色、光影、背景绘制 |
| 一页一动作 | 不画分镜、不画时间流动 | 分镜设计、跨格连贯 |
| 一句对话 | 口语、 ≤18 字、带一点反差萌 | 旁白、论述、信息密度 |
| 情绪转折 | 前半页「我以为是…」，后半页「其实是…」 | 说教，换成被理解的感觉 |
| 大量留白 | 上 1/3 下 1/4 空着 | 排版拥挤、缩略图看不清 |

## 常见失败模式

| 现象 | 原因 | 修法 |
|---|---|---|
| 中文错字 / 糊字 / 乱码 | 让生图模型写字 | 一律无字底图 + compose.py |
| 第 3 页熊换了围巾 | 每页单独生成 | 封面作参考图 + 角色卡逐字复用 |
| 一页塞了 4 个概念 | 想保留原文结构 | 一页一个动作，其余进配文 |
| 做成 20 页文字卡 | 沿用旧素材惯性 | 砍到 6–9 页，改 3:4 竖版 |
| 缩略图看不清 | 标题 30px、字数多 | 标题 62px+、≤12 字 |
| 要商用 / 长期做号 | 高相似版有 IP 风险 | 换 `examples/art-original/` 原创版 |
| 被限流 | 未标 AI | 发布时勾选 AI 标识 |

## 一键起步

```sh
# 1) 读源文，写 storyboard.md 与 spec.json
# 2) 生成 art/00-cover.png（用上面的 prompt，SCENE 换成封面场景）
# 3) 其余每页把 00-cover.png 作为参考图，SCENE 换成分镜表里的「一个动作」
# 4) 合成
python3 scripts/compose.py spec.json --font "$COMIC_FONT" \
  --outdir pages --html --contact-sheet
# 5) 打开 pages/preview.html 做四查
```

完整调研、案例、逐页改造方案与 3.7 整套文案设计见 `references/`；已做好的样张见 `examples/`。
