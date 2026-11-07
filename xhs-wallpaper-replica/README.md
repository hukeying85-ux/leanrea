# xhs-wallpaper-replica

把一条小红书壁纸笔记变成一套可发布的复刻壁纸：下载原图 → 生图模型重画无字底图 → 脚本加 iOS 锁屏/主屏覆盖层 → 总图 + 双机封面 → 文案 → Google Drive 按轮归档。技能本体在 [SKILL.md](SKILL.md)。

## 这次跑的例子：弥弥壁纸《小新手机壁纸｜过的是我梦寐以求的生活》

| | 内容 | 位置 |
|---|---|---|
| 第 1 轮 | 原帖 7 张 PNG 原图（1440×3200，第 7 张为 1600×1600 双机海报）+ 笔记文本 | `examples/shinchan-6aedad8b/01-原图/` |
| 第 2 轮 | 复刻 10 张：6 张按原帖逐张重画 + 4 张按正文新补场景（缘侧发呆 / 全家早餐 / 长椅冰棍 / 夏夜线香花火）；全部是 1440×3200 干净壁纸，不带任何手机 UI | `examples/shinchan-6aedad8b/02-复刻/` |
| 总图 | 2×5 拼版 | `02-复刻/总图.jpg` |
| 封面 | 双机预览（两张竖图并排，仿原帖第 7 图的构图，不带手机 UI） | `02-复刻/封面-双机预览.jpg` |
| 第 4 轮 | **新画 10 张**（不是复刻）：雨天窗边 / 放学路上 / 厨房做蛋糕 / 阳台晾被子 / 海边沙堡 / 夏夜西瓜电视 / 雪天堆雪人 / 幼稚园午睡 / 河堤骑车 / 秋日银杏；同一画风、全新场景、1440×3200 干净壁纸 | `examples/shinchan-6aedad8b/03-新画10张/` |
| 第 3 轮 | 小红书视频下载测试（木可 · 吉隆坡机场 T2 过夜转机，64 s）：网页码流 + 封面进 git，262 MB 无水印原片由 runner 直传 Drive | `examples/video-test-6a4be129/` |
| 文案 | 第 2 轮发布文案 + 第 1 轮原帖存档 | `references/copy-小新壁纸.md` |
| 工具盘点 | GitHub 上的小红书原图下载工具 + token 取法 | `references/github-tools.md` |

Google Drive：`我的云端硬盘/一二和布布 - 原始素材/素材 05/` 下 `第1轮-原版7张（小红书下载）`、`第2轮-复刻10张`（10 张干净 PNG、总图、封面、文案 Doc、SKILL）、`第3轮-视频下载测试`（`原片/` 与 `结果/` 分开）、`第4轮-新画10张`（10 张全新场景的干净 PNG、总图、封面、文案 Doc、spec）。

![总图](examples/shinchan-6aedad8b/02-复刻/总图.jpg)

## 复现

```bash
# 0) 原图：沙箱里走 tools/xhs-relay（见 tools/xhs-relay/README.md）；本机直接拼 token 下载
# 1) 底图：按 SKILL.md ③ 用 generate_image 出 10 张 688×1536 无字图 → 02-复刻/art/01..10.png
# 2) 字体
mkdir -p ~/.fonts && cd ~/.fonts   # Inter-Variable.ttf（google/fonts 仓库）+ LXGWWenKai-Medium.ttf（lxgw/LxgwWenKai release）
# 3) 合成
python3 scripts/phone_mockup.py all examples/shinchan-6aedad8b/02-复刻/spec.json \
    --art-dir examples/shinchan-6aedad8b/02-复刻/art --out /path/to/第2轮-复刻10张 --format png
```

仓库里只留 `art/`（真正的源文件，688×1536 PNG）和 `壁纸/` 的 JPG 留档；1440×3200 的 PNG 交付件可随时由上面一条命令重新生成。想看带 iOS 锁屏/主屏界面的效果图加 `--ui ios`（仅展示用，不是壁纸）。

## 说明

- 角色为第三方 IP（蜡笔小新），仅供个人壁纸、非商用；全部图片为 AI 生成，发布时勾选「AI 生成」。
- 688×1536 → 1440×3200 是 Lanczos 放大，手机上观感正常，100% 看比原帖略软；要更锐利在本机过一遍 Real-ESRGAN（anime 模型，×2）再合成。
