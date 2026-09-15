#!/usr/bin/env python3
"""
AI分析模块 - 使用AI分析时间使用数据
"""

import os
import json
from datetime import datetime, timedelta


class AIAnalyzer:
    """AI分析器"""

    def __init__(self, config=None):
        """
        初始化AI分析器

        Args:
            config: AI配置字典
        """
        self.config = config or {}
        self.model = self.config.get('model', 'gpt-4')
        self.api_key = self.config.get('api_key', '')

    def analyze(self, combined_data):
        """
        分析时间使用数据

        Args:
            combined_data: 合并后的数据字典

        Returns:
            dict: 分析结果
        """
        date = combined_data.get('date')
        atimelogger = combined_data.get('atimelogger', {})
        health = combined_data.get('huawei_health', {})
        summary = combined_data.get('summary', {})

        activities = atimelogger.get('activities', [])
        activity_breakdown = summary.get('activity_breakdown', {})

        # 基础统计
        total_activities = len(activities)
        total_tracked_seconds = summary.get('total_tracked_time', 0)
        total_tracked_hours = total_tracked_seconds / 3600

        # 睡眠分析
        sleep_data = summary.get('sleep', {})
        sleep_duration = sleep_data.get('huawei_duration', 0)
        sleep_hours = sleep_duration / 3600 if sleep_duration else 0

        # 生产时间分析
        productive_time = activity_breakdown.get('生产', 0)
        productive_hours = productive_time / 3600

        # 娱乐时间分析
        entertainment_time = activity_breakdown.get('娱乐', 0)
        entertainment_hours = entertainment_time / 3600

        # 松鼠病分析
        squirrel_time = activity_breakdown.get('松鼠病', 0)
        squirrel_hours = squirrel_time / 3600

        # 家庭时间
        family_time = activity_breakdown.get('家庭', 0)
        family_hours = family_time / 3600

        # 生成关键洞察
        key_insights = []

        # 睡眠洞察
        if sleep_hours > 0:
            if sleep_hours < 6:
                key_insights.append(f"睡眠时间不足（{sleep_hours:.1f}小时），建议调整作息")
            elif sleep_hours > 9:
                key_insights.append(f"睡眠时间较长（{sleep_hours:.1f}小时），可能影响日间效率")
            else:
                key_insights.append(f"睡眠时间合理（{sleep_hours:.1f}小时）")

        # 生产时间洞察
        if productive_hours < 1:
            key_insights.append(f"生产时间较少（{productive_hours:.1f}小时），建议增加专注工作时间")
        elif productive_hours > 4:
            key_insights.append(f"生产时间充足（{productive_hours:.1f}小时），效率较高")
        else:
            key_insights.append(f"生产时间{productive_hours:.1f}小时，处于正常水平")

        # 松鼠病洞察
        if squirrel_hours > 2:
            key_insights.append(f"松鼠病时间较长（{squirrel_hours:.1f}小时），注意力分散较多")
        elif squirrel_hours < 0.5:
            key_insights.append(f"松鼠病控制良好（{squirrel_hours:.1f}小时），专注力较强")

        # 娱乐时间洞察
        if entertainment_hours > 3:
            key_insights.append(f"娱乐时间较长（{entertainment_hours:.1f}小时），可适当减少")

        # 生成建议
        recommendations = []

        if sleep_hours < 6:
            recommendations.append("建议提前30分钟入睡，保证7-8小时睡眠")

        if productive_hours < 2:
            recommendations.append("尝试使用番茄工作法，每天专注工作2-3小时")

        if squirrel_hours > 1:
            recommendations.append("工作时关闭手机通知，减少干扰")

        if not recommendations:
            recommendations.append("时间管理良好，继续保持！")

        # 计算效率评分
        efficiency_score = self._calculate_efficiency_score(
            productive_hours, sleep_hours, squirrel_hours, entertainment_hours
        )

        return {
            'date': date,
            'summary': {
                'total_activities': total_activities,
                'total_time': f"{int(total_tracked_hours)}小时{int((total_tracked_hours % 1) * 60)}分",
                'sleep_time': f"{int(sleep_hours)}小时{int((sleep_hours % 1) * 60)}分" if sleep_hours > 0 else 'N/A',
                'productive_time': f"{int(productive_hours)}小时{int((productive_hours % 1) * 60)}分",
                'entertainment_time': f"{int(entertainment_hours)}小时{int((entertainment_hours % 1) * 60)}分",
                'squirrel_time': f"{int(squirrel_hours)}小时{int((squirrel_hours % 1) * 60)}分",
                'family_time': f"{int(family_hours)}小时{int((family_hours % 1) * 60)}分",
                'efficiency_score': efficiency_score
            },
            'key_insights': key_insights,
            'recommendations': recommendations,
            'activity_breakdown': activity_breakdown,
            'raw_data': combined_data
        }

    def _calculate_efficiency_score(self, productive_hours, sleep_hours, squirrel_hours, entertainment_hours):
        """
        计算效率评分

        Returns:
            int: 0-100的评分
        """
        score = 50  # 基础分

        # 生产时间加分
        if productive_hours >= 4:
            score += 25
        elif productive_hours >= 2:
            score += 15
        elif productive_hours >= 1:
            score += 5

        # 睡眠时间加分
        if 7 <= sleep_hours <= 9:
            score += 15
        elif 6 <= sleep_hours < 7:
            score += 5

        # 松鼠病减分
        if squirrel_hours > 3:
            score -= 20
        elif squirrel_hours > 2:
            score -= 10
        elif squirrel_hours > 1:
            score -= 5

        # 娱乐时间减分
        if entertainment_hours > 4:
            score -= 10
        elif entertainment_hours > 3:
            score -= 5

        return max(0, min(100, score))
