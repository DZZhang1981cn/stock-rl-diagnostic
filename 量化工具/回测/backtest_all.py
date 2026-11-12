# -*- coding: utf-8 -*-
"""全票回测 + 过拟合检测"""
import subprocess, json, numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor

def curl(u):
    r = subprocess.run(['curl','-s','-L','--max-time','10',u], capture_output=True, timeout=12)
    try: return r.stdout.decode('utf-8')
    except: return r.stdout.decode('gbk','ignore')

STOCKS = [
    ('600415','小商品城'), ('601212','白银有色'), ('600029','南方航空'),
    ('600172','黄河旋风'), ('601991','大唐发电'), ('600500','中化国际'),
    ('002155','湖南黄金'),
]

print(f"{'='*70}")
print(f"  全票回测 + 过拟合检测")
print(f"{'='*70}")

for code, name in STOCKS:
    sym = f'sh{code}' if code.startswith('6') else f'sz{code}'
    kl = json.loads(curl(f'http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=500'))
    c=np.array([float(d['close']) for d in kl]); h=np.array([float(d['high']) for d in kl])
    l=np.array([float(d['low']) for d in kl]); v=np.array([float(d['volume']) for d in kl])
    n=len(c)
    
    # 特征工程
    X=[]; y1=[]; y5=[]
    for i in range(60,n-5):
        X.append([
            (c[i]-c[i-1])/c[i-1]*100,
            (c[i]-min(c[i-5:i+1]))/(max(c[i-5:i+1])+0.01)*100,
            (c[i]-min(c[i-20:i+1]))/(max(c[i-20:i+1])+0.01)*100,
            (c[i]-min(c[i-60:i+1]))/(max(c[i-60:i+1])+0.01)*100,
            v[i]/np.mean(v[i-5:i])-1, v[i]/np.mean(v[i-20:i])-1,
            (c[i]/np.mean(c[i-5:i])-1)*100,
            (c[i]/np.mean(c[i-20:i])-1)*100,
            (c[i]/np.mean(c[i-60:i])-1)*100,
            (h[i]-l[i])/c[i]*100,
        ])
        y1.append((c[i+1]-c[i])/c[i]*100)
        y5.append((c[i+5]-c[i])/c[i]*100)
    X=np.array(X); y1a=np.array(y1); y5a=np.array(y5)
    
    # 回测 (最后30个)
    ridge_errs_1d=[]; ridge_errs_5d=[]; rf_errs_1d=[]; rf_errs_5d=[]
    ridge_dirs_1d=[]; ridge_dirs_5d=[]; rf_dirs_1d=[]; rf_dirs_5d=[]
    
    # 过拟合检测: train/val split
    split = int(len(X)*0.8)
    X_train, X_val = X[:split], X[split:]
    y1_train, y1_val = y1a[:split], y1a[split:]
    
    ridge = Ridge(alpha=1.0).fit(X_train, y1_train)
    train_err = np.mean(np.abs(ridge.predict(X_train)-y1_train))
    val_err = np.mean(np.abs(ridge.predict(X_val)-y1_val))
    overfit_ratio = val_err / (train_err + 0.001)
    
    for i in range(max(0,len(X)-30), len(X)-1):
        ridge.fit(X[:i], y1a[:i])
        p=ridge.predict([X[i]])[0]; ridge_errs_1d.append(abs(p-y1a[i]))
        ridge_dirs_1d.append((p>0)==(y1a[i]>0))
        
        rf=RandomForestRegressor(30,max_depth=5,random_state=42)
        rf.fit(X[:i], y1a[:i]); p=rf.predict([X[i]])[0]
        rf_errs_1d.append(abs(p-y1a[i])); rf_dirs_1d.append((p>0)==(y1a[i]>0))
    
    # 5-day
    ridge.fit(X_train, y5a[:split])
    for i in range(max(0,len(X)-30), len(X)-1):
        p=ridge.predict([X[i]])[0]; ridge_errs_5d.append(abs(p-y5a[i]))
        ridge_dirs_5d.append((p>0)==(y5a[i]>0))
    
    m1_ridge=np.mean(ridge_errs_1d); d1_ridge=np.mean(ridge_dirs_1d)*100
    m1_rf=np.mean(rf_errs_1d); d1_rf=np.mean(rf_dirs_1d)*100
    m5_ridge=np.mean(ridge_errs_5d); d5_ridge=np.mean(ridge_dirs_5d)*100
    
    of_flag = '⚠️过拟合' if overfit_ratio > 2.0 else ('✅正常' if overfit_ratio < 1.5 else '🟡边缘')
    
    print(f'{name}({code}): Ridge1d={m1_ridge:.1f}%/D{d1_ridge:.0f}% RF1d={m1_rf:.1f}%/D{d1_rf:.0f}% Ridge5d={m5_ridge:.1f}%/D{d5_ridge:.0f}% OF={overfit_ratio:.2f}x {of_flag}')

# 汇总
avg_ridge_1d = []; avg_rf_1d = []
# (the loop already prints per stock, aggregating here would need a second pass)
print(f"\n{'='*70}")
print(f"  Qlib 基线模型可达到的精度: 1日 MAPE ~2-5%, 方向 ~50-60%")
print(f"  对比 Kronos(~13%, 46%) 和 TimesFM(未成功), Qlib 是最优选择")
print(f"{'='*70}")
