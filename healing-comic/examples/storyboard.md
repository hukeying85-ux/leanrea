# 样张分镜表：《引导型恋人指南》四条底线

6 页 · 1080×1440 竖版 · 画风参考「一二布布」（白熊猫 + 奶茶棕熊）；原创替代版在 `art-original/`。
`art/` 为无字底图，`pages/` 为脚本填字后的成品。全部中文由 `scripts/compose.py` 排版，生图阶段零文字。

| # | 源文出处 | 一个动作（SCENE） | 大标题 / 副标题 | 气泡台词 | 页脚出处 |
|---|---|---|---|---|---|
| 01 | 导言 | 两只熊盖同一条蓝毯子，两只冒热气的杯子，一盏落地灯 | 真正的引导型恋人 / 从来不是当爹当妈 | 把选择权还回去，再在旁边站得稳一点。 | 内容出自《引导型恋人指南》v1.1.0 · 导言 |
| 02 | 四条底线 1；2.6 | 布布抬手轻轻摇头想独处；一二把手机扣在桌上，笑着点头 | 他说想一个人待着 / 我就把手机扣下 | 好，那我不加安排。/ 下周三你有空再告诉我。 | 2.6 第一句 · 对方可以随时说不想聊、不想被安排 |
| 03 | 四条底线 2 | 一二把空白便签揉成团丢进纸篓，改捧一杯可可递过去 | 揉掉那张 /「改造清单」 | 我不改你，只说这件事让我有点难受。 | 3 只谈具体行为、具体影响、具体请求 |
| 04 | 四条底线 3；13.8 | 傍晚长椅，布布低头；一二不说话，只把爪子轻轻搭在它背上，远处小屋亮着灯 | 不急着修好他 / 先陪他坐一会儿 | 我们一起找人聊聊，不是谁有病。 | 13.8 危机 / 成瘾 / 自伤先转介，不做诊断不治疗 |
| 05 | 四条底线 4；第 11 章 | 手机倒扣在桌上没人碰；一二背对着它去浇花，布布递来两块小饼干 | 他的手机倒扣着 / 我去给花浇水 | 你的手机，我不看。 | 4 查手机、装定位、冷暴力、试探，一律不做 |
| 06 | 导言 + 第 13 章 | 夜里并排坐在窗台看月亮，一二把毯子一角推过去，各自留一点距离 | 既能靠近 / 也有退路 | 两个人都站在自己的位置上，就很好。 | 完整 13 章 104 个具体场景 · CC BY 4.0 |

## 生图用提示词（每页只换 SCENE）

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

SCENE: <上表「一个动作」列，写成英文具体描述>

LARGE clean empty cream space across the top third and the bottom quarter for
later text overlay. CRITICAL: absolutely no text, no Chinese characters, no
letters, no numbers, no captions, no speech balloons, no speech bubbles,
no watermark, no logo.
```

**执行顺序**：生成封面时挂 2–3 张一二布布原图（`image-search/` 转存的 PNG）做参考；之后每页挂「新封面 + 1 张原图」。本样张就是这么做的。

## 复现

```sh
cd healing-comic
python3 scripts/compose.py examples/spec.json \
  --font /path/to/LXGWWenKai-Regular.ttf \
  --font-medium /path/to/LXGWWenKai-Medium.ttf \
  --art-root examples \
  --outdir examples/pages --html --contact-sheet
```

## 还没做的两页（凑成 8 页时补）

- 反差开场：「我以为引导 = 替他兜底一切」→ 一二两手抱满一堆东西快拿不住，布布在旁边伸手想接。
- 对照页：「控制让人更怕你，引导让人更没得选？」→ 同一只熊左右两种表情，中间只放一个小箭头。

补页不用改脚本，只改 `spec.json` + 新增 `art/*.png`。
