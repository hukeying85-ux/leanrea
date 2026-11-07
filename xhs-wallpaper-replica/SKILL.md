---
name: xhs-wallpaper-replica
description: 给一条小红书壁纸笔记链接，下载原图 → 拆解版式 → 用生图模型重画「一模一样」的无字底图 → 脚本加 iOS 锁屏/主屏覆盖层、拼总图、做双机封面 → 写发布文案 → 按「第N轮」子文件夹归档到 Google Drive。当用户说「把这条壁纸笔记的图下载下来」「照这个帖子复刻 10 张壁纸」「做一套同款小新/卡通手机壁纸并上传到云盘」时使用。沙箱里下不了小红书图时自动走 tools/xhs-relay（GitHub Actions 代下）。
---

# xhs-wallpaper-replica：从一条壁纸笔记到一套能发的复刻壁纸

一个 SKILL.md + 一个脚本（`scripts/phone_mockup.py`）+ 一个代下 workflow（`tools/xhs-relay/`）。
不需要 MCP，不需要 Photoshop，**不让生图模型写任何字或画任何 UI**。

**核心原则一：壁纸就是壁纸。** 参考帖里的「05:20」「Friday, November 6」、手电筒/相机圆钮、Home 条、主屏毛玻璃图标，
全是壁纸博主 P 上去的 iOS 预览效果——那些东西手机自带，**交付件里一律不要**。交付 = 1440×3200 的干净底图。

**核心原则二：模型只画画，字和 UI 永远不交给生图模型。** 如果确实要做一张「带手机界面的效果预览图」（比如封面），
用 `phone_mockup.py --ui ios` 由脚本按下表几何画，日期随时能换，而且绝不混进壁纸本体。

## 何时用 / 何时别用

- 用：壁纸类笔记（锁屏/主屏预览图、双机海报）；要求「复刻一样的 N 张」+ 总图 + 文案 + 云盘归档；卡通 IP 同人壁纸。
- 别用：真人摄影壁纸（生图模型复刻真人有肖像问题）；要逐像素搬运原图（那叫盗图，直接下载就好，不要叫复刻）；商用。

## 全流程（本项目完整跑通：弥弥壁纸 · 小新壁纸 7 张 → 复刻 10 张）

```
① 抓图           ② 拆解            ③ 底图              ④ 合成+验收            ⑤ 文案        ⑥ 归档
fetch_page/      量几何、列场景、    generate_image      phone_mockup.py        copy-*.md     Drive 第N轮/
xhs-relay        记录原帖 UI 几何    688×1536 无字图     放大到 1440×3200 干净壁纸              + SKILL + 文案Doc
01-原图/         spec.json          02-复刻/art/        壁纸/ 总图 封面（--ui ios 另出预览）
```

### ① 抓图（原图，不是 1080 webp 预览）

1. `fetch_page` 打开带 `xsec_token` 的分享链接，抄下标题/正文/标签/作者和每张图的 URL（`…/spectrum/<token>!nd_dft_wlteh_webp_3`）。
2. 能直连 CDN 的机器：`https://sns-img-bd.xhscdn.com/<token>` 就是无水印 PNG 原图（token = `spectrum/1040g…`，去掉 `!` 后缀）。
   视频笔记同理：`https://sns-video-bd.xhscdn.com/<originVideoKey>` 是作者上传的无水印原片（可能几百 MB），网页 `masterUrl` 只是 720p 码流。
3. Arena 沙箱直连不了 → 写 `tools/xhs-relay/queue.json`，push，等 workflow 把原图 commit 回同一分支（`tools/xhs-relay/README.md`）。
   超大的视频原片不进 git：沙箱用 Drive 连接器开一个 resumable 上传会话，用 `relay_pubkey.pem` 加密后放到 `secrets/*.enc`，runner 解密后直传 Drive。
