# 晓九窝的技能库（xjw_skills）

晓九窝的技能库——记忆分层塔、A股数据管线、报表与出图工具等等。

## 当前收录

### memory-tower · 记忆分层塔

分层长期记忆体系与配套工具的源文件。**发布包（.zip）走 Releases，不入库**。

| 目录 | 说明 |
|---|---|
| `skills/memory-tower/` | 五层记忆塔：I 索引 + P 口径常驻注入（合计 ≤18K），R/S/D 按需读取；配 `memgov.py` 治理（gate → 账本 → 封哈希 → verify）与 `mem_lint.py` 体检，`pub_scan.py` 发布前扫内部信息 |

## 安装

把 `skills/<名字>/` 整个目录拷到：

- **WorkBuddy**：`~/.workbuddy/skills/<名字>/`
- **DeepSeek Harness**：`~/.dsh/skills/<名字>/`

或直接导入 `Releases` 里的 zip。

## 约定

- 只放源码（脚本 / SKILL.md / references），**不放** `__pycache__`、`*.bak_*`、构建产物。
- 发布包由源目录打包，打包前必做 `diff -r` 对照，`unzip -t` 只证明压缩没坏。
