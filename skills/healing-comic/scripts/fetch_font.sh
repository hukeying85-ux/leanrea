#!/usr/bin/env bash
# 下载霞鹜文楷 Regular（SIL OFL 1.1，与原指南所用字体同款）。
# 只需要一个中文字体；也可以把任意中文 .ttf/.ttc 路径传给 compose.py --font。
set -euo pipefail
DEST="${1:-$HOME/.fonts/LXGWWenKai-Regular.ttf}"
mkdir -p "$(dirname "$DEST")"
URL="https://github.com/lxgw/LxgwWenKai/raw/main/fonts/TTF/LXGWWenKai-Regular.ttf"
echo "下载 $URL -> $DEST"
curl -fL --retry 2 -o "$DEST" "$URL"
echo "完成。使用："
echo "  COMIC_FONT=$DEST python3 scripts/compose.py examples/spec.json --outdir examples/pages --html --contact-sheet"
# 也可用 gh（已登录 GitHub 的环境）：
# gh api repos/lxgw/LxgwWenKai/git/blobs/<sha> --jq .content | base64 -d > "$DEST"
