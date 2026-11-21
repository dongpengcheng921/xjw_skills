#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pub_scan.py — 对外分发前扫描器（2026-11-21 立）

在**解包产物**上跑，不在源目录跑（源目录有 .bak_* 会稀释结果）。
命中即阻断发布；退出码 0=干净 / 1=命中 / 3=路径不存在。

用法：
  python3 pub_scan.py <解包目录>          # 扫全部文件
  python3 pub_scan.py <目录> --list      # 只列类别与条数，不打印原文
  python3 pub_scan.py <目录> --words "甲|乙"   # 发布前临时加内部词表（不进源码）

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

# 内部人名 / 目录名 / 业务代号：**默认留空**。
# 为什么留空：这个词表一旦写死就会进对外源码，本身构成泄露。
# 发布前用参数临时传，源码永远保持空：
#   python3 pub_scan.py <目录> --words "甲|乙|丙"
#   PSRD_SCAN_WORDS="甲|乙|丙" python3 pub_scan.py <目录>
INTERNAL_WORDS = []


def extra_words():
    """临时的内部词表：--words 优先，其次环境变量 PSRD_SCAN_WORDS。不进源码。"""
    raw = os.environ.get("PSRD_SCAN_WORDS", "").strip()
    av = sys.argv[1:]
    if "--words" in av:
        i = av.index("--words")
        if i + 1 < len(av):
            raw = av[i + 1]
    return [w for w in re.split(r"[|,，\s]+", raw) if w]


def internal_pattern(words):
    words = [w for w in dict.fromkeys(list(INTERNAL_WORDS) + list(words)) if w]
    if not words:
        return None
    return re.compile("|".join(re.escape(w) for w in words))

SKIP_EXT = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico"}


def walk(root):
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            yield p


def main():
    av = sys.argv[1:]
    quiet = "--list" in av
    # --words 带一个值，取值前先把它从位置参数里摘出去
    pos = []
    skip = False
    for i, a in enumerate(av):
        if skip:
            skip = False
            continue
        if a == "--words":
            skip = True
            continue
        if not a.startswith("-"):
            pos.append(a)
    if not pos:
        print(__doc__)
        sys.exit(3)
    root = pos[0]
    if not os.path.isdir(root):
        print(f"目录不存在：{root}", file=sys.stderr)
        sys.exit(3)
    words = extra_words()
    INTERNAL = internal_pattern(words)

    hits = []
    for p in walk(root):
        try:
            lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            checks = list(PATS) + ([("内部标识", INTERNAL)] if INTERNAL else [])
            for name, pat in checks:
                m = pat.search(line)
                if m:
                    rel = os.path.relpath(p, root)
                    hits.append((name, rel, i, m.group(0)))
    tag = f"（含临时词表 {len(words)} 个）" if words else ""
    if not hits:
        print(f"✅ 0 命中：可对外分发{tag}")
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
