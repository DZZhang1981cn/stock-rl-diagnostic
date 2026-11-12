#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宏观素材提取器 v2（项目 4）2026-10-03

⚠️ 库只读；产出全部写在本目录。

实测发现日报有**两族、格式完全不同**：
  · 宏观日报族（含 📊 板块信号）：表是 | 信号 | 动态 |，数值藏在中文长句里
  · 归档族（"非农持仓深度分析"式）：含【操作建议表】| 股票 | 动作 | 触发价 | 金额 | 优先级 |
因此本版不再只盯"信号表"，而是：
  ① 把**所有**日报表格无损转存（macro_daily_tables.csv）—— 不丢信息
  ② 单独抽出【操作建议表】→ macro_trade_plans.csv（计划交易，可与持仓台账对照执行）
  ③ 尽力从信号表抽数值 → macro_indicators_timeseries.csv（可能稀疏，属正常）
  ④ 事件日历 → macro_events.csv + 持仓暴露矩阵

产出：
  macro_daily_tables.csv           全部日报表格无损转存（日期,章节,表头,整行）
  macro_trade_plans.csv            计划交易（日期,代码,名称,动作,触发价,金额,优先级）
  macro_indicators_raw.csv         信号|动态 原文
  macro_indicators_timeseries.csv  日期,指标,数值,单位,环比%,同比%
  macro_events.csv                 事件日历
  event_exposure_matrix.md         事件 × 持仓 暴露矩阵 v1

用法：python3 macro_extract.py
"""

import csv
import re
import sys
from pathlib import Path

VAULT = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆"
OUT_DIR = Path(__file__).resolve().parent
LEDGER_CURRENT = OUT_DIR.parent / "持仓台账" / "positions_current.csv"

DAILY_DIRS = [
    "03_投资研究/理财/宏观经济日报",
    "03_投资研究/理财/宏观经济日报_历史归档",
]
CALENDAR = "04_宏观与资讯/宏观事件日历.md"

EXPOSURE = [
    (r"美联储|FOMC|议息|美债|加息|降息", ["银行", "贵金属", "地产", "高股息"], "利率与汇率 → 高股息吸引力 / 外币负债 / 贵金属"),
    (r"LPR|利率|降准|货币政策", ["银行", "地产", "券商"], "资金价格 → 金融与地产估值"),
    (r"非农|就业|美国经济|耐用品", ["贵金属", "出口"], "美国需求 → 出口链与避险资产"),
    (r"PMI|工业利润|CPI|PPI|经济数据", ["周期", "制造"], "景气度 → 周期品与制造业盈利"),
    (r"原油|油价|石油|中东|伊朗|地缘", ["航空", "电力", "化工", "轮胎成本"], "油价 → 航空成本 / 煤价替代 / 橡胶与化工原料"),
    (r"关税|中美|经贸|磋商|贸易", ["外贸", "消费电子", "出口"], "贸易条件 → 外贸与出口链"),
    (r"用电|电力|煤价|保供", ["电力"], "电价与煤价 → 电力盈利"),
    (r"消费|旅游|内需|零售|以旧换新", ["消费", "旅游", "酒店"], "内需 → 消费与出行链"),
]

HOLDING_SECTOR = {
    "600600": ("青岛啤酒", ["消费", "大麦成本"]),
    "601991": ("大唐发电", ["电力", "煤价成本"]),
    "000651": ("格力电器", ["消费", "铜铝成本"]),
    "600415": ("小商品城", ["外贸", "消费"]),
    "603501": ("豪威集团", ["消费电子", "出口"]),
    "600029": ("南方航空", ["航空", "油价成本"]),
}

NUM_UNIT = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,14}?)([\d]+\.?\d*)\s*(元/公斤|元/斤|元/吨|元|点|%|亿元|万吨)")


def clean_md(s):
    s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    return s.replace("~~", "").replace("**", "").replace("`", "").strip()


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


def sections_of(text):
    """给每行标注所属章节（## / ###），供表格归属用"""
    out, cur = [], ""
    for line in text.splitlines():
        m = re.match(r"^#{2,3}\s+(.*)", line)
        if m:
            cur = clean_md(m.group(1))
        out.append(cur)
    return out


def extract_daily():
    raw, ts, tables, plans = [], [], [], []
    for rel in DAILY_DIRS:
        d = VAULT / rel
        if not d.exists():
            print(f"WARN 目录不存在: {rel}", file=sys.stderr)
            continue
        for f in sorted(d.glob("*.md")):
            date = f.stem
            text = f.read_text(encoding="utf-8", errors="ignore")
            sec_lines = sections_of(text)
            for header, rows in iter_tables(text):
                h = "|".join(header)
                for r in rows:
                    tables.append([date, rel.split("/")[-1], h, " | ".join(clean_md(c) for c in r)])

                # ① 信号 | 动态
                if "信号" in header[0] and len(header) >= 2:
                    for r in rows:
                        if len(r) < 2:
                            continue
                        signal, detail = clean_md(r[0]), clean_md(r[1])
                        if not signal or not detail:
                            continue
                        raw.append([date, rel.split("/")[-1], signal, detail])
                        mm = re.search(r"环比[涨跌降升]?\s*([\d.]+)\s*%", detail)
                        tt = re.search(r"同比[涨跌降升]?\s*([\d.]+)\s*%", detail)
                        for name, val, unit in NUM_UNIT.findall(detail):
                            ts.append([date, f"{signal}·{name.strip()}", val, unit,
                                       mm.group(1) if mm else "", tt.group(1) if tt else ""])

                # ② 操作建议表：股票 | 动作 | 触发价 | 金额 | 优先级
                if any("动作" in x for x in header) and any("触发价" in x for x in header):
                    def idx(*names):
                        for i, x in enumerate(header):
                            if any(n in x for n in names):
                                return i
                        return -1
                    i_stock, i_act = idx("股票", "代码"), idx("动作")
                    i_price, i_amt, i_pri = idx("触发价", "价格"), idx("金额"), idx("优先级")
                    for r in rows:
                        if i_stock < 0 or len(r) <= max(i_stock, i_act, i_price, i_amt, i_pri):
                            continue
                        raw_stock = clean_md(r[i_stock])
                        mcode = re.search(r"\d{6}", raw_stock)
                        code = mcode.group() if mcode else ""
                        name = re.sub(r"\d{6}", "", raw_stock).strip()
                        if not name and not code:
                            continue
                        plans.append([date, code, name, clean_md(r[i_act]),
                                      clean_md(r[i_price]), clean_md(r[i_amt]), clean_md(r[i_pri])])
    return raw, ts, tables, plans


