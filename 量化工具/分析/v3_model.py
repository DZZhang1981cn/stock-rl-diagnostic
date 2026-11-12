#!/usr/bin/env python3
"""
v3 预测模型 — 持久化版
可被外部调用：python3 v3_model.py predict → 输出三只票预测
             python3 v3_model.py review   → 复盘上次预测
"""
import subprocess, json, math, os, sys
from datetime import datetime

MODEL_FILE = os.path.expanduser('~/Desktop/AI工作/v3_model_weights.json')
DATA_CACHE = os.path.expanduser('~/Desktop/AI工作/v3_data_cache.json')

# ===== 方法定义 =====
LOOKBACK = 20; WARMUP = 80

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '30',
        '-H', 'User-Agent: Mozilla/5.0', url],
        capture_output=True, text=True, timeout=35)
    return json.loads(r.stdout)

def lt(w): 
    n=len(w);xm=(n-1)/2;ym=sum(w)/n
    n2=sum((i-xm)*(w[i]-ym) for i in range(n));d=sum((i-xm)**2 for i in range(n))
    return ym+(n2/d if d else 0)*n
def mom(w): return w[-1]+(w[-1]-w[-6])*0.2+(w[-1]-w[-2])*0.3
def mr(w): m=sum(w[-10:])/10; return w[-1]+(m-w[-1])*0.3
def mf(w,feats): return w[-1]*(1+feats.get('market_ret_5',0)*feats.get('beta',1))
def ap(w,feats): return w[-1]*(1+feats.get('alpha_5',0)*1.5)
def sr_m(w,feats): return w[-1]*(1+feats.get('sector_vs_market',0)*0.5)
def ic(w,feats): 
    if feats.get('independent')=='stock_driven': return w[-1]*(1+feats.get('alpha_5',0)*1.2)
    return w[-1]

METHODS = {
    '线性趋势': lambda w,f: lt(w),
    '动量': lambda w,f: mom(w),
    '均值回归': lambda w,f: mr(w),
    '跟随大盘': mf,
    'α延续': ap,
    '行业轮动': sr_m,
    '独立延续': ic,
}

# ===== 数据加载与对齐 =====
def load_all_data():
    """拉取并缓存全量数据"""
    if os.path.exists(DATA_CACHE):
        with open(DATA_CACHE) as f:
            cache = json.load(f)
        age_h = (os.path.getmtime(DATA_CACHE) - datetime.now().timestamp()) / 3600
        if abs(age_h) < 4:  # 4小时内缓存有效
            return cache
    
    print("  拉取全量数据...")
    stocks = {}
    for sym in ['sh600415','sh601212','sh600029']:
        code = sym.replace('sh','')
        stocks[code] = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1500')
    
    market = curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=1500')
    
    sector_data = {}
    for sname, scode in [('商业百货','sh000827'),('有色金属','sh000819')]:
        try: sector_data[sname] = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={scode}&scale=240&ma=no&datalen=1500')
        except: sector_data[sname] = market
    sector_data['民航机场'] = market
    
    data = {'stocks': stocks, 'market': market, 'sectors': sector_data}
    with open(DATA_CACHE, 'w') as f:
        # Convert to serializable format
        json.dump(data, f, ensure_ascii=False)
    return data

# ===== 特征计算 =====
def build_aligned(data, code):
    sectors = {'600415':'商业百货','601212':'有色金属','600029':'民航机场'}
    kl = data['stocks'][code]
    market = data['market']
    sec_kl = data['sectors'][sectors[code]]
    
    closes = [float(d['close']) for d in kl]
    highs = [float(d['high']) for d in kl]
    lows = [float(d['low']) for d in kl]
    volumes = [float(d['volume']) for d in kl]
    days = [d['day'] for d in kl]
    
    mkt_closes = [float(d['close']) for d in market]
    mkt_days = [d['day'] for d in market]
    sec_closes = [float(d['close']) for d in sec_kl]
    sec_days = [d['day'] for d in sec_kl]
    
    mkt_map = {d:c for d,c in zip(mkt_days, mkt_closes)}
    sec_map = {d:c for d,c in zip(sec_days, sec_closes)}
    
    mc = [mkt_map.get(d) for d in days]
    sc = [sec_map.get(d) for d in days]
    
    for arr in [mc, sc]:
        last = None
        for i in range(len(arr)):
            if arr[i] is None: arr[i] = last if last is not None else closes[i]
            else: last = arr[i]
    
    return closes, highs, lows, volumes, days, mc, sc

