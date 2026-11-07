#!/usr/bin/env python3
"""清掉结果目录里不是素材的文件。

为什么需要它：结果分支 media-out 是用 cp -r 覆盖式同步的，删不掉远端
已经存在的文件。之前有一次提取把页脚的营业执照 PDF 当图片存了下来
（最大 9MB），靠这个脚本按文件头把它们认出来删掉。

用法：python3 purge_nonmedia.py <目录>
"""
import os
import sys

# 只要内容开头是这些，就一定不是图片/音视频素材
BAD_HEAD = (b"%PDF", b"<html", b"<!DOCTYPE html", b"<!doctype html",
            b"<?xml", b"<svg", b"<!ENTITY")
# 这些扩展名是说明文件，不参与内容判定
KEEP_EXT = (".md", ".json", ".txt", ".log", ".csv")


def purge(root):
    removed = []
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            if p.lower().endswith(KEEP_EXT):
                continue
            try:
                head = open(p, "rb").read(64)
            except Exception:
                continue
            if head.startswith(BAD_HEAD):
                try:
                    os.remove(p)
                    removed.append(p)
                except Exception:
                    pass
    return removed


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "media-raw"
    if not os.path.isdir(target):
        print("skip: %s not a directory" % target)
        sys.exit(0)
    gone = purge(target)
    print("purged non-media files: %d" % len(gone))
    for g in gone[:30]:
        print("  -", g)