4. 存成 `examples/<slug>/01-原图/01.png…` + `note.json` + `note.md`。Drive 侧按小红书网页版下载命名：`<标题>_<n>_<作者>_来自小红书网页版.png`。
5. 更多工具（XHS-Downloader 13k★ 等）和取 token 的办法见 `references/github-tools.md`。

### ② 拆解参考帖 → `spec.json`

- 数清楚：几张锁屏、几张主屏、有没有双机海报（原帖 7 张 = 4 锁屏 + 2 主屏 + 1 双机图，第 5 张是 841×1870 小图）。
- 量几何：原图 1440×3200 上用 numpy 找白色像素行/列（时钟、日期、Home 条、暗色圆钮），得到下面的常量；主屏毛玻璃块用目测对齐即可，像素检测不稳。
- 列场景：每张一句话（谁 / 在哪 / 做什么 / 光线 / 主色），对应回正文里的句子——正文每句都应该有一张图。
- 复刻张数 > 原帖张数时，新场景从正文没画到的句子里来（本例正文「一起发呆」「吵吵闹闹的一家人」「甜点」→ 缘侧发呆、全家早餐、长椅冰棍 + 一张夏夜线香花火收尾）。
- 写成 `02-复刻/spec.json`：`pages[{n, name, overlay: lock|home, from, line}]`、`date`、`time`、`cover{left,right}`。
  每页可选 `ax`/`ay`（0–1，默认 0.5）：`phone_mockup.py` 把底图等比铺满 1440×3200 后按这个锚点裁切，底图偏宽时用来保住主体（第 11 轮 04/06 写 0.5、10 写 0.4）。

**锁屏几何表（1440×3200，实测自参考帖）**

| 元素 | 位置 | 备注 |
|------|------|------|
| 日期 "Friday, November 6" | 居中，字框 y 284–354（中心 319） | Inter wght 600 · 78 px |
| 时钟 "05:20" | 居中，数字高 244，中心 y 553 | Inter wght 700 · 336 px · opsz 32 |
| 手电筒 / 相机 圆钮 | 圆心 (231, 2940) / (1209, 2940)，r≈92 | 底图模糊 + 压暗 0.74，白色矢量图标 |
| Home 条 | x 468–971，y 3129–3147 | 白色圆角条 |
| 主屏图标 | 244×244，圆角 54；列中心 x 212/548/892/1228；行中心 y 300/602；Dock y 2960 | 模糊 40 + 白 42% + 1 px 白描边 |
| 双机海报 | 1600×1600 米色 #F1DECB，两台 560×1244，圆角 84，深色细边，柔影 | 左锁屏右主屏 |

### ③ 底图：generate_image 三种模式

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

C. 名画风（第 6 轮，一二布布《疑似梵高的真迹》）：原帖只有 1 张，用户要的是「这种画作风格，不止梵高」→ 角色锚 + 名画锚：

```
Use the attached image ONLY to keep the two characters exactly as designed (一二 = chubby white bear, round
black panda ears, dot eyes, pink round cheeks; 布布 = chubby light-brown bear, round ears, yellow-orange
cheeks). Repaint them INTO <画家 · 作品> : <那幅画最有辨识度的 2–3 个元素 + 笔触/用色词>, thick impasto oil
texture, portrait format. No text, no signature, no frame, no watermark.
```

名画清单先定 10 幅再出图（梵高给 3–4 幅压住「原帖气质」，其余换莫奈 / 北斋 / 克里姆特 / 蒙克 / 维米尔 / 达芬奇拉开差异）。
人像类名画（珍珠耳环 / 蒙娜丽莎）要写清「把整个人换成熊」，否则容易出「熊头 + 人身」的梗图（第 6 轮 #10 就是，留着当梗图也行，正经路线就重画）。