def compute_features(closes, mc, sc, i):
    start = max(0, i-LOOKBACK); end = i
    if end - start < 5: return {}
    
    sr = [(closes[j]-closes[j-1])/max(closes[j-1],0.01) for j in range(start+1, end+1)]
    mr_vals = [(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(start+1, end+1)]
    xr = [(sc[j]-sc[j-1])/max(sc[j-1],0.01) for j in range(start+1, end+1)]
    
    n = len(sr); sm=sum(sr)/n; mm=sum(mr_vals)/n
    cov=sum((sr[j]-sm)*(mr_vals[j]-mm) for j in range(n))/n
    var_m=sum((mr_vals[j]-mm)**2 for j in range(n))/n
    beta=cov/var_m if var_m>0 else 1
    
    sr5=(closes[i]/max(closes[max(0,i-5)],0.01)-1)
    mr5=(mc[i]/max(mc[max(0,i-5)],0.01)-1)
    xr5=(sc[i]/max(sc[max(0,i-5)],0.01)-1)
    alpha5=sr5-beta*mr5
    
    if abs(sr5)>0.03:
        independent='stock_driven' if abs(alpha5)>abs(beta*mr5)*0.5 else 'market_driven'
    else:
        independent='low_vol'
    
    return {
        'beta':beta,'alpha_5':alpha5,'independent':independent,
        'market_ret_5':mr5,'sector_ret_5':xr5,'sector_vs_market':xr5-mr5,
    }

def classify_regime(closes, highs, lows, i, feats):
    c = closes[max(0,i-60):i+1]
    if len(c)<30: return 'unknown'
    ma20=sum(c[-20:])/20
    part = c[max(0,len(c)-40):len(c)-20]
    ma20_20d=sum(part)/max(len(part),1)
    trend=(ma20-ma20_20d)/ma20_20d*100
    
    if trend>3: base='strong_bull'
    elif trend>0: base='weak_bull'
    elif trend<-3: base='strong_bear'
    elif trend<0: base='weak_bear'
    else: base='sideways'
    
    ind=feats.get('independent',''); alpha=feats.get('alpha_5',0)
    if ind=='stock_driven':
        base='alpha_up' if alpha>0.02 else 'alpha_down'
    return base

# ===== 训练 =====
def train(data, code):
    names = {'600415':'小商品城','601212':'白银有色','600029':'南方航空'}
    closes, highs, lows, volumes, days, mc, sc = build_aligned(data, code)
    total = len(closes)
    
    all_p = []
    for i in range(WARMUP, total):
        w = closes[i-LOOKBACK:i]
        actual = closes[i]; prev = closes[i-1]
        feats = compute_features(closes, mc, sc, i)
        reg = classify_regime(closes, highs, lows, i, feats)
        preds = {}
        for mn, fn in METHODS.items():
            try: preds[mn] = fn(w, feats)
            except: preds[mn] = w[-1]
        all_p.append({'actual':actual,'prev':prev,'preds':preds,'regime':reg})
    
    n = len(all_p)
    
    # Per-regime stats
    rs = {}
    for p in all_p:
        r = p['regime']
        if r not in rs: rs[r] = {'c':0,'m':{m:{'dc':0,'t':0,'ae':[]} for m in METHODS}}
        rs[r]['c'] += 1
        ad = 1 if p['actual']>p['prev'] else(-1 if p['actual']<p['prev'] else 0)
        for mn in METHODS:
            ms = rs[r]['m'][mn]
            pd_ = 1 if p['preds'][mn]>p['prev'] else(-1 if p['preds'][mn]<p['prev'] else 0)
            if ad==pd_: ms['dc']+=1
            ms['t']+=1; ms['ae'].append(abs(p['preds'][mn]-p['actual']))
    
    # Weights per regime
    rw = {}
    for r, rrs in rs.items():
        wgt = {}; tw = 0
        for mn in METHODS:
            s = rrs['m'][mn]; acc = s['dc']/max(s['t'],1)*100
            w = max(acc-47, 1); wgt[mn] = w; tw += w
        for mn in wgt: wgt[mn] /= max(tw, 0.01)
        rw[r] = wgt
    
    # Evaluate
    fdc = 0; ft = 0; fe = []
    for p in all_p:
        r = p['regime']; cw = rw.get(r, {m:1/len(METHODS) for m in METHODS})
        wp = sum(p['preds'][m]*cw[m] for m in METHODS)
        ad = 1 if p['actual']>p['prev'] else(-1 if p['actual']<p['prev'] else 0)
        pd_ = 1 if wp>p['prev'] else(-1 if wp<p['prev'] else 0)
        if ad==pd_: fdc+=1
        ft+=1; fe.append(abs(wp-p['actual']))
    
    fa = fdc/ft*100
    se = sorted(fe)
    ci68 = se[int(len(se)*0.68)]; ci90 = se[int(len(se)*0.9)]
    
    return {
        'name': names[code],
        'regime_weights': rw,
        'dir_acc': fa,
        'ci68': ci68,
        'ci90': ci90,
        'n': ft,
        'last_data_day': days[-1],
    }

# ===== 预测 =====
def predict(data, model, code):
    closes, highs, lows, volumes, days, mc, sc = build_aligned(data, code)
    i = len(closes) - 1
    w = closes[-LOOKBACK:]
    feats = compute_features(closes, mc, sc, i)
    reg = classify_regime(closes, highs, lows, i, feats)
    
    preds = {}
    for mn, fn in METHODS.items():
        try: preds[mn] = fn(w, feats)
        except: preds[mn] = w[-1]
    
    rw = model['regime_weights']
    cw = rw.get(reg, {m:1/len(METHODS) for m in METHODS})
    wp = sum(preds[m]*cw[m] for m in METHODS)
    
    return {
        'price': wp,
        'regime': reg,
        'ci68': model['ci68'],
        'lo': wp - model['ci68'],
        'hi': wp + model['ci68'],
        'beta': feats.get('beta', 1),
        'alpha': feats.get('alpha_5', 0),
        'prev_close': closes[-1],
        'weights': {m: cw[m] for m in sorted(cw, key=cw.get, reverse=True)[:3]},
    }

# ===== 主入口 =====
if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'predict'
    
    data = load_all_data()
    
    if cmd == 'train':
        print("=" * 60)
        print("  v3 模型训练")
        print("=" * 60)
        models = {}
        for code in ['600415','601212','600029']:
            print(f"  训练 {code}...")
            m = train(data, code)
            models[code] = m
            print(f"    {m['name']}: {m['dir_acc']:.1f}% (N={m['n']})")
        
        with open(MODEL_FILE, 'w') as f:
            json.dump(models, f, ensure_ascii=False, indent=2)
        print(f"\n  ✅ 模型已保存至 {MODEL_FILE}")
    
    elif cmd == 'predict':
        if not os.path.exists(MODEL_FILE):
            print("  模型文件不存在，先训练...")
            models = {}
            for code in ['600415','601212','600029']:
                models[code] = train(data, code)
            with open(MODEL_FILE, 'w') as f:
                json.dump(models, f, ensure_ascii=False, indent=2)
        else:
            with open(MODEL_FILE) as f:
                models = json.load(f)
        
        print("=" * 60)
        print(f"  v3 预测 — {data['stocks']['600415'][-1]['day']}")
        print("=" * 60)
        for code in ['600415','601212','600029']:
            m = models[code]
            p = predict(data, m, code)
            top_w = ', '.join([f'{k}({v:.0%})' for k,v in p['weights'].items()])
            print(f"\n  {m['name']} ({code})")
            print(f"  昨收: ¥{p['prev_close']:.2f}")
            print(f"  阶段: {p['regime']} | β={p['beta']:.2f} α={p['alpha']*100:+.1f}%")
            print(f"  预测: ¥{p['price']:.2f} ±{p['ci68']:.2f} → [{p['lo']:.2f}, {p['hi']:.2f}]")
            print(f"  关键方法: {top_w}")
    
    elif cmd == 'review':
        # 复盘：对比上次预测 vs 最新收盘
        print("  复盘功能 - 需结合快照中的上次预测")
        # 简化版：只输出当前状态
        for code in ['600415','601212','600029']:
            closes, _, _, _, days, _, _ = build_aligned(data, code)
            print(f"  {code}: {days[-1]} 收 {closes[-1]:.2f}")
    
    else:
        print(f"  Usage: python3 v3_model.py [train|predict|review]")
