#!/usr/bin/env python3
"""
v3 持仓诊断工具 v2 — 聚焦诊断信息深度
用法: python3 diagnose.py [codes...]
"""
import subprocess, json, math, os, sys
from datetime import datetime

MODEL_FILE = os.path.expanduser('~/Desktop/AI工作/v3_model_weights.json')
LOOKBACK = 20; WARMUP = 80
STOCKS = {'600415':'小商品城','601212':'白银有色','600029':'南方航空'}

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '30', '-H', 'User-Agent: Mozilla/5.0', url], capture_output=True, text=True, timeout=35)
    return json.loads(r.stdout)

def lt(w): n=len(w);xm=(n-1)/2;ym=sum(w)/n;n2=sum((i-xm)*(w[i]-ym) for i in range(n));d=sum((i-xm)**2 for i in range(n));return ym+(n2/d if d else 0)*n
def mom(w): return w[-1]+(w[-1]-w[-6])*0.2+(w[-1]-w[-2])*0.3
def mr_fn(w): m=sum(w[-10:])/10; return w[-1]+(m-w[-1])*0.3
def mf(w,f): return w[-1]*(1+f.get('market_ret_5',0)*f.get('beta',1))
def ap(w,f): return w[-1]*(1+f.get('alpha5',0)*1.5)
def sr_m(w,f): return w[-1]*(1+f.get('sector_vs_market',0)*0.5)
def ic(w,f):
    if f.get('independent')=='stock_driven': return w[-1]*(1+f.get('alpha5',0)*1.2)
    return w[-1]

METHODS = {'线性趋势':lt,'动量':mom,'均值回归':mr_fn,'跟随大盘':mf,'α延续':ap,'行业轮动':sr_m,'独立延续':ic}

