#!/usr/bin/env bash
# fetch_bilibili.sh —— 把 B 站源视频拉进「原始素材」目录（只需在本机跑一次）。
#
# 为什么不在 Agent 沙箱里跑：Agent 容器出网只放行 github / npm / pypi，
# www.bilibili.com、api.bilibili.com、i0.hdslb.com 全部 TLS 被拒
# （curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL），装什么下载器都连不上。
# 所以这个脚本是给「有完整网络的那台机器」用的，Agent 侧的复刻走
# 「视频标题 + 视频里那个 GitHub 项目的事实」路线。
#
# 用法:
#   bash scripts/fetch_bilibili.sh BV1suxg6MEJz "/g/我的云端硬盘/一二和布布 - 原始素材/素材 08"
#   ENGINE=bbdown bash scripts/fetch_bilibili.sh "https://www.bilibili.com/video/BV1suxg6MEJz/" ./素材08
#
# 环境变量:
#   ENGINE=ytdlp|bbdown   （默认 ytdlp，没装 yt-dlp 时自动尝试 BBDown）
#   COOKIES_BROWSER=chrome  想拿 1080P 以上就得带登录 Cookie
set -euo pipefail

URL_OR_BV="${1:-}"
DEST="${2:-./素材 08}"
ENGINE="${ENGINE:-ytdlp}"
COOKIES_BROWSER="${COOKIES_BROWSER:-}"

if [[ -z "$URL_OR_BV" ]]; then
  echo "用法: $0 <BV号或完整链接> [目标目录]" >&2
  exit 64
fi
case "$URL_OR_BV" in
  http*) URL="$URL_OR_BV" ;;
  BV*)   URL="https://www.bilibili.com/video/$URL_OR_BV/" ;;
  *)     URL="https://www.bilibili.com/video/$URL_OR_BV/" ;;
esac

mkdir -p "$DEST"
echo "源：$URL"
echo "目标目录：$DEST"

have() { command -v "$1" >/dev/null 2>&1; }

if [[ "$ENGINE" == "bbdown" ]] || { [[ "$ENGINE" == "ytdlp" ]] && ! have yt-dlp && have BBDown; }; then
  # BBDown：对 B 站最省事，自动选流、自动合轨、支持字幕与弹幕
  if ! have BBDown; then
    echo "没装 BBDown。装法：winget install nilaoda.BBDown | scoop install bbdown" >&2
    exit 69
  fi
  echo "引擎：BBDown"
  ARGS=("$URL" --work-dir "$DEST" --multi-thread --file-pattern "<videoTitle>")
  [[ -n "$COOKIES_BROWSER" ]] && ARGS+=(--use-mp4box)
  BBDown "${ARGS[@]}"
else
  if ! have yt-dlp; then
    echo "没装 yt-dlp。装法：winget install yt-dlp | scoop install yt-dlp | pipx install yt-dlp" >&2
    exit 69
  fi
  echo "引擎：yt-dlp"
  ARGS=(
    -f "bv*+ba/b" --merge-output-format mp4
    --write-subs --sub-langs "zh.*" --write-thumbnail --write-info-json
    --embed-metadata --no-overwrites
    -o "%(uploader)s - %(title).80s.%(ext)s" -P "$DEST"
  )
  [[ -n "$COOKIES_BROWSER" ]] && ARGS+=(--cookies-from-browser "$COOKIES_BROWSER")
  yt-dlp "${ARGS[@]}" "$URL"
fi

echo "完成。落盘："
ls -lh "$DEST" | tail -n +1
echo
echo "下一步（Agent 侧复刻）："
echo "  1) 用下载好的视频核对分镜与口播事实（README / 官网），不要照抄别人的解说词"
echo "  2) 按 SKILL.md G 段出 10 页：底图 → art_shift → compose → slideshow → grid_preview"
