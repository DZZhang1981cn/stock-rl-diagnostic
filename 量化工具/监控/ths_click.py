#!/usr/bin/env python3
"""
同花顺 GUI 点击助手 — 使用 CGEvent 模拟鼠标点击
纯 ctypes，无需额外依赖
"""

import ctypes
import ctypes.util
import time
import subprocess
import sys

# 加载 CoreGraphics
_cg_path = ctypes.util.find_library('CoreGraphics')
if not _cg_path:
    _cg_path = '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics'
cg = ctypes.CDLL(_cg_path)

# CGEvent 类型
CGEventRef = ctypes.c_void_p
CGPoint = ctypes.c_double * 2

# 常量
kCGEventLeftMouseDown = 1
kCGEventLeftMouseUp = 2
kCGHIDEventTap = 0
kCGMouseButtonLeft = 0

# 函数签名
cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
cg.CGEventCreateMouseEvent.restype = CGEventRef
cg.CGEventPost.argtypes = [ctypes.c_uint32, CGEventRef]
cg.CGEventPost.restype = None
cg.CFRelease.argtypes = [ctypes.c_void_p]
cg.CFRelease.restype = None


def click(x: int, y: int):
    """在屏幕坐标 (x, y) 处点击"""
    pt = CGPoint(x, y)
    down = cg.CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, pt, kCGMouseButtonLeft)
    up = cg.CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, pt, kCGMouseButtonLeft)
    cg.CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.03)
    cg.CGEventPost(kCGHIDEventTap, up)
    cg.CFRelease(down)
    cg.CFRelease(up)


def get_win_pos():
    """获取同花顺主窗口屏幕坐标 (x, y, w, h)"""
    r = subprocess.run([
        'osascript', '-e',
        'tell application "System Events" to tell process "同花顺" to get position of window 1'
    ], capture_output=True, text=True, timeout=5)
    pos = r.stdout.strip()
    # 格式: "0, 33"
    parts = pos.replace(' ', '').split(',')
    x = int(parts[0])
    y = int(parts[1])

    r2 = subprocess.run([
        'osascript', '-e',
        'tell application "System Events" to tell process "同花顺" to get size of window 1'
    ], capture_output=True, text=True, timeout=5)
    size = r2.stdout.strip()
    parts2 = size.replace(' ', '').split(',')
    w = int(parts2[0])
    h = int(parts2[1])
    return x, y, w, h


# 校准坐标（窗口局部，不含标题栏偏移）
BTN_BUY_X, BTN_BUY_Y = 178, 78
BTN_SELL_X, BTN_SELL_Y = 222, 78
BTN_CONFIRM_X, BTN_CONFIRM_Y = 395, 165


def click_buy():
    """点击买入标签"""
    x, y, w, h = get_win_pos()
    click(x + BTN_BUY_X, y + BTN_BUY_Y)


def click_sell():
    """点击卖出标签"""
    x, y, w, h = get_win_pos()
    click(x + BTN_SELL_X, y + BTN_SELL_Y)


# click_confirm 已禁用 —— L1 模式禁止自动确认，永远由用户手动点击
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: ths_click.py buy|sell|pos")
        sys.exit(1)
    action = sys.argv[1]
    if action == 'buy':
        click_buy()
        print("✅ 已点击买入")
    elif action == 'sell':
        click_sell()
        print("✅ 已点击卖出")
    elif action == 'pos':
        x, y, w, h = get_win_pos()
        print(f"窗口: ({x}, {y}) 尺寸: {w}x{h}")
    else:
        print(f"未知操作: {action}")
