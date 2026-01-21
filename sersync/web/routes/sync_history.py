"""
Sync History API 路由 - 同步历史记录
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

router = APIRouter()


# ========== 数据模型 ==========

class SyncHistoryEntry(BaseModel):
    """同步历史条目"""
    id: int
    timestamp: str
    event_type: str
    file_path: str
    remote_ip: str
    remote_module: str
    success: bool
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None


class SyncHistoryResponse(BaseModel):
    """同步历史响应"""
    total: int
    entries: List[SyncHistoryEntry]
    page: int
    page_size: int


class SyncStatsResponse(BaseModel):
    """同步统计响应"""
    total_syncs: int
    successful_syncs: int
    failed_syncs: int
    success_rate: float
    avg_duration_ms: Optional[float] = None
    most_synced_files: List[dict]
    sync_by_hour: List[dict]


# ========== API 端点 ==========

@router.get("/recent", response_model=List[SyncHistoryEntry])
async def get_recent_sync_history(
    limit: int = Query(50, ge=1, le=500, description="返回的记录数量"),
    success: Optional[bool] = Query(None, description="过滤成功/失败状态"),
    event_type: Optional[str] = Query(None, description="过滤事件类型"),
    remote_ip: Optional[str] = Query(None, description="过滤远程IP")
):
    """
    获取最近的同步历史记录

    Args:
        limit: 返回的记录数量
        success: 过滤成功/失败状态
        event_type: 过滤事件类型
        remote_ip: 过滤远程IP

    Returns:
        同步历史记录列表
    """
    try:
        from sersync.web.database import get_db_manager, SyncLog
        db = get_db_manager()
        
        session = db.get_session()
        try:
            query = session.query(SyncLog)
            
            # 应用过滤条件
            if success is not None:
                query = query.filter(SyncLog.success == success)
            
            if event_type:
                query = query.filter(SyncLog.event_type == event_type)
                
            if remote_ip:
                query = query.filter(SyncLog.remote_ip == remote_ip)
            
            # 按时间倒序排列并限制数量
            logs = query.order_by(SyncLog.timestamp.desc()).limit(limit).all()
            
            return [
                SyncHistoryEntry(
                    id=log.id,
                    timestamp=log.timestamp.isoformat(),
                    event_type=log.event_type,
                    file_path=log.file_path,
                    remote_ip=log.remote_ip,
                    remote_module=log.remote_module,
                    success=log.success,
                    error_message=log.error_message,
                    duration_ms=log.duration_ms
                )
                for log in logs
            ]
        finally:
            session.close()
            
    except Exception as e:
        logger.error("Failed to fetch sync history", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch sync history")


@router.get("/paginated", response_model=SyncHistoryResponse)
async def get_paginated_sync_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页记录数"),
    success: Optional[bool] = Query(None, description="过滤成功/失败状态"),
    event_type: Optional[str] = Query(None, description="过滤事件类型"),
    file_path: Optional[str] = Query(None, description="文件路径关键词搜索")
):
    """
    获取分页的同步历史记录

    Args:
        page: 页码
        page_size: 每页记录数
        success: 过滤成功/失败状态
        event_type: 过滤事件类型
        file_path: 文件路径关键词搜索

    Returns:
        分页的同步历史记录
    """
    try:
        from sersync.web.database import get_db_manager, SyncLog
        from sersync.web.cache import cached_sync_query
        
        # 使用缓存装饰器
        @cached_sync_query(ttl=15)  # 15秒缓存
        def get_paginated_data(page, page_size, success, event_type, file_path):
            db = get_db_manager()
            session = db.get_session()
            try:
                query = session.query(SyncLog)
                
                # 应用过滤条件
                if success is not None:
                    query = query.filter(SyncLog.success == success)
                
                if event_type:
                    query = query.filter(SyncLog.event_type == event_type)
                    
                if file_path:
                    query = query.filter(SyncLog.file_path.like(f'%{file_path}%'))
                
                # 获取总数（使用子查询优化）
                total = query.count()
                
                # 分页查询
                offset = (page - 1) * page_size
                logs = query.order_by(SyncLog.timestamp.desc()).offset(offset).limit(page_size).all()
                
                return {
                    'total': total,
                    'logs': logs
                }
            finally:
                session.close()
        
        # 获取数据
        data = get_paginated_data(page, page_size, success, event_type, file_path)
        
        entries = [
            SyncHistoryEntry(
                id=log.id,
                timestamp=log.timestamp.isoformat(),
                event_type=log.event_type,
                file_path=log.file_path,
                remote_ip=log.remote_ip,
                remote_module=log.remote_module,
                success=log.success,
                error_message=log.error_message,
                duration_ms=log.duration_ms
            )
            for log in data['logs']
        ]
        
        return SyncHistoryResponse(
            total=data['total'],
            entries=entries,
            page=page,
            page_size=page_size
        )
            
    except Exception as e:
        logger.error("Failed to fetch paginated sync history", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch sync history")


@router.get("/stats", response_model=SyncStatsResponse)
async def get_sync_stats(
    hours: int = Query(24, ge=1, le=168, description="统计时间范围（小时）")
):
    """
    获取同步统计信息

    Args:
        hours: 统计时间范围（小时）

    Returns:
        同步统计信息
    """
    try:
        from sersync.web.database import get_db_manager, SyncLog
        from sqlalchemy import func
        db = get_db_manager()
        
        session = db.get_session()
        try:
            # 计算时间范围
            since = datetime.now() - timedelta(hours=hours)
            
            # 基本统计
            total_query = session.query(SyncLog).filter(SyncLog.timestamp >= since)
            total_syncs = total_query.count()
            
            successful_syncs = total_query.filter(SyncLog.success == True).count()
            failed_syncs = total_syncs - successful_syncs
            success_rate = (successful_syncs / total_syncs * 100) if total_syncs > 0 else 0
            
            # 平均持续时间
            avg_duration = session.query(func.avg(SyncLog.duration_ms)).filter(
                SyncLog.timestamp >= since,
                SyncLog.duration_ms.isnot(None)
            ).scalar()
            
            # 最常同步的文件（Top 10）
            most_synced_files = session.query(
                SyncLog.file_path,
                func.count(SyncLog.id).label('sync_count')
            ).filter(
                SyncLog.timestamp >= since
            ).group_by(SyncLog.file_path).order_by(
                func.count(SyncLog.id).desc()
            ).limit(10).all()
            
            # 按小时统计同步数量
            sync_by_hour = session.query(
                func.strftime('%Y-%m-%d %H:00:00', SyncLog.timestamp).label('hour'),
                func.count(SyncLog.id).label('sync_count'),
                func.sum(func.case([(SyncLog.success == True, 1)], else_=0)).label('success_count')
            ).filter(
                SyncLog.timestamp >= since
            ).group_by(
                func.strftime('%Y-%m-%d %H:00:00', SyncLog.timestamp)
            ).order_by('hour').all()
            
            return SyncStatsResponse(
                total_syncs=total_syncs,
                successful_syncs=successful_syncs,
                failed_syncs=failed_syncs,
                success_rate=round(success_rate, 2),
                avg_duration_ms=round(avg_duration, 2) if avg_duration else None,
                most_synced_files=[
                    {
                        "file_path": file_path,
                        "sync_count": sync_count
                    }
                    for file_path, sync_count in most_synced_files
                ],
                sync_by_hour=[
                    {
                        "hour": hour,
                        "total": sync_count,
                        "success": success_count,
                        "failed": sync_count - success_count
                    }
                    for hour, sync_count, success_count in sync_by_hour
                ]
            )
        finally:
            session.close()
            
    except Exception as e:
        logger.error("Failed to get sync stats", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get sync stats")


@router.get("/file/{file_id}")
async def get_file_sync_history(
    file_id: str,
    limit: int = Query(50, ge=1, le=200, description="返回的记录数量")
):
    """
    获取特定文件的同步历史

    Args:
        file_id: 文件路径（URL编码）
        limit: 返回的记录数量

    Returns:
        该文件的同步历史记录
    """
    try:
        from urllib.parse import unquote
        from sersync.web.database import get_db_manager, SyncLog
        
        # URL解码文件路径
        file_path = unquote(file_id)
        
        db = get_db_manager()
        session = db.get_session()
        try:
            logs = session.query(SyncLog).filter(
                SyncLog.file_path == file_path
            ).order_by(SyncLog.timestamp.desc()).limit(limit).all()
            
            return {
                "file_path": file_path,
                "total_syncs": len(logs),
                "history": [
                    {
                        "id": log.id,
                        "timestamp": log.timestamp.isoformat(),
                        "event_type": log.event_type,
                        "remote_ip": log.remote_ip,
                        "remote_module": log.remote_module,
                        "success": log.success,
                        "error_message": log.error_message,
                        "duration_ms": log.duration_ms
                    }
                    for log in logs
                ]
            }
        finally:
            session.close()
            
    except Exception as e:
        logger.error("Failed to get file sync history", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get file sync history")


@router.delete("/cleanup")
async def cleanup_old_sync_logs(
    days: int = Query(7, ge=1, le=365, description="保留天数")
):
    """
    清理旧的同步日志

    Args:
        days: 保留天数

    Returns:
        清理结果
    """
    try:
        from sersync.web.database import get_db_manager
        from sersync.web.cache import clear_sync_history_cache
        
        db = get_db_manager()
        result = db.cleanup_old_logs(days=days)
        
        # 清理缓存
        clear_sync_history_cache()
        
        if result:
            return {
                "success": True,
                "message": f"Successfully cleaned up logs older than {days} days",
                "sync_logs_deleted": result['sync_logs_deleted'],
                "app_logs_deleted": result['app_logs_deleted']
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to cleanup logs")
            
    except Exception as e:
        logger.error("Failed to cleanup sync logs", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to cleanup logs")


@router.post("/cache/clear")
async def clear_cache():
    """
    清空同步历史缓存
    
    Returns:
        清理结果
    """
    try:
        from sersync.web.cache import clear_sync_history_cache, cleanup_expired_cache
        
        # 清空所有缓存
        clear_sync_history_cache()
        
        # 清理过期缓存
        expired_count = cleanup_expired_cache()
        
        return {
            "success": True,
            "message": "Cache cleared successfully",
            "expired_entries_cleaned": expired_count
        }
        
    except Exception as e:
        logger.error("Failed to clear cache", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@router.get("/cache/stats")
async def get_cache_stats():
    """
    获取缓存统计信息
    
    Returns:
        缓存统计
    """
    try:
        from sersync.web.cache import get_sync_history_cache
        
        cache = get_sync_history_cache()
        stats = cache.get_stats()
        
        return {
            "cache_stats": stats,
            "cache_enabled": True
        }
        
    except Exception as e:
        logger.error("Failed to get cache stats", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get cache stats")