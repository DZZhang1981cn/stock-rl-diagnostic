# -*- coding: utf-8 -*-
"""
手工多模型预测 v2 — 新增超跌反弹维度
用法: from predict import predict_stock; result = predict_stock(ohlcv_df, mkt_df)
"""
import numpy as np

def rsi(close, period=14):
    """计算 RSI"""
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.convolve(gain, np.ones(period)/period, mode='full')[:len(close)-period+1]
    avg_loss = np.convolve(loss, np.ones(period)/period, mode='full')[:len(close)-period+1]
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - 100 / (1 + rs)

def bollinger_bands(close, period=20, k=2):
    """布林带"""
    ma = np.convolve(close, np.ones(period)/period, mode='valid')
    # rolling std
    std = []
    for i in range(period-1, len(close)):
        std.append(np.std(close[i-period+1:i+1]))
    std = np.array(std)
    return ma + k*std, ma, ma - k*std  # upper, mid, lower

def predict_stock(close, high, low, volume, market_close=None):
    """
    多模型加权综合预测
    close/high/low/volume: numpy arrays, 至少60个数据点
    market_close: 大盘收盘价(可选), len=len(close)
    
    返回: dict with 'direction', 'price_1d', 'price_5d', 'score', 'signals'
    """
    n = len(close)
    last = close[-1]
    
    # =============================================
    # 1. MA趋势 (25%)
    # =============================================
    ma5 = np.mean(close[-5:])
    ma10 = np.mean(close[-10:])
    ma20 = np.mean(close[-20:])
    ma60 = np.mean(close[-min(n,60):])
    
    trend_up = ma5 > ma10 > ma20
    trend_score = 0
    if trend_up:              trend_score = 25
    elif ma5 > ma10:          trend_score = 18
    elif ma5 > ma20:          trend_score = 10
    else:                     trend_score = 0
    
    trend_signal = 'bullish' if trend_up else ('neutral' if ma5 > ma20 else 'bearish')
    
    # =============================================
    # 2. 5日动量 (25%)
    # =============================================
    mom_5d = (close[-1] / close[max(0, n-6)] - 1) * 100
    mom_score = 0
    if mom_5d > 5:        mom_score = 25
    elif mom_5d > 2:      mom_score = 20
    elif mom_5d > 0:      mom_score = 12
    elif mom_5d > -2:     mom_score = 6
    else:                 mom_score = 0
    
    # =============================================
    # 3. 均值回归 (20%)
    # =============================================
    bias_ma20 = (last / ma20 - 1) * 100
    reg_score = 0
    if bias_ma20 > 10:              reg_score = 0   # 严重偏离，回归压力大
    elif bias_ma20 > 5:             reg_score = 5   # 偏高压
    elif -2 < bias_ma20 < 2:        reg_score = 20  # 正常区间，无压力
    elif -5 < bias_ma20 <= -2:      reg_score = 15  # 偏低，但不过度
    elif bias_ma20 <= -5:           reg_score = 10  # 偏低，回归向上
    else:                           reg_score = 10
    
    # =============================================
    # 4. 加速度 (15%)
    # =============================================
    if n >= 10:
        mom_5d_before = (close[n-6] / close[max(0, n-11)] - 1) * 100
        accel = mom_5d - mom_5d_before
    else:
        accel = 0
    accel_score = 0
    if accel > 3:           accel_score = 15
    elif accel > 0:         accel_score = 10
    elif accel > -3:        accel_score = 7
    else:                   accel_score = 0
    
    # =============================================
    # 5. 线性回归 (15%)
    # =============================================
    if n >= 15:
        x = np.arange(15)
        y = close[-15:]
        slope = np.polyfit(x, y, 1)[0] / last * 100  # % per day
    else:
        slope = bias_ma20 / max(n, 20)
    lin_score = 0
    if slope > 0.3:         lin_score = 15
    elif slope > 0:         lin_score = 10
    elif slope > -0.3:      lin_score = 5
    else:                   lin_score = 0
    
    # =============================================
    # 6. 🆕 超跌反弹 (权重 = max(20, 替换原有权重))
    # =============================================
    oversold_score = 0
    oversold_signals = []
    
    # 6a. RSI(14) 超卖
    rsi_vals = rsi(close, 14)
    rsi_now = rsi_vals[-1] if len(rsi_vals) > 0 else 50
    if rsi_now < 20:
        oversold_score += 8
        oversold_signals.append(f'RSI={rsi_now:.0f}超卖')
    elif rsi_now < 30:
        oversold_score += 5
        oversold_signals.append(f'RSI={rsi_now:.0f}偏低')
    elif rsi_now < 40:
        oversold_score += 2
    
    # 6b. 布林带下轨
    if n >= 20:
        bb_upper, bb_mid, bb_lower = bollinger_bands(close, 20, 2)
        bb_lower_now = bb_lower[-1]
        if last < bb_lower_now:
            oversold_score += 5
            oversold_signals.append('跌破布林下轨')
        elif last < bb_mid[-1] * 0.95:
            oversold_score += 2
            oversold_signals.append('布林下轨附近')
    
    # 6c. MA60 乖离率
    bias_ma60 = (last / ma60 - 1) * 100
    if bias_ma60 < -20:
        oversold_score += 7
        oversold_signals.append(f'距MA60乖离{bias_ma60:.0f}%')
    elif bias_ma60 < -15:
        oversold_score += 5
        oversold_signals.append(f'距MA60乖离{bias_ma60:.0f}%')
    elif bias_ma60 < -10:
        oversold_score += 3
        oversold_signals.append(f'距MA60乖离{bias_ma60:.0f}%')
    elif bias_ma60 < -5:
        oversold_score += 1
    
    # 6d. 恐慌放量（底部巨量出清）
    if n >= 20:
        vol_ma20 = np.mean(volume[-20:])
        vol_now = volume[-1]
        vol_ratio = vol_now / vol_ma20
        # 60日位置
        low_60d = np.min(low[-min(n,60):])
        high_60d = np.max(high[-min(n,60):])
        pos_60d = (last - low_60d) / (high_60d - low_60d) * 100 if high_60d != low_60d else 50
        
        if pos_60d < 15 and vol_ratio > 1.5:
            oversold_score += 5
            oversold_signals.append(f'底部放量({pos_60d:.0f}%位,量比{vol_ratio:.1f}x)')
        elif pos_60d < 25 and vol_ratio > 1.2:
            oversold_score += 3
            oversold_signals.append(f'低位放量({pos_60d:.0f}%位,量比{vol_ratio:.1f}x)')
    
    oversold_score = min(oversold_score, 25)  # 上限25分
    has_oversold = oversold_score >= 5
    
    # =============================================
    # 加权综合 (6维度)
    # 当超跌信号强时，增大其权重
    # =============================================
    if has_oversold:
        # 超跌模式下，降低趋势/动量权重，提高超跌权重
        total = (trend_score * 0.15 + mom_score * 0.15 + reg_score * 0.15 +
                 accel_score * 0.10 + lin_score * 0.10 + oversold_score * 0.35)
        max_possible = 25*0.15 + 25*0.15 + 20*0.15 + 15*0.10 + 15*0.10 + 25*0.35
    else:
        total = (trend_score * 0.25 + mom_score * 0.25 + reg_score * 0.20 +
                 accel_score * 0.15 + lin_score * 0.15 + oversold_score * 0.0)
        max_possible = 25*0.25 + 25*0.25 + 20*0.20 + 15*0.15 + 15*0.15
    
    composite = total / max_possible if max_possible > 0 else 0.5
    
    # =============================================
    # 价格预测
    # =============================================
    if has_oversold:
        # 超跌反弹模式：短期反弹 + 中期回归MA20
        rebound_pct = min(oversold_score / 25 * 0.08, 0.08)  # 最高8%反弹
        price_1d = last * (1 + rebound_pct * 0.2)  # 首日温和反弹
        price_5d = min(last * (1 + rebound_pct), ma20 * 1.02)  # 5日向MA20回归
    else:
        # 正常模式
        trend_pct = (trend_score / 25) * 0.02 * 5  # 5天趋势幅度
        mom_pct = mom_5d / 100 * 0.3  # 动量延续30%
        price_1d = last * (1 + max(trend_pct, mom_pct) * 0.2)
        price_5d = last * (1 + max(trend_pct, mom_pct))
    
    # =============================================
    # 方向判断
    # =============================================
    if composite > 0.65:       direction = '📈 看涨'
    elif composite > 0.50:     direction = '↗️ 偏多'
    elif composite > 0.40:     direction = '➡️ 震荡'
    elif composite > 0.30:     direction = '↘️ 偏空'
    else:                      direction = '📉 看空'
    
    return {
        'direction': direction,
        'composite': composite,
        'price_1d': price_1d,
        'price_5d': price_5d,
        'has_oversold': has_oversold,
        'oversold_score': oversold_score,
        'oversold_signals': oversold_signals,
        'detail': {
            'trend': {'score': trend_score, 'signal': trend_signal, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20},
            'momentum_5d': {'score': mom_score, 'value': mom_5d},
            'regression': {'score': reg_score, 'bias_ma20': bias_ma20, 'bias_ma60': bias_ma60},
            'acceleration': {'score': accel_score, 'value': accel},
            'linear': {'score': lin_score, 'slope': slope},
            'oversold': {'score': oversold_score, 'rsi': rsi_now, 'pos_60d': pos_60d if n>=20 else 50},
        }
    }


