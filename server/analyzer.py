# -*- coding: utf-8 -*-
"""
Pure Python sleep analysis pipeline.

This module intentionally has no PyQt dependency so it can be reused by the
desktop worker and the server FastAPI service.
"""

import base64
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime

import httpx
from openai import OpenAI


logger = logging.getLogger(__name__)

NO_MAIN_SLEEP_STATE = "no_main_sleep"
NO_MAIN_SLEEP_WARNING = "无睡眠，严重警告！"
NO_MAIN_SLEEP_ZERO_FIELDS = (
    "sleep_score", "deep_sleep_min", "light_sleep_min", "rem_sleep_min",
    "awake_min", "awake_count", "deep_sleep_ratio", "light_sleep_ratio",
    "rem_sleep_ratio", "sleep_continuity", "breathing_score", "total_sleep_min",
    "sleep_cycles", "fall_asleep_min", "wake_up_min",
)


def clean_url(url):
    """Normalize OpenAI-compatible base URLs."""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-len("/chat/completions")].rstrip("/")
    return url


def to_min(val):
    """Convert duration values such as '1小时20分' or '80min' to minutes."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).lower()
    h_match = re.search(r"(\d+)\s*(?:h|小时|时)", s)
    m_match = re.search(r"(\d+)\s*(?:m|分钟|分)", s)
    total = 0
    if h_match:
        total += int(h_match.group(1)) * 60
    if m_match:
        total += int(m_match.group(1))
    if total > 0:
        return total
    try:
        clean_s = re.sub(r"[^\d.]", "", s)
        if not clean_s:
            return 0
        return int(float(clean_s))
    except Exception:
        return 0


def clean_num(val):
    """Extract a numeric value from model output."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return val
    try:
        clean_s = re.sub(r"[^\d.]", "", str(val))
        if not clean_s:
            return 0
        num = float(clean_s)
        return int(num) if num == int(num) else num
    except Exception:
        return 0


SLEEP_REQUIRED_FIELD_LABELS = {
    "sleep_score": "睡眠评分",
    "deep_sleep_min": "深睡时长",
    "deep_sleep_ratio": "深睡比例",
    "sleep_start": "入睡时间",
    "sleep_end": "醒来时间",
    "total_sleep_min": "夜间睡眠时长",
    "official_advice": "华为官方建议原文",
}


def _is_missing_sleep_value(value):
    if value is None or value == "":
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "null", "none", "无", "未识别", "无法识别"}:
        return True
    return False


def _sleep_validation_snapshot(data):
    parts = []
    for key, label in SLEEP_REQUIRED_FIELD_LABELS.items():
        value = data.get(key)
        display = "--" if _is_missing_sleep_value(value) else value
        parts.append(f"{label}({key})={display}")
    return "；".join(parts)


def _format_missing_sleep_fields(missing):
    return "、".join(f"{SLEEP_REQUIRED_FIELD_LABELS.get(key, key)}({key})" for key in missing)


def _official_advice_is_incomplete(value):
    if _is_missing_sleep_value(value):
        return False
    text = re.sub(r"\s+", "", str(value))
    if not text:
        return False
    starts_with_suggestion = text.startswith("建议") or text.startswith("睡眠建议")
    has_interpretation = any(
        marker in text
        for marker in (
            "睡眠时长",
            "长期睡眠",
            "免疫力",
            "待改善",
            "严重不足",
            "不足",
            "优秀",
            "良好",
            "一般",
            "较差",
        )
    )
    return starts_with_suggestion and not has_interpretation


@dataclass
class SleepAnalysisResult:
    date: str = ""
    sleep_data: dict | None = None
    analysis_report: str = ""
    report_path: str = ""
    status: str = "error"
    error: str = ""

    def to_dict(self):
        return asdict(self)


