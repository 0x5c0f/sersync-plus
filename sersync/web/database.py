"""
数据库模型 - SQLite

功能:
- 日志存储
- 同步历史
- 性能指标
"""

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, Text, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from pathlib import Path
import structlog

logger = structlog.get_logger()

Base = declarative_base()


# ========== 数据模型 ==========

class SyncLog(Base):
    """同步日志"""
    __tablename__ = 'sync_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    event_type = Column(String(50), index=True)  # CLOSE_WRITE, DELETE, etc.
    file_path = Column(String(500), index=True)
    remote_ip = Column(String(50))
    remote_module = Column(String(100))
    success = Column(Boolean, default=True, index=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)


class SystemMetric(Base):
    """系统性能指标"""
    __tablename__ = 'system_metrics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    cpu_percent = Column(Float)
    memory_percent = Column(Float)
    disk_usage_percent = Column(Float)
    events_processed = Column(Integer)
    files_synced = Column(Integer)
    queue_size = Column(Integer)


class ApplicationLog(Base):
    """应用日志"""
    __tablename__ = 'application_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)
    level = Column(String(20), index=True)  # DEBUG, INFO, WARNING, ERROR
    message = Column(Text)
    context = Column(Text, nullable=True)  # JSON 格式的上下文
    module = Column(String(100), nullable=True)


# ========== 数据库管理器 ==========