- 没有名字的原创角色（第 8 轮五只猫）：先把每只的毛色 / 花纹 / 表情写成一句固定「角色串」（黑猫黄绿眼粉腮 · 白底橘斑 · 灰虎斑 · 眯眼橘猫 · 白猫），
  A/B 两种提示词都原样带上，再加「same five cats, same white stone ledge, same bay」——10 张的角色一致性靠这句话，不靠模型记忆。
  原帖 ≈ 9:20（850×1850）就直接走 phone_mockup 标准流程，交付 1440×3200 零裁切。
- 原帖本身就是干净壁纸（没有锁屏 UI，如第 7 轮一二布布鲜花）时，A 模式提示词把「REMOVE the lock-screen overlay」换成「same portrait format and composition」+ 逐项描述画面即可，复刻度很高；
  原帖只有 5 张而用户要 10 张 → 01–05 用 A 逐张复刻、06–10 用 B 出新场景，B 的风格锚轮换用不同原图（田野场景锚田野图、庭院场景锚庭院图），构图不会串。
  原帖画幅不是 9:20 时交付画幅跟原帖（第 7 轮 1536×2752），用 `painting_set.py`，不要硬裁成 1440×3200。
- 原帖多于 10 张（第 9 轮猫和老鼠 18 张）时全走 A 模式，不出新场景：先拼一张原片总图，按「场景 / 道具 / 配色 / 光线」挑差异最大的 10 张（同一张沙发的两种盖被只留一张），
  在原片总图上用 ★ 标出选中的，spec 的 `label` 里记下对应原图号，文案「发图顺序」再按情绪走向重排；经典 IP（汤姆/杰瑞）的提示词把角色写成固定描述串
  （grey-blue cat with white muzzle and paws / small brown mouse with big round ears），不写 IP 名字也能复刻到位。
- 原帖是 3:5 的「画」而不是 9:20 壁纸（第 10 轮厚涂油画 971×1619）：交付跟原帖 3:5（1536×2560，`painting_set.py`），再用 `phone_mockup.py build --ui ios` 看 9:20 居中裁切后的装机效果——
  两侧各裁约 12%，主体在中间的都没事，时钟压到主体的那张（灯塔塔顶）改做主屏预览；文案里提醒用户「缩放/平移」。
  油画类 A 模式提示词开头写「Recreate this exact painting as a faithful replica … same thick impasto oil-paint brushwork」，再逐项点元素和配色（honey-gold / peach / periwinkle-blue），复刻度极高，生图输出 800×1328 ≈ 3:5 基本零裁切。
  原帖 9 张要 10 张时，第 10 张从正文没画到的句子 + 作者昵称里找梗（「坐一会儿吧」+「一只小猫」→ 窗台小猫看灯塔），风格锚用最点题的那张原图。
- 生图偶尔会吐出偏宽的 848×1264（≈ 2:3，第 11 轮线条小狗 10 张里中了 3 张），硬居中裁成 9:20 会切掉两侧 33%：`phone_mockup.py` 支持 spec 每页 `"ax"`/`"ay"`（0–1，默认 0.5）
  锚点裁切——先拼一张候选裁切对比图看主体落在哪，再给偏宽那页写 `ax`（主体偏左写 0.4），不用重新生图；主体实在保不住再重生成。
  原帖多于 10 张时翻评论区「求图N」决定封面（第 11 轮「求图一」×4、「求图6」被作者亲自回图 → 封面左 01 右 06）。
  线条小狗类 IP 也写固定描述串：白狗 = fluffy white puppy drawn with loose scribbly broken black outline strokes, tiny dot eyes；黄狗 = round light-tan puppy, floppy ears, clean black outline, red collar。
  画面里本身带字母的原图（07「FLYING」）、主角换成别的狗的原图、同款衣服换个背景的重复图直接剔除，不要替它们改字。
