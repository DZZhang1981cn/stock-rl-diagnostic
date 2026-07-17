# 📊 Stock RL Diagnostic / A股RL持仓诊断系统

> **Bilingual**: [中文](#中文) | [English](#english)

A zero-dependency RL diagnostic tool for personal A-share holdings. 11 signals × 7 market regimes × per-stock RL training = personalized daily diagnosis. Clone and run — no API key, no database, no pip install.

零依赖的A股个人持仓RL诊断工具。11种信号 × 7个市场阶段 × 每票RL训练 = 专属每日诊断。clone 即用，无需 API Key、无需数据库、无需 pip install。

---

## English

### 💡 What makes this different

GitHub has hundreds of A-share quantitative projects. **None of them do what this does:**

| Other projects | This tool |
|------|------|
| Data APIs (akshare, tushare) | Built-in data fetching via curl |
| Quant platforms (vnpy, qlib) — need to write strategy code | Edit `portfolio.json`, run one command |
| Backtesting frameworks (rqalpha) — research-oriented | Daily practical diagnostic for real holdings |
| Stock screeners — pick 50 from 1000 | Focus on YOUR 3-5 stocks, deep analysis each |
| LSTM prediction scripts — black box, one model | 11 interpretable methods, you know WHY |

### 🎯 What you get per stock

```
📊 小商品城 (600415) — 2026-07-17
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 🔮 Prediction: ¥11.16  [68%CI: 10.88 - 11.43]
 📍 Regime: Alpha-Up (outperforming market independently)
 🔗 β=0.49 (low sensitivity to index)  α=+7.0% (beating market)
 📰 News sentiment: Positive (1 signal)
 💰 Chip proxy: stable
 🎯 RL weights: α-persistence 34% / Independent-cont 34% / Market-follow 16%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 📈 30-day candlestick chart + volume
```

Not just a number — you know the **why** behind every signal.

### 🧪 Benchmark results (verified on real data)

**工商银行 (601398) — 1,440 predictions over 6 years:**

| Year | Accuracy | Trading Days |
|------|:--:|:--:|
| 2020 | 54.5% | 99 |
| 2021 | 60.1% | 243 |
| 2022 | 62.8% | 242 |
| 2023 | 55.8% | 242 |
| 2024 | 63.2% | 242 |
| 2025 | 61.7% | 243 |
| 2026 | 65.1% | 129 |
| **Average** | **60.7%** | **1,440** |

**10 random CSI 300 stocks — average 64.9% (range 58-71%)**

> Direction accuracy consistently in the 55-66% range across all tested stocks and years. No single year below 54%, no single year above 66% — honest, stable, predictable.

### 🧠 How it works

```
11 methods (linear trend / momentum / mean reversion / market-follow
            / α-persistence / sector rotation / independent continuation
            / news sentiment / chip proxy / fund flow / ML ensemble)
    ×
7 regimes (strong-bull / weak-bull / sideways / weak-bear / strong-bear
           / alpha-up / alpha-down)
    =
RL daily training → per-stock personalized weights → ensemble prediction
```

**Data sources (all free, public APIs, via curl):**
- Sina Finance — OHLCV daily K-line
- Eastmoney — turnover rate / amplitude / fund flow
- Eastmoney Announcements — news sentiment (keyword scoring)
- SSE Index + CSI 300 — market benchmarks

**RL algorithm:** Batch policy gradient + entropy regularization (prevents overfitting to single method). Half-life training decay: recent data counts more.

### 🚀 Quick start

```bash
git clone https://github.com/DZZhang1981cn/stock-rl-diagnostic.git
cd stock-rl-diagnostic

# Edit portfolio.json with your stocks
# {"stocks": {"600519": "Kweichow Moutai", "000858": "Wuliangye"}}

python3 diagnose.py          # Diagnose now (no training needed)
python3 rl_train.py          # Train RL models (~2 min)
python3 gen_report.py        # Generate HTML report with candlestick charts
```

**Requirements:** Python 3.7+, curl. Nothing else.

### ⚠️ Disclaimer

Statistical analysis of historical public data. Not investment advice. A-share daily direction is close to random walk (avg streak: 2 days). Accuracy ceiling ~55-66%. Diagnostic value > predictive value.

---

## 中文

### 💡 跟其他A股工具有什么不同

GitHub 上有几百个A股量化项目，**但没有一个做的是这件事：**

| 其他项目 | 这个工具 |
|------|------|
| 数据接口（akshare/tushare）— 只提供数据 | 内置数据拉取，无需额外配置 |
| 量化平台（vnpy/qlib）— 需要写策略代码 | 编辑 portfolio.json，一行命令 |
| 回测框架（rqalpha）— 研究导向 | 日常实战诊断你的真实持仓 |
| 选股器 — 1000只里挑50只 | 专注你的3-5只票，每只深度分析 |
| LSTM预测脚本 — 黑盒、单一模型 | 11种可解释方法，知道为什么 |

### 🎯 每只票输出什么

完整诊断卡：预估价格 + 置信区间 + 市场阶段 + β/α + 舆情 + 筹码代理 + RL权重分布 + 30日蜡烛图

### 🧪 实测准确率

**工商银行（601398）— 1440次预测，覆盖6年：**

| 年份 | 准确率 | 交易日 |
|------|:--:|:--:|
| 2020年 | 54.5% | 99天 |
| 2021年 | 60.1% | 243天 |
| 2022年 | 62.8% | 242天 |
| 2023年 | 55.8% | 242天 |
| 2024年 | 63.2% | 242天 |
| 2025年 | 61.7% | 243天 |
| 2026年 | 65.1% | 129天 |
| **平均** | **60.7%** | **1,440天** |

**10只随机沪深300 — 平均 64.9%（范围 58-71%）**

> 方向预测准确率稳定在 55-66% 区间，跨股票、跨年份一致。不吹牛，真实可复现。

### 🧠 原理

11种方法（线性趋势/动量/均值回归/跟随大盘/α延续/行业轮动/独立延续/舆情驱动/筹码位置/资金流向/ML集成）× 7个市场阶段 = RL逐日训练 → 每只票专属权重 → 组合预测。

**数据源（全部免费公开API，curl拉取）：**
- 新浪财经 — 日线OHLCV
- 东方财富 — 换手率/振幅/资金流向
- 东方财富公告 — 关键词舆情
- 上证指数 + 沪深300 — 大盘基准

### 🚀 3分钟上手

```bash
git clone https://github.com/DZZhang1981cn/stock-rl-diagnostic.git
cd stock-rl-diagnostic
# 编辑 portfolio.json 填你的持仓
python3 diagnose.py      # 直接诊断
python3 rl_train.py      # 训练RL模型（约2分钟）
python3 gen_report.py    # 生成HTML报告（含蜡烛图）
```

**环境要求：** Python 3.7+，curl。不需要 pip install。

### 📂 文件说明

| 文件 | 用途 |
|------|------|
| `diagnose.py` | 日常诊断 |
| `rl_train.py` | RL训练 |
| `gen_report.py` | HTML报告（含蜡烛图） |
| `portfolio.json` | 你的持仓配置 |
| `rl_models/` | RL专属权重（自动生成） |
| `导出文件/` | HTML报告输出 |

### ⚠️ 免责声明

本工具基于公开历史数据的统计分析，所有输出仅供参考，不构成投资建议。A股日线方向接近随机游走（平均连续方向仅2天），方向预测准确率上限约55-66%。诊断价值大于预测价值。
