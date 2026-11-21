#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memgov.py — 记忆治理器（账本 + 完整性 + 闸门 + 恢复 + 时效）

给「分层加载模型」补上**动态治理**能力。设计原则：不靠"想起来"，靠"一条命令"。

三态存在（与记忆系统同构）：
  策略层（常驻）  = memory/INDEX.md §5「治理层」——每次必读，规定何时记账/过闸/封哈希
  机制层（工具）  = 本文件——不占注入，按需调用
  数据层（硬盘）  = memory/LEDGER.jsonl（append-only 账本）+ memory/INTEGRITY.json（哈希封条）

子命令
  seal                         对内存层封哈希 → 写 INTEGRITY.json
  verify                       校验：完整性（哈希漂移）+ 一致性（跨层/红线/marker）+ 账实相符
  gate <文件> [--strict]        提交前闸门：体积/编码/栅栏/marker/重复行/控制符
  ledger -m "动作" -l R [--reason "…"] [--file X]   追加一条账（自动补前后 sha8）
  ledger --show [N]            看最近 N 条账
  ledger --grep 关键词          查账本
  restore <备份文件> <目标> [--yes]   从备份恢复（默认只打印计划）
  decay [--days N]             时效扫描：过期事实 / 长期未动且含未决项
  stat                         各层体积 + 红线（同 memfind --stat 摘要）

路径
  MEM = /Users/ios/OP/workspace/.workbuddy/memory