- 生图输出 688×1536（≈9:20），一次 1 张；10 张可以并行 5+5。
- 角色一致性提示：小新（黄上衣红短裤 / 睡衣 / 幼稚园绿短裤白 T）、小白（白色棉花糖狗）、广志（黑短发眼镜 / 蓝衬衫）、美冴（棕色短卷发）、小葵（橙色头发婴儿）、妮妮（双马尾粉裙）、风间（蓝色西瓜头）。
- 常见翻车：留下了时钟（提示词没写 REMOVE）→ 重生成；出现日文/英文招牌字 → 提示词加 `no readable text on signs`；上半部分太满 → 加 calm top 15%；比例变 3:4 → 忘了传 images。
- 道具上的小字（罐子 "SUGAR"、海报）最容易漏：提示词写 `no letters on jars / packaging / posters`；已经生成的，用 edit 模式只改那一处，
  或者直接 Pillow 按精确坐标用两侧颜色线性插值抹掉（`03-新画10张/art/03.png` 就是这么修的）。
- 生图每轮上限 10 张，10 张一套正好用完——留 1 张余量给返工更稳（先出 9 张或分两轮）。
- 多轮出图时每轮换一个文件前缀（`复刻图` / `新画` / `新画2-`），Drive 里不同轮的文件名才不会撞；场景清单先对着前几轮查重再写提示词。
- 新场景的风格锚：优先用自己上一轮的干净底图（`02-复刻/art/*.png`）而不是带 UI 的原图，既保 9:20 又不会把时钟带进来。

### ④′ 名画风 / 同画幅交付（`scripts/painting_set.py`）

原帖不是 9:20 壁纸、而是某个固定画幅（第 6 轮 1532×2560）时不用 phone_mockup，改用 `painting_set.py`：

```bash
python3 scripts/painting_set.py examples/<slug>/02-复刻/spec.json \
        --art-dir examples/<slug>/02-复刻/art --out <交付目录> --format png     # Drive 交付
python3 scripts/painting_set.py … --out examples/<slug>/02-复刻/成图 --format jpg  # 仓库留档
```

- spec 里 `canvas: [W, H]` 用原帖尺寸；每页可写 `anchor: top|center|bottom`，生图的长宽比不一（768×1376 / 800×1337 / 848×1264）时按 cover 盖满裁切，重要内容在上/下的页面用 anchor 保住。
- 文件名 `<prefix>NN-<画家·作品>.png`；`总图.jpg` 2×5 带图注（标题 / 副标题不要放 emoji，字体没有彩色 emoji 字形）。
- 验收：10 张尺寸一致、无文字签名、两只角色特征不漂（耳朵颜色、脸颊颜色最容易漂）。

### ④ 合成 + 验收（`scripts/phone_mockup.py`）—— 每轮交付两份：干净壁纸 + 手机UI预览

**铁律：先出干净图，再由脚本「加」UI；永远不要让生图模型画 UI 再去「去」。**
加 = 确定性叠加（时钟 / 日期 / 手电筒 / 相机 / Home 条 / 主屏毛玻璃图标），几秒钟、可换日期时间、不碰画面；
去 = 要重生成或 inpaint，不可控还会伤画面。所以 10 张干净底图是源头，UI 版只是它的派生物。

每轮 Drive 里固定两份：
- `<轮文件夹>/`（或 `结果/`）：干净 PNG ×10 = 真正的壁纸交付物；
- `<轮文件夹>/手机UI预览/`（或 `结果/手机UI预览/`）：同名 JPG ×10 + `预览总图.jpg`，叠了 iOS 锁屏/主屏 UI，用来看「装到手机上」的实测效果：时钟压没压到主体、非 9:20 的画幅被手机裁掉了多少。只看不发。


