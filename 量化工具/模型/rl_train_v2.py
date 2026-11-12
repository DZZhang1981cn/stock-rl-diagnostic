#!/usr/bin/env python3
"""
v2 升级: 资金流向 + 轻量ML方法
"""
import subprocess, json, math, os

MODEL_DIR = os.path.expanduser('~/Desktop/AI工作/量化工具/模型/rl_models')
os.makedirs(MODEL_DIR, exist_ok=True)

def curl(url, ref=None):
    cmd = ['curl', '-s', '-L', '--max-time', '15', '-H', 'User-Agent: Mozilla/5.0']
    if ref: cmd += ['-H', f'Referer: {ref}']
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return r.stdout

LOOKBACK=20;WARMUP=60
LR=0.008;BATCH=20;ENTROPY_COEF=0.15

def lt(w):n=len(w);xm=(n-1)/2;ym=sum(w)/n;n2=sum((i-xm)*(w[i]-ym) for i in range(n));d=sum((i-xm)**2 for i in range(n));return ym+(n2/d if d else 0)*n
def mom(w):return w[-1]+(w[-1]-w[-6])*0.2+(w[-1]-w[-2])*0.3
def mrv(w):m=sum(w[-10:])/10;return w[-1]+(m-w[-1])*0.3
def mf(w,f):return w[-1]*(1+f['market_ret_5']*f['beta'])
def ap(w,f):return w[-1]*(1+f['alpha5']*1.5)
def srm(w,f):return w[-1]*(1+f.get('sector_vs_market',0)*0.5)
def ic(w,f):
    if f.get('independent')=='stock_driven':return w[-1]*(1+f['alpha5']*1.2)
    return w[-1]
def news_s(w,f):
    s=f.get('news_sentiment',0)
    return w[-1]*1.01 if s>0.5 else (w[-1]*0.99 if s<-0.5 else w[-1])
def chip_p(w,f):
    c=f.get('chip_score',0)
    return w[-1]*1.01 if c>3 else (w[-1]*0.99 if c<-2 else w[-1])

# --- v2 新增方法 ---
def fund_flow(w, f):
    """资金流向: 主力连续流入→看涨，连续流出→看跌"""
    ff = f.get('fund_flow_5d', 0)  # 5日主力净流入占比
    ff_trend = f.get('fund_trend', 0)  # 趋势
    if ff_trend > 2: return w[-1] * 1.02  # 主力持续流入
    elif ff_trend < -2: return w[-1] * 0.98  # 主力持续流出
    elif ff > 0.5: return w[-1] * 1.01
    return w[-1]

def ml_ensemble(w, f):
    """轻量ML: 多特征加权打分"""
    score = 0
    # α延续
    a5 = f.get('alpha5', 0)
    if a5 > 0.02: score += 0.3
    elif a5 < -0.02: score -= 0.3
    # β + 大盘方向
    mr5 = f.get('market_ret_5', 0)
    if mr5 > 0.01 and f.get('beta', 1) > 0: score += 0.15
    elif mr5 < -0.01: score -= 0.15
    # 资金流向
    ff_trend = f.get('fund_trend', 0)
    if ff_trend > 1: score += 0.2
    elif ff_trend < -1: score -= 0.2
    # 舆情
    ns = f.get('news_sentiment', 0)
    if ns > 0.3: score += 0.1
    elif ns < -0.3: score -= 0.1
    # 筹码
    cs = f.get('chip_score', 0)
    if cs > 3: score += 0.1
    return w[-1] * (1 + score * 0.02)

METHODS = {
    '线性趋势':lt,'动量':mom,'均值回归':mrv,'跟随大盘':mf,'α延续':ap,
    '行业轮动':srm,'独立延续':ic,'舆情驱动':news_s,'筹码位置':chip_p,
    '资金流向':fund_flow,'ML集成':ml_ensemble,
}

# ===== 资金流向数据拉取 =====
def fetch_fund_flow(code, sym):
    """拉取个股资金流向历史数据"""
    secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
    try:
        resp = curl(f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=200&secid={secid}&fields1=f1,f2&fields2=f51,f52,f53,f54,f55',
                    'https://data.eastmoney.com/')
        data = json.loads(resp)
        if data.get('data') and data['data'].get('klines'):
            result = {}
            for k in data['data']['klines']:
                parts = k.split(',')
                if len(parts) >= 5:
                    day = parts[0]
                    main_in = float(parts[1]) if parts[1] != '-' else 0
                    super_in = float(parts[2]) if parts[2] != '-' else 0
                    big_in = float(parts[3]) if parts[3] != '-' else 0
                    mid_in = float(parts[4]) if parts[4] != '-' else 0
                    result[day] = {
                        'main': main_in, 'super': super_in,
                        'big': big_in, 'mid': mid_in,
                    }
            return result
    except:
        pass
    return {}

