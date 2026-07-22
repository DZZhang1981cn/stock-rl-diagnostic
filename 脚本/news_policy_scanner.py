#!/usr/bin/env python3
"""
新闻联播政策信号扫描器 v1.0
扫描最近 N 期新闻联播文字稿 → 提取政策关键词 → 映射到 A 股板块

用法:
  python3 news_policy_scanner.py                        # 扫描最近3期，输出所有信号
  python3 news_policy_scanner.py --days 7               # 扫描最近7天
  python3 news_policy_scanner.py --stocks 600547,601991  # 输出这两只票的政策风向
  python3 news_policy_scanner.py --json                 # JSON 格式输出（供其他脚本调用）

数据源:
  /Users/zhangzhenhua/Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆/新闻联播/
  可通过环境变量 NEWS_BROADCAST_DIR 覆盖

新建: 2026-07-22
"""

import os
import re
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# ── 数据源路径 ──────────────────────────────────────────
DEFAULT_BASE_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆/新闻联播/"
)
BASE_DIR = os.environ.get("NEWS_BROADCAST_DIR", DEFAULT_BASE_DIR)

# ── 关键词 → 板块映射表 ────────────────────────────────
KEYWORD_MAP = {
    # 一级信号（头条级）
    "节能降碳|碳中和|碳达峰|新能源|可再生能源|光伏|风电|新型能源": {
        "sectors": ["电力", "新能源", "光伏", "储能"],
        "level": 3,
        "direction": 1
    },
    "新能源汽车|电动车|充电桩": {
        "sectors": ["新能源车", "锂电", "充电桩"],
        "level": 3,
        "direction": 1
    },
    "交通强国|高铁|高速公路|综合交通.*枢纽|基础设施.*更新|农村公路": {
        "sectors": ["基建", "建材", "工程机械", "钢铁"],
        "level": 3,
        "direction": 1
    },
    "数字经济|数字化转型|人工智能|AI |算力": {
        "sectors": ["计算机", "通信", "数据中心"],
        "level": 3,
        "direction": 1
    },
    "半导体|芯片|集成电路": {
        "sectors": ["半导体", "电子"],
        "level": 3,
        "direction": 1
    },
    "种业|粮食安全|农业现代化": {
        "sectors": ["农业", "种业", "化肥"],
        "level": 2,
        "direction": 1
    },
    "健康中国|医疗卫生|生物医药|中医药|卫生健康": {
        "sectors": ["医药", "医疗器械"],
        "level": 2,
        "direction": 1
    },
    "住房|房地产|保障房|城市更新": {
        "sectors": ["房地产", "建材", "家电"],
        "level": 2,
        "direction": 1
    },
    "育儿|生育|托育|家政": {
        "sectors": ["母婴", "家政服务", "消费"],
        "level": 1,
        "direction": 1
    },
    "养老|老龄化|银发经济": {
        "sectors": ["养老服务", "医疗器械"],
        "level": 1,
        "direction": 1
    },
    "降准|降息|流动性|货币政策": {
        "sectors": ["全市场"],
        "level": 3,
        "direction": 1
    },
    # 二级信号
    "外贸|进出口|跨境电商": {
        "sectors": ["港口", "航运", "外贸"],
        "level": 2,
        "direction": 1
    },
    "免签|入境游|旅游": {
        "sectors": ["旅游", "航空", "酒店"],
        "level": 2,
        "direction": 1
    },
    "家电.*以旧换新|消费补贴": {
        "sectors": ["家电", "消费"],
        "level": 2,
        "direction": 1
    },
    "稀土|有色金属|矿产": {
        "sectors": ["有色", "稀土"],
        "level": 2,
        "direction": 1
    },
    "军工|国防|航天": {
        "sectors": ["军工", "航空航天"],
        "level": 2,
        "direction": 1
    },
    "煤炭|煤电|火电": {
        "sectors": ["煤炭"],
        "level": 1,
        "direction": 1  # 注意：需根据上下文判断方向
    },
    # 反向信号（利空）
    "产能过剩|去产能": {
        "sectors": ["钢铁", "水泥", "化工"],
        "level": 2,
        "direction": -1
    },
    "房住不炒|房地产调控": {
        "sectors": ["房地产", "建材"],
        "level": 2,
        "direction": -1
    },
    "反垄断|平台整改": {
        "sectors": ["互联网", "平台经济"],
        "level": 2,
        "direction": -1
    },
    "环保限产|节能.*传统|节能减排.*钢铁|节能减排.*化工": {
        "sectors": ["钢铁", "化工", "水泥"],
        "level": 2,
        "direction": -1
    },
    "集采|医保控费": {
        "sectors": ["医药"],
        "level": 2,
        "direction": -1
    },
}

# ── 板块 → 股票映射（观察池 + 持仓常用） ────────────
SECTOR_STOCK_MAP = {
    "电力": ["600726", "601991", "600236", "600578", "600863"],
    "黄金": ["600547", "000975", "600489", "600988"],
    "贵金属": ["600547", "000975", "600489", "600988"],
    "有色": ["601168", "000603", "000975"],
    "新能源": ["601991", "600236", "600032"],
    "基建": ["600039", "601233", "300896"],
    "建材": ["000786", "002043", "601233"],
    "家电": ["000651"],
    "消费": ["000651", "002027", "300896"],
    "航空": ["600029"],
    "化工": ["601233", "600426", "600989"],
    "医药": ["300896", "300832", "000661"],
    "计算机": ["000938", "002396", "301165"],
    "半导体": ["603893", "688608"],
    "港口": ["001872"],
    "农业": ["000893", "002545"],
}


