#!/usr/bin/env python3
"""
aTimeLogger数据提取模块

功能：
- 通过API获取时间记录数据
- 处理跨天记录的正确归属
- 转换时区为中国时区
"""

import requests
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict


class AtimeloggerExtractor:
    """aTimeLogger数据提取器"""

    def __init__(self, config):
        """
        初始化提取器

        Args:
            config: 配置字典，包含 base_url, username, password
        """
        self.config = config or {}
        self.base_url = self.config.get('base_url', 'https://app.atimelogger.pro')
        self.username = self.config.get('username', '')
        self.password = self.config.get('password', '')
        self.session = None
        self.token = None
        self.saved_token = self.config.get('token', '')
        self.failure_reason = None
        self.types_map = {}
        self.china_tz = timezone(timedelta(hours=8))

        # 睡眠相关关键字
        self.sleep_keywords = ['睡觉', '睡眠', '上床', '起床', 'Sleep', 'Bed', 'Wake']

    def _login(self):
        """优先复用 Token；无效时再用账号密码重新获取。"""
        if self.token:
            return True

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Origin': 'https://app.atimelogger.pro',
            'Content-Type': 'application/json'
        })

        if self.saved_token:
            self.token = self.saved_token
            self.session.headers['Authorization'] = f'Bearer {self.token}'
            try:
                self._load_types()
                return True
            except requests.HTTPError as exc:
                if not self._is_auth_error(exc):
                    self.failure_reason = "aTimeLogger 连接失败，请检查网络后重试。"
                    return False
                self.token = None
                self.session.headers.pop('Authorization', None)
            except requests.RequestException:
                self.failure_reason = "aTimeLogger 连接失败，请检查网络后重试。"
                return False

        if not self.username or not self.password:
            self.failure_reason = "aTimeLogger 未配置可用授权，请在设置中重新保存账号密码后重试。"
            return False

        try:
            resp = self.session.post(
                f'{self.base_url}/auth/jwt',
                json={'username': self.username, 'password': self.password},
                timeout=30,
                verify=False
            )
            resp.raise_for_status()
            self.token = resp.json()['token']
            self.session.headers['Authorization'] = f'Bearer {self.token}'
            self._load_types()
            return True
        except requests.HTTPError as exc:
            self.failure_reason = (
                "aTimeLogger 授权已失效，请在设置中重新保存账号密码后重试。"
                if self._is_auth_error(exc)
                else "aTimeLogger 登录失败，请稍后重试。"
            )
            return False
        except (requests.RequestException, KeyError, ValueError):
            self.failure_reason = "aTimeLogger 登录失败，请稍后重试。"
            return False

    @staticmethod
    def _is_auth_error(exc):
        response = getattr(exc, 'response', None)
        return getattr(response, 'status_code', None) in (401, 403)

    def _load_types(self):
        """加载活动类型映射"""
        resp = self.session.get(f'{self.base_url}/api/types', timeout=30, verify=False)
        resp.raise_for_status()
        types = resp.json()
        self.types_map = {t['id']: t for t in types}

    def _parse_iso_time(self, iso_string):
        """解析ISO 8601时间字符串并转换为中国时区"""
        if iso_string.endswith('Z'):
            iso_string = iso_string[:-1] + '+00:00'

        utc_dt = datetime.fromisoformat(iso_string)
        return utc_dt.astimezone(self.china_tz)

    def extract_daily_data(self, date_str):
        """
        提取指定日期的数据

        Args:
            date_str: 日期字符串 (YYYY-MM-DD)

        Returns:
            dict: 包含活动列表的数据字典
        """
        if not self._login():
            return None

        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        prev_date = target_date - timedelta(days=1)
        next_date = target_date + timedelta(days=1)

        # 查询前后三天以确保获取所有跨天记录
        payload = {
            'from': prev_date.strftime('%Y-%m-%d'),
            'to': next_date.strftime('%Y-%m-%d')
        }

        try:
            resp = self.session.post(
                f'{self.base_url}/api/intervals',
                json=payload,
                timeout=30,
                verify=False
            )
            resp.raise_for_status()

            data = resp.json()

            activities = []
            for day in data.get('content', []):
                for interval in day.get('intervals', []):
                    activity = self._process_interval(interval, target_date)
                    if activity:
                        activities.append(activity)

            # 按开始时间排序，跨天记录排在最前面
            def sort_key(act):
                start_time = act['start']
                if start_time.date() < target_date:
                    return datetime.combine(target_date, datetime.min.time()).replace(tzinfo=self.china_tz) - timedelta(seconds=1)
                return start_time

            activities.sort(key=sort_key)

            # 计算统计信息
            type_durations = defaultdict(int)
            total_duration = 0

            for activity in activities:
                type_durations[activity['type']] += activity['duration']
                total_duration += activity['duration']

            return {
                'date': date_str,
                'activities': activities,
                'summary': {
                    'total_activities': len(activities),
                    'total_duration': total_duration,
                    'type_durations': dict(type_durations)
                }
            }

        except requests.HTTPError as exc:
            if self._is_auth_error(exc):
                self.failure_reason = "aTimeLogger 授权已失效，请在设置中重新保存账号密码后重试。"
            else:
                self.failure_reason = "aTimeLogger 数据获取失败，请稍后重试。"
            return None
        except requests.RequestException:
            self.failure_reason = "aTimeLogger 连接失败，请检查网络后重试。"
            return None
        except (ValueError, KeyError, TypeError):
            self.failure_reason = "aTimeLogger 数据解析失败，请稍后重试。"
            return None

    def _process_interval(self, interval, target_date):
        """
        处理单个时间间隔，判断是否应该归属到目标日期

        Args:
            interval: API返回的interval数据
            target_date: 目标日期

        Returns:
            dict or None: 处理后的活动数据
        """
        type_id = interval.get('typeId')
        type_info = self.types_map.get(type_id, {'name': '未知', 'id': type_id})

        start = self._parse_iso_time(interval.get('start'))
        finish = self._parse_iso_time(interval.get('finish'))
        duration = interval.get('duration', 0)

        start_date = start.date()
        finish_date = finish.date()

        # 判断是否跨天
        crosses_midnight = start_date != finish_date

        if not crosses_midnight:
            # 不跨天，直接判断
            if start_date == target_date:
                return {
                    'type': type_info['name'],
                    'start': start,
                    'finish': finish,
                    'duration': duration,
                    'comment': interval.get('comment', ''),
                    'tags': interval.get('tags', [])
                }
            # 特殊逻辑：如果是“上床”记录且发生在前一天晚上（18:00后），也包含进来用于计算
            if type_info['name'] in ['上床', 'Bed'] and start_date == (target_date - timedelta(days=1)) and start.hour >= 18:
                return {
                    'type': type_info['name'],
                    'start': start,
                    'finish': finish,
                    'duration': duration,
                    'comment': interval.get('comment', ''),
                    'tags': interval.get('tags', [])
                }
        else:
            # 跨天记录，判定归属
            # 核心策略：只要该活动与 target_date 有重叠，就包含进来（哪怕只有1秒）
            # 1. 睡眠相关活动：归属于结束日期（起床日期）
            is_sleep_related = any(kw in type_info['name'] for kw in self.sleep_keywords)

            if is_sleep_related:
                if finish_date == target_date:
                    return {
                        'type': type_info['name'], 'start': start, 'finish': finish,
                        'duration': duration, 'comment': interval.get('comment', ''), 'tags': interval.get('tags', [])
                    }
            else:
                # 2. 普通活动：只要跨越了 target_date 就算
                # 情况A: 开始于 target_date (必然在 target_date 有时长)
                # 情况B: 结束于 target_date (必然在 target_date 有时长)
                # 情况C: 横跨整个 target_date (start < target < finish)
                if start_date == target_date or finish_date == target_date or (start_date < target_date < finish_date):
                    return {
                        'type': type_info['name'], 'start': start, 'finish': finish,
                        'duration': duration, 'comment': interval.get('comment', ''), 'tags': interval.get('tags', [])
                    }

        return None
