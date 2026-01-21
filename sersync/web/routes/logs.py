"""
Logs API 路由 - 日志查看
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()

router = APIRouter()


# ========== 数据模型 ==========

class LogEntry(BaseModel):
    """日志条目"""
    timestamp: str
    level: str
    message: str
    context: Optional[dict] = None


# ========== API 端点 ==========

@router.get("/recent", response_model=List[LogEntry])
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=1000),
    level: Optional[str] = Query(None, regex="^(DEBUG|INFO|WARNING|ERROR)$")
):
    """
    获取最近的日志

    Args:
        limit: 返回的日志条目数量
        level: 日志级别过滤

    Returns:
        日志条目列表
    """
    try:
        from sersync.web.database import get_db_manager
        db = get_db_manager()

        # 从数据库读取日志
        logs = db.get_recent_application_logs(limit=limit, level=level)

        return [
            LogEntry(
                timestamp=log.timestamp.isoformat(),
                level=log.level,
                message=log.message,
                context={"module": log.module} if log.module else None
            )
            for log in logs
        ]
    except Exception as e:
        logger.error("Failed to fetch logs", error=str(e))
        return []


@router.get("/search")
async def search_logs(
    query: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    搜索日志

    Args:
        query: 搜索关键词
        limit: 返回的日志条目数量

    Returns:
        匹配的日志条目
    """
    try:
        from sersync.web.database import get_db_manager
        db = get_db_manager()

        # 搜索日志
        logs = db.search_logs(keyword=query, limit=limit)

        results = [
            {
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
                "message": log.message,
                "module": log.module
            }
            for log in logs
        ]

        return {
            "query": query,
            "results": results,
            "total": len(results)
        }
    except Exception as e:
        logger.error("Failed to search logs", error=str(e))
        return {
            "query": query,
            "results": [],
            "total": 0
        }


@router.get("/stats")
async def get_log_stats():
    """
    获取日志统计

    Returns:
        日志统计信息
    """
    try:
        from sersync.web.database import get_db_manager
        db = get_db_manager()

        session = db.get_session()
        try:
            from sersync.web.database import ApplicationLog

            # 统计各级别日志数量
            total = session.query(ApplicationLog).count()
            debug_count = session.query(ApplicationLog).filter(ApplicationLog.level == 'DEBUG').count()
            info_count = session.query(ApplicationLog).filter(ApplicationLog.level == 'INFO').count()
            warning_count = session.query(ApplicationLog).filter(ApplicationLog.level == 'WARNING').count()
            error_count = session.query(ApplicationLog).filter(ApplicationLog.level == 'ERROR').count()

            # 获取最近的错误
            recent_errors = session.query(ApplicationLog).filter(
                ApplicationLog.level == 'ERROR'
            ).order_by(ApplicationLog.timestamp.desc()).limit(10).all()

            return {
                "total_logs": total,
                "by_level": {
                    "DEBUG": debug_count,
                    "INFO": info_count,
                    "WARNING": warning_count,
                    "ERROR": error_count
                },
                "recent_errors": [
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "message": log.message
                    }
                    for log in recent_errors
                ]
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("Failed to get log stats", error=str(e))
        return {
            "total_logs": 0,
            "by_level": {
                "DEBUG": 0,
                "INFO": 0,
                "WARNING": 0,
                "ERROR": 0
            },
            "recent_errors": []
        }
