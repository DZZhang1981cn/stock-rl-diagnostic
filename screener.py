#!/usr/bin/env python3
"""选股器 v5 — 每日排名 | python3 screener.py"""
import subprocess, json, os, time
from datetime import datetime

OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/导出文件')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url, ref=None):
    cmd = ['curl', '-s', '-L', '--max-time', '12', '-H', 'User-Agent: Mozilla/5.0']
    if ref: cmd += ['-H', f'Referer: {ref}']
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.stdout

# ===== 股票池 =====
POOL = [
    ('600519','茅台'),('000858','五粮液'),('601318','平安'),('600036','招行'),
    ('000333','美的'),('002415','海康'),('600887','伊利'),('601166','兴业'),
    ('600030','中信'),('600276','恒瑞'),('601857','中石油'),('600900','长电'),
    ('000651','格力'),('600809','汾酒'),('002594','比亚迪'),('601398','工行'),
    ('300750','宁德'),('600028','中石化'),('601088','神华'),('000001','平安银行'),
    ('000725','京东方'),('002714','牧原'),('601899','紫金'),('000568','老窖'),
    ('600690','海尔'),('600031','三一'),('300059','东财'),('603259','药明康德'),
    ('600436','片仔癀'),('000538','白药'),('601628','国寿'),('000776','广发'),
    ('600019','宝钢'),('002352','顺丰'),('600048','保利'),('601919','中远海控'),
    ('600406','国电南瑞'),('601985','核电'),('600660','福耀'),('300015','爱尔'),
    ('000661','长春高新'),('600585','海螺'),('600309','万华'),('002460','赣锋'),
    ('002230','科大讯飞'),('600029','南航'),('000002','万科'),('601111','国航'),
    ('601288','农行'),('601939','建行'),('601328','交行'),('600000','浦发'),
    ('601601','太保'),('600837','海通'),('601688','华泰'),('002475','立讯'),
    ('600050','联通'),('601668','建筑'),('600104','上汽'),('002142','宁波银行'),
    ('000063','中兴'),('601225','陕煤'),('002304','洋河'),('600745','闻泰'),
    ('300122','智飞'),('600196','复星'),('600438','通威'),('601615','明阳'),
    ('300274','阳光电源'),('688981','中芯国际'),('688111','金山办公'),
    ('300124','汇川'),('601100','恒立液压'),('002050','三花'),('601689','拓普'),
    ('002920','德赛西威'),('600025','华能水电'),('601390','中国中铁'),
    ('601800','中国交建'),('601186','中国铁建'),('001979','招商蛇口'),
    ('002271','东方雨虹'),('600176','中国巨石'),('601636','旗滨'),
]

TOP_N = 12

