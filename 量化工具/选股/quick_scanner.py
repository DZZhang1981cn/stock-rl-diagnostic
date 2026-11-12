#!/usr/bin/env python3
"""全市场多因子选股扫描 - 基于东方财富API"""
import subprocess
import json
import re
import sys

# === 拉取全市场涨幅前200 ===
def fetch_top200():
    url = "http://push2.eastmoney.com/api/qt/clist/get?fid=f3&po=1&pz=200&pn=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
    r = subprocess.run(["curl", "-s", "-L", "--max-time", "20", url], capture_output=True, text=True)
    if r.returncode != 0:
        print("网络请求失败")
        sys.exit(1)
    try:
        data = json.loads(r.stdout)
        return data.get("data", {}).get("diff", [])
    except:
        print("JSON解析失败")
        sys.exit(1)

def score_stock(s):
    try:
        code = s.get("f12", "")
        name = s.get("f14", "")
        price = float(s.get("f2", 0))
        pct_5d = float(s.get("f8", 0) or 0)     # 5日涨幅
        pct_today = float(s.get("f3", 0) or 0)   # 今日涨幅
        vol_ratio = float(s.get("f10", 0) or 0)  # 量比
        turnover = float(s.get("f15", 0) or 0)   # 换手率
        pe = float(s.get("f9", 0) or 0)          # PE
        mkt_cap = float(s.get("f20", 0) or 0)    # 总市值(亿)
        
        # === 过滤 ===
        if pe <= 0 or pe > 500:
            return None
        if pct_today <= 0:
            return None
        if vol_ratio < 0.8:
            return None
        if turnover < 1.5 or turnover > 25:
            return None
        if mkt_cap < 30 or mkt_cap > 2000:
            return None
        
        # === 评分 ===
        # 1. 动量 (30分) - 5日涨幅
        momentum = min(pct_5d / 30 * 30, 30) if pct_5d > 0 else 0
        
        # 2. 持续力 (15分) - 今日涨幅 vs 5日均速
        avg_daily = pct_5d / 5 if pct_5d > 0 else 0
        sustain = min(pct_today / max(avg_daily, 0.1) * 15, 15) if avg_daily > 0 else 7
        
        # 3. 量能 (15分) - 量比 1.2-2.5 满分
        if 1.2 <= vol_ratio <= 2.5:
            volume_score = 15
        elif 0.8 <= vol_ratio < 1.2:
            volume_score = 10
        elif 2.5 < vol_ratio <= 3.5:
            volume_score = 10
        else:
            volume_score = 5
        
        # 4. 换手质量 (10分) - 3%-15% 满分
        if 3 <= turnover <= 15:
            turnover_score = 10
        elif 1.5 <= turnover < 3:
            turnover_score = 7
        elif 15 < turnover <= 25:
            turnover_score = 7
        else:
            turnover_score = 3
        
        # 5. PE合理性 (15分) - 5-20 满分
        if 5 <= pe <= 20:
            pe_score = 15
        elif 20 < pe <= 40:
            pe_score = 12
        elif 40 < pe <= 80:
            pe_score = 8
        elif 80 < pe <= 150:
            pe_score = 5
        else:
            pe_score = 3
        
        # 6. 市值适中 (15分) - 50-500亿 满分
        if 50 <= mkt_cap <= 500:
            cap_score = 15
        elif 30 <= mkt_cap < 50:
            cap_score = 10
        elif 500 < mkt_cap <= 1000:
            cap_score = 12
        elif 1000 < mkt_cap <= 2000:
            cap_score = 8
        else:
            cap_score = 5
        
        total = momentum + sustain + volume_score + turnover_score + pe_score + cap_score
        
        return {
            "code": code,
            "name": name,
            "price": price,
            "pct_5d": pct_5d,
            "pct_today": pct_today,
            "vol_ratio": vol_ratio,
            "turnover": turnover,
            "pe": pe,
            "mkt_cap": mkt_cap,
            "score": round(total, 1),
            "momentum": round(momentum, 1),
            "sustain": round(sustain, 1),
            "volume": volume_score,
            "turn": turnover_score,
            "pe_s": pe_score,
            "cap": cap_score,
        }
    except:
        return None

def main():
    print("=== 全市场选股扫描 ===\n")
    stocks = fetch_top200()
    print(f"拉取 {len(stocks)} 只涨幅领跑股\n")
    
    results = []
    for s in stocks:
        r = score_stock(s)
        if r:
            results.append(r)
    
    results.sort(key=lambda x: -x["score"])
    top = results[:15]
    
    # 输出
    print(f"{'排名':<4} {'代码':<8} {'名称':<8} {'现价':>6} {'5日%':>7} {'量比':>5} {'换手%':>6} {'PE':>6} {'市值':>7} {'得分':>5}")
    print("-" * 80)
    for i, r in enumerate(top, 1):
        print(f"{i:<4} {r['code']:<8} {r['name']:<8} {r['price']:>6.2f} {r['pct_5d']:>+6.1f}% {r['vol_ratio']:>5.1f} {r['turnover']:>5.1f}% {r['pe']:>5.0f} {r['mkt_cap']:>6.0f}亿 {r['score']:>5.1f}")
    
    print(f"\n评分明细:")
    for i, r in enumerate(top[:10], 1):
        print(f"  #{i} {r['name']}({r['code']}) {r['score']}分 | 动量{r['momentum']} 持续{r['sustain']} 量能{r['volume']} 换手{r['turn']} PE{r['pe_s']} 市值{r['cap']}")

if __name__ == "__main__":
    main()
