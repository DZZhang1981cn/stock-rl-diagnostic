#!/usr/bin/env python3
"""
RL 强化学习训练系统
- 逐日预测 → 根据结果奖惩 → 更新权重
- 舆情数据作为额外特征
- 每只票独立训练专属模型
"""
import subprocess, json, math, os, sys
from datetime import datetime

MODEL_DIR = os.path.expanduser('~/Desktop/AI工作/rl_models')
os.makedirs(MODEL_DIR, exist_ok=True)

def curl(url, ref=None):
    cmd = ['curl', '-s', '-L', '--max-time', '30', '-H', 'User-Agent: Mozilla/5.0']
    if ref: cmd += ['-H', f'Referer: {ref}']
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    return r.stdout

# ===== 方法 =====
LOOKBACK = 20; WARMUP = 60  # RL需要更多预热

def lt(w): n=len(w);xm=(n-1)/2;ym=sum(w)/n;n2=sum((i-xm)*(w[i]-ym) for i in range(n));d=sum((i-xm)**2 for i in range(n));return ym+(n2/d if d else 0)*n
def mom(w): return w[-1]+(w[-1]-w[-6])*0.2+(w[-1]-w[-2])*0.3
def mr_fn(w): m=sum(w[-10:])/10; return w[-1]+(m-w[-1])*0.3
def mf(w,f): return w[-1]*(1+f['market_ret_5']*f['beta'])
def ap(w,f): return w[-1]*(1+f['alpha5']*1.5)
def sr_m(w,f): return w[-1]*(1+f.get('sector_vs_market',0)*0.5)
def ic(w,f):
    if f.get('independent')=='stock_driven': return w[-1]*(1+f['alpha5']*1.2)
    return w[-1]
def news_sentiment(w,f):
    """舆情驱动: 根据近期公告情绪调整"""
    sent = f.get('news_sentiment', 0)
    if sent > 0.5: return w[-1] * 1.01
    elif sent < -0.5: return w[-1] * 0.99
    return w[-1]
def chip_position(w,f):
    """筹码位置: 筹码集中时方向更可信"""
    chip = f.get('chip_score', 0)
    if chip > 3: return w[-1] * 1.01  # 筹码锁定→看多
    elif chip < -2: return w[-1] * 0.99
    return w[-1]

METHODS = {
    '线性趋势':lt,'动量':mom,'均值回归':mr_fn,
    '跟随大盘':mf,'α延续':ap,'行业轮动':sr_m,'独立延续':ic,
    '舆情驱动':news_sentiment,'筹码位置':chip_position,
}

# ===== 舆情获取 =====
POS_WORDS = ['增长','盈利','中标','签约','突破','利好','回购','增持','分红','预增','预盈','扭亏','中标','合同']
NEG_WORDS = ['亏损','减持','处罚','诉讼','退市','警示','调查','下滑','下跌','预亏','预减','辞职','冻结','查封']

def fetch_news_sentiment(code):
    """拉最近公告，做关键词情绪打分"""
    try:
        url = f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=30&page_index=1&ann_type=A&client_source=web&stock_list={code}'
        resp = curl(url, 'https://data.eastmoney.com/')
        if not resp or len(resp)<50: return {'sentiment':0, 'count':0, 'latest':[]}
        data = json.loads(resp)
        if not data.get('data') or not data['data'].get('list'): return {'sentiment':0, 'count':0, 'latest':[]}
        
        items = data['data']['list']
        scores = []; latest = []
        for item in items[:30]:
            title = item.get('title','')
            score = sum(1 for w in POS_WORDS if w in title) - sum(1 for w in NEG_WORDS if w in title)
            if score != 0: scores.append(score)
            if len(latest) < 5: latest.append(title[:40])
        
        avg = sum(scores)/len(scores) if scores else 0
        return {'sentiment': round(avg, 2), 'count': len(scores), 'latest': latest}
    except:
        return {'sentiment': 0, 'count': 0, 'latest': []}

