# 静态壁纸 → 动态 / 3D 壁纸：GitHub 工具盘点 + 实测对比

> 样例：第 17 轮《金鱼游动 福气满满》10 张 1440×1920 油画（Drive `第17轮-金鱼福气油画/结果/动态壁纸/`），
> 第 18 轮《水果里藏着风景》10 张同流程复跑（`第18轮-水果风景厚涂油画/结果/动态壁纸/`）。
> 星标数为 2026-11-10 `gh api` 实查。

## 先把概念说清

| 用户说的 | 手机上实际是什么 | 文件 |
|---|---|---|
| 动态壁纸 | 一段 **无缝循环的短视频**（3–10 s），由系统或 app 在桌面 / 锁屏循环播放 | MP4（Android 视频壁纸）、实况照片 JPG+MOV（iOS 锁屏）、动态照片 `.MP.jpg`（Pixel / 三星锁屏） |
| 3D 壁纸 | **深度视差**：按深度图把画面拆成远近，跟着陀螺仪 / 鼠标反向位移 | 原图 + 深度图（或前景 / 背景两层 PNG）+ 一个会渲染视差的 app / 网页 |
| 裸眼 3D（iOS 景深） | iOS 锁屏把主体抠出来压在时钟前（第 13 轮做过，`depth_mask.py`） | 普通 PNG，系统自己抠 |

静态图变「活」有三条技术路线，第四类是播放器 / 封装格式：

1. **深度视差 2.5D**：单目深度估计（MiDaS / Depth Anything）→ 按深度位移像素。便宜、可控、任何图都行；穿帮点在物体边缘（背景被拉伸）。
2. **生成式图生视频**：SVD / CogVideoX / Wan2.1 / LTX-Video / DynamiCrafter。真能让鱼游、水流；但要 8–24 GB 显存，一支 5 s 几分钟，不保证无缝循环，角色会漂。
3. **程序化特效**：粒子（星屑 / 花瓣 / 雪）、高光流光、呼吸辉光、Ken Burns 推拉。零风险，叠在 1 上效果最好。
4. **播放器 / 格式**：Lively、Wallpaper Engine、ScreenPlay（桌面）；UndeadWallpaper、Live Wallpaper Maker、FloatDeck（Android）；Motion Photo / Live Photo（相册格式）。

沙箱只有 CPU、出网只到 GitHub / PyPI / npm：路线 1 + 3 + 4 全部跑通（见下），路线 2 只盘点、给接法。

## 工具表（24 个 GitHub 项目）