class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: str = "/var/sersync/sersync.db"):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库引擎
        self.engine = create_engine(
            f'sqlite:///{self.db_path}',
            echo=False,
            connect_args={"check_same_thread": False}
        )

        # 创建表
        Base.metadata.create_all(self.engine)

        # 创建额外的索引以优化查询性能
        with self.engine.connect() as conn:
            try:
                # 为分页查询优化的复合索引
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_sync_logs_timestamp_success 
                    ON sync_logs(timestamp DESC, success)
                """))
                
                # 为文件路径搜索优化的索引
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_sync_logs_file_path_timestamp 
                    ON sync_logs(file_path, timestamp DESC)
                """))
                
                # 为远程服务器过滤优化的索引
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_sync_logs_remote_timestamp 
                    ON sync_logs(remote_ip, remote_module, timestamp DESC)
                """))
                
                conn.commit()
                logger.debug("Database indexes created successfully")
            except Exception as e:
                logger.warning("Failed to create database indexes", error=str(e))

        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        logger.info("Database initialized", path=str(self.db_path))

    def get_session(self):
        """获取数据库会话"""
        return self.SessionLocal()

    def add_sync_log(
        self,
        event_type: str,
        file_path: str,
        remote_ip: str,
        remote_module: str,
        success: bool,
        error_message: str = None,
        duration_ms: int = None
    ):
        """
        添加同步日志

        Args:
            event_type: 事件类型
            file_path: 文件路径
            remote_ip: 远程 IP
            remote_module: 远程模块名
            success: 是否成功
            error_message: 错误消息（可选）
            duration_ms: 持续时间（毫秒）
        """
        session = self.get_session()
        try:
            log = SyncLog(
                event_type=event_type,
                file_path=file_path,
                remote_ip=remote_ip,
                remote_module=remote_module,
                success=success,
                error_message=error_message,
                duration_ms=duration_ms
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to add sync log", error=str(e))
        finally:
            session.close()

    def add_system_metric(
        self,
        cpu_percent: float,
        memory_percent: float,
        disk_usage_percent: float,
        events_processed: int,
        files_synced: int,
        queue_size: int
    ):
        """
        添加系统指标

        Args:
            cpu_percent: CPU 使用率
            memory_percent: 内存使用率
            disk_usage_percent: 磁盘使用率
            events_processed: 已处理事件数
            files_synced: 已同步文件数
            queue_size: 队列大小
        """
        session = self.get_session()
        try:
            metric = SystemMetric(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_usage_percent=disk_usage_percent,
                events_processed=events_processed,
                files_synced=files_synced,
                queue_size=queue_size
            )
            session.add(metric)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to add system metric", error=str(e))
        finally:
            session.close()

    def add_application_log(
        self,
        level: str,
        message: str,
        context: str = None,
        module: str = None
    ):
        """
        添加应用日志

        Args:
            level: 日志级别
            message: 日志消息
            context: 上下文（JSON 字符串）
            module: 模块名
        """
        session = self.get_session()
        try:
            log = ApplicationLog(
                level=level,
                message=message,
                context=context,
                module=module
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to add application log", error=str(e))
        finally:
            session.close()

    def get_recent_sync_logs(self, limit: int = 100, success: bool = None):
        """
        获取最近的同步日志

        Args:
            limit: 返回数量
            success: 过滤成功/失败（None 表示全部）

        Returns:
            日志列表
        """
        session = self.get_session()
        try:
            query = session.query(SyncLog)

            if success is not None:
                query = query.filter(SyncLog.success == success)

            logs = query.order_by(SyncLog.timestamp.desc()).limit(limit).all()
            return logs
        finally:
            session.close()

    def get_recent_application_logs(self, limit: int = 100, level: str = None):
        """
        获取最近的应用日志

        Args:
            limit: 返回数量
            level: 过滤日志级别

        Returns:
            日志列表
        """
        session = self.get_session()
        try:
            query = session.query(ApplicationLog)

            if level:
                query = query.filter(ApplicationLog.level == level)

            logs = query.order_by(ApplicationLog.timestamp.desc()).limit(limit).all()
            return logs
        finally:
            session.close()

    def search_logs(self, keyword: str, limit: int = 100):
        """
        搜索日志

        Args:
            keyword: 搜索关键词
            limit: 返回数量

        Returns:
            匹配的日志
        """
        session = self.get_session()
        try:
            logs = session.query(ApplicationLog).filter(
                ApplicationLog.message.like(f'%{keyword}%')
            ).order_by(ApplicationLog.timestamp.desc()).limit(limit).all()
            return logs
        finally:
            session.close()

    def get_sync_stats(self, hours: int = 24):
        """
        获取同步统计

        Args:
            hours: 统计时间范围（小时）

        Returns:
            统计数据
        """
        from datetime import timedelta

        session = self.get_session()
        try:
            since = datetime.now() - timedelta(hours=hours)

            total = session.query(SyncLog).filter(
                SyncLog.timestamp >= since
            ).count()

            success = session.query(SyncLog).filter(
                SyncLog.timestamp >= since,
                SyncLog.success == True
            ).count()

            failed = total - success

            return {
                'total': total,
                'success': success,
                'failed': failed,
                'success_rate': (success / total * 100) if total > 0 else 0
            }
        finally:
            session.close()

    def cleanup_old_logs(self, days: int = 7):
        """
        清理旧日志

        Args:
            days: 保留天数
        """
        from datetime import timedelta

        session = self.get_session()
        try:
            cutoff = datetime.now() - timedelta(days=days)

            # 删除旧的同步日志
            deleted_sync = session.query(SyncLog).filter(
                SyncLog.timestamp < cutoff
            ).delete()

            # 删除旧的应用日志
            deleted_app = session.query(ApplicationLog).filter(
                ApplicationLog.timestamp < cutoff
            ).delete()

            session.commit()

            logger.info(
                "Old logs cleaned up",
                sync_logs=deleted_sync,
                app_logs=deleted_app
            )

            return {
                'sync_logs_deleted': deleted_sync,
                'app_logs_deleted': deleted_app
            }
        except Exception as e:
            session.rollback()
            logger.error("Failed to cleanup logs", error=str(e))
            return None
        finally:
            session.close()


# 全局数据库实例
_db_manager = None


def get_db_manager(db_path: str = None) -> DatabaseManager:
    """获取全局数据库管理器实例"""
    global _db_manager
    if _db_manager is None:
        # 如果没有指定路径，从配置管理器获取
        if db_path is None:
            from sersync.web.config_manager import get_db_path
            db_path = get_db_path()
        _db_manager = DatabaseManager(db_path)
    return _db_manager


def set_db_path(db_path: str):
    """设置数据库路径（在初始化前调用）"""
    global _db_manager
    if _db_manager is not None:
        logger.warning("Database manager already initialized, path change ignored")
        return
    # 重置全局实例，下次调用 get_db_manager 时会使用新路径
    _db_manager = None
