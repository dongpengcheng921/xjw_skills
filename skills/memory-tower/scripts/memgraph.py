#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memgraph.py — 领域关联图遍历器（"神经网络层"的检索端）

把记忆体系从「分层 + 平面索引」升级为「节点 + 边」的网络：
  节点 = 领域/资产（config_xjw / of2 / cron / db_links / ...）
  边   = 真源 / 产物 / 规则 / 技能 / 定时 / 文档 / 记忆 / 关联域

数据真源：memory/DOMAINS.json（节点与边）。本工具只做遍历与校验，不存数据。

用法
  python scripts/tools/memgraph.py                      # 列出所有节点（一览）
  python scripts/tools/memgraph.py <域>                 # 展开某节点的全部边
  python scripts/tools/memgraph.py <域> --depth 2       # 连带"关联域"再展开一层
  python scripts/tools/memgraph.py --check              # 校验所有路径是否存在（断链检测）
  python scripts/tools/memgraph.py --orphans            # 找"缺真源/缺记忆"的孤立节点
  python scripts/tools/memgraph.py --edges              # 打印边清单
  python scripts/tools/memgraph.py --dot                # 输出 Graphviz dot（可渲染成图）

判据
  * 每个节点**必须有真源**（否则是"印象"不是"资产"）
  * 每个节点**必须有记忆锚**（否则新会话找不到它）
  * `--check` 报断链是**真信号**：真源搬了/删了，DOMAINS.json 该更新
