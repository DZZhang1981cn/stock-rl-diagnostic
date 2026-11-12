#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""持仓台账提取器 v3（2026-10-03）

从 Obsidian 库里**周期性笔记**中抽取「持仓表」，汇总成可累计的台账。
⚠️ Obsidian 库全程**只读**；所有产出写到本目录（~/Desktop/AI工作/量化工具/分析/持仓台账/）。

库内实际存在至少 7 种表头变体（实测），因此本版规则：
  1. **按表头名映射列**，别名表覆盖全部实测变体：
     名称 = 名称/股票名称/股票(不含"代码"的单元格)
     股数 = 股数/持股/持股数/数量
     成本 = 成本/成本价
     现价 = 现价/最新价/收盘价/含"收盘"的列（如"9/19收盘"）
     盈亏额 = 浮盈亏/浮动盈亏/盈亏额/浮亏
     盈亏率 = 盈亏率/盈亏%
  2. 同一列只被一个字段占用（避免"盈亏"抢走"盈亏率"列）。
  3. 持仓表判定 = 同时具备 代码 + 名称 + 股数 + 成本（避免把观察池/高股息候选/分红表误判）。
  4. 账户总览只在首列含「指标」的表里取；表头含「变化」时取倒数第二列。
  5. 「万/亿」换算**不作用于百分比字段**。
  6. 同快照按代码去重；对票数/总市值/仓位做合理性检查，可疑快照打标且不参与事件推导。

产出：positions_timeseries.csv / positions_current.csv / position_events.csv / extract_report.txt
用法：python3 extract_positions.py [--check]     # 全量约 1-2 分钟（iCloud）
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆"
OUT_DIR = Path(__file__).resolve().parent

SOURCE_DIRS = [
    "03_投资研究/股票投资/板块周报",
    "03_投资研究/股票投资/周末体检",
    "03_投资研究/股票投资/每日盘前简报",
    "03_投资研究/投资日记",
    "03_投资研究/持仓分析",
    "03_投资研究/个股研究",
]

# 顺序即优先级；先匹配到的字段先占列
FIELD_ALIASES = [
    ("代码", ["代码"]),
    ("盈亏率", ["盈亏率", "盈亏%"]),
    ("盈亏额", ["浮盈亏", "浮动盈亏", "盈亏额", "浮亏"]),
    ("股数", ["股数", "持股", "数量"]),
    ("成本", ["成本"]),
    ("现价", ["现价", "最新价", "收盘"]),
    ("市值", ["市值"]),
    ("名称", ["名称", "股票"]),
]
PCT_FIELDS = {"盈亏率", "持仓占比"}
HOLDING_REQUIRED = ("代码", "名称", "股数", "成本")

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
EMOJI_RE = re.compile(r"^[^\u4e00-\u9fa5A-Za-z0-9]+")


def num(v, allow_wan=True):
    """'¥549,121' / '-9.76%' / '66.4万' / '+2.3% ✅' → float（百分比不做万换算）"""
    if v is None:
        return None
    s = str(v)
    mult = 1.0
    if allow_wan and "%" not in s:
        if "亿" in s:
            mult = 1e8
        elif "万" in s:
            mult = 1e4
    s = s.replace("，", ",").replace("¥", "").replace(",", "")
    for ch in ("**", "✅", "～", "~", "*"):
        s = s.replace(ch, "")
    m = NUM_RE.search(s)
    return float(m.group()) * mult if m else None


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep(line):
    return bool(re.match(r"^\|[\s:\-|]+\|\s*$", line.strip()))


def iter_tables(text):
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:
        if lines[i].strip().startswith("|") and is_sep(lines[i + 1]):
            header = split_row(lines[i])
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(split_row(lines[j]))
                j += 1
            yield header, rows
            i = j
        else:
            i += 1


def col_map(header):
    """按别名优先级映射 → {字段: 列下标}；每列只归一个字段"""
    m, used = {}, set()
    for out_name, aliases in FIELD_ALIASES:
        for a in aliases:
            for idx, h in enumerate(header):
                if idx in used:
                    continue
                if out_name == "名称" and "代码" in h:  # 避免把"股票代码"当名称
                    continue
                if a in h:
                    m[out_name] = idx
                    used.add(idx)
                    break
            if out_name in m:
                break
    return m


