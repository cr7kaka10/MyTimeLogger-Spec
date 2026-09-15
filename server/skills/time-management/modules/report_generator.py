#!/usr/bin/env python3
"""
报告生成模块 - 生成时间管理分析报告
"""

import os
import json
from datetime import datetime
from pathlib import Path

try:
    from .report_paths import resolve_reports_dir
except ImportError:
    from report_paths import resolve_reports_dir


class ReportGenerator:
    """报告生成器"""

    def __init__(self, output_dir=None):
        """
        初始化报告生成器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = resolve_reports_dir(output_dir)

    def generate(self, combined_data, analysis_result, date):
        """
        生成报告

        Args:
            combined_data: 合并后的数据
            analysis_result: AI分析结果
            date: 日期字符串

        Returns:
            str: 报告文件路径
        """
        # 生成Markdown报告
        md_path = self._generate_markdown(combined_data, analysis_result, date)

        # 生成JSON数据文件
        json_path = self._generate_json(combined_data, analysis_result, date)

        return md_path

    def _generate_markdown(self, combined_data, analysis_result, date):
        """生成Markdown格式报告"""

        atimelogger = combined_data.get('atimelogger', {})
        health = combined_data.get('huawei_health', {})
        summary = analysis_result.get('summary', {})
        insights = analysis_result.get('key_insights', [])
        recommendations = analysis_result.get('recommendations', [])
        activities = atimelogger.get('activities', [])

        # 构建报告内容
        lines = [
            f"# 📊 时间管理分析报告 - {date}",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**效率评分**: {summary.get('efficiency_score', 0)}/100",
            "",
            "---",
            "",
            "## 📈 数据概览",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 时间记录总数 | {summary.get('total_activities', 0)} 条 |",
            f"| 总追踪时长 | {summary.get('total_time', 'N/A')} |",
            f"| 睡眠时长 | {summary.get('sleep_time', 'N/A')} |",
            f"| 生产时间 | {summary.get('productive_time', 'N/A')} |",
            f"| 娱乐时间 | {summary.get('entertainment_time', 'N/A')} |",
            f"| 松鼠病时间 | {summary.get('squirrel_time', 'N/A')} |",
            f"| 家庭时间 | {summary.get('family_time', 'N/A')} |",
            "",
            "---",
            "",
            "## 💡 关键洞察",
            "",
        ]

        for i, insight in enumerate(insights, 1):
            lines.append(f"{i}. {insight}")

        lines.extend([
            "",
            "---",
            "",
            "## 🎯 改进建议",
            "",
        ])

        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")

        lines.extend([
            "",
            "---",
            "",
            "## ⏱ 详细时间记录",
            "",
            "| 序号 | 类别 | 开始时间 | 结束时间 | 时长 | 备注 |",
            "|------|------|----------|----------|------|------|",
        ])

        for i, activity in enumerate(activities, 1):
            start = activity.get('start', '')
            finish = activity.get('finish', '')

            # 格式化时间
            if hasattr(start, 'strftime'):
                start_str = start.strftime('%H:%M')
            else:
                start_str = str(start)

            if hasattr(finish, 'strftime'):
                finish_str = finish.strftime('%H:%M')
            else:
                finish_str = str(finish)

            duration = activity.get('duration', 0)
            duration_str = f"{duration // 3600:02d}:{(duration % 3600) // 60:02d}"

            comment = activity.get('comment', '')

            lines.append(
                f"| {i} | {activity.get('type', '未知')} | "
                f"{start_str} | {finish_str} | {duration_str} | {comment} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 📱 华为运动健康数据",
            "",
        ])

        if health:
            sleep_start = health.get('sleep_start', 'N/A')
            sleep_end = health.get('sleep_end', 'N/A')
            sleep_duration = health.get('sleep_duration', 0)
            sleep_score = health.get('sleep_score', 'N/A')

            sleep_hours = sleep_duration / 3600 if sleep_duration else 0
            sleep_duration_str = f"{int(sleep_hours)}小时{int((sleep_hours % 1) * 60)}分"

            lines.extend([
                f"- **入睡时间**: {sleep_start}",
                f"- **醒来时间**: {sleep_end}",
                f"- **睡眠时长**: {sleep_duration_str}",
                f"- **睡眠评分**: {sleep_score}",
            ])

            if 'deep_sleep' in health:
                lines.append(f"- **深睡时长**: {health.get('deep_sleep', 'N/A')}")
            if 'light_sleep' in health:
                lines.append(f"- **浅睡时长**: {health.get('light_sleep', 'N/A')}")
            if 'rem_sleep' in health:
                lines.append(f"- **REM睡眠**: {health.get('rem_sleep', 'N/A')}")
        else:
            lines.append("*未获取到华为运动健康数据*")

        lines.extend([
            "",
            "---",
            "",
            "## 📊 时间分配图表",
            "",
            "```",
        ])

        # 添加简单的ASCII图表
        activity_breakdown = analysis_result.get('activity_breakdown', {})
        total_seconds = sum(activity_breakdown.values())

        if total_seconds > 0:
            for activity_type, seconds in sorted(
                activity_breakdown.items(),
                key=lambda x: x[1],
                reverse=True
            ):
                percentage = (seconds / total_seconds) * 100
                bar_length = int(percentage / 2)
                bar = '█' * bar_length
                hours = seconds / 3600
                lines.append(
                    f"{activity_type:8s} {bar:50s} {hours:5.1f}h ({percentage:5.1f}%)"
                )

        lines.extend([
            "```",
            "",
            "---",
            "",
            f"*报告由时间管理技能自动生成*",
        ])

        # 写入文件
        report_path = self.output_dir / f"time_report_{date}.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return str(report_path)

    def _generate_json(self, combined_data, analysis_result, date):
        """生成JSON格式数据文件"""

        data = {
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'combined_data': combined_data,
            'analysis': analysis_result
        }

        json_path = self.output_dir / f"time_data_{date}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        return str(json_path)
