#!/usr/bin/env python3
"""持仓批量分析 - 2026-08-25 技术指标 + 量能 + 多模型预测"""
import subprocess, json, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from predict import predict_stock

# (代码, 名称, 数量, 成本价, 现价)  现价来自腾讯实时报价 08-25 收盘
HOLDINGS = [
    ("600029", "南方航空", 5200, 5.561, 5.060),
    ("600377", "宁沪高速", 1500, 12.121, 12.250),
    ("600415", "小商品城", 4800, 12.531, 12.170),
    ("600600", "青岛啤酒", 4300, 56.652, 51.240),
    ("601991", "大唐发电", 16800, 6.154, 5.900),
    ("603501", "豪威集团", 500, 83.781, 85.550),
]

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '12', url],
                       capture_output=True, text=True, timeout=15)
    return r.stdout

def get_kline(code, datalen=120):
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    raw = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={datalen}')
    return json.loads(raw)

def rsi_calc(close, period=14):
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.convolve(gain, np.ones(period)/period, mode='full')[:len(close)-period+1]
    avg_loss = np.convolve(loss, np.ones(period)/period, mode='full')[:len(close)-period+1]
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - 100 / (1 + rs)

def analyze(code, name, qty, cost, last):
    kl = get_kline(code)
    close = np.array([float(d['close']) for d in kl])
    high = np.array([float(d['high']) for d in kl])
    low = np.array([float(d['low']) for d in kl])
    volume = np.array([float(d['volume']) for d in kl])

    pred = predict_stock(close, high, low, volume)

    n = len(close)
    ma5 = np.mean(close[-5:])
    ma10 = np.mean(close[-10:])
    ma20 = np.mean(close[-20:])
    ma60 = np.mean(close[-min(n,60):])

    # 量能
    vol_today = volume[-1]
    vol_ma5 = np.mean(volume[-6:-1])
    vol_ma20 = np.mean(volume[-21:-1])
    vol_ratio_5 = vol_today / vol_ma5 if vol_ma5 else 0
    vol_ratio_20 = vol_today / vol_ma20 if vol_ma20 else 0

    # 关键位
    high_20 = np.max(high[-20:])
    low_20 = np.min(low[-20:])
    high_60 = np.max(high[-60:])
    low_60 = np.min(low[-60:])
    pos_20 = (last - low_20) / (high_20 - low_20) * 100 if high_20 != low_20 else 50

    # RSI
    rv = rsi_calc(close)
    rsi_now = rv[-1] if len(rv) else 50

    # 盈亏
    market_val = qty * last
    cost_val = qty * cost
    pnl = market_val - cost_val
    pnl_pct = pnl / cost_val * 100

    return {
        'code': code, 'name': name, 'qty': qty, 'cost': cost, 'last': last,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'vol_ratio_5': vol_ratio_5, 'vol_ratio_20': vol_ratio_20,
        'high_20': high_20, 'low_20': low_20, 'high_60': high_60, 'low_60': low_60,
        'pos_20': pos_20, 'rsi': rsi_now,
        'market_val': market_val, 'pnl': pnl, 'pnl_pct': pnl_pct,
        'pred': pred,
    }

if __name__ == '__main__':
    tot_mv = 0; tot_cost = 0; tot_pnl = 0
    for code, name, qty, cost, last in HOLDINGS:
        try:
            r = analyze(code, name, qty, cost, last)
            d = r['pred']
            tot_mv += r['market_val']; tot_cost += qty*cost; tot_pnl += r['pnl']
            print(f"\n{'='*64}")
            print(f"{name}({code})  {qty}股  成本{cost}  现价{last}")
            print(f"  市值{r['market_val']:,.0f}  浮亏{r['pnl']:+,.0f} ({r['pnl_pct']:+.2f}%)")
            print(f"  MA5={r['ma5']:.2f} MA10={r['ma10']:.2f} MA20={r['ma20']:.2f} MA60={r['ma60']:.2f}")
            print(f"  量比: vs5日={r['vol_ratio_5']:.2f}x vs20日={r['vol_ratio_20']:.2f}x  RSI={r['rsi']:.0f}")
            print(f"  20日区间[{r['low_20']:.2f},{r['high_20']:.2f}] 位置{r['pos_20']:.0f}%  60日区间[{r['low_60']:.2f},{r['high_60']:.2f}]")
            print(f"  预测: {d['direction']} 综合{d['composite']:.2f}  1日¥{d['price_1d']:.2f}  5日¥{d['price_5d']:.2f}")
            if d['has_oversold']:
                print(f"  🔥超跌反弹: {', '.join(d['oversold_signals'])}")
            det = d['detail']
            print(f"  维度: 趋势{det['trend']['score']}/25 动量{det['momentum_5d']['score']}/25 回归{det['regression']['score']}/20 加速{det['acceleration']['score']}/15 线性{det['linear']['score']}/15 超跌{det['oversold']['score']}/25")
            print(f"  RSI={det['oversold']['rsi']:.0f} 60日位置={det['oversold']['pos_60d']:.0f}%  MA20偏差{det['regression']['bias_ma20']:+.1f}%")
        except Exception as e:
            print(f"\n{name}({code}) 分析失败: {e}")
    print(f"\n{'='*64}")
    print(f"合计: 市值{tot_mv:,.0f}  成本{tot_cost:,.0f}  浮亏{tot_pnl:+,.0f} ({tot_pnl/tot_cost*100:+.2f}%)")