"""
import sys, os, re, json, hashlib, argparse, datetime, shutil
from pathlib import Path

MEM = Path(os.environ.get("PSRD_MEM") or (Path.cwd() / ".psrd"))
LEDGER = MEM / "LEDGER.jsonl"
INTEGRITY = MEM / "INTEGRITY.json"
USAGE = MEM / "USAGE.jsonl"      # 由 memfind.py 埋点写入

# 内存层（受治理、封哈希）；R/S 也纳入完整性，但红线不同
# ⚠️ P 的硬帽是 **10,000 字符**：平台每轮只注入 MEMORY.md 前 10,000 字符，超了尾巴静默丢。
# 2026-10-25 前此处写 25000（宽 2.5 倍 ⇒ 假绿），已与 mem_lint.py 同步改为 10000。
CORE = {
    "INDEX": ("INDEX.md", 8000),
    "P":     ("MEMORY.md", 10000),
    "R":     ("RULES.md", 20000),
    "S":     ("SECONDARY.md", 300000),
}
# 外部真源（不属记忆层，但"改动应可知"——纳入封条，检测静默变更）
EXTERNAL = {}
_ext = os.environ.get("PSRD_EXTERNAL")
if _ext:
    try: EXTERNAL = json.loads(_ext)
    except Exception: pass
# 必带 marker
MARKERS = {"S": "DO NOT INJECT", "INDEX": "速查表"}
ACTOR = os.environ.get("PSRD_ACTOR", "agent")

C_OK="\033[32m"; C_WARN="\033[33m"; C_ERR="\033[31m"; C_DIM="\033[2m"; C_KEY="\033[1;36m"; C_END="\033[0m"
if not sys.stdout.isatty():
    C_OK=C_WARN=C_ERR=C_DIM=C_KEY=C_END=""

# 禁止作为"当前口径"引用的字符串（出现即告警；R 的禁引清单本身豁免）
BANNED_CURRENT = ["+378%", "+371.1%", "26.4%", "25.9%", "18.89%", "17.29%"]
# 出现这些词=该数字已被正确标注为"历史/禁用"，不算违规
NEG_MARKERS = ["禁止", "legacy", "作废", "旧", "前视", "不对外", "不得", "勿", "降级",
               "已定案", "历史", "不能引用", "坏值", "脏值"]


def banned_in_p(text, window=40):
    """返回 P 中「疑似被当作当前口径」的禁用数字（已标注历史的不算）。"""
    hits = []
    for b in BANNED_CURRENT:
        start = 0
        while True:
            i = text.find(b, start)
            if i < 0:
                break
            ctx = text[max(0, i - window): i + len(b) + window]
            if not any(m in ctx for m in NEG_MARKERS):
                hits.append(b)
                break
            start = i + len(b)
    return hits


def read(p):
    try: return Path(p).read_text(encoding="utf-8")
    except Exception: return ""


def sha(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except Exception:
        return ""


def sha8(p):
    s = sha(p)
    return s[:8] if s else "—"


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- seal / verify ----------------

def load_integrity():
    if INTEGRITY.exists():
        try: return json.loads(INTEGRITY.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}


def save_integrity(d):
    INTEGRITY.write_text(json.dumps(d, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def cmd_seal(a):
    d = load_integrity()
    files = dict(d.get("files", {}))
    for k, (fn, _) in CORE.items():
        p = MEM / fn
        if not p.exists():
            continue
        s = read(p)
        files[fn] = {"sha256": sha(p), "chars": len(s), "bytes": len(s.encode("utf-8")),
                     "sealed_at": now()}
    d["files"] = files
    # 外部真源（单独分区）
    ext = {}
    for tag, path in EXTERNAL.items():
        p = Path(path)
        if p.exists():
            s = read(p)
            ext[p.name] = {"path": path.replace("\\", "/"), "sha256": sha(p),
                           "chars": len(s), "sealed_at": now()}
    d["external"] = ext
    d["last_seal"] = now()
    d["last_seal_sha"] = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:12]
    save_integrity(d)
    print(f"{C_OK}✅ 已封哈希 {len(files)} 个内存层 + {len(ext)} 个外部真源 → INTEGRITY.json{C_END}")
    for fn, v in sorted(files.items()):
        print(f"   [内存] {fn:<16} {v['sha256'][:12]}  {v['chars']:>9,} 字符")
    for fn, v in sorted(ext.items()):
        print(f"   {C_DIM}[外部] {fn:<16} {v['sha256'][:12]}  {v['chars']:>9,} 字符{C_END}")
    return 0


def _ledger_entries():
    if not LEDGER.exists():
        return []
    out = []
    for ln in LEDGER.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try: out.append(json.loads(ln))
            except Exception: pass
    return out


def cmd_verify(a):
    d = load_integrity()
    files = d.get("files", {})
    entries = _ledger_entries()
    problems = 0
    print(f"{C_KEY}═══ 记忆治理校验 ═══{C_END}")
    print(f"{C_DIM}封条时间：{d.get('last_seal','—')}｜账本 {len(entries)} 条{C_END}\n")

    # 1) 完整性 + 账实相符
    print(f"{C_KEY}[1] 完整性 / 账实相符{C_END}")
    if not files:
        print(f"  {C_WARN}⚠️ 无封条（先跑 seal）{C_END}")
    for k, (fn, limit) in CORE.items():
        p = MEM / fn
        if not p.exists():
            print(f"  {C_ERR}❌ 丢失：{fn}{C_END}"); problems += 1; continue
        cur = sha(p)
        rec = files.get(fn)
        if not rec:
            print(f"  {C_WARN}⚠️ 未封条（新增？）：{fn}{C_END}"); continue
        if cur == rec["sha256"]:
            continue
        # 变了：查账本里封条之后有没有该文件的账
        since = [e for e in entries
                 if e.get("file") == fn and e.get("ts", "") >= d.get("last_seal", "")]
        if since:
            print(f"  {C_OK}✅ 已改动且有账：{fn}{C_END}  {C_DIM}({since[-1].get('summary','')[:40]}){C_END}")
        else:
            print(f"  {C_ERR}❌ 改动但【无账】= 可疑：{fn}{C_END}  {C_DIM}封条 {rec['sha256'][:8]} → 现 {cur[:8]}{C_END}")
            problems += 1
    # 丢失/新增
    for fn in files:
        if not (MEM / fn).exists():
            print(f"  {C_ERR}❌ 封条有但文件丢失：{fn}{C_END}"); problems += 1

    # 2) 红线
    print(f"\n{C_KEY}[2] 体积红线{C_END}")
    for k, (fn, limit) in CORE.items():
        p = MEM / fn
        if not p.exists(): continue
        n = len(read(p))
        if n > limit:
            print(f"  {C_ERR}❌ {fn} {n:,} > {limit:,}{C_END}"); problems += 1
        else:
            print(f"  {C_OK}✅ {fn} {n:,} / {limit:,}{C_END}")

    # 3) marker
    print(f"\n{C_KEY}[3] 必带 marker{C_END}")
    for k, mk in MARKERS.items():
        fn = CORE[k][0]; p = MEM / fn
        if not p.exists(): continue
        if mk in read(p):
            print(f"  {C_OK}✅ {fn} 含「{mk}」{C_END}")
        else:
            print(f"  {C_ERR}❌ {fn} 缺「{mk}」{C_END}"); problems += 1

    # 4) 禁止口径出现在 P（当前口径层）
    print(f"\n{C_KEY}[4] 禁止口径未混入 P{C_END}")
    pm = read(MEM / "MEMORY.md")
    hit = banned_in_p(pm)
    if hit:
        print(f"  {C_ERR}❌ P 含禁止口径（且非历史标注语境）：{hit}{C_END}"); problems += 1
    else:
        print(f"  {C_OK}✅ P 未见禁止口径混用{C_END}")

    # 5) 外部真源（改动应可知）
    print(f"\n{C_KEY}[5] 外部真源变更检测{C_END}")
    ext = d.get("external", {})
    if not ext:
        print(f"  {C_DIM}（无外部真源封条；跑 seal 生成）{C_END}")
    for fn, rec in sorted(ext.items()):
        p = Path(rec["path"])
        if not p.exists():
            print(f"  {C_ERR}❌ 外部真源丢失：{fn}{C_END}"); problems += 1; continue
        cur = sha(p)
        if cur == rec["sha256"]:
            print(f"  {C_OK}✅ 未变：{fn}{C_END}")
        else:
            since = [e for e in entries if e.get("file") == fn and e.get("ts", "") >= d.get("last_seal", "")]
            if since:
                print(f"  {C_OK}✅ 已变且有账：{fn}{C_END}")
            else:
                print(f"  {C_WARN}⚠️ 已变、无账：{fn}  {C_DIM}{rec['sha256'][:8]} → {cur[:8]}"
                      f"（确认是否预期；预期则记账再 seal）{C_END}")

    print()
    if problems:
        print(f"{C_ERR}✗ {problems} 项待处理{C_END}")
    else:
        print(f"{C_OK}✓ 全部通过（{len(files)} 封条 / {len(entries)} 账）{C_END}")
    return 1 if problems else 0


# ---------------- gate ----------------

def cmd_gate(a):
    p = Path(a.file)
    if not p.exists():
        p = MEM / p  # 只给文件名时自动补全 MEM 前缀
    if not p.exists():
        print(f"{C_ERR}文件不存在：{p}{C_END}"); return 2
    text = read(p)
    name = p.name
    issues, warns = [], []

    # 红线
    for k, (fn, limit) in CORE.items():
        if fn == name and len(text) > limit:
            issues.append(f"体积 {len(text):,} > 红线 {limit:,}")

    # 编码
    if "\ufffd" in text:
        issues.append("含 U+FFFD 替换符（编码损坏）")

    # 代码栅栏平衡（只数"行首"的 ```，避免行内 ``` 误判）
    fences = sum(1 for ln in text.splitlines() if ln.lstrip().startswith("```"))
    if fences % 2:
        issues.append(f"``` 代码栅栏未闭合（行首栅栏 {fences} 个 = 奇数）")

    # marker
    for k, mk in MARKERS.items():
        if CORE[k][0] == name and mk not in text:
            warns.append(f"缺必带 marker「{mk}」")

    # 重复相邻行
    lines = text.splitlines()
    dup = sum(1 for i in range(1, len(lines)) if lines[i].strip() and lines[i] == lines[i-1])
    if dup:
        warns.append(f"{dup} 处相邻重复行（合并候选）")

    # 控制符
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        issues.append("含控制字符")

    # 禁止口径（仅 P）
    if name == "MEMORY.md":
        h = banned_in_p(text)
        if h:
            warns.append(f"疑似禁止口径：{h}（确认非历史标注语境）")

    print(f"{C_KEY}═══ 闸门：{name}（{len(text):,} 字符）═══{C_END}")
    for i in issues: print(f"  {C_ERR}❌ {i}{C_END}")
    for w in warns:  print(f"  {C_WARN}⚠️ {w}{C_END}")
    if not issues and not warns:
        print(f"  {C_OK}✅ 通过{C_END}")
    if issues:
        print(f"\n{C_ERR}✗ 拦截（{len(issues)} 严重）{C_END}"); return 1
    print(f"\n{C_OK}✓ 放行（{len(warns)} 提示）{C_END}" if warns else f"\n{C_OK}✓ 放行{C_END}")
    return 0


# ---------------- ledger ----------------

def cmd_ledger(a):
    if a.show:
        entries = _ledger_entries()[-a.show:]
        print(f"{C_KEY}═══ 账本（最近 {len(entries)} 条）═══{C_END}")
        for e in entries:
            print(f"  {C_DIM}{e.get('ts','')}{C_END} [{e.get('layer','?')}] {e.get('summary','')}"
                  f"  {C_DIM}{e.get('prev_sha8','—')}→{e.get('new_sha8','—')}{C_END}")
            if e.get("reason"):
                print(f"       {C_DIM}原因：{e['reason']}{C_END}")
        return 0
    if a.grep:
        entries = [e for e in _ledger_entries()
                   if a.grep.lower() in json.dumps(e, ensure_ascii=False).lower()]
        print(f"{C_KEY}═══ 账本命中「{a.grep}」：{len(entries)} 条 ═══{C_END}")
        for e in entries:
            print(f"  {e.get('ts','')} [{e.get('layer','?')}] {e.get('file','')} {e.get('summary','')}")
            if e.get("prev_sha8"): print(f"       {C_DIM}{e['prev_sha8']}→{e.get('new_sha8','')}{C_END}")
            if e.get("reason"): print(f"       {C_DIM}原因：{e['reason']}{C_END}")
        return 0
    # add
    if not a.message:
        print(f"{C_ERR}需 -m \"动作摘要\"{C_END}"); return 2
    layer = a.layer or "?"
    fn = None
    if a.file:
        fn = Path(a.file).name
    elif layer.upper() in CORE:
        fn = CORE[layer.upper()][0]
    prev = "—"; new = "—"
    if fn and (MEM / fn).exists():
        new = sha8(MEM / fn)
        d = load_integrity()
        rec = d.get("files", {}).get(fn)
        if rec: prev = rec["sha256"][:8]
    entry = {"ts": now(), "layer": layer, "file": fn or "", "action": a.action or "edit",
             "summary": a.message, "reason": a.reason or "",
             "prev_sha8": prev, "new_sha8": new, "actor": ACTOR}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"{C_OK}✅ 已记账 [{layer}] {a.message}{C_END}  {C_DIM}{prev}→{new}{C_END}")
    return 0


# ---------------- restore ----------------

def cmd_restore(a):
    src, dst = Path(a.backup), Path(a.target)
    if not src.exists():
        print(f"{C_ERR}备份不存在：{src}{C_END}"); return 2
    if not dst.exists():
        print(f"{C_WARN}目标不存在：{dst}（将新建）{C_END}")
    print(f"{C_KEY}═══ 恢复计划 ═══{C_END}")
    print(f"  来源：{src}  ({src.stat().st_size:,} B, {read(src).count(chr(10))+1} 行)")
    if dst.exists():
        print(f"  目标：{dst}  ({dst.stat().st_size:,} B, {read(dst).count(chr(10))+1} 行)")
        print(f"  {C_WARN}将覆盖目标；旧目标自动存为 {dst.name}.before_restore{C_END}")
    if not a.yes:
        print(f"\n{C_DIM}（预览模式；加 --yes 执行）{C_END}")
        return 0
    if dst.exists():
        shutil.copy2(dst, dst.with_suffix(dst.suffix + ".before_restore"))
    shutil.copy2(src, dst)
    print(f"\n{C_OK}✅ 已恢复 {dst}{C_END}")
    print(f"{C_DIM}提示：恢复后跑 `memgov.py ledger -m \"从 X 恢复\"` 记账，再 `seal`{C_END}")
    return 0


# ---------------- decay ----------------

def cmd_decay(a):
    print(f"{C_KEY}═══ 时效扫描（阈值 {a.days} 天）═══{C_END}")
    today = datetime.date.today()
    files = sorted(MEM.glob("*.md")) + sorted(MEM.glob("_archive/**/*.md"))
    stale, undecided = [], []
    for p in files:
        s = read(p)
        # "数据截至 / 截至 YYYY-MM-DD" 且过期
        for m in re.finditer(r"(?:数据)?截至\s*(\d{4})-(\d{2})-(\d{2})", s):
            try:
                d = datetime.date(*map(int, m.groups()))
            except Exception:
                continue
            age = (today - d).days
            if age > a.days:
                stale.append((p.name, m.group(0), age))
        if ("待裁定" in s or "未决" in s or "待用户" in s):
            mt = datetime.date.fromtimestamp(p.stat().st_mtime)
            age = (today - mt).days
            if age > a.days:
                undecided.append((p.name, age))
    print(f"\n{C_KEY}[1] 过期事实（含「截至」且超期）{C_END}")
    if stale:
        for n, txt, age in stale[:30]:
            print(f"  {C_WARN}⚠️ {n}: {txt}（{age} 天前）{C_END}")
    else:
        print(f"  {C_OK}✅ 无{C_END}")
    print(f"\n{C_KEY}[2] 长期未动且含未决项{C_END}")
    if undecided:
        for n, age in undecided[:30]:
            print(f"  {C_WARN}⚠️ {n}: 未动 {age} 天{C_END}")
    else:
        print(f"  {C_OK}✅ 无{C_END}")
    return 0


def cmd_stat(a):
    print(f"{C_KEY}═══ 治理对象体积 ═══{C_END}")
    for k, (fn, limit) in CORE.items():
        p = MEM / fn
        if not p.exists(): continue
        n = len(read(p))
        tag = f"{C_OK}✅ <{limit//1000}K{C_END}" if n <= limit else f"{C_ERR}❌ 超{n-limit}{C_END}"
        print(f"  {k:<6}{fn:<16}{n:>9,} 字符  {tag}")
    print(f"  {C_DIM}账本 {len(_ledger_entries())} 条｜封条 {len(load_integrity().get('files',{}))} 个{C_END}")
    return 0


# ---------------- precedence（冲突解析优先级） ----------------

# 锚定最优（2026-10-10 立）：高 → 低
PRECEDENCE = [
    ("1", "用户当场最新明示", "用户一手 > 一切；⚠️ 未落 P 则下轮失效，当场裁定须同轮回写"),
    ("2", "真源文件 / 锁件", "真源 > 记忆转述（config_xjw / 锁件 / SKILL.md `version:` / 实盘台账）"),
    ("3", "层序 P>R>S>D>归档", "同事实跨层冲突时，高层胜（P=当前口径是唯一真值）"),
    ("4", "时效 新>旧", "同层内新值胜；但**已被显式作废的旧值不得复活**（P 不留旧值）"),
    ("5", "机制 优于 结论", "有实测/机制证据的 > 口头结论（防「结论对+论证错」）"),
    ("6", "具体 > 一般", "特殊条款/专项裁定 > 通则"),
]


def cmd_precedence(a):
    print(f"{C_KEY}═══ 解析优先级（冲突时谁赢 · 高→低）═══{C_END}")
    for n, name, note in PRECEDENCE:
        print(f"  {C_OK}{n}. {name}{C_END}")
        print(f"     {C_DIM}{note}{C_END}")
    if not a.keyword:
        print(f"\n{C_DIM}跨层查同一事实：memgov.py precedence --scan <关键词>{C_END}")
        return 0
    # scan：把各层命中按优先级排出来，便于人工判冲突
    kws = [a.keyword] + (a.scan or [])
    order = [("P", "MEMORY.md", "3"), ("R", "RULES.md", "3"), ("S", "SECONDARY.md", "3"),
             ("INDEX", "INDEX.md", "3")]
    print(f"\n{C_KEY}── 跨层命中「{' + '.join(kws)}」──{C_END}")
    total = 0
    for tag, fn, _ in order:
        p = MEM / fn
        if not p.exists():
            continue
        lines = read(p).splitlines()
        hits = [ln.strip() for ln in lines if all(k.lower() in ln.lower() for k in kws)]
        if hits:
            print(f"\n  {C_KEY}[{tag}] {fn}{C_END}  {len(hits)} 命中")
            for h in hits[:8]:
                print(f"    · {h[:150]}")
            total += len(hits)
    # 也扫当日日志
    for p in sorted(MEM.glob("20[0-9][0-9]-*.md"))[-2:]:
        lines = read(p).splitlines()
        hits = [ln.strip() for ln in lines if all(k.lower() in ln.lower() for k in kws)]
        if hits:
            print(f"\n  {C_KEY}[D] {p.name}{C_END}  {len(hits)} 命中")
            for h in hits[:5]:
                print(f"    · {h[:150]}")
    if total == 0:
        print(f"  {C_WARN}无命中{C_END}")
    print(f"\n{C_DIM}判读：若高层与低层给出不同值 ⇒ 以高层为准，且低层应被改齐或标注作废。{C_END}")
    return 0


# ---------------- usage（可观测） ----------------

def _usage_entries():
    if not USAGE.exists():
        return []
    out = []
    for ln in USAGE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try: out.append(json.loads(ln))
            except Exception: pass
    return out


def _headings(name):
    """列出某文件所有 ## 标题。"""
    p = MEM / name
    if not p.exists(): return []
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+)$", read(p), re.M)]


