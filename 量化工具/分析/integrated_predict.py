# -*- coding: utf-8 -*-
"""
综合预测引擎 — 融合 Qlib基线 + 新闻情感 + 手工多模型
"""
import subprocess, json, os, sys, numpy as np
sys.path.insert(0, os.path.expanduser('~/Desktop/AI工作/脚本'))
from predict import predict_stock
try:
    from qwen_sentiment import analyze_sentiment, load_model as load_qwen
    HAS_QWEN = True
except:
    HAS_QWEN = False

def curl(url):
    r = subprocess.run(['curl','-s','-L','--max-time','10',url], capture_output=True, timeout=12)
    try: return r.stdout.decode('utf-8')
    except: return r.stdout.decode('gbk', errors='ignore')

# ===== 1. 新闻情感 =====
def get_news_sentiment():
    SECTOR_KW = {
        '商贸': ['义乌','小商品','外贸','进出口','跨境电商','长三角','供应链','物流','中欧班列'],
        '有色': ['黄金','白银','铜','铝','稀土','贵金属','矿产资源','有色金属','矿业'],
        '电力': ['电力','能源','节能降碳','碳中和','新能源','光伏','风电','储能','电网'],
        '航空': ['航空','机场','民航','航班','航线','机票','出行'],
        '消费': ['消费','零售','以旧换新','家电','汽车','补贴'],
        'AI': ['人工智能','AI','算力','芯片','半导体','数字经济'],
        '金融': ['银行','保险','券商','资本市场','降息','利率','货币政策'],
    }
    POS = ['增长','创新高','突破','利好','盈利','改善','回暖','复苏','支持','加大','推进','加快','扩大','积极','提升','超预期']
    NEG = ['下跌','亏损','下滑','风险','下降','压力','挑战','制裁','关税','贸易战','违约','暴雷','跌停','减值']
    
    articles = []
    try:
        data = json.loads(curl('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=20&page=1'))
        for item in data['result']['data']:
            articles.append(item.get('title','')+' '+item.get('intro',''))
        data = json.loads(curl('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=20&page=1'))
        for item in data['result']['data']:
            articles.append(item.get('title','')+' '+item.get('intro',''))
    except: pass
    
    xwlb_dir = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆/新闻联播/")
    try:
        for fname in sorted(os.listdir(xwlb_dir))[-3:]:
            with open(os.path.join(xwlb_dir, fname)) as f:
                articles.append(f.read()[:5000])
    except: pass
    
    signals = {}
    for sector, keywords in SECTOR_KW.items():
        scores = []
        for text in articles:
            if any(kw in text for kw in keywords):
                p = sum(1 for w in POS if w in text)
                n = sum(1 for w in NEG if w in text)
                scores.append(1.0 if p>n else (0.0 if n>p else 0.5))
        if scores:
            avg = sum(scores)/len(scores)
            signals[sector] = {'sentiment': avg, 'mentions': len(scores)}
        else:
            signals[sector] = {'sentiment': 0.5, 'mentions': 0}
    return signals

# ===== 2. 持仓映射 =====
HOLDINGS = {
    '600415': {'name':'小商品城','sector':'商贸','shares':15200,'cost':11.558},
    '601212': {'name':'白银有色','sector':'有色','shares':10000,'cost':5.701},
    '600029': {'name':'南方航空','sector':'航空','shares':5200,'cost':5.561},
    '600172': {'name':'黄河旋风','sector':'工业','shares':2000,'cost':12.033},
    '601991': {'name':'大唐发电','sector':'电力','shares':2000,'cost':6.763},
    '600500': {'name':'中化国际','sector':'商贸','shares':0,'cost':0},
    '002155': {'name':'湖南黄金','sector':'有色','shares':0,'cost':0},
}

# ===== 3. 综合预测 =====
news_signals = get_news_sentiment() if __name__ == '__main__' else {}

def predict_all(holdings=None):
    if holdings is None: holdings = HOLDINGS
    
    market_raw = curl('http://qt.gtimg.cn/q=sh000001')
    sh_fields = market_raw.split('"')[1].split('~') if '=' in market_raw else ['0']*40
    sh_idx = float(sh_fields[3]) if len(sh_fields)>3 else 3000
    sh_chg = (float(sh_fields[3])/float(sh_fields[4])-1)*100 if len(sh_fields)>4 else 0
    
    results = []
    for code, info in holdings.items():
        sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
        try:
            kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=200'))
            close = np.array([float(d['close']) for d in kl])
            high  = np.array([float(d['high']) for d in kl])
            low   = np.array([float(d['low']) for d in kl])
            volume = np.array([float(d['volume']) for d in kl])
            
            pred = predict_stock(close, high, low, volume)
            
            # 实时价格
            qt_raw = curl(f'http://qt.gtimg.cn/q={sym}')
            price = close[-1]
            prev = close[-2] if len(close)>1 else price
            try:
                f = qt_raw.split('"')[1].split('~')
                if len(f)>3: price=float(f[3]); prev=float(f[4])
            except: pass
            chg = (price/prev-1)*100
            
            # 新闻修正
            ns = news_signals.get(info['sector'], {}).get('sentiment', 0.5)
            composite = pred['composite'] * 0.7 + (ns * 0.3)  # 70%技术 + 30%新闻
            
            # 持仓盈亏
            if info['shares'] > 0:
                pnl = (price - info['cost']) * info['shares']
                pnl_pct = (price/info['cost']-1)*100
            else:
                pnl = pnl_pct = 0
            
            results.append({
                'code': code, 'name': info['name'], 'price': price, 'chg': chg,
                'direction': pred['direction'], 'composite': composite,
                'price_1d': pred['price_1d'], 'price_5d': pred['price_5d'],
                'news_sentiment': ns, 'has_oversold': pred['has_oversold'],
                'oversold_signals': pred['oversold_signals'],
                'pnl': pnl, 'pnl_pct': pnl_pct,
            })
        except Exception as e:
            print(f'  ⚠️ {code}: {e}')
    
    return results, sh_idx, sh_chg

if __name__ == '__main__':
    results, sh_idx, sh_chg = predict_all()
    print(f'\n 综合预测 ({len(results)} 票) | 上证 {sh_idx:.0f} ({sh_chg:+.1f}%)')
    print(f' {"代码":<8s} {"名称":<8s} {"现价":>7s} {"方向":>6s} {"1日":>7s} {"5日":>7s} {"新闻":>5s} {"超跌"}')
    print('-'*65)
    for r in results:
        ns = f'{r["news_sentiment"]:.2f}'
        os_str = '🔥' if r['has_oversold'] else ''
        print(f' {r["code"]:<8s} {r["name"]:<8s} ¥{r["price"]:>6.2f} {r["direction"]:>6s} ¥{r["price_1d"]:>6.2f} ¥{r["price_5d"]:>6.2f} {ns:>5s}  {os_str}')
