"""
Control API 路由 - 系统控制
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import structlog
from sersync.web.auth import get_current_user

logger = structlog.get_logger()

router = APIRouter()


# ========== 数据模型 ==========

class ControlResponse(BaseModel):
    """控制操作响应"""
    success: bool
    message: str
    action: str


# ========== API 端点（需要认证）==========

@router.post("/start", response_model=ControlResponse)
async def start_engine(current_user: str = Depends(get_current_user)):
    """
    启动同步引擎

    Returns:
        操作结果
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    if engine.is_running():
        return ControlResponse(
            success=False,
            message="Engine is already running",
            action="start"
        )

    # TODO: 在后台任务中启动引擎
    logger.info("Engine start requested", user=current_user)

    return ControlResponse(
        success=True,
        message="Engine start command issued",
        action="start"
    )


@router.post("/stop", response_model=ControlResponse)
async def stop_engine(current_user: str = Depends(get_current_user)):
    """
    停止同步引擎

    Returns:
        操作结果
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    if not engine.is_running():
        return ControlResponse(
            success=False,
            message="Engine is not running",
            action="stop"
        )

    # TODO: 在后台任务中停止引擎
    logger.info("Engine stop requested", user=current_user)

    return ControlResponse(
        success=True,
        message="Engine stop command issued",
        action="stop"
    )


@router.post("/full-sync", response_model=ControlResponse)
async def trigger_full_sync(current_user: str = Depends(get_current_user)):
    """
    触发全量同步

    Returns:
        操作结果
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    if not engine.is_running():
        raise HTTPException(status_code=400, detail="Engine is not running")

    # TODO: 在后台任务中执行全量同步
    logger.info("Full sync requested", user=current_user)

    return ControlResponse(
        success=True,
        message="Full sync command issued",
        action="full_sync"
    )


@router.post("/clear-fail-log", response_model=ControlResponse)
async def clear_fail_log(current_user: str = Depends(get_current_user)):
    """
    清空失败日志

    Returns:
        操作结果
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        raise HTTPException(status_code=503, detail="Engine not available")

    from pathlib import Path
    fail_log_path = Path(engine.config.fail_log.path)

    if fail_log_path.exists():
        fail_log_path.write_text('#!/bin/bash\n')
        logger.info("Fail log cleared", user=current_user)

        return ControlResponse(
            success=True,
            message="Fail log cleared successfully",
            action="clear_fail_log"
        )
    else:
        return ControlResponse(
            success=False,
            message="Fail log does not exist",
            action="clear_fail_log"
        )
