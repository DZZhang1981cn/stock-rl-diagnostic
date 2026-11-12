# -*- coding: utf-8 -*-
"""
Qwen2.5-1.5B 金融情感分析 — FinGPT 替代方案
"""
import subprocess, json, os, re, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

MODEL_PATH = '/tmp/qwen_local'
_device = None
_model = None
_tokenizer = None

def load_model():
    global _model, _tokenizer, _device
    if _model is not None: return
    _device = 'mps' if torch.backends.mps.is_available() else 'cpu'
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    _model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, torch_dtype=torch.float16, device_map=_device, trust_remote_code=True)
    print(f'Qwen loaded on {_device}')

def analyze_sentiment(text):
    """对单条文本做情感分析"""
    load_model()
    prompt = f'判断财经新闻情感，只回复一个字（积极/消极/中性）：\n{text[:200]}\n情感：'
    inputs = _tokenizer(prompt, return_tensors='pt').to(_device)
    with torch.no_grad():
        outputs = _model.generate(**inputs, max_new_tokens=3, do_sample=False, pad_token_id=_tokenizer.eos_token_id)
    result = _tokenizer.decode(outputs[0], skip_special_tokens=True)
    # 提取第一个情感词
    for word in ['积极','消极','中性']:
        if word in result[-10:]:
            return word
    return '中性'

def analyze_news_batch(articles):
    """批量分析"""
    load_model()
    sentiments = {}
    for i, article in enumerate(articles):
        text = article.get('title','')[:80]
        if not text: continue
        sentiment = analyze_sentiment(text)
        key = article.get('title','')[:30]
        sentiments[key] = sentiment
        if i % 5 == 0:
            print(f'  [{i+1}/{len(articles)}] {sentiment}: {text[:40]}...')
    return sentiments

def sector_from_news(articles):
    """从新闻中提取板块情感信号"""
    load_model()
    SECTORS = {
        '商贸':'义乌|小商品|外贸|进出口|跨境电商|长三角|供应链|物流|中欧班列|数贸',
        '有色':'黄金|白银|铜|铝|稀土|贵金属|矿产',
        '电力':'电力|能源|节能降碳|碳中和|新能源|光伏|风电|储能|电网',
        '航空':'航空|机场|民航|航班|航线|机票',
        '消费':'消费|零售|以旧换新|家电|汽车|补贴',
        'AI':'人工智能|AI|算力|芯片|半导体|数字经济',
        '金融':'银行|保险|券商|资本市场|降息|利率|货币',
    }
    sector_signals = {}
    for sector, pattern in SECTORS.items():
        sector_arts = [a for a in articles if re.search(pattern, a.get('title','')+a.get('intro',''))]
        if len(sector_arts) < 2: continue
        # 最多取5条做情感分析
        samples = sector_arts[:5]
        scores = []
        for a in samples:
            s = analyze_sentiment(a.get('title','')[:100])
            scores.append(1.0 if s=='积极' else (0.0 if s=='消极' else 0.5))
        avg = np.mean(scores)
        sector_signals[sector] = {
            'sentiment': avg,
            'mentions': len(sector_arts),
            'direction': '🟢' if avg>0.55 else ('🔴' if avg<0.45 else '⚪'),
        }
    return sector_signals

if __name__ == '__main__':
    load_model()
    # 快速测试
    tests = [
        '义乌小商品城进出口总值突破8365亿元创新高',
        '金价突破2400美元创历史新高',
        '三大航司上半年预亏合计超百亿',
        '央行宣布降准0.5个百分点释放万亿流动性',
        '美伊冲突升级油价突破100美元',
    ]
    print('Qwen2.5-1.5B 金融情感测试:')
    for t in tests:
        s = analyze_sentiment(t)
        print(f'  {s}: {t[:50]}')
