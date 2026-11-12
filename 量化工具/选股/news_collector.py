# -*- coding: utf-8 -*-
"""
中文财经新闻聚合采集器
数据源:
  1. 新浪财经要闻 (lid=2509) - 国际/国内混合
  2. 新浪实时财经 (lid=2516) - 实时更新
  3. 新闻联播文字稿 (Obsidian) - 政策信号
输出: news_collection.jsonl
"""
import subprocess, json, os, re, time
from datetime import datetime

OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/资料')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url):
    r = subprocess.run(['curl','-s','-L','--max-time','10',url], capture_output=True, timeout=12)
    try: return r.stdout.decode('utf-8')
    except: return r.stdout.decode('gbk', errors='ignore')

articles = []
seen = set()

# ===== 源1: 新浪要闻 (lid=2509) =====
print("📥 新浪财经要闻...")
try:
    data = json.loads(curl('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=30&page=1'))
    for item in data['result']['data']:
        title = item.get('title','').strip()
        if title and title not in seen:
            seen.add(title)
            articles.append({
                'source': 'sina_finance',
                'title': title,
                'url': item.get('url',''),
                'time': item.get('ctime',''),
                'intro': item.get('intro',''),
            })
    print(f"  +{len(articles)} 条")
except: pass

# ===== 源2: 新浪实时财经 (lid=2516) =====
print("📥 新浪实时财经...")
try:
    data = json.loads(curl('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=30&page=1'))
    for item in data['result']['data']:
        title = item.get('title','').strip()
        if title and title not in seen:
            seen.add(title)
            articles.append({
                'source': 'sina_realtime',
                'title': title,
                'url': item.get('url',''),
                'time': item.get('ctime',''),
                'intro': item.get('intro',''),
            })
    print(f"  +{len(articles)} 条")
except: pass

# ===== 源3: 新闻联播最近3期 =====
print("📥 新闻联播...")
xwlb_dir = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ZZH图书馆/新闻联播/")
try:
    files = sorted([f for f in os.listdir(xwlb_dir) if f.endswith('.md')])[-3:]
    for fname in files:
        with open(os.path.join(xwlb_dir, fname), 'r', encoding='utf-8') as f:
            content = f.read()
        # 按 ## 标题分段
        sections = [s.strip() for s in content.split('## ') if s.strip() and len(s) > 20]
        for sec in sections:
            title = sec.split('\n')[0][:100].strip()
            if title and title not in seen:
                seen.add(title)
                articles.append({
                    'source': 'xwlb',
                    'title': title,
                    'url': '',
                    'time': fname.replace('_新闻联播.md',''),
                    'intro': sec[:200],
                })
    print(f"  +{len(articles)} 条 (新闻联播)")
except: pass

# ===== 保存 =====
out_path = os.path.join(OUTPUT_DIR, f'news_collection_{datetime.now().strftime("%Y%m%d")}.jsonl')
with open(out_path, 'w', encoding='utf-8') as f:
    for a in articles:
        f.write(json.dumps(a, ensure_ascii=False) + '\n')

print(f"\n✅ 总计 {len(articles)} 条 | 保存: 资料/news_collection_{datetime.now().strftime('%Y%m%d')}.jsonl")

# 按来源统计
from collections import Counter
srcs = Counter(a['source'] for a in articles)
for s, c in srcs.items():
    print(f"  {s}: {c} 条")
