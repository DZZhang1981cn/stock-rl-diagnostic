# -*- coding: utf-8 -*-
"""
A股多策略选股引擎 — 复刻 TSP 18 策略核心
用法: python3 脚本/strategy_scanner.py [--strategy all|boll|ma|turnover|limitup|reversal|oversold]
"""
import subprocess, json, time, sys, numpy as np
from collections import defaultdict

def curl(url):
    r = subprocess.run(['curl','-s','-L','--max-time','10',url],
                       capture_output=True, timeout=12)
    try: return r.stdout.decode('utf-8')
    except: return r.stdout.decode('gbk', errors='ignore')

# ==================== 股票池 ====================
POOL = [
    # 金融 (12)
    ('601398','工行'),('601939','建行'),('600036','招行'),('000001','平安银行'),('002142','宁波银行'),
    ('601318','平安'),('601628','国寿'),('601601','太保'),
    ('600030','中信证券'),('601211','国泰君安'),('601688','华泰'),('300059','东方财富'),
    # 消费 (12)
    ('600519','茅台'),('000858','五粮液'),('000568','老窖'),('600809','汾酒'),
    ('600887','伊利'),('603288','海天'),('000333','美的'),('000651','格力'),
    ('002594','比亚迪'),('600104','上汽'),('000625','长安'),('601633','长城'),
    # 医药 (8)
    ('600276','恒瑞'),('603259','药明'),('300122','智飞'),('000661','长春高新'),
    ('600436','片仔癀'),('300015','爱尔'),('300760','迈瑞'),('600085','同仁堂'),
    # 科技/AI (12)
    ('002415','海康'),('002230','科大讯飞'),('002049','紫光国微'),('000977','浪潮'),
    ('000938','紫光'),('000063','中兴'),('002475','立讯精密'),('600703','三安'),
    ('002236','大华'),('600745','闻泰'),('300124','汇川'),('688256','寒武纪'),
    # 新能源 (8)
    ('300750','宁德'),('601012','隆基'),('600438','通威'),('601615','明阳'),
    ('300274','阳光'),('300014','亿纬'),('002459','晶澳'),('688599','天合'),
    # 有色/资源 (12)
    ('601899','紫金'),('600489','中金'),('600988','赤峰'),('600547','山东'),
    ('000975','山金'),('601168','西部'),('601212','白银'),('600362','江铜'),
    ('000630','铜陵'),('000060','中金岭南'),('000807','云铝'),('002155','湖南黄金'),
    # 电力/能源 (10)
    ('600900','长电'),('601985','核电'),('600025','华能水电'),('600406','国电南瑞'),
    ('600886','国投'),('601991','大唐'),('600023','浙能'),('600011','华能'),
    ('600726','华电能'),('600236','桂冠'),
    # 基建/军工 (6)
    ('601668','中建'),('601390','中铁'),('600031','三一'),('600893','航发'),
    ('600760','沈飞'),('600150','船舶'),
    # 交通/物流 (5)
    ('601919','中远海控'),('600029','南航'),('601111','国航'),('002352','顺丰'),('601006','大秦'),
    # 商贸 (4)
    ('600415','小商品城'),('600755','厦门国贸'),('600058','五矿发展'),('600500','中化国际'),
    # 地产/建材 (4)
    ('600048','保利'),('600585','海螺'),('002271','东方雨虹'),('000786','北新建材'),
    # 中小活跃 (8)
    ('002241','歌尔'),('002456','欧菲光'),('300433','蓝思'),('601360','三六零'),
    ('600570','恒生'),('300502','新易盛'),('300308','中际旭创'),('002916','深南'),
    # 消费/农业 (5)
    ('002714','牧原'),('300498','温氏'),('002027','分众'),('300628','亿联'),('300896','爱美客'),
    # 更多 (10)
    ('600172','黄河'),('600028','石化'),('601088','神华'),('601728','电信'),('600050','联通'),
    ('600309','万华'),('600346','恒力'),('000301','盛虹'),('002555','三七'),('300418','昆仑'),
]  # ~108 stocks

print(f"🔍 多策略选股引擎 | 扫描 {len(POOL)} 只")

# ==================== 策略函数 ====================

