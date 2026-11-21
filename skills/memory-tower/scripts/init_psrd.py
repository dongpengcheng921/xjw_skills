#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_psrd.py — 初始化 PSRD 记忆体系（P/R/S/D 分层 + 治理）

在一个项目目录下生成 `.psrd/` 记忆目录（INDEX/P/R/S + 空账本/封条），
让 memgov.py / mem_lint.py / memfind.py 开箱即用。

用法：
  python3 init_psrd.py                 # 在当前目录初始化 .psrd/
  python3 init_psrd.py --dir <路径>    # 在指定目录初始化
  python3 init_psrd.py --force         # 覆盖已存在的文件（默认跳过已存在）

之后：
  export PSRD_MEM=<项目>/.psrd        # 或让工具自动探测 .psrd/
  python3 memgov.py seal              # 首次封哈希
"""
import argparse
import json
import sys
from pathlib import Path

# ── 模板（平台中立骨架，不含任何具体项目内容）────────────────
TEMPLATES = {
    "INDEX.md": """# INDEX.md — 记忆索引层（常驻 · ≤8,000 字符）

> 本文件只放「目录 + 判据关键词 + 指针」，真内容在各层本体。
> ⛔ 禁止把内容搬进本文件——只加目录行。超 8K 说明又混入了内容，应下沉。

## 0 三层加载模型

| 层 | 文件 | 注入 | 体积 |
|---|---|---|---|
| I | INDEX.md | ✅ 常驻 | ≤8K |
| P | MEMORY.md | ✅ 常驻 | ≤10K（平台硬帽）|
| R | RULES.md | ⛔ 按需 | ~20K |
| S | SECONDARY.md | ⛔ 按需 | ~300K |
| D | YYYY-MM-DD.md | ⛔ 按需 | 只留最近 5 天 |

**核心判据**：注入 = P 层前 10K 字符；其余（R/S/D）全部按需（Grep → Read 命中行）。
⇒ 体系可无限增长（新规则进 R、新细节进 S、新流水进 D），内存占用不变。

## 1 速查表（要做什么 → 读哪里）

| 我要… | 一步操作 |
|---|---|
| 改内存层文件（INDEX/P/R/S） | §5 治理层：`gate` → 改 → `ledger` → `seal` |
| 两条记忆打架 | §6 优先级；或 `memgov.py precedence <关键词>` |
| 找历史细节 | S 目录 → Read |
| 找某天流水 | `D/YYYY-MM-DD.md` |
| 体检 | `python3 mem_lint.py` |

## 5 治理层（改内存层文件必经）

`memgov.py gate <文件>` → 改 → `memgov.py ledger -m "动作" -l R` → `memgov.py seal`

## 6 优先级（冲突时谁赢 · 高→低，`memgov.py precedence`）

1. 用户当场最新明示（未落 P 则下轮失效）
2. 真源文件 / 锁件（config / SKILL.md version / 台账）
3. 层序 P > R > S > D > 归档
4. 时效 新 > 旧（已被显式作废的旧值不得复活）
5. 机制 优于 结论（防「结论对+论证错」）
6. 具体 > 一般
""",
    "MEMORY.md": """# MEMORY.md — 当前语境（P 层 · 常驻 · ≤10,000 字符）

> 每轮对话都注入的前 10K 字符，是「当前口径」唯一真值。只放每轮都在场的关键信息。
> ⛔ 超 10K 尾巴会被平台静默丢弃——内容多了就下沉到 R/S。

## 身份
（agent 是谁、服务谁、定位）

## 红线
（绝不做的事）

## 报数口径
（关键数字 / 版本 / 地址的真源，只此一处）

## 当前结构
（项目当前状态 / 目录 / 关键路径）
""",
    "RULES.md": """# RULES.md — 纪律判据（R 层 · 按需 · ~20K）

> 用法：`Grep RULES.md "<关键词>"` 再 Read 命中行。**不必读全篇。**

## §1 工程纪律
- 改生产三件套：备份 + 就地改 + 自证
- 先 dry-run，再 UPSERT

## §2 目录落点
- 白名单 / 禁野路径

（新纪律按 §N 追加；判据写清，便于 Grep）
""",
    "SECONDARY.md": """# SECONDARY.md — 技术细节（S 层 · 按需 · ~300K）

DO NOT INJECT

> 只放技术细节 / 数据源 / 脚本清单 / 历史蒸馏。先看本文件目录，再 Read 命中章节。
> 归档：原样搬到 `_archive/`，本体留指针 + 目录行。
""",
    "DOMAINS.json": json.dumps({
        "meta": {"版本": "1.0",
                 "说明": "领域关联图：节点(领域/资产) + 边(关联域)。用 memgraph.py 遍历、--check 校验断链、--orphans 找孤立节点。"},
        "nodes": {},
    }, ensure_ascii=False, indent=2) + "\n",
}


def main():
    ap = argparse.ArgumentParser(description="初始化 PSRD 记忆体系")
    ap.add_argument("--dir", default=".", help="目标项目目录（默认当前目录）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    a = ap.parse_args()

    base = Path(a.dir).resolve()
    mem = base / ".psrd"
    mem.mkdir(parents=True, exist_ok=True)

    created, skipped = [], []
    for fn, body in TEMPLATES.items():
        p = mem / fn
        if p.exists() and not a.force:
            skipped.append(fn)
            continue
        p.write_text(body, encoding="utf-8")
        created.append(fn)

    # 空账本 + 空封条（不存在才建，不覆盖已有）
    ledger = mem / "LEDGER.jsonl"
    if not ledger.exists():
        ledger.write_text("", encoding="utf-8")
        created.append("LEDGER.jsonl")
    integrity = mem / "INTEGRITY.json"
    if not integrity.exists():
        integrity.write_text(json.dumps({"files": {}, "external": {}, "last_seal": ""},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
        created.append("INTEGRITY.json")

    print(f"PSRD 记忆体系 → {mem}/")
    for fn in created:
        print(f"  ✅ 新建 {fn}")
    for fn in skipped:
        print(f"  ⏭  已存在，跳过 {fn}（--force 覆盖）")
    print()
    print("接下来：")
    print(f"  export PSRD_MEM={mem}")
    print("  python3 memgov.py seal        # 首次封哈希")
    print("  python3 mem_lint.py           # 体检")
    return 0


if __name__ == "__main__":
    sys.exit(main())
