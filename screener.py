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
    # 金融 (银行/保险/券商)
    ('601398','工行'),('601939','建行'),('601288','农行'),('601988','中行'),('600036','招行'),
    ('601328','交行'),('600016','民生'),('000001','平安银行'),('002142','宁波银行'),('600000','浦发'),
    ('601166','兴业'),('600919','江苏银行'),('601818','光大'),('601318','平安'),('601628','国寿'),
    ('601601','太保'),('601336','新华保险'),('600030','中信证券'),('601211','国泰君安'),
    ('600837','海通证券'),('601688','华泰证券'),('000776','广发证券'),('300059','东方财富'),
    # 消费 (白酒/食品/家电/汽车)
    ('600519','茅台'),('000858','五粮液'),('000568','老窖'),('600809','汾酒'),('002304','洋河'),
    ('600887','伊利'),('000895','双汇'),('603288','海天'),('600690','海尔'),('000333','美的'),
    ('000651','格力'),('002594','比亚迪'),('600104','上汽'),('000625','长安'),('601633','长城'),
    ('000800','一汽解放'),('600660','福耀'),('601799','星宇'),('600741','华域'),
    # 医药
    ('600276','恒瑞'),('603259','药明康德'),('300122','智飞生物'),('000661','长春高新'),
    ('600436','片仔癀'),('000538','云南白药'),('600196','复星医药'),('300015','爱尔眼科'),
    ('002007','华兰生物'),('300760','迈瑞医疗'),('600085','同仁堂'),('002001','新和成'),
    # 科技 (芯片/软件/AI)
    ('002415','海康'),('002230','科大讯飞'),('002049','紫光国微'),('000977','浪潮信息'),
    ('688981','中芯国际'),('688111','金山办公'),('688012','中微公司'),('600745','闻泰科技'),
    ('300124','汇川技术'),('002475','立讯精密'),('000063','中兴通讯'),('600703','三安光电'),
    ('000100','TCL科技'),('002236','大华股份'),('300274','阳光电源'),
    # 能源/资源
    ('601857','中石油'),('600028','中石化'),('601088','神华'),('601225','陕煤'),
    ('601899','紫金矿业'),('600019','宝钢'),('002460','赣锋锂业'),('600309','万华化学'),
    ('600585','海螺水泥'),('601636','旗滨集团'),('000012','南玻A'),('600176','中国巨石'),
    ('002271','东方雨虹'),('000786','北新建材'),
    # 新能源
    ('300750','宁德时代'),('601012','隆基绿能'),('600438','通威股份'),('601615','明阳智能'),
    ('002129','中环股份'),('601689','拓普集团'),('002050','三花智控'),('002920','德赛西威'),
    ('300496','中科创达'),
    # 电力/公用
    ('600900','长电'),('601985','核电'),('600025','华能水电'),('600406','国电南瑞'),
    ('003816','广核'),('600886','国投电力'),
    # 基建/地产
    ('601668','中国建筑'),('601390','中国中铁'),('601800','中国交建'),('601186','中国铁建'),
    ('600048','保利发展'),('001979','招商蛇口'),('000002','万科A'),('600383','金地集团'),
    ('600031','三一重工'),('000157','中联重科'),('601100','恒立液压'),
    # 交通/物流
    ('601919','中远海控'),('600029','南航'),('601111','国航'),('600115','东航'),
    ('600009','上海机场'),('002352','顺丰控股'),('601006','大秦铁路'),
    # 农业/牧业
    ('002714','牧原股份'),('000876','新希望'),('300498','温氏股份'),('002385','大北农'),
    # 军工
    ('600893','航发动力'),('600760','中航沈飞'),('002013','中航机电'),
    # 更多中小盘活跃票
    ('002241','歌尔股份'),('000938','紫光股份'),('002456','欧菲光'),('300433','蓝思科技'),
    ('601360','三六零'),('002602','世纪华通'),('300418','昆仑万维'),('002555','三七互娱'),
    ('600570','恒生电子'),('002410','广联达'),('300033','同花顺'),
    ('601012','隆基绿能'),('600905','三峡能源'),('601728','中国电信'),
    ('688599','天合光能'),('688005','容百科技'),('300014','亿纬锂能'),
    ('600150','中国船舶'),('601989','中国重工'),('600685','中船防务'),
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
        
        # === 判断牛熊 ===
        mkt_ma10 = sum(mkt_c[-10:])/10; mkt_ma20 = sum(mkt_c[-20:])/20
        is_bull = mkt_ma10 > mkt_ma20

        # === 新评分逻辑 ===
        score = 0
        
        # 1. α 核心 (50分)
        if a5 > 0.06: score += 50
        elif a5 > 0.03: score += 40
        elif a5 > 0: score += 25
        elif a5 > -0.03: score += 10
        else: score += 0   # α为负的不考虑
        
        # 2. 量能 + 波动 (20分，牛熊不同)
        if is_bull:
            # 牛市: 正常量 + 低波
            if 0.8 < vr < 1.5: score += 10
            elif 0.5 < vr < 2.0: score += 5
            if vola < 5: score += 10
            elif vola < 8: score += 5
        else:
            # 熊市: 放量 + 高波(有资金异动)
            if vr > 1.2: score += 10
            elif vr > 0.8: score += 5
            if vola > 3: score += 10
            elif vola > 2: score += 5
        
        # 3. α 持续性 (20分)
        score += min(aup, 10) / 10 * 20
        
        # 4. 趋势加分 (10分)
        if trend > 5: score += 10
        elif trend > 0: score += 5

        results.append({
            'code': code, 'name': name, 'price': c[i], 'chg': (c[i]-prev)/prev*100,
            'score': score, 'a5': a5, 'aup': aup, 'trend': trend,
            'vr': vr, 'vola': vola, 'is_bull': is_bull,
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
mkt_label = '🐂 牛市' if results and results[0]['is_bull'] else '🐻 熊市'
print(f"  📈 每日选股 Top {TOP_N} — {now} | {mkt_label}")
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
