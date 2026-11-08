#!/usr/bin/env python3
"""把本轮产出镜像同步到结果分支的 media-raw 目录。

为什么要它：结果分支是长期累积的存档，而本轮工作区只有这一轮下载的东西。
用 `cp -r` 覆盖的话，上一轮的重复文件、改名前的旧文件都留在里面越积越多
（7 张图曾经被存成 14 个文件）。所以按「平台目录 / 笔记目录」逐个做镜像：
本轮没有的文件，在结果分支里也要删掉。

用法：python3 publish_sync.py <本轮media-raw> <结果分支里的media-raw>
"""
import os
import shutil
import sys


def mirror(src_dir, dst_dir, report):
    """让 dst_dir 的内容与 src_dir 完全一致。"""
    os.makedirs(dst_dir, exist_ok=True)
    want = set(os.listdir(src_dir))
    for name in sorted(set(os.listdir(dst_dir)) - want):
        p = os.path.join(dst_dir, name)
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                os.remove(p)
            except OSError:
                pass
        report.append("DEL %s" % os.path.relpath(p, dst_dir))
    for name in sorted(want):
        s, d = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        if os.path.isdir(s):
            mirror(s, d, report)
        else:
            if not os.path.exists(d) or (
                    os.path.getsize(s) != os.path.getsize(d)):
                shutil.copy2(s, d)
                report.append("PUT %s" % os.path.relpath(d, dst_dir))


def main():
    if len(sys.argv) < 3:
        print("usage: publish_sync.py SRC DEST")
        return 1
    src, dest = sys.argv[1], sys.argv[2]
    if not os.path.isdir(src):
        print("skip: %s is not a directory" % src)
        return 0
    os.makedirs(dest, exist_ok=True)

    report = []
    # 顶层文件（_LAST_RUN.md 之类）直接覆盖
    for name in sorted(os.listdir(src)):
        s = os.path.join(src, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dest, name))

    # 平台目录 / 笔记目录逐层镜像
    for plat in sorted(os.listdir(src)):
        psrc = os.path.join(src, plat)
        if not os.path.isdir(psrc) or plat.startswith("_"):
            continue
        pdst = os.path.join(dest, plat)
        os.makedirs(pdst, exist_ok=True)
        for note in sorted(os.listdir(psrc)):
            nsrc = os.path.join(psrc, note)
            if not os.path.isdir(nsrc):
                if os.path.isfile(nsrc):
                    shutil.copy2(nsrc, os.path.join(pdst, note))
                continue
            mirror(nsrc, os.path.join(pdst, note), report)

    head = ["cwd=%s" % os.getcwd(),
            "src=%s (exists=%s)" % (os.path.abspath(src), os.path.isdir(src)),
            "dest=%s (exists=%s)" % (os.path.abspath(dest), os.path.isdir(dest)),
            "src top=%s" % sorted(os.listdir(src))[:10],
            "changes=%d" % len(report)]
    body = head + report[:200]
    print("\n".join(body))
    # 日志读不到（results-receiver 被墙），把报告写进结果分支自己取证
    try:
        d = os.path.join(dest, "_debug")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "_publish.txt"), "w", encoding="utf-8").write(
            "\n".join(body))
    except Exception as e:
        print("report write failed: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
