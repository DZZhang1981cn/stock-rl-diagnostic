#!/usr/bin/env python3
"""观察池技术面扫描 - 2026-08-25 判断增仓/建仓/减仓"""
import subprocess, json, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from predict import predict_stock

# 观察池 (代码, 名称, 加入价)
WATCHLIST = [
    ("002027", "分众传媒", 5.11),
    ("300628", "亿联网络", 37.75),
    ("000651", "格力电器", 40.59),
    ("600547", "山东黄金", 27.40),
    ("000975", "山金国际", 22.52),
    ("600236", "桂冠电力", 12.24),
    ("600489", "中金黄金", 22.11),
    ("600988", "赤峰黄金", 38.22),
    ("601168", "西部矿业", 36.50),
    ("300896", "爱美客", 108.80),
    ("600726", "华电能源", 6.60),
    ("601991", "大唐发电", 6.95),  # 已持仓
]

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '12', url], capture_output=True, text=True, timeout=15)
    return r.stdout

def kline(code, datalen=120):
    sym = f'sh{code}' if code.startswith(('6','68')) else f'sz{code}'
    raw = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={datalen}')
    return json.loads(raw)

def rsi_calc(close, period=14):
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    ag = np.convolve(gain, np.ones(period)/period, mode='full')[:len(close)-period+1]
    al = np.convolve(loss, np.ones(period)/period, mode='full')[:len(close)-period+1]
    rs = ag / (al + 1e-10)
    return 100 - 100 / (1 + rs)

for code, name, join_price in WATCHLIST:
    try:
        kl = kline(code)
        close = np.array([float(d['close']) for d in kl])
        high = np.array([float(d['high']) for d in kl])
        low = np.array([float(d['low']) for d in kl])
        volume = np.array([float(d['volume']) for d in kl])
        n = len(close)
        last = close[-1]
        ma5 = np.mean(close[-5:]); ma20 = np.mean(close[-20:]); ma60 = np.mean(close[-min(n,60):])
        rv = rsi_calc(close); rsi = rv[-1] if len(rv) else 50
        high_60 = np.max(high[-60:]); low_60 = np.min(low[-60:])
        pos_60 = (last - low_60) / (high_60 - low_60) * 100 if high_60 != low_60 else 50
        vol_ratio = volume[-1] / np.mean(volume[-6:-1]) if np.mean(volume[-6:-1]) else 0
        chg_60 = (last / close[-61] - 1) * 100 if n > 61 else 0
        chg_5 = (last / close[-6] - 1) * 100 if n > 6 else 0
        vs_join = (last / join_price - 1) * 100
        pred = predict_stock(close, high, low, volume)
        print(f"\n{name}({code}) 现价{last:.2f} 加入价{join_price} 较加入{vs_join:+.1f}%")
        print(f"  60日{chg_60:+.1f}% 5日{chg_5:+.1f}% RSI={rsi:.0f} 60日位置{pos_60:.0f}% 量比{vol_ratio:.2f}x")
        print(f"  MA5={ma5:.2f} MA20={ma20:.2f} MA60={ma60:.2f}")
        print(f"  预测: {pred['direction']} 综合{pred['composite']:.2f} 5日¥{pred['price_5d']:.2f}")
        if pred['has_oversold']:
            print(f"  🔥超跌: {', '.join(pred['oversold_signals'])}")
    except Exception as e:
        print(f"\n{name}({code}) 失败: {e}")