def calc_indicators(close, high, low, volume, n=20):
    """通用指标计算"""
    c, h, l, v = close, high, low, volume
    last = c[-1]
    
    # MA
    ma5 = np.mean(c[-5:]); ma10 = np.mean(c[-10:])
    ma20 = np.mean(c[-20:]); ma60 = np.mean(c[-min(len(c),60):])
    
    # 布林
    bb_std = np.std(c[-n:])
    bb_mid = ma20; bb_up = bb_mid + 2*bb_std; bb_low = bb_mid - 2*bb_std
    
    # RSI(14)
    delta = np.diff(c[-15:])
    gain = np.sum(delta[delta>0]); loss = -np.sum(delta[delta<0])
    rsi = 100 - 100/(1 + gain/(loss+0.01))
    
    # 量比
    v5 = np.mean(v[-5:]); v20 = np.mean(v[-20:]); vr = v5/v20 if v20 else 1
    
    # 60日位置
    l60 = np.min(l[-min(len(c),60):]); h60 = np.max(h[-min(len(c),60):])
    pos60 = (last-l60)/(h60-l60)*100 if h60!=l60 else 50
    
    # 乖离
    bias60 = (last/ma60-1)*100
    
    # 换手率（用成交量/流通盘估算，粗略值）
    turnover = v[-1] / max(np.mean(v[-60:]), 1) * 5  # 5%均值=1
    
    # 涨停检测 (A股 ±10%)
    is_limit_up = (c[-1]/c[-2]-1) >= 0.095 if len(c)>1 else False
    
    # 连板数
    boards = 0
    for j in range(len(c)-1, 0, -1):
        if (c[j]/c[j-1]-1) >= 0.095: boards += 1
        else: break
    
    return {
        'last': last, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'bb_up': bb_up, 'bb_mid': bb_mid, 'bb_low': bb_low,
        'rsi': rsi, 'vr': vr, 'pos60': pos60, 'bias60': bias60,
        'turnover': turnover, 'is_limit_up': is_limit_up, 'boards': boards,
    }

# ===== 策略1: 布林突破 =====
def boll_breakout(c, h, l, v):
    ind = calc_indicators(c, h, l, v)
    breakout = ind['last'] > ind['bb_up'] * 0.99 and ind['vr'] >= 1.3
    if breakout:
        score = ind['vr']*40 + (ind['last']/c[-2]-1)*100*30 + min((ind['pos60']-40)/20, 1)*30
        return {'match': True, 'score': score, 'reason': f"突破上轨,量比{ind['vr']:.1f}x,位置{ind['pos60']:.0f}%"}
    return {'match': False, 'score': 0}

# ===== 策略2: 均线多头 =====
def bullish_alignment(c, h, l, v):
    ind = calc_indicators(c, h, l, v)
    align = ind['ma5'] > ind['ma10'] > ind['ma20'] > ind['ma60']
    mom_20d = (c[-1]/c[-21]-1)*100 if len(c)>20 else 0
    if align and mom_20d > 0:
        score = ind['pos60']*0.4 + ind['vr']*10 + min(mom_20d*3, 30)
        return {'match': True, 'score': score, 'reason': f"多头排列,20日+{mom_20d:.1f}%,位置{ind['pos60']:.0f}%"}
    return {'match': False, 'score': 0}

# ===== 策略3: 高换手拉升 =====
def high_turnover(c, h, l, v):
    ind = calc_indicators(c, h, l, v)
    chg = (c[-1]/c[-2]-1)*100 if len(c)>1 else 0
    if ind['turnover'] > 3 and chg > 2:
        score = ind['turnover']*6 + chg*5 + ind['vr']*10
        return {'match': True, 'score': score, 'reason': f"换手{ind['turnover']:.1f}%,涨{chg:.1f}%,量比{ind['vr']:.1f}x"}
    return {'match': False, 'score': 0}

# ===== 策略4: 连板股 =====
def consecutive_limits(c, h, l, v):
    ind = calc_indicators(c, h, l, v)
    if ind['boards'] >= 2 and ind['is_limit_up']:
        score = ind['boards']*30 + min(ind['turnover']*5, 30) + (ind['vr']-0.8)*10
        return {'match': True, 'score': score, 'reason': f"{ind['boards']}连板,换手{ind['turnover']:.1f}%,量比{ind['vr']:.1f}x"}
    return {'match': False, 'score': 0}

