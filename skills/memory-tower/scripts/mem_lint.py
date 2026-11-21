#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mem_lint.py — 记忆体系体检（2026-10-20 立）

设计动机：记忆这套「索引常驻 + 本体按需」的体系，最大的风险不是体积超限，而是
**指针悄悄腐坏**（迁移改路径、文件被挪走、口径写死旧环境）——没人用就不会发现。
本工具把「腐坏」变成可机检的项，供每周自检 / 迁移后复查调用。

检查项：
  1. 体积红线：INDEX<8K / **MEMORY<10K（平台注入硬帽）** / RULES<20K / SECONDARY<300K（字符）
  2. 旧环境残留：E:\\ 、C:/Users、Dpc_wy、Docker 等 Windows 时代标记
  3. 索引指针存活：INDEX.md 里反引号包住的路径是否还存在
  4. 日报断档：最近 10 天应有交易日日志（缺失只提示，不判死）

用法：python3 scripts/tools/mem_lint.py [--quiet]
退出码：0 全绿 / 1 有 🔴 / 2 有 ⚠️
"""
import os, re, sys, glob
from datetime import datetime, timedelta

MEM = os.environ.get("PSRD_MEM") or os.path.join(os.getcwd(), ".psrd")
WS = os.environ.get("PSRD_WS") or ""
CLAW = os.environ.get("PSRD_CLAW") or ""
QUIET = '--quiet' in sys.argv

RED, YEL, OK = [], [], []

# ⚠️ P 的硬帽是 **10,000 字符**（不是 25K）：平台每轮只注入 MEMORY.md 的前 10,000 字符，
# 超出部分**静默丢弃**（悬案台账、飞书身份表就在文件尾部）。2026-10-25 前此处写 25000，
# 比真实上限宽 2.5 倍 ⇒ P 超帽时 lint 仍报绿，属假绿。R/S 不注入，阈值不变。
LIMITS = {'INDEX.md': 8000, 'MEMORY.md': 10000, 'RULES.md': 20000, 'SECONDARY.md': 300000}

def chars(p):
    try:
        return len(open(p, encoding='utf-8', errors='replace').read())
    except FileNotFoundError:
        return None

def check_sizes():
    for fn, lim in LIMITS.items():
        p = os.path.join(MEM, fn)
        n = chars(p)
        if n is None:
            RED.append(f"{fn} 不存在")
        elif n > lim:
            RED.append(f"{fn} 超红线：{n:,} > {lim:,}")
        elif n > lim * 0.9:
            YEL.append(f"{fn} 逼近红线：{n:,} / {lim:,}（{n/lim:.0%}）")
        else:
            OK.append(f"{fn} {n:,}/{lim:,}")

STALE_PAT = re.compile(r'E:\\|E:/OP|C:/Users|C:\\Users|Dpc_wy')

def check_stale():
    targets = []
    targets += glob.glob(os.path.join(MEM, '*.md'))
    if CLAW:
        targets += glob.glob(os.path.join(CLAW, '*.md'))
    if WS:
        targets += glob.glob(os.path.join(WS, 'scripts/tools/*.py'))
        targets += glob.glob(os.path.join(WS, 'skills/*/SKILL.md'))
        targets += glob.glob(os.path.join(WS, '.workbuddy/memory/automations/*/memory.md'))
        targets += glob.glob(os.path.join(WS, 'studio/*.py'))
    ME = os.path.abspath(__file__)
    hits, hist = {}, {}
    for p in targets:
        # 🔧 2026-11-21 修自证式误报：本文件的 STALE_PAT 定义与说明里就写着 E:\\ / C:/Users 等字样，
        #    扫到别的副本（如工作区 scripts/tools/mem_lint.py）必然自己把自己判红。
        #    ⇒ 按文件名跳过所有 mem_lint.py 副本，不只跳过正在跑的这一份。
        if os.path.abspath(p) == ME or os.path.basename(p) == 'mem_lint.py':
            continue
        try:
            txt = open(p, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        txt = '\n'.join(l for l in txt.splitlines()
                        if 'mem_lint' not in l and '旧环境标记' not in l)
        n = len(re.findall(STALE_PAT, txt))
        if not n:
            continue
        rel = os.path.relpath(p, WS)
        # 活文件（跑得着）→ 红；历史记录（日志/SECONDARY/归档）→ 仅统计
        is_hist = ('SECONDARY.md' in rel or '/_archive/' in rel or '/backup/' in rel
                   or re.search(r'memory/\d{4}-\d{2}-\d{2}\.md$', rel) is not None)
        (hist if is_hist else hits)[rel] = n
    if not hits:
        OK.append("活文件旧路径标记 0 处")
    for k, v in sorted(hits.items(), key=lambda kv: -kv[1])[:12]:
        RED.append(f"活文件旧路径 {v} 处：{k}")
    if hist:
        OK.append(f"历史记录旧路径 {sum(hist.values())} 处（不注入，不判红）")
    return sum(hits.values()) + sum(hist.values())

PTR_PAT = re.compile(r'`([^`\n]{3,120})`')

def check_pointers():
    idx = os.path.join(MEM, 'INDEX.md')
    if not os.path.exists(idx):
        RED.append("INDEX.md 缺失，指针检查跳过"); return
    txt = open(idx, encoding='utf-8', errors='replace').read()
    dead, live = [], 0
    for m in PTR_PAT.finditer(txt):
        s = m.group(1).strip()
        if not (s.startswith('/') or s.startswith('~') or s.startswith('skills/')
                or s.startswith('scripts/') or s.startswith('picker/')):
            continue
        if any(c in s for c in ' <>|*'):     # 通配/占位，跳过
            continue
        p = os.path.expanduser(s)
        if not p.startswith('/'):
            p = os.path.join(WS, p) if WS else os.path.join(MEM, p)
        if os.path.exists(p):
            live += 1
        else:
            dead.append(s)
    if dead:
        for d in dead[:10]:
            RED.append(f"索引指针失效：{d}")
    OK.append(f"索引指针存活 {live} 条")

def check_daily():
    d = datetime.now()
    # 🔧 2026-11-21 修噪声：全新体系（根目录与 _archive 里一个 YYYY-MM-DD.md 都没有）不列缺失日期。
    #    起因：新装用户第一次体检就见「日报缺：11-13、11-14…」一排，会以为坏了。
    #    判据：一份日志都没有 = 尚未开始记录（正常态）；只要有一份，就照旧查断档。
    has_any = bool(glob.glob(os.path.join(MEM, "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))) \
        or bool(glob.glob(os.path.join(MEM, "_archive", "**", "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"),
                             recursive=True))
    if not has_any:
        OK.append("日报：尚未开始记录（新体系正常态；有第一份日志后自动查断档）")
        return
    miss, archived = [], []
    for i in range(1, 11):
        day = d - timedelta(days=i)
        if day.weekday() >= 5:      # 周末不判
            continue
        name = f"{day:%Y-%m-%d}.md"
        if os.path.exists(os.path.join(MEM, name)):
            continue
        # 🔧 2026-10-21 修假红：日报按 R §13「14 天后移 _archive/daily_YYYYMM/」归档，
        #    但 10-18 那次蒸馏归档进的是 _archive/distilled_YYYYMMDD/ ⇒ 只看根目录会把
        #    「已归档」误报成「断档」。现在递归扫 _archive，找到即算存在（单列归档数）。
        if glob.glob(os.path.join(MEM, "_archive", "**", name), recursive=True):
            archived.append(f"{day:%Y-%m-%d}")
        else:
            miss.append(f"{day:%Y-%m-%d}")
    if miss:
        YEL.append("日报缺：" + "、".join(miss[:6]) + ("…" if len(miss) > 6 else ""))
    else:
        tail = f"（其中 {len(archived)} 篇已归档：{'、'.join(archived)}）" if archived else ""
        OK.append("近 10 天日报齐全" + tail)



def _require_mem():
    if not os.path.isdir(MEM):
        print(f"记忆目录不存在：{MEM}", file=sys.stderr)
        print("先跑 init_psrd.py --dir <目录> 初始化，或设 PSRD_MEM 指向已有记忆目录。", file=sys.stderr)
        sys.exit(3)

def main():
    _require_mem()
    check_sizes()
    n_stale = check_stale()
    check_pointers()
    check_daily()

    if not QUIET:
        print("═══ 记忆体系体检 ═══")
        for t in OK:  print(f" ✅ {t}")
        for t in YEL: print(f" ⚠️  {t}")
        for t in RED: print(f" 🔴 {t}")
        print(f"\n小结：✅{len(OK)} / ⚠️{len(YEL)} / 🔴{len(RED)}；旧环境标记合计 {n_stale} 处")
    if RED: sys.exit(1)
    if YEL: sys.exit(2)

if __name__ == '__main__':
    main()
