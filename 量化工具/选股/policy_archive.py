#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""政策语料结构化（补上新闻联播笔记里那个一直空着的 "PHASE 2"）

把所有新闻联播语料（新库 + 旧库，实测 640 篇 / 2025-01 → 2026-10）逐期跑
`news_policy_scanner` 的**同一套** KEYWORD_MAP 映射，落库成「日期 × 板块」时间序列，
供回溯与后续「政策词 → 板块 N 日涨幅」类回测使用。

⚠️ 库只读；产出全部写在 本目录/政策信号库/。

产出：
  policy_daily.jsonl              逐期明细（日期 / 来源 / frontmatter tags / 各板块 mentions·score·direction）
  policy_signals_timeseries.csv   长表（一行 = 日期 × 板块）
  policy_summary.md               覆盖范围 + 全期/最近月/逐月 板块热度

用法：
  python3 policy_archive.py --limit 12          # 冒烟测试（只跑最新 12 期）
  python3 policy_archive.py --since 2026-01-01  # 只跑某日期之后
  python3 policy_archive.py                     # 全量（640 篇，iCloud 约 10-30 分钟）
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import news_policy_scanner as nps  # noqa: E402  复用同一套映射

OUT = HERE / "政策信号库"
TOP_RE = re.compile(r"新思想引领新征程|习近平|国务院新闻办|李强")


def all_news_files():
    """{YYYY-MM-DD: Path}，遍历 nps.BASE_DIRS 全部目录；同日以先出现者为准"""
    files = {}
    for base_str in nps.BASE_DIRS:
        base = Path(base_str)
        if not base.exists():
            print(f"WARN 目录不存在: {base}", file=sys.stderr)
            continue
        for p in base.rglob("*_新闻联播.md"):
            m = re.match(r"(\d{4}-\d{2}-\d{2})_新闻联播\.md$", p.name)
            if m and m.group(1) not in files:
                files[m.group(1)] = p
    return dict(sorted(files.items()))


def frontmatter_tags(text):
    """旧库有 tags frontmatter，新库没有（实测）——有就取，取不到返回空"""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return []
    for line in m.group(1).splitlines():
        if line.strip().startswith("tags:"):
            raw = line.split(":", 1)[1]
            return [t.strip() for t in re.findall(r"[^\[\],、\s]+", raw) if t.strip()]
    return []


def scan_one(content):
    """单期 → {板块: {mentions, score, direction}}（与 nps.scan_signals 同一算法）"""
    sig = defaultdict(lambda: {"mentions": 0, "score": 0, "direction": 0})
    for title, body in nps.extract_headlines(content).items():
        is_top = bool(TOP_RE.search(title))
        for pattern, info in nps.KEYWORD_MAP.items():
            if re.search(pattern, title) or re.search(pattern, body):
                weight = 3 if is_top else 2
                score = info["level"] * weight
                for sector in info["sectors"]:
                    s = sig[sector]
                    s["mentions"] += 1
                    s["score"] += score * info["direction"]
                    s["direction"] = info["direction"]
    return dict(sig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=str, default="", help="只处理该日期(YYYY-MM-DD)及之后")
    ap.add_argument("--limit", type=int, default=0, help="只处理最新 N 期（冒烟测试用）")
    args = ap.parse_args()

    files = all_news_files()
    items = list(files.items())
    if args.since:
        items = [(d, p) for d, p in items if d >= args.since]
    if args.limit:
        items = items[-args.limit:]
    if not items:
        print("ERROR 没有可处理的新闻联播文件", file=sys.stderr)
        sys.exit(1)

    print(f"待处理 {len(items)} 期：{items[0][0]} ~ {items[-1][0]}", file=sys.stderr)
    OUT.mkdir(parents=True, exist_ok=True)

    daily = []
    t0 = time.time()
    for i, (date, path) in enumerate(items, 1):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"ERROR {path}: {e}", file=sys.stderr)
            continue
        headlines = nps.extract_headlines(text)
        daily.append({"date": date, "file": str(path), "tags": frontmatter_tags(text),
                      "sectors": scan_one(text), "headlines": len(headlines)})
        if i % 25 == 0 or i == len(items):
            el = time.time() - t0
            print(f"  ... {i}/{len(items)}  已用 {el:.0f}s  均 {el / i:.2f}s/期", file=sys.stderr)

    if not daily:
        print("ERROR 没有任何一期解析成功", file=sys.stderr)
        sys.exit(1)

    with (OUT / "policy_daily.jsonl").open("w", encoding="utf-8") as fh:
        for d in daily:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    with (OUT / "policy_signals_timeseries.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["日期", "板块", "提及次数", "信号分", "方向"])
        for d in daily:
            for sector, v in sorted(d["sectors"].items(), key=lambda kv: -abs(kv[1]["score"])):
                w.writerow([d["date"], sector, v["mentions"], v["score"], v["direction"]])

    # ── 汇总 ────────────────────────────────────────────
    total = defaultdict(lambda: {"mentions": 0, "score": 0})
    monthly = defaultdict(lambda: defaultdict(int))
    for d in daily:
        for sector, v in d["sectors"].items():
            total[sector]["mentions"] += v["mentions"]
            total[sector]["score"] += v["score"]
            monthly[d["date"][:7]][sector] += v["mentions"]

    last_ym = max(d["date"] for d in daily)[:7]
    recent = defaultdict(lambda: {"mentions": 0, "score": 0})
    for d in daily:
        if d["date"][:7] == last_ym:
            for sector, v in d["sectors"].items():
                recent[sector]["mentions"] += v["mentions"]
                recent[sector]["score"] += v["score"]

    lines = [
        "# 政策信号库（新闻联播 → 板块）",
        "",
        f"> 生成于 {time.strftime('%Y-%m-%d %H:%M')}｜覆盖 **{len(daily)}** 期"
        f"（{daily[0]['date']} ~ {daily[-1]['date']}）",
        "> 映射逻辑与 `news_policy_scanner.py` 完全同源（KEYWORD_MAP；头条权重 3、普通 2）。",
        "> ⚠️ 本目录只是对**语料的结构化**，不改变 NEWS_POLICY_RULE 里「政策只影响置信度、不参与打分」的约定。",
        "",
        "## 全期累计（按 |信号分| 排序，前 20）",
        "",
        "| 板块 | 累计提及 | 累计信号分 |",
        "|---|---:|---:|",
    ]
    for sector, v in sorted(total.items(), key=lambda kv: -abs(kv[1]["score"]))[:20]:
        lines.append(f"| {sector} | {v['mentions']} | {v['score']} |")

    lines += ["", f"## 最近一个月（{last_ym}）板块热度", "", "| 板块 | 提及 | 信号分 |", "|---|---:|---:|"]
    for sector, v in sorted(recent.items(), key=lambda kv: -kv[1]["mentions"])[:15]:
        lines.append(f"| {sector} | {v['mentions']} | {v['score']} |")

    lines += ["", "## 逐月提及 Top5", "", "| 月份 | Top5 板块（提及数） |", "|---|---|"]
    for ym in sorted(monthly):
        top5 = sorted(monthly[ym].items(), key=lambda kv: -kv[1])[:5]
        lines.append(f"| {ym} | " + "、".join(f"{s}({n})" for s, n in top5) + " |")

    (OUT / "policy_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nOK 完成 {len(daily)} 期 → {OUT}", file=sys.stderr)
    print("   policy_daily.jsonl / policy_signals_timeseries.csv / policy_summary.md", file=sys.stderr)


if __name__ == "__main__":
    main()
