#!/usr/bin/env python3
"""2026-07-12 Top7 选股 7天回测 —— 拉取最新收盘价，计算涨跌幅"""
import json, sys, gzip
from urllib.request import Request, urlopen

stocks = [
    ("000938", "sz", "紫光股份", 38.41, 198.2, 1),
    ("000977", "sz", "浪潮信息", 89.52, 163.3, 2),
    ("000063", "sz", "中兴通讯", 40.53, 97.0,  3),
    ("002049", "sz", "紫光国微", 85.83, 59.7,  4),
    ("600025", "sh", "华能水电", 9.62,  53.5,  5),
    ("000301", "sz", "东方盛虹", 12.55, 53.5,  6),
    ("002241", "sz", "歌尔股份", 22.57, 52.8,  7),
]

def fetch_json(url, referer):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": referer,
        "Accept-Encoding": "gzip, deflate",
    })
    with urlopen(req, timeout=15) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")

results = []
print("=" * 70)
print("  2026-07-12 Top7 选股 → 7天回测 (基准日 07-12, 回测日 07-18)")
print("=" * 70)

for code, mkt, name, base_price, score, rank in stocks:
    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/"
        f"json_v2.php/CN_MarketData.getKLineData?"
        f"symbol={mkt}{code}&scale=240&ma=no&datalen=20"
    )
    try:
        data = json.loads(fetch_json(url, "https://finance.sina.com.cn"))
        if data:
            last = data[-1]
            close = float(last['close'])
            change_pct = round((close - base_price) / base_price * 100, 2)
            hit = "✅" if change_pct >= 3.0 else ("📈" if change_pct > 0 else "📉")
            results.append({
                "rank": rank, "code": code, "name": name,
                "base": base_price, "close": close,
                "date": last['day'], "change_pct": change_pct,
                "hit_3pct": change_pct >= 3.0, "up": change_pct > 0,
                "score": score, "hit_mark": hit
            })
            print(f"  #{rank} {name:　<4}({code})  基准¥{base_price:>8.2f} → "
                  f"{last['day']}收盘¥{close:>8.2f}  {hit} {change_pct:+.2f}%")
        else:
            print(f"  #{rank} {name}({code}): K线无数据")
    except Exception as e:
        print(f"  #{rank} {name}({code}): 失败 - {e}")

print("=" * 70)

# 统计
if results:
    up_count = sum(1 for r in results if r['up'])
    down_count = sum(1 for r in results if not r['up'])
    hit_count = sum(1 for r in results if r['hit_3pct'])
    total = len(results)
    
    avg_change = round(sum(r['change_pct'] for r in results) / total, 2)
    
    print(f"\n  📊 汇总统计")
    print(f"  上涨: {up_count}/{total}  下跌: {down_count}/{total}")
    print(f"  ≥3%命中: {hit_count}/{total} = {hit_count/total*100:.1f}%  (历史基准 ~25%)")
    print(f"  平均涨跌: {avg_change:+.2f}%")
    
    # 按得分分组
    high_score = [r for r in results if r['rank'] <= 3]
    low_score = [r for r in results if r['rank'] > 3]
    if high_score:
        hs_avg = round(sum(r['change_pct'] for r in high_score) / len(high_score), 2)
        print(f"  高分组(#1-3)平均: {hs_avg:+.2f}%")
    if low_score:
        ls_avg = round(sum(r['change_pct'] for r in low_score) / len(low_score), 2)
        print(f"  低分组(#4-7)平均: {ls_avg:+.2f}%")
    
    print(f"\n{'='*70}")
    print(f"  📋 按得分排名对比")
    print(f"  {'排名':<6}{'名称':<8}{'得分':>8}{'涨跌幅':>10}{'达标':>6}")
    print(f"  {'-'*40}")
    for r in sorted(results, key=lambda x: x['rank']):
        bar = "█" * max(1, int(abs(r['change_pct']) * 3))
        direction = "▲" if r['change_pct'] > 0 else "▼"
        print(f"  #{r['rank']:<4} {r['name']:<6}  {r['score']:>+7.1f}  "
              f"{r['change_pct']:>+8.2f}% {r['hit_mark']:<4} {direction} {bar}")
    
    # 输出 JSON
    print(f"\n{'='*70}")
    print(json.dumps(results, ensure_ascii=False, indent=2))