```bash
# 字体：中文 霞鹜文楷（--cjk-font）；只有 --ui ios 才需要时钟字体 Inter（--clock-font）
python3 scripts/phone_mockup.py all  examples/<slug>/02-复刻/spec.json \
        --art-dir examples/<slug>/02-复刻/art --out <交付目录> --format png     # Drive 交付：干净 PNG
python3 scripts/phone_mockup.py all  … --out examples/<slug>/02-复刻/壁纸 --format jpg   # 仓库留档：JPG
python3 scripts/phone_mockup.py all  … --ui ios --date "Saturday, November 7" --time 05:20   # 必做：手机UI预览 → OUT/预览-iOS/ + 总图（带机框）
# 非 9:20 画幅（第 6/7 轮 1532×2560 / 1536×2752）：先用 painting_set.py 出干净图，再用一份 overlay 全 lock 的临时 spec 把 art/ 喂给
# phone_mockup.py build --ui ios → fit_canvas 会按 9:20 居中放大裁切，正好等于手机「填充」行为；只取 预览-iOS/ 与总图，1440×3200 的干净版不要交付
```

产出（默认 `--ui none`）：`复刻图NN-<场景>.png`（1440×3200 干净壁纸，就是交付物）、`总图.jpg`（2×5 拼版，米色底圆角卡片）、`封面-双机预览.jpg`（两张竖图并排）。
`--ui ios` 时额外多一个 `预览-iOS/` 子目录，仅作展示，不要当壁纸交付。

放大说明：688×1536 → 1440×3200 用 Lanczos ×2.09 + 轻锐化，手机上看没问题，放到 100% 会比原帖软一点。
要更锐利就在本机跑一次 `realesrgan-ncnn-vulkan -n realesrgan-x4plus-anime -s 2 -i art -o art_up` 再喂给脚本。

验收清单（每张都过）：

- [ ] 顶部 15% 没有被角色/招牌占住，时钟和日期压在干净背景上
- [ ] 无任何文字、签名、水印；无残留 UI
- [ ] 角色特征对（眉毛、发型、服装颜色），画风和其余 9 张统一
- [ ] 干净交付件里没有任何手机 UI（时间/日期/图标/Home 条）
- [ ] `手机UI预览/` 齐 10 张 + 预览总图；逐张看时钟（y≈319–553）有没有压到脸，非 9:20 画幅看两侧被裁后主体还在不在
- [ ] 10 张尺寸一致 1440×3200；总图里一眼看出是一套

### ⑤ 文案（`references/copy-小新壁纸.md`）

标题 ≤20 字 ×3 候选 → 正文 ~300 字（勾回原帖情绪，但全部重写）→ 8 个话题 → 置顶评论（取图/致谢原作者）→ 发布勾选项。
正文里必须有「AI 生成，仅供个人壁纸使用」；发布页勾「AI 生成」。

### ⑥ 归档到 Google Drive（每轮一个子文件夹）