# 大盘
market = json.loads(curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh000001&scale=240&ma=no&datalen=60'))
mkt_c = [float(d['close']) for d in market]; mkt_d = [d['day'] for d in market]

print(f"🔍 扫描 {len(POOL)} 只...")
results = []

for code, name in POOL:
    try:
        sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
        url = f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=60'
        kl = json.loads(curl(url))
        c = [float(d['close']) for d in kl]; h = [float(d['high']) for d in kl]
        l = [float(d['low']) for d in kl]; v = [float(d['volume']) for d in kl]
        days = [d['day'] for d in kl]
        
        md = {d: cv for d, cv in zip(mkt_d, mkt_c)}
        mc = [md.get(d) for d in days]
        last = None
        for j in range(len(mc)):
            if mc[j] is None: mc[j] = last if last else c[j]
            else: last = mc[j]
        
        i = len(c) - 1; prev = c[i-1]
        
        # α(5日超额收益)
        sr5 = (c[i]/max(c[max(0,i-5)], 0.01) - 1)
        mr5 = (mc[i]/max(mc[max(0,i-5)], 0.01) - 1)
        a5 = sr5 - mr5
        
        # α_up持续天数
        aup = 0
        for j in range(i, max(0,i-20), -1):
            if j >= 5:
                s5 = (c[j]/max(c[max(0,j-5)],0.01)-1); m5 = (mc[j]/max(mc[max(0,j-5)],0.01)-1)
                if s5 - m5 > 0.015: aup += 1
                else: break
        
        # 趋势
        seg = c[max(0,i-30):i+1]
        ma10 = sum(seg[-10:])/10; ma20 = sum(seg[-20:])/20
        trend = (ma10/ma20 - 1) * 100
        
        # 量能
        v5 = sum(v[max(0,i-4):i+1])/5; v20 = sum(v[max(0,i-19):i+1])/20
        vr = v5/v20 if v20 else 1
        
        # 波动
        atr = sum(max(h[j]-l[j], abs(h[j]-c[j-1]), abs(l[j]-c[j-1])) for j in range(max(1,i-14),i+1))/14
        vola = atr/c[i]*100
        
        # === 综合打分 ===
        score = 0
        score += min(max(a5, -0.05), 0.12) / 0.12 * 40  # α 40%
        score += min(aup, 8) / 8 * 25                     # 持续性 25%
        score += min(max(trend, -5), 12) / 12 * 15        # 趋势 15%
        score += (min(max(vr, 0.5), 2.0)-0.5)/1.5 * 10   # 量能 10%
        score += max(0, (6 - vola)/6 * 10)                # 低波 10%
        
        results.append({
            'code': code, 'name': name, 'price': c[i], 'chg': (c[i]-prev)/prev*100,
            'score': score, 'a5': a5, 'aup': aup, 'trend': trend,
            'vr': vr, 'vola': vola,
            'reg': 'alpha_up' if aup>=2 else ('trending' if trend>3 else 'neutral'),
        })
    except:
        pass
    time.sleep(0.03)

results.sort(key=lambda x: -x['score'])

# ===== 输出 =====
now = datetime.now().strftime('%Y-%m-%d %H:%M')
date_str = results[0]['code'] and datetime.now().strftime('%Y-%m-%d') if results else ''
top = results[:TOP_N]

print(f"\n{'='*60}")
print(f"  📈 每日选股 Top {TOP_N} — {now}")
print(f"{'='*60}")
for idx, r in enumerate(top):
    a_s = f"+{r['a5']*100:.1f}%" if r['a5']>0 else f"{r['a5']*100:.1f}%"
    reg = '🟢强' if r['reg']=='alpha_up' else ('🟡趋' if r['reg']=='trending' else '⚪')
    print(f"  {idx+1:2d}. {r['name']:<6s} {r['code']}  ¥{r['price']:>7.2f}  得分{r['score']:>4.0f}  {reg}  α{a_s}  量{r['vr']:.1f}x  波{r['vola']:.1f}%")

# HTML报告
path = os.path.join(OUTPUT_DIR, f'每日选股_{datetime.now().strftime("%Y-%m-%d")}.html')
with open(path, 'w') as f:
    f.write(f'''<!DOCTYPE html><html lang="zh-CN">
<head><meta charset="UTF-8"><title>每日选股</title>
<style>body{{font-family:-apple-system,sans-serif;background:#f5f5f5;padding:20px;color:#333}}
.card{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 2px 6px rgba(0,0,0,.08)}}
h1{{text-align:center}}table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#f8f9fa}}.up{{color:#e74c3c}}.down{{color:#27ae60}}
.r{{display:inline-block;width:24px;height:24px;border-radius:50%;text-align:center;line-height:24px;font-size:12px;font-weight:700;color:#fff;margin-right:6px}}
.r1{{background:#e74c3c}}.r2{{background:#e67e22}}.r3{{background:#f39c12}}.r4{{background:#3498db}}
.note{{font-size:12px;color:#999;text-align:center;margin-top:16px;padding:12px;background:#fffbe6;border-radius:8px}}
.bar{{display:inline-block;height:12px;border-radius:3px;vertical-align:middle}}
</style></head><body>
<h1>📈 每日选股 Top {TOP_N}</h1>
<p style="text-align:center;color:#888;font-size:13px">{now} | 扫描{len(results)}只</p>
<div class="card"><table>
<tr><th>#</th><th>名称</th><th>代码</th><th>现价</th><th>涨跌</th><th>得分</th><th>α</th><th>趋势</th><th>量比</th><th>波动</th></tr>
''')
    for idx, r in enumerate(top):
        rc = 'r1' if idx<3 else ('r2' if idx<6 else 'r4')
        chg_c = 'up' if r['chg']>0 else 'down'
        a_c = 'up' if r['a5']>0 else 'down'
        score_w = max(10, r['score']); bar_w = int(score_w/80*200)
        f.write(f'<tr><td><span class="r {rc}">{idx+1}</span></td><td><b>{r["name"]}</b></td>')
        f.write(f'<td>{r["code"]}</td><td>¥{r["price"]:.2f}</td>')
        f.write(f'<td class="{chg_c}">{r["chg"]:+.2f}%</td>')
        f.write(f'<td><b>{r["score"]:.0f}</b> <span class="bar" style="width:{bar_w}px;background:{"#e74c3c" if r["score"]>40 else "#f39c12"}"></span></td>')
        f.write(f'<td class="{a_c}">{r["a5"]*100:+.1f}%</td>')
        f.write(f'<td>{r["trend"]:+.1f}%</td><td>{r["vr"]:.1f}x</td><td>{r["vola"]:.1f}%</td></tr>')
    f.write('</table></div>')
    f.write('<div class="note">⚠️ 每日更新排名，建议结合 diagnose.py 深度诊断。日线方向准确率约60%。</div>')
    f.write('</body></html>')

print(f'\n✅ {path}')
