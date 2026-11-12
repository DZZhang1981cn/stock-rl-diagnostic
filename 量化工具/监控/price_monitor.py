#!/usr/bin/env python3
"""
股票触发价监控 — 盘中每60秒扫一次，到触发价自动飞书通知
用法: nohup python price_monitor.py > /tmp/price_monitor.log 2>&1 &
"""

import asyncio, json, subprocess, sys, time, aiohttp, re
from datetime import datetime

FEISHU_HOST = "https://open.feishu.cn"
CHAT_ID = "oc_9af81a013c84716b6e832fb7b2db2781"

# ====== 监控配置 ======
WATCHLIST = [
    # (代码, 名称, 持仓, 成本, 触发价, 方向, 操作描述, 金额, 比例, 预填数量)
    # 2026-08-05 基于同花顺实盘更新 — 7只票 15条规则
    # 🟢 加仓组
    ("sh600172", "黄河旋风", 4600, 10.753, 11.50, "buy",  "加仓 2,300股 ¥26,450 (+50%)",    26450, "50%",  2300),
    ("sh601991", "大唐发电", 9900, 6.251,  6.50,  "buy",  "加仓 3,000股 ¥19,500 (+30%)",    19500, "30%",  3000),
    ("sh600377", "宁沪高速", 6000, 12.121, 12.15, "buy",  "加仓 1,000股 ¥12,150 (+17%)",    12150, "17%",  1000),
    ("sh600415", "小商品城", 4800, 12.531, 12.75, "buy",  "加仓 2,000股 ¥25,500 (+42%)",    25500, "42%",  2000),
    ("sh600600", "青岛啤酒", 3800, 57.066, 55.00, "buy",  "加仓 1,000股 ¥55,000 (+26%)",    55000, "26%",  1000),
    ("sh600029", "南方航空", 5200, 5.561,  5.35,  "buy",  "加仓 1,000股 ¥5,350 (+19%)",     5350,  "19%",  1000),
    # 🔴 止损/止盈组
    ("sh600172", "黄河旋风", 4600, 10.753, 10.80, "sell", "止盈 2,300股 ¥24,840 (-50%)",    24840, "50%",  2300),
    ("sh600172", "黄河旋风", 4600, 10.753, 10.00, "sell", "止损清仓 2,300股 ¥23,000",        23000, "50%",  2300),
    ("sh601991", "大唐发电", 9900, 6.251,  6.10,  "sell", "止盈 3,000股 ¥18,300 (-30%)",    18300, "30%",  3000),
    ("sh600377", "宁沪高速", 6000, 12.121, 11.50, "sell", "减仓 2,000股 ¥23,000 (-33%)",    23000, "33%",  2000),
    ("sh601212", "白银有色", 10000, 5.701, 5.20,  "sell", "减仓 3,000股 ¥15,600 (-30%)",    15600, "30%",  3000),
    ("sh601212", "白银有色", 10000, 5.701, 4.85,  "sell", "止损清仓 7,000股 ¥33,950",        33950, "70%",  7000),
    ("sh600600", "青岛啤酒", 3800, 57.066, 52.00, "sell", "止损 1,200股 ¥62,400 (-32%)",    62400, "32%",  1200),
    ("sh600029", "南方航空", 5200, 5.561,  5.05,  "sell", "减仓 2,000股 ¥10,100 (-38%)",    10100, "38%",  2000),
]

# 已触发过的（防重复）
fired = set()

def get_keychain(account: str) -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", account, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

async def get_token(app_id, app_secret):
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
                          json={"app_id": app_id, "app_secret": app_secret}) as r:
            return (await r.json())["tenant_access_token"]

async def send_feishu(token, text):
    async with aiohttp.ClientSession() as s:
        await s.post(f"{FEISHU_HOST}/open-apis/im/v1/messages?receive_id_type=chat_id",
            json={"receive_id": CHAT_ID, "msg_type": "text",
                  "content": json.dumps({"text": text}, ensure_ascii=False)},
            headers={"Authorization": f"Bearer {token}"})

async def fetch_prices(codes):
    """拉腾讯行情"""
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    proc = subprocess.run(["curl", "-s", url], capture_output=True, timeout=10)
    raw = proc.stdout.decode("gbk", errors="replace")
    prices = {}
    for line in raw.strip().split("\n"):
        m = re.match(r'v_(s[hz]\d{6})="', line)
        if not m: continue
        flds = line.split("~")
        try:
            prices[m.group(1)] = float(flds[3])
        except: pass
    return prices

def is_trading_time():
    """判断是否在交易时段"""
    now = datetime.now()
    if now.weekday() >= 5: return False  # 周末
    t = now.hour * 100 + now.minute
    return 925 <= t <= 1505  # 9:25-15:05