```
素材 05/
├─ 第1轮-原版7张（小红书下载）/   <标题>_<n>_<作者>_来自小红书网页版.png ×7 · 总图.jpg · note.json · Doc「第1轮 · 小红书文案」
├─ 第2轮-复刻10张/               复刻图01…10.png（1440×3200 干净壁纸）· 总图.jpg · 封面-双机预览.jpg · 手机UI预览/（iOS 叠层 ×10 + 预览总图）
│                                · Doc「第2轮 · 小红书文案」· 小新壁纸复刻方案-SKILL.md · spec.json
├─ 第3轮-视频下载测试/            原片/（runner 直传的无水印原片 + 网页码流 + 封面 + note.json）· 结果/（关键帧总图、音频、信息 Doc）
├─ 第4轮-新画10张/               新画01…10.png（全新场景，非复刻）· 总图.jpg · 封面-双机预览.jpg · Doc「第4轮 · 小红书文案」· spec.json · 手机UI预览/
├─ 第5轮-新画10张/               新画2-01…10.png（第二套全新场景）· 总图.jpg · 封面-双机预览.jpg · Doc「第5轮 · 小红书文案」· spec.json · 手机UI预览/
├─ 第6轮-一二布布名画风/          原片/（小红书无水印 webp · 转PNG · note.json · Doc「笔记信息」）
│                                结果/（名画01…10.png 1532×2560 · 总图.jpg · spec.json · Doc「第6轮 · 小红书文案」· 手机UI预览/）
├─ 第7轮-一二布布鲜花壁纸/        原片/（5 张原图 `<标题>_<n>_<作者>_来自小红书网页版.*` · 原片总图.jpg · note.json · Doc「笔记信息」）
│                                结果/（鲜花01…10.png 1536×2752 · 总图.jpg · spec.json · Doc「第7轮 · 小红书文案」· 手机UI预览/）
├─ 第8轮-小猫樱花治愈壁纸/        原片/（4 张原图 850×1850 同上命名 · 原片总图.jpg · note.json · Doc「笔记信息」）
│                                结果/（小猫01…10.png 1440×3200 · 总图.jpg · 封面-双机预览.jpg · spec.json · Doc「第8轮 · 小红书文案」· 手机UI预览/ 10 jpg + 预览总图.jpg）
├─ 第9轮-猫和老鼠停战壁纸/        原片/（18 张原图 1290×2796 同上命名 · 原片总图.jpg（★ 标出选中的 10 张）· note.json · Doc「笔记信息」）
│                                结果/（猫鼠01…10.png 1440×3200 · 总图.jpg · 封面-双机预览.jpg · spec.json · Doc「第9轮 · 小红书文案」· 手机UI预览/ 10 jpg + 预览总图.jpg）
├─ 第10轮-日落灯塔油画壁纸/       原片/（9 张 PNG 原图 971×1619 同上命名 · 原片总图.jpg · note.json · Doc「笔记信息」）
│                                结果/（灯塔01…10.png 1536×2560（3:5 跟原帖）· 总图.jpg · 封面-双机预览.jpg · spec.json · Doc「第10轮 · 小红书文案」· 手机UI预览/ 10 jpg + 预览总图.jpg）
└─ 第11轮-线条小狗春天壁纸/       原片/（14 张原图 尺寸不一 ≈ 9:18.5 同上命名 · 原片总图.jpg（★ 标出选中的 10 张）· note.json · Doc「笔记信息」）
                                 结果/（小狗01…10.png 1440×3200 · 总图.jpg · 封面-双机预览.jpg · spec.json · Doc「第11轮 · 小红书文案」· 手机UI预览/ 10 jpg + 预览总图.jpg）
```