def cmd_usage(a):
    entries = _usage_entries()
    print(f"{C_KEY}═══ 可观测：检索热度 / 冷门条目 ═══{C_END}")
    if not entries:
        print(f"  {C_WARN}⚠️ 无埋点数据（USAGE.jsonl 为空）——先跑几次 memfind 检索{C_END}")
        return 0
    print(f"{C_DIM}埋点 {len(entries)} 条｜{entries[0].get('ts','')} ~ {entries[-1].get('ts','')}"
          f"｜⚠️ 仅统计「经工具检索」，直接 Read 未埋点{C_END}\n")

    # [1] 按层
    from collections import Counter
    by_layer = Counter()
    for e in entries:
        if e.get("kind") == "sec":
            by_layer[e.get("layer", "R")] += 1
        else:
            by_layer[e.get("layer", "?")] += 1
    print(f"{C_KEY}[1] 检索量（按层）{C_END}")
    for k, v in by_layer.most_common():
        print(f"    {k:<8}{v:>5} 次")
    zc = sum(1 for e in entries if e.get("kind") == "grep" and e.get("hits", 0) == 0)
    print(f"    {C_DIM}其中零命中 {zc} 次（{zc*100//max(len(entries),1)}% —— 高则说明 INDEX 速查表需补关键词）{C_END}")

    # [2] 热关键词
    kwc = Counter()
    for e in entries:
        for k in e.get("kws", []):
            kwc[k] += 1
    print(f"\n{C_KEY}[2] 热关键词 Top 10{C_END}")
    for k, v in kwc.most_common(10):
        print(f"    {C_OK}{v:>4}×{C_END}  {k}")
    if not kwc:
        print(f"    {C_DIM}（无 grep 检索）{C_END}")

    # [3] 热节
    secc = Counter()
    for e in entries:
        for s in e.get("sections", []):
            secc[s] += 1;
        if e.get("kind") == "sec":
            secc[f"RULES.md::(§{e.get('sec')})"] += 1
    print(f"\n{C_KEY}[3] 热节 Top 10{C_END}")
    for s, v in secc.most_common(10):
        print(f"    {C_OK}{v:>4}×{C_END}  {s}")

    # [4] 冷节（从未被检索到）
    print(f"\n{C_KEY}[4] 冷节（从未被检索到 ⇒ 归档/复核候选）{C_END}")
    for fn, label in (("RULES.md", "R"), ("SECONDARY.md", "S")):
        heads = _headings(fn)
        hit_titles = set()
        for s in secc:
            if "::" in s:
                f, t = s.split("::", 1)
                if f == fn:
                    hit_titles.add(t.lstrip("(§").rstrip(")"))
        cold = [h for h in heads if h not in hit_titles
                and not any(h in ht or ht in h for ht in hit_titles if ht)]
        print(f"    {C_DIM}── {label} {fn}：{len(heads)} 节，{len(cold)} 节从未命中 ──{C_END}")
        for h in cold[:a.limit]:
            print(f"      {C_WARN}•{C_END} {h[:70]}")
        if len(cold) > a.limit:
            print(f"      {C_DIM}… 共 {len(cold)} 节（--limit 调）{C_END}")
    print(f"\n{C_DIM}用法：冷节多在 S（历史/蒸馏型，本就少读）属正常；"
          f"若 R 出现冷节 ⇒ 检查该纪律是否已失效或该并档。{C_END}")
    return 0