POS_WORDS=['增长','盈利','中标','签约','突破','利好','回购','增持','分红','预增','预盈']
NEG_WORDS=['亏损','减持','处罚','诉讼','退市','警示','调查','下滑','下跌','预亏','预减']

def fetch_news(code):
    try:
        resp=curl(f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=30&page_index=1&ann_type=A&client_source=web&stock_list={code}','https://data.eastmoney.com/')
        data=json.loads(resp)
        items=data['data']['list']
        scores=[sum(1 for w in POS_WORDS if w in i.get('title',''))-sum(1 for w in NEG_WORDS if w in i.get('title','')) for i in items[:30]]
        scores=[s for s in scores if s!=0]
        return {'sentiment':round(sum(scores)/len(scores),2) if scores else 0,'count':len(scores)}
    except:
        return {'sentiment':0,'count':0}

def compute_feats(c,mc,h,l,v,i,news_info,fund_flow_data):
    s=max(0,i-LOOKBACK);e=i
    if e-s<5:return{}
    sr=[(c[j]-c[j-1])/max(c[j-1],0.01) for j in range(s+1,e+1)]
    mr=[(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(s+1,e+1)]
    n=len(sr);sm=sum(sr)/n;mm=sum(mr)/n
    cov=sum((sr[j]-sm)*(mr[j]-mm) for j in range(n))/n
    vm=sum((mr[j]-mm)**2 for j in range(n))/n
    beta=cov/vm if vm>0 else 1
    sr5=(c[i]/max(c[max(0,i-5)],0.01)-1)
    mr5=(mc[i]/max(mc[max(0,i-5)],0.01)-1)
    a5=sr5-beta*mr5
    ind='stock_driven' if abs(sr5)>0.03 and abs(a5)>abs(beta*mr5)*0.5 else ('market_driven' if abs(sr5)>0.03 else 'low_vol')
    v5=sum(v[max(0,i-4):i+1])/5;v20=sum(v[max(0,i-19):i+1])/20
    dry=0
    for j in range(i,max(0,i-20),-1):
        if j>=2 and v[j]<sum(v[max(0,j-2):j+1])/3*0.85:dry+=1
        else:break
    amp5=sum((h[j]-l[j])/c[j]*100 for j in range(max(0,i-4),i+1))/5
    amp20=sum((h[j]-l[j])/c[j]*100 for j in range(max(0,i-19),i+1))/20
    ar=amp5/amp20 if amp20 else 1;h10=max(h[max(0,i-9):i+1]);l10=min(l[max(0,i-9):i+1])
    rp=(h10-l10)/c[i]*100
    cs=dry*0.5+(1 if ar<0.85 else 0)*2+(1 if rp<8 else 0)*1
    
    # 资金流向特征
    ff_5d = 0; ff_trend = 0
    if fund_flow_data:
        dl = list(fund_flow_data.keys())
        # 找到最近5天
        recent_flows = []
        for d in sorted(dl)[-5:]:
            recent_flows.append(fund_flow_data[d]['main'])
        if recent_flows:
            ff_5d = sum(recent_flows) / len(recent_flows)
            # 趋势: 连续正向天数
            ff_trend = 0
            for fv in reversed(recent_flows):
                if fv > 0: ff_trend += 1
                else: break
    
    return {'beta':beta,'alpha5':a5,'market_ret_5':mr5,'sector_vs_market':0,'independent':ind,
            'news_sentiment':news_info.get('sentiment',0),'chip_score':cs,
            'fund_flow_5d':ff_5d,'fund_trend':ff_trend}

def classify(c,h,l,i,feats):
    cs=c[max(0,i-60):i+1]
    if len(cs)<30:return'unknown'
    m20=sum(cs[-20:])/20;p=cs[max(0,len(cs)-40):len(cs)-20];m20_20d=sum(p)/max(len(p),1)
    tr=(m20-m20_20d)/m20_20d*100
    if tr>3:base='strong_bull'
    elif tr>0:base='weak_bull'
    elif tr<-3:base='strong_bear'
    elif tr<0:base='weak_bear'
    else:base='sideways'
    ind=feats.get('independent','');a5=feats.get('alpha5',0)
    if ind=='stock_driven':base='alpha_up' if a5>0.02 else 'alpha_down'
    return base

# ===== 主训练 =====
market=json.loads(curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=1500'))
mkt_c=[float(d['close']) for d in market];mkt_d=[d['day'] for d in market]

CONFIG_FILE = os.path.expanduser('~/Desktop/AI工作/量化工具/分析/portfolio.json')
STOCKS = {'600415':'小商品城','601212':'白银有色','600029':'南方航空'}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        config = json.load(f)
        STOCKS = config.get('stocks', STOCKS)

print("=" * 60)
print("  RL v2: +资金流向 +ML集成")
print("=" * 60)

for code,name in STOCKS.items():
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    kl=json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1500'))
    c=[float(d['close']) for d in kl];h=[float(d['high']) for d in kl]
    l=[float(d['low']) for d in kl];v=[float(d['volume']) for d in kl]
    ds=[d['day'] for d in kl]
    
    md={d:c2 for d,c2 in zip(mkt_d,mkt_c)};mc=[md.get(d) for d in ds]
    last=None
    for i in range(len(mc)):
        if mc[i] is None:mc[i]=last if last else c[i]
        else:last=mc[i]
    
    # 拉资金流向
    fund_flow_data = fetch_fund_flow(code, sym)
    print(f"  {name}: K线{len(c)}条, 资金流向{len(fund_flow_data)}条")
    
    news_info=fetch_news(code);total=len(c)
    
    regimes_all=['strong_bull','weak_bull','sideways','weak_bear','strong_bear','alpha_up','alpha_down']
    w={r:{m:1.0 for m in METHODS} for r in regimes_all}
    for r in w:
        tw=sum(w[r].values())
        for m in w[r]:w[r][m]/=tw
    
    buffer={r:{m:0.0 for m in METHODS} for r in regimes_all}
    buffer_count={r:0 for r in regimes_all}
    
    correct=0;total_p=0;history=[]
    
    for i in range(WARMUP,total):
        wnd=c[i-LOOKBACK:i];actual=c[i];prev=c[i-1]
        feats=compute_feats(c,mc,h,l,v,i,news_info,fund_flow_data)
        reg=classify(c,h,l,i,feats)
        
        preds={}
        for mn,fn in METHODS.items():
            try:preds[mn]=fn(wnd,feats)
            except:preds[mn]=wnd[-1]
        
        cw=w.get(reg,{m:1/len(METHODS) for m in METHODS})
        wp=sum(preds[m]*cw[m] for m in METHODS)
        
        ad=1 if actual>prev else(-1 if actual<prev else 0)
        pd=1 if wp>prev else(-1 if wp<prev else 0)
        reward=1 if ad==pd else-1
        if ad==pd:correct+=1
        total_p+=1
        
        if reg in buffer:
            for mn in METHODS:
                md2=1 if preds[mn]>prev else(-1 if preds[mn]<prev else 0)
                mc2=1 if md2==ad else-1
                buffer[reg][mn]+=reward*mc2
            buffer_count[reg]+=1
        
        if total_p%BATCH==0:
            for r in buffer:
                if buffer_count[r]==0:continue
                for mn in METHODS:
                    grad=buffer[r][mn]/buffer_count[r]
                    p=w[r][mn]
                    entropy_grad=-ENTROPY_COEF*(math.log(max(p,1e-6))+1)
                    w[r][mn]=max(w[r][mn]+LR*(grad+entropy_grad),0.005)
                tw=sum(w[r].values())
                for mn in w[r]:w[r][mn]/=max(tw,0.001)
                buffer[r]={m:0.0 for m in METHODS}
                buffer_count[r]=0
        
        if total_p%200==0:history.append({'step':total_p,'acc':correct/total_p*100})
    
    fa=correct/total_p*100
    
    model={'code':code,'name':name,'weights':w,'final_acc':fa,'total_preds':total_p,
           'correct':correct,'lr':LR,'entropy':ENTROPY_COEF,'version':'v2','history':history}
    with open(os.path.join(MODEL_DIR,f'{code}.json'),'w') as f:
        json.dump(model,f,ensure_ascii=False,indent=2)
    
    h=model['history']
    print(f"  RL v1→v2: {fa:.1f}% (+{fa-h[0]['acc']:+.1f}%)")
    for reg in ['strong_bear','alpha_up','alpha_down']:
        ws=w[reg];top=sorted(ws.items(),key=lambda x:-x[1])[:4]
        print(f"    {reg}: {[(m,f'{v:.0%}') for m,v in top]}")

print("✅ RL v2 完成")
