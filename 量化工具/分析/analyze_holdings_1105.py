# -*- coding: utf-8 -*-
"""
持仓分析 2026-11-05 — 读取同花顺实盘后的技术面 + 量能 + 多模型预测
持仓来源：同花顺 CUA 实时读取（2026-11-05 收盘）
"""
import subprocess, json, os, sys
import numpy as np

sys.path.insert(0, os.path.expanduser('~/Desktop/AI工作/量化工具/分析'))
from predict import predict_stock, rsi, bollinger_bands

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '12', url],
                       capture_output=True, timeout=15)
    try:
        return r.stdout.decode('utf-8')
    except Exception:
        return r.stdout.decode('gbk', errors='ignore')

# 当前持仓（同花顺 2026-11-05 收盘实盘）
HOLDINGS = [
    {'code': '600600', 'name': '青岛啤酒', 'sym': 'sh600600', 'shares': 4300,  'cost': 56.652, 'market': '沪'},
    {'code': '601991', 'name': '大唐发电', 'sym': 'sh601991', 'shares': 17800, 'cost': 6.135,  'market': '沪'},
    {'code': '601390', 'name': '中国中铁', 'sym': 'sh601390', 'shares': 12200, 'cost': 4.241,  'market': '沪'},
    {'code': '510330', 'name': '沪深300ETF', 'sym': 'sh510330', 'shares': 12900, 'cost': 4.348, 'market': '沪', 'etf': True},
    {'code': '159352', 'name': 'A500ETF', 'sym': 'sz159352', 'shares': 26800, 'cost': 1.116, 'market': '深', 'etf': True},
]

def fetch_kline(sym, datalen=160):
    url = (f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/'
           f'CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={datalen}')
    return json.loads(curl(url))

def ma(arr, n):
    if len(arr) < n:
        return np.nan
    return float(np.mean(arr[-n:]))

def analyze(code, name, sym, shares, cost, is_etf=False):
    kl = fetch_kline(sym)
    close = np.array([float(d['close']) for d in kl])
    high  = np.array([float(d['high']) for d in kl])
    low   = np.array([float(d['low']) for d in kl])
    vol   = np.array([float(d['volume']) for d in kl])
    days  = [d['day'] for d in kl]
    last = close[-1]
    prev = close[-2]

    # 实时价（腾讯）
    try:
        raw = curl(f'http://qt.gtimg.cn/q={sym}')
        f = raw.split('"')[1].split('~')
        price = float(f[3]); prev_close = float(f[4])
    except Exception:
        price, prev_close = last, prev
    chg = (price / prev_close - 1) * 100

    # 均线
    ma5, ma10, ma20, ma30 = ma(close,5), ma(close,10), ma(close,20), ma(close,30)
    ma60 = ma(close, 60)

    # RSI
    rsi_vals = rsi(close, 14)
    rsi_now = float(rsi_vals[-1]) if len(rsi_vals) > 0 else 50.0

    # 布林带
    bb_up, bb_mid, bb_low = bollinger_bands(close, 20, 2)
    bb_up, bb_mid, bb_low = float(bb_up[-1]), float(bb_mid[-1]), float(bb_low[-1])

    # 量能
    vol_today = float(vol[-1]); vol_yest = float(vol[-2])
    vol_5  = ma(vol, 5); vol_10 = ma(vol, 10); vol_20 = ma(vol, 20); vol_30 = ma(vol, 30)
    vol_ratio_5 = vol_today / vol_5 if vol_5 else 0
    vol_ratio_20 = vol_today / vol_20 if vol_20 else 0
    vol_circ = vol_today / vol_yest if vol_yest else 0
    vol_max_90 = float(np.max(vol[-90:])) if len(vol) >= 90 else float(np.max(vol))
    vol_max_90_day = days[-90:][int(np.argmax(vol[-90:]))] if len(vol) >= 90 else days[-1]

    # 60日位置
    low_60 = float(np.min(low[-60:])); high_60 = float(np.max(high[-60:]))
    pos_60 = (price - low_60) / (high_60 - low_60) * 100 if high_60 != low_60 else 50

    # 近20日区间
    low_20 = float(np.min(low[-20:])); high_20 = float(np.max(high[-20:]))
    dist_low = (price - low_20) / low_20 * 100
    dist_high = (high_20 - price) / price * 100

    # 量价配合
    if chg > 0 and vol_ratio_5 > 1.2:
        vol_price = '放量上涨→走强'
    elif chg > 0 and vol_ratio_5 < 0.8:
        vol_price = '缩量上涨→反弹偏弱'
    elif chg < 0 and vol_ratio_5 > 1.2:
        vol_price = '放量下跌→走弱(抛压大)'
    elif chg < 0 and vol_ratio_5 < 0.8:
        vol_price = '缩量下跌→弱势但抛压衰竭'
    else:
        vol_price = '量价持平'

    # 多模型预测
    pred = predict_stock(close, high, low, vol)

    # 20日波动率 + CI（95%）
    ret_20 = np.diff(close[-21:]) / close[-21:-1]
    sigma = float(np.std(ret_20)) if len(ret_20) > 1 else 0.02
    def ci(horizon):
        w = sigma * np.sqrt(horizon) * 1.96
        return w

    # 盈亏
    mv = price * shares
    pnl = (price - cost) * shares
    pnl_pct = (price / cost - 1) * 100

    # 支撑/阻力
    support = min(ma20, bb_low) if not np.isnan(ma20) else bb_low
    resist = max(ma5, ma10) if not np.isnan(ma5) else bb_up

    return {
        'code': code, 'name': name, 'price': price, 'chg': chg,
        'shares': shares, 'cost': cost, 'mv': mv, 'pnl': pnl, 'pnl_pct': pnl_pct,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma30': ma30, 'ma60': ma60,
        'rsi': rsi_now, 'bb_up': bb_up, 'bb_mid': bb_mid, 'bb_low': bb_low,
        'vol_today': vol_today, 'vol_5': vol_5, 'vol_20': vol_20,
        'vol_ratio_5': vol_ratio_5, 'vol_ratio_20': vol_ratio_20, 'vol_circ': vol_circ,
        'vol_max_90': vol_max_90, 'vol_max_90_day': vol_max_90_day,
        'pos_60': pos_60, 'low_20': low_20, 'high_20': high_20,
        'dist_low': dist_low, 'dist_high': dist_high, 'vol_price': vol_price,
        'composite': pred['composite'], 'direction': pred['direction'],
        'price_1d': pred['price_1d'], 'price_5d': pred['price_5d'],
        'has_oversold': pred['has_oversold'], 'oversold_signals': pred['oversold_signals'],
        'oversold_score': pred['oversold_score'],
        'detail': pred['detail'], 'sigma': sigma,
        'ci_1d': ci(1), 'ci_3d': ci(3), 'ci_5d': ci(5), 'ci_7d': ci(7),
        'support': support, 'resist': resist,
    }

