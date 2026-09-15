#!/usr/bin/env python3
"""
测试 aTimeLogger API 连通性和数据拉取
"""
import sys
import os
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.atimelogger_extractor import AtimeloggerExtractor

# 加载配置
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

atl_config = config.get('atimelogger', {})
print(f"账号: {atl_config.get('username')}")
print(f"Base URL: {atl_config.get('base_url')}")

# 测试日期：今天和昨天
today = datetime.now().strftime('%Y-%m-%d')
yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

print(f"\n--- 测试日期: {today} (今天) ---")
extractor = AtimeloggerExtractor(atl_config)

# 先测试登录
ok = extractor._login()
print(f"登录结果: {'✅ 成功' if ok else '❌ 失败'}")

if ok:
    print(f"活动类型数量: {len(extractor.types_map)}")
    print("活动类型列表:")
    for tid, t in list(extractor.types_map.items())[:10]:
        print(f"  [{tid}] {t.get('name', '?')}")

    # 拉取今天数据
    print(f"\n--- 拉取 {today} 数据 ---")
    data = extractor.extract_daily_data(today)
    if data:
        acts = data.get('activities', [])
        print(f"✅ 共 {len(acts)} 条记录")
        for a in acts:
            start = a['start'].strftime('%H:%M') if hasattr(a['start'], 'strftime') else a['start']
            finish = a['finish'].strftime('%H:%M') if hasattr(a['finish'], 'strftime') else a['finish']
            dur = a['duration']
            h, m = dur // 3600, (dur % 3600) // 60
            print(f"  {start}-{finish} [{a['type']}] {h:02d}:{m:02d} {a.get('comment','')}")
    else:
        print("❌ 未获取到数据")

    # 拉取昨天数据
    print(f"\n--- 拉取 {yesterday} 数据 ---")
    data2 = extractor.extract_daily_data(yesterday)
    if data2:
        acts2 = data2.get('activities', [])
        print(f"✅ 共 {len(acts2)} 条记录")
        for a in acts2:
            start = a['start'].strftime('%H:%M') if hasattr(a['start'], 'strftime') else a['start']
            finish = a['finish'].strftime('%H:%M') if hasattr(a['finish'], 'strftime') else a['finish']
            dur = a['duration']
            h, m = dur // 3600, (dur % 3600) // 60
            print(f"  {start}-{finish} [{a['type']}] {h:02d}:{m:02d} {a.get('comment','')}")
    else:
        print("❌ 未获取到数据")
