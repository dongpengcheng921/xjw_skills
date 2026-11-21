#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mkindex.py — 语料索引生成器（"硬盘"的目录页自动生成器）

把「分层加载模型」推广到任意会慢慢增长的语料目录：
  任何目录（docs / skills / reports / studio）都可以生成一份「索引页」，
  索引页 = 文件名 + 一句话摘要 + 体积 + 关键词 —— 供"内存层"引用，本体按需 Read。

设计原则（与 memory/INDEX.md 一致）
  * 索引页只放"目录 + 摘要 + 指针"，**不放内容**
  * 有手工摘要就用手工的（在文件头 `> 摘要：xxx` 或 `# 标题` 取），否则自动截首段
  * 可重复运行、幂等、不覆盖手工维护的 INDEX（区分 AUTO 区与 MANUAL 区）

用法
  python scripts/tools/mkindex.py <目录>                       # 预览（stdout）
  python scripts/tools/mkindex.py <目录> -o INDEX.md           # 写入
  python scripts/tools/mkindex.py <目录> --glob "*.md"         # 自定义匹配
  python scripts/tools/mkindex.py <目录> --max-summary 120     # 摘要长度

输出分区
  <!-- AUTO:BEGIN --> ... <!-- AUTO:END -->   自动生成区（可覆盖）
  其余内容视作 MANUAL 区，写回时原样保留（可手工补充导读/分类）
"""
import sys, os, re, argparse, datetime
from pathlib import Path

C_KEY = "\033[1;36m"; C_DIM = "\033[2m"; C_END = "\033[0m"
if not sys.stdout.isatty():
    C_KEY = C_DIM = C_END = ""

AUTO_BEGIN = "<!-- AUTO:BEGIN 以下由 mkindex.py 自动生成，勿手改 -->"
AUTO_END = "<!-- AUTO:END -->"


def first_heading(text):
    """取第一个 # 标题。"""
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def explicit_summary(text):
    """找 `> 摘要：xxx` / `> **一句话**：xxx` / `摘要：xxx` 形式的手工摘要。"""
    for pat in (r"^>\s*(?:\*\*)?摘要(?:\*\*)?[：:]\s*(.+)$",
                r"^>\s*(?:\*\*)?一句话(?:\*\*)?[：:]\s*(.+)$",
                r"^摘要[：:]\s*(.+)$"):
        m = re.search(pat, text, re.M)
        if m:
            return m.group(1).strip()
    return ""


def auto_summary(text, limit=100):
    """跳过标题/引用块/元数据行，取第一个正文段作为摘要。"""
    lines = text.splitlines()
    buf = []
    started = False
    for ln in lines:
        s = ln.strip()
        if not started:
            if s.startswith("#") or s.startswith(">") or s.startswith("---") or not s:
                continue
            started = True
        if started:
            if s.startswith("#") or s.startswith("|") or s.startswith(">"):
                break
            buf.append(s)
            if len(" ".join(buf)) >= limit:
                break
    s = re.sub(r"[*`\[\]]", "", " ".join(buf))
    # 去掉常见元数据尾巴（生成：… ｜ 脚本：… ｜ 日期：…）
    s = re.sub(r"[｜|]\s*(生成|脚本|日期|来源|登记|更新)[：:].*$", "", s)
    s = re.sub(r"(生成|脚本|日期|来源|登记|更新)[：:]\s*\S+\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip("｜| ")
    return s[:limit]


def keywords(text, k=6):
    """粗提英文标识符/反引号内容作为关键词（无依赖）。"""
    toks = re.findall(r"`([^`\n]{2,30})`", text)
    toks += re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{3,20})\b", text)
    stop = {"html", "http", "https", "this", "that", "with", "from", "true", "false", "none", "md", "py", "json", "csv"}
    seen, out = set(), []
    for t in toks:
        tl = t.lower()
        if tl in stop or tl in seen:
            continue
        seen.add(tl); out.append(t)
        if len(out) >= k:
            break
    return out


def build_auto(dirp, glob, max_summary, max_depth=1):
    files = sorted(Path(dirp).rglob(glob)) if max_depth > 1 else sorted(Path(dirp).glob(glob))
    rows = []
    for f in files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        title = first_heading(text) or f.stem
        summ = explicit_summary(text) or auto_summary(text, max_summary)
        kw = keywords(text)
        rel = f.relative_to(dirp).as_posix()
        rows.append((rel, title, summ, len(text), kw))
    return rows, files


def render(rows, dirp, nfiles):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [AUTO_BEGIN,
           f"> 目录 `{dirp}`｜{nfiles} 个文件｜生成 {now}｜**重跑本工具即刷新**",
           "",
           "| # | 文件 | 一句话 | 字符 | 关键词 |",
           "|---|---|---|---|---|"]
    for i, (rel, title, summ, n, kw) in enumerate(rows, 1):
        t = title.replace("|", "／")
        s = summ.replace("|", "／")
        kws = " ".join(f"`{k}`" for k in kw)
        out.append(f"| {i} | `{rel}` | {t}｜{s} | {n:,} | {kws} |")
    out.append(AUTO_END)
    return "\n".join(out)


def merge(existing, auto_block):
    """若已有 INDEX，替换 AUTO 区；否则整体生成。"""
    if AUTO_BEGIN in existing and AUTO_END in existing:
        pre = existing[:existing.index(AUTO_BEGIN)]
        post = existing[existing.index(AUTO_END) + len(AUTO_END):]
        return pre + auto_block + post
    header = ("# 索引页（由 mkindex.py 生成）\n\n"
              "> ⛔ **本文件是「目录页」，不是内容页**：只放文件名 + 一句话 + 关键词。\n"
              "> 需要正文 ⇒ 用 `memfind.py` 或直接 Read 对应文件。\n\n"
              "<!-- 手工导读区：可在此补分类/入口，写在本行与 AUTO 区之间 -->\n\n")
    return header + auto_block


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("-o", "--out", help="输出文件（默认只打印）")
    ap.add_argument("--glob", default="*.md")
    ap.add_argument("--max-summary", type=int, default=100)
    ap.add_argument("--depth", type=int, default=1, help="递归深度：1=仅当前目录")
    a = ap.parse_args()

    dirp = a.dir
    if not os.path.isdir(dirp):
        print(f"目录不存在：{dirp}"); return 1
    rows, files = build_auto(dirp, a.glob, a.max_summary, a.depth)
    auto = render(rows, dirp, len(files))
    total = sum(r[3] for r in rows)

    if not a.out:
        print(auto)
        print(f"\n{C_DIM}（{len(rows)} 文件 / {total:,} 字符）{C_END}", file=sys.stderr)
        return 0

    outp = Path(a.out)
    existing = outp.read_text(encoding="utf-8") if outp.exists() else ""
    outp.write_text(merge(existing, auto), encoding="utf-8")
    newlen = len(outp.read_text(encoding="utf-8"))
    print(f"{C_KEY}✅ 已写入 {outp}{C_END}")
    print(f"   文件 {len(rows)} 个 / 正文合计 {total:,} 字符 ⇒ 索引 {newlen:,} 字符"
          f"（压缩比 {total/max(newlen,1):.0f}×）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
