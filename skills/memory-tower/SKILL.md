---
name: memory-tower
description: 分层长期记忆体系（PSRD = Index/Present/Rules/Secondary + Daily 日志）。当你需要「记住用户的要求与偏好」「回忆之前的约定与规则」「检查记忆健康度」「让 AI 越用越懂你」时使用。核心思想：只有 I+P 两层常驻注入（合计 ≤18K：I≤8K + P≤10K 硬帽），R/S/D 按需读取——体系可持续增长而内存占用不变。用 memgov.py 治理（改前快照 gate + 账本 + 封哈希 + 验封 verify + 优先级裁决），mem_lint.py 体检。
version: 1.0.4
agent_created: true
---

# Memory Tower · 分层记忆塔

> 一句话：**注入的只有 I+P 两层（≤18K），其余 R/S/D 全部按需读（Grep → Read 命中行）**。体系持续增长，内存占用不变。

## 这是什么

把 AI 的长期记忆拆成五层，按「每轮是否需要在场」分层：

| 层 | 文件 | 放什么 | 注入 | 体积帽 |
|---|---|---|---|---|
| I | `INDEX.md` | 目录 + 判据关键词 + 指针 | ✅ 常驻 | ≤8K |
| P | `MEMORY.md` | 每轮都要知道的口径（身份/红线/报数/当前结构）| ✅ 常驻 | ≤10K（平台硬帽）|
| R | `RULES.md` | 纪律/规则/判据 | ⛔ 按需 | ~20K |
| S | `SECONDARY.md` | 技术细节/数据源/脚本清单/历史蒸馏 | ⛔ 按需 | ~300K |
| D | `YYYY-MM-DD.md` | 每天流水 | ⛔ 按需 | 只留最近 5 天 |

**关键纪律**：
- 内容只进 **R/S/D**，**不**进 I/P。I 只放目录行，P 只放「每轮都在场」的最小口径。
- P 层超 10K 尾巴会被平台静默丢弃 → 内容多了就下沉到 R/S。
- 需要一条规则/细节时，`Grep` 命中行再 `Read`，**不读全篇**。

## 初始化

```bash
python3 scripts/init_psrd.py --dir <项目目录>
# 生成 <项目>/.psrd/{INDEX,MEMORY,RULES,SECONDARY}.md + LEDGER.jsonl + INTEGRITY.json
export PSRD_MEM=<项目>/.psrd    # 或让工具自动探测当前目录 .psrd/
```

## 日常使用（什么时候写哪一层）

| 场景 | 写哪里 | 动作 |
|---|---|---|
| 用户说「以后都这样」「记住这个规则」 | R 层 | 追加 §N 判据（写清关键词，便于 Grep）|
| 记住技术细节/数据源/脚本路径 | S 层 | 追加章节 + 更新 INDEX 目录行 |
| 记住今天干了什么 | D 层 | 新建 `YYYY-MM-DD.md` |
| 记住「每轮都要知道」的（身份/红线/报数口径）| P 层 | 精炼写入，超 10K 下沉 |
| 两条记忆打架 | 问 memgov | `memgov.py precedence <关键词>` |

## 改内存层文件必经四步（治理）

```bash
python3 memgov.py gate <文件>                    # 1. 闸门：质检 + 自动留存 <文件>.prev（回滚用）
# …改文件…
python3 memgov.py ledger -m "动作说明" -l R       # 2. 记账（谁/改了什么/为何）
python3 memgov.py seal                            # 3. 封哈希
python3 memgov.py verify                           # 4. 验封（防无账改动）
```

**铁律：改 INDEX/P/R/S 没有账 = 可疑改动**（`mem_lint.py` 会报）。

**改坏了怎么退**：`gate` 会把你放行前的版本存成 `<文件>.prev`，直接 `python3 memgov.py restore <文件>.prev <文件> --yes` 就能回到改前状态（恢复后记得补一条 `ledger` 再 `seal`）。

## 工具速查

| 工具 | 用途 | 常用子命令 |
|---|---|---|
| `memgov.py` | 治理器 | `seal` `verify` `gate` `ledger` `restore` `decay` `stat` `usage` `precedence` |
| `mem_lint.py` | 体检 | 体积帽 / 旧路径 / 断档日报 / 指针悬空 |
| `memfind.py` | 检索 | 跨层按关键词查 |
| `memgraph.py` | 领域关联 | 领域 → 相关条目 |
| `mkindex.py` | 建索引 | 重建 INDEX 目录行 |
| `pub_scan.py` | 对外分发前扫描 | 路径/人名/平台ID/凭证/内部目录名/数据标识，命中即阻断 |
| `init_psrd.py` | 初始化 | `--dir` `--force` |

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `PSRD_MEM` | 当前目录 `.psrd/` | 记忆目录 |
| `PSRD_ACTOR` | `agent` | 记账署名 |
| `PSRD_EXTERNAL` | `{}` | 外部真源路径（JSON）|
| `PSRD_WS` / `PSRD_CLAW` | 空（不检查） | 体检用旧环境残留检查 |

## 优先级（冲突时谁赢，高→低）

见 `references/governance.md`。要点：

1. 用户当场最新明示 > 2. 真源文件/锁件 > 3. 层序 P>R>S>D>归档 > 4. 时效新>旧 > 5. 机制优于结论 > 6. 具体>一般

## 平台适配

本 skill 是**平台中立核心**：SKILL.md（本文）+ `scripts/`（参数化工具）+ `references/`（说明）。
套到具体平台时只改「工具怎么被调用」这一层：
- WorkBuddy/Claude Code：直接 `python3 scripts/memgov.py …`
- DSH bundle：把 `scripts/` 打成 tool，SKILL.md 挂到插件
- 其它：init_psrd.py 生成 `.psrd/` 后，已验证 DSH / WorkBuddy；其它环境需自测
