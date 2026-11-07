# 素材08 第 1 轮 · 《手机上的广告，一根线关掉》

**源视频**：[BV1suxg6MEJz](https://www.bilibili.com/video/BV1suxg6MEJz/) —《来自民间大佬制作APP，GitHub刚发布就狂揽2.6k Stars！手机去广告这块最高的山来了！一款国产安卓手机去广告神器》（UP：青临同学，2026-10-27 发布）

**源视频里讲的工具**：[`rddmwmddr/android-ad-cleaner`](https://github.com/rddmwmddr/android-ad-cleaner)（中文名「肉呆去广告」，MIT）
—— 通过 ADB 连电脑，只拨系统和 App 自带的开关，关掉国产安卓的开屏广告、下拉热搜、应用商店推广位、营销推送、广告组件和快应用；不 root、不刷机、可还原，附带 Mac / Windows 桌面客户端和 AI 智能体一条命令跑法。发布 3 天 2.6k★，本轮制作时 6.8k★。

**本轮产出**：10 页 3:4 漫画成品 + 40 秒轮播视频 + 总预览图 + B 站文案 + 三个新脚本。

---

## 1. 目录

```
runs/素材08-r1/
  art/            生图模型直出的 10 张无字底图（896×1200）
  art-fit/        垂直下移 110px 后的底图（1080×1447，给点题句腾净区）
  pages/          10 张成品 1080×1447（素材08_01.png … 素材08_10.png）
  pages/preview.html, preview.jpg   compose.py 自带的两份预览
  video/素材08-r1.mp4              40.0s / 1080×1440 / 30fps / 9.6MB / 无音轨
  素材08-总预览图.jpg               5×2 拼版总预览（2388×1470）
  spec.json       排版输入（标题 / 标签 / 点题句 / 气泡锚点）
  copy-素材08-肉呆去广告.md           B 站发布文案 + 分镜表
  README.md       本文件
```

## 2. 十页结构（一页 = 一个动作 + 一句台词 + 两个角色）

| # | 标签 | 点题句 | 布布（触发句） | 一二（引导句） |
|---|---|---|---|---|
| 01 | — | 手机上的广告 / 一根线关掉 | 副题：不 root、不刷机，只拨系统自带的开关 | |
| 02 | 开屏广告 | 打开 App，先看五秒广告 | 跳过键在哪，手指都找酸了 | 它本来就不想让你找到 |
| 03 | 下拉热搜 | 搜索框一拉，全是别人热搜 | 我只想搜个天气而已 | 顺手动两下，就能关干净 |
| 04 | 应用商店 | 商店里的轮播，比软件还显眼 | 装个软件，还得先逛广告 | 这些推广位，系统里能关 |
| 05 | 营销推送 | 通知栏一天响十次，全是推荐 | 手机一震，我以为有人找我 | 留下快递和天气就好 |
| 06 | 快应用 | 点错一下，就跳出个小程序 | 手指一抖，又跳出来一个 | 快应用也能一次性关掉 |
| 07 | 接上电脑 | 一根数据线，点五下就完事 | 要装一堆东西吗 | 就一根线，插上点几下 |
| 08 | 不 root | 不刷机，只拨自带的开关 | 会不会把手机弄坏了 | 不动系统，只动那几个开关 |
| 09 | 能还原 | 关了什么，都能一条条退回 | 改错了怎么办 | 改之前有备份，一条命令还原 |
| 10 | 手机安静了 | 广告停了，时间还给自己 | 今天没人找我吧 | 没人找你，挺好的 |

情绪曲线：**烦（02–06 五个具体场景，读者逐条对号入座）→ 解（07–09 三步讲清做法与安全边界）→ 松（10 收尾）**。
五页「烦」各自对应源工具的一大类开关，读者在第 3 页就会想「我手机也这样」。

## 3. 关于「下载源视频」

**这个沙箱下不了 B 站视频**：容器出网只放行 github / npm / pypi，`www.bilibili.com`、`api.bilibili.com`、`i0.hdslb.com` 全部 TLS 连接被拒（`SSL_ERROR_SYSCALL`），装 `yutto`/`BBDown`/`yt-dlp` 也一样连不上。所以本轮是**按视频标题 + 视频里那个 GitHub 项目的 README/官网事实**做的复刻，不是逐帧比对。

在你的本机（Windows，G 盘那个云端硬盘目录）跑下面这条就能把原片放进 `素材 08`：

```powershell
# 任选其一，都已经在 scripts/fetch_bilibili.sh 里写好
winget install yt-dlp          # 或 scoop install yt-dlp
yt-dlp -f "bv*+ba/b" --merge-output-format mp4 `
  -o "G:\我的云端硬盘\一二和布布 - 原始素材\素材 08\%(title)s.%(ext)s" `
  "https://www.bilibili.com/video/BV1suxg6MEJz/"
```

想要弹幕/字幕/封面：`--write-subs --write-thumbnail --write-info-json`；B 站要登录才给 1080P 以上，加 `--cookies-from-browser chrome`。
（`scripts/fetch_bilibili.sh` 里也给了 BBDown 的写法——它是目前对 B 站最省事的 CLI。）

## 4. 本轮新增的三个脚本（都可跨轮复用）

| 脚本 | 解决的问题 | 本轮实测 |
|---|---|---|
| `scripts/art_shift.py` | 生图模型把角色画得偏高，中幅点题句（y≈0.568）压脸。**不重画**，整张底图下移 N px、顶部补暖纸色再裁回 1080×1447 | `--dy 110` 后 10/10 页点题句落在角色头顶上方 |
| `scripts/slideshow.py` | SKILL E 段的 ffmpeg 配方自动化：zoompan 缓推/缓拉、xfade 0.5s、封面 4s + 内容 4.5s、libx264 crf21 | 10 页 → 40.0s / 1080×1440 / 9.6MB，编码 56s |
| `scripts/grid_preview.py` | 一套成品页 → 一张带标题的 5×2 总预览图 | 2388×1470，缩到 200px 宽仍认得出封面标题 |

踩过的坑（已写进 SKILL.md 的失败模式表）：
**`-loop 1 -t N` 喂 zoompan 会让帧数按 `d` 倍放大**——第一次跑出 10 分 56 秒、30MB。正确做法是每张图只喂一帧，由 `zoompan=d=<帧数>` 负责复制，再补 `-t 总时长` 兜底。

## 5. 复现

```sh
cd healing-comic
python3 -m pip install Pillow imageio-ffmpeg
bash scripts/fetch_font.sh                       # 或自备任意中文 ttf

# 1) 底图已在 art/，只想改文案：
python3 scripts/art_shift.py --src runs/素材08-r1/art --out runs/素材08-r1/art-fit --dy 110
python3 scripts/compose.py runs/素材08-r1/spec.json --layout xhs2 \
  --font ~/.fonts/LXGWWenKai-Regular.ttf --font-medium ~/.fonts/LXGWWenKai-Regular.ttf \
  --art-root runs/素材08-r1 --outdir runs/素材08-r1/pages --html --contact-sheet

# 2) 出视频 + 总预览图
python3 scripts/slideshow.py --spec runs/素材08-r1/spec.json \
  --pages runs/素材08-r1/pages --out runs/素材08-r1/video/素材08-r1.mp4
python3 scripts/grid_preview.py --pages runs/素材08-r1/pages \
  --out runs/素材08-r1/素材08-总预览图.jpg --font ~/.fonts/LXGWWenKai-Regular.ttf --cols 5
```

## 6. 版权与合规

- 画面为 **AI 生成**，角色是「一二和布布」高相似重绘（原作：黄小 B）。**发布时必须勾选平台的「AI 生成合成内容」标识**；商用 / 长期做号请换 `examples/art-original/` 的原创角色。
- 文案里的事实（免 root、只拨开关、可还原、MIT、机型适配）来自 `android-ad-cleaner` 仓库 README 与官网；工具本身与其作者无隶属关系，属于「介绍 + 教程」范畴。
- 视频无音轨是刻意的：B 站发布时在站内选配乐能蹭热点曲库。
