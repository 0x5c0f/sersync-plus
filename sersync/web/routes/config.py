"""
Config API 路由 - 配置管理
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict
import structlog
from pathlib import Path

logger = structlog.get_logger()

router = APIRouter()


# ========== 数据模型 ==========

class ConfigSummary(BaseModel):
    """配置摘要"""
    version: str
    watch_path: str
    remotes: List[Dict]
    inotify_events: Dict
    filter_enabled: bool
    filter_patterns: List[str]
    rsync_params: str
    notification_enabled: bool
    web_enabled: bool
    bidirectional_enabled: bool


# ========== API 端点 ==========

@router.get("/summary", response_model=ConfigSummary)
async def get_config_summary():
    """
    获取配置摘要

    Returns:
        配置摘要信息
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not running")

    config = engine.config

    return ConfigSummary(
        version=config.version,
        watch_path=config.watch_path,
        remotes=[
            {"ip": r.ip, "name": r.name}
            for r in config.remotes
        ],
        inotify_events={
            "delete": config.inotify.delete,
            "create_folder": config.inotify.create_folder,
            "create_file": config.inotify.create_file,
            "close_write": config.inotify.close_write,
            "move_from": config.inotify.move_from,
            "move_to": config.inotify.move_to,
            "attrib": config.inotify.attrib,
            "modify": config.inotify.modify,
        },
        filter_enabled=config.filter.enabled,
        filter_patterns=config.filter.patterns,
        rsync_params=config.rsync.common_params,
        notification_enabled=config.notification.enabled,
        web_enabled=config.web.enabled,
        bidirectional_enabled=config.bidirectional.enabled,
    )


@router.get("/file")
async def get_config_file():
    """
    获取原始配置文件内容

    Returns:
        配置文件内容（文本）
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not running")

    # 注意：需要记录配置文件路径
    # TODO: 在引擎中记录配置文件路径
    return {
        "message": "Configuration file content",
        "note": "Feature not yet implemented"
    }


@router.get("/validate")
async def validate_config():
    """
    验证当前配置

    Returns:
        验证结果
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not running")

    config = engine.config
    errors = []
    warnings = []

    # 验证监控路径
    watch_path = Path(config.watch_path)
    if not watch_path.exists():
        errors.append(f"Watch path does not exist: {config.watch_path}")
    elif not watch_path.is_dir():
        errors.append(f"Watch path is not a directory: {config.watch_path}")

    # 验证远程目标
    if len(config.remotes) == 0:
        warnings.append("No remote targets configured")

    # 验证 inotify 配置
    if not config.inotify.close_write and not config.inotify.modify:
        warnings.append("Neither closeWrite nor modify events are enabled")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "timestamp": str(Path(config.watch_path).stat().st_mtime) if watch_path.exists() else None
    }
