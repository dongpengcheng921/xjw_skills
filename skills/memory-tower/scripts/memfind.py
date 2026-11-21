#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memfind.py — 记忆检索器（"硬盘"的读磁头）

把「记忆体系」当成分层存储来用：
  INDEX.md  +  MEMORY.md   = 内存（常驻注入，小）
  RULES.md  /  SECONDARY.md / D / _archive  = 硬盘（不注入，按需读）

本工具负责「按需读」这一半——不用把 R/S 整篇塞进上下文，
而是 关键词 → 命中行 + 节号 + 上下文，用一次工具调用换回注入额度。

用法
  python scripts/tools/memfind.py <关键词> [...]        # 多关键词 AND
  python scripts/tools/memfind.py --sec 12             # 按节号直接取 R 的 §12
  python scripts/tools/memfind.py --layer R|S|D|all    # 限定层
  python scripts/tools/memfind.py --stat               # 各层体积 + 红线
  python scripts/tools/memfind.py --index              # 打印内存层（INDEX 全文）
  python scripts/tools/memfind.py --todo               # 空指针抽检

设计要点
  * 默认只回 **命中行 + 所在节标题 + 命中上下文**，绝不 dump 全篇
  * 命中行支持 `+N` 参数控制上下文行数（默认 0，只回本行）
  * 节内检索：`--sec 12` 直接取 R §12 全节（比 grep 更好读）
  * 空指针告警：INDEX §2 列的关键词若在 R 里 grep 不到 ⇒ 报告（防索引腐坏）
