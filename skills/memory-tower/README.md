# Memory Tower · 分层记忆塔

> 让 AI 越用越懂你，而内存占用永远不变。

一个**分层长期记忆体系** skill：把 AI 的记忆拆成一座五层塔，只有塔尖常驻注入（≤18K 字符），塔身按需读取——**知识无限积累，注入体积恒定**。配套治理工具（封哈希 + 账本 + 体检），让记忆「可审计、可回滚、不腐坏」。

---

## 1. 解决什么问题

AI 长期记忆的经典困境：

- ❌ **单文件记所有**：每轮全量注入 → 要么爆上下文，要么精简到丢信息。
- ❌ **纯靠自动 summary**：流水账，关键规则记不住，反复让你重说。
- ❌ **记忆改了没账**：谁改的、改了什么、为什么，无从查证，越记越乱。

Memory Tower 的解：**按「每轮是否需要在场」分层**，常驻的只有塔尖，其余按需读。

---

## 2. 五层塔

```
        🏔 塔尖（观景台）—— I 索引 + P 口径
              ✅ 每轮常驻注入，≤ 18K 字符
        ─────────────────────────────
        🏢 塔身（楼层）—— R 规则 + S 技术细节
              ⛔ 用到哪层爬哪层（Grep → Read 命中行）
        ─────────────────────────────
        🏚 塔基（档案库）—— D 日志 + 归档
              ⛔ 流水往下沉，旧的归档
```

| 层 | 文件 | 放什么 | 注入 | 体积帽 |
|---|---|---|---|---|
| I | `INDEX.md` | 目录 + 关键词 + 指针 | ✅ 常驻 | ≤8K |
| P | `MEMORY.md` | 每轮都要知道的口径（身份/红线/报数）| ✅ 常驻 | ≤10K（硬帽）|
| R | `RULES.md` | 纪律 / 规则 / 判据 | ⛔ 按需 | ~20K |
| S | `SECONDARY.md` | 技术细节 / 数据源 / 蒸馏 | ⛔ 按需 | ~300K |
| D | `YYYY-MM-DD.md` | 每天流水 | ⛔ 按需 | 留最近 5 天 |

**铁律**：内容只进 R/S/D，不进 I/P。I 只放目录行，P 只放最小口径。P 超 10K 会被平台静默丢尾巴，必须下沉。

---

## 3. 快速开始（3 步）

```bash
# ① 初始化（在项目目录生成 .psrd/ 四层 + 账本 + 封条）
python3 scripts/init_psrd.py --dir <项目目录>
export PSRD_MEM=<项目目录>/.psrd

# ② 记住一条规则（改 R 层，走治理四步）
python3 scripts/memgov.py gate RULES.md        # 快照
# …编辑 RULES.md，追加 §N 判据…
python3 scripts/memgov.py ledger -m "加规则：xxx" -l R   # 记账
python3 scripts/memgov.py seal                 # 封哈希

# ③ 体检（检查体积帽 / 断档 / 无账改动）
python3 scripts/mem_lint.py
```

---

## 4. 五层怎么用（什么时候写哪层）

| 场景 | 写哪里 |
|---|---|
| 用户说「以后都这样」「记住这个规则」 | **R 层**，追加 §N 判据（写清关键词，便于 Grep）|
| 记住技术细节 / 数据源 / 脚本路径 | **S 层**，追加章节 + 更新 I 目录行 |
| 记住今天干了什么 | **D 层**，新建 `YYYY-MM-DD.md` |
| 记住「每轮都要知道」的（身份/红线/报数口径）| **P 层**，精炼写入 |
| 两条记忆打架 | `memgov.py precedence <关键词>` |

---

## 5. 治理四步（改 I/P/R/S 必经）

```
gate → 改 → ledger → seal → verify
```

| 步 | 命令 | 作用 |
|---|---|---|
| 快照 | `memgov.py gate <文件>` | 记改前 sha |
| 改 | 正常编辑 | 就地改 |
| 记账 | `memgov.py ledger -m "动作" -l R` | 写 LEDGER.jsonl |
| 封哈希 | `memgov.py seal` | 锁定状态 |
| 验封 | `memgov.py verify` | 报「无账改动」|

**铁律：改 I/P/R/S 没有账 = 可疑改动**（`mem_lint.py` 会报 🔴）。

---

## 6. 工具清单

| 工具 | 用途 |
|---|---|
| `init_psrd.py` | 初始化（`--dir` / `--force`）|
| `memgov.py` | 治理器（seal / verify / gate / ledger / restore / decay / stat / usage / precedence）|
| `mem_lint.py` | 体检（体积帽 / 断档日报 / 悬空指针 / 无账改动）|
| `memfind.py` | 检索（跨层按关键词查）|
| `memgraph.py` | 领域关联 |
| `mkindex.py` | 重建索引目录行 |

**`mem_lint.py` 退出码**（挂 CI 用）：`0` 全绿 / `1` 有红（🔴 必须修）/ `2` 有黄（⚠️ 建议修）/ `3` 记忆目录不存在。

---

## 7. 配置（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `PSRD_MEM` | 当前目录 `.psrd/` | 记忆目录 |
| `PSRD_ACTOR` | `agent` | 记账署名 |
| `PSRD_EXTERNAL` | `{}` | 外部真源路径（JSON）|
| `PSRD_WS` / `PSRD_CLAW` | 空（不检查） | 体检用旧环境残留检查 |

**接已有记忆树时**：若 INDEX.md 里有 `picker/docs/…`、`skills/…`、`scripts/…` 这类**工作区相对指针**，必须 `export PSRD_WS=<工作区根>`，否则体检会把它们判「索引指针失效」。全新 `init` 出来的体系不含这类指针，不设也行。

---

## 8. 优先级（冲突时谁赢，高→低）

1. 用户当场最新明示
2. 真源文件 / 锁件
3. 层序 P > R > S > D > 归档
4. 时效 新 > 旧
5. 机制 优于 结论
6. 具体 > 一般

---

## 9. 平台安装

**DeepSeek Harness**：复制整个目录到 `~/.dsh/skills/memory-tower/`，DSH 自动发现（无需重启）。

**WorkBuddy / Claude Code**：复制到 `<home>/.workbuddy/skills/memory-tower/`（含 `_skillhub_meta.json`）。

**其它平台**：任何能跑 Python 的 agent —— 运行 `init_psrd.py` 建 `.psrd/`，用 `memgov.py` / `mem_lint.py` 治理即可。

---

## 10. 目录结构

```
memory-tower/
├── SKILL.md                  # AI 核心指令（给 agent 看）
├── README.md                 # 本说明书（给人看）
├── references/
│   ├── governance.md         # 治理细则：阈值 + 优先级 + 归档
│   └── three-tier-model.md   # 为什么分层（O(1) 内存 / O(n) 知识）
└── scripts/                  # 6 个工具（全参数化，无硬编码依赖）
    ├── init_psrd.py
    ├── memgov.py
    ├── mem_lint.py
    ├── memfind.py
    ├── memgraph.py
    └── mkindex.py
```

---

**一句话总结**：塔尖常驻（I+P ≤18K），塔身按需（R/S/D），动塔有账（gate→ledger→seal）。知识无限长，注入永远只有塔尖。