def diagnose(code, name, stock_kl, market_kl, hs300_kl, models):
    closes = [float(d['close']) for d in stock_kl]
    highs = [float(d['high']) for d in stock_kl]
    lows = [float(d['low']) for d in stock_kl]
    volumes = [float(d['volume']) for d in stock_kl]
    days = [d['day'] for d in stock_kl]
    total = len(closes)
    
    mkt_c = [float(d['close']) for d in market_kl]; mkt_d = [d['day'] for d in market_kl]
    hs_c = [float(d['close']) for d in hs300_kl]; hs_d = [d['day'] for d in hs300_kl]
    
    def align(ref, src_d, src_c):
        m = {d:c for d,c in zip(src_d, src_c)}
        arr = [m.get(d) for d in ref]
        last = None
        for i in range(len(arr)):
            if arr[i] is None: arr[i] = last if last else closes[i]
            else: last = arr[i]
        return arr
    
    mc = align(days, mkt_d, mkt_c)
    hc = align(days, hs_d, hs_c)
    
    # ===== 当前状态 =====
    i = total - 1
    w = closes[-LOOKBACK:i+1]
    prev = closes[-2] if total >= 2 else closes[-1]
    
    start = max(0,i-LOOKBACK); end = i
    sr = [(closes[j]-closes[j-1])/max(closes[j-1],0.01) for j in range(start+1,end+1)]
    mr = [(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(start+1,end+1)]
    hr = [(hc[j]-hc[j-1])/max(hc[j-1],0.01) for j in range(start+1,end+1)]
    n = len(sr); sm=sum(sr)/n; mm=sum(mr)/n; hm=sum(hr)/n
    cov_sh=sum((sr[j]-sm)*(mr[j]-mm) for j in range(n))/n
    var_sh=sum((mr[j]-mm)**2 for j in range(n))/n
    beta_sh=cov_sh/var_sh if var_sh>0 else 1
    cov_hs=sum((sr[j]-sm)*(hr[j]-hm) for j in range(n))/n
    var_hs=sum((hr[j]-hm)**2 for j in range(n))/n
    beta_hs300=cov_hs/var_hs if var_hs>0 else 1
    
    sr5=(closes[i]/max(closes[max(0,i-5)],0.01)-1)
    mr5=(mc[i]/max(mc[max(0,i-5)],0.01)-1)
    hr5=(hc[i]/max(hc[max(0,i-5)],0.01)-1)
    alpha5_sh=sr5-beta_sh*mr5
    alpha5_hs300=sr5-beta_hs300*hr5
    independent='stock_driven' if abs(sr5)>0.03 and abs(alpha5_sh)>abs(beta_sh*mr5)*0.5 else ('market_driven' if abs(sr5)>0.03 else 'low_vol')
    
    feats={'beta':beta_sh,'beta_hs300':beta_hs300,'alpha5':alpha5_sh,'alpha5_hs300':alpha5_hs300,'market_ret_5':mr5,'sector_vs_market':hr5-mr5,'independent':independent}
    
    # 阶段
    c_seg=closes[max(0,i-60):i+1]
    ma20=sum(c_seg[-20:])/20; part=c_seg[max(0,len(c_seg)-40):len(c_seg)-20]
    ma20_20d=sum(part)/max(len(part),1); trend_strength=(ma20-ma20_20d)/ma20_20d*100
    if trend_strength>3: regime='strong_bull'
    elif trend_strength>0: regime='weak_bull'
    elif trend_strength<-3: regime='strong_bear'
    elif trend_strength<0: regime='weak_bear'
    else: regime='sideways'
    if independent=='stock_driven': regime='alpha_up' if alpha5_sh>0.02 else 'alpha_down'
    
    h60=max(highs[max(0,i-60):i+1]); l60=min(lows[max(0,i-60):i+1])
    position=(closes[i]-l60)/(h60-l60)*100 if h60!=l60 else 50
    
    trs=[]
    for j in range(max(1,i-14),i+1):
        trs.append(max(highs[j]-lows[j],abs(highs[j]-closes[j-1]),abs(lows[j]-closes[j-1])))
    atr14=sum(trs)/len(trs) if trs else 0.01
    volatility=atr14/closes[i]*100
    
    v5=sum(volumes[max(0,i-4):i+1])/5; v20=sum(volumes[max(0,i-19):i+1])/20
    vol_ratio=v5/v20 if v20 else 1
    price_chg=closes[i]-prev
    if price_chg>0 and v5>v20*1.1: vol_price='放量上涨'
    elif price_chg>0 and v5<v20*0.9: vol_price='缩量上涨(⚠️)'
    elif price_chg<0 and v5>v20*1.1: vol_price='放量下跌(🔴)'
    elif price_chg<0 and v5<v20*0.9: vol_price='缩量下跌'
    else: vol_price='量价平'
    
    # 预测
    preds={}
    for mn,fn in METHODS.items():
        try:preds[mn]=fn(w,feats)
        except:preds[mn]=w[-1]
    wp=sum(preds.values())/len(preds)
    pred_dirs=[1 if preds[m]>closes[i] else(-1 if preds[m]<closes[i] else 0) for m in METHODS]
    bulls=sum(1 for d in pred_dirs if d>0); bears=sum(1 for d in pred_dirs if d<0)
    
    if code in models:
        m=models[code];rw=m.get('regime_weights',{})
        cw=rw.get(regime,{m2:1/len(METHODS) for m2 in METHODS})
        wp=sum(preds[m2]*cw.get(m2,0) for m2 in METHODS)
        ci68=m.get('ci68',0.2); ci95=m.get('ci90',ci68*1.65)
    else:
        ci68=0.25; ci95=0.45
    
    # ===== 历史对比 =====
    # 阶段演变
    regime_history=[]
    for j in range(max(WARMUP,total-10),total):
        seg_j=closes[max(0,j-60):j+1]
        m20_j=sum(seg_j[-20:])/20; p_j=seg_j[max(0,len(seg_j)-40):len(seg_j)-20]
        m20_20d_j=sum(p_j)/max(len(p_j),1);trend_j=(m20_j-m20_20d_j)/m20_20d_j*100
        if trend_j>3: r_j='🟢牛'
        elif trend_j>0: r_j='🟢微牛'
        elif trend_j<-3: r_j='🔴熊'
        elif trend_j<0: r_j='🔴微熊'
        else: r_j='⚪横'
        # check independence
        if j>=5:
            sr5_j=(closes[j]/max(closes[max(0,j-5)],0.01)-1)
            mr5_j=(mc[j]/max(mc[max(0,j-5)],0.01)-1)
            a5_j=sr5_j-beta_sh*mr5_j
            if abs(sr5_j)>0.03 and abs(a5_j)>abs(beta_sh*mr5_j)*0.5:
                r_j='🟢α↑' if a5_j>0.02 else '🔴α↓'
        regime_history.append({'day':days[j],'label':r_j})
    
    # beta/alpha 历史分布
    beta_history=[]; alpha_history=[]; vol_history=[]
    for j in range(WARMUP,total):
        s_j=max(0,j-20);e_j=j
        if e_j-s_j<5:continue
        sr_j=[(closes[k]-closes[k-1])/max(closes[k-1],0.01) for k in range(s_j+1,e_j+1)]
        mr_j=[(mc[k]-mc[k-1])/max(mc[k-1],0.01) for k in range(s_j+1,e_j+1)]
        n_j=len(sr_j);sm_j=sum(sr_j)/n_j;mm_j=sum(mr_j)/n_j
        cv_j=sum((sr_j[k]-sm_j)*(mr_j[k]-mm_j) for k in range(n_j))/n_j
        vm_j=sum((mr_j[k]-mm_j)**2 for k in range(n_j))/n_j
        b_j=cv_j/vm_j if vm_j>0 else 1
        sr5_j=(closes[j]/max(closes[max(0,j-5)],0.01)-1)
        mr5_j=(mc[j]/max(mc[max(0,j-5)],0.01)-1)
        a_j=sr5_j-b_j*mr5_j
        beta_history.append(b_j); alpha_history.append(a_j)
        tr_j=[max(highs[k]-lows[k],abs(highs[k]-closes[k-1]),abs(lows[k]-closes[k-1])) for k in range(max(1,j-14),j+1)]
        vol_history.append(sum(tr_j)/len(tr_j)/closes[j]*100)
    
    # 百分位
    def pct(arr,val):
        if not arr:return 50
        return sum(1 for v in arr if v<val)/len(arr)*100
    
    beta_pct=pct(beta_history,beta_sh)
    alpha_pct=pct(alpha_history,alpha5_sh)
    vol_pct=pct(vol_history,volatility)
    
    # ===== 风险等级 =====
    risk_score=0
    if volatility>5:risk_score+=2
    elif volatility>3:risk_score+=1
    if vol_ratio>2:risk_score+=1
    if position>80:risk_score+=1
    elif position<20:risk_score+=1
    if regime in('strong_bear','alpha_down'):risk_score+=1
    if abs(beta_sh)>1.5:risk_score+=1
    if risk_score>=4:risk_level='🔴 高'
    elif risk_score>=2:risk_level='🟡 中'
    else:risk_level='🟢 低'
    
    return {
        'name':name,'code':code,'date':days[-1],
        'close':closes[i],'prev_close':prev,
        'regime':regime,'trend_strength':trend_strength,
        'beta_sh':beta_sh,'beta_hs300':beta_hs300,'beta_pct':beta_pct,
        'alpha5_sh':alpha5_sh,'alpha5_hs300':alpha5_hs300,'alpha_pct':alpha_pct,
        'position':position,'volatility':volatility,'vol_pct':vol_pct,
        'vol_ratio':vol_ratio,'vol_price':vol_price,
        'bulls':bulls,'bears':bears,
        'model_pred':wp,'ci68':ci68,'ci95':ci95,
        'risk_level':risk_level,
        'regime_history':regime_history,
    }

# ===== 输出 =====
def print_diagnosis(d):
    print(f"\n{'='*60}")
    print(f"  {d['name']} ({d['code']}) — {d['date']}")
    print(f"{'='*60}")
    chg=(d['close']-d['prev_close'])/d['prev_close']*100
    print(f"  昨收: ¥{d['close']:.2f} ({chg:+.2f}%)")
    
    # ===== 核心诊断 =====
    stage_labels={
        'strong_bull':'强势上涨','weak_bull':'温和上涨',
        'strong_bear':'强势下跌','weak_bear':'温和下跌',
        'sideways':'横盘震荡','alpha_up':'独立走强','alpha_down':'独立走弱',
    }
    stage=stage_labels.get(d['regime'],d['regime'])
    
    # 阶段演变
    evo=' → '.join([h['label'] for h in d['regime_history']])
    
    print(f"")
    print(f"  ┌─ 核心诊断")
    print(f"  │ 阶段: {stage}")
    print(f"  │ 近10日演变: {evo}")
    print(f"  │ 60日位置: {d['position']:.0f}%  |  趋势强度: {d['trend_strength']:+.1f}%")
    print(f"  │")
    print(f"  │ 大盘联动:")
    beta_label='高敏感' if d['beta_sh']>1.3 else ('低敏感' if d['beta_sh']<0.7 else '中敏感')
    print(f"  │   β(上证)= {d['beta_sh']:.2f} ({beta_label}) 历史分位 {d['beta_pct']:.0f}%")
    print(f"  │   α(近5日)= {d['alpha5_sh']*100:+.1f}% (历史分位 {d['alpha_pct']:.0f}%)")
    if d['alpha5_sh']>0.03:print(f"  │   → 个股正在独立跑赢大盘，不跟跌")
    elif d['alpha5_sh']<-0.03:print(f"  │   → 个股正在独立跑输大盘，自身问题")
    else:print(f"  │   → 个股走势与大盘同步，无独立行情")
    
    print(f"  │")
    print(f"  │ 市场信号:")
    print(f"  │   波动率: {d['volatility']:.1f}% (历史分位 {d['vol_pct']:.0f}%)")
    print(f"  │   量比: {d['vol_ratio']:.2f}x  |  {d['vol_price']}")
    print(f"  │   方法共识: {d['bulls']}看涨/{d['bears']}看跌")
    print(f"  │")
    print(f"  │ 风险等级: {d['risk_level']}")
    
    # 解读
    print(f"  │")
    print(f"  │ 📝 综合解读:")
    interpret(d)
    
    # 价格参考
    print(f"  └─ 价格参考: ¥{d['model_pred']:.2f} [68%CI: {d['model_pred']-d['ci68']:.2f}-{d['model_pred']+d['ci68']:.2f}]")

def interpret(d):
    """根据所有信号综合解读"""
    points=[]
    
    # 阶段解读
    if d['regime']=='alpha_up':
        points.append('个股正在脱离大盘独立走强，这是最强的看涨信号之一')
        if d['beta_sh']<0.7:
            points.append('低β(+): 不跟大盘跌，适合作为防守仓位')
    elif d['regime']=='alpha_down':
        points.append('个股独立走弱，问题可能不在大盘而在个股自身')
        if d['alpha5_sh']<-0.1:
            points.append('⚠️ α极端负值，短期或有利空事件冲击')
    elif d['regime']=='strong_bear':
        points.append('处于强下跌趋势，注意控制仓位')
        if d['position']<20:
            points.append('已接近60日低点区域，超跌反弹概率在累积')
    elif d['regime']=='strong_bull':
        points.append('处于强上涨趋势')
        if d['position']>80:
            points.append('已接近60日高点，注意获利回吐压力')
    elif d['regime']=='sideways':
        points.append('横盘震荡中，方向不明，适合观望')
    
    # 波动率解读
    if d['vol_pct']>80:
        points.append(f"波动率处于历史高位({d['vol_pct']:.0f}%分位)，价格可能剧烈波动")
    elif d['vol_pct']<20:
        points.append(f"波动率处于历史低位({d['vol_pct']:.0f}%分位)，可能酝酿变盘")
    
    # 量价解读
    if '缩量上涨' in d['vol_price']:
        points.append('缩量上涨需警惕——没有量能支持的反弹容易回落')
    elif '放量下跌' in d['vol_price']:
        points.append('放量下跌——有资金在离场，短期承压')
    elif '放量上涨' in d['vol_price']:
        points.append('放量上涨——有增量资金进场，信号偏积极')
    
    # β解读
    if d['beta_pct']>80:
        points.append(f'β处于历史高位({d["beta_pct"]:.0f}%分位)，个股近期与大盘高度联动')
    
    for pt in points:
        print(f"  │   • {pt}")

# ===== 主入口 =====
if __name__=='__main__':
    target_codes=sys.argv[1:] if len(sys.argv)>1 else list(STOCKS.keys())
    
    models={}
    if os.path.exists(MODEL_FILE):
        with open(MODEL_FILE) as f:models=json.load(f)
    
    print("  ⏳ 拉取数据...")
    market_kl=curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=200')
    hs300_kl=curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000300&scale=240&ma=no&datalen=200')
    
    for code in target_codes:
        sym=f'sh{code}' if code.startswith('6') else f'sz{code}'
        try:
            kl=curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=200')
            name=STOCKS.get(code,code)
            d=diagnose(code,name,kl,market_kl,hs300_kl,models)
            print_diagnosis(d)
        except Exception as e:
            print(f"  {code}: 诊断失败 - {e}")
    
    print(f"\n{'='*60}")
    print(f"  诊断完成")
    print(f"{'='*60}")
