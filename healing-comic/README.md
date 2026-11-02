# healing-comic · 小红书「一二布布式」治愈简笔漫画技能

> 一个 `SKILL.md` + 一个只依赖 Pillow 的脚本，把长文 / PDF / 指南压成 6–9 页可爱治愈漫画。
> 延续本仓库 `leanrea/` 的思路：不装 MCP、不加 200 个工具、不依赖第三方服务，Agent 用已有能力就能跑。

## 这次回答了什么

针对 `引导型恋人指南_2026-10-31_v1.1.0/引导型恋人指南.pdf`，以及你给的小红书笔记
[《毁掉关系的八种做法》· 睡觉吐泡泡](https://www.xiaohongshu.com/discovery/item/6ae8524a00000000100133ce?source=webshare&xhsshare=pc_web&xsec_token=ABkdgaKMLDV2CGcE-vyjxjJuSnUgL9J-neqAIPn2NfnMU=&xsec_source=pc_share)：

1. **GitHub 上有没有漫画制作的 skills** → 有，14 个，逐个读了 `SKILL.md`。结论与推荐组合见 [`references/github-skills.md`](references/github-skills.md)。
2. **这份 PDF 怎么改成那种简单的可爱治愈漫画** → 不是给 20 张横版文字卡换个画风，而是砍到 6–9 页竖版、一页一个动作一句台词。逐页映射表、文案、发布清单见 [`references/conversion-plan.md`](references/conversion-plan.md)。
3. **自己找的案例** → 笔记原页拆解 + 8 张原图直链 + 现成生图提示词 + IP 设定 + 同赛道账号 + GitHub 成品 + 平台合规，见 [`references/cases.md`](references/cases.md)。
4. **还直接做了一套样张** → 6 页 1080×1440 成品 + 3.7「承诺要小而可兑现」文案设计样张 3 页，见 [`examples/pages/preview.html`](examples/pages/preview.html)；整套发布文案在 [`references/copy-3.7-承诺要小而可兑现.md`](references/copy-3.7-承诺要小而可兑现.md)。

## 先看成品

- 整套预览：[`examples/pages/preview.html`](examples/pages/preview.html)（浏览器直接打开，v2 版式：80px 大标题、左对齐、无页眉标签/页码）
- 拼版缩略图：[`examples/pages/preview.jpg`](examples/pages/preview.jpg)
- 单页成品：[`examples/pages/`](examples/pages/)；3.7 文案设计样张（3 页）：[`examples/pages-37/`](examples/pages-37/)
- 无字底图（可换文案重新合成）：[`examples/art/`](examples/art/)

样张内容取自《引导型恋人指南 v1.1.0》的「四条底线」，把 4 条各 200 字的条目压成 4 个动作 + 4 句口语；角色为**一二布布风高相似重绘**（用原版表情包当参考图 + 按原作特征修正）；商用 / 长期做号请换 `examples/art-original/` 的原创版「白团子 + 阿棕」。

## 目录

```
SKILL.md                     单文件技能：规格、7 步工作流、提示词模板、失败模式、四查清单
references/
  github-skills.md           GitHub 调研（含 star / 可借鉴点 / 不适用场景）
  cases.md                   小红书案例库 + 风格拆解 + 参考图直链 + 合规
  conversion-plan.md         本 PDF 的逐页改造方案与发布清单
examples/
  storyboard.md              6 页分镜表 + 可复制的生图提示词
  spec.json                  排版输入（标题 / 台词 / 出处）
  art/*.png                  6 张零文字底图
  pages/*.png                6 张 1080×1440 成品 + preview.html + preview.jpg
scripts/
  compose.py                 无字底图 + spec.json -> 成品页（Pillow，中文折行 / 气泡 / 预览）
  fetch_font.sh              可选：下载霞鹜文楷（SIL OFL 1.1）
```

## 复现样张

```sh
cd healing-comic
python3 -m pip install Pillow                  # 唯一依赖
bash scripts/fetch_font.sh                     # 或自备任意中文 .ttf/.ttc
python3 scripts/compose.py examples/spec.json \
  --font ~/.fonts/LXGWWenKai-Regular.ttf \
  --art-root examples --outdir examples/pages --html --contact-sheet
```

换文案只改 `spec.json` 重跑即可，`art/` 原图不动。补第 7、8 页只需按 `storyboard.md` 新增底图并往 `spec.json` 加两条。

## 三条硬规则

1. **中文永远不由生图模型写**：所有字都由 `compose.py` 后期合成，避免错字糊字。
2. **封面先出，后续页拿它当参考图**：蝴蝶结 / 围巾 / 耳朵才不会漂。
3. **发布时勾选 AI 生成合成内容标识**：小红书 2026-02 起要求，未标识会限制分发；并保留原书 CC BY 4.0 署名与免责条款。

## 许可

本目录文字与代码沿用仓库 MIT；示例画面为 AI 生成，仅作风格演示。原书正文 CC BY 4.0，字体霞鹜文楷 SIL OFL 1.1。