def main():
    results = []
    for h in HOLDINGS:
        try:
            r = analyze(h['code'], h['name'], h['sym'], h['shares'], h['cost'], h.get('etf', False))
            results.append(r)
        except Exception as e:
            print(f'  ⚠️ {h["code"]} {h["name"]}: {e}')
            import traceback; traceback.print_exc()

    # 输出 JSON 供后续整理
    out = {r['code']: r for r in results}
    with open('/tmp/holdings_analysis_1105.json', 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=float)

    # 文本摘要
    print('=' * 78)
    print('  持仓技术面分析 2026-11-05（同花顺实盘）')
    print('=' * 78)
    for r in results:
        print(f"\n【{r['name']} {r['code']}】现价 ¥{r['price']:.3f} ({r['chg']:+.2f}%)")
        print(f"  持仓 {r['shares']} 股 | 成本 ¥{r['cost']:.3f} | 市值 ¥{r['mv']:,.0f} | 盈亏 {r['pnl']:+,.0f} ({r['pnl_pct']:+.2f}%)")
        print(f"  MA5={r['ma5']:.3f} MA10={r['ma10']:.3f} MA20={r['ma20']:.3f} MA60={r['ma60']:.3f} | RSI={r['rsi']:.0f} | 60日位置={r['pos_60']:.0f}%")
        print(f"  布林: 上{r['bb_up']:.3f} 中{r['bb_mid']:.3f} 下{r['bb_low']:.3f}")
        print(f"  量能: 今日{r['vol_today']/1e4:.0f}万手 | 量比5日{r['vol_ratio_5']:.2f}x 20日{r['vol_ratio_20']:.2f}x 环比{r['vol_circ']:.2f}x | 90日最大量日={r['vol_max_90_day']}")
        print(f"  量价: {r['vol_price']}")
        print(f"  预测: 综合{r['composite']:.2f} {r['direction']} | 1日¥{r['price_1d']:.3f} 5日¥{r['price_5d']:.3f}")
        print(f"  95%CI(1日±{r['ci_1d']*100:.1f}% / 3日±{r['ci_3d']*100:.1f}% / 5日±{r['ci_5d']*100:.1f}% / 7日±{r['ci_7d']*100:.1f}%)")
        if r['has_oversold']:
            print(f"  🔥 超跌信号({r['oversold_score']}/25): {', '.join(r['oversold_signals'])}")
        d = r['detail']
        print(f"  维度: MA趋势{d['trend']['score']}/25 动量{d['momentum_5d']['score']}/25 回归{d['regression']['score']}/20 加速{d['acceleration']['score']}/15 线性{d['linear']['score']}/15")
        print(f"  支撑≈¥{r['support']:.3f} 阻力≈¥{r['resist']:.3f} | 20日区间[{r['low_20']:.3f},{r['high_20']:.3f}]")

    print('\n' + '=' * 78)
    print('  完成，结果已存 /tmp/holdings_analysis_1105.json')

if __name__ == '__main__':
    main()