class SleepAnalyzer:
    """
    睡眠截图分析器，可在服务端后台任务和 PC 客户端本地分析两种场景下复用。

    【两种使用场景】
    1. 服务端后台任务（server.py 的 _run_analysis）：
       - 由 FastAPI BackgroundTasks 在独立线程中调用
       - image_path 为上传图片的本地路径
       - 通过 progress_callback 将进度推送到 SSE 队列

    2. PC 客户端本地分析（gui.py 的睡眠分析按钮）：
       - 在 QThread 中调用，通过 progress_callback 更新 UI 进度条
       - db 参数传入 StudyLogger 实例，用于读写本地 huawei_sleep_data 表

    【数据库恢复逻辑】
    初始化时若 sleep_data 为空且传入了 db 和 date_str，会自动从数据库查询
    该日期的已有数据。若数据完整（通过 validate_data 校验），则跳过 OCR 识别。

    Args:
        ai_cfg: AI 模型配置字典（vision_api_key、vision_model 等）
        image_path: 睡眠截图的本地文件路径（可为 None，此时依赖数据库恢复）
        sleep_data: 已有的睡眠数据字典（外部传入时跳过 OCR）
        date_str: 目标日期字符串（YYYY-MM-DD），用于数据库查询和日期校验
        include_time_analysis: True 时生成完整报告（含时间管理部分），False 时仅生成睡眠报告
        db: StudyLogger 实例，用于数据库恢复和报告生成时的数据查询
        progress_callback: 进度回调函数 callback(msg: str)，每个关键步骤调用一次
    """

    def __init__(
        self,
        ai_cfg,
        image_path=None,
        sleep_data=None,
        date_str=None,
        include_time_analysis=False,
        db=None,
        progress_callback=None,
        force_refresh=False,
        pre_report_callback=None,
        report_provider_config=None,
        user_id=None,
    ):
        self.ai_cfg = ai_cfg or {}
        self.image_path = image_path
        self.sleep_data = sleep_data
        self.date_str = date_str
        self.include_time_analysis = include_time_analysis
        self.db = db
        self.progress_callback = progress_callback
        self.force_refresh = force_refresh
        self.pre_report_callback = pre_report_callback
        self.report_provider_config = report_provider_config if isinstance(report_provider_config, dict) else {
            "ai_model_config": self.ai_cfg,
        }
        self.user_id = user_id

        # 逻辑恢复与合并：如果有目标日期且配置了 db，去数据库捞取本地的睡眠数据进行合并
        if self.db and self.date_str:
            if getattr(self.db, "requires_report_user_id", False):
                if not isinstance(self.user_id, int):
                    raise ValueError("server_sleep_report_user_id_required")
                existing = self.db.get_huawei_sleep_data(self.user_id, self.date_str)
            else:
                existing = self.db.get_huawei_sleep_data(self.date_str)
            if existing:
                if not self.sleep_data:
                    self.sleep_data = {}
                # 合并本地的核心睡眠指标，保留已有键 (防止覆盖由外部或服务端传入的日记等内容)
                for k, v in existing.items():
                    if k not in self.sleep_data or self.sleep_data[k] is None or self.sleep_data[k] == '':
                        self.sleep_data[k] = v
                logger.info(f"从数据库恢复并合并了 {self.date_str} 的已有睡眠数据")

    def progress(self, msg):
        if self.progress_callback:
            self.progress_callback(msg)

    @staticmethod
    def validate_data(data):
        """Validate raw Huawei sleep OCR fields."""
        if SleepAnalyzer.is_no_main_sleep(data):
            sleep_date = str(data.get("sleep_date") or data.get("date") or "")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sleep_date):
                return True, ""
            return False, "无有效主睡眠事实缺少有效日期(sleep_date)。"
        required = [
            "sleep_score",
            "deep_sleep_min",
            "deep_sleep_ratio",
            "sleep_start",
            "sleep_end",
            "total_sleep_min",
            "official_advice",
        ]
        missing = []
        for key in required:
            val = data.get(key)
            if _is_missing_sleep_value(val):
                missing.append(key)

        if missing:
            msg = (
                f"睡眠数据不完整：缺失 {_format_missing_sleep_fields(missing)}。"
                f"已识别字段：{_sleep_validation_snapshot(data)}"
            )
            logger.warning(f"[校验失败] {msg}")
            return False, msg

        if _official_advice_is_incomplete(data.get("official_advice")):
            msg = (
                "睡眠数据不完整：华为官方建议原文(official_advice)只识别到建议卡片，"
                "缺少“解读与建议”区域前半段解读原文。"
                f"已识别字段：{_sleep_validation_snapshot(data)}"
            )
            logger.warning(f"[校验失败] {msg}")
            return False, msg

        try:
            total = to_min(data.get("total_sleep_min", 0))
            deep = to_min(data.get("deep_sleep_min", 0))
            light = to_min(data.get("light_sleep_min", 0))
            rem = to_min(data.get("rem_sleep_min", 0))
            sum_stages = deep + light + rem
            if total != sum_stages:
                msg = (
                    f"睡眠数据数学校验失败：夜间睡眠时长({total}分钟) != "
                    f"睡眠阶段之和({sum_stages}分钟) [深睡{deep}+浅睡{light}+REM{rem}]。"
                    f"已识别字段：{_sleep_validation_snapshot(data)}"
                )
                logger.warning(f"[校验失败] {msg}")
                return False, msg
            logger.debug(f"[校验通过] 数学逻辑自洽: {total} == {sum_stages}")
        except Exception as exc:
            logger.debug(f"[校验跳过] 数学检查异常: {exc}")

        return True, ""

    @staticmethod
    def is_no_main_sleep(data):
        return isinstance(data, dict) and (
            data.get("record_state") == NO_MAIN_SLEEP_STATE
            or data.get("full_report_state") == NO_MAIN_SLEEP_STATE
        )

    @staticmethod
    def normalize_no_main_sleep(data):
        normalized = dict(data or {})
        sleep_date = normalized.get("sleep_date") or normalized.get("date")
        normalized.update({field: 0 for field in NO_MAIN_SLEEP_ZERO_FIELDS})
        normalized.update({
            "sleep_date": sleep_date,
            "date": sleep_date,
            "record_state": NO_MAIN_SLEEP_STATE,
            "full_report_state": NO_MAIN_SLEEP_STATE,
            "sleep_start": None,
            "sleep_end": None,
            "official_advice": NO_MAIN_SLEEP_WARNING,
            "analysis_report": NO_MAIN_SLEEP_WARNING,
            "report_status": 1,
        })
        return normalized

    @staticmethod
    def normalize_data(data):
        if not data or not isinstance(data, dict):
            return data

        time_fields = [
            "deep_sleep_min",
            "light_sleep_min",
            "rem_sleep_min",
            "awake_min",
            "fall_asleep_min",
            "wake_up_min",
            "total_sleep_min",
        ]
        for field in time_fields:
            if field in data:
                data[field] = to_min(data[field])

        num_fields = [
            "sleep_score",
            "sleep_cycles",
            "awake_count",
            "deep_sleep_ratio",
            "light_sleep_ratio",
            "rem_sleep_ratio",
            "sleep_continuity",
            "breathing_score",
        ]
        for field in num_fields:
            if field in data:
                data[field] = clean_num(data[field])

        official_advice = (
            data.get("official_advice")
            or data.get("huawei_advice")
            or data.get("huawei_official_advice")
        )
        if official_advice is not None:
            normalized_advice = str(official_advice).strip()
            if normalized_advice.lower() in {"null", "none", "无", "未识别", "无法识别"}:
                normalized_advice = ""
            data["official_advice"] = normalized_advice

        total = data.get("total_sleep_min", 0)
        if total and total > 0:
            if data.get("deep_sleep_ratio") is None and data.get("deep_sleep_min") is not None:
                data["deep_sleep_ratio"] = round(to_min(data["deep_sleep_min"]) / total * 100)
            if data.get("light_sleep_ratio") is None and data.get("light_sleep_min") is not None:
                data["light_sleep_ratio"] = round(to_min(data["light_sleep_min"]) / total * 100)
            if data.get("rem_sleep_ratio") is None and data.get("rem_sleep_min") is not None:
                data["rem_sleep_ratio"] = round(to_min(data["rem_sleep_min"]) / total * 100)

        return data

    @staticmethod
    def extract_json(text):
        if not text:
            return None
        if "```" in text:
            try:
                json_part = text.split("```")[1].replace("json", "").strip()
                return json.loads(json_part)
            except Exception:
                pass
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            candidate = match.group(1)
            try:
                return json.loads(candidate)
            except Exception:
                pass
        brace_count = 0
        first_brace = -1
        for idx, char in enumerate(text):
            if char == "{":
                if first_brace == -1:
                    first_brace = idx
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0 and first_brace != -1:
                    try:
                        return json.loads(text[first_brace : idx + 1])
                    except Exception:
                        continue
        return None

    def _load_prompt(self):
        # 路径修正：现在 analyzer.py 和 skills 都在 server/ 子目录下
        root_dir = os.path.dirname(__file__)
        skill_path = os.path.join(root_dir, "skills", "time-management", "SKILL.md")
        try:
            if os.path.exists(skill_path):
                with open(skill_path, "r", encoding="utf-8") as file:
                    content = file.read()
                if "```vision_prompt" in content:
                    return content.split("```vision_prompt")[1].split("```")[0].strip()
                if "```text" in content:
                    return content.split("```text")[1].split("```")[0].strip()
        except Exception:
            logger.exception("读取睡眠视觉 Prompt 失败")

        return (
            "请从睡眠截图中精确提取以下 13 个原始指标并以纯 JSON 格式返回。严禁任何开场白、Markdown 符号或额外计算：\n"
            "1. sleep_date (日期, YYYY-MM-DD)\n"
            "2. sleep_score (睡眠评分)\n"
            "3. total_sleep_min (夜间睡眠时长, 对应'夜间睡眠')\n"
            "4. deep_sleep_min (深睡时长)\n"
            "5. light_sleep_min (浅睡时长)\n"
            "6. rem_sleep_min (快速眼动/REM时长)\n"
            "7. awake_count (清醒次数)\n"
            "8. sleep_start (入睡时刻, e.g. 23:30)\n"
            "9. sleep_end (醒来时刻, e.g. 07:00)\n"
            "10. deep_sleep_ratio (深睡比例 %)\n"
            "11. light_sleep_ratio (浅睡比例 %)\n"
            "12. rem_sleep_ratio (快速眼动比例 %)\n"
            "13. sleep_continuity (深睡连续性)\n"
            "14. breathing_score (呼吸质量)\n"
            "15. official_advice (华为运动健康截图中“解读与建议/建议/解读”区域的完整官方原文；必须逐字摘录，保留多段换行；如果截图中不可见或无法辨认，填 null)\n"
            "16. analysis_report (兼容字段，仅当截图中明确出现同一段官方建议时才填同样原文；否则填 null)\n\n"
            "注意：严禁提取或计算 sleep_cycles, awake_min, fall_asleep_min, wake_up_min，这些将由系统公式处理。\n"
            "必须逐行检查截图中'解读与建议'、'建议'、'解读'、'睡眠建议'、'华为运动健康建议'等区域；找到后必须逐字摘录完整区域，不能只摘录建议卡片一句话，不能概括、改写、扩写或把 AI 自己生成的建议冒充官方建议。\n"
            "必须确保 total_sleep_min 对应截图中的'夜间睡眠'数值。\n"
            "重要：必须核对数值，确保 total_sleep_min = deep_sleep_min + light_sleep_min + rem_sleep_min。"
        )

    def _prepare_image(self):
        # 按照老板要求：图片不要再压缩了，保证数据必须完整提取，不用担心 token
        return self.image_path, None

    def _extract_sleep_data(self):
        candidates = [("主", "vision")]
        for number in (1, 2):
            prefix = f"vision_backup_{number}"
            if number == 1 and not all(self.ai_cfg.get(f"{prefix}_{key}") for key in ("base_url", "api_key", "model")):
                prefix = "backup"
            if all(self.ai_cfg.get(f"{prefix}_{key}") for key in ("base_url", "api_key", "model")):
                candidates.append((f"备用 {number}", prefix))
        total_attempts = len(candidates)
        # 在循环外创建 http_client，避免每次重试都重建连接（修复连接资源泄漏）
        with httpx.Client(
            verify=False,
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        ) as http_client:
            for attempt, (model_type, prefix) in enumerate(candidates, start=1):
                try:
                    v_url = clean_url(self.ai_cfg.get(f"{prefix}_base_url", ""))
                    v_key = self.ai_cfg.get(f"{prefix}_api_key", "")
                    v_model = self.ai_cfg.get(f"{prefix}_model", "glm-4v-flash")

                    if not v_key:
                        raise ValueError("视觉模型 API Key 为空")

                    self.progress(f"{model_type}模型解析中 ({attempt}/{total_attempts})...")

                    client_v = OpenAI(api_key=v_key, base_url=v_url, http_client=http_client)

                    hint_year = str(datetime.now().year)
                    try:
                        basename = os.path.basename(self.image_path)
                        match = re.search(r"(20[2-3]\d)", basename)
                        if match:
                            hint_year = match.group(1)
                            logger.debug(f"文件名识别到年份建议: {hint_year}")
                    except Exception:
                        pass

                    final_img_path, temp_img_path = self._prepare_image()
                    try:
                        with open(final_img_path, "rb") as file:
                            img_b64 = base64.b64encode(file.read()).decode()
                    finally:
                        if temp_img_path and os.path.exists(temp_img_path):
                            os.remove(temp_img_path)

                    prompt = self._load_prompt()
                    if hint_year:
                        prompt += f"\n\n注意：当前上下文年份为 {hint_year}。请将此年份与截图中识别到的月、日组合成完整的 sleep_date。"

                    vision_resp = client_v.chat.completions.create(
                        model=v_model,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                                    {"type": "text", "text": prompt},
                                ],
                            }
                        ],
                        temperature=0.1,
                    )
                    content = vision_resp.choices[0].message.content
                    if not content:
                        raise ValueError("模型返回内容为空")

                    sleep_data = self.extract_json(content.strip())
                    if not sleep_data:
                        raise ValueError(f"模型输出不符合 JSON 格式，请检查模型稳定性。输出内容: {content[:50]}...")

                    sleep_data = self.normalize_data(sleep_data)
                    extracted_date = sleep_data.get("sleep_date")
                    if extracted_date and self.date_str:
                        try:
                            target_dt = datetime.strptime(self.date_str, "%Y-%m-%d")
                            ext_dt = datetime.strptime(extracted_date, "%Y-%m-%d")
                            if abs((target_dt - ext_dt).days) > 1:
                                raise ValueError(f"日期不匹配！截图日期是 {extracted_date}，而当前处理日期是 {self.date_str}。请确认是否选错了图。")
                        except Exception as exc:
                            if "日期不匹配" in str(exc):
                                raise

                    is_valid, reason = self.validate_data(sleep_data)
                    if is_valid:
                        if self.is_no_main_sleep(sleep_data):
                            sleep_data = self.normalize_no_main_sleep(sleep_data)
                            self.progress("识别到无有效主睡眠，跳过后续指标提取。")
                        sleep_data["extracted_by"] = v_model
                        return sleep_data

                    self.progress(f"{v_model} 识别异常: {reason}")
                    if attempt < total_attempts:
                        self.progress(f"提取不完整，正在进行第 {attempt} 次重试...")
                        time.sleep(2)
                    else:
                        self.progress("已达到最大重试次数，将使用现有提取结果。")
                        sleep_data["extracted_by"] = v_model
                        return sleep_data
                except Exception as exc:
                    if "日期不匹配" in str(exc):
                        raise
                    if attempt >= total_attempts:
                        raise
                    err_msg = str(exc)
                    if "Connection error" in err_msg:
                        err_msg = "网络连接失败，请检查 API 地址或网络环境"
                    self.progress(f"分析出错，正在重试({attempt})... {err_msg}")
                    time.sleep(3)
        raise RuntimeError("未获取到睡眠数据，分析中止。")

    def analyze(self):
        try:
            logger.info(
                "[sleep-report] analyzer start date=%s image_path=%s injected_sleep_data=%s include_time_analysis=%s force_refresh=%s",
                self.date_str,
                self.image_path,
                self.sleep_data is not None,
                self.include_time_analysis,
                self.force_refresh,
            )
            # 逻辑恢复：如果已有完整数据（从 DB 恢复或外部传入），直接跳过识别
            is_valid_sleep_data = False
            validation_reason = ""
            if self.sleep_data:
                is_valid_sleep_data, validation_reason = self.validate_data(self.sleep_data)
                logger.info("[sleep-report] analyzer precheck date=%s valid=%s reason=%s", self.date_str, is_valid_sleep_data, validation_reason)

            if not self.force_refresh and self.sleep_data and is_valid_sleep_data:
                source = self.sleep_data.get("source")
                if source and source != "screenshot_ocr":
                    self.progress("检测到结构化睡眠数据，跳过 OCR 识别阶段...")
                    logger.info("[sleep-report] analyzer reuse structured date=%s source=%s", self.date_str, source)
                else:
                    self.progress("检测到数据库中已有完整睡眠包，跳过 OCR 识别阶段...")
                    logger.info("[sleep-report] analyzer reuse existing_ocr date=%s", self.date_str)
            elif not self.image_path or not os.path.exists(self.image_path):
                if self.sleep_data and validation_reason:
                    logger.warning("[sleep-report] analyzer missing image and invalid structured date=%s reason=%s", self.date_str, validation_reason)
                    raise FileNotFoundError(f"结构化睡眠数据不完整，且未找到截图文件: {validation_reason}")
                logger.warning("[sleep-report] analyzer missing image date=%s", self.date_str)
                raise FileNotFoundError("未找到截图文件，且数据库中无今日数据。")
            else:
                if self.sleep_data and validation_reason:
                    self.progress(f"结构化睡眠数据校验失败，回退 OCR 识别: {validation_reason}")
                logger.info(f"开始分析截图: {self.image_path}")
                logger.info("[sleep-report] analyzer ocr start date=%s image_path=%s", self.date_str, self.image_path)
                self.sleep_data = self._extract_sleep_data()
                logger.info("[sleep-report] analyzer ocr done date=%s keys=%s", self.date_str, sorted((self.sleep_data or {}).keys()))

            if not self.sleep_data:
                raise RuntimeError("未获取到睡眠数据，分析中止。")

            target_date = self.sleep_data.get("sleep_date") or self.sleep_data.get("date")
            if not target_date or len(str(target_date)) < 8:
                raise ValueError("未识别到有效的睡眠日期，分析中止。")
            else:
                current_year = str(datetime.now().year)
                if not str(target_date).startswith(current_year):
                    target_date = current_year + str(target_date)[4:]
                    self.sleep_data["sleep_date"] = target_date

            self.sleep_data["date"] = target_date
            if self.is_no_main_sleep(self.sleep_data):
                self.sleep_data = self.normalize_no_main_sleep(self.sleep_data)
                self.progress("无有效主睡眠：已按 0 分事实保存，跳过时间计算与普通报告。")
                logger.warning("[sleep-report] no main sleep short-circuit date=%s", target_date)
                return SleepAnalysisResult(
                    date=target_date,
                    sleep_data=self.sleep_data,
                    analysis_report=NO_MAIN_SLEEP_WARNING,
                    report_path="",
                    status="done",
                    error="",
                )
            if self.pre_report_callback and not self.force_refresh:
                cached = self.pre_report_callback(target_date, self.sleep_data)
                if cached:
                    self.progress("检测到服务端已有同日分析结果，复用报告并跳过重复生成...")
                    logger.info("[sleep-report] analyzer reuse report date=%s", target_date)
                    return SleepAnalysisResult(
                        date=cached.get("date") or target_date,
                        sleep_data=cached.get("sleep_data") or self.sleep_data,
                        analysis_report=cached.get("analysis_report") or "",
                        report_path=cached.get("report_path") or "",
                        status="done",
                        error="",
                    )
            self.progress(f"日期: {target_date}，正在拉取数据...")
            logger.info("[sleep-report] analyzer report generation start date=%s include_time_analysis=%s", target_date, self.include_time_analysis)

            # 路径修正：现在 analyzer.py 和 skills 都在 server/ 子目录下
            root_dir = os.path.dirname(__file__)
            skill_dir = os.path.join(root_dir, "skills", "time-management")
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)
            from generate_full_report import generate_comprehensive_report

            report_path = generate_comprehensive_report(
                target_date,
                injected_sleep_data=self.sleep_data,
                force_pull=True,
                include_time_analysis=self.include_time_analysis,
                db=self.db,
                provider_config=self.report_provider_config,
                user_id=self.user_id,
            )
            logger.info("[sleep-report] analyzer report generation done date=%s report_path=%s", target_date, report_path)

            if report_path is None and self.sleep_data.get("full_report_state") == "insufficient_time_records":
                self.progress("时间记录过少，已保留睡眠报告。")
                return SleepAnalysisResult(date=target_date, sleep_data=self.sleep_data, status="done", error="")

            if report_path and os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as file:
                    report = file.read()
            else:
                report = "生成报告失败，请检查同步配置。"

            self.progress("分析完成，正在同步结果...")
            logger.info("[sleep-report] analyzer done date=%s report_path=%s", target_date, report_path)
            return SleepAnalysisResult(
                date=target_date,
                sleep_data=self.sleep_data,
                analysis_report=report,
                report_path=report_path or "",
                status="done",
                error="",
            )
        except Exception as exc:
            logger.error(f"SleepAnalyzer Error: {exc}", exc_info=True)
            logger.error("[sleep-report] analyzer error date=%s error=%s", self.date_str, exc, exc_info=True)
            return SleepAnalysisResult(
                date="",
                sleep_data=self.sleep_data,
                analysis_report="",
                report_path="",
                status="error",
                error=str(exc),
            )