| # | 项目 | ★ | 类别 | 做什么 | 硬件 / 平台 | 本轮 | 评价 |
|---|---|---|---|---|---|---|---|
| 1 | [BrokenSource/DepthFlow](https://github.com/BrokenSource/DepthFlow) | 1.6k | 2.5D | 图 (+深度) → 视差视频，steep-parallax 着色器，内置 Depth Anything，有 ComfyUI 节点 ([akatz-ai/ComfyUI-Depthflow-Nodes](https://github.com/akatz-ai/ComfyUI-Depthflow-Nodes) ★369) | 需 OpenGL（ModernGL）+ torch；有显卡最佳 | ✗ 沙箱无 EGL/GL、torch 2 GB | 这条路线最成熟的开箱工具，**有电脑就用它**；`live_wallpaper.py parallax` 是它的 CPU 单层近似 |
| 2 | [vt-vl-lab/3d-photo-inpainting](https://github.com/vt-vl-lab/3d-photo-inpainting) | 7.1k | 2.5D | CVPR 2020 分层深度 + 补洞，相机大幅度环绕也不穿帮 | GPU，权重外链 | ✗ | 效果最像「真 3D」，但老、慢、装起来麻烦 |
| 3 | [panrafal/depthy](https://github.com/panrafal/depthy) | 1.3k | 2.5D | 浏览器里图 + 深度 → 视差 GIF/视频（Google 相机 Lens Blur 时代的元老） | 浏览器 | ◐ 同算法自写 | 算法 = 按深度做 UV 偏移，我们的 parallax 模式就是它 |
| 4 | [longweekendlabs/parallax-studio](https://github.com/longweekendlabs/parallax-studio) | 4 | 2.5D | 桌面 app：自动深度 + 人像保护 + 循环 MP4/GIF 导出，模型 75 MB 全本地 | Win / Linux / mac | ✗ GUI | 2025 新作，给不想碰命令行的人 |
| 5 | [mert5961/SceneShift](https://github.com/mert5961/SceneShift) | 0 | 2.5D 网页 | 浏览器 WebGPU 跑 Depth Anything V2 + 光线步进视差 + 陀螺仪 / 麦克风 | 新版 Chrome | ◐ 同原理自写 | 它的「ray march 比朴素偏移好 4 dB」结论我们抄进了 `parallax_web.py`（6 步步进遮挡） |
| 6 | [thygate/stable-diffusion-webui-depthmap-script](https://github.com/thygate/stable-diffusion-webui-depthmap-script) | 1.9k | 2.5D | WebUI 插件：高分辨率深度图、立体对、3D 网格、补洞视频 | GPU + A1111 | ✗ | 已经在用 WebUI 的人顺手就能做 |
| 7 | [DepthAnything/Depth-Anything-V2](https://github.com/DepthAnything/Depth-Anything-V2) | 9.1k | 深度模型 | 当前最好的单目深度，Small 25M 参数 | 权重在 HF（沙箱不通） | ✗ | 有网就用它替换 MiDaS，边缘干净很多 |
| 8 | [isl-org/MiDaS](https://github.com/isl-org/MiDaS) | 5.4k | 深度模型 | v2.1 small 66 MB ONNX，CPU 0.4 s/张 | CPU 即可 | ✅ `depth_midas.py` | Lively「Depth Wallpaper」用的就是它；油画也能分出桌面 / 主体 / 墙，鱼群分不开 |
| 9 | [Stability-AI/generative-models](https://github.com/Stability-AI/generative-models) (SVD) | 27k | 图生视频 | 14/25 帧 576×1024 | ≥12 GB 显存 | ✗ | 2023 老将，运动小、稳定，适合壁纸这种「微动」 |
| 10 | [zai-org/CogVideo](https://github.com/zai-org/CogVideo) (CogVideoX-5B-I2V) | 13k | 图生视频 | 6 s 720×480 | 16 GB | ✗ | 开源里最早可用的 I2V，画风会漂 |
| 11 | [Wan-Video/Wan2.1](https://github.com/Wan-Video/Wan2.1) | 17k | 图生视频 | 1.3B / 14B，720p 5 s | 8–24 GB | ✗ | 2025 开源最强 I2V，油画笔触保持最好；ComfyUI 一键工作流多 |
| 12 | [Lightricks/LTX-Video](https://github.com/Lightricks/LTX-Video) | 11k | 图生视频 | 2B 蒸馏版实时级 | 8 GB | ✗ | 最快最省显存，细节略糊，做壁纸够 |
| 13 | [Doubiiu/DynamiCrafter](https://github.com/Doubiiu/DynamiCrafter) | 3.0k | 图生视频 | 开放域图片动画，有「循环视频」模式 | 12 GB | ✗ | **唯一把「生成无缝循环」做成功能的**，壁纸场景专用 |
| 14 | [guoyww/AnimateDiff](https://github.com/guoyww/AnimateDiff) | 12k | 图生视频 | SD1.5 运动模块 + SparseCtrl 从图起手 | 8 GB | ✗ | 2D 插画 / 动漫风最好用，写实差 |
| 15 | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | 146k | 工作台 | 以上 9–14 全有节点；配 Depthflow 节点可一条线做深度 + 视差 | GPU | ✗ | 有显卡时的总入口 |
| 16 | [lively-community/lively](https://github.com/lively-community/lively) | 20k | Windows 播放器 | MP4 / GIF / 网页 / **Depth Wallpaper（拖一张 PNG 自动 3D，MiDaS）** | Windows 10/11 | ☆ 用户侧 | **Windows 用户首选**：我们的 PNG 直接拖进去就是 3D；MP4 拖进去就是动态 |
| 17 | [kelteseth/ScreenPlay](https://github.com/kelteseth/ScreenPlay) | 260 | 桌面播放器 | 视频 / 网页 / QML 壁纸，跨平台 | Win / mac / Linux | ☆ | 开源的 Wallpaper Engine 平替 |
| 18 | [maocide/UndeadWallpaper](https://github.com/maocide/UndeadWallpaper) | 149 | Android | 任意视频设为主屏 / 锁屏动态壁纸，无广告 | Android 8+ | ☆ 用户侧 | 我们的 `-combo.mp4` 直接喂它 |
| 19 | [R-Dilipkumar/live-wallpaper-maker-android](https://github.com/R-Dilipkumar/live-wallpaper-maker-android) | 0 | Android | 分层编辑器：视频 / 图 / 粒子 / 文字，每层独立倾斜深度 | Android 10+ | ☆ | 吃我们导出的 `NN-fg.png` + `NN-bg.png` 两层 |
| 20 | [kxxoling/FloatDeck](https://github.com/kxxoling/FloatDeck) | 59 | Android | 陀螺仪 3D 视差 + 漂浮立绘（OpenGL ES） | Android | ☆ | 二次元向，两层 PNG 也能用 |
| 21 | [mihir-io/MotionPhotoMuxer](https://github.com/mihir-io/MotionPhotoMuxer) | 175 | 格式 | JPG + MP4 → Google 动态照片 | Python + exiv2 | ◐ 同格式自写 | `motion_photo.py android` 不依赖 exiv2，产物 `.MP.jpg` |
| 22 | [RhetTbull/makelive](https://github.com/RhetTbull/makelive) | 262 | 格式 | JPG + MOV → 苹果实况照片（AVFoundation） | 仅 macOS | ✗ | iPhone 实况壁纸的正路；没有 Mac 就用 intoLive |
| 23 | [wagerfield/parallax](https://github.com/wagerfield/parallax) | 17k | 网页 | 分层 DOM 跟随陀螺仪 / 鼠标 | 任何浏览器 | ◐ | 2014 经典，我们的 `parallax_web.py` 是 WebGL 版（按像素深度而不是整层） |
| 24 | [exiftool/exiftool](https://github.com/exiftool/exiftool) | — | 格式 | 写 ContentIdentifier 等元数据 | Perl，沙箱可 clone | ✅ | 结论：**不能给非 iPhone 照片从零造 Apple MakerNotes**，实况配对只能上设备 / Mac 做 |

✅ 实跑  ◐ 同原理 / 同格式自写并实跑  ☆ 用户设备上用（Windows / Android 侧）  ✗ 沙箱跑不了（GPU / GUI / 外链权重）

## 实测对比（金鱼01 金光鱼缸，1440×1920，6 s 30 fps，全部无缝循环）

`live_wallpaper.py` 六种模式 + 三种封装，文件在 Drive `结果/动态壁纸/工具对比/`（每种都有 MP4 + GIF 预览），对比图 `对比总图.jpg`。

| 方法 | 对应工具 | 看起来 | 穿帮点 | 适合 | 推荐 |
|---|---|---|---|---|---|
| kenburns 推拉 | ffmpeg zoompan / 任何剪辑软件 | 整幅缓慢呼吸 | 没有；但也最「不像动」 | 任何图，保底 | ★★ |
| parallax 深度视差 | depthy / DepthFlow / Lively Depth | 桌面、鱼缸往前探，墙往后退，像在手机上倾斜 | 鱼缸边缘 2–3 px 拉丝；鱼群被当成墙的一部分 | 有明确前后景的图（桌面 + 物体 + 墙） | ★★★★ |
| layers 两层 3D | Live Wallpaper Maker / FloatDeck 的分层 | 前后两层速度不同，立体感最强 | Otsu 阈值把桌面 + 鱼缸整块当前景，补洞处轻微糊 | 需要分层 PNG 的 app | ★★★ |
| particles 金粉 | 程序化 | 金色星屑上升闪烁，和画里的金光一体 | 粒子过大过亮会像雪花；默认已调小 | 金光 / 星空 / 烛光题材 | ★★★★ |
| shimmer 流光 | 程序化（水面着色器思路） | 金光柱和水面「流动」，高光呼吸 | 只在亮部起作用，白纸底的画要用 `--highlight sat` | 发光体、水面、星河 | ★★★★ |
| **combo 三合一** | — | 视差 + 流光 + 金粉，最像「真的动态壁纸」 | 同上叠加 | **金鱼 10 张成品用的就是它** | ★★★★★ |
| 3D 网页 | SceneShift / depthy / wagerfield | 手机倾斜即动，6 步遮挡修正边缘比 parallax 视频干净 | 需要浏览器打开，不能直接当系统壁纸 | 发给别人玩 / Lively 网页壁纸 | ★★★★ |
| Motion Photo `.MP.jpg` | MotionPhotoMuxer | 相册里是静图，长按会动；Pixel / 三星可设动态锁屏 | 微信传会被压成静图，要用文件方式传 | Android | ★★★ |
| Live Photo（JPG+MOV） | makelive / intoLive | iPhone 锁屏实况 | 沙箱只能把 MOV 的 identifier 写好，JPG 一半要在设备 / Mac 上完成 | iOS | ★★ |

观察：
- 金鱼这组是「深色厚涂 + 自发光主体」，shimmer + particles 增益最大；视差幅度 2.2% 宽就够，再大鱼缸边缘会撕。
- 水果这组（第 18 轮，已全量跑完）是「白纸底 + 彩色主体」：流光蒙版改成 `--highlight sat`，粒子关掉（`--particles none`；`petal` 在白纸上几乎看不见还添噪点），视差用 `--focus 0.35` 让水果整体往前「浮」出纸面，效果比金鱼还明显——因为白纸被 MiDaS 正确地判成了最远。帧差分验证：草莓 / 蓝莓 / 西瓜三张的运动都只落在画面主体上，纸纹区域差分全黑（纸没在呼吸），这就是 `sat` 蒙版的意义。
- 第 18 轮成品参数：`--modes combo --particles none --highlight sat --focus 0.35 --gif --export-layers`；10 张 1440×1920 combo mp4 ≈ 4 MB/张，分层 PNG 因白纸 bg 压不动约 7 MB/张。
- MiDaS 对油画的误判集中在「发光体」（金光柱、月亮）会被当成近景；要更干净换 Depth Anything V2（有网时）。

## 装到手机 / 电脑上

- **Android**：`-combo.mp4` → UndeadWallpaper（或三星「图库 → 视频 → 设为锁屏壁纸」≤ 15 s、vivo/OPPO 自带视频壁纸）；`.MP.jpg` → 相册长按会动，Pixel / 三星可直接设为动态锁屏；两层 PNG → Live Wallpaper Maker 做陀螺仪 3D。
- **iPhone**：MP4 → intoLive（免费）→ 保存为实况照片 → 设置壁纸（iOS 17+ 实况壁纸亮屏时播放）；有 Mac 用 makelive 配 JPG+MOV。
- **Windows**：Lively Wallpaper 拖 MP4 = 动态；拖 PNG 选 Depth Wallpaper = 自动 3D；Wallpaper Engine 用「场景 → 图片 → Depth Parallax」并导入我们的 `depth/NN.png`。
- **任何手机浏览器**：`3D网页/index.html`（整个文件夹一起拷），点「开启陀螺仪」。

## 有显卡时怎么接生成式（路线 2）

ComfyUI 装 Wan2.1-I2V-14B（24 GB）或 LTX-Video（8 GB），输入我们的 1440×1920 PNG，提示词写
「static camera, the goldfish slowly swim upward, golden glitter drifts, gentle ambient motion, oil painting texture preserved, seamless loop」，
出 5 s → `ffmpeg -filter_complex "[0]reverse[r];[0][r]concat"` 做正反拼接循环 → 再走 `motion_photo.py`。DynamiCrafter 的 loop 模式可以直接出循环。
生成式会把笔触抹平、鱼会变形，所以**先用路线 1+3 交付，生成式作为加料**。
