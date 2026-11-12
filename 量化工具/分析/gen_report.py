#!/usr/bin/env python3
"""持仓诊断报告 — 含蜡烛图"""
import subprocess, json, math, os
from datetime import datetime

MODEL_DIR = os.path.expanduser('~/Desktop/AI工作/rl_models')
OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/导出文件')
LOOKBACK = 20
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url, ref=None):
    cmd = ['curl', '-s', '-L', '--max-time', '30', '-H', 'User-Agent: Mozilla/5.0']
    if ref: cmd += ['-H', f'Referer: {ref}']
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    return json.loads(r.stdout)

def lt(w): n=len(w);xm=(n-1)/2;ym=sum(w)/n;n2=sum((i-xm)*(w[i]-ym) for i in range(n));d=sum((i-xm)**2 for i in range(n));return ym+(n2/d if d else 0)*n
def mom(w): return w[-1]+(w[-1]-w[-6])*0.2+(w[-1]-w[-2])*0.3
def mr_fn(w): m=sum(w[-10:])/10; return w[-1]+(m-w[-1])*0.3
def mf(w,f): return w[-1]*(1+f['market_ret_5']*f['beta'])
def ap(w,f): return w[-1]*(1+f['alpha5']*1.5)
def sr_m(w,f): return w[-1]*(1+f.get('sector_vs_market',0)*0.5)
def ic(w,f):
    if f.get('independent')=='stock_driven': return w[-1]*(1+f['alpha5']*1.2)
    return w[-1]
def news_s(w,f):
    s=f.get('news_sentiment',0)
    return w[-1]*1.01 if s>0.5 else (w[-1]*0.99 if s<-0.5 else w[-1])
def chip_p(w,f):
    c=f.get('chip_score',0)
    return w[-1]*1.01 if c>3 else (w[-1]*0.99 if c<-2 else w[-1])

METHODS = ['线性趋势','动量','均值回归','跟随大盘','α延续','行业轮动','独立延续','舆情驱动','筹码位置','资金流向','ML集成']
METHOD_FNS = {'线性趋势':lt,'动量':mom,'均值回归':mr_fn,'跟随大盘':mf,'α延续':ap,'行业轮动':sr_m,'独立延续':ic,'舆情驱动':news_s,'筹码位置':chip_p,'资金流向':news_s,'ML集成':news_s}

POS_WORDS=['增长','盈利','中标','签约','突破','利好','回购','增持','分红','预增','预盈']
NEG_WORDS=['亏损','减持','处罚','诉讼','退市','警示','调查','下滑','下跌','预亏','预减']

def fetch_news(code):
    try:
        url=f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=30&page_index=1&ann_type=A&client_source=web&stock_list={code}'
        resp=curl(url, 'https://data.eastmoney.com/')
        items=resp['data']['list']
        scores=[sum(1 for w in POS_WORDS if w in i.get('title',''))-sum(1 for w in NEG_WORDS if w in i.get('title','')) for i in items[:30]]
        scores=[s for s in scores if s!=0]
        return {'sentiment':round(sum(scores)/len(scores),2) if scores else 0,'count':len(scores),'latest':[i.get('title','')[:50] for i in items[:5]]}
    except:
        return {'sentiment':0,'count':0,'latest':[]}