"""
import sys, os, re, json, argparse, datetime
from pathlib import Path

# ---------- 路径 ----------
MEM = Path(os.environ.get("PSRD_MEM") or (Path.cwd() / ".psrd"))
WS = Path(os.environ["PSRD_WS"]) if os.environ.get("PSRD_WS") else None
USAGE = MEM / "USAGE.jsonl"      # 读取埋点：每次检索落一条，供 memgov usage 分析
LAYERS = {
    "INDEX": [MEM / "INDEX.md"],
    "P":     [MEM / "MEMORY.md"],
    "R":     [MEM / "RULES.md"],
    "S":     [MEM / "SECONDARY.md"],
    "D":     sorted(MEM.glob("20[0-9][0-9]-*.md")),
    "ARC":   sorted(MEM.glob("_archive/**/*.md")),
    # 推广语料（"硬盘"扩展区）——索引页常驻引用，本体按需读
    "DOC":   sorted((WS / "picker/docs").glob("*.md")) if WS else [],
    "SKILL": sorted(WS.glob("skills/*/SKILL.md")) if WS else [],
    "REPORT": sorted((WS / "Claw/reports").glob("**/*.md")) if WS else [],
}
# 索引页（这些是"内存"，可整体打印）
INDEXES = {
    "DOC":   (WS / "picker/docs/INDEX.md") if WS else MEM / "_no_ws_doc",
    "SKILL": (WS / "skills/INDEX_generated.md") if WS else MEM / "_no_ws_skill",
}
# P 硬帽 10,000 = 平台注入上限（10-25 由 25000 修正，见 mem_lint.py 注释）
REDLINES = {"INDEX": 8000, "P": 10000, "R": 20000, "S": 300000}

C_OK, C_WARN, C_ERR, C_DIM, C_KEY, C_SEC = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1;36m", "\033[1;35m"
C_END = "\033[0m"
if not sys.stdout.isatty():
    C_OK = C_WARN = C_ERR = C_DIM = C_KEY = C_SEC = C_END = ""


def read(p):
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def layer_files(name):
    """返回该层的文件列表；all/short 前缀都支持。"""
    name = name.upper()
    if name in ("ALL", "*"):
        out = []
        for k in ("INDEX", "P", "R", "S", "D", "ARC"):
            out += LAYERS[k]
        return out
    if name == "ALL2":   # 含推广语料
        out = []
        for k in ("INDEX", "P", "R", "S", "DOC", "SKILL", "REPORT"):
            out += LAYERS[k]
        return out
    if name not in LAYERS:
        alias = {"RULES": "R", "MEMORY": "P", "SECONDARY": "S", "INDEX": "INDEX",
                 "DOCS": "DOC", "PICKER": "DOC", "SKILLS": "SKILL"}
        name = alias.get(name, name)
    return LAYERS.get(name, [])


def find_section(lines, idx):
    """向上找最近的 markdown 标题行，返回 (节标题, 行号)。"""
    for j in range(idx, -1, -1):
        m = re.match(r"^(#{1,3})\s+(.*)$", lines[j])
        if m:
            return m.group(2).strip(), j + 1
    return "", 0


def log_usage(entry):
    """把一次检索落进 USAGE.jsonl（可观测：哪些条目被查过/从没被查过）。"""
    entry = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **entry}
    try:
        with USAGE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def grep(files, kws, ctx=0, limit=60, quiet_empty=True):
    """在 files 里搜 kws（AND 语义：同一行须含全部关键词）。返回 (命中数, 命中节标题集合)。"""
    total = 0
    sections = []
    for p in files:
        if not Path(p).exists():
            continue
        lines = read(p).splitlines()
        hits = []
        for i, ln in enumerate(lines):
            if all(k.lower() in ln.lower() for k in kws):
                hits.append(i)
        if not hits:
            continue
        print(f"\n{C_KEY}── {Path(p).name} ──{C_END}  {len(hits)} 命中")
        last_sec = None
        shown = 0
        for i in hits:
            if shown >= limit:
                print(f"  {C_DIM}… 还有 {len(hits)-shown} 条，用更具体的关键词或调 --limit{C_END}")
                break
            sec, secno = find_section(lines, i)
            if sec != last_sec:
                print(f"  {C_SEC}§ {sec}{C_END}  {C_DIM}(L{secno}){C_END}")
                last_sec = sec
                if sec:
                    sections.append(f"{Path(p).name}::{sec}")
            lo, hi = max(0, i - ctx), min(len(lines), i + ctx + 1)
            for k in range(lo, hi):
                mark = "▶" if k == i else " "
                print(f"  {mark} L{k+1}: {lines[k].strip()[:400]}")
            shown += 1
            total += 1
    if total == 0 and not quiet_empty:
        print(f"{C_WARN}无命中：{' + '.join(kws)}{C_END}")
    return total, sorted(set(sections))


def get_section(file, num):
    """取 RULES.md 的某个 §<num> 整节（到下一个同级/更高级标题为止）。"""
    lines = read(Path(file)).splitlines()
    pat = re.compile(r"^##\s+" + re.escape(str(num)) + r"(?!\d)")
    start = None
    for i, ln in enumerate(lines):
        if pat.match(ln):
            start = i
            break
    if start is None:
        print(f"{C_ERR}未找到 §{num}{C_END}")
        return False
    # 到下一个 ## 标题
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j]):
            end = j
            break
    body = "\n".join(lines[start:end]).rstrip()
    print(f"{C_KEY}══ {Path(file).name} §{num} ══{C_END}")
    print(body)
    print(f"\n{C_DIM}（{len(body)} 字符 · L{start+1}-{end}）{C_END}")
    return True


def stat():
    print(f"{C_KEY}═══ 记忆体系体积现状 ═══{C_END}")
    print(f"{'层':<7}{'文件':<24}{'字符':>11}{'字节':>11}  红线")
    for k in ("INDEX", "P", "R", "S"):
        for p in LAYERS[k]:
            if not Path(p).exists():
                continue
            s = read(p)
            rl = REDLINES.get(k)
            tag = ""
            if rl:
                tag = f"{C_OK}✅ <{rl//1000}K{C_END}" if len(s) <= rl else f"{C_ERR}❌ 超{rl}{C_END}"
            print(f"{k:<7}{Path(p).name:<24}{len(s):>11,}{len(s.encode('utf-8')):>11,}  {tag}")
    # 汇总类
    groups = [("D", LAYERS["D"], "20[0-9][0-9]-*.md"), ("ARC", LAYERS["ARC"], "_archive")]
    for k, fs, pat in groups:
        tot = sum(len(read(p)) for p in fs)
        print(f"{k:<7}{f'{pat} ({len(fs)} 个)':<24}{tot:>11,}  {C_DIM}不注入{C_END}")
    # 推广语料
    print(f"{C_DIM}── 推广语料（硬盘扩展区）──{C_END}")
    for k in ("DOC", "SKILL", "REPORT"):
        fs = LAYERS[k]
        tot = sum(len(read(p)) for p in fs)
        idxp = INDEXES.get(k)
        idxn = f"索引 {len(read(idxp)):,}" if idxp and idxp.exists() else f"{C_WARN}无索引{C_END}"
        print(f"{k:<7}{f'({len(fs)} 个)':<24}{tot:>11,}  {C_DIM}不注入 · {idxn}{C_END}")
    inj = sum(len(read(p)) for p in LAYERS["INDEX"] + LAYERS["P"])
    demand = sum(len(read(p)) for k in ("R", "S", "D", "ARC", "DOC", "SKILL", "REPORT") for p in LAYERS[k])
    print(f"\n{C_OK}▶ 常驻注入面（INDEX+P）= {inj:,} 字符{C_END}")
    print(f"{C_DIM}▶ 按需层（R+S+D+ARC+DOC+SKILL+REPORT）= {demand:,} 字符（不占注入）{C_END}")
    return True


def corpus(name):
    """打印某推广语料的索引页。"""
    name = name.upper()
    idxp = INDEXES.get(name) or INDEXES.get({"DOCS": "DOC", "PICKER": "DOC", "SKILLS": "SKILL"}.get(name, name))
    if not idxp or not Path(idxp).exists():
        print(f"{C_ERR}该层无索引页（可用 mkindex.py 生成）：{name}{C_END}")
        return False
    print(read(idxp))
    return True


def _extract_kw(seg):
    """从 INDEX §2 段落里抽关键词：以 | 和 / 和 、 分隔，去括号注，只留含实义的 token。"""
    kws = []
    for blk in re.findall(r"：([^：\n]{4,})", seg):
        for k in re.split(r"[｜|/、,，]", blk):
            k = k.strip()
            k = re.sub(r"[（(].*?[)）]", "", k).strip()
            k = re.sub(r"^[①-⑩★🔴⚠️\s]+", "", k).strip()
            if 2 <= len(k) <= 40 and not k.startswith("http"):
                kws.append(k)
    return list(dict.fromkeys(kws))


def todo(which="R"):
    """空指针抽检：INDEX §2 里出现的英文标识符/代码类关键词逐个在 RULES.md 里找。

    说明：中文短语是"人工摘要标签"，不要求逐字命中（这是设计）；
    真正需要零容忍的是 **代码标识符 / 文件名 / 命令**——它们是指针的锚点。
    """
    idx = read(MEM / "INDEX.md")
    m = re.search(r"##\s*2.*?(?=\n##\s)", idx, re.S)
    seg = m.group(0) if m else idx
    kws = _extract_kw(seg)
    # 只对"代码类"锚点做严格校验：含字母/下划线/dot/py/等，且非纯中文
    code_kw = [k for k in kws if re.search(r"[A-Za-z_]", k) and not re.fullmatch(r"[\u4e00-\u9fff]+", k)]
    target = read(MEM / "RULES.md").lower()
    miss = []
    for k in code_kw:
        # 取其中最长的英文 token 做子串检查（容忍 INDEX 里的连接符写法）
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_./\-*]{1,}", k)
        if not tokens:
            continue
        if not all(t.lower() in target for t in tokens):
            miss.append((k, [t for t in tokens if t.lower() not in target]))
    print(f"{C_KEY}═══ INDEX → RULES.md 锚点抽检 ═══{C_END}")
    print(f"关键词 {len(kws)} 个，其中代码类锚点 {len(code_kw)} 个")
    if miss:
        print(f"{C_ERR}❌ {len(miss)} 个锚点在 RULES.md 里找不到：{C_END}")
        for k, bad in miss:
            print(f"   - {k}   {C_DIM}缺: {', '.join(bad)}{C_END}")
    else:
        print(f"{C_OK}✅ 全部代码类锚点命中，索引健康{C_END}")
    return True




def _require_mem():
    if not os.path.isdir(MEM):
        print(f"记忆目录不存在：{MEM}", file=sys.stderr)
        print("先跑 init_psrd.py --dir <目录> 初始化，或设 PSRD_MEM 指向已有记忆目录。", file=sys.stderr)
        sys.exit(3)

def main():
    _require_mem()
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("kw", nargs="*")
    ap.add_argument("--sec", help="取 RULES.md 的 §N 整节")
    ap.add_argument("--layer", default="all")
    ap.add_argument("-n", "--ctx", type=int, default=0, help="上下文行数")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--stat", action="store_true")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--corpus", help="打印某推广语料的索引页：DOC|SKILL")
    ap.add_argument("--todo", action="store_true")
    ap.add_argument("--no-log", action="store_true", help="本次不写 USAGE.jsonl（埋点）")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()

    if a.help or not (a.kw or a.sec or a.stat or a.index or a.corpus or a.todo):
        print(__doc__)
        return 0
    if a.stat:
        stat(); return 0
    if a.index:
        print(read(MEM / "INDEX.md")); return 0
    if a.corpus:
        corpus(a.corpus); return 0
    if a.todo:
        todo(); return 0
    if a.sec:
        get_section(MEM / "RULES.md", a.sec)
        if not a.no_log:
            log_usage({"kind": "sec", "layer": "R", "sec": a.sec})
        return 0
    files = layer_files(a.layer)
    n, secs = grep(files, a.kw, ctx=a.ctx, limit=a.limit)
    if n == 0:
        print(f"{C_WARN}无命中：{' + '.join(a.kw)}{C_END}")
        print(f"{C_DIM}提示：--stat 看有哪些层；--index 看内存层索引{C_END}")
    if not a.no_log:
        log_usage({"kind": "grep", "layer": a.layer.upper(), "kws": a.kw, "hits": n, "sections": secs})
    return 0


if __name__ == "__main__":
    sys.exit(main())
