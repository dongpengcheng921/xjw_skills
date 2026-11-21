#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pub_scan.py — 对外分发前扫描器（2026-11-21 立）

在**解包产物**上跑，不在源目录跑（源目录有 .bak_* 会稀释结果）。
命中即阻断发布；退出码 0=干净 / 1=命中 / 3=路径不存在。

用法：
  python3 pub_scan.py <解包目录>          # 扫全部文件
  python3 pub_scan.py <目录> --list      # 只列类别与条数，不打印原文

为什么模式要拼起来写：
  本文件自己也在包里。若把正则以完整字面量写在源码里，扫描器必然扫到自己那几行，
  变成"永远红"的假闸门（同类事故：mem_lint 的 STALE_PAT 曾把另一个副本判红 7 处）。
  所以下面一律用字符串拼接构造模式——运行时等价，静态文本里不出现完整样态。
"""
import os
import re
import sys

D = "/"          # 斜杠单独取，避免出现路径样态
SL = os.sep

PATS = [
    ("路径", re.compile(
        D + "Users" + D + r"|" + D + "home" + D + r"|[A-Za-z]:\\\\")),
    ("平台ID", re.compile(r"\bou_[0-9a-f]{8,}|\boc_[0-9a-f]{8,}|\bcli_[0-9a-f]{8,}")),
    ("凭证", re.compile(r"\bsk-[A-Za-z0-9]{16,}|\bBearer\s+[A-Za-z0-9._-]{10,}|APP_SECRET\s*=\s*\S+")),
    ("凭证文件", re.compile(r"\." + "env" + r"\b|password\s*=\s*\S+|secret\s*=\s*\S+")),
]

# 内部人名 / 目录名 / 业务代号：按项目实际情况补，用 | 分隔
INTERNAL_WORDS = [
    # 例：内部成员称呼、只有本机存在的顶层目录、自有库名
]
INTERNAL = re.compile("|".join(INTERNAL_WORDS)) if INTERNAL_WORDS else None

SKIP_EXT = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico"}


def walk(root):
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            yield p


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    quiet = "--list" in sys.argv
    if not args:
        print(__doc__)
        sys.exit(3)
    root = args[0]
    if not os.path.isdir(root):
        print(f"目录不存在：{root}", file=sys.stderr)
        sys.exit(3)

    hits = []
    for p in walk(root):
        try:
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            for name, pat in [(n, c) for n, c in PATS] + ([("内部标识", INTERNAL)] if INTERNAL else []):
                m = pat.search(line)
                if m:
                    rel = os.path.relpath(p, root)
                    hits.append((name, rel, i, m.group(0)))
    if not hits:
        print("✅ 0 命中：可对外分发")
        sys.exit(0)
    for name, rel, i, s in hits:
        if quiet:
            print(f"  🔴 {name}: {rel}:{i}")
        else:
            print(f"  🔴 {name}: {rel}:{i}  …{s}…")
    print(f"\n🔴 合计 {len(hits)} 处命中 ⇒ 阻断发布")
    sys.exit(1)


if __name__ == "__main__":
    main()
