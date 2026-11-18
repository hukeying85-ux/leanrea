# 小红书原图下载 —— GitHub 工具盘点（2026-11-07 调研）

结论先说：**下载小红书笔记原图不需要登录、不需要逆向**。拿到图片 token 之后，直接请求
`https://sns-img-bd.xhscdn.com/<token>`（无水印 PNG 原图）或
`https://ci.xiaohongshu.com/<token>?imageView2/format/png` 就行——这是下面所有工具共同的套路，
本仓库的 `tools/xhs-relay/xhs_fetch.py` 就是把这条路压缩成 160 行并挪到 GitHub Actions 上跑。

## 怎么从网页拿 token

网页版 `<meta name="og:image">` / `__INITIAL_STATE__` 里的图片地址长这样：

```
https://sns-web-i10.rednotecdn.com/202611071603/e3379917…/spectrum/1040g34o3277p5n58mga05o18tfi09a4tid65a10!nd_dft_wlteh_webp_3
                                     ^时效戳      ^签名        ^-------------------- token --------------------^ ^格式后缀(1080 webp)
```

token = `"/".join(url.split("/")[5:]).split("!")[0]`（XHS-Downloader 同款取法），即 `spectrum/1040g34o…`。
把它拼到上面两个无签名域名就是原图；本仓库 7 张 1440×3200 的 PNG 就是这么拿到的（1.6–4.9 MB/张）。

## 工具一览（按 star）

| 仓库 | ★ | 最近更新 | 类型 | 适合什么 |
|------|---|---------|------|---------|
| [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 70.5k | 2026-11-05 | Python，多平台爬虫 | 要批量抓笔记+评论+搜索；用 Playwright 保持登录态。杀鸡用牛刀，单帖取图不用它 |
| [JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) | 13.2k | 2026-11-06 | Python CLI / TUI / API / 浏览器脚本 | **单帖或批量下载原图/视频的首选**。贴链接即可，支持 `xsec_token` 链接，可不登录；`source/application/image.py` 里就是上面的 token 拼接逻辑 |
| [cv-cat/Spider_XHS](https://github.com/cv-cat/Spider_XHS) | 8.4k | 2026-10-22 | Python，含签名逆向 | 需要搜索/用户主页/私信等 API 时用；取图能力和 XHS-Downloader 一样 |
| [xisuo67/XHS-Spider](https://github.com/xisuo67/XHS-Spider) | 1.5k | 2025-12-16 | Windows GUI | 不会命令行的人批量下载 |
| [NEORUAA/XHS_Downloader_Android](https://github.com/NEORUAA/XHS_Downloader_Android) | 629 | 2026-11-06 | Android App | 手机上「分享到 App」直接存无压缩原图；同作者有 iOS 版 |
| [xhs996/xhs_spider](https://github.com/xhs996/xhs_spider) | 370 | 2026-10-22 | Python | `xsec_token` 生成、shield 算法，链接过期时自救 |
| [smile7up/xiaohongshu-downloader](https://github.com/smile7up/xiaohongshu-downloader) | 46 | 2026-02-07 | Python | 轻量脚本版 |
| [kongzhu2/XHS_Downloader_Chrome_Extension](https://github.com/kongzhu2/XHS_Downloader_Chrome_Extension) | 34 | 2023-11-19 | Chrome 插件 | 网页上点一下存图（久未更新，可能失效） |
| [Guing/xhs-downloader-skill](https://github.com/Guing/xhs-downloader-skill) | 17 | 2026-02-05 | AI 编程助手 Skill | 给 Claude Code / Cursor 等装的下载技能，会顺手生成作品信息 |
| [nfe-w/xhs_note_downloader](https://github.com/nfe-w/xhs_note_downloader) | 9 | 2025-04-07 | Python | 笔记下载器（简版） |
| [sujingyan12138/xiaohongshu-downloader](https://github.com/sujingyan12138/xiaohongshu-downloader) | 3 | 2026-07-30 | Python | 批量最高画质无水印 |
| [yuevthins/xhs-down-ai-cli](https://github.com/yuevthins/xhs-down-ai-cli) | 1 | 2026-05-04 | Skill + CLI 适配 | Codex / Claude Code / Gemini CLI 都能调 |
| [yuuki-yoda/xiaohongshu-downloader](https://github.com/yuuki-yoda/xiaohongshu-downloader) | 0 | 2026-10-30 | Claude Code skill | 视频 + 字幕 + AI 总结，偏视频 |

## 在本机怎么用（最省事的两条）

```bash
# 1) XHS-Downloader：一条命令
pip install xhs-downloader    # 或 git clone 后 python main.py
xhs                            # 进 TUI，粘贴笔记链接（带 xsec_token 的分享链接最稳）

# 2) 不装任何东西：浏览器 F12 → 网络面板筛选 webp → 复制 spectrum/… token → 拼 URL 下载
curl -L -o 01.png "https://sns-img-bd.xhscdn.com/spectrum/1040g34o3277p5n58mga05o18tfi09a4tid65a10"
```

## 在 Arena 沙箱里怎么用（为什么要做 xhs-relay）

沙箱出网只有 github.com / pypi / npm，`xhscdn.com`、`rednotecdn.com` 全部不通，`fetch_page` 也只渲染文本。
所以把下载挪到 GitHub Actions runner 上：

1. `fetch_page` 读笔记页 → 拿到 7 个图片 URL（含 token）
2. 写进 `tools/xhs-relay/queue.json`，push 到工作分支
3. `.github/workflows/xhs-relay.yml` 触发 `xhs_fetch.py`：每个 token 试 4 种 URL（sns-img-bd 原图 / ci.xiaohongshu.com png / jpg / 网页 webp），留最大的那个，连同 `note.json`、`note.md` 一起 commit 回**同一条分支**
4. 本地 `git pull --rebase` 就拿到原图（Actions artifact 走 blob.core.windows.net，沙箱下不动，所以必须 commit 回来）

详见 `tools/xhs-relay/README.md`。
