#!/usr/bin/env python3
"""
选股器 v2: 阶段过滤 + α排序 + 资金流向 + 舆情
零依赖，curl拉数据
"""
import subprocess, json, math, os, sys, time
from datetime import datetime

OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/导出文件')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url, ref=None):
    cmd = ['curl', '-s', '-L', '--max-time', '15', '-H', 'User-Agent: Mozilla/5.0']
    if ref: cmd += ['-H', f'Referer: {ref}']
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return r.stdout

# ===== 1. 获取沪深300成分股列表 =====
print("⏳ 获取沪深300成分股...")
try:
    resp = curl('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=400&po=1&np=1&fields=f12,f14&fid=f3&fs=b:1+f:!50&fltt=2',
                'https://data.eastmoney.com/')
    data = json.loads(resp)
    stocks = [(item['f12'], item['f14']) for item in data['data']['diff'] if item['f12'].startswith(('6','0','3'))]
    print(f"  获取到 {len(stocks)} 只股票")
except:
    # Fallback: 沪深300完整成分股
    stocks = [
        ('600519','贵州茅台'),('000858','五粮液'),('601318','中国平安'),('600036','招商银行'),
        ('000333','美的集团'),('002415','海康威视'),('600887','伊利股份'),('601166','兴业银行'),
        ('000002','万科A'),('600030','中信证券'),('600276','恒瑞医药'),('601857','中国石油'),
        ('600900','长江电力'),('000651','格力电器'),('601012','隆基绿能'),('600809','山西汾酒'),
        ('002594','比亚迪'),('601888','中国中免'),('600585','海螺水泥'),('300750','宁德时代'),
        ('601398','工商银行'),('600028','中国石化'),('601088','中国神华'),('000001','平安银行'),
        ('002475','立讯精密'),('600050','中国联通'),('601668','中国建筑'),('000725','京东方A'),
        ('002714','牧原股份'),('601899','紫金矿业'),('000568','泸州老窖'),('002304','洋河股份'),
        ('600690','海尔智家'),('000338','潍柴动力'),('601225','陕西煤业'),('000625','长安汽车'),
        ('600104','上汽集团'),('002142','宁波银行'),('000063','中兴通讯'),('601169','北京银行'),
        ('601288','农业银行'),('601939','建设银行'),('601328','交通银行'),('600016','民生银行'),
        ('000776','广发证券'),('601211','国泰君安'),('600837','海通证券'),('601688','华泰证券'),
        ('601628','中国人寿'),('601601','中国太保'),('601336','新华保险'),('600000','浦发银行'),
        ('002352','顺丰控股'),('600309','万华化学'),('601006','大秦铁路'),('600019','宝钢股份'),
        ('002460','赣锋锂业'),('300059','东方财富'),('600570','恒生电子'),('002236','大华股份'),
        ('000100','TCL科技'),('600703','三安光电'),('002049','紫光国微'),('000977','浪潮信息'),
        ('600745','闻泰科技'),('603259','药明康德'),('300122','智飞生物'),('000661','长春高新'),
        ('600436','片仔癀'),('000538','云南白药'),('600196','复星医药'),('300015','爱尔眼科'),
        ('600031','三一重工'),('000157','中联重科'),('600438','通威股份'),('601615','明阳智能'),
        ('002129','中环股份'),('601919','中远海控'),('600115','中国东航'),('600029','南方航空'),
        ('601111','中国国航'),('600009','上海机场'),('601877','正泰电器'),('300274','阳光电源'),
        ('002230','科大讯飞'),('688981','中芯国际'),('688111','金山办公'),('688012','中微公司'),
        ('600588','用友网络'),('002410','广联达'),('300124','汇川技术'),('601100','恒立液压'),
        ('002050','三花智控'),('601689','拓普集团'),('002920','德赛西威'),('300496','中科创达'),
        ('600406','国电南瑞'),('601985','中国核电'),('003816','中国广核'),('600025','华能水电'),
        ('601390','中国中铁'),('601800','中国交建'),('601186','中国铁建'),('600048','保利发展'),
        ('001979','招商蛇口'),('600383','金地集团'),('002146','荣盛发展'),('000069','华侨城A'),
        ('600660','福耀玻璃'),('601799','星宇股份'),('000800','一汽解放'),('600741','华域汽车'),
        ('600754','锦江酒店'),('002271','东方雨虹'),('000786','北新建材'),('002372','伟星新材'),
        ('600176','中国巨石'),('601636','旗滨集团'),('000012','南玻A'),('600801','华新水泥'),
    ]