async def main():
    app_id = get_keychain("feishu-app-id")
    app_secret = get_keychain("feishu-app-secret")
    token = await get_token(app_id, app_secret)

    unique_codes = list(set(w[0] for w in WATCHLIST))
    print(f"[{datetime.now():%H:%M:%S}] 监控启动: {len(WATCHLIST)} 条规则, {len(unique_codes)} 只票", flush=True)
    print(f"  规则清单:")
    for rule in WATCHLIST:
        code, name, shares, cost, price, direction, desc, amt, pct, prefill_qty = rule
        emoji = "🟢" if direction == "buy" else "🔴"
        edge = "≥" if direction == "buy" else "≤"
        print(f"  {emoji} {name} {edge}¥{price} → {desc} ({prefill_qty}股)")

    # 初始拉一次
    initial = await fetch_prices(unique_codes)
    for code, price in initial.items():
        print(f"  {code}: ¥{price}", flush=True)

    last_heartbeat = 0
    while True:
        if not is_trading_time():
            await asyncio.sleep(60)
            continue

        try:
            prices = await fetch_prices(unique_codes)
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] fetch error: {e}", flush=True)
            await asyncio.sleep(30)
            continue

        # 心跳：每5分钟打印一次当前价格
        now_ts = int(time.time())
        if now_ts - last_heartbeat >= 300:
            last_heartbeat = now_ts
            parts = [f"{datetime.now():%H:%M:%S} 💓"]
            for code, price in prices.items():
                name = next((w[1] for w in WATCHLIST if w[0]==code), code)
                parts.append(f"{name} ¥{price}")
            print(" | ".join(parts), flush=True)

        for rule in WATCHLIST:
            code, name, shares, cost, trigger, direction, desc, amt, pct, prefill_qty = rule
            current = prices.get(code)
            if current is None: continue
            rule_id = f"{code}_{trigger}_{direction}"
            if rule_id in fired: continue

            if direction == "buy" and current >= trigger:
                fired.add(rule_id)
                buy_qty = prefill_qty
                new_total = shares + buy_qty
                chg = (current - cost) / cost * 100
                emoji = "🟢" if chg > 0 else "🟡"
                pure_code = code[2:]  # sh600600 → 600600
                msg = f"""⚡ {emoji} 加仓触发 — {name} ({code})
触发价: ¥{trigger} | 当前: ¥{current}
成本: ¥{cost:.2f} | 浮亏: {chg:+.1f}%
━━━━━━━━━━━━━━━━━━━
📌 建议买入: {buy_qty:,} 股
金额: ¥{amt:,} | 加仓后: {new_total:,} 股
比例: +{pct}
━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now():%H:%M:%S}"""
                await send_feishu(token, msg)
                print(f"[{datetime.now():%H:%M:%S}] 🔔 {emoji} {name} ≥¥{trigger} 加仓{buy_qty}股 ¥{amt}")
                # L1 预填同花顺
                subprocess.Popen([
                    sys.executable, '-u',
                    '/Users/zhangzhenhua/Desktop/AI工作/量化工具/监控/ths_prefill.py',
                    pure_code, 'buy', str(trigger), str(buy_qty)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"          → 同花顺预填: {pure_code} buy ¥{trigger} × {buy_qty}股")

            elif direction == "sell" and current <= trigger:
                fired.add(rule_id)
                sell_qty = prefill_qty
                remain = shares - sell_qty
                chg = (current - cost) / cost * 100
                pure_code = code[2:]  # sh601212 → 601212
                msg = f"""⚠️ 减仓/止损 — {name} ({code})
触发价: ¥{trigger} | 当前: ¥{current}
成本: ¥{cost:.2f} | 浮亏: {chg:+.1f}%
━━━━━━━━━━━━━━━━━━━
📌 建议卖出: {sell_qty:,} 股
回收: ¥{amt:,} | 剩余: {remain:,} 股
比例: -{pct}
━━━━━━━━━━━━━━━━━━━
⏰ {datetime.now():%H:%M:%S}"""
                await send_feishu(token, msg)
                print(f"[{datetime.now():%H:%M:%S}] 🔔 ⚠️ {name} ≤¥{trigger} 卖出{sell_qty}股 ¥{amt}")
                # L1 预填同花顺
                subprocess.Popen([
                    sys.executable, '-u',
                    '/Users/zhangzhenhua/Desktop/AI工作/量化工具/监控/ths_prefill.py',
                    pure_code, 'sell', str(trigger), str(sell_qty)
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"          → 同花顺预填: {pure_code} sell ¥{trigger} × {sell_qty}股")

        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