def extract_events():
    p = VAULT / CALENDAR
    if not p.exists():
        print(f"WARN 文件不存在: {CALENDAR}", file=sys.stderr)
        return []
    out = []
    for header, rows in iter_tables(p.read_text(encoding="utf-8", errors="ignore")):
        h = "|".join(header)
        if "事件" not in h or "日期" not in h:
            continue
        for r in rows:
            if len(r) < 3:
                continue
            rec = {"日期": clean_md(r[0]), "事件": clean_md(r[1]), "重要性": clean_md(r[2]),
                   "阶段": clean_md(r[3]) if len(r) > 3 else "",
                   "状态": clean_md(r[4]) if len(r) > 4 else "",
                   "详细分析": clean_md(r[5]) if len(r) > 5 else ""}
            if rec["事件"] and rec["日期"]:
                out.append(rec)
    return out


def load_holdings():
    if not LEDGER_CURRENT.exists():
        return []
    with LEDGER_CURRENT.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def build_matrix(events, holdings):
    lines = ["# 宏观事件 × 持仓 暴露矩阵（v1 自动生成）", "",
             "> 事件源：`04_宏观与资讯/宏观事件日历.md`｜持仓源：`持仓台账/positions_current.csv`",
             "> ⚠️ 传导映射写在 `macro_extract.py` 的 `EXPOSURE` / `HOLDING_SECTOR` 里，**随时可改**。",
             "> 只做「可能受影响」的定向提示，**不构成操作建议**；幅度需人工判断。", ""]
    if not holdings:
        lines.append("_未读到持仓台账，先跑 持仓台账/extract_positions.py_")
        return "\n".join(lines)
    lines += ["## 当前持仓（来自台账）", "", "| 代码 | 名称 | 股数 | 成本 | 盈亏率% |", "|---|---|---:|---:|---:|"]
    for h in holdings:
        lines.append(f"| {h['代码']} | {h['名称']} | {h['股数']} | {h['成本']} | {h['盈亏率%']} |")
    lines += ["", "## 事件 → 受影响板块 → 相关持仓", "",
              "| 事件（含日期原文） | 重要性 | 阶段 | 受影响板块 | 命中的持仓 | 传导逻辑 |",
              "|---|---|---|---|---|---|"]
    for e in events:
        hit, logics = set(), []
        for pat, sectors, why in EXPOSURE:
            if re.search(pat, e["事件"] + e["详细分析"]):
                hit.update(sectors)
                logics.append(why)
        hits = [f"{n}({c})" for c, (n, secs) in HOLDING_SECTOR.items() if hit & set(secs)]
        if hit:
            lines.append("| {} | {} | {} | {} | {} | {} |".format(
                e["日期"] + " " + e["事件"], e["重要性"], e["阶段"], "、".join(sorted(hit)),
                "、".join(hits) or "—", "；".join(dict.fromkeys(logics))))
    return "\n".join(lines)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw, ts, tables, plans = extract_daily()
    events = extract_events()

    def dump(name, header, rows):
        with (OUT_DIR / name).open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)

    dump("macro_daily_tables.csv", ["日期", "来源目录", "表头", "整行"], tables)
    dump("macro_trade_plans.csv", ["日期", "代码", "名称", "动作", "触发价", "金额", "优先级"], plans)
    dump("macro_indicators_raw.csv", ["日期", "来源目录", "信号", "动态原文"], raw)
    dump("macro_indicators_timeseries.csv", ["日期", "指标", "数值", "单位", "环比%", "同比%"], ts)
    dump("macro_events.csv", ["日期", "事件", "重要性", "阶段", "状态", "详细分析"],
         [[e["日期"], e["事件"], e["重要性"], e["阶段"], e["状态"], e["详细分析"]] for e in events])

    holdings = load_holdings()
    (OUT_DIR / "event_exposure_matrix.md").write_text(build_matrix(events, holdings), encoding="utf-8")

    print(f"日报表格行: {len(tables)}  |  计划交易: {len(plans)}  |  信号原文: {len(raw)}  "
          f"|  指标行: {len(ts)}  |  事件: {len(events)}  |  持仓: {len(holdings)}")
    print("已写出 6 个文件到 " + str(OUT_DIR))


if __name__ == "__main__":
    main()