用 Drive 连接器：`create_folder` → `upload_file`（md 用 `target_mime_type=application/vnd.google-apps.document` 转成 Doc）。
以后再来一轮就 `第3轮-…`，不要往旧文件夹里混。
用户要求「原片和结果分开」时（第 3 / 6 / 7 轮），轮文件夹下再开 `原片/` 与 `结果/` 两个子文件夹，原片按下载原格式（webp 就传 webp）再附一份转 PNG。

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
├─ scripts/painting_set.py       名画风 / 同画幅交付：cover 裁切到 spec.canvas + 带图注总图
├─ references/github-tools.md    小红书下载工具盘点 + token 取法
├─ references/copy-小新壁纸.md    第2轮文案 + 第1轮原帖文案存档
├─ references/copy-一二布布名画.md 第6轮文案（名画 10 张）
├─ references/copy-一二布布鲜花.md 第7轮文案（鲜花 10 张）
├─ references/copy-小猫樱花.md     第8轮文案（小猫 10 张 + 锁屏备注）
├─ references/copy-猫和老鼠停战.md 第9轮文案（猫鼠 10 张 + 锁屏备注）
├─ references/copy-日落灯塔.md     第10轮文案（灯塔 10 张 + 3:5 裁切备注）
├─ references/copy-线条小狗春天.md 第11轮文案（线条小狗 10 张 + 锁屏/ax 裁切备注）
└─ examples/shinchan-6aedad8b/
   ├─ 01-原图/ 01–07.png, note.json, note.md
   ├─ 02-复刻/ spec.json, art/01–10.png(688×1536 无字底图), 壁纸/ ×10 (jpg), 总图.jpg, 封面-双机预览.jpg
   │          （每个轮次目录另有 预览总图-iOS.jpg；50 张 UI 预览本体不进仓库，一条命令可再生）
   ├─ 03-新画10张/ 同上结构；模式 B（新场景）的完整样例，风格锚用的是 02-复刻/art 里的干净底图
   ├─ 04-新画10张-第5轮/ 第二套新场景；文件前缀改成「新画2-」避免和上一套同名
   ├─ ../video-test-6a4be129/01-原片/ video.mp4(网页码流), cover.jpg, note.json, drive_upload.json
   ├─ ../vangogh-bubu-6aeeecba/ 模式 C 样例：01-原片/01.webp(1532×2560)+note；02-复刻/ spec.json, ref-原图.jpg, art/01–10.png, 成图/ ×10 (jpg), 总图.jpg
   ├─ ../flowers-bubu-6ae3391a/ 模式 A+B 混合样例（原帖本身就是干净壁纸）：01-原片/01–05 (1536×2752)+note；02-复刻/ spec.json, art/01–10.png, 成图/ ×10 (jpg), 总图.jpg
   ├─ ../cat-sakura-6ae8870f/   非 IP 的治愈系插画样例（4 原图 ≈ 9:20 → 标准 phone_mockup 流程）：01-原片/01–04 (850×1850)+note；02-复刻/ spec.json, art/01–10.png(688×1536), 壁纸/ ×10 (jpg), 总图.jpg, 封面-双机预览.jpg, 预览总图-iOS.jpg
   ├─ ../tomjerry-6aed5b12/    （18 原图 1290×2796 ≈ 9:20 → 挑 10 张逐张复刻）：01-原片/01–18+note；02-复刻/ spec.json, art/01–10.png(688×1536), 壁纸/ ×10 (jpg), 总图.jpg, 封面-双机预览.jpg, 预览总图-iOS.jpg
   ├─ ../lighthouse-6aede8e7/  厚涂油画 · 3:5 画幅样例（9 原图 971×1619 → 01–09 A 模式逐张复刻 + 10 B 模式新场景；painting_set 1536×2560 + phone_mockup --ui ios 看 9:20 裁切）：01-原片/01–09.png+note；02-复刻/ spec.json, art/01–10.png(800×1328), 成图/ ×10 (jpg), 总图.jpg, 封面-双机预览.jpg, 预览总图-iOS.jpg
   └─ ../linedog-69bec419/     线条小狗 · 14 原图尺寸不一 → 挑 10 张 A 模式逐张复刻；spec 每页 ax 锚点裁切偏宽输出：01-原片/01–14.jpg+note；02-复刻/ spec.json, art/01–10.png(768×1376 / 848×1264), 壁纸/ ×10 (jpg), 总图.jpg, 封面-双机预览.jpg, 预览总图-iOS.jpg
```

## 沙箱踩坑备忘

- 沙箱可能被回滚到旧快照：本地 git 历史、`~/.fonts`、pip 包、gitignored 的 `google_drive/` 暂存目录全会丢。每轮开工先 `git status && git log --oneline -3`；
  不对就 `git fetch && git reset origin/<branch> && git checkout origin/<branch> -- xhs-wallpaper-replica`，再 `pip install pillow numpy`，字体用 GitHub blobs API 重拉
  （`gh api repos/lxgw/LxgwWenKai/git/blobs/<sha> -H "Accept: application/vnd.github.raw"`，release 资源域名在沙箱里不通）。
  Inter（iOS 时钟字体）同法：`gh api repos/google/fonts/contents/ofl/inter` 取 `Inter[opsz,wght].ttf` 的 sha → blobs API 存为 `~/.fonts/Inter-Variable.ttf`。
- 已经传到 Drive 的东西不受影响，暂存目录丢了不用重传。