def is_holdings_table(cmap):
    return all(k in cmap for k in HOLDING_REQUIRED)


def date_from_name(name):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""


def parse_account_table(header, rows):
    out = {}
    if not header or "指标" not in header[0]:
        return out
    val_idx = len(header) - 2 if any("变化" in h for h in header) else 1
    for r in rows:
        if len(r) <= val_idx:
            continue
        k, val = r[0], r[val_idx]
        for key, names in (("total_assets", ("总资产",)), ("total_cost", ("总成本",)),
                           ("total_pnl", ("总盈亏",)), ("total_mv", ("总市值",)),
                           ("holdings_count", ("持仓数量", "持仓数")), ("position_pct", ("仓位",))):
            if key in out:
                continue
            if any(n in k for n in names):
                out[key] = num(val, allow_wan=key != "position_pct")
    return out


def parse_file(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta = {"data_date": "", "total_assets": None, "total_cost": None, "total_pnl": None,
            "total_mv": None, "position_pct": None, "holdings_count": None}

    m = re.search(r"最新更新\s*(\d{4}-\d{2}-\d{2})", text)
    if m:
        meta["data_date"] = m.group(1)

    holdings = []
    for header, rows in iter_tables(text):
        cmap = col_map(header)
        if is_holdings_table(cmap):
            for r in rows:
                if len(r) <= max(cmap.values()):
                    continue
                code = re.sub(r"\D", "", r[cmap["代码"]])
                if len(code) != 6:
                    continue  # 跳过表内合计行等
                name = EMOJI_RE.sub("", r[cmap["名称"]]).strip() or r[cmap["名称"]]
                holdings.append({
                    "代码": code, "名称": name,
                    "成本": num(r[cmap["成本"]]) if "成本" in cmap else None,
                    "股数": num(r[cmap["股数"]]) if "股数" in cmap else None,
                    "现价": num(r[cmap["现价"]]) if "现价" in cmap else None,
                    "市值": num(r[cmap["市值"]]) if "市值" in cmap else None,
                    "盈亏额": num(r[cmap["盈亏额"]]) if "盈亏额" in cmap else None,
                    "盈亏率": num(r[cmap["盈亏率"]], allow_wan=False) if "盈亏率" in cmap else None,
                })
        else:
            for k, v in parse_account_table(header, rows).items():
                if v is not None and meta.get(k) is None:
                    meta[k] = v

    seen, uniq = set(), []
    for r in holdings:
        if r["代码"] in seen:
            continue
        seen.add(r["代码"])
        uniq.append(r)

    for line in text.splitlines():  # 页脚兜底：只认 '>' 引用行
        if not line.lstrip().startswith(">"):
            continue
        if meta["total_assets"] is None:
            m = re.search(r"总资产\s*¥?([\d,]+(?:\.\d+)?万?)", line)
            if m:
                meta["total_assets"] = num(m.group(1))
        if meta["total_mv"] is None:
            m = re.search(r"总市值\s*~?¥?([\d,]+(?:\.\d+)?万?)", line)
            if m:
                meta["total_mv"] = num(m.group(1))
        if meta["position_pct"] is None:
            m = re.search(r"仓位\s*~?\s*([\d.]+)%", line)
            if m:
                meta["position_pct"] = float(m.group(1))

    if not meta["data_date"]:
        meta["data_date"] = date_from_name(path.name)

    flags = []
    if len(uniq) > 10:
        flags.append(f"票数异常({len(uniq)})")
    if meta["total_mv"] is not None and not (1e5 < meta["total_mv"] < 5e6):
        flags.append(f"总市值异常({meta['total_mv']:g})")
    if meta["position_pct"] is not None and not (0 <= meta["position_pct"] <= 100):
        flags.append(f"仓位异常({meta['position_pct']:g})")

    return meta, uniq, flags


def main():
    check_only = "--check" in sys.argv
    snapshots, report = [], []

    for rel in SOURCE_DIRS:
        d = VAULT / rel
        if not d.exists():
            report.append(f"⚠️ 目录不存在: {rel}")
            continue
        for f in sorted(d.glob("*.md")):
            try:
                meta, rows, flags = parse_file(f)
            except Exception as e:
                report.append(f"❌ {rel}/{f.name}: {type(e).__name__} {e}")
                continue
            mark = "✅" if rows and not flags else ("⚠️" if rows else "·")
            tail = f"  ⚠️ {'; '.join(flags)}" if flags else ""
            report.append(f"{mark} {rel}/{f.name}: {meta['data_date'] or '未知'} 票{len(rows)}{tail}")
            if rows:
                snapshots.append({"report_date": date_from_name(f.name), "data_date": meta["data_date"],
                                  "source": f"{rel}/{f.name}", "meta": meta, "rows": rows, "flags": flags})

    snapshots.sort(key=lambda s: (s["data_date"] or s["report_date"]))
    print("\n".join(report))
    print(f"\n识别到 {len(snapshots)} 张持仓快照")
    for s in snapshots:
        m = s["meta"]
        f = f"  ⚠️ {'; '.join(s['flags'])}" if s["flags"] else ""
        print(f"  {s['data_date'] or s['report_date']}  {len(s['rows'])} 票  "
              f"总市值={m['total_mv']}  总资产={m['total_assets']}  仓位={m['position_pct']}  持仓数={m['holdings_count']}{f}")

    if check_only:
        print("\n(--check 模式，未写文件)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    with (OUT_DIR / "positions_timeseries.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["数据日期", "报告日期", "来源文件", "代码", "名称", "成本", "股数", "现价", "市值",
                    "盈亏额", "盈亏率%", "快照总市值", "快照总资产", "快照仓位%", "可疑", "提取时间"])
        for s in snapshots:
            m = s["meta"]
            for r in s["rows"]:
                w.writerow([s["data_date"], s["report_date"], s["source"], r["代码"], r["名称"], r["成本"],
                            r["股数"], r["现价"], r["市值"], r["盈亏额"], r["盈亏率"], m["total_mv"],
                            m["total_assets"], m["position_pct"], "; ".join(s["flags"]), now])

    if snapshots:
        cur = snapshots[-1]
        with (OUT_DIR / "positions_current.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["数据日期", "代码", "名称", "成本", "股数", "现价", "市值", "盈亏率%", "来源"])
            for r in cur["rows"]:
                w.writerow([cur["data_date"], r["代码"], r["名称"], r["成本"], r["股数"], r["现价"],
                            r["市值"], r["盈亏率"], cur["source"]])

    with (OUT_DIR / "position_events.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["日期", "代码", "名称", "事件", "股数变化", "股数前", "股数后", "成本前", "成本后", "依据"])
        for prev, cur in zip(snapshots, snapshots[1:]):
            if prev["flags"] or cur["flags"]:
                continue
            a = {r["代码"]: r for r in prev["rows"]}
            b = {r["代码"]: r for r in cur["rows"]}
            span = f"{prev['data_date']}→{cur['data_date']}"
            for code in sorted(set(a) | set(b)):
                ra, rb = a.get(code), b.get(code)
                if ra and not rb:
                    w.writerow([cur["data_date"], code, ra["名称"], "清仓", -ra["股数"], ra["股数"], 0,
                                ra["成本"], "", span])
                elif rb and not ra:
                    w.writerow([cur["data_date"], code, rb["名称"], "建仓", rb["股数"], 0, rb["股数"],
                                "", rb["成本"], span])
                else:
                    d_share = (rb["股数"] or 0) - (ra["股数"] or 0)
                    d_cost = round(rb["成本"] - ra["成本"], 4) if (
                        ra["成本"] is not None and rb["成本"] is not None
                        and abs(ra["成本"] - rb["成本"]) > 0.0005) else None
                    if abs(d_share) > 0.5:
                        w.writerow([cur["data_date"], code, rb["名称"], "加仓" if d_share > 0 else "减仓",
                                    d_share, ra["股数"], rb["股数"], ra["成本"], rb["成本"], span])
                    elif d_cost:
                        w.writerow([cur["data_date"], code, rb["名称"], "成本变动", 0, ra["股数"], rb["股数"],
                                    ra["成本"], rb["成本"], span])

    (OUT_DIR / "extract_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n已写出：positions_timeseries.csv / positions_current.csv / position_events.csv / extract_report.txt")


if __name__ == "__main__":
    main()