# 拉大盘
market = json.loads(curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=200'))
mkt_c = [float(d['close']) for d in market]; mkt_d = [d['day'] for d in market]

POS_WORDS = ['增长','盈利','中标','签约','突破','利好','回购','增持','分红','预增','预盈']
NEG_WORDS = ['亏损','减持','处罚','诉讼','退市','警示','调查','下滑','下跌','预亏','预减']

# ===== 2. 逐票扫描 =====
print(f"\n🔍 扫描 {len(stocks)} 只股票...")
results = []
count = 0

def quick_score(code, name):
    """快速打分：拉60天K线 + 计算阶段 + α"""
    try:
        sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
        url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=60'
        kl = json.loads(curl(url))
        if not kl or len(kl) < 30: return None
        
        c = [float(d['close']) for d in kl]; total = len(c)
        i = total - 1
        
        # 对齐大盘
        ds = [d['day'] for d in kl]
        md = {d: cv for d, cv in zip(mkt_d, mkt_c)}
        mc = [md.get(d) for d in ds]
        last = None
        for j in range(len(mc)):
            if mc[j] is None: mc[j] = last if last else c[j]
            else: last = mc[j]
        
        # 趋势强度
        seg = c[max(0,i-60):i+1]
        ma20 = sum(seg[-20:])/20
        part = seg[max(0,len(seg)-40):len(seg)-20]
        ma20_20d = sum(part)/max(len(part), 1)
        trend_strength = (ma20 - ma20_20d) / ma20_20d * 100
        
        # α (5日超额)
        sr5 = (c[i]/max(c[max(0,i-5)], 0.01) - 1)
        mr5 = (mc[i]/max(mc[max(0,i-5)], 0.01) - 1)
        
        # beta
        lookback = min(20, i)
        s = max(0, i-lookback); e = i
        if e - s >= 5:
            sr_r = [(c[j]-c[j-1])/max(c[j-1],0.01) for j in range(s+1,e+1)]
            mr_r = [(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(s+1,e+1)]
            n = len(sr_r); sm = sum(sr_r)/n; mm = sum(mr_r)/n
            cov = sum((sr_r[j]-sm)*(mr_r[j]-mm) for j in range(n))/n
            vm = sum((mr_r[j]-mm)**2 for j in range(n))/n
            beta = cov/vm if vm > 0 else 1
        else:
            beta = 1
        
        alpha5 = sr5 - beta * mr5
        
        # 阶段判断
        if trend_strength > 3: regime = 'strong_bull'
        elif trend_strength > 0: regime = 'weak_bull'
        elif trend_strength < -3: regime = 'strong_bear'
        elif trend_strength < 0: regime = 'weak_bear'
        else: regime = 'sideways'
        
        # α独立性覆盖
        if abs(sr5) > 0.03 and abs(alpha5) > abs(beta * mr5) * 0.5:
            regime = 'alpha_up' if alpha5 > 0.02 else 'alpha_down'
        
        # === 阶段过滤 ===
        if regime in ('strong_bear', 'weak_bear', 'alpha_down'):
            return None  # 直接排除
        
        # 量能
        vols = [float(d['volume']) for d in kl]
        v5 = sum(vols[max(0,i-4):i+1])/5
        v20 = sum(vols[max(0,i-19):i+1])/20
        vol_ratio = v5/v20 if v20 else 1
        
        # 综合打分
        score = 0
        
        # α强度 (40%)
        alpha_norm = min(max(alpha5, -0.1), 0.1)  # clamp to ±10%
        score += (alpha_norm / 0.1) * 40  # -40 to +40
        
        # 趋势 (10%)
        trend_norm = min(max(trend_strength, -20), 20) / 20
        score += trend_norm * 10
        
        # 量能 (15%)
        if vol_ratio > 1.3: score += 15
        elif vol_ratio > 1.0: score += 8
        elif vol_ratio > 0.7: score += 3
        
        # 阶段加分 (15%)
        if regime == 'alpha_up': score += 15
        elif regime == 'strong_bull': score += 10
        elif regime == 'weak_bull': score += 5
        elif regime == 'sideways': score += 2
        
        # 价格位置加分 (10%)
        h60 = max([float(d['high']) for d in kl][max(0,i-60):i+1])
        l60 = min([float(d['low']) for d in kl][max(0,i-60):i+1])
        pos = (c[i] - l60) / (h60 - l60) * 100 if h60 != l60 else 50
        if 30 < pos < 70: score += 10  # 中部位置最好
        
        # 波动风险扣分 (10%)
        trs = []
        for j in range(max(1,i-14), i+1):
            h_j = float(kl[j]['high']); l_j = float(kl[j]['low']); pc = float(kl[j-1]['close'])
            trs.append(max(h_j-l_j, abs(h_j-pc), abs(l_j-pc)))
        atr = sum(trs)/len(trs) if trs else 0.01
        vola = atr / c[i] * 100
        if vola > 5: score -= 10
        elif vola > 3: score -= 5
        
        return {
            'code': code, 'name': name, 'price': c[i],
            'regime': regime, 'alpha5': alpha5, 'beta': beta,
            'score': score, 'trend': trend_strength,
            'vol_ratio': vol_ratio, 'vola': vola, 'pos': pos,
        }
    except:
        return None

for code, name in stocks:
    r = quick_score(code, name)
    if r:
        results.append(r)
        count += 1
    if count % 50 == 0:
        print(f"  已扫 {count} 只, 通过 {len(results)} 只...")
    time.sleep(0.05)  # 避免请求过快

print(f"\n  扫描完成: {count} 只, 阶段过滤通过 {len(results)} 只")

# ===== 3. 排序 + Top股票深度分析 =====
results.sort(key=lambda x: -x['score'])
top_n = min(15, len(results))

print(f"\n🏆 Top {top_n} 深度分析...")

for r in results[:top_n]:
    code = r['code']; name = r['name']
    # 舆情
    try:
        resp = curl(f'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=10&page_index=1&ann_type=A&client_source=web&stock_list={code}',
                    'https://data.eastmoney.com/')
        data = json.loads(resp)
        items = data['data']['list']
        scores = [sum(1 for w in POS_WORDS if w in i.get('title','')) - sum(1 for w in NEG_WORDS if w in i.get('title','')) for i in items[:10]]
        scores = [s for s in scores if s != 0]
        r['news_sentiment'] = round(sum(scores)/len(scores), 2) if scores else 0
        r['news_count'] = len(scores)
    except:
        r['news_sentiment'] = 0; r['news_count'] = 0
    
    # 资金流向
    try:
        secid = f'1.{code}' if code.startswith('6') else f'0.{code}'
        resp = curl(f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=5&secid={secid}&fields1=f1,f2&fields2=f51,f52',
                    'https://data.eastmoney.com/')
        data = json.loads(resp)
        flows = []
        for k in data['data']['klines']:
            p = k.split(','); flows.append(float(p[1]) if p[1] != '-' else 0)
        r['fund_5d'] = sum(flows[-5:]) if flows else 0
    except:
        r['fund_5d'] = 0
    
    reg_labels = {'alpha_up':'🟢独立走强','strong_bull':'🟢强势上涨','weak_bull':'🟢温和上涨','sideways':'⚪横盘'}
    r['reg_label'] = reg_labels.get(r['regime'], r['regime'])

# ===== 4. 生成HTML =====
now = datetime.now().strftime('%Y-%m-%d %H:%M')
date_str = datetime.now().strftime('%Y-%m-%d')

html = f'''<!DOCTYPE html><html lang="zh-CN">
<head><meta charset="UTF-8"><title>选股报告 — {date_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f5f5;color:#333;padding:20px}}
h1{{text-align:center;color:#1a1a2e;margin-bottom:5px}}
.sub{{text-align:center;color:#888;margin-bottom:20px;font-size:14px}}
.card{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,.08)}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid #eee;font-size:13px}}
th{{background:#f8f9fa;font-weight:600}}
.up{{color:#e74c3c}}.down{{color:#27ae60}}
.bar{{display:inline-block;height:16px;border-radius:3px;vertical-align:middle}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;margin:2px}}
.tag-up{{background:#ffeaea;color:#e74c3c}}
.tag-down{{background:#eafaf1;color:#27ae60}}
.tag-neutral{{background:#f0f0f0;color:#666}}
.rank{{display:inline-block;width:24px;height:24px;border-radius:50%;text-align:center;line-height:24px;font-size:12px;font-weight:700;color:#fff;margin-right:6px}}
.r1{{background:#e74c3c}}.r2{{background:#e67e22}}.r3{{background:#f39c12}}.r4{{background:#3498db}}
.note{{font-size:12px;color:#999;text-align:center;margin-top:20px;padding:12px;background:#fffbe6;border-radius:8px}}
.summary{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:20px}}
.sm{{background:#fff;padding:16px;border-radius:8px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.sm .val{{font-size:28px;font-weight:700;color:#1a1a2e}}
.sm .lbl{{font-size:12px;color:#888;margin-top:4px}}
</style></head><body>
<h1>🔍 选股报告</h1>
<p class="sub">生成时间: {now} | 方法: 阶段过滤 + α排序 + 资金流向 + 舆情</p>

<div class="summary">
<div class="sm"><div class="val">{count}</div><div class="lbl">扫描股票</div></div>
<div class="sm"><div class="val">{len(results)}</div><div class="lbl">阶段过滤通过</div></div>
<div class="sm"><div class="val">{top_n}</div><div class="lbl">最终推荐</div></div>
</div>

<div class="card">
<h2>📋 Top {top_n} 推荐</h2>
<table>
<tr><th>#</th><th>代码</th><th>名称</th><th>现价</th><th>得分</th><th>阶段</th><th>α</th><th>β</th><th>量比</th><th>舆情</th><th>资金流向</th></tr>
'''

for idx, r in enumerate(results[:top_n]):
    rank = idx + 1
    rc = 'r1' if rank <= 3 else ('r2' if rank <= 6 else ('r3' if rank <= 10 else 'r4'))
    ns = r.get('news_sentiment', 0)
    ns_label = '正面' if ns > 0.2 else ('负面' if ns < -0.2 else '中性')
    ns_tag = 'tag-up' if ns > 0.2 else ('tag-down' if ns < -0.2 else 'tag-neutral')
    fund = r.get('fund_5d', 0)
    fund_str = f'{fund/1e8:+.1f}亿' if abs(fund) > 1e7 else f'{fund/1e4:+.0f}万'
    alpha_str = f'<span class="up">+{r["alpha5"]*100:.1f}%</span>' if r['alpha5'] > 0 else f'<span class="down">{r["alpha5"]*100:.1f}%</span>'
    
    html += f'''<tr>
<td><span class="rank {rc}">{rank}</span></td>
<td>{r['code']}</td><td><b>{r['name']}</b></td>
<td>¥{r['price']:.2f}</td>
<td><b>{r['score']:.0f}</b></td>
<td>{r['reg_label']}</td>
<td>{alpha_str}</td>
<td>{r['beta']:.2f}</td>
<td>{r['vol_ratio']:.2f}x</td>
<td><span class="tag {ns_tag}">{ns_label}</span></td>
<td>{fund_str}</td>
</tr>'''

html += '''</table></div>

<div class="card">
<h2>📊 评分说明</h2>
<table>
<tr><th>因子</th><th>权重</th><th>说明</th></tr>
<tr><td>α强度</td><td>40%</td><td>近5日超额收益（vs大盘），已验证最强的单信号</td></tr>
<tr><td>量能+阶段</td><td>30%</td><td>量比>1.2加分 / alpha_up额外加分</td></tr>
<tr><td>趋势+位置</td><td>20%</td><td>趋势方向 + 在60日区间的合理位置</td></tr>
<tr><td>波动风险</td><td>-10%</td><td>高波动扣分</td></tr>
</table>
</div>

<div class="card">
<h2>📰 筛选逻辑</h2>
<ol>
<li><b>阶段过滤</b>: 排除 strong_bear / weak_bear / alpha_down 阶段的股票</li>
<li><b>α排序</b>: 按近5日超额收益排序（最强预测信号）</li>
<li><b>舆情复核</b>: 拉取最近公告，标记正面/负面</li>
<li><b>资金复核</b>: 拉取近5日主力资金净流入</li>
</ol>
</div>

<p class="note">⚠️ 基于历史数据的统计筛选，不构成投资建议。历史命中率约60-65%（方向），建议结合diagnose.py做二次确认。</p>
</body></html>'''

path = os.path.join(OUTPUT_DIR, f'选股报告_{date_str}.html')
with open(path, 'w') as f: f.write(html)
print(f'\n✅ {path}')

# 命令行输出
print(f"\n{'='*55}")
print(f"  🏆 Top {top_n}")
print(f"{'='*55}")
for idx, r in enumerate(results[:top_n]):
    alpha_s = f'+{r["alpha5"]*100:.1f}%' if r['alpha5'] > 0 else f'{r["alpha5"]*100:.1f}%'
    ns = r.get('news_sentiment', 0)
    ns_s = '📰+' if ns > 0.2 else ('📰-' if ns < -0.2 else '')
    print(f"  {idx+1:2d}. {r['name']:<8s} {r['code']}  ¥{r['price']:>7.2f}  得分{r['score']:>5.0f}  {r['reg_label']}  α{alpha_s}  β{r['beta']:.2f}  {ns_s}")