# ===== 命令行入口 =====
if __name__ == '__main__':
    import subprocess, json, sys
    
    def curl(url):
        r = subprocess.run(['curl','-s','-L','--max-time','10',url],
                           capture_output=True, text=True, timeout=12)
        return r.stdout
    
    code = sys.argv[1] if len(sys.argv) > 1 else '600415'
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=200'))
    
    close = np.array([float(d['close']) for d in kl])
    high  = np.array([float(d['high']) for d in kl])
    low   = np.array([float(d['low']) for d in kl])
    volume = np.array([float(d['volume']) for d in kl])
    
    result = predict_stock(close, high, low, volume)
    
    print(f"\n{'='*50}")
    print(f"  {code} 预测结果")
    print(f"{'='*50}")
    print(f"  当前价: ¥{close[-1]:.2f}")
    print(f"  综合评分: {result['composite']:.2f}")
    print(f"  方向: {result['direction']}")
    print(f"  1日预测: ¥{result['price_1d']:.2f}")
    print(f"  5日预测: ¥{result['price_5d']:.2f}")
    if result['has_oversold']:
        print(f"  🔥 超跌反弹信号: {', '.join(result['oversold_signals'])}")
        print(f"     超跌得分: {result['oversold_score']}/25")
    print(f"\n  维度详情:")
    d = result['detail']
    print(f"  MA趋势:  {d['trend']['score']}/25  ({d['trend']['signal']}, MA5={d['trend']['ma5']:.2f})")
    print(f"  5日动量:  {d['momentum_5d']['score']}/25  ({d['momentum_5d']['value']:+.1f}%)")
    print(f"  均值回归: {d['regression']['score']}/20  (MA20偏差{d['regression']['bias_ma20']:+.1f}%)")
    print(f"  加速度:   {d['acceleration']['score']}/15  ({d['acceleration']['value']:+.1f}%)")
    print(f"  线性:     {d['linear']['score']}/15  ({d['linear']['slope']:+.3f}%/天)")
    print(f"  超跌:     {d['oversold']['score']}/25  (RSI={d['oversold']['rsi']:.0f}, 60日位置={d['oversold']['pos_60d']:.0f}%)")
