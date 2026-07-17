#!/usr/bin/env python3
"""选股综合报告: 双版本排名 + K线图 + 财务数据"""
import subprocess, json, math, os, time
from datetime import datetime

OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/导出文件')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '15', '-H', 'User-Agent: Mozilla/5.0', url], capture_output=True, text=True, timeout=20)
    return json.loads(r.stdout)

def financial(code):
    try:
        sym = 'sh'+code if code.startswith('6') else 'sz'+code
        r = subprocess.run(['curl', '-s', '-L', '--max-time', '8', '-H', 'User-Agent: Mozilla/5.0', f'http://qt.gtimg.cn/q={sym}'], capture_output=True, timeout=10)
        parts = r.stdout.decode('gbk', errors='replace').split('~')
        if len(parts) > 50:
            return {'pe': parts[39] or '-', 'mcap': parts[45] or '-', 'pb': parts[46] or '-' if len(parts)>46 else '-'}
    except: pass
    return {'pe': '-', 'mcap': '-', 'pb': '-'}

def candlestick_svg(o, h, l, c, v, days, w=560, h_chart=200):
    n = len(o); ml=50; mr=10; mt=15; mb=35
    cw=w-ml-mr; ch=h_chart-mt-mb
    candle_w=max(cw/n*0.6, 2); gap=cw/n
    pmin=min(l); pmax=max(h); pr=pmax-pmin if pmax>pmin else 1
    vmax=max(v)
    def px(i): return ml+i*gap
    def py(p): return mt+ch*(1-(p-pmin)/pr)
    svg = f'<svg width="{w}" height="{h_chart+50}" xmlns="http://www.w3.org/2000/svg">'
    svg += f'<rect width="{w}" height="{h_chart+50}" fill="#fafafa"/>'
    for i in range(5):
        p = pmin+pr*i/4; y = py(p)
        svg += f'<line x1="{ml}" y1="{y:.0f}" x2="{w-mr}" y2="{y:.0f}" stroke="#eee" stroke-width="0.5"/>'
        svg += f'<text x="2" y="{y+4:.0f}" font-size="9" fill="#999">{p:.2f}</text>'
    for i in range(0, n, max(1, n//8)):
        svg += f'<text x="{px(i):.0f}" y="{h_chart+16}" font-size="9" fill="#666" text-anchor="middle">{days[i][-5:]}</text>'
    for i in range(n):
        x = px(i); clr = '#e74c3c' if c[i]>=o[i] else '#27ae60'
        bh = max(abs(c[i]-o[i])/pr*ch, 0.5); by = py(max(c[i],o[i]))
        wx = x + candle_w/2
        svg += f'<line x1="{wx:.1f}" y1="{py(h[i]):.1f}" x2="{wx:.1f}" y2="{py(l[i]):.1f}" stroke="{clr}" stroke-width="0.8"/>'
        svg += f'<rect x="{x:.1f}" y="{by:.1f}" width="{candle_w:.1f}" height="{bh:.1f}" fill="{clr}" rx="1"/>'
    vh = 35; vy = h_chart+20
    for i in range(n):
        x = px(i); bar_h = v[i]/vmax*vh if vmax>0 else 0
        svg += f'<rect x="{x:.1f}" y="{vy-bar_h:.1f}" width="{candle_w:.1f}" height="{bar_h:.1f}" fill="#e74c3c66" opacity="0.4"/>'
    svg += '</svg>'
    return svg

POOL = [('600519','茅台'),('000858','五粮液'),('601318','平安'),('600036','招行'),
    ('000333','美的'),('600887','伊利'),('600030','中信'),('601857','中石油'),
    ('000651','格力'),('002594','比亚迪'),('300750','宁德'),('600028','中石化'),
    ('601398','工行'),('600436','片仔癀'),('000568','老窖'),('601628','国寿'),
    ('600031','三一'),('300059','东财'),('000538','白药'),('601919','中远海控'),
    ('600048','保利'),('601985','核电'),('600660','福耀'),('600029','南航'),
    ('600585','海螺'),('600900','长电'),('601225','陕煤'),('002475','立讯'),
    ('601088','神华'),('002714','牧原'),('601899','紫金'),('000776','广发'),
    ('002415','海康'),('002230','讯飞'),('601166','兴业'),('002241','歌尔'),
    ('601012','隆基'),('600406','国电南瑞'),('603259','药明'),('000002','万科')]

market = curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=200')
mkt_c = [float(d['close']) for d in market]; mkt_d = [d['day'] for d in market]
mkt_label = '🐂 牛市' if sum(mkt_c[-10:])/10 > sum(mkt_c[-20:])/20 else '🐻 熊市'
now = datetime.now().strftime('%Y-%m-%d %H:%M')
date_str = datetime.now().strftime('%Y-%m-%d')

print(f"🔍 生成综合报告 ({len(POOL)}只)...")

# 收集所有数据
all_data = []
for code, name in POOL:
    try:
        sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
        kl200 = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=200')
        kl = curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=60')
        c=[float(d['close']) for d in kl]; h=[float(d['high']) for d in kl]; l=[float(d['low']) for d in kl]
        v=[float(d['volume']) for d in kl]; o=[float(d['open']) for d in kl]; days=[d['day'] for d in kl]
        i=len(c)-1
        md={d:cv for d,cv in zip(mkt_d,mkt_c)};mc=[md.get(d) for d in days]
        last=None
        for j in range(len(mc)):
            if mc[j] is None: mc[j]=last if last else c[j]
            else: last=mc[j]
        def ret(off): return c[i]/max(c[max(0,i-off)],0.01)-1
        def mret(off): return mc[i]/max(mc[max(0,i-off)],0.01)-1
        
        a5=ret(5)-mret(5); a10=ret(10)-mret(10); a20=ret(20)-mret(20)
        aup=0
        for j in range(i,max(0,i-20),-1):
            if j>=5: s5=c[j]/max(c[max(0,j-5)],0.01)-1; m5=mc[j]/max(mc[max(0,j-5)],0.01)-1
            if s5-m5>0.015: aup+=1
            else: break
        seg=c[max(0,i-30):i+1];ma10=sum(seg[-10:])/10;ma20=sum(seg[-20:])/20
        trend=(ma10/ma20-1)*100
        v5=sum(v[max(0,i-4):i+1])/5;v20=sum(v[max(0,i-19):i+1])/20;vr=v5/v20 if v20 else 1
        trs=[max(h[j]-l[j],abs(h[j]-c[j-1]),abs(l[j]-c[j-1])) for j in range(max(1,i-14),i+1)]
        vola=sum(trs)/len(trs)/c[i]*100 if trs else 3
        if i>=20:
            sr=[(c[j]-c[j-1])/max(c[j-1],0.01) for j in range(i-19,i+1)]
            mr=[(mc[j]-mc[j-1])/max(mc[j-1],0.01) for j in range(i-19,i+1)]
            nf=len(sr);sm=sum(sr)/nf;mm=sum(mr)/nf
            covv=sum((sr[j]-sm)*(mr[j]-mm) for j in range(nf))/nf
            vmm=sum((mr[j]-mm)**2 for j in range(nf))/nf
            beta=covv/vmm if vmm>0 else 1
        else: beta=1
        
        q_score = a5/0.05*20+a10/0.10*15+a20/0.15*10+(vr-1)*10+(-vola/3)*5+(-beta/0.5)*5+ret(5)*10-ret(10)*5
        o_score = min(max(a5,-0.05),0.12)/0.12*40+min(aup,8)/8*25+min(max(trend,-5),12)/12*15+(min(max(vr,0.5),2.0)-0.5)/1.5*10+max(0,(6-vola)/6*10)
        
        # K线数据 (30天)
        kf={'o':o[max(0,i-29):i+1],'h':h[max(0,i-29):i+1],'l':l[max(0,i-29):i+1],'c':c[max(0,i-29):i+1],'v':v[max(0,i-29):i+1],'days':days[max(0,i-29):i+1]}
        
        all_data.append({'code':code,'name':name,'price':c[i],'q_score':q_score,'o_score':o_score,
            'a5':a5,'a10':a10,'a20':a20,'vr':vr,'vola':vola,'beta':beta,
            'trend':trend,'chg':ret(1)*100,'kf':kf,'fin':financial(code)})
    except: pass
    time.sleep(0.03)

# 排序
qlib_rank = sorted(all_data, key=lambda x:-x['q_score'])[:12]
old_rank = sorted(all_data, key=lambda x:-x['o_score'])[:12]

# ===== 生成HTML =====
html = f'''<!DOCTYPE html><html lang="zh-CN">
<head><meta charset="UTF-8"><title>选股综合报告 — {date_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f5f5;color:#333;padding:20px}}
h1{{text-align:center;color:#1a1a2e;margin-bottom:4px}}
.sub{{text-align:center;color:#888;font-size:13px;margin-bottom:24px}}
.card{{background:#fff;border-radius:12px;padding:20px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
.card h2{{font-size:18px;margin-bottom:14px;border-bottom:2px solid #eee;padding-bottom:8px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}}
th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#f8f9fa;font-size:11px;font-weight:600}}
.up{{color:#e74c3c}}.down{{color:#27ae60}}
.rank{{display:inline-block;width:22px;height:22px;border-radius:50%;text-align:center;line-height:22px;font-size:11px;font-weight:700;color:#fff;margin-right:4px}}
.r1{{background:#e74c3c}}.r2{{background:#e67e22}}.r3{{background:#f39c12}}
.chart-box{{overflow-x:auto;margin:8px 0}}
.note{{font-size:12px;color:#999;text-align:center;margin-top:16px;padding:12px;background:#fffbe6;border-radius:8px}}
.stock-card{{border:1px solid #eee;border-radius:8px;padding:16px;margin-bottom:12px}}
.stock-card h3{{font-size:15px;margin-bottom:8px}}
.stock-grid{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:8px}}
.stock-m{{background:#f8f9fa;padding:8px;border-radius:6px;text-align:center}}
.stock-m .v{{font-size:16px;font-weight:700}}.stock-m .l{{font-size:11px;color:#888}}
.both{{background:#e8f5e9;border:2px solid #4caf50;border-radius:8px;padding:12px;margin-bottom:12px}}
</style></head><body>
<h1>📊 选股综合报告</h1>
<p class="sub">{now} | {mkt_label} | 扫描{len(all_data)}只 | Qlib多因子 + 5因子双版本</p>
'''

# === 双版都推荐的票 ===
qlib_codes = {r['code'] for r in qlib_rank}
old_codes = {r['code'] for r in old_rank}
both_codes = qlib_codes & old_codes
both = [r for r in qlib_rank if r['code'] in both_codes]

if both:
    html += '<div class="card"><h2>🎯 双版共同推荐（最高置信度）</h2><table>'
    html += '<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>Qlib得分</th><th>5F得分</th><th>α5</th><th>PE</th><th>PB</th><th>市值(亿)</th></tr>'
    for idx, r in enumerate(both):
        f = r['fin']; rc = 'r1' if idx<3 else 'r2'
        html += f'<tr><td><span class="rank {rc}">{idx+1}</span></td><td><b>{r["name"]}</b></td><td>{r["code"]}</td>'
        html += f'<td>¥{r["price"]:.2f}</td><td><b>{r["q_score"]:.0f}</b></td><td><b>{r["o_score"]:.0f}</b></td>'
        html += f'<td class="{"up" if r["a5"]>0 else "down"}">{r["a5"]*100:+.1f}%</td>'
        html += f'<td>{f["pe"]}</td><td>{f["pb"]}</td><td>{f["mcap"]}</td></tr>'
    html += '</table></div>'

# === Qlib排名+详细 ===
html += '<div class="card"><h2>📊 Qlib多因子 Top 12（稳定版，最大回撤-36%）</h2><table>'
html += '<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>涨跌</th><th>得分</th><th>α5</th><th>α10</th><th>α20</th><th>量比</th><th>波动</th><th>PE</th><th>PB</th><th>市值</th></tr>'
for idx, r in enumerate(qlib_rank):
    f = r['fin']; rc = 'r1' if idx<3 else ('r2' if idx<6 else 'r3')
    html += f'<tr><td><span class="rank {rc}">{idx+1}</span></td><td><b>{r["name"]}</b></td><td>{r["code"]}</td>'
    html += f'<td>¥{r["price"]:.2f}</td><td class="{"up" if r["chg"]>0 else "down"}">{r["chg"]:+.1f}%</td>'
    html += f'<td><b>{r["q_score"]:.0f}</b></td>'
    html += f'<td class="{"up" if r["a5"]>0 else "down"}">{r["a5"]*100:+.1f}%</td>'
    html += f'<td>{r["a10"]*100:+.1f}%</td><td>{r["a20"]*100:+.1f}%</td>'
    html += f'<td>{r["vr"]:.1f}x</td><td>{r["vola"]:.1f}%</td>'
    html += f'<td>{f["pe"]}</td><td>{f["pb"]}</td><td>{f["mcap"]}</td></tr>'
html += '</table></div>'

# === K线图 ===
html += '<div class="card"><h2>📈 Top 6 K线图 (Qlib版)</h2>'
for idx, r in enumerate(qlib_rank[:6]):
    svg = candlestick_svg(r['kf']['o'], r['kf']['h'], r['kf']['l'], r['kf']['c'], r['kf']['v'], r['kf']['days'])
    f = r['fin']
    html += f'''<div class="stock-card">
<h3>#{idx+1} {r['name']} ({r['code']}) ¥{r['price']:.2f} | α5={r['a5']*100:+.1f}% | PE={f['pe']} PB={f['pb']}</h3>
<div class="stock-grid">
<div class="stock-m"><div class="v">{r['q_score']:.0f}</div><div class="l">Qlib得分</div></div>
<div class="stock-m"><div class="v">{r['a5']*100:+.1f}%</div><div class="l">α(超额)</div></div>
<div class="stock-m"><div class="v">{r['vr']:.1f}x</div><div class="l">量比</div></div>
<div class="stock-m"><div class="v" style="color:{'#e74c3c' if r['vola']>4 else '#333'}">{r['vola']:.1f}%</div><div class="l">波动率</div></div>
</div>
<div class="chart-box">{svg}</div></div>'''
html += '</div>'

# === 5因子排名 ===
html += '<div class="card"><h2>📊 5因子版 Top 12（收益更高，回撤-47%）</h2><table>'
html += '<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>得分</th><th>α5</th><th>PE</th><th>PB</th><th>市值</th></tr>'
for idx, r in enumerate(old_rank):
    f = r['fin']; rc = 'r1' if idx<3 else ('r2' if idx<6 else 'r3')
    html += f'<tr><td><span class="rank {rc}">{idx+1}</span></td><td><b>{r["name"]}</b></td><td>{r["code"]}</td>'
    html += f'<td>¥{r["price"]:.2f}</td><td><b>{r["o_score"]:.0f}</b></td>'
    html += f'<td class="{"up" if r["a5"]>0 else "down"}">{r["a5"]*100:+.1f}%</td>'
    html += f'<td>{f["pe"]}</td><td>{f["pb"]}</td><td>{f["mcap"]}</td></tr>'
html += '</table></div>'

html += '<div class="note">⚠️ 基于历史数据的统计分析，不构成投资建议。Qlib版更稳定（回撤-36%），5因子版收益更高（回撤-47%）。</div></body></html>'

path = os.path.join(OUTPUT_DIR, f'选股综合报告_{date_str}.html')
with open(path, 'w') as f: f.write(html)
print(f'✅ {path}')
