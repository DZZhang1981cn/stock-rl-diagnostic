#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前分析报告生成器 v1
用法: python3 脚本/premarket_report.py [日期]
输出: 导出文件/盘前分析_YYYY-MM-DD.html
"""
import subprocess, json, sys, os, time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.expanduser('~/Desktop/AI工作/脚本'))
from predict import predict_stock
from integrated_predict import predict_all, get_news_sentiment

# 策略扫描（轻量版）
def run_strategy_scan():
    """跑 4 个核心策略，返回命中列表"""
    import numpy as np
    POOL_SMALL = [
        ('601398','工行'),('600036','招行'),('601318','平安'),('601601','太保'),
        ('600030','中信'),('300059','东财'),('600519','茅台'),('000858','五粮液'),
        ('000333','美的'),('002594','比亚迪'),('600276','恒瑞'),('300760','迈瑞'),
        ('002415','海康'),('000977','浪潮'),('000938','紫光'),('000063','中兴'),
        ('300750','宁德'),('601012','隆基'),('600438','通威'),
        ('601899','紫金'),('600988','赤峰'),('601168','西部'),('000975','山金'),
        ('600900','长电'),('601985','核电'),('600886','国投'),
        ('601668','中建'),('600031','三一'),('600029','南航'),('601919','海控'),
        ('600415','小商品'),('600755','厦门国贸'),('600500','中化国际'),
        ('002241','歌尔'),('002456','欧菲光'),('300502','新易盛'),
        ('002714','牧原'),('300896','爱美客'),('002027','分众'),
        ('600309','万华'),('600028','石化'),('601088','神华'),('601728','电信'),
    ]
    
    def curl(u):
        r = subprocess.run(['curl','-s','-L','--max-time','10',u], capture_output=True, timeout=12)
        try: return r.stdout.decode('utf-8')
        except: return r.stdout.decode('gbk','ignore')
    
    def calc_all(c, h, l, v):
        n = len(c); last = c[-1]
        ma5 = np.mean(c[-5:]); ma10 = np.mean(c[-10:])
        ma20 = np.mean(c[-20:]); ma60 = np.mean(c[-min(n,60):])
        bb_std = np.std(c[-20:]); bb_up = ma20 + 2*bb_std
        delta = np.diff(c[-15:]); gain = np.sum(delta[delta>0]); loss = -np.sum(delta[delta<0])
        rsi = 100 - 100/(1 + gain/(loss+0.01))
        v5 = np.mean(v[-5:]); v20 = np.mean(v[-20:]); vr = v5/v20 if v20 else 1
        l60 = np.min(l[-min(n,60):]); h60 = np.max(h[-min(n,60):])
        pos60 = (last-l60)/(h60-l60)*100 if h60!=l60 else 50
        bias60 = (last/ma60-1)*100; chg = (last/c[-2]-1)*100 if len(c)>1 else 0
        turnover = v[-1]/max(np.mean(v[-60:]),1)*5
        return {'last':last,'ma5':ma5,'ma10':ma10,'ma20':ma20,'ma60':ma60,
                'bb_up':bb_up,'rsi':rsi,'vr':vr,'pos60':pos60,'bias60':bias60,
                'turnover':turnover,'chg':chg}
    
    hits = []
    for code, name in POOL_SMALL:
        try:
            sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
            kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=120'))
            if len(kl)<60: continue
            c=np.array([float(d['close']) for d in kl]); h=np.array([float(d['high']) for d in kl])
            l=np.array([float(d['low']) for d in kl]); v=np.array([float(d['volume']) for d in kl])
            ind = calc_all(c,h,l,v)
            
            strategies = []
            if ind['last']>ind['bb_up']*0.99 and ind['vr']>=1.3:
                strategies.append(('布林突破', ind['vr']*25 + ind['chg']*5))
            if ind['ma5']>ind['ma10']>ind['ma20']>ind['ma60'] and ind['chg']>0:
                strategies.append(('多头排列', ind['pos60']*0.4 + ind['chg']*5))
            if ind['turnover']>3 and ind['chg']>2:
                strategies.append(('高换手', ind['turnover']*6 + ind['chg']*5))
            if (ind['bias60']<-15 or ind['rsi']<30 or ind['pos60']<15) and ind['chg']>0:
                strategies.append(('超跌反弹', (1-ind['pos60']/100)*50 + ind['chg']*5))
            
            if strategies:
                best = max(strategies, key=lambda x: x[1])
                hits.append({'code':code,'name':name,'price':ind['last'],'chg':ind['chg'],
                             'strategy':best[0],'score':best[1],'rsi':ind['rsi'],'pos60':ind['pos60']})
        except: pass
        time.sleep(0.03)
    return sorted(hits, key=lambda x: -x['score'])[:10]

OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/导出文件')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url):
    r = subprocess.run(['curl','-s','-L','--max-time','10',url], capture_output=True, timeout=12)
    raw = r.stdout
    try: return raw.decode('utf-8')
    except: return raw.decode('gbk')

# ============== 分析标的 ==============
STOCKS = [
    ('600415','小商品城','持仓-商贸'),
    ('601212','白银有色','持仓-有色'),
    ('600029','南方航空','持仓-航空'),
    ('600172','黄河旋风','持仓-工业'),
    ('601991','大唐发电','持仓-电力'),
    ('600500','中化国际','观察-商贸'),
    ('002155','湖南黄金','观察-有色'),
]

HOLDINGS = {
    '600415': {'shares': 15200, 'cost': 11.558},
    '601212': {'shares': 10000, 'cost': 5.701},
    '600029': {'shares': 5200,  'cost': 5.561},
    '600172': {'shares': 2000,  'cost': 12.033},
    '601991': {'shares': 2000,  'cost': 6.763},
}

# ============== 拉取数据 ==============
now = datetime.now()
date_str = now.strftime('%Y-%m-%d')
print(f"📊 生成 {date_str} 盘前分析报告...")

# 实时行情
qt_codes = ','.join([f'sh{c}' if c.startswith('6') else f'sz{c}' for c in [s[0] for s in STOCKS]])
qt_raw = curl(f'http://qt.gtimg.cn/q={qt_codes}')

# 上证指数
mkt_raw = curl('http://qt.gtimg.cn/q=sh000001')
mkt_data = {}
for line in qt_raw.strip().split('\n'):
    if '=' not in line: continue
    code = line.split('=')[0].replace('v_sh','').replace('v_sz','')
    fields = line.split('"')[1].split('~') if '"' in line else []
    if len(fields) > 33:
        mkt_data[code] = {
            'name': fields[1], 'price': float(fields[3]),
            'prev_close': float(fields[4]), 'open': float(fields[5]),
            'high': float(fields[33]), 'low': float(fields[34]),
            'volume': float(fields[6]), 'amount': float(fields[37])/1e8 if fields[37] else 0,
        }

# 大盘
sh_fields = mkt_raw.split('"')[1].split('~') if '=' in mkt_raw else []
sh_idx = float(sh_fields[3]) if len(sh_fields) > 3 else 0
sh_chg = (float(sh_fields[3])/float(sh_fields[4])-1)*100 if len(sh_fields) > 4 else 0

# ============== 逐票预测 ==============
results = []
for code, name, tag in STOCKS:
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    try:
        kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=200'))
        close = np.array([float(d['close']) for d in kl])
        high  = np.array([float(d['high']) for d in kl])
        low   = np.array([float(d['low']) for d in kl])
        volume = np.array([float(d['volume']) for d in kl])
        
        pred = predict_stock(close, high, low, volume)
        
        qt = mkt_data.get(code, {})
        price = qt.get('price', close[-1])
        prev = qt.get('prev_close', close[-2] if len(close) > 1 else price)
        chg = (price/prev-1)*100 if prev else 0
        
        # 持仓盈亏
        holding = HOLDINGS.get(code)
        if holding:
            pnl = (price - holding['cost']) * holding['shares']
            pnl_pct = (price/holding['cost']-1)*100
            mkt_val = price * holding['shares']
        else:
            pnl = pnl_pct = mkt_val = 0
        
        # 超跌信号
        oversold_info = ''
        if pred['has_oversold']:
            oversold_info = '🔥 ' + ', '.join(pred['oversold_signals'])
        
        results.append({
            'code': code, 'name': name, 'tag': tag, 'price': price, 'chg': chg,
            'pnl': pnl, 'pnl_pct': pnl_pct, 'mkt_val': mkt_val,
            'pred': pred, 'oversold_info': oversold_info,
        })
    except Exception as e:
        print(f"  ⚠️ {code} {name}: {e}")
    time.sleep(0.05)

# ============== 生成 HTML ==============
total_mkt_val = sum(r['mkt_val'] for r in results)
total_pnl = sum(r['pnl'] for r in results)
total_cost = sum(HOLDINGS[c]['shares']*HOLDINGS[c]['cost'] for c in HOLDINGS)
total_pnl_pct = (total_mkt_val/total_cost-1)*100 if total_cost else 0

# 策略扫描
scan_hits = run_strategy_scan()

html = f'''<!DOCTYPE html><html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>盘前分析 {date_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f0f2f5;color:#1a1a2e;line-height:1.6;padding:20px}}
.card{{background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
h1{{text-align:center;font-size:22px;margin-bottom:4px}}
h2{{font-size:16px;margin-bottom:16px;color:#555;border-bottom:2px solid #667eea;padding-bottom:8px}}
h3{{font-size:14px;margin:12px 0 8px;color:#444}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:8px 12px;text-align:right;border-bottom:1px solid #eee}}
th{{background:#f8f9fa;font-weight:600;color:#555;text-align:center}}
td:first-child,th:first-child{{text-align:left}}
tr:hover{{background:#f8f9ff}}
.up{{color:#e74c3c;font-weight:600}}.down{{color:#27ae60;font-weight:600}}
.neutral{{color:#888}}
.tag{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;margin-right:4px}}
.tag-hold{{background:#e8f5e9;color:#2e7d32}}
.tag-watch{{background:#fff3e0;color:#e65100}}
.badge{{display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700}}
.bull{{background:#fee;color:#c0392b}}.bear{{background:#efe;color:#27ae60}}.warn{{background:#ffeaa7;color:#d68910}}
.signal{{padding:8px 12px;border-radius:6px;margin:6px 0;font-size:13px}}
.signal-oversold{{background:#ffe0e0;border-left:3px solid #e74c3c}}
.summary-box{{display:flex;gap:20px;flex-wrap:wrap}}
.summary-item{{flex:1;min-width:120px;text-align:center;padding:16px;background:#f8f9fa;border-radius:8px}}
.summary-val{{font-size:24px;font-weight:700}}
.footer{{text-align:center;font-size:12px;color:#999;margin-top:20px}}
.bar{{display:inline-block;height:14px;border-radius:3px;vertical-align:middle;margin-right:4px}}
</style></head><body>
<h1>📊 盘前分析报告</h1>
<p style="text-align:center;color:#888;font-size:13px">{date_str} | 上证 {sh_idx:.0f} ({sh_chg:+.2f}%)</p>

<div class="card">
<h2>📈 持仓总览</h2>
<div class="summary-box">
<div class="summary-item"><div class="summary-val">¥{total_mkt_val:,.0f}</div><div style="font-size:12px;color:#888">持仓市值</div></div>
<div class="summary-item"><div class="summary-val" style="color:{'#e74c3c' if total_pnl>=0 else '#27ae60'}">{total_pnl:+,.0f}</div><div style="font-size:12px;color:#888">浮动盈亏</div></div>
<div class="summary-item"><div class="summary-val" style="color:{'#e74c3c' if total_pnl_pct>=0 else '#27ae60'}">{total_pnl_pct:+.2f}%</div><div style="font-size:12px;color:#888">盈亏率</div></div>
</div>

<table>
<tr><th>代码</th><th>名称</th><th>类型</th><th>现价</th><th>涨跌</th><th>预测方向</th><th>1日预测</th><th>5日预测</th><th>超跌信号</th><th>持仓盈亏</th></tr>
'''

for r in results:
    pred = r['pred']
    chg_class = 'up' if r['chg']>0 else ('down' if r['chg']<0 else 'neutral')
    dir_class = 'up' if pred['composite']>0.5 else ('down' if pred['composite']<0.3 else 'neutral')
    tag_class = 'tag-hold' if '持仓' in r['tag'] else 'tag-watch'
    pnl_class = 'up' if r['pnl']>0 else ('down' if r['pnl']<0 else 'neutral')
    
    has_os = '🔥' if pred['has_oversold'] else ''
    
    html += f'''<tr>
<td><b>{r['code']}</b></td><td><b>{r['name']}</b></td>
<td><span class="tag {tag_class}">{r['tag']}</span></td>
<td>¥{r['price']:.2f}</td><td class="{chg_class}">{r['chg']:+.2f}%</td>
<td class="{dir_class}">{pred['direction']}</td>
<td>¥{pred['price_1d']:.2f}</td><td>¥{pred['price_5d']:.2f}</td>
<td>{has_os}{r['oversold_info']}</td>
<td class="{pnl_class}">{r['pnl']:+,.0f} ({r['pnl_pct']:+.1f}%)</td>
</tr>'''

html += '</table></div>'

# 超跌信号汇总
oversold_stocks = [r for r in results if r['pred']['has_oversold']]
if oversold_stocks:
    html += '<div class="card"><h2>🔥 超跌反弹信号</h2>'
    for r in oversold_stocks:
        pred = r['pred']
        d = pred['detail']['oversold']
        html += f'''<div class="signal signal-oversold">
<b>{r['name']} ({r['code']})</b> — RSI={d['rsi']:.0f}, 60日位置={d['pos_60d']:.0f}%, 得分={pred['oversold_score']}/25<br>
<small>{r['oversold_info']}</small></div>'''
    html += '</div>'

# 维度详情
html += '<div class="card"><h2>📊 维度详情</h2><table>'
html += '<tr><th>股票</th><th>MA趋势</th><th>5日动量</th><th>均值回归</th><th>加速度</th><th>线性</th><th>超跌</th><th>综合</th></tr>'
for r in results:
    d = r['pred']['detail']
    html += f'''<tr><td><b>{r['name']}</b></td>
<td>{d['trend']['score']}/25</td><td>{d['momentum_5d']['score']}/25</td>
<td>{d['regression']['score']}/20</td><td>{d['acceleration']['score']}/15</td>
<td>{d['linear']['score']}/15</td><td>{d['oversold']['score']}/25</td>
<td><b>{r['pred']['composite']:.2f}</b></td></tr>'''
html += '</table></div>'

# 策略扫描
if scan_hits:
    html += '<div class="card"><h2>🔍 策略扫描 Top 10</h2><table>'
    html += '<tr><th>#</th><th>股票</th><th>现价</th><th>涨跌</th><th>策略</th><th>得分</th><th>信号</th></tr>'
    for i, h in enumerate(scan_hits):
        chg_c = 'up' if h['chg']>0 else 'down'
        strat_c = 'bull' if h['strategy'] in ('布林突破','高换手') else ('warn' if h['strategy']=='超跌反弹' else '')
        html += f'''<tr><td>{i+1}</td><td><b>{h['name']}</b> <small>{h['code']}</small></td>
<td>¥{h['price']:.2f}</td><td class="{chg_c}">{h['chg']:+.1f}%</td>
<td><span class="badge {strat_c}">{h['strategy']}</span></td>
<td>{h['score']:.0f}</td><td>RSI{h['rsi']:.0f}</td></tr>'''
    html += '</table></div>'

# 风险评估
html += '<div class="card"><h2>⚠️ 风险提示</h2><table>'
html += '<tr><th>股票</th><th>风险</th><th>建议</th></tr>'
for r in results:
    pred = r['pred']
    d = pred['detail']
    risk = ''; advice = ''
    if d['oversold']['rsi'] < 30:
        risk = '超卖，反弹概率高'
        advice = '不当割，持有等反弹'
    elif d['oversold']['rsi'] > 75:
        risk = '超买，回调风险'
        advice = '考虑减仓止盈'
    elif pred['composite'] < 0.3:
        risk = '多方信号弱'
        advice = '观望不加仓'
    elif pred['composite'] > 0.7:
        risk = '多方信号强'
        advice = '持有或小幅加仓'
    else:
        risk = '正常'
        advice = '持仓不动'
    
    html += f'''<tr><td><b>{r['name']}</b></td><td>{risk}</td><td>{advice}</td></tr>'''
html += '</table></div>'

html += f'''<div class="footer">
<p>生成时间: {now.strftime("%Y-%m-%d %H:%M")} | 数据来源: 腾讯行情 + Sina K线</p>
<p style="margin-top:4px">⚠️ 本报告由自动化脚本生成，仅供参考，不构成投资建议</p>
</div></body></html>'''

path = os.path.join(OUTPUT_DIR, f'盘前分析_{date_str}.html')
with open(path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'✅ 报告已生成: 导出文件/盘前分析_{date_str}.html')
print(f'   持仓市值: ¥{total_mkt_val:,.0f} | 浮动盈亏: {total_pnl:+,.0f}')