# ===== 特征计算 =====
def compute_features(closes, mc, highs, lows, volumes, i, news_info):
    start=max(0,i-LOOKBACK);end=i
    if end-start<5: return {}
    
    sr=[(closes[j]-closes[j-1])/max(closes[j-1],0.01) for j in range(start+1,end+1)]
    mr=[(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(start+1,end+1)]
    n=len(sr);sm=sum(sr)/n;mm=sum(mr)/n
    cov=sum((sr[j]-sm)*(mr[j]-mm) for j in range(n))/n
    vm=sum((mr[j]-mm)**2 for j in range(n))/n
    beta=cov/vm if vm>0 else 1
    sr5=(closes[i]/max(closes[max(0,i-5)],0.01)-1)
    mr5=(mc[i]/max(mc[max(0,i-5)],0.01)-1)
    alpha5=sr5-beta*mr5
    ind='stock_driven' if abs(sr5)>0.03 and abs(alpha5)>abs(beta*mr5)*0.5 else ('market_driven' if abs(sr5)>0.03 else 'low_vol')
    
    # 筹码代理
    v5=sum(volumes[max(0,i-4):i+1])/5;v20=sum(volumes[max(0,i-19):i+1])/20
    dry=0
    for j in range(i,max(0,i-20),-1):
        if j>=2 and volumes[j]<sum(volumes[max(0,j-2):j+1])/3*0.85:dry+=1
        else:break
    amp5=sum((highs[j]-lows[j])/closes[j]*100 for j in range(max(0,i-4),i+1))/5
    amp20=sum((highs[j]-lows[j])/closes[j]*100 for j in range(max(0,i-19),i+1))/20
    amp_ratio=amp5/amp20 if amp20 else 1
    h10=max(highs[max(0,i-9):i+1]);l10=min(lows[max(0,i-9):i+1])
    range_pct=(h10-l10)/closes[i]*100
    chip_score = dry*0.5 + (1 if amp_ratio<0.85 else 0)*2 + (1 if range_pct<8 else 0)*1
    
    return {
        'beta':beta,'alpha5':alpha5,'market_ret_5':mr5,'sector_vs_market':0,
        'independent':ind,'news_sentiment':news_info.get('sentiment',0),
        'chip_score':chip_score,
    }

# ===== 阶段分类 =====
def classify_regime(closes, highs, lows, i, feats):
    c=closes[max(0,i-60):i+1]
    if len(c)<30: return 'unknown'
    ma20=sum(c[-20:])/20;part=c[max(0,len(c)-40):len(c)-20]
    ma20_20d=sum(part)/max(len(part),1);trend=(ma20-ma20_20d)/ma20_20d*100
    if trend>3: base='strong_bull'
    elif trend>0: base='weak_bull'
    elif trend<-3: base='strong_bear'
    elif trend<0: base='weak_bear'
    else: base='sideways'
    ind=feats.get('independent','');a5=feats.get('alpha5',0)
    if ind=='stock_driven': base='alpha_up' if a5>0.02 else 'alpha_down'
    return base

# ===== RL 训练核心 =====
def train_rl(code, name, kl_data, market_data, lr=0.05):
    """强化学习训练：逐日预测→奖惩→更新权重"""
    closes=[float(d['close']) for d in kl_data];days=[d['day'] for d in kl_data]
    highs=[float(d['high']) for d in kl_data];lows=[float(d['low']) for d in kl_data]
    volumes=[float(d['volume']) for d in kl_data]
    
    mkt_c=[float(d['close']) for d in market_data];mkt_d=[d['day'] for d in market_data]
    md={d:c for d,c in zip(mkt_d,mkt_c)};mc=[md.get(d) for d in days]
    last=None
    for i in range(len(mc)):
        if mc[i] is None:mc[i]=last if last else closes[i]
        else:last=mc[i]
    
    total=len(closes)
    
    # 拉舆情（最近一批）
    news_info = fetch_news_sentiment(code)
    
    # 初始化权重：每阶段每方法等权
    all_regimes = ['strong_bull','weak_bull','sideways','weak_bear','strong_bear','alpha_up','alpha_down']
    weights = {r: {m: 1.0 for m in METHODS} for r in all_regimes}
    for r in weights:
        tw = sum(weights[r].values())
        for m in weights[r]: weights[r][m] /= tw
    
    # 训练记录
    history = []
    correct = 0; total_preds = 0
    
    for i in range(WARMUP, total):
        w=closes[i-LOOKBACK:i]; actual=closes[i]; prev=closes[i-1]
        
        feats=compute_features(closes,mc,highs,lows,volumes,i,news_info)
        reg=classify_regime(closes,highs,lows,i,feats)
        
        # 预测
        preds={}
        for mn,fn in METHODS.items():
            try:preds[mn]=fn(w,feats)
            except:preds[mn]=w[-1]
        
        cw=weights.get(reg, {m:1/len(METHODS) for m in METHODS})
        wp=sum(preds[m]*cw[m] for m in METHODS)
        
        # 判断方向
        actual_dir = 1 if actual>prev else (-1 if actual<prev else 0)
        pred_dir = 1 if wp>prev else (-1 if wp<prev else 0)
        reward = 1 if actual_dir==pred_dir else -1
        if actual_dir==pred_dir: correct += 1
        total_preds += 1
        
        # RL更新：每个方法按贡献奖惩
        if reg in weights:
            for mn in METHODS:
                method_dir = 1 if preds[mn]>prev else (-1 if preds[mn]<prev else 0)
                method_correct = 1 if method_dir==actual_dir else -1
                # 正确的方法加分，错误的方法扣分
                delta = lr * (reward * method_correct) * cw.get(mn, 0.1)
                weights[reg][mn] = max(weights[reg][mn] + delta, 0.01)
            
            # 归一化
            tw = sum(weights[reg].values())
            for m in weights[reg]: weights[reg][m] /= max(tw, 0.01)
        
        if total_preds % 200 == 0:
            acc = correct/total_preds*100
            history.append({'step':total_preds,'acc':acc})
    
    final_acc = correct/total_preds*100
    
    # 保存模型
    model = {
        'code': code, 'name': name,
        'weights': weights,
        'final_acc': final_acc,
        'total_preds': total_preds,
        'correct': correct,
        'lr': lr,
        'trained_at': datetime.now().isoformat(),
        'history': history,
    }
    
    model_path = os.path.join(MODEL_DIR, f'{code}.json')
    with open(model_path, 'w') as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    
    return model

# ===== 强化一轮（收盘后调用） =====
def reinforce_step(code, prev_pred, actual_close, prev_close, lr=0.03):
    """单步强化：根据今日实际结果更新权重"""
    model_path = os.path.join(MODEL_DIR, f'{code}.json')
    if not os.path.exists(model_path):
        return False
    
    with open(model_path) as f:
        model = json.load(f)
    
    # 实际方向
    actual_dir = 1 if actual_close>prev_close else (-1 if actual_close<prev_close else 0)
    pred_dir = 1 if prev_pred>prev_close else (-1 if prev_pred<prev_close else 0)
    reward = 1 if actual_dir==pred_dir else -1
    
    # 更新所有权重（因为没有保存单次的方法投票，简化处理：对整个集合奖惩）
    # 实际应用中应在预测时保存各方法投票
    for reg in model['weights']:
        for mn in model['weights'][reg]:
            model['weights'][reg][mn] += lr * reward * model['weights'][reg][mn]
            model['weights'][reg][mn] = max(model['weights'][reg][mn], 0.01)
        tw = sum(model['weights'][reg].values())
        for mn in model['weights'][reg]:
            model['weights'][reg][mn] /= max(tw, 0.01)
    
    model['reinforced_at'] = datetime.now().isoformat()
    model['last_reward'] = reward
    
    with open(model_path, 'w') as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    
    return True

# ===== 主入口 =====
if __name__ == '__main__':
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'portfolio.json')
    STOCKS = {'600415':'小商品城','601212':'白银有色','600029':'南方航空'}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            config = json.load(f)
            STOCKS = config.get('stocks', STOCKS)
    
    print("=" * 60)
    print("  RL 强化学习训练")
    print("=" * 60)
    
    # 拉数据
    print("  ⏳ 拉取大盘...")
    market = json.loads(curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=1500'))
    
    for code, name in STOCKS.items():
        sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
        print(f"\n  {'='*50}")
        print(f"  {name} ({code})")
        
        try:
            kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1500'))
        except:
            print(f"    K线失败")
            continue
        
        model = train_rl(code, name, kl, market, lr=0.05)
        
        print(f"    训练完成: {model['total_preds']}次预测")
        print(f"    最终准确率: {model['final_acc']:.1f}%")
        
        # 学习曲线
        if model['history']:
            h = model['history']
            print(f"    学习曲线: {h[0]['acc']:.1f}% → {h[-1]['acc']:.1f}%")
        
        # 各阶段权重
        print(f"    各阶段顶级权重:")
        for reg in ['strong_bear','weak_bear','sideways','weak_bull','strong_bull','alpha_up','alpha_down']:
            if reg not in model['weights']: continue
            ws = model['weights'][reg]
            top = sorted(ws.items(), key=lambda x:-x[1])[:2]
            print(f"      {reg:<14} → {[(m,f'{w:.0%}') for m,w in top]}")
    
    print(f"\n{'='*60}")
    print(f"  ✅ 模型保存至 {MODEL_DIR}/")
    print(f"{'='*60}")
