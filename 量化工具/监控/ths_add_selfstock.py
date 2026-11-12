#!/usr/bin/env python3
"""
同花顺批量添加自选股脚本
用法: python3 ths_add_selfstock.py

逐只通过键盘精灵搜索股票 → 检查是否已在自选股 → 未加入的自动添加
"""

import subprocess
import time
import sys


def osa(script: str, timeout: int = 5) -> str:
    """执行 AppleScript，返回输出"""
    r = subprocess.run(['osascript', '-e', script],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


# ====== 观察池完整清单 ======
WATCHLIST_STOCKS = [
    # 高分红基础设施（2026-08-07 新增）
    "000429",  # 粤高速A
    "600548",  # 深高速
    "600012",  # 皖通高速
    "600350",  # 山东高速
    "600900",  # 长江电力
    "601006",  # 大秦铁路
    "601816",  # 京沪高铁
    # 原有观察池
    "002027",  # 分众传媒
    "300628",  # 亿联网络
    "000651",  # 格力电器
    "600547",  # 山东黄金
    "000975",  # 山金国际
    "600236",  # 桂冠电力
    "600489",  # 中金黄金
    "600988",  # 赤峰黄金
    "601168",  # 西部矿业
    "300896",  # 爱美客
    "600726",  # 华电能源
    "603979",  # 金诚信
    "601233",  # 桐昆股份
    "002415",  # 海康威视
    "002236",  # 大华股份
]


def add_to_selfstock() -> str:
    """
    通过操作菜单添加/检查当前股票到自选股
    返回: 'added' | 'already' | 'failed' | 'no_menu'
    """
    try:
        # 步骤1: 打开操作菜单
        osa('''
            tell application "System Events"
                tell process "同花顺"
                    tell menu bar 1
                        click menu bar item "操作"
                    end tell
                end tell
            end tell
        ''', timeout=3)
        time.sleep(0.4)

        # 步骤2: 读取第一个菜单项
        first_item = osa('''
            tell application "System Events"
                tell process "同花顺"
                    try
                        tell menu 1 of menu bar item "操作" of menu bar 1
                            return name of menu item 1
                        end tell
                    on error
                        return "MENU_ERROR"
                    end try
                end tell
            end tell
        ''', timeout=3)

        if first_item == "MENU_ERROR":
            return "no_menu"

        # 步骤3: 根据菜单项决定操作
        if "添加自选股" in first_item:
            # 点击添加
            osa('''
                tell application "System Events"
                    tell process "同花顺"
                        tell menu 1 of menu bar item "操作" of menu bar 1
                            click menu item 1
                        end tell
                    end tell
                end tell
            ''', timeout=3)
            time.sleep(0.3)
            return "added"
        elif "删除自选股" in first_item:
            # 关闭菜单
            osa('''
                tell application "System Events"
                    tell process "同花顺"
                        key code 53
                    end tell
                end tell
            ''', timeout=2)
            return "already"
        else:
            # 未知状态，关闭菜单
            osa('''
                tell application "System Events"
                    tell process "同花顺"
                        key code 53
                    end tell
                end tell
            ''', timeout=2)
            print(f"(菜单: {first_item[:30]})", end=" ")
            return "failed"
    except Exception as e:
        return "failed"


def search_stock(code: str):
    """在键盘精灵中搜索股票代码"""
    osa('tell application "同花顺" to activate')
    time.sleep(0.3)

    osa(f'''
        tell application "System Events"
            tell process "同花顺"
                set frontmost to true
                delay 0.3
                keystroke "{code}"
                delay 0.3
                keystroke return
            end tell
        end tell
    ''')
    time.sleep(1.2)  # 等待股票页面加载 + 菜单更新


def main():
    print(f"📋 同花顺批量添加自选股")
    print(f"   共 {len(WATCHLIST_STOCKS)} 只需检查\n")

    added = []
    skipped = []
    failed = []

    for i, code in enumerate(WATCHLIST_STOCKS):
        print(f"[{i+1:2d}/{len(WATCHLIST_STOCKS)}] {code} ...", end=" ", flush=True)

        # 搜索股票
        search_stock(code)

        # 尝试添加（会在内部判断是否已在自选股）
        result = add_to_selfstock()

        if result == "added":
            added.append(code)
            print("✅ 已添加")
        elif result == "already":
            skipped.append(code)
            print("⏭️ 已在自选股")
        elif result == "no_menu":
            failed.append(code)
            print("⚠️ 菜单不可用（重试）")
        else:
            failed.append(code)
            print("❌ 失败")

    # 汇总
    print(f"\n{'=' * 40}")
    print(f"📊 完成统计:")
    print(f"   ✅ 新添加: {len(added)} 只")
    if added:
        print(f"      {', '.join(added)}")
    print(f"   ⏭️ 已存在: {len(skipped)} 只")
    print(f"   ❌ 失败: {len(failed)} 只")
    if failed:
        print(f"      {', '.join(failed)}")


if __name__ == "__main__":
    main()
