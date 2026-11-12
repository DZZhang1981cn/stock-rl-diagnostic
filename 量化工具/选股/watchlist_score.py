#!/usr/bin/env python3
"""基于实时数据的观察池评分"""
import subprocess
import re

# 新浪实时数据
stocks = {
    "002027": {"name": "分众传媒", "entry": 5.11, "style": "成长"},
    "300628": {"name": "亿联网络", "entry": 37.75, "style": "均衡"},
    "000651": {"name": "格力电器", "entry": 40.59, "style": "防御"},
    "600547": {"name": "山东黄金", "entry": 27.40, "style": "贵金属"},
    "601991": {"name": "大唐发电", "entry": 6.95, "style": "电力"},
    "000975": {"name": "山金国际", "entry": 22.52, "style": "贵金属"},
    "600236": {"name": "桂冠电力", "entry": 12.24, "style": "水电"},
    "600489": {"name": "中金黄金", "entry": 22.11, "style": "贵金属"},
    "600988": {"name": "赤峰黄金", "entry": 38.22, "style": "贵金属"},
    "601168": {"name": "西部矿业", "entry": 36.50, "style": "有色"},
    "300896": {"name": "爱美客", "entry": 108.80, "style": "医美"},
    "600726": {"name": "华电能源", "entry": 6.60, "style": "电力"},
}

# 从腾讯行情获取更多数据
codes = ",".join(f"{'sh' if c.startswith('6') else 'sz'}{c}" for c in stocks)
url = f"http://qt.gtimg.cn/q={codes}"
r = subprocess.run(["curl", "-s", url], capture_output=True)
raw = r.stdout.decode("gbk", errors="replace")

results = []
for code, info in stocks.items():
    prefix = "sh" if code.startswith("6") else "sz"
    m = re.search(rf'{prefix}{code}="([^"]*)"', raw)
    if not m:
        continue
    fields = m.group(1).split("~")
    # 字段: 1=名, 3=现价, 4=昨收, 5=今开, 6=成交量, 31=涨跌额, 32=涨跌幅, 33=最高, 34=最低, 39=PE, 45=总市值
    try:
        name = fields[1]
        price = float(fields[3])
        prev_close = float(fields[4])
        volume = int(fields[6])
        change_pct = float(fields[32])
        high = float(fields[33])
        low = float(fields[34])
        pe = float(fields[39]) if fields[39] else 0
        mkt_cap = float(fields[45]) / 1e8 if fields[45] else 0
    except:
        continue
    
    pct_from_entry = (price - info["entry"]) / info["entry"] * 100
    
    # 评分: 回撤幅度 + PE 合理性 + 今日动能
    score = 0
    
    # 回撤加分 (从高点回撤越多越好, 但要在0%以上)
    if pct_from_entry < 0 and pct_from_entry > -20:
        score += min(abs(pct_from_entry) * 2, 30)  # 回撤 -5% 加 10分, -10% 加 20分
    elif 0 <= pct_from_entry < 5:
        score += 10  # 小幅上涨也可接受
    
    # PE 合理性
    if 0 < pe <= 15:
        score += 25
    elif 15 < pe <= 25:
        score += 20
    elif 25 < pe <= 40:
        score += 10
    
    # 今日动能
    if 0 < change_pct <= 3:
        score += 20  # 温和上涨
    elif 3 < change_pct <= 5:
        score += 15  # 强势但不追
    elif -3 < change_pct <= 0:
        score += 10  # 微跌可关注
    elif change_pct > 5:
        score += 5   # 涨太多追高风险
    
    # 市值适中
    if 50 <= mkt_cap <= 500:
        score += 15
    elif 30 <= mkt_cap < 50 or 500 < mkt_cap <= 1000:
        score += 10
    
    results.append({
        "code": code, "name": name, "price": price, "entry": info["entry"],
        "pct": pct_from_entry, "pe": pe, "today": change_pct,
        "style": info["style"], "score": min(score, 100),
        "mkt_cap": mkt_cap
    })

results.sort(key=lambda x: -x["score"])

print(f"{'排名':<4} {'代码':<8} {'名称':<8} {'加入价':>7} {'现价':>7} {'变动%':>7} {'PE':>6} {'今涨%':>6} {'风格':<8} {'评分':>5} {'建议'}")
print("-" * 100)
for i, r in enumerate(results, 1):
    advice = ""
    if r["score"] >= 70:
        advice = "🟢 可建仓"
    elif r["score"] >= 55:
        advice = "🟡 观察"
    else:
        advice = "🔴 暂缓"
    print(f"{i:<4} {r['code']:<8} {r['name']:<8} {r['entry']:>7.2f} {r['price']:>7.2f} {r['pct']:>+6.1f}% {r['pe']:>5.0f} {r['today']:>+5.1f}% {r['style']:<8} {r['score']:>5.0f} {advice}")
