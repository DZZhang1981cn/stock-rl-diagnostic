#!/usr/bin/env python3
"""背离诊断：同业对比 - 区分个股α vs 行业β"""
import subprocess, json, sys, os
import numpy as np

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '12', url], capture_output=True, text=True, timeout=15)
    return r.stdout

def kline(code, datalen=70):
    sym = f'sh{code}' if code.startswith(('6','68')) else f'sz{code}'
    raw = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={datalen}')
    return json.loads(raw)

def chg(code, days=60):
    kl = kline(code, days+15)
    close = [float(d['close']) for d in kl]
    if len(close) < days: return None
    return (close[-1]/close[-days-1]-1)*100

groups = {
    "青岛啤酒(600600)": ["600600", "600132", "002461"],   # 啤酒: 青啤/重啤/珠江
    "大唐发电(601991)": ["601991", "600011", "600027", "600795"],  # 电力: 大唐/华能/华电/国电
    "豪威集团(603501)": ["603501", "688981", "688008", "603986"],  # 半导体: 豪威/中芯/澜起/兆易
}

names = {
    "600600":"青岛啤酒","600132":"重庆啤酒","002461":"珠江啤酒",
    "601991":"大唐发电","600011":"华能国际","600027":"华电国际","600795":"国电电力",
    "603501":"豪威集团","688981":"中芯国际","688008":"澜起科技","603986":"兆易创新",
}

for label, codes in groups.items():
    print(f"\n【{label}】近60日涨跌幅对比")
    vals = []
    for c in codes:
        try:
            v = chg(c)
            vals.append((c, v))
            nm = names.get(c, c)
            print(f"  {nm}({c}): {v:+.1f}%" if v is not None else f"  {nm}({c}): 无数据")
        except Exception as e:
            print(f"  {c}: 失败 {e}")
    if len(vals) >= 2:
        target = vals[0][1]
        peers = [v for _, v in vals[1:] if v is not None]
        if target is not None and peers:
            avg = np.mean(peers)
            alpha = target - avg
            print(f"  → 个股{target:+.1f}% vs 同业均值{avg:+.1f}% → α={alpha:+.1f}% ({'个股跑输行业' if alpha<0 else '个股跑赢行业'})")
