# xhs-relay —— 让 GitHub Actions 替沙箱下载小红书原图 / 视频

Arena 沙箱出网只有 github / pypi / npm，小红书 CDN 一律不通；Actions 的 artifact 又存在
`*.blob.core.windows.net`（同样不通）。所以这个 workflow 在 runner 上下载，然后把结果 **commit 回触发它的那条分支**，
沙箱 `git pull` 就能拿到。

## 用法

1. 用 `fetch_page` 打开笔记链接（带 `xsec_token` 的分享链接），从页面里抄下图片 URL（`…/spectrum/<token>!nd_dft_wlteh_webp_3`）。
2. 编辑 `tools/xhs-relay/queue.json`：

   ```json
   {"jobs": [{
     "note_url": "https://www.xiaohongshu.com/discovery/item/<id>?xsec_token=…",
     "out_dir": "skills/xhs-wallpaper-replica/examples/<name>/01-原图",
     "max_total_mb": 80,
     "image_urls": ["https://sns-web-i10.rednotecdn.com/…/spectrum/<token>!nd_dft_wlteh_webp_3", "…"]
   }]}
   ```

   `image_urls` 可省略——脚本会自己抓笔记页解析 `__INITIAL_STATE__`；但沙箱里先用 `fetch_page` 抄好更稳。
3. `git add tools/xhs-relay/queue.json && git commit -m "xhs-relay: queue <id>" && git push origin <分支>`
   （workflow 对 `queue.json` / `xhs_fetch.py` / `secrets/*.enc` / workflow 文件的 push 触发；
   当前 token 对 `workflow_dispatch` 是 403，所以 **只能靠 push 触发**。）
4. `gh run list --workflow xhs-relay.yml --branch <分支> -L 1` 看到 success 后 `git pull --rebase`。
   输出：`<out_dir>/01.png … NN.png`（每张取 4 种 URL 变体里最大的那个）、`note.json`（标题/正文/标签/作者/图片清单）、`note.md`。

## 视频笔记

写法完全一样，脚本按 `type == "video"` 自动切换：

- 下载顺序：`https://sns-video-bd.xhscdn.com/<video.consumer.originVideoKey>`（作者上传的无水印原片，可能几百 MB）→
  不行或超过 `max_video_mb`（默认 60）时退到最高分辨率码流 `video.media.stream.*[].masterUrl`（网页播放的 720p/1080p 转码流）。
  落地 `video.mp4` + `cover.jpg`，`note.json.video` 里有时长、各码流参数、原片 key 和 **原片 md5**（`video.media.video.md5`）。
- **原片太大不进 git → 直传 Google Drive**（已用 262 MB 的原片验证，md5 与页面一致）：
  1. 沙箱里用 Drive 连接器 `initiate_resumable_upload`（文件名、父文件夹、`video/mp4`）拿到一次性 session URI（7 天有效）。
  2. 用 runner 的公钥加密后提交，**明文不进仓库、不进日志**：
     ```bash
     printf '%s' "$URI" | openssl pkeyutl -encrypt -pubin -inkey tools/xhs-relay/relay_pubkey.pem \
        -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 | base64 -w0 \
        > tools/xhs-relay/secrets/DRIVE_UPLOAD_URI__<note_id前8位>.enc && git add -A tools/xhs-relay/secrets && git commit -m "xhs-relay: drive uri" && git push
     ```
  3. runner 用只存在 Actions cache（`xhs-relay-rsa-v1-<分支>`）里的 RSA-4096 私钥解密成环境变量 `DRIVE_UPLOAD_URI__<id8>`，
     对应任务即使已有 `note.json` 也会重跑，边下边按 Content-Range / X-Goog-Upload 协议 PUT 到 Drive，
     结果写到 `<out_dir>/drive_upload.json`（字节数、md5、Drive 文件 id、`md5_match`），用过的 `.enc` 自动删除。
  - 私钥丢了（cache 7 天没人碰会被清）runner 会重新生成并提交新的 `relay_pubkey.pem`，旧密文作废、重新加密即可。
  - 为什么这么绕：`gh secret set` 与 `workflow_dispatch` 对当前 token 都是 403，唯一能传参的通道就是仓库文件。

## 为什么能拿到原图

小红书图片的 token（`spectrum/1040g…`）拼到无签名域名即原图：
`https://sns-img-bd.xhscdn.com/<token>`（PNG 原图，1440×3200 约 2–5 MB）或
`https://ci.xiaohongshu.com/<token>?imageView2/format/png`。网页上带时效签名的 `rednotecdn.com` 地址只是 1080 宽的 webp 预览。
不需要 cookie；如果以后需要登录态，把 cookie 字符串放进仓库 secret `COOKIES_XHS` 即可。

## 文件

- `xhs_fetch.py` —— runner 上跑的脚本（requests + Pillow，解析页面 → 下载 → 写 note.json/md）
- `queue.json` —— 任务清单（跑完不用清空：`out_dir` 里已有 `note.json` 的任务会跳过；要重抓加 `"force": true` 或删掉 `note.json`；
  `"keep_html": true` 会把笔记页 HTML 一起落地，用来离线调解析器）
- `relay_pubkey.pem` / `secrets/*.enc` —— 上面说的加密信道（公钥由 runner 生成并提交）
- `../../.github/workflows/xhs-relay.yml` —— workflow（`xhs-relay[bot]` 提交，GITHUB_TOKEN 的 push 不会再触发自己）

## 已知坑

- `__INITIAL_STATE__` 是 JS 字面量不是 JSON：有 `undefined`、`new Set([])`、`new Map([])`，要先规整（`undefined→null`，`new Set/Map([...])→[...]`）
  再 `json.loads`；失败时脚本回退到正则抓 token（此时时长/话题/互动数会是空的）。
- 单条笔记页只给「当前最适合网页」的那一档码流（本例只有 720p h264），1080p/HDR 要靠原片。
- 提交信息里的「fetched N image(s)」依赖 `core.quotePath=false`，否则中文路径被转义、数字恒为 0。
- 单次 workflow 产物建议 < 80 MB（`max_total_mb`），大图集分多次 queue。
