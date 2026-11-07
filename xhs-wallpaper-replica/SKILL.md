---
name: xhs-wallpaper-replica
description: 给一条小红书壁纸笔记链接，下载原图 → 拆解版式 → 用生图模型重画「一模一样」的无字底图 → 脚本加 iOS 锁屏/主屏覆盖层、拼总图、做双机封面 → 写发布文案 → 按「第N轮」子文件夹归档到 Google Drive。当用户说「把这条壁纸笔记的图下载下来」「照这个帖子复刻 10 张壁纸」「做一套同款小新/卡通手机壁纸并上传到云盘」时使用。沙箱里下不了小红书图时自动走 tools/xhs-relay（GitHub Actions 代下）。
---

# xhs-wallpaper-replica：从一条壁纸笔记到一套能发的复刻壁纸

一个 SKILL.md + 一个脚本（`scripts/phone_mockup.py`）+ 一个代下 workflow（`tools/xhs-relay/`）。
不需要 MCP，不需要 Photoshop，**不让生图模型写任何字或画任何 UI**。

**核心原则：模型只画画，锁屏时间 / 日期 / 手电筒 / 相机 / Home 条 / 毛玻璃图标 / 拼版全部由脚本画。**
参考帖里那些「05:20」「Friday, November 6」是壁纸博主自己 P 的 iOS 预览效果，不是画的一部分；
只要几何量对了（见下表），复刻出来的预览图和原帖肉眼不可分，而且日期随时能换。

## 何时用 / 何时别用

- 用：壁纸类笔记（锁屏/主屏预览图、双机海报）；要求「复刻一样的 N 张」+ 总图 + 文案 + 云盘归档；卡通 IP 同人壁纸。
- 别用：真人摄影壁纸（生图模型复刻真人有肖像问题）；要逐像素搬运原图（那叫盗图，直接下载就好，不要叫复刻）；商用。

## 全流程（本项目完整跑通：弥弥壁纸 · 小新壁纸 7 张 → 复刻 10 张）

```
① 抓图           ② 拆解            ③ 底图              ④ 合成+验收            ⑤ 文案        ⑥ 归档
fetch_page/      量几何、列场景、    generate_image      phone_mockup.py        copy-*.md     Drive 第N轮/
xhs-relay        分锁屏/主屏        688×1536 无字图     1440×3200 + 覆盖层                   + SKILL + 文案Doc
01-原图/         spec.json          02-复刻/art/        预览/ 壁纸/ 总图 封面
```

### ① 抓图（原图，不是 1080 webp 预览）

1. `fetch_page` 打开带 `xsec_token` 的分享链接，抄下标题/正文/标签/作者和每张图的 URL（`…/spectrum/<token>!nd_dft_wlteh_webp_3`）。
2. 能直连 CDN 的机器：`https://sns-img-bd.xhscdn.com/<token>` 就是无水印 PNG 原图（token = `spectrum/1040g…`，去掉 `!` 后缀）。
3. Arena 沙箱直连不了 → 写 `tools/xhs-relay/queue.json`，push，等 workflow 把原图 commit 回同一分支（`tools/xhs-relay/README.md`）。
4. 存成 `examples/<slug>/01-原图/01.png…` + `note.json` + `note.md`。Drive 侧按小红书网页版下载命名：`<标题>_<n>_<作者>_来自小红书网页版.png`。
5. 更多工具（XHS-Downloader 13k★ 等）和取 token 的办法见 `references/github-tools.md`。

### ② 拆解参考帖 → `spec.json`

- 数清楚：几张锁屏、几张主屏、有没有双机海报（原帖 7 张 = 4 锁屏 + 2 主屏 + 1 双机图，第 5 张是 841×1870 小图）。
- 量几何：原图 1440×3200 上用 numpy 找白色像素行/列（时钟、日期、Home 条、暗色圆钮），得到下面的常量；主屏毛玻璃块用目测对齐即可，像素检测不稳。
- 列场景：每张一句话（谁 / 在哪 / 做什么 / 光线 / 主色），对应回正文里的句子——正文每句都应该有一张图。
- 复刻张数 > 原帖张数时，新场景从正文没画到的句子里来（本例正文「一起发呆」「吵吵闹闹的一家人」「甜点」→ 缘侧发呆、全家早餐、长椅冰棍 + 一张夏夜线香花火收尾）。
- 写成 `02-复刻/spec.json`：`pages[{n, name, overlay: lock|home, from, line}]`、`date`、`time`、`cover{left,right}`。

**锁屏几何表（1440×3200，实测自参考帖）**

| 元素 | 位置 | 备注 |
|------|------|------|
| 日期 "Friday, November 6" | 居中，字框 y 284–354（中心 319） | Inter wght 600 · 78 px |
| 时钟 "05:20" | 居中，数字高 244，中心 y 553 | Inter wght 700 · 336 px · opsz 32 |
| 手电筒 / 相机 圆钮 | 圆心 (231, 2940) / (1209, 2940)，r≈92 | 底图模糊 + 压暗 0.74，白色矢量图标 |
| Home 条 | x 468–971，y 3129–3147 | 白色圆角条 |
| 主屏图标 | 244×244，圆角 54；列中心 x 212/548/892/1228；行中心 y 300/602；Dock y 2960 | 模糊 40 + 白 42% + 1 px 白描边 |
| 双机海报 | 1600×1600 米色 #F1DECB，两台 560×1244，圆角 84，深色细边，柔影 | 左锁屏右主屏 |

### ③ 底图：generate_image 两种模式

两条铁律：**提示词里必须写「移除所有 UI、不要任何文字」**；**9:20 的长宽比只能靠「把原图当 images 传进去」保住**——纯文生图的长宽比不受控。

