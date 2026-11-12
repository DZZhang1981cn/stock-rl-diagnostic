#!/usr/bin/env python3
"""Qlib风格多因子选股器"""
import subprocess, json, math, os
from datetime import datetime

OUTPUT_DIR = os.path.expanduser('~/Desktop/AI工作/导出文件')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def curl(url):
    r = subprocess.run(['curl', '-s', '-L', '--max-time', '15', '-H', 'User-Agent: Mozilla/5.0', url], capture_output=True, text=True, timeout=20)
    return json.loads(r.stdout)
