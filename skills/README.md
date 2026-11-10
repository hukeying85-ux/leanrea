# skills/ —— 本仓库全部技能（Agent Skills）

每个子文件夹就是一个独立的 skill：`SKILL.md` 是给 agent 读的主文件（frontmatter 里有 `name` / `description`），
旁边的 `scripts/`、`references/`、`examples/` 是它用到的脚本、参考资料和跑过的样例。
这是 [skills CLI](https://skills.sh) / Claude Code 认的标准布局：`skills/<名字>/SKILL.md`。

| skill | 一句话 | 入口 | 体量 |
|---|---|---|---|
| [`xhs-wallpaper-replica/`](xhs-wallpaper-replica/) | **小红书壁纸全流程**：笔记链接 → 原图抓取（`tools/xhs-relay`）→ 生图模型逐张复刻 / 同风格新场景 10 张 → 干净 PNG + 总图 + 双机封面 + iOS 预览 → 文案 → Google Drive 按轮归档 | [SKILL.md](xhs-wallpaper-replica/SKILL.md) · [README](xhs-wallpaper-replica/README.md)（17 轮结果索引） | 4 个脚本 · 15 个样例目录 |
| [`healing-comic/`](healing-comic/) | 长文 / PDF → 6–9 页小红书治愈系简笔漫画 + 幻灯视频（中文由脚本压字，生图不写字） | [SKILL.md](healing-comic/SKILL.md) · [README](healing-comic/README.md) · [说明](healing-comic/说明.md) | 脚本 + 多套样例 |
| [`leanrea/`](leanrea/) | 用本机 CLI 工具逆向任何软件（Electron / Mach-O / Go / APK …），不装 MCP | [SKILL.md](leanrea/SKILL.md) | 单文件 8 KB |

## 怎么用

- **给 agent 装上**（任选）：
  ```sh
  npx skills add <owner>/leanrea            # skills CLI 会列出这三个 skill 让你选
  cp -R skills/xhs-wallpaper-replica ~/.claude/skills/   # 或手动拷到 Claude Code 的 skills 目录
  ```
  没有 skills 机制的 agent，直接把对应的 `SKILL.md` 贴进系统提示即可，都是纯文本。
- **在仓库里跑脚本**：先 `cd skills/<名字>`，SKILL.md / README 里的命令都是相对 skill 自己的目录写的
  （例如 `python3 scripts/phone_mockup.py all examples/…/spec.json …`）。
- **壁纸流程的两个外部依赖**不在 skill 里，放在仓库根目录：
  - [`tools/xhs-relay/`](../tools/xhs-relay/README.md)：GitHub Actions 代沙箱下载小红书原图 / 视频，`queue.json` 里的 `out_dir` 写成 `skills/xhs-wallpaper-replica/examples/<name>/01-原片`；
  - `google_drive/`（gitignored）：上传 Drive 前的暂存目录。

## 约定

- 新 skill 就在这里再开一个文件夹，不要放回仓库根目录。
- 每个 skill 自带 `README.md` 记录「这次跑了什么、怎么复现」，`SKILL.md` 只写流程和踩坑，样例进 `examples/`。
- 样例里的大图（PNG）照旧进 git；仓库根目录的 [`README.md`](../README.md) 有三个 skill 的总览。