A. 复刻原帖某张（edit 模式，`images=[01-原图/0N.png]`）：

```
Recreate this exact illustration as a clean phone wallpaper: same scene, same composition and camera,
same characters (Crayon Shin-chan art style: round faces, thick eyebrows, simple black-dot eyes, soft
watercolor-like textures), same palette and lighting. REMOVE the lock-screen overlay completely — no clock,
no date, no icons, no home bar, no text or watermark anywhere. Fill those areas with the natural scene
(wall / sky / floor). Full-bleed 9:20 portrait, no border.
```

B. 新场景（把一张风格最接近的原图当 style + aspect 锚，`images=[01-原图/02.png]`）：

```
Use the attached image ONLY as a reference for art style, line weight, palette and the 9:20 portrait format.
Paint a completely NEW scene: <谁 在哪 做什么，光线，主色，1–2 个道具>. Keep the top 15% (sky / wall) and the
bottom 12% (floor / grass) calm and uncluttered so a clock and two buttons can sit there. No text, no UI,
no signature, no border.
```

- 生图输出 688×1536（≈9:20），一次 1 张；10 张可以并行 5+5。
- 角色一致性提示：小新（黄上衣红短裤 / 睡衣 / 幼稚园绿短裤白 T）、小白（白色棉花糖狗）、广志（黑短发眼镜 / 蓝衬衫）、美冴（棕色短卷发）、小葵（橙色头发婴儿）、妮妮（双马尾粉裙）、风间（蓝色西瓜头）。
- 常见翻车：留下了时钟（提示词没写 REMOVE）→ 重生成；出现日文/英文招牌字 → 提示词加 `no readable text on signs`；上半部分太满 → 加 calm top 15%；比例变 3:4 → 忘了传 images。

### ④ 合成 + 验收（`scripts/phone_mockup.py`）

```bash
# 字体：时钟 Inter（variable），中文 霞鹜文楷；放 ~/.fonts 或 --clock-font/--cjk-font
python3 scripts/phone_mockup.py all  examples/<slug>/02-复刻/spec.json \
        --art-dir examples/<slug>/02-复刻/art --out <交付目录> --format png          # Drive 交付：PNG
python3 scripts/phone_mockup.py all  … --out examples/<slug>/02-复刻 --format jpg --no-clean   # 仓库留档：JPG 预览
python3 scripts/phone_mockup.py build … --date "Saturday, November 7" --time 05:20              # 换日期
```

产出：`壁纸/复刻图NN-<场景>.png`（1440×3200 干净版）、`预览/复刻图NN-<场景>.png`（加覆盖层，发帖用）、`总图.jpg`（2×5 拼版，米色底手机圆角）、`封面-双机预览.jpg`。

放大说明：688×1536 → 1440×3200 用 Lanczos ×2.09 + 轻锐化，手机上看没问题，放到 100% 会比原帖软一点。
要更锐利就在本机跑一次 `realesrgan-ncnn-vulkan -n realesrgan-x4plus-anime -s 2 -i art -o art_up` 再喂给脚本。

验收清单（每张都过）：

- [ ] 顶部 15% 没有被角色/招牌占住，时钟和日期压在干净背景上
- [ ] 无任何文字、签名、水印；无残留 UI
- [ ] 角色特征对（眉毛、发型、服装颜色），画风和其余 9 张统一
- [ ] 锁屏/主屏分配和原帖同比例（本例 7 锁 3 主）
- [ ] 10 张尺寸一致 1440×3200；总图里一眼看出是一套

### ⑤ 文案（`references/copy-小新壁纸.md`）

标题 ≤20 字 ×3 候选 → 正文 ~300 字（勾回原帖情绪，但全部重写）→ 8 个话题 → 置顶评论（取图/致谢原作者）→ 发布勾选项。
正文里必须有「AI 生成，仅供个人壁纸使用」；发布页勾「AI 生成」。

### ⑥ 归档到 Google Drive（每轮一个子文件夹）

```
素材 05/
├─ 第1轮-原版7张（小红书下载）/   <标题>_<n>_<作者>_来自小红书网页版.png ×7 · 总图.jpg · note.json · Doc「第1轮 · 小红书文案」
└─ 第2轮-复刻10张/               复刻图01…10.png（预览版）· 壁纸干净版/ ×10 · 总图.jpg · 封面-双机预览.jpg
                                 · Doc「第2轮 · 小红书文案」· 小新壁纸复刻方案-SKILL.md · spec.json
```

用 Drive 连接器：`create_folder` → `upload_file`（md 用 `target_mime_type=application/vnd.google-apps.document` 转成 Doc）。
以后再来一轮就 `第3轮-…`，不要往旧文件夹里混。

## 合规三句话

1. 蜡笔小新等卡通形象是第三方 IP：个人壁纸、非商用、不做付费取图、不写「官方/正版」。
2. 全部图片是生图模型输出：发布页勾「AI 生成」，正文写明。
3. 复刻的是「版式 + 题材」，不是搬运原图；文案重写，置顶评论给原作者致谢（@弥弥壁纸）。

## 目录

```
xhs-wallpaper-replica/
├─ SKILL.md                      本文件
├─ README.md                     这次跑的结果 + 复现命令
├─ scripts/phone_mockup.py       放大 / 锁屏 / 主屏 / 总图 / 双机封面
├─ references/github-tools.md    小红书下载工具盘点 + token 取法
├─ references/copy-小新壁纸.md    第2轮文案 + 第1轮原帖文案存档
└─ examples/shinchan-6aedad8b/
   ├─ 01-原图/ 01–07.png, note.json, note.md
   └─ 02-复刻/ spec.json, art/01–10.png(688×1536 无字底图), 预览/ ×10 (jpg), 总图.jpg, 封面-双机预览.jpg
```