def find_news_files(days=3):
    """找到最近 N 天的新闻联播文件"""
    base = Path(BASE_DIR)
    if not base.exists():
        return []

    today = datetime.now()
    files = []
    for i in range(days):
        d = today - timedelta(days=i)
        fname = d.strftime("%Y-%m-%d_新闻联播.md")
        fpath = base / fname
        if fpath.exists():
            files.append(str(fpath))
    return sorted(files)


def extract_headlines(content):
    """从新闻联播内容中提取各条新闻标题"""
    headlines = {}
    current_title = None
    current_lines = []

    for line in content.split('\n'):
        # 匹配## 标题
        m = re.match(r'^##\s+(.*)', line)
        if m:
            if current_title:
                headlines[current_title] = '\n'.join(current_lines)
            current_title = m.group(1).strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)

    if current_title:
        headlines[current_title] = '\n'.join(current_lines)

    return headlines


def scan_signals(news_files):
    """扫描所有新闻联播文件，提取政策信号"""
    all_signals = defaultdict(lambda: {"mentions": 0, "score": 0, "direction": 0})

    for fpath in news_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        date_str = Path(fpath).stem[:10]
        headlines = extract_headlines(content)

        for title, body in headlines.items():
            # 判断权重
            is_top = bool(re.search(r'新思想引领新征程|习近平|国务院新闻办|李强', title))

            for pattern, info in KEYWORD_MAP.items():
                if re.search(pattern, title) or re.search(pattern, body):
                    weight = 3 if is_top else 2
                    signal_score = info["level"] * weight

                    for sector in info["sectors"]:
                        key = sector
                        all_signals[key]["mentions"] += 1
                        all_signals[key]["score"] += signal_score * info["direction"]
                        all_signals[key]["direction"] = info["direction"]

    return dict(all_signals)


def stock_policy_wind(stock_code, signals):
    """判断单只股票的政策风向"""
    for sector, stocks in SECTOR_STOCK_MAP.items():
        if stock_code in stocks and sector in signals:
            score = signals[sector]["score"]
            if score >= 6:
                return "🟢 强顺风", score
            elif score >= 3:
                return "🟢 顺风", score
            elif score >= 1:
                return "🟡 微顺风", score
            elif score <= -4:
                return "🔴 强逆风", score
            elif score <= -1:
                return "🔴 逆风", score
    return "⚪ 中性", 0


def main():
    parser = argparse.ArgumentParser(description="新闻联播政策信号扫描器")
    parser.add_argument("--days", type=int, default=3, help="扫描最近N天（默认3）")
    parser.add_argument("--stocks", type=str, default="", help="逗号分隔的股票代码，输出政策风向")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    args = parser.parse_args()

    news_files = find_news_files(args.days)

    if not news_files:
        result = {"error": "未找到新闻联播文件", "dir": BASE_DIR}
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print("❌ 未找到新闻联播文件，请设置 NEWS_BROADCAST_DIR 环境变量")
        return

    signals = scan_signals(news_files)

    if args.json:
        output = {
            "files_scanned": len(news_files),
            "date_range": f"{Path(news_files[0]).stem[:10]} ~ {Path(news_files[-1]).stem[:10]}",
            "signals": {k: v for k, v in sorted(signals.items(), key=lambda x: -abs(x[1]["score"]))},
        }
        if args.stocks:
            output["stock_winds"] = {}
            for code in args.stocks.split(","):
                code = code.strip()
                wind, score = stock_policy_wind(code, signals)
                output["stock_winds"][code] = {"wind": wind, "score": score}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 文本输出
    print(f"📡 新闻联播政策信号扫描（最近{args.days}期）")
    print(f"   文件数: {len(news_files)}")
    print(f"   日期范围: {Path(news_files[0]).stem[:10]} ~ {Path(news_files[-1]).stem[:10]}")
    print()

    # 按信号强度排序
    ranked = sorted(signals.items(), key=lambda x: -abs(x[1]["score"]))

    print("【板块政策信号】")
    print(f"{'板块':<12} {'提及':>4} {'信号分':>6} {'方向':<8}")
    print("-" * 32)
    for sector, info in ranked:
        if info["score"] == 0:
            continue
        direction = "🟢 利好" if info["direction"] > 0 else "🔴 利空"
        print(f"{sector:<12} {info['mentions']:>4}次 {info['score']:>+5}  {direction}")

    if args.stocks:
        print()
        print("【持仓/观察池政策风向】")
        print(f"{'代码':<8} {'风向':<12} {'信号分':>6}")
        print("-" * 28)
        for code in args.stocks.split(","):
            code = code.strip()
            wind, score = stock_policy_wind(code, signals)
            print(f"{code:<8} {wind:<12} {score:>+5}")


if __name__ == "__main__":
    main()
