# -*- coding: utf-8 -*-
"""服务端集中日志配置与横切日志工具。"""

from __future__ import annotations

import asyncio
import json
import functools
import inspect
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from logging import FileHandler, StreamHandler
from pathlib import Path
from typing import Callable, Iterable


LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_LEVEL = "INFO"
ALLOWED_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
DEFAULT_LOGGER_NAMES = [
    "server",
    "server.request",
    "server.sync_hub",
    "server.ticktick_client",
    "server.store",
    "server.analyzer",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
]
LOGGER_ALIASES = {
    "server.sync_hub": ("sync_hub",),
    "server.ticktick_client": ("ticktick_client",),
    "server.store": ("store",),
    "server.analyzer": ("analyzer",),
}


def _logger_targets(name: str) -> tuple[str, ...]:
    """返回公开 canonical logger 及直接脚本启动时的受控别名。"""
    return (name, *LOGGER_ALIASES.get(name, ()))


@dataclass
class LoggingRuntimeConfig:
    global_level: str = DEFAULT_LEVEL
    module_levels: dict[str, str] = field(default_factory=dict)

    def normalized(self) -> "LoggingRuntimeConfig":
        return LoggingRuntimeConfig(
            global_level=normalize_level_name(self.global_level),
            module_levels={name: normalize_level_name(level) for name, level in self.module_levels.items() if name},
        )

    def public(self) -> dict:
        normalized = self.normalized()
        return {
            "global_level": normalized.global_level,
            "module_levels": normalized.module_levels,
            "available_levels": sorted(ALLOWED_LEVELS, key=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].index),
            "logger_names": DEFAULT_LOGGER_NAMES,
        }


class LoggingConfigStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> LoggingRuntimeConfig:
        if not self.path.exists():
            return LoggingRuntimeConfig(
                global_level=os.getenv("MYTIMELOGGER_LOG_LEVEL", DEFAULT_LEVEL),
                module_levels={name: logging.getLevelName(level) for name, level in parse_module_levels(os.getenv("MYTIMELOGGER_LOG_LEVELS")).items()},
            ).normalized()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("日志配置文件格式无效")
        return LoggingRuntimeConfig(
            global_level=str(raw.get("global_level") or DEFAULT_LEVEL),
            module_levels={str(k): str(v) for k, v in (raw.get("module_levels") or {}).items()},
        ).normalized()

    def save(self, values: dict) -> LoggingRuntimeConfig:
        if not isinstance(values, dict):
            raise ValueError("日志配置必须是 JSON 对象")
        current = self.load()
        merged = asdict(current)
        if "global_level" in values:
            merged["global_level"] = values["global_level"]
        if "module_levels" in values:
            if not isinstance(values["module_levels"], dict):
                raise ValueError("module_levels 必须是对象")
            merged["module_levels"] = values["module_levels"]
        config = LoggingRuntimeConfig(
            global_level=str(merged["global_level"]),
            module_levels={str(k): str(v) for k, v in merged["module_levels"].items() if str(k).strip()},
        ).normalized()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
        return config


def parse_log_level(value: str | None, default: int = logging.INFO) -> int:
    if value is None or not str(value).strip():
        return default
    raw = str(value).strip().upper()
    if raw.isdigit():
        return int(raw)
    return logging._nameToLevel.get(raw, default)


def normalize_level_name(value: str | None) -> str:
    raw = str(value or DEFAULT_LEVEL).strip().upper()
    if raw not in ALLOWED_LEVELS:
        raise ValueError(f"不支持的日志级别: {value}")
    return raw


def parse_module_levels(value: str | None) -> dict[str, int]:
    levels: dict[str, int] = {}
    if not value:
        return levels
    for part in value.split(","):
        if not part.strip() or "=" not in part:
            continue
        name, level = part.split("=", 1)
        module = name.strip()
        if module:
            levels[module] = parse_log_level(level, logging.INFO)
    return levels


def format_module_levels(module_levels: dict[str, str] | None) -> str:
    return ",".join(f"{name}={normalize_level_name(level)}" for name, level in (module_levels or {}).items() if name)


def configure_logging(
    *,
    log_dir: str,
    global_level: str | None = None,
    module_levels: str | None = None,
    logger_names: Iterable[str] | None = None,
) -> str:
    """配置 stdout + 日期日志文件，并应用全局/模块日志级别。"""
    root_logger = logging.getLogger()
    level = parse_log_level(global_level or os.getenv("MYTIMELOGGER_LOG_LEVEL", DEFAULT_LEVEL))
    root_logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)

    has_stdout = any(
        isinstance(handler, StreamHandler)
        and not isinstance(handler, FileHandler)
        and getattr(handler, "stream", None) is sys.stdout
        for handler in root_logger.handlers
    )
    if not has_stdout:
        console_handler = StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            if (
                isinstance(handler, StreamHandler)
                and not isinstance(handler, FileHandler)
                and getattr(handler, "stream", None) is sys.stdout
            ):
                handler.setFormatter(formatter)

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.abspath(os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log"))
    has_file = any(
        isinstance(handler, FileHandler)
        and os.path.abspath(getattr(handler, "baseFilename", "")) == log_file
        for handler in root_logger.handlers
    )
    if not has_file:
        file_handler = FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    else:
        for handler in root_logger.handlers:
            if isinstance(handler, FileHandler) and os.path.abspath(getattr(handler, "baseFilename", "")) == log_file:
                handler.setFormatter(formatter)

    overrides = parse_module_levels(module_levels or os.getenv("MYTIMELOGGER_LOG_LEVELS"))
    for name in logger_names or DEFAULT_LOGGER_NAMES:
        for target in _logger_targets(name):
            logging.getLogger(target).setLevel(level)
    for name, override_level in overrides.items():
        for target in _logger_targets(name):
            logging.getLogger(target).setLevel(override_level)
    return log_file


@contextmanager
def log_context(logger: logging.Logger, operation: str, level: int = logging.DEBUG, **fields):
    started = time.perf_counter()
    logger.log(level, "%s start extra=%s", operation, fields)
    try:
        yield
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception("%s error elapsed_ms=%s extra=%s", operation, elapsed_ms, fields)
        raise
    else:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.log(level, "%s ok elapsed_ms=%s extra=%s", operation, elapsed_ms, fields)


def traced(operation: str | None = None, level: int = logging.DEBUG):
    """装饰同步/异步函数，集中记录入口、成功、耗时、异常。"""
    def decorator(func: Callable):
        op = operation or f"{func.__module__}.{func.__qualname__}"
        logger = logging.getLogger(func.__module__)

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with log_context(logger, op, level=level):
                    return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with log_context(logger, op, level=level):
                return func(*args, **kwargs)

        return wrapper

    return decorator


async def request_logging_middleware(request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    logger = logging.getLogger("server.request")
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request error method=%s path=%s status=%s elapsed_ms=%s request_id=%s",
            request.method,
            request.url.path,
            500,
            elapsed_ms,
            request_id,
        )
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request ok method=%s path=%s status=%s elapsed_ms=%s request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        request_id,
    )
    return response
