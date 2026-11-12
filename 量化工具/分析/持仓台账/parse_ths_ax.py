#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同花顺持仓快照解析器（2026-10-03）

背景：同花顺 Mac 版的持仓表格在 macOS 辅助功能（AX）树里**没有行结构**，
只有一个个带坐标的 AXStaticText 单元格。但坐标本身就能重建表格：
表头按钮给出每个字段的 x 坐标，数据单元格按 y 分组成行。

流程（两步，可复用）：
  ① 用 CUA 把窗口 AX 全文 dump 到文件（node_repl + computer.observeWindow）
  ② python3 parse_ths_ax.py <AX文本文件> [日期]   ← 本脚本

输出：
  终端打印账户总览 + 重建出的持仓表
  `ths_live_<日期>.csv`（与本脚本同目录）

⚠️ 只读解析，不涉及任何下单动作。
✅ 实测：表头首列名是「证券代码」（不是「代码」），此处按实测写死。
"""

import csv
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 表头字段（顺序 = 从左到右，按 2026-10-03 实测的 AX 表头按钮名）
HEADERS = ["证券代码", "证券名称", "市价", "盈亏", "当日盈亏", "浮动盈亏比(%)", "实际数量",
           "股票余额", "可用余额", "冻结数量", "成本价", "市值", "仓位占比(%)",
           "交易市场", "股东账户"]
OUT_ALIAS = {"证券代码": "代码"}  # 输出时简写
ACCOUNT = ["总资产", "总市值", "总盈亏", "当日盈亏", "资金余额", "可取金额", "可用金额"]

NODE_RE = re.compile(r"frame=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)")
QUOTED_RE = re.compile(r'"([^"]*)"')


def parse_nodes(text):
    """AX 文本 → [(name, x, y, w, h)]"""
    out = []
    for line in text.splitlines():
        m = NODE_RE.search(line)
        if not m:
            continue
        names = QUOTED_RE.findall(line)
        if names:
            out.append((names[0], float(m.group(1)), float(m.group(2)),
                        float(m.group(3)), float(m.group(4))))
    return out


def build(nodes):
    # ① 表头 x 坐标（精确匹配整名，避免「盈亏」误吃「当日盈亏」）
    col_x = {}
    for h in HEADERS:
        for name, x, _y, _w, hh in nodes:
            if name == h and 10 < hh < 40:
                col_x.setdefault(h, x)
                break

    # ② 账户总览：标签在左侧(x<80)，取同一行(x≈142)的值
    acct = {}
    for name, x, y, _w, _h in nodes:
        if name in ACCOUNT and x < 80:
            for n2, x2, y2, _w2, _h2 in nodes:
                if abs(x2 - 142) < 6 and abs(y2 - y) < 3:
                    acct[name] = n2
                    break

    # ③ 数据行：单元格 x 落在已知列上 → 按 y 分组成行
    rows = {}
    for name, x, y, _w, _h in nodes:
        for col, cx in col_x.items():
            if abs(x - cx) < 6:
                rows.setdefault(round(y, 1), {})[col] = name
                break
    data = []
    for y in sorted(rows):
        if re.fullmatch(r"\d{6}", rows[y].get("证券代码", "")):
            data.append(rows[y])
    return acct, data, col_x


def main():
    if len(sys.argv) < 2:
        print("用法: python3 parse_ths_ax.py <AX文本文件> [日期YYYY-MM-DD]", file=sys.stderr)
        sys.exit(1)
    src = Path(sys.argv[1]).expanduser()
    date = sys.argv[2] if len(sys.argv) > 2 else "live"
    acct, data, col_x = build(parse_nodes(src.read_text(encoding="utf-8", errors="ignore")))

    if not col_x:
        print("⚠️ 未识别到持仓表头（该窗口当前可能不在「持仓」页）", file=sys.stderr)

    print("== 账户总览 ==")
    for k in ACCOUNT:
        if k in acct:
            print(f"  {k}: {acct[k]}")
    print(f"\n== 持仓 {len(data)} 只 ==")
    show = ["证券代码", "证券名称", "市价", "盈亏", "浮动盈亏比(%)", "实际数量",
            "可用余额", "成本价", "市值", "仓位占比(%)"]
    for r in data:
        print("  " + " | ".join(f"{OUT_ALIAS.get(k, k)}={r.get(k, '')}" for k in show))

    out = HERE / f"ths_live_{date}.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["数据日期"] + [OUT_ALIAS.get(k, k) for k in HEADERS])
        for r in data:
            w.writerow([date] + [r.get(k, "") for k in HEADERS])
    print(f"\n已写出 {out}")


if __name__ == "__main__":
    main()
