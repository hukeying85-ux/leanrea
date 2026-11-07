# xhs-relay —— 让 GitHub Actions 替沙箱下载小红书原图

Arena 沙箱出网只有 github / pypi / npm，小红书 CDN 一律不通；Actions 的 artifact 又存在
`*.blob.core.windows.net`（同样不通）。所以这个 workflow 在 runner 上下载，然后把结果 **commit 回触发它的那条分支**，
沙箱 `git pull` 就能拿到。

## 用法

1. 用 `fetch_page` 打开笔记链接（带 `xsec_token` 的分享链接），从页面里抄下图片 URL（`…/spectrum/<token>!nd_dft_wlteh_webp_3`）。
2. 编辑 `tools/xhs-relay/queue.json`：

   ```json
   {"jobs": [{
     "note_url": "https://www.xiaohongshu.com/discovery/item/<id>?xsec_token=…",
     "out_dir": "xhs-wallpaper-replica/examples/<name>/01-原图",
     "max_total_mb": 80,
     "image_urls": ["https://sns-web-i10.rednotecdn.com/…/spectrum/<token>!nd_dft_wlteh_webp_3", "…"]
   }]}
   ```

   `image_urls` 可省略——脚本会自己抓笔记页解析 `__INITIAL_STATE__`；但沙箱里先用 `fetch_page` 抄好更稳。
3. `git add tools/xhs-relay/queue.json && git commit -m "xhs-relay: queue <id>" && git push origin <分支>`
   （workflow 对 `tools/xhs-relay/**` 的 push 触发，也可以 `gh workflow run xhs-relay.yml --ref <分支>`）。
4. `gh run list --workflow xhs-relay.yml --branch <分支> -L 1` 看到 success 后 `git pull --rebase`。
   输出：`<out_dir>/01.png … NN.png`（每张取 4 种 URL 变体里最大的那个）、`note.json`（标题/正文/标签/作者/图片清单）、`note.md`。

## 为什么能拿到原图

小红书图片的 token（`spectrum/1040g…`）拼到无签名域名即原图：
`https://sns-img-bd.xhscdn.com/<token>`（PNG 原图，1440×3200 约 2–5 MB）或
`https://ci.xiaohongshu.com/<token>?imageView2/format/png`。网页上带时效签名的 `rednotecdn.com` 地址只是 1080 宽的 webp 预览。
不需要 cookie；如果以后需要登录态，把 cookie 字符串放进仓库 secret `COOKIES_XHS` 即可。

## 文件

- `xhs_fetch.py` —— runner 上跑的脚本（requests + Pillow，解析页面 → 下载 → 写 note.json/md）
- `queue.json` —— 任务清单（跑完不用清空：`out_dir` 里已有 `note.json` 的任务会跳过；要重抓加 `"force": true`）
- `../../.github/workflows/xhs-relay.yml` —— workflow（`xhs-relay[bot]` 提交，GITHUB_TOKEN 的 push 不会再触发自己）

## 已知坑

- `__INITIAL_STATE__` 里有 JS 的 `undefined`，要整体替换成 `null` 才能 `json.loads`；失败时脚本回退到正则抓 token。
- 提交信息里的「fetched N image(s)」依赖 `core.quotePath=false`，否则中文路径被转义、数字恒为 0。
- 单次 workflow 产物建议 < 80 MB（`max_total_mb`），大图集分多次 queue。
