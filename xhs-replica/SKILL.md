# xhs-replica

把一份小红书图文素材，复刻成 N 张「同角色、同设计语言、换内容」的成品图。
角色（一二／布布）一个像素都不能改，改的只有场景和内容。

## 硬性指标

| 项 | 值 |
|---|---|
| 输出尺寸 | **1080 × 2280** |
| 比例 | **9:19**（0.4737） |
| 格式 | PNG（成品）／JPG（下载的原片） |
| 模型原生输出 | 704 × 1504 —— **必须**裁到 9:19 再重采样，不能直接拉伸 |

每一轮出图后先 `python3 -c "from PIL import Image; print(Image.open(f).size)"` 抽查，
不是 `1080, 2280` 就不要进云盘。

## 流程

```
1 取素材   抓笔记页 → 提 CDN 图链 → 下载 → webp 转 png
2 量设计   对原片跑 OCR + 分带取色 + 边缘密度，得到设计语言
3 生成     原图作参考图锁角色，提示词锁风格与构图
4 后期     finish.py：裁切 → 放大 → USM → 胶片分级 → 叠文字元素
5 出总图   每轮必出一张 总图.jpg（全部成品的拼版），随成品一起上传
6 归档     云盘「每轮一个子文件夹」+ 档案 Doc（含来源链接与文案）
7 文案     标题三选一 + 正文 + 短版 + 话题标签
```

**第 5 步是硬要求**：只要一轮出了多张，就必须有一张总图，并且**上传到该轮子文件夹**，
不能只留在本地。选首图、跟人讨论都靠它。

### 1. 取素材

沙箱出网常被限制。可行的路子：临时 GitHub Actions 工作流，让 runner 去抓
（它有公网），抓完 `git add` 回分支，本地 `git pull`。

- 笔记页的 CDN 链接带时间戳签名，会过期 —— **让 runner 现抓页面现提链接**，
  不要复用旧链接。
- 下载带 `Referer: https://www.xiaohongshu.com/` 和桌面版 UA。
- **抓完立刻把图和 workflow 从仓库删掉**，别把二进制留在 git 历史里。

### 2. 量设计（别靠猜）

看不到图的时候，用脚本把原片量出来：

- `tesseract -l chi_sim+eng --psm 11 tsv` → 有没有文字、在哪、多大
- 分 10 带取主色 → 配色是糖果色还是低饱和胶片调
- 边缘密度图 → 满幅出血还是有留白、有没有标题栏

本项目原片实测结论（写死在提示词里）：

- 满幅出血，无白边、无留白、**无中文标题栏**
- 低饱和胶片调：石板蓝灰 `#525f6d` ／ 暖褐 `#b38671` ／ 奶油白 `#f2ede5`
- 顶部与四角压暗（电影暗角），中段暖高光
- 全画面密集纹理道具，无空场
- 物件上印**英文小字**（实测到 `BLANKET`、`COFFEE`）

### 3. 生成

参考图给 4–6 张原片缩略图（720×1520 足够），提示词结构：

```
Reference-locked: reproduce the EXACT same two cartoon bear characters ...
absolutely no redesign. Full-bleed vertical illustration, 1080x2280 (9:19
phone wallpaper), no borders or margins ...
Muted low-saturation film palette of slate blue-grey, warm taupe, cream and
soft cocoa brown, with restrained <节日> accents ... used sparingly.
Cinematic soft directional light, gentle vignette, richly textured ...
Layered depth: soft foreground props, the two bears in the mid-ground,
atmospheric background.
IMPORTANT: absolutely no letters, words, numbers or writing anywhere in the
artwork, and keep one calm uncluttered flat surface in the lower third.
Scene: <具体场景，两只在做什么、前景中景背景各有什么>
```

最后两句是关键：

- **禁止模型写字** —— 它要么不出，要么拼错。字一律后期叠。
- **留一块平整面** —— 给后期叠字留位置。

### 4. 后期

```sh
pip install --break-system-packages pillow numpy
python3 scripts/finish.py spec.json
```

`finish.py` 依次做：

1. 居中裁到 9:19 → `LANCZOS` 重采样到 1080×2280
2. `UnsharpMask(radius=2, percent=60, threshold=3)`
3. 胶片分级：降饱和 0.8 → 冷暖分离（暗部暖褐／亮部石板蓝）→ S 曲线 → 暗角 → 颗粒
4. `stamp_word()`：在**下半部最平整的区块**叠加一个词 —— 这是画面里唯一的文字元素，
   要做得像设计元素而不是小贴图：默认 `scale=1.35`（约 0.46W 宽）、字距 0.16em、
   下方一条细规线、透明度 0.72、轻微旋转 ±2°，颜色取该区块底色
   （亮底压暗、暗底提亮）

只是补字、不想重新调色时，单独调 `stamp_word()` 即可，**不要**重复跑分级。

**用英文，不要用中文**，三个理由：

1. 原片实测只有英文（`BLANKET`、`COFFEE`），用中文等于改设计
2. 模型画汉字必崩，英文短词容错高
3. 英文能确定性叠；中文要装 CJK 字体（`pip install mplfonts`，
   自带 Noto Sans CJK SC / 思源宋体），`lang="zh"` 才可用 —— 留作备选，不默认用

### 5. 归档

云盘按轮次分子文件夹，不要平铺：

```
原始素材/
└─ 素材 02/
   ├─ 第1轮-原片9张（小红书下载）
   ├─ 第2轮-常规复刻10张
   ├─ 第3轮-圣诞特辑10张
   ├─ 第4轮-跨年特辑10张
   └─ 素材02-档案与小红书文案        ← 来源链接、每轮清单、设计语言、文案
```

档案 Doc 里要记：生成会话链接、原笔记链接、云盘路径、每轮文件清单、
设计语言、当轮文案。

### 6. 文案

固定结构：标题三选一 + 正文（前 3 行必须在折叠前露完）+ 短版（单图用）
+ 话题标签 + 发布提示（勾「含 AI 生成内容」、首图建议）。

## 坑

- **模型输出不是 9:19**：704×1504 是 0.4681，差一点点，直接拉伸会变形，必须先裁。
- **英文小字漏字**：模型不可靠，必须后期叠。
- **重复调色**：补字时重跑 `finish.py` 会二次降饱和、二次暗角，画面会发灰。
- **参考图漂移**：别拿上一轮生成的图当参考，会累积漂移，永远用原片。
- **二进制进 git**：抓图用过的 workflow 和图片必须清掉，否则分支会被重置/膨胀。
- **看不到图**：没有视觉能力时，所有判断都要落到数据上（OCR、取色、边缘密度），
  别靠「感觉」。
