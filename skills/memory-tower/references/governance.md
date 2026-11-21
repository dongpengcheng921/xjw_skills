# PSRD 治理细则（governance）

## 1 治理四步（改内存层文件必经）

```
gate → 改 → ledger → seal → verify
```

| 步 | 命令 | 作用 |
|---|---|---|
| 快照 | `memgov.py gate <文件>` | 记 prev sha8，可追溯改前状态 |
| 改 | （正常编辑文件） | 就地改，别换文件名 |
| 记账 | `memgov.py ledger -m "动作" -l R` | 写 LEDGER.jsonl：时间/actor/文件/层级/动作/前后 sha8 |
| 封哈希 | `memgov.py seal` | 重算并写 INTEGRITY.json，锁定当前状态 |
| 验封 | `memgov.py verify` | 比对 sha，报告「无账改动」（改动没走 ledger）|

**铁律：改 INDEX/P/R/S 没有账 = 可疑改动**（`mem_lint.py` 会报 🔴）。

## 2 体积阈值 + 超限处理

| 层 | 帽 | 超限时 |
|---|---|---|
| I INDEX.md | 8K | 内容下沉，只留目录行 |
| P MEMORY.md | 10K（平台硬帽）| 尾巴被静默丢弃 → 必须下沉 R/S |
| R RULES.md | 20K | 已否决/过期条目移 `_archive/`，本体留指针 |
| S SECONDARY.md | 300K | 原样搬到 `_archive/SECONDARY_*.md`，本体留指针 + 目录行 |
| D YYYY-MM-DD.md | — | 只留最近 5 天，旧的删/归档 |

## 3 优先级（冲突裁决，高→低）

`memgov.py precedence <关键词>` 输出命中条目的裁决顺序。

1. **用户当场最新明示** —— 未落 P 则下轮失效
2. **真源文件 / 锁件** —— config / SKILL.md version / 台账
3. **层序** —— P > R > S > D > 归档
4. **时效** —— 新 > 旧（已被显式作废的旧值不得复活）
5. **机制 优于 结论** —— 防「结论对 + 论证错」
6. **具体 > 一般**

## 4 归档（不删除，只下沉）

- 原则：**原样搬迁**（零改动），本体留指针 + 目录行。
- 归档前三判据：①无活跃引用 ②不在 P 层口径 ③不是唯一真源。
- 落点：`_archive/SECONDARY_distilled_<日期>.md` 之类。

## 5 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `PSRD_MEM` | 金晓九默认目录 | 记忆目录（`.psrd/`）|
| `PSRD_ACTOR` | `agent` | 记账署名 |
| `PSRD_EXTERNAL` | `{}` | 外部真源路径（JSON 字符串）|
| `PSRD_WS` / `PSRD_CLAW` | 金晓九默认 | mem_lint 旧环境残留检查 |
