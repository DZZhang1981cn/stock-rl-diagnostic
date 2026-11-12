# -*- coding: utf-8 -*-
"""
FinGPT 中文金融情感分析 — 新闻联播信号提取 + 新浪财经新闻
依赖: transformers, torch, peft
"""
import subprocess, json, os, sys
import re

def curl(url):
    r = subprocess.run(['curl','-s','-L','--max-time','10',url], capture_output=True, timeout=12)
    try: return r.stdout.decode('utf-8')
    except: return r.stdout.decode('gbk', errors='ignore')

SECTOR_KEYWORDS = {
    '商贸': ['义乌','小商品','外贸','进出口','跨境电商','长三角','供应链','物流','中欧班列','数贸'],
    '有色': ['黄金','白银','铜','铝','稀土','贵金属','矿产资源','有色金属','矿业'],
    '电力': ['电力','能源','节能降碳','碳中和','碳达峰','新能源','光伏','风电','储能','电网','发电'],
    '航空': ['航空','机场','民航','航班','航线','机票','出行','旅游'],
    '消费': ['消费','零售','以旧换新','家电','汽车','补贴','内需'],
    'AI/科技': ['人工智能','AI','算力','芯片','半导体','数字经济','数字化转型'],
    '地产': ['房地产','住房','保障房','城中村','楼市'],
    '金融': ['银行','保险','券商','资本市场','降息','利率','货币政策','LPR'],
}

def rule_based_sentiment(text, sector=None):
    """基于规则的情感分析 (FinGPT 加载前先用)"""
    positive = ['增长','创新高','突破','利好','盈利','改善','回暖','复苏','支持','加大','推进','加快','扩大','积极','提升','超预期','涨停']
    negative = ['下跌','亏损','下滑','风险','下降','压力','挑战','制裁','关税','贸易战','违约','暴雷','跌停','减值','警告']
    
    pos = sum(1 for w in positive if w in text)
    neg = sum(1 for w in negative if w in text)
    
    if pos > neg: return 'positive', min(pos / max(len(positive), 1), 1.0)
    elif neg > pos: return 'negative', min(neg / max(len(negative), 1), 1.0)
    return 'neutral', 0.5

def extract_sector_signals(articles):
    """从新闻中提取板块信号"""
    signals = {}
    for sector, keywords in SECTOR_KEYWORDS.items():
        matches = 0
        sentiment_scores = []
        for a in articles:
            text = a.get('title','') + ' ' + a.get('intro','')
            if any(kw in text for kw in keywords):
                matches += 1
                sent, score = rule_based_sentiment(text, sector)
                sentiment_scores.append(1.0 if sent=='positive' else (0.0 if sent=='negative' else 0.5))
        
        if matches > 0:
            avg_sent = sum(sentiment_scores) / len(sentiment_scores)
            signals[sector] = {
                'mentions': matches,
                'sentiment': avg_sent,
                'direction': '🟢' if avg_sent > 0.55 else ('🔴' if avg_sent < 0.45 else '⚪'),
                'intensity': min(matches / 5, 1.0)  # 0-1, normalized
            }
    
    return signals

if __name__ == '__main__':
    # 拉新闻
    print("📥 采集新闻...")
    articles = []
    
    # 新浪实时
    data = json.loads(curl('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=20&page=1'))
    for item in data['result']['data']:
        articles.append({'title': item.get('title',''), 'intro': item.get('intro',''), 'source': 'sina'})
    
    # 新浪要闻
    data = json.loads(curl('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=20&page=1'))
    for item in data['result']['data']:
        articles.append({'title': item.get('title',''), 'intro': item.get('intro',''), 'source': 'sina'})
    
    # 新闻联播
    xwlb_dir = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆/新闻联播/")
    for fname in sorted(os.listdir(xwlb_dir))[-3:]:
        with open(os.path.join(xwlb_dir, fname)) as f:
            content = f.read()
        sections = [s.strip() for s in content.split('## ') if s.strip() and len(s)>20]
        for sec in sections:
            articles.append({'title': sec.split('\n')[0][:200], 'intro': sec[:300], 'source': 'xwlb'})
    
    # 分析
    signals = extract_sector_signals(articles)
    
    print(f"\n{'='*60}")
    print(f"  📊 板块信号分析 (基于 {len(articles)} 条新闻)")
    print(f"{'='*60}")
    print(f"  {'板块':<10s} {'提及':>4s} {'情感':>6s} {'方向':>4s} {'强度'}")
    print(f"  {'-'*40}")
    
    sorted_signals = sorted(signals.items(), key=lambda x: -x[1]['intensity'] * x[1]['sentiment'])
    for sector, s in sorted_signals:
        bar = '█' * int(s['intensity']*10)
        print(f"  {sector:<10s} {s['mentions']:>4d} {s['sentiment']:>5.2f}  {s['direction']}   {bar}")
    
    # 持仓相关信号
    print(f"\n  {'='*60}")
    print(f"  持仓相关")
    print(f"  {'='*60}")
    portfolio_sectors = {
        '600415 小商品城': '商贸',
        '601212 白银有色': '有色',
        '600029 南方航空': '航空',
        '600172 黄河旋风': '工业',
        '601991 大唐发电': '电力',
    }
    for stock, sector in portfolio_sectors.items():
        s = signals.get(sector, {})
        if s:
            print(f"  {stock}: {s['direction']} 提及{s['mentions']}次, 情感{s['sentiment']:.2f}")
        else:
            print(f"  {stock}: ⚪ 无相关信号")
