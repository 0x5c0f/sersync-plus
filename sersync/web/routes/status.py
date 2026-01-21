"""
Status API 路由 - 系统状态和指标
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime
import structlog

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = structlog.get_logger()

router = APIRouter()


# ========== 数据模型 ==========

class SystemMetrics(BaseModel):
    """系统指标"""
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_usage_percent: float
    disk_free_gb: float
    network_sent_mb: Optional[float] = None
    network_recv_mb: Optional[float] = None


class SyncStatus(BaseModel):
    """同步状态"""
    status: str  # running, paused, stopped, error
    watch_path: str
    remotes: int
    events_processed: int
    files_synced: int
    files_filtered: int
    sync_success: int
    sync_failed: int
    uptime_seconds: int


class DashboardStatus(BaseModel):
    """仪表盘状态"""
    system: SystemMetrics
    sync: SyncStatus
    notification_enabled: bool
    websocket_connections: int


# ========== API 端点 ==========

@router.get("/current", response_model=DashboardStatus)
async def get_current_status():
    """
    获取当前系统和同步状态

    Returns:
        完整的仪表盘状态
    """
    # 获取系统指标
    if PSUTIL_AVAILABLE:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()

        system_metrics = SystemMetrics(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=mem.percent,
            memory_used_mb=mem.used / 1024 / 1024,
            memory_total_mb=mem.total / 1024 / 1024,
            disk_usage_percent=disk.percent,
            disk_free_gb=disk.free / 1024 / 1024 / 1024,
            network_sent_mb=net.bytes_sent / 1024 / 1024,
            network_recv_mb=net.bytes_recv / 1024 / 1024,
        )
    else:
        # psutil 不可用时的降级处理
        system_metrics = SystemMetrics(
            cpu_percent=0.0,
            memory_percent=0.0,
            memory_used_mb=0.0,
            memory_total_mb=0.0,
            disk_usage_percent=0.0,
            disk_free_gb=0.0,
        )

    # 获取同步状态（从核心引擎）
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if engine:
        stats = engine.get_stats()
        sync_status = SyncStatus(
            status="running" if engine.is_running() else "stopped",
            watch_path=engine.config.watch_path,
            remotes=len(engine.config.remotes),
            events_processed=stats.get('events_processed', 0),
            files_synced=stats.get('files_synced', 0),
            files_filtered=stats.get('files_filtered', 0),
            sync_success=stats.get('sync_success', 0),
            sync_failed=stats.get('sync_failed', 0),
            uptime_seconds=stats.get('uptime_seconds', 0),
        )
        notification_enabled = engine.notification_engine is not None
    else:
        # 引擎未运行时的默认状态
        sync_status = SyncStatus(
            status="stopped",
            watch_path="N/A",
            remotes=0,
            events_processed=0,
            files_synced=0,
            files_filtered=0,
            sync_success=0,
            sync_failed=0,
            uptime_seconds=0,
        )
        notification_enabled = False

    # 获取 WebSocket 连接数
    from sersync.web import manager
    websocket_connections = manager.get_connection_count()

    return DashboardStatus(
        system=system_metrics,
        sync=sync_status,
        notification_enabled=notification_enabled,
        websocket_connections=websocket_connections
    )


@router.get("/metrics")
async def get_metrics():
    """
    获取详细的性能指标

    Returns:
        详细指标字典
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    if not engine:
        return {
            "error": "Engine not running",
            "stats": {}
        }

    stats = engine.get_stats()

    return {
        "timestamp": datetime.now().isoformat(),
        "engine_stats": stats,
        "queue_stats": stats.get('queue_stats', {}),
        "sync_stats": stats.get('sync_stats', {}),
        "filter_stats": stats.get('filter_stats', {}),
    }


@router.get("/health")
async def health_check():
    """
    健康检查

    Returns:
        健康状态
    """
    from sersync.core.engine import get_engine_instance
    engine = get_engine_instance()

    is_healthy = engine is not None and engine.is_running()

    return {
        "healthy": is_healthy,
        "status": "running" if is_healthy else "stopped",
        "timestamp": datetime.now().isoformat()
    }