# ===== 策略5: 超跌反弹 =====
def oversold_bounce(c, h, l, v):
    ind = calc_indicators(c, h, l, v)
    chg = (c[-1]/c[-2]-1)*100 if len(c)>1 else 0
    oversold = ind['bias60'] < -15 or ind['rsi'] < 30 or ind['pos60'] < 15
    bouncing = chg > 0  # 需要当日已经出现反弹
    if oversold and bouncing:
        score = (1-ind['pos60']/100)*50 + (1-ind['rsi']/100)*20 + ind['vr']*8
        return {'match': True, 'score': score, 'reason': f"RSI{ind['rsi']:.0f},乖离{ind['bias60']:.0f}%,60日位{ind['pos60']:.0f}%"}
    return {'match': False, 'score': 0}

# ===== 策略6: 断板反包 =====  
def broken_board_recovery(c, h, l, v):
    ind = calc_indicators(c, h, l, v)
    chg = (c[-1]/c[-2]-1)*100 if len(c)>1 else 0
    # 简化版: 前3天内有涨停板 + 今天放量上涨 ≥3%
    had_limit = any((c[j]/c[j-1]-1)>=0.095 for j in range(len(c)-3, max(0,len(c)-1)))
    if had_limit and chg >= 3 and ind['vr'] > 1.2:
        score = chg*8 + ind['vr']*10
        return {'match': True, 'score': score, 'reason': f"断板反包,涨{chg:.1f}%,量比{ind['vr']:.1f}x"}
    return {'match': False, 'score': 0}


# ==================== 执行扫描 ====================
STRATEGIES = {
    'boll': ('布林突破', boll_breakout),
    'ma': ('均线多头', bullish_alignment),
    'turnover': ('高换手拉抈', high_turnover),
    'limitup': ('连板股', consecutive_limits),
    'reversal': ('断板反包', broken_board_recovery),
    'oversold': ('超跌反弹', oversold_bounce),
}

arg = sys.argv[2] if len(sys.argv)>2 else 'all'
selected = list(STRATEGIES.keys()) if arg=='all' else [s for s in arg.split(',') if s in STRATEGIES]

results = defaultdict(list)
for code, name in POOL:
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    try:
        kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=120'))
        if len(kl) < 60: continue
        c = np.array([float(d['close']) for d in kl])
        h = np.array([float(d['high']) for d in kl])
        l = np.array([float(d['low']) for d in kl])
        v = np.array([float(d['volume']) for d in kl])
        
        for sid in selected:
            sname, sfunc = STRATEGIES[sid]
            r = sfunc(c, h, l, v)
            if r['match']:
                results[sid].append({
                    'code': code, 'name': name, 'price': c[-1],
                    'chg': (c[-1]/c[-2]-1)*100, 'score': r['score'], 'reason': r['reason']
                })
        time.sleep(0.02)
    except: pass

# ==================== 输出 ====================
total_matches = sum(len(v) for v in results.values())
print(f"\n共命中 {total_matches} 次（{len(results)} 个策略）\n")

for sid in selected:
    sname, _ = STRATEGIES[sid]
    items = sorted(results[sid], key=lambda x: -x['score'])
    if not items:
        print(f"━━━ {sname}: 无匹配 ━━━\n")
        continue
    print(f"━━━ {sname} (命中 {len(items)} 只) ━━━")
    print(f"  {'代码':<8s} {'名称':<8s} {'现价':>7s} {'涨跌':>6s} {'得分':>6s}  理由")
    for item in items[:8]:
        print(f"  {item['code']:<8s} {item['name']:<8s} ¥{item['price']:>6.2f} {item['chg']:>+5.1f}% {item['score']:>5.0f}  {item['reason'][:50]}")
    print()

# ==================== 综合排名 ====================
all_hits = {}
for sid in selected:
    for item in results[sid]:
        key = item['code']
        if key not in all_hits or item['score'] > all_hits[key]['score']:
            all_hits[key] = item

ranked = sorted(all_hits.values(), key=lambda x: -x['score'])
print(f"━━━ 🏆 综合 Top 10 ━━━")
print(f"  {'#':>2s} {'代码':<8s} {'名称':<8s} {'现价':>7s} {'涨跌':>6s} {'得分':>6s}  理由")
for i, item in enumerate(ranked[:10]):
    print(f"  {i+1:>2d} {item['code']:<8s} {item['name']:<8s} ¥{item['price']:>6.2f} {item['chg']:>+5.1f}% {item['score']:>5.0f}  {item['reason'][:50]}")
