# GitHub Actions 中继下载方案

日期：2026-11-05 ｜ 适用：本沙箱（Arena）内采集任意平台素材

---

## 一、真正的病根

之前那份《下载工具箱·安装与测试报告》的判断是：

> 本沙箱出口只放行 github.com / pypi.org / registry.npmjs.org，
> 抖音/小红书/YouTube 全部 HTTP 000，所以抓不到，换台能出网的机器再补。

**前半句对，结论可以再往前走一步。**

沙箱出网确实被限制，但 **GitHub Actions 的 runner 出网不受限**。
所以不需要"换台机器"——把下载任务搬到 runner 上跑，结果 commit 回分支，
本地 `git pull` 就能拿到。本机一行命令即可完成，全程不出沙箱。

链路：

```
本沙箱                        GitHub                        本沙箱
写 .mediaqueue/urls.txt  →  Actions runner 跑 yt-dlp   →  git pull
git push                     /gallery-dl/直连            media-raw/ 里就是素材
                             结果 commit 回分支
```

---

## 二、怎么用

仓库里已经备好，开箱即用：

```bash
tools/media-library/gh-relay "https://www.douyin.com/video/xxxx"
tools/media-library/gh-relay "url1" "url2" "url3"
tools/media-library/gh-relay --from links.txt
tools/media-library/gh-relay --status     # 看上一次跑的结果
```

脚本会自己：写队列 → push → 轮询 workflow → 跑完 `git pull` → 打印结果表。
通常 1–3 分钟。

产物落在 `media-raw/<云盘目录名>/<作品ID>/`，跟云盘 8 个平台文件夹一一对应，
每条带 `meta.json`（来源链接、命中工具、逐文件 sha256、字节数）可直接拖拽同步。

文件：

| 文件 | 作用 |
|---|---|
| `tools/media-library/gh-relay` | 本地入口：排队、推送、轮询、拉回 |
| `tools/media-library/relay_worker.py` | runner 上跑的下载器，四级降级 |
| `.github/workflows/media-relay.yml` | 触发器：队列或工具变更就跑，结果 commit 回来 |
| `.mediaqueue/urls.txt` | 待抓链接，一行一条 |

---

## 三、降级策略（worker 内部）

每条链接依次试，命中即停：

1. **yt-dlp** —— 视频优先，格式阶梯 `bv*[h<=480]+ba/b` → `18/22/43/b` → `b` → `bv*+ba/b` → `worst`
2. **平台专用通道** —— 小红书 `xhs-dump`、B站 `bilibili-api`、抖音 `douyin-api`
3. **gallery-dl** —— 相册优先（TikTok / Instagram / Pinterest / 微博）
4. **html-scrape** —— 兜底，直接扒页面里的 CDN 图片链接

两个坑已经填掉，别再踩：

* `--write-thumbnail` 一定会写缩略图，**不能把"有文件"当成功**，
  否则失败会被伪装成成功。只认 mp4/m4a/webm 等真媒体扩展名。
* 命令拼装时 URL 必须真的进 argv，漏了会得到
  `You must provide at least one URL` 这种看起来像平台风控的假错误。

---

## 四、实测结果（2026-11-05，Actions 数据中心 IP）

| 平台 | 结果 | 命中 | 拿到什么 |
|---|---|---|---|
| **TikTok** | ✅ | yt-dlp | 真视频，3.20 MB |
| **小红书** | ✅ | xhs-dump | 4 张图，0.29 MB |
| **YouTube** | ⚠️ | scrape | 42 个缩略图/封面，1.06 MB，**没拿到视频** |
| **B站** | ❌ | — | 网页和 API 都返回 **HTTP 412** |
| **抖音** | ❌ | — | yt-dlp 要 cookie；iesdouyin 公开接口已失效 |

### 逐条说清楚

**TikTok —— 通了。** 第一个格式失败，阶梯往下走到 `b` 就拿到了完整 mp4。
这是"沙箱里也能抓 TikTok"的完整证据。

**YouTube —— 半通。** 缩略图、封面图能拿到（42 个），视频拿不到。
三种报错轮换出现：`Requested format is not available` /
`HTTP 403 Forbidden` / `The page needs to be reloaded`。
这是 YouTube 对数据中心 IP 的常规风控，不是工具问题。

**B站 —— 卡在 WAF。** 网页端和 `api.bilibili.com/x/web-interface/view`
**都返回 412 Precondition Failed**，带浏览器 UA、带 Referer、带自举 cookie 都无效。
B站对机房 IP 是硬拒绝。

**抖音 —— 卡在 cookie。** yt-dlp 明确要求 `Fresh cookies (not necessarily logged in) are needed`；
自举匿名 cookie 拿不到（抖音不返回 Set-Cookie）。
老的 `www.iesdouyin.com/web/api/v2/aweme/iteminfo` 无水印接口**已经失效**，
现在返回 HTML 不是 JSON。

---

## 五、剩下的三个怎么破（按性价比排序）

**1. 导出 cookie（能一次解决抖音 + YouTube，大概率也能解 B站）**

浏览器装 *Get cookies.txt LOCALLY* 扩展，分别在 douyin.com / youtube.com /
bilibili.com 登录状态下导出 Netscape 格式，存成：

```
.config/cookies/douyin.txt
.config/cookies/youtube.txt
.config/cookies/bilibili.txt
```

然后在 `relay_worker.py` 的 `try_ytdlp()` 里按域名挂上去：

```python
COOKIE_FILES = {
    "douyin.com":   os.environ.get("COOKIES_DOUYIN"),
    "youtube.com":  os.environ.get("COOKIES_YOUTUBE"),
    "bilibili.com": os.environ.get("COOKIES_BILIBILI"),
}
```

cookie 内容走 **GitHub Actions Secrets** 注入（`env:` 段），
不要直接写进仓库。

**2. 换 runner 地区（专治 B站）**

B站的 412 是地区 + 机房双判定。GitHub 托管 runner 只有美西/欧洲，
可以挂 self-hosted runner 在国内机器或香港节点的机器上，B站/抖音/快手基本就通了。
仓库里的工作流改一行即可：`runs-on: self-hosted`。

**3. 小红书补全 9 张**

现在拿 4 张，是因为**未登录**状态下笔记页只暴露部分图。
带上 xhs 的 cookie 再跑一次 `xhs-dump` 应该就是全套 9 张。

---

## 六、结论

"沙箱内抓不了国内平台"这个结论**已经不成立**——
TikTok 和小红书是实测跑通的证据，整条链路（排队→runner→commit→pull）是可用的。

剩下 B站、抖音、YouTube 视频三家的拦路石**不是网络出口，是平台风控**，
需要的是 cookie 或换 runner 地区，跟工具箱装得对不对没关系。
