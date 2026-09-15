#!/usr/bin/env python3
"""
华为运动健康截图解析模块

功能：
- 从截图中提取睡眠数据
- 使用 PaddleOCR 自动识别图片（可选）
- 计算清醒时长、入睡用时、醒来用时
- 计算睡眠周期数
- 保存为结构化数据
"""

import re
import logging
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

def _trace_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [value]
    return [str(value)]


class ScreenshotParser:
    """截图数据解析器"""

    def __init__(self, output_dir=None, use_ocr=False):
        r"""
        初始化解析器

        Args:
            output_dir: 数据输出目录，默认为 读取 MYTIMELOGGER_SCREENSHOT_OUTPUT_DIR
            use_ocr: 是否启用 OCR 自动识别（需要安装 PaddleOCR）
        """
        # 默认使用工作空间目录
        if output_dir is None:
            output_dir = os.getenv("MYTIMELOGGER_SCREENSHOT_OUTPUT_DIR", str(Path.cwd() / "data" / "screenshot_output"))
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.use_ocr = use_ocr
        self.ocr_extractor = None

        if use_ocr:
            try:
                from .ocr_extractor import OCRExtractor
                self.ocr_extractor = OCRExtractor()
            except ImportError:
                print("⚠️ 未安装 PaddleOCR，OCR 功能将不可用")
                print("   请运行: pip install paddleocr paddlepaddle")
                self.use_ocr = False

    def parse_sleep_data(self, text_content, image_date=None):
        """
        从截图文本中提取睡眠数据

        Args:
            text_content: OCR识别或用户提供的文本
            image_date: 截图日期 (YYYY-MM-DD)，如果为None则尝试从文本解析

        Returns:
            dict: 解析后的睡眠数据
        """
        sleep_data = {
            'date': None,
            'sleep_start': None,      # 入睡时间 (HH:MM)
            'sleep_end': None,        # 醒来时间 (HH:MM)，对应华为健康显示的"醒来"
            'night_sleep_duration': 0,      # 夜间睡眠时长（秒），华为健康显示的睡眠时长
            'night_sleep_duration_min': 0,  # 夜间睡眠时长（分钟）
            'deep_sleep': 0,          # 深睡时长（秒）
            'light_sleep': 0,         # 浅睡时长（秒）
            'rem_sleep': 0,           # REM睡眠（秒）
            'awake_time': 0,          # 清醒时长（秒）
            'awake_count': 0,         # 清醒次数
            'sleep_score': None,      # 睡眠评分
            'fall_asleep_time': 0,    # 入睡需要的时间（分钟）
            'wake_up_time': 0,        # 起床需要的时间（分钟）
            'sleep_cycles': 0.0,      # 睡眠周期数
            'analysis': {},           # 解读与建议
            'raw_text': text_content
        }

        # 1. 解析日期
        if image_date:
            sleep_data['date'] = image_date
        else:
            sleep_data['date'] = self._parse_date(text_content)

        # 2. 解析入睡和醒来时间
        sleep_data['sleep_start'] = self._parse_time(text_content, '入睡|就寝| bedtime')
        sleep_data['sleep_end'] = self._parse_time(text_content, '醒来|起床| wakeup')

        # 3. 解析夜间睡眠时长（华为健康显示的睡眠时长）
        night_sleep_seconds = self._parse_night_sleep_duration(text_content)
        if night_sleep_seconds > 0:
            sleep_data['night_sleep_duration'] = night_sleep_seconds
            sleep_data['night_sleep_duration_min'] = night_sleep_seconds / 60

        # 4. 解析深睡、浅睡、REM
        sleep_data['deep_sleep'] = self._parse_sleep_stage(text_content, '深睡|deep')
        sleep_data['light_sleep'] = self._parse_sleep_stage(text_content, '浅睡|light')
        sleep_data['rem_sleep'] = self._parse_sleep_stage(text_content, '快速眼动|REM|眼动')

        # 5. 解析清醒次数
        sleep_data['awake_count'] = self._parse_awake_count(text_content)

        # 如果清醒次数为0但文本中有"清醒次数 4次"，重新解析
        if sleep_data['awake_count'] == 0:
            awake_match = re.search(r'清醒次数\s*(\d+)\s*次', text_content)
            if awake_match:
                sleep_data['awake_count'] = int(awake_match.group(1))

        # 计算清醒时长：总在床时间 - 夜间睡眠时长
        sleep_data['awake_time'] = self._calculate_awake_time(sleep_data)

        # 6. 解析睡眠评分
        sleep_data['sleep_score'] = self._parse_sleep_score(text_content)

        # 7. 计算入睡用时和醒来用时
        sleep_data['fall_asleep_time'] = self._calculate_fall_asleep_time(text_content)
        sleep_data['wake_up_time'] = self._calculate_wake_up_time(text_content)

        # 8. 计算睡眠周期数 (每周期90分钟)
        if sleep_data['sleep_duration_min'] > 0:
            sleep_data['sleep_cycles'] = round(sleep_data['sleep_duration_min'] / 90, 2)

        # 9. 解析睡眠阶段比例
        sleep_data['deep_sleep_ratio'] = self._parse_ratio(text_content, '深睡')
        sleep_data['light_sleep_ratio'] = self._parse_ratio(text_content, '浅睡')
        sleep_data['rem_sleep_ratio'] = self._parse_ratio(text_content, 'REM')

        # 10. 解析深睡连续性和呼吸质量
        sleep_data['deep_sleep_continuity'] = self._parse_score_field(text_content, '深睡连续性')
        sleep_data['breath_quality'] = self._parse_score_field(text_content, '呼吸质量')

        # 11. 解析解读与建议
        sleep_data['analysis'] = self._parse_sleep_analysis(text_content)

        # 12. 数据逻辑复核（新增）
        self._verify_and_fix_data(sleep_data)

        return sleep_data

    def _verify_and_fix_data(self, data):
        """数据复核程序：确保关键派生指标（周期、清醒时长等）按公式计算得出"""
        try:
            # 1. 计算清醒时长 (必须依赖已有的 total_sleep_min)
            # 清醒时长 = (醒来时间 - 入睡时间) - 夜间睡眠时长
            awake_sec = self._calculate_awake_time(data)
            data['awake_time'] = awake_sec
            data['awake_min'] = int(round(awake_sec / 60.0))

            # 2. 计算睡眠周期 (按总时长 / 90分钟)
            total_min = data.get('total_sleep_min', 0)
            if total_min > 0:
                data['sleep_cycles'] = round(total_min / 90.0, 2)

            # 3. 统一字段名（兼容性）
            # fall_asleep_min 和 wake_up_min 通常在外部由 atimelogger 联动计算
            # 这里仅做字段补全
            if 'fall_asleep_min' not in data:
                data['fall_asleep_min'] = data.get('fall_asleep_time', 0)
            if 'wake_up_min' not in data:
                data['wake_up_min'] = data.get('wake_up_time', 0)

        except Exception as e:
            print(f"⚠️ 数据复核过程中出错: {e}")

    def parse_image(self, image_path, image_date=None):
        """
        从图片中直接解析睡眠数据（使用 PaddleOCR）

        Args:
            image_path: 图片路径
            image_date: 截图日期 (YYYY-MM-DD)，如果为None则尝试从图片解析

        Returns:
            dict: 解析后的睡眠数据
        """
        if not self.use_ocr or not self.ocr_extractor:
            raise RuntimeError(
                "OCR 功能未启用，请初始化时设置 use_ocr=True 并安装 PaddleOCR"
            )

        print(f"📷 使用 PaddleOCR 识别图片: {image_path}")

        # 使用 OCR 提取文本
        text_content = self.ocr_extractor.extract_text_from_image(image_path)

        print(f"✅ OCR 识别完成，文本长度: {len(text_content)} 字符")

        # 使用文本解析方法
        sleep_data = self.parse_sleep_data(text_content, image_date)

        # 添加图片来源标记
        sleep_data['source'] = 'paddleocr'
        sleep_data['image_path'] = str(image_path)

        return sleep_data

    def _parse_date(self, text):
        """从文本中解析日期"""
        # 匹配格式：2026-03-18 或 2026/03/18 或 3月18日
        patterns = [
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'(\d{1,2})月(\d{1,2})日',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    year, month, day = groups
                    return f"{year}-{int(month):02d}-{int(day):02d}"
                elif len(groups) == 2:
                    month, day = groups
                    year = datetime.now().year
                    return f"{year}-{int(month):02d}-{int(day):02d}"

        return datetime.now().strftime('%Y-%m-%d')

    def _parse_time(self, text, keyword_pattern):
        """解析时间（入睡/起床）"""
        # 华为健康特殊格式：入睡00:20 醒来07:07
        if '入睡' in keyword_pattern:
            # 匹配"入睡00:20"或"入睡 00:20"
            pattern = r'入睡\s*(\d{1,2}):(\d{2})'
            match = re.search(pattern, text)
            if match:
                return f"{int(match.group(1)):02d}:{match.group(2)}"

        if '醒来' in keyword_pattern or '起床' in keyword_pattern:
            # 匹配"醒来07:07"或"醒来 07:07"
            pattern = r'醒来\s*(\d{1,2}):(\d{2})'
            match = re.search(pattern, text)
            if match:
                return f"{int(match.group(1)):02d}:{match.group(2)}"

        # 通用匹配格式：23:30 入睡 或 入睡 23:30
        pattern = rf'(?:{keyword_pattern})\s*(\d{{1,2}}):(\d{{2}})|(\d{{1,2}}):(\d{{2}})\s*(?:{keyword_pattern})'
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            groups = match.groups()
            if groups[0] and groups[1]:
                return f"{int(groups[0]):02d}:{groups[1]}"
            elif groups[2] and groups[3]:
                return f"{int(groups[2]):02d}:{groups[3]}"

        # 尝试单独匹配时间格式
        time_pattern = r'(\d{1,2}):(\d{2})'
        matches = re.findall(time_pattern, text)
        if matches:
            # 返回第一个找到的时间
            hour, minute = matches[0]
            return f"{int(hour):02d}:{minute}"

        return None

    def _parse_duration(self, text):
        """解析睡眠时长"""
        # 匹配格式：8小时15分 或 8h15m 或 8:15 或 8小时
        patterns = [
            r'(\d+)\s*小时?\s*(\d+)\s*分',
            r'(\d+)h\s*(\d+)m',
            r'睡眠时长[\s:]*(\d+):(\d+)',
            r'共[\s:]*(\d+)\s*小时?\s*(\d*)\s*分?',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2)) if match.group(2) else 0
                return hours * 3600 + minutes * 60

        # 如果只匹配到小时
        hour_pattern = r'(\d+)\s*小时'
        match = re.search(hour_pattern, text)
        if match:
            return int(match.group(1)) * 3600

        return 0

    def _parse_sleep_stage(self, text, keyword_pattern):
        """解析睡眠阶段时长"""
        # 匹配格式：深睡 2小时30分 或 深睡 2h30m 或 深睡 2:30
        pattern = rf'(?:{keyword_pattern})\s*(\d+)\s*小时?\s*(\d+)\s*分?'
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            return hours * 3600 + minutes * 60

        # 匹配格式：深睡 150分钟
        min_pattern = rf'(?:{keyword_pattern})\s*(\d+)\s*分'
        match = re.search(min_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1)) * 60

        # 匹配格式：深睡 2.5小时
        hour_decimal_pattern = rf'(?:{keyword_pattern})\s*(\d+\.?\d*)\s*小时'
        match = re.search(hour_decimal_pattern, text, re.IGNORECASE)
        if match:
            hours = float(match.group(1))
            return int(hours * 3600)

        return 0

    def _parse_awake_time(self, text):
        """解析清醒时长"""
        patterns = [
            r'清醒\s*(\d+)\s*小时?\s*(\d+)\s*分?',
            r'清醒\s*(\d+)\s*分',
            r' awake\s*(\d+)\s*min',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) > 1 and match.group(2):
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    return hours * 3600 + minutes * 60
                else:
                    return int(match.group(1)) * 60

        return 0

    def _parse_awake_count(self, text):
        """解析清醒次数"""
        pattern = r'清醒\s*(\d+)\s*次'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
        return 0

    def _parse_sleep_score(self, text):
        """解析睡眠评分"""
        patterns = [
            r'睡眠.*?评分\s*(\d+)',
            r'睡眠质量\s*(\d+)\s*分',
            r'得分\s*(\d+)',
            r'(\d+)\s*分',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                score = int(match.group(1))
                if 0 <= score <= 100:
                    return score

        return None

    def calculate_sleep_transition_times(self, sleep_data, atimelogger_activities):
        """
        计算入睡需要的时间和起床需要的时间

        公式：
        - 入睡需要的时间 = 华为健康入睡时间 - aTimeLogger「睡觉」开始时间
        - 醒来需要的时间 = aTimeLogger「睡觉」结束时间 - 华为健康醒来时间

        Args:
            sleep_data: 睡眠数据字典
            atimelogger_activities: aTimeLogger活动列表

        Returns:
            tuple: (fall_asleep_minutes, wake_up_minutes)
        """
        fall_asleep_time = 0
        wake_up_time = 0
        trace = []

        # 获取华为健康的入睡和醒来时间
        huawei_sleep_start = sleep_data.get('sleep_start')  # 格式: "HH:MM"
        huawei_sleep_end = sleep_data.get('sleep_end')  # 格式: "HH:MM"
        sleep_date = sleep_data.get('date')  # 格式: "YYYY-MM-DD"

        if not huawei_sleep_start or not huawei_sleep_end or not sleep_date:
            logger.info(
                "[sleep-report] transition skipped date=%s reason=missing_huawei_time sleep_start=%s sleep_end=%s",
                sleep_date,
                huawei_sleep_start,
                huawei_sleep_end,
            )
            return fall_asleep_time, wake_up_time, None, None

        try:
            # 解析华为健康时间
            # 核心修正：华为记录日期通常是“醒来日期”
            huawei_bedtime = datetime.strptime(f"{sleep_date} {huawei_sleep_start}", "%Y-%m-%d %H:%M")
            huawei_wake_time = datetime.strptime(f"{sleep_date} {huawei_sleep_end}", "%Y-%m-%d %H:%M")

            # 处理跨天情况：如果入睡时间（如23:30）数值上大于醒来时间（如07:00）
            # 且它们标记的是同一天，则说明入睡其实发生在“前一天”
            if huawei_bedtime > huawei_wake_time:
                huawei_bedtime -= timedelta(days=1)
            logger.info(
                "[sleep-report] transition huawei date=%s sleep_start=%s normalized_start=%s sleep_end=%s normalized_end=%s",
                sleep_date,
                huawei_sleep_start,
                huawei_bedtime,
                huawei_sleep_end,
                huawei_wake_time,
            )

            matched_start_naive = None
            matched_finish_naive = None
            min_start_diff = float('inf')
            min_finish_diff = float('inf')

            # 从aTimeLogger活动中查找「上床」和「起床」记录
            for activity in atimelogger_activities:
                activity_type = activity.get('type', '')
                start_time = activity.get('start')
                finish_time = activity.get('finish')

                # 核心修正：aTimeLogger 数据通常带秒，而华为数据仅精确到分钟。
                # 在计算前抹掉秒和毫秒，确保计算基准完全对齐。
                china_tz = timezone(timedelta(hours=8))
                if isinstance(start_time, str):
                    start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if isinstance(finish_time, str):
                    finish_time = datetime.fromisoformat(finish_time.replace('Z', '+00:00'))

                if start_time:
                    start_time = start_time.astimezone(china_tz).replace(tzinfo=None, second=0, microsecond=0)
                if finish_time:
                    finish_time = finish_time.astimezone(china_tz).replace(tzinfo=None, second=0, microsecond=0)

                # 计算入睡需要的时间：aTimeLogger上床/睡觉开始时间 → 华为健康入睡时间
                if '上床' in activity_type or '就寝' in activity_type or 'bed' in activity_type.lower() or '睡觉' in activity_type:
                    if start_time:
                        # 统一去掉时区信息（aTimeLogger是UTC+8，转为naive后直接用）
                        if hasattr(start_time, 'tzinfo') and start_time.tzinfo:
                            start_naive = start_time.replace(tzinfo=None)
                        else:
                            start_naive = start_time

                        # 公式：华为入睡时间 - 上床时间（正数 = 上床后X分钟睡着）
                        raw_time_diff = (huawei_bedtime - start_naive).total_seconds() / 60

                        # 跨天修正
                        time_diff = raw_time_diff
                        if time_diff > 720:
                            time_diff -= 24 * 60
                        elif time_diff < -720:
                            time_diff += 24 * 60

                        event = (
                            f"入睡候选: 华为入睡({huawei_bedtime}) - aTimeLogger开始({start_naive}) "
                            f"= raw {raw_time_diff:.2f}min, normalized {time_diff:.2f}min, no_range_filter"
                        )
                        trace.append(event)
                        logger.info("[sleep-report] transition candidate kind=fall_asleep activity=%s raw_diff_min=%.2f normalized_diff_min=%.2f no_range_filter=true", activity_type, raw_time_diff, time_diff)

                        candidate_score = abs(time_diff)
                        if candidate_score < min_start_diff:
                            fall_asleep_time = int(round(time_diff))
                            matched_start_naive = start_naive
                            min_start_diff = candidate_score
                            logger.info("[sleep-report] transition selected kind=fall_asleep value_min=%s atm_start=%s no_range_filter=true", fall_asleep_time, matched_start_naive)

                # 计算醒来需要的时间：华为醒来时间 → aTimeLogger起床结束时间
                if '起床' in activity_type or 'wake' in activity_type.lower() or '睡觉' in activity_type:
                    if finish_time:
                        if hasattr(finish_time, 'tzinfo') and finish_time.tzinfo:
                            finish_naive = finish_time.replace(tzinfo=None)
                        else:
                            finish_naive = finish_time

                        # 公式：起床活动结束时间 - 华为醒来时间（正数 = 醒后X分钟才起床）
                        raw_time_diff = (finish_naive - huawei_wake_time).total_seconds() / 60

                        # 跨天修正
                        time_diff = raw_time_diff
                        if time_diff > 720:
                            time_diff -= 24 * 60
                        elif time_diff < -720:
                            time_diff += 24 * 60

                        event = (
                            f"起床候选: aTimeLogger结束({finish_naive}) - 华为醒来({huawei_wake_time}) "
                            f"= raw {raw_time_diff:.2f}min, normalized {time_diff:.2f}min, no_range_filter"
                        )
                        trace.append(event)
                        logger.info("[sleep-report] transition candidate kind=wake_up activity=%s raw_diff_min=%.2f normalized_diff_min=%.2f no_range_filter=true", activity_type, raw_time_diff, time_diff)

                        candidate_score = abs(time_diff)
                        if candidate_score < min_finish_diff:
                            wake_up_time = int(round(time_diff))
                            matched_finish_naive = finish_naive
                            min_finish_diff = candidate_score
                            logger.info("[sleep-report] transition selected kind=wake_up value_min=%s atm_end=%s no_range_filter=true", wake_up_time, matched_finish_naive)

        except Exception as e:
            logger.exception("[sleep-report] transition failed date=%s error=%s", sleep_date, e)

        atm_start_str = matched_start_naive.strftime("%H:%M") if matched_start_naive else None
        atm_end_str = matched_finish_naive.strftime("%H:%M") if matched_finish_naive else None
        trace.append(f"最终入睡用时: {fall_asleep_time}min; 最终起床用时: {wake_up_time}min; no_range_filter")
        sleep_data["calc_trace"] = _trace_list(sleep_data.get("calc_trace")) + trace
        logger.info(
            "[sleep-report] transition final date=%s fall_asleep_min=%s wake_up_min=%s atm_sleep_start=%s atm_sleep_end=%s no_range_filter=true",
            sleep_date,
            fall_asleep_time,
            wake_up_time,
            atm_start_str,
            atm_end_str,
        )

        return fall_asleep_time, wake_up_time, atm_start_str, atm_end_str

    def _calculate_fall_asleep_time(self, text):
        """计算入睡需要的时间（分钟）- 从文本解析"""
        # 尝试从文本中直接解析
        pattern = r'入睡.*?用时\s*(\d+)\s*分'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))

        pattern2 = r'(?:fall\s*asleep|入睡).*?(\d+)\s*min'
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # 默认值：如果没有找到，返回0
        return 0

    def _calculate_wake_up_time(self, text):
        """计算起床需要的时间（分钟）- 从文本解析"""
        # 尝试从文本中直接解析
        pattern = r'起床.*?用时\s*(\d+)\s*分'
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))

        pattern2 = r'(?:wake\s*up|起床).*?(\d+)\s*min'
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # 默认值
        return 0

    def _parse_night_sleep_duration(self, text):
        """
        解析夜间睡眠时长（华为健康显示的睡眠时长）

        Args:
            text: 截图文本

        Returns:
            int: 夜间睡眠时长（秒）
        """
        # 匹配格式：夜间睡眠 7小时8分钟 或 夜间睡眠 7小时 或 夜间睡眠 8h15m
        patterns = [
            r'夜间睡眠\s*(\d+)\s*小时?\s*(\d+)\s*分',
            r'夜间睡眠\s*(\d+)h\s*(\d+)m',
            r'夜间睡眠\s*(\d+)\s*小时',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hours = int(match.group(1))
                minutes = int(match.group(2)) if len(match.groups()) > 1 and match.group(2) else 0
                return hours * 3600 + minutes * 60

        return 0

    def _calculate_awake_time(self, sleep_data):
        """
        计算清醒时长

        清醒时长 = 总在床时间 - 夜间睡眠时长
        其中：总在床时间 = 醒来时间 - 入睡时间

        注意：华为健康的"夜间睡眠"等于深睡+浅睡+REM，清醒时长需要单独计算

        Args:
            sleep_data: 睡眠数据字典

        Returns:
            int: 清醒时长（秒）
        """
        sleep_start = sleep_data.get('sleep_start')
        sleep_end = sleep_data.get('sleep_end')
        night_sleep_duration = sleep_data.get('night_sleep_duration', 0)

        if not sleep_start or not sleep_end or night_sleep_duration == 0:
            return 0

        try:
            # 解析时间
            start_hour, start_min = map(int, sleep_start.split(':'))
            end_hour, end_min = map(int, sleep_end.split(':'))

            # 计算总在床时长（分钟）
            start_total_min = start_hour * 60 + start_min
            end_total_min = end_hour * 60 + end_min

            # 处理跨天情况
            if end_total_min < start_total_min:
                end_total_min += 24 * 60  # 加24小时

            total_in_bed_min = end_total_min - start_total_min
            total_in_bed_sec = total_in_bed_min * 60

            # 清醒时长 = 总在床时间 - 夜间睡眠时长
            awake_time = total_in_bed_sec - night_sleep_duration

            # 如果计算结果为负（数据不一致），设为0
            return max(0, awake_time)

        except Exception as e:
            print(f"计算清醒时长失败: {e}")
            return 0

    def _parse_sleep_analysis(self, text):
        """
        解析睡眠分析与建议

        Args:
            text: 截图文本

        Returns:
            dict: 分析与建议
        """
        analysis = {
            'summary': '',
            'suggestions': [],
            'issues': []
        }

        # 提取解读与建议部分
        analysis_section = ''
        if '解读与建议' in text:
            # 提取"解读与建议"之后的所有内容
            parts = text.split('解读与建议')
            if len(parts) > 1:
                analysis_section = parts[1].strip()

        if analysis_section:
            # 提取总结（第一段）
            lines = analysis_section.split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 10:
                    analysis['summary'] = line
                    break

            # 提取问题关键词
            issue_keywords = ['易醒', '不足', '较长', '偏短', '问题', '风险']
            for keyword in issue_keywords:
                if keyword in analysis_section:
                    # 找到包含关键词的句子
                    sentences = analysis_section.split('。')
                    for sentence in sentences:
                        if keyword in sentence and len(sentence) > 5:
                            issue = sentence.strip()
                            if issue and issue not in analysis['issues']:
                                analysis['issues'].append(issue)
                            break

            # 提取建议（包含"建议"的句子）
            sentences = analysis_section.split('。')
            for sentence in sentences:
                if '建议' in sentence or '可以' in sentence or '尝试' in sentence:
                    suggestion = sentence.strip()
                    if suggestion and len(suggestion) > 5 and suggestion not in analysis['suggestions']:
                        analysis['suggestions'].append(suggestion)

        return analysis

    def _parse_ratio(self, text, keyword):
        """
        解析睡眠阶段比例

        Args:
            text: 文本内容
            keyword: 关键词（深睡、浅睡、REM）

        Returns:
            int: 比例（百分比，如 26 表示 26%）
        """
        # 匹配格式：深睡 26% 或 深睡比例 26%
        pattern = rf'{keyword}.*?(\d+)\s*[%％]'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0

    def _parse_score_field(self, text, keyword):
        """
        解析评分字段

        Args:
            text: 文本内容
            keyword: 关键词（深睡连续性、呼吸质量）

        Returns:
            int: 评分
        """
        # 匹配格式：深睡连续性 70分 或 呼吸质量 98分
        pattern = rf'{keyword}.*?(\d+)\s*分?'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            score = int(match.group(1))
            if 0 <= score <= 100:
                return score
        return 0

    def save_sleep_data(self, sleep_data):
        """
        保存睡眠数据到JSON文件

        Args:
            sleep_data: 睡眠数据字典

        Returns:
            str: 保存的文件路径
        """
        import json

        date = sleep_data.get('date')
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        output_file = self.output_dir / f"sleep_{date}.json"

        # 添加保存时间
        sleep_data['saved_at'] = datetime.now().isoformat()

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(sleep_data, f, ensure_ascii=False, indent=2)

        return str(output_file)

    def format_sleep_summary(self, sleep_data):
        """
        格式化睡眠数据摘要

        Args:
            sleep_data: 睡眠数据字典

        Returns:
            str: 格式化的摘要文本
        """
        lines = [
            f"📅 日期: {sleep_data.get('date', 'N/A')}",
            f"🛏️ 入睡时间: {sleep_data.get('sleep_start', 'N/A')}",
            f"🌅 醒来时间: {sleep_data.get('sleep_end', 'N/A')}",
            f"⏱️ 睡眠时长: {sleep_data.get('sleep_duration_min', 0):.0f}分钟 ({sleep_data.get('sleep_duration_min', 0)/60:.1f}小时)",
            f"😴 深睡: {sleep_data.get('deep_sleep', 0)/60:.0f}分钟",
            f"😌 浅睡: {sleep_data.get('light_sleep', 0)/60:.0f}分钟",
            f"👁️ REM: {sleep_data.get('rem_sleep', 0)/60:.0f}分钟",
            f"👀 清醒: {sleep_data.get('awake_time', 0)/60:.0f}分钟 (共{sleep_data.get('awake_count', 0)}次)",
            f"📊 睡眠评分: {sleep_data.get('sleep_score', 'N/A')}分",
            f"⏰ 入睡用时: {sleep_data.get('fall_asleep_time', 0)}分钟",
            f"🌄 起床用时: {sleep_data.get('wake_up_time', 0)}分钟",
            f"🔄 睡眠周期: {sleep_data.get('sleep_cycles', 0)}个",
        ]

        # 添加解读与建议
        analysis = sleep_data.get('analysis', {})
        if analysis:
            lines.append("")
            lines.append("💡 睡眠分析:")

            if analysis.get('summary'):
                lines.append(f"  总结: {analysis['summary']}")

            if analysis.get('issues'):
                lines.append("  问题:")
                for issue in analysis['issues']:
                    lines.append(f"    - {issue}")

            if analysis.get('suggestions'):
                lines.append("  建议:")
                for suggestion in analysis['suggestions']:
                    lines.append(f"    - {suggestion}")

        return '\n'.join(lines)
