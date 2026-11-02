# GitHub 上「漫画制作 Skills」调研

调研时间：2026-11-02。方法：`gh search repos` 多组中英文关键词（comic skill / manga skill / 文章转漫画 / 小红书 漫画 / 条漫 / 四格），再用 `gh api repos/.../contents/SKILL.md` 逐个读源码，不是只看 README。star 数为当日 GitHub API 返回值。

## 结论先说

**有，而且不少；但没有一个是「开箱即用的小红书一二布布治愈简笔漫画」。** 现有项目分三类：

1. **文章 / 教材 → 漫画**（最接近，解决「长文变分镜 + 角色一致性」）
2. **小红书图文 / 卡片排版**（解决 3:4、18 图上限、封面、发布文案）
3. **重型条漫流水线**（多格连载、并行生图、审核门禁，对本任务过度设计）

一二布布那种「简单」恰恰是它们都不做的：那些项目都在加流程、加角色卡、加校验，而治愈简笔漫画需要的是**减到一页一个动作、一句台词**。所以最省事的做法是：借 1 类项目的「角色卡 + 无字底图 + 脚本填字」三个约定，自己写一个 8 KB 的 SKILL.md（即本仓库 `healing-comic/SKILL.md`）。

## 值得抄的（按相关度）

| 仓库 | ★ | 做什么 | 对本任务可借鉴 / 不适用 |
|---|---|---|---|
| [jasonmarkppp/crayon-shinchan-xhs-skill](https://github.com/jasonmarkppp/crayon-shinchan-xhs-skill) | 0 | **把资料改编成蜡笔漫画主题的小红书多页图文**：核实资料 → 定题 → 分镜 → 固定头像署名 → 逐页生图 → 检查 → 整套预览 + 发布文案。默认 6 张、3:4、奶油蜡笔质感，每页一个知识点 | ⭐ 最贴近的「资料 → 漫画套图」全流程，连 6 张 / 3:4 / 每页一个点都和本方案一致。直接换风格提示词即可 |
| [trumanzhongqiang/science-comic-skill](https://github.com/trumanzhongqiang/science-comic-skill) | 0 | 科普漫画：事实核查 → 角色卡锚定 → 分镜 → 逐格出图 → **空白气泡检测 + 中文合成**；自带 `tools/compose.py`、`preview.html`、`examples/` | ⭐⭐ 工程上最该抄：`detect_regions.py` 定位空白泡、`compose.py` 做中文禁则折行 / 字号自适应 / 拼图；明确写了「精确文字、精确数量一律后期脚本绘制」「20 格以上角色一致性不可靠」 |
| [changyiwu/teach-comic](https://github.com/changyiwu/teach-comic) | 0 | 教材 → 4:5 / 1080×1350 / 2×2 四格，生图阶段画**空白气泡**，之后用 JSON 把中文排进泡里，保留 raw → normalized → final 三阶段 | ⭐⭐ 「气泡外观由生图画、文字由脚本填」的分工，以及绝不覆盖原图的三阶段文件命名。负面清单很实用：`no text, no letters, no lettering, no captions` |
| [iithink88/article-to-comic-skill](https://github.com/iithink88/article-to-comic-skill) | 8 | 文章 → 漫画，**角色档案 + 全文注入**保证一致性，按字数定 4–16 格，输出自包含 HTML | ⭐ 角色档案字段（发型 / 服装 / 配饰三锚点）与「prompt = 风格前缀 + 角色A + 角色B + 动作 + 镜头 + 氛围」公式 |
| [zhuyansen/xhs-cover-skill](https://github.com/zhuyansen/xhs-cover-skill) | 1 | 小红书封面：两行标题 + 一个数字 + 两三样证据，一个 JSON 出 3:4 / 16:9 / 9:16，**只依赖 Pillow，不联网、不调模型** | ⭐⭐ 和 leanrea 同款「一个脚本替代一堆服务」的思路；本仓库 `compose.py` 就是这个模式的漫画版 |
| [xiangzhengqian/xiaoyang-xhs-comic-workflow](https://github.com/xiangzhengqian/xiaoyang-xhs-comic-workflow) | 0 | 小红书漫画工作流：story scripting、visual identity constraints、page composition scripts、QC checks | 同赛道，可作交叉参考 |

## 生态里体量大、但不必装

| 仓库 | ★ | 定位 | 判断 |
|---|---|---|---|
| [yang0/handraw-style](https://github.com/yang0/handraw-style) | 6900 | 367 种手绘风格编号画廊 + 中英双语生图提示词库 | 想要换画风时查编号很香；但它是提示词库，不管分镜和排版 |
| [comeonzhj/Auto-Redbook-Skills](https://github.com/comeonzhj/Auto-Redbook-Skills) | 2433 | 自动写小红书笔记 + 自动出图 + 自动发布 | 偏「运营自动化」，会引入发布依赖；本任务只要一套图 |
| [autoclaw-cc/xiaohongshu-skills](https://github.com/autoclaw-cc/xiaohongshu-skills) | 2018 | 浏览器自动化：登录 / 发布 / 搜索 / 互动 | 只在要自动发布时才需要 |
| [dososo/blcaptain-style-skill](https://github.com/dososo/blcaptain-style-skill) | 181 | 中文图文卡片，3 视觉语言 / 35 版式 / 11 色板 | 做知识卡片很强，但成品是「海报级卡片」不是漫画 |
| [acheAIsuiyimen/ache-life-to-comic-skill](https://github.com/acheAIsuiyimen/ache-life-to-comic-skill) | 79 | 漫画手帐长期连载，按月成册、HTML 主版本 | 工程最完整（设计系统、QA 门禁、月册），但面向「长期续更」，对一次性 8 页太重 |
| [Irixil/xiaohongshu-skill](https://github.com/Irixil/xiaohongshu-skill) | 22 | 知识图解：3:4 卡片、Gate 0–5、封面 + 至少 4 卡 | 「先选题再出图、母稿保护」的编辑纪律值得抄；它主张把中文直接生进图里，与本方案相反（简笔漫画不适用） |
| [rnthking/redya-skills](https://github.com/rnthking/redya-skills) | 17 | 红鸦 AI 图文生成的 Skill / MCP / OpenAPI 接入 | 依赖第三方账号与积分 |
| [hanzhangzzz/agent-skills-zh](https://github.com/hanzhangzzz/agent-skills-zh) | 1 | 中文优先技能集，含 GPT-Image 提示词导演、小红书下载器 | 提示词导演可用来打磨风格词 |
| [FightJs/vertical-comic-skills](https://github.com/FightJs/vertical-comic-skills) | 0 | 条漫逐格成品五件套：阶段审查、并行生图、规则记忆、ZIP 交接 | 30+ 格连载才用得上 |
| [sa-san10/rimochan-nyamuru-manga-forge](https://github.com/sa-san10/rimochan-nyamuru-manga-forge) | — | 日文 OMNY(YAML 分镜) → 原稿 PNG 流水线 | 分镜 YAML 思路好，但对「6 页简笔」是杀鸡用牛刀 |
| [onewaymyway/mini_agent](https://github.com/onewaymyway/mini_agent) `comic-4panel` | — | 2×2 四格漫画，对白由生图模型直接画进画面 | 反面教材：中文交给生图，正是本方案要避开的 |

## 推荐组合

- **只想要一套图**：直接用本仓库 `healing-comic/`（单 SKILL.md + Pillow 脚本），不装任何依赖。
- **想要更多画风可选**：加 `yang0/handraw-style` 查风格编号。
- **以后要做 20+ 页连载**：换 `ache-life-to-comic-skill` 或 `FightJs/vertical-comic-skills`。
- **要自动发布**：再加 `autoclaw-cc/xiaohongshu-skills`（注意平台合规）。
