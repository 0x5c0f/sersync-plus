"""
日志系统配置
"""

import sys
import logging
import structlog
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_format: str = "text",
    log_file: Optional[str] = None
):
    """
    配置结构化日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_format: 日志格式 (text, json)
        log_file: 日志文件路径（可选）
    """
    log_level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
    }

    # 处理器列表
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # 格式化器
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        )

    # 配置
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            log_level_map.get(level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 文件日志
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level_map.get(level, logging.INFO))
        logging.root.addHandler(file_handler)

    logger = structlog.get_logger()
    logger.info("Logging configured", level=level, format=log_format, file=log_file)

    return logger


# 全局 logger 实例
logger = structlog.get_logger()