"""
import sys, os, re, json, argparse
from pathlib import Path

MEM = Path(os.environ.get("PSRD_MEM") or (Path.cwd() / ".psrd"))
DATA = MEM / "DOMAINS.json"

C_OK="\033[32m"; C_WARN="\033[33m"; C_ERR="\033[31m"; C_DIM="\033[2m"; C_KEY="\033[1;36m"; C_NODE="\033[1;35m"; C_END="\033[0m"
if not sys.stdout.isatty():
    C_OK=C_WARN=C_ERR=C_DIM=C_KEY=C_NODE=C_END=""

# 路径类字段（参与 --check）
PATH_FIELDS = ("真源", "产物")


def load():
    if not DATA.exists():
        print(f"{C_ERR}找不到 {DATA}{C_END}"); sys.exit(2)
    return json.loads(DATA.read_text(encoding="utf-8"))


def norm(p):
    """只对「绝对路径」做校验（盘符开头）；其余（符号引用/模板/说明文字）跳过。"""
    if not p:
        return None
    p2 = p.split("（")[0].strip()
    if "<" in p2 or ">" in p2:          # 模板占位（<项目>/<id>）⇒ 不校验
        return None
    if not re.match(r"^[A-Za-z]:[\\/]", p2):
        return None                     # 非绝对路径 ⇒ 不适用
    return p2.replace("\\", "/")


def exists(p):
    q = norm(p)
    if q is None:
        return None                     # 不适用
    if "*" in q or "?" in q:            # glob 模式：查父目录有无匹配
        pp = Path(q)
        try:
            return any(pp.parent.glob(pp.name))
        except Exception:
            return None
    try:
        return Path(q).exists()
    except Exception:
        return None


def list_nodes(d):
    print(f"{C_KEY}═══ 领域关联图 · {len(d['nodes'])} 个节点（{d['meta']['版本']}）═══{C_END}")
    for k, v in d["nodes"].items():
        t = v.get("类型", "")
        st = v.get("状态", v.get("版本", ""))
        print(f"  {C_NODE}{k:<14}{C_END} {v.get('名称',''):<34} {C_DIM}[{t}]{C_END} {st}")
    print(f"\n{C_DIM}展开某节点：memgraph.py <域>｜校验断链：--check｜找孤立：--orphans{C_END}")


def show(d, key, depth=1):
    nodes = d["nodes"]
    if key not in nodes:
        cand = [k for k in nodes if key.lower() in k.lower() or key in nodes[k].get("名称", "")]
        print(f"{C_ERR}无此节点：{key}{C_END}")
        if cand:
            print(f"  相近：{', '.join(cand)}")
        return 1
    seen = set()

    def _show(k, lvl):
        if k in seen or k not in nodes:
            return
        seen.add(k)
        v = nodes[k]
        pad = "  " * lvl
        print(f"\n{pad}{C_NODE}◆ {k}{C_END}  {v.get('名称','')}  {C_DIM}[{v.get('类型','')}]{C_END}")
        for f in ("状态", "版本", "在线", "锁定", "库", "工具", "备注"):
            if v.get(f) not in (None, "", [], False):
                val = v[f]
                if isinstance(val, bool):
                    val = "是" if val else "否"
                elif isinstance(val, list):
                    val = " / ".join(map(str, val))
                print(f"{pad}   {C_DIM}{f}{C_END}：{val}")
        for f in ("真源", "产物", "规则", "技能", "定时", "文档", "记忆"):
            if v.get(f):
                print(f"{pad}   {C_KEY}{f}{C_END}")
                for item in v[f]:
                    mark = ""
                    if f in PATH_FIELDS:
                        ok = exists(item)
                        if ok is False: mark = f" {C_ERR}⚠️不存在{C_END}"
                        elif ok is True: mark = f" {C_OK}✓{C_END}"
                    print(f"{pad}     · {item}{mark}")
        if lvl < depth and v.get("关联"):
            for nxt in v["关联"]:
                print(f"{pad}   {C_DIM}──关联──▸ {nxt}{C_END}")
                _show(nxt, lvl + 1)

    _show(key, 0)
    return 0


def check(d):
    print(f"{C_KEY}═══ 断链校验（真源/产物 是否存在）═══{C_END}")
    bad = 0; checked = 0
    for k, v in d["nodes"].items():
        for f in PATH_FIELDS:
            for item in v.get(f, []):
                r = exists(item)
                if r is None:
                    continue
                checked += 1
                if not r:
                    print(f"  {C_ERR}❌ {k}.{f}: {item}{C_END}")
                    bad += 1
    print(f"\n检查 {checked} 条路径，断链 {bad} 条", end="")
    if bad:
        print(f"  {C_WARN}⇒ 更新 DOMAINS.json 或找回文件{C_END}")
    else:
        print(f"  {C_OK}✅{C_END}")
    return 1 if bad else 0


def orphans(d):
    print(f"{C_KEY}═══ 孤立节点检测（缺真源 / 缺记忆 / 无边）═══{C_END}")
    bad = 0
    for k, v in d["nodes"].items():
        probs = []
        if not v.get("真源"):
            probs.append("缺真源")
        if not v.get("记忆"):
            probs.append("缺记忆锚")
        if not v.get("关联"):
            probs.append("无关联边")
        if probs:
            bad += 1
            print(f"  {C_WARN}⚠️ {k}（{v.get('名称','')}）：{'、'.join(probs)}{C_END}")
    if not bad:
        print(f"  {C_OK}✅ 无孤立节点{C_END}")
    return 0


def edges(d):
    print(f"{C_KEY}═══ 边清单（领域 → 关联域）═══{C_END}")
    n = 0
    for k, v in d["nodes"].items():
        for t in v.get("关联", []):
            n += 1
            ok = "" if t in d["nodes"] else f" {C_ERR}⚠️未定义节点{C_END}"
            print(f"  {k} ──▸ {t}{ok}")
    print(f"\n{C_DIM}共 {n} 条边（{len(d['nodes'])} 节点）{C_END}")
    return 0


def dot(d):
    print("digraph domains {")
    print('  rankdir=LR; node [shape=box, style=rounded, fontname="Microsoft YaHei"];')
    for k, v in d["nodes"].items():
        lbl = v.get("名称", k).replace('"', "")
        print(f'  "{k}" [label="{k}\\n{lbl}"];')
    for k, v in d["nodes"].items():
        for t in v.get("关联", []):
            if t in d["nodes"]:
                print(f'  "{k}" -> "{t}";')
    print("}")
    return 0




def _require_mem():
    if not os.path.isdir(MEM):
        print(f"记忆目录不存在：{MEM}", file=sys.stderr)
        print("先跑 init_psrd.py --dir <目录> 初始化，或设 PSRD_MEM 指向已有记忆目录。", file=sys.stderr)
        sys.exit(3)

def main():
    _require_mem()
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("node", nargs="?")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--orphans", action="store_true")
    ap.add_argument("--edges", action="store_true")
    ap.add_argument("--dot", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    a = ap.parse_args()
    d = load()
    if a.help:
        print(__doc__); return 0
    if a.check:   return check(d)
    if a.orphans: return orphans(d)
    if a.edges:   return edges(d)
    if a.dot:     return dot(d)
    if a.node:    return show(d, a.node, a.depth)
    list_nodes(d); return 0


if __name__ == "__main__":
    sys.exit(main())