def _require_mem():
    if not os.path.isdir(MEM):
        print(f"记忆目录不存在：{MEM}", file=sys.stderr)
        print("先跑 init_psrd.py --dir <目录> 初始化，或设 PSRD_MEM 指向已有记忆目录。", file=sys.stderr)
        sys.exit(3)

def main():
    ap = argparse.ArgumentParser(description="记忆治理器")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("seal")
    sub.add_parser("verify")
    sub.add_parser("stat")
    g = sub.add_parser("gate"); g.add_argument("file"); g.add_argument("--strict", action="store_true")
    l = sub.add_parser("ledger")
    l.add_argument("-m", "--message"); l.add_argument("-l", "--layer")
    l.add_argument("--reason"); l.add_argument("--file"); l.add_argument("--action")
    l.add_argument("--show", type=int, nargs="?", const=20); l.add_argument("--grep")
    r = sub.add_parser("restore"); r.add_argument("backup"); r.add_argument("target"); r.add_argument("--yes", action="store_true")
    dc = sub.add_parser("decay"); dc.add_argument("--days", type=int, default=30)
    us = sub.add_parser("usage"); us.add_argument("--limit", type=int, default=25)
    pc = sub.add_parser("precedence"); pc.add_argument("keyword", nargs="?"); pc.add_argument("--scan", nargs="*")

    a = ap.parse_args()
    if not a.cmd:
        print(__doc__); return 0
    _require_mem()
    return {"seal": cmd_seal, "verify": cmd_verify, "gate": cmd_gate, "ledger": cmd_ledger,
            "restore": cmd_restore, "decay": cmd_decay, "stat": cmd_stat,
            "usage": cmd_usage, "precedence": cmd_precedence}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main() or 0)
