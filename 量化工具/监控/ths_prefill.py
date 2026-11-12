#!/usr/bin/env python3
"""
同花顺 L1 预填助手 — 点击买卖标签 + 填入代码/价格/数量
用户手动点击「确定」确认交易

用法: python ths_prefill.py <code> <direction> <price> <qty>
  例: python ths_prefill.py 600600 buy 55.00 1000
      python ths_prefill.py 601212 sell 5.05 3000
"""

import subprocess
import sys
import time
import ths_click


def osa(script: str) -> str:
    """执行 AppleScript，返回输出"""
    r = subprocess.run(['osascript', '-e', script],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def fill_field(field_idx: int, value: str):
    """聚焦文本字段并填入值"""
    # 聚焦
    osa(f'''
        tell application "System Events"
            tell process "同花顺"
                set frontmost to true
                set focused of text field {field_idx} of window 1 to true
            end tell
        end tell
    ''')
    time.sleep(0.1)
    # 全选 + 输入
    osa(f'''
        tell application "System Events"
            tell process "同花顺"
                keystroke "a" using command down
                delay 0.05
                keystroke "{value}"
            end tell
        end tell
    ''')


def prefill(code: str, direction: str, price: str, qty: str):
    """
    L1 预填：点击方向标签 → 填入代码 → 价格 → 数量 → 等待用户确认
    """
    # 1. 激活窗口
    osa('tell application "同花顺" to activate')
    time.sleep(0.3)

    # 2. 点击买入或卖出标签
    if direction == 'buy':
        ths_click.click_buy()
        print(f"🟢 已切到「买入」标签")
    else:
        ths_click.click_sell()
        print(f"🔴 已切到「卖出」标签")
    time.sleep(0.2)

    # 3. 填入代码
    fill_field(1, code)
    time.sleep(0.25)  # 等行情加载
    print(f"📌 代码: {code}")

    # 4. 填入价格
    fill_field(2, price)
    time.sleep(0.1)
    print(f"💰 价格: ¥{price}")

    # 5. 填入数量
    fill_field(3, qty)
    time.sleep(0.1)
    print(f"📊 数量: {qty} 股")

    # 6. 切换到数量框（最后一步留在这里，用户确认后按 Tab 到确定按钮或直接点）
    osa(f'''
        tell application "System Events"
            tell process "同花顺"
                set frontmost to true
                set focused of text field 3 of window 1 to true
            end tell
        end tell
    ''')

    print(f"\n✅ 预填完成 — {code} | {direction} | ¥{price} | {qty}股")
    print("⚠️  请确认后手动点击「确定」按钮")


if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("用法: python ths_prefill.py <代码> <buy|sell> <价格> <数量>")
        print("例: python ths_prefill.py 600600 buy 55.00 1000")
        sys.exit(1)

    code = sys.argv[1]
    direction = sys.argv[2].lower()
    price = sys.argv[3]
    qty = sys.argv[4]

    if direction not in ('buy', 'sell'):
        print(f"方向必须为 buy 或 sell，收到: {direction}")
        sys.exit(1)

    prefill(code, direction, price, qty)