def candlestick_svg(kf, w=600, h=220):
    o,kh,kl,c,v,days = kf['o'],kf['h'],kf['l'],kf['c'],kf['v'],kf['days']
    n=len(o);ml=50;mr=10;mt=15;mb=35
    cw=w-ml-mr;ch=h-mt-mb
    candle_w=max(cw/n*0.6,2);gap=cw/n
    pmin=min(kl);pmax=max(kh);pr=pmax-pmin if pmax>pmin else 1
    vmax=max(v)
    def px(i):return ml+i*gap
    def py(p):return mt+ch*(1-(p-pmin)/pr)
    svg=f'<svg width="{w}" height="{h+50}" xmlns="http://www.w3.org/2000/svg">'
    svg+=f'<rect width="{w}" height="{h+50}" fill="#fafafa"/>'
    for i in range(5):
        p=pmin+pr*i/4;y=py(p)
        svg+=f'<line x1="{ml}" y1="{y:.0f}" x2="{w-mr}" y2="{y:.0f}" stroke="#eee" stroke-width="0.5"/>'
        svg+=f'<text x="2" y="{y+4:.0f}" font-size="9" fill="#999">{p:.2f}</text>'
    for i in range(0,n,max(1,n//8)):
        svg+=f'<text x="{px(i):.0f}" y="{h+16}" font-size="9" fill="#666" text-anchor="middle">{days[i][-5:]}</text>'
    for i in range(n):
        x=px(i);clr='#e74c3c' if c[i]>=o[i] else '#27ae60'
        bh=max(abs(c[i]-o[i])/pr*ch,0.5);by=py(max(c[i],o[i]));wx=x+candle_w/2
        svg+=f'<line x1="{wx:.1f}" y1="{py(kh[i]):.1f}" x2="{wx:.1f}" y2="{py(kl[i]):.1f}" stroke="{clr}" stroke-width="0.8"/>'
        svg+=f'<rect x="{x:.1f}" y="{by:.1f}" width="{candle_w:.1f}" height="{bh:.1f}" fill="{clr}" rx="1"/>'
    vh=35;vy=h+20
    for i in range(n):
        x=px(i);bar_h=v[i]/vmax*vh if vmax>0 else 0
        clr='#e74c3c66' if c[i]>=o[i] else '#27ae6066'
        svg+=f'<rect x="{x:.1f}" y="{vy-bar_h:.1f}" width="{candle_w:.1f}" height="{bar_h:.1f}" fill="{clr}"/>'
    svg+='</svg>'
    return svg

# ===== 诊断数据 =====
market=curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=200')
hs300=curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000300&scale=240&ma=no&datalen=200')
mkt_c=[float(d['close']) for d in market]; mkt_d=[d['day'] for d in market]
hs_c=[float(d['close']) for d in hs300]; hs_d=[d['day'] for d in hs300]

def align(ref,src_d,src_c):
    m={d:c for d,c in zip(src_d,src_c)};arr=[m.get(d) for d in ref];last=None
    for i in range(len(arr)):
        if arr[i] is None:arr[i]=last if last else 0
        else:last=arr[i]
    return arr

results = []
STOCKS={'600415':'小商品城','601212':'白银有色','600029':'南方航空'}

for code,name in STOCKS.items():
    model_path=os.path.join(MODEL_DIR,f'{code}.json')
    rl_weights=None;rl_acc=0
    if os.path.exists(model_path):
        with open(model_path) as f: rl_model=json.load(f)
        rl_weights=rl_model['weights']; rl_acc=rl_model['final_acc']
    
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=200'
    kl = curl(url)
    c=[float(d['close']) for d in kl];h_=[float(d['high']) for d in kl];l_=[float(d['low']) for d in kl]
    v_=[float(d['volume']) for d in kl];ds=[d['day'] for d in kl];o_=[float(d['open']) for d in kl]
    
    mc=align(ds,mkt_d,mkt_c);hc=align(ds,hs_d,hs_c)
    total=len(c);i=total-1;w=c[-LOOKBACK:i+1];prev=c[-2]
    
    s=max(0,i-LOOKBACK);e=i
    sr=[(c[j]-c[j-1])/max(c[j-1],0.01) for j in range(s+1,e+1)]
    mr=[(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(s+1,e+1)]
    hr=[(hc[j]-hc[j-1])/max(hc[j-1],0.01) for j in range(s+1,e+1)]
    n=len(sr);sm=sum(sr)/n;mm=sum(mr)/n;hm=sum(hr)/n
    cov_sh=sum((sr[j]-sm)*(mr[j]-mm) for j in range(n))/n;var_sh=sum((mr[j]-mm)**2 for j in range(n))/n
    cov_hs=sum((sr[j]-sm)*(hr[j]-hm) for j in range(n))/n;var_hs=sum((hr[j]-hm)**2 for j in range(n))/n
    beta_sh=cov_sh/var_sh if var_sh>0 else 1;beta_hs300=cov_hs/var_hs if var_hs>0 else 1
    sr5=(c[i]/max(c[max(0,i-5)],0.01)-1);mr5=(mc[i]/max(mc[max(0,i-5)],0.01)-1);hr5=(hc[i]/max(hc[max(0,i-5)],0.01)-1)
    alpha5_sh=sr5-beta_sh*mr5;alpha5_hs300=sr5-beta_hs300*hr5
    ind='stock_driven' if abs(sr5)>0.03 and abs(alpha5_sh)>abs(beta_sh*mr5)*0.5 else ('market_driven' if abs(sr5)>0.03 else 'low_vol')
    
    v5=sum(v_[max(0,i-4):i+1])/5;v20=sum(v_[max(0,i-19):i+1])/20
    dry=0
    for j in range(i,max(0,i-20),-1):
        if j>=2 and v_[j]<sum(v_[max(0,j-2):j+1])/3*0.85:dry+=1
        else:break
    amp5=sum((h_[j]-l_[j])/c[j]*100 for j in range(max(0,i-4),i+1))/5
    amp20=sum((h_[j]-l_[j])/c[j]*100 for j in range(max(0,i-19),i+1))/20
    ar=amp5/amp20 if amp20 else 1;h10=max(h_[max(0,i-9):i+1]);l10=min(l_[max(0,i-9):i+1])
    rp=(h10-l10)/c[i]*100
    cs=dry*0.5+(1 if ar<0.85 else 0)*2+(1 if rp<8 else 0)*1
    
    news_info=fetch_news(code)
    feats={'beta':beta_sh,'alpha5':alpha5_sh,'market_ret_5':mr5,'sector_vs_market':hr5-mr5,'independent':ind,'news_sentiment':news_info['sentiment'],'chip_score':cs}
    
    c_seg=c[max(0,i-60):i+1];ma20=sum(c_seg[-20:])/20;part=c_seg[max(0,len(c_seg)-40):len(c_seg)-20]
    ma20_20d=sum(part)/max(len(part),1);trend=(ma20-ma20_20d)/ma20_20d*100
    if trend>3:reg='strong_bull'
    elif trend>0:reg='weak_bull'
    elif trend<-3:reg='strong_bear'
    elif trend<0:reg='weak_bear'
    else:reg='sideways'
    if ind=='stock_driven':reg='alpha_up' if alpha5_sh>0.02 else 'alpha_down'
    
    preds={}
    for mn,fn in METHOD_FNS.items():
        try:preds[mn]=fn(w,feats)
        except:preds[mn]=w[-1]
    
    if rl_weights and reg in rl_weights:
        cw=rl_weights[reg];wp=sum(preds[m]*cw[m] for m in METHODS)
    else:
        wp=sum(preds.values())/len(preds)
    
    chg=(c[i]-prev)/prev*100;chg5=(c[i]/max(c[max(0,i-5)],0.01)-1)*100
    h60=max(h_[max(0,i-60):i+1]);l60=min(l_[max(0,i-60):i+1])
    pos=(c[i]-l60)/(h60-l60)*100 if h60!=l60 else 50
    vola=sum(max(h_[j]-l_[j],abs(h_[j]-c[j-1]),abs(l_[j]-c[j-1])) for j in range(max(1,i-14),i+1))/14/c[i]*100
    vr=v5/v20 if v20 else 1
    bulls=sum(1 for pv in preds.values() if pv>c[i]);bears=sum(1 for pv in preds.values() if pv<c[i])
    
    risk=0
    if vola>5:risk+=2
    elif vola>3:risk+=1
    if vr>2:risk+=1
    if pos<20:risk+=1
    if pos>80:risk+=1
    if reg in('strong_bear','alpha_down'):risk+=1
    if abs(beta_sh)>1.5:risk+=1
    
    # K线数据
    kf={'days':ds[max(0,total-30):total], 'o':o_[max(0,total-30):total],
        'h':h_[max(0,total-30):total], 'l':l_[max(0,total-30):total],
        'c':c[max(0,total-30):total], 'v':v_[max(0,total-30):total]}
    svg_chart = candlestick_svg(kf)
    
    results.append({
        'name':name,'code':code,'date':ds[-1],
        'close':c[i],'chg':chg,'chg5':chg5,
        'rl_pred':wp,'ci68_val':wp*0.025,
        'reg':reg,'trend':trend,
        'beta_sh':beta_sh,'beta_hs300':beta_hs300,
        'alpha5_sh':alpha5_sh,'alpha5_hs300':alpha5_hs300,
        'pos':pos,'vola':vola,'vr':vr,
        'bulls':bulls,'bears':bears,
        'risk':risk,
        'news':news_info,
        'chip':{'dry':dry,'amp_ratio':ar,'range':rp,'score':cs},
        'rl_acc':rl_acc,'rl_weights':cw if rl_weights else {},
        'svg_chart': svg_chart,
        'mkt_chg5':(mc[i]/max(mc[max(0,i-5)],0.01)-1)*100,
    })

# ===== 生成HTML =====
now=datetime.now().strftime('%Y-%m-%d %H:%M')
date_str=results[0]['date']
stage_labels={'strong_bull':'强势上涨','weak_bull':'温和上涨','strong_bear':'强势下跌','weak_bear':'温和下跌','sideways':'横盘震荡','alpha_up':'独立走强','alpha_down':'独立走弱'}

html_parts = [f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>持仓诊断报告 — {date_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f5f5;color:#333;padding:20px}}
h1{{text-align:center;color:#1a1a2e;margin-bottom:5px}}
.sub{{text-align:center;color:#888;margin-bottom:24px;font-size:14px}}
.card{{background:#fff;border-radius:12px;padding:24px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.card h2{{font-size:20px;margin-bottom:16px;border-bottom:2px solid #eee;padding-bottom:8px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
.grid4{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px}}
.metric{{padding:12px;background:#f8f9fa;border-radius:8px}}
.metric .label{{font-size:12px;color:#888;margin-bottom:4px}}
.metric .value{{font-size:22px;font-weight:700}}
.metric .sub{{font-size:11px;color:#999}}
.up{{color:#e74c3c}}.down{{color:#27ae60}}
.chart-box{{display:flex;justify-content:center;overflow-x:auto;margin:12px 0}}
.bar-container{{display:flex;align-items:center;gap:8px;margin:4px 0}}
.bar-label{{width:70px;text-align:right;font-size:13px}}
.bar-track{{flex:1;height:18px;background:#eee;border-radius:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px}}
.note{{font-size:12px;color:#999;margin-top:12px;padding:10px;background:#fffbe6;border-radius:4px}}
.news-item{{padding:5px 0;border-bottom:1px solid #f0f0f0;font-size:13px}}
.news-pos{{border-left:3px solid #e74c3c;padding-left:8px}}
.news-neg{{border-left:3px solid #27ae60;padding-left:8px}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}
th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #eee;font-size:13px}}
th{{background:#f8f9fa}}
</style></head>
<body>
<h1>📊 持仓诊断报告</h1>
<p class="sub">生成时间: {now} | RL强化学习模型 | 包含蜡烛图</p>
''']

# 汇总表
html_parts.append('<div class="card"><h2>📋 三票总览</h2><table>')
html_parts.append('<tr><th>股票</th><th>昨收</th><th>涨跌</th><th>RL预估</th><th>阶段</th><th>β</th><th>α</th><th>风险</th><th>RL准确率</th></tr>')
for r in results:
    chg_s=f"<span class='up'>+{r['chg']:.2f}%</span>" if r['chg']>0 else f"<span class='down'>{r['chg']:.2f}%</span>"
    risk_s='🟢' if r['risk']<2 else ('🟡' if r['risk']<4 else '🔴')
    html_parts.append(f"<tr><td><b>{r['name']}</b><br><span style='font-size:11px;color:#888'>{r['code']}</span></td>")
    html_parts.append(f"<td>¥{r['close']:.2f}</td><td>{chg_s}</td><td><b>¥{r['rl_pred']:.2f}</b></td>")
    html_parts.append(f"<td>{stage_labels.get(r['reg'],r['reg'])}</td>")
    html_parts.append(f"<td>{r['beta_sh']:.2f}</td><td>{r['alpha5_sh']*100:+.1f}%</td>")
    html_parts.append(f"<td>{risk_s}</td><td>{r['rl_acc']:.1f}%</td></tr>")
html_parts.append('</table></div>')

# 每只票详情
for r in results:
    stage=stage_labels.get(r['reg'],r['reg'])
    dir_up=r['rl_pred']>r['close']
    
    html_parts.append(f'''<div class="card">
<h2>{r['name']} ({r['code']}) — {stage}</h2>
<div class="grid3">
<div class="metric"><div class="label">昨收</div><div class="value">¥{r['close']:.2f}</div><div class="sub">{r['chg']:+.2f}% | 5日 {r['chg5']:+.1f}%</div></div>
<div class="metric"><div class="label">RL预估</div><div class="value {'up' if dir_up else 'down'}">¥{r['rl_pred']:.2f}</div><div class="sub">68%CI: ±{r['ci68_val']:.2f}</div></div>
<div class="metric"><div class="label">阶段</div><div class="value">{stage}</div><div class="sub">趋势强度 {r['trend']:+.1f}%</div></div>
</div>

<div class="grid4">
<div class="metric"><div class="label">β(上证/沪深300)</div><div class="value" style="font-size:16px">{r['beta_sh']:.2f} / {r['beta_hs300']:.2f}</div></div>
<div class="metric"><div class="label">α(近5日超额)</div><div class="value {'up' if r['alpha5_sh']>0 else 'down'}" style="font-size:16px">{r['alpha5_sh']*100:+.1f}%</div></div>
<div class="metric"><div class="label">60日位置</div><div class="value" style="font-size:16px">{r['pos']:.0f}%</div></div>
<div class="metric"><div class="label">波动率 / 量比</div><div class="value" style="font-size:16px">{r['vola']:.1f}% / {r['vr']:.2f}x</div></div>
</div>

<h3 style="margin-top:20px;margin-bottom:8px">📈 近30日蜡烛图</h3>
<div class="chart-box">{r['svg_chart']}</div>
''')
    
    # RL权重
    if r['rl_weights']:
        html_parts.append('<h3 style="margin-top:16px;margin-bottom:8px">🎯 RL方法权重</h3>')
        for mn,w in sorted(r['rl_weights'].items(),key=lambda x:-x[1]):
            if w<0.03:continue
            pct=w*100
            color='#e74c3c' if 'α' in mn else ('#3498db' if '大盘' in mn else ('#2ecc71' if '回归' in mn else '#9b59b6'))
            html_parts.append(f'<div class="bar-container"><div class="bar-label">{mn}</div><div class="bar-track"><div class="bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div><div style="width:40px;text-align:right;font-size:13px">{pct:.0f}%</div></div>')
    
    # 舆情
    if r['news']['count']>0:
        sl='正面' if r['news']['sentiment']>0 else ('负面' if r['news']['sentiment']<0 else '中性')
        html_parts.append(f'<h3 style="margin-top:16px;margin-bottom:8px">📰 近期公告 ({sl}, {r["news"]["count"]}条信号)</h3>')
        for item in r['news']['latest']:
            cls='news-pos' if any(w in item for w in POS_WORDS) else ('news-neg' if any(w in item for w in NEG_WORDS) else '')
            html_parts.append(f'<div class="news-item {cls}">{item}</div>')
    
    # 风险
    risk_label='低风险' if r['risk']<2 else ('中等风险' if r['risk']<4 else '高风险')
    html_parts.append(f'<div class="note">⚠️ {risk_label} | 方法投票: {r["bulls"]}涨/{r["bears"]}跌</div>')
    html_parts.append('</div>')

html_parts.append('<div class="note" style="text-align:center;margin-top:20px">⚠️ 基于历史数据的统计分析，不构成投资建议</div></body></html>')

html = '\n'.join(html_parts)
path=os.path.join(OUTPUT_DIR,f'持仓诊断_{date_str}.html')
with open(path,'w') as f:f.write(html)
print(f'✅ {path}')
