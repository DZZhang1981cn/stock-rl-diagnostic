# -*- coding: utf-8 -*-
"""TimesFM 600415 预测 + 回测"""
import subprocess, json, numpy as np, pandas as pd
import torch
import timesfm

def curl(url):
    r = subprocess.run(['curl','-s','-L','--max-time','10',url], capture_output=True, timeout=12)
    try: return r.stdout.decode('utf-8')
    except: return r.stdout.decode('gbk', errors='ignore')

print("📥 拉数据...")
kl = json.loads(curl('http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600415&scale=240&ma=no&datalen=500'))
close = np.array([float(d['close']) for d in kl], dtype=np.float32)

print("🚀 加载 TimesFM 2.0...")
torch.set_float32_matmul_precision("high")
model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")

cfg = timesfm.ForecastConfig(max_context=512, max_horizon=32, normalize_inputs=True)
model.compile(cfg)

# ===== 预测 =====
ctx = close[-256:].copy()
last = ctx[-1]

print(f"🔮 预测未来10天 (当前: ¥{last:.2f})...")
pf, qf = model.forecast(horizon=10, inputs=[ctx])
pf = pf[0].numpy()  # point forecast
qf = qf[0].numpy()  # quantile forecast [horizon, 10 quantiles]

print(f"\n{'='*55}")
print(f"  TimesFM 预测: 600415")
print(f"{'='*55}")
print(f"  {'天':>3s} {'点预测':>8s} {'P10':>8s} {'P50':>8s} {'P90':>8s}")
print(f"  {'-'*40}")
for i in range(10):
    print(f"  {i+1:>3d} ¥{pf[i]:>7.2f} ¥{qf[i,0]:>7.2f} ¥{qf[i,5]:>7.2f} ¥{qf[i,9]:>7.2f}")

# 下周汇总
week_pf = pf[:5]
chg = (week_pf[4] - last) / last * 100
print(f"\n  {'='*55}")
print(f"  下周汇总")
print(f"  {'='*55}")
print(f"  周五预测: ¥{week_pf[4]:.2f}  ({chg:+.1f}%)")
print(f"  周中最高: ¥{max(week_pf):.2f}")
print(f"  周中最低: ¥{min(week_pf):.2f}")
print(f"  90%CI:    [¥{min(qf[:5,0]):.2f}, ¥{max(qf[:5,9]):.2f}]")

# ===== 回测 =====
print(f"\n{'='*55}")
print(f"  滚动回测 (最近10次)...")

errors, dir_correct = [], 0
for start in range(len(close)-40, len(close)-10, 3):
    ctx = close[start-256:start].copy()
    actual = close[start:start+5]
    pf, _ = model.forecast(horizon=5, inputs=[ctx])
    pf = pf[0].numpy()
    for j in range(min(5, len(actual))):
        err = abs(pf[j] - actual[j]) / actual[j] * 100
        errors.append(err)
    dir_correct += (pf[0] > ctx[-1]) == (actual[0] > ctx[-1])

mape = np.mean(errors)
dir_acc = dir_correct / 10 * 100

print(f"  样本: {len(errors)} 点")
print(f"  MAPE: {mape:.2f}%")
print(f"  方向: {dir_acc:.0f}%")

# ===== 对比 =====
print(f"\n  {'='*55}")
print(f"  对比汇总")
print(f"  {'='*55}")
print(f"  {'模型':<15s} {'MAPE':>8s} {'方向'}")
print(f"  {'-'*30}")
print(f"  {'Kronos-base':<15s} {'~13%':>8s} {'~46%'}")
print(f"  {'TimesFM 2.0':<15s} {mape:>7.2f}% {dir_acc:>5.0f}%")
print(f"  {'手工多模型':<15s} {'~14%':>8s} {'~46%'}")
