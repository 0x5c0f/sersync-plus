"""
Sersync 主引擎

功能:
- 协调所有核心模块
- 事件分发与处理
- 定期全量同步
- 失败重试
- 通知系统集成
- Web 实时推送
"""

import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from sersync.config.models import SersyncConfig
from sersync.core.monitor import FileMonitor
from sersync.core.event_queue import EventQueue
from sersync.core.filter import FileFilter
from sersync.core.sync_engine import SyncEngine

logger = structlog.get_logger()


class SersyncEngine:
    """Sersync 主引擎"""

    def __init__(self, config: SersyncConfig, threads: int = 10):
        """
        初始化引擎

        Args:
            config: Sersync 配置
            threads: 工作线程数
        """
        self.config = config
        self.threads = threads
        self._running = False
        self._tasks = []
        self._loop = None  # 保存事件循环引用

        # 初始化各个模块
        self.monitor = FileMonitor(
            watch_path=config.watch_path,
            config=config.inotify,
            event_callback=self._on_file_event,
            recursive=True
        )

        self.event_queue = EventQueue(window_size=5, max_queue_size=10000)

        self.file_filter = FileFilter(
            config=config.filter,
            enable_auto_temp_filter=True
        )

        self.sync_engine = SyncEngine(
            config=config.rsync,
            remotes=config.remotes,
            watch_path=config.watch_path,
            fail_log=config.fail_log
        )

        # 初始化双向同步引擎
        self.bidirectional_engines = {}
        self._setup_bidirectional_sync(config)

        # 初始化数据库（如果启用）
        if config.database.enabled:
            try:
                from sersync.web.config_manager import set_web_config
                set_web_config(config)
                logger.info("Database configured", path=config.database.path)
            except Exception as e:
                logger.error("Failed to configure database", error=str(e))

        # 初始化通知系统
        self.notifier = None
        self.notification_engine = None
        if config.notification.enabled:
            self._setup_notification(config)

        # 初始化 FailLog 执行器
        self.faillog_executor = None
        if config.fail_log.path:  # 如果配置了 failLog 路径
            try:
                from sersync.core.faillog_executor import FailLogExecutor
                self.faillog_executor = FailLogExecutor(config.fail_log)
                logger.info("FailLog executor initialized", path=config.fail_log.path)
            except Exception as e:
                logger.error("Failed to initialize FailLog executor", error=str(e))

        # 统计信息
        self.stats = {
            'start_time': None,
            'events_processed': 0,
            'files_synced': 0,
            'files_filtered': 0,
            'sync_success': 0,
            'sync_failed': 0,
        }

        # Web 推送功能（延迟初始化）
        self.web_broadcast_callback = None

        logger.info(
            "Sersync engine initialized",
            watch_path=config.watch_path,
            remotes=len(config.remotes),
            threads=threads,
            debug=config.debug,
            notification_enabled=config.notification.enabled
        )

    def set_web_broadcast_callback(self, callback):
        """
        设置 Web 推送回调函数

        Args:
            callback: 异步回调函数，接收 (message_type, data) 参数
        """
        self.web_broadcast_callback = callback
        logger.info("Web broadcast callback registered")

    async def _broadcast_to_web(self, message_type: str, data: dict):
        """
        向 Web 客户端广播消息

        Args:
            message_type: 消息类型 (status/event/metrics)
            data: 消息数据
        """
        if self.web_broadcast_callback:
            try:
                await self.web_broadcast_callback({
                    'type': message_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error("Web broadcast failed", error=str(e))

    def _setup_notification(self, config: SersyncConfig):
        """设置通知系统"""
        try:
            from sersync.notification import (
                NotificationService,
                NotificationRuleEngine,
                ImmediateRule,
                BatchRule,
                ScheduleRule,
            )

            # 初始化通知服务
            self.notifier = NotificationService(
                config_path=config.notification.apprise_config,
                templates=config.notification.templates,
                enabled=True
            )

            if not self.notifier.is_enabled():
                logger.warning("Notification service not available (Apprise not installed)")
                return

            # 创建规则引擎
            self.notification_engine = NotificationRuleEngine(self.notifier)

            # 注册规则
            for rule_config in config.notification.rules:
                if rule_config['notify'] == 'immediate':
                    rule = ImmediateRule(
                        event=rule_config['event'],
                        tags=rule_config['tags']
                    )
                elif rule_config['notify'] == 'batch':
                    rule = BatchRule(
                        event=rule_config['event'],
                        tags=rule_config['tags'],
                        batch_size=rule_config['batch_size'],
                        batch_interval=rule_config['batch_interval']
                    )
                elif rule_config['notify'] == 'schedule':
                    rule = ScheduleRule(
                        event=rule_config['event'],
                        tags=rule_config['tags'],
                        cron=rule_config['cron']
                    )
                else:
                    continue

                self.notification_engine.register_rule(rule)

            logger.info(
                "Notification system initialized",
                rules=len(config.notification.rules),
                templates=len(config.notification.templates)
            )

        except ImportError:
            logger.warning(
                "Notification module not available",
                hint="Install with: poetry install -E notifications"
            )
            self.notifier = None
            self.notification_engine = None

    def _setup_bidirectional_sync(self, config: SersyncConfig):
        """设置双向同步引擎"""
        try:
            from sersync.bidirectional.sync_engine import BidirectionalSyncEngine
            
            # 为每个配置为双向同步的remote创建引擎
            for remote in config.remotes:
                if remote.mode == 'bidirectional':
                    # 构建元信息配置
                    metadata_config = None
                    if remote.metadata_dir or remote.conflict_backup_dir or remote.lock_file:
                        metadata_config = {
                            'metadata_dir': remote.metadata_dir,
                            'conflict_backup_dir': remote.conflict_backup_dir,
                            'lock_file': remote.lock_file
                        }
                    
                    # 创建双向同步引擎
                    bidir_engine = BidirectionalSyncEngine(
                        watch_path=config.watch_path,
                        remote_config=remote,
                        rsync_config=config.rsync,
                        metadata_config=metadata_config
                    )
                    
                    self.bidirectional_engines[f"{remote.ip}::{remote.name}"] = bidir_engine
                    
                    logger.info(
                        "Bidirectional sync engine created",
                        remote=f"{remote.ip}::{remote.name}",
                        node_id=bidir_engine.metadata_manager.node_id,
                        conflict_strategy=remote.conflict_strategy
                    )
            
            if self.bidirectional_engines:
                logger.info(
                    "Bidirectional sync initialized",
                    engines_count=len(self.bidirectional_engines)
                )
                
        except ImportError:
            logger.warning(
                "Bidirectional sync module not available",
                hint="Check if bidirectional sync dependencies are installed"
            )
        except Exception as e:
            logger.error("Failed to initialize bidirectional sync", error=str(e))

    def _setup_notification(self, config: SersyncConfig):
        """设置通知系统"""
        try:
            from sersync.notification import (
                NotificationService,
                NotificationRuleEngine,
                ImmediateRule,
                BatchRule,
                ScheduleRule,
            )

            # 初始化通知服务
            self.notifier = NotificationService(
                config_path=config.notification.apprise_config,
                templates=config.notification.templates,
                enabled=True
            )

            if not self.notifier.is_enabled():
                logger.warning("Notification service not available (Apprise not installed)")
                return

            # 创建规则引擎
            self.notification_engine = NotificationRuleEngine(self.notifier)

            # 注册规则
            for rule_config in config.notification.rules:
                if rule_config['notify'] == 'immediate':
                    rule = ImmediateRule(
                        event=rule_config['event'],
                        tags=rule_config['tags']
                    )
                elif rule_config['notify'] == 'batch':
                    rule = BatchRule(
                        event=rule_config['event'],
                        tags=rule_config['tags'],
                        batch_size=rule_config['batch_size'],
                        batch_interval=rule_config['batch_interval']
                    )
                elif rule_config['notify'] == 'schedule':
                    rule = ScheduleRule(
                        event=rule_config['event'],
                        tags=rule_config['tags'],
                        cron=rule_config['cron']
                    )
                else:
                    continue

                self.notification_engine.register_rule(rule)

            logger.info(
                "Notification system initialized",
                rules=len(config.notification.rules),
                templates=len(config.notification.templates)
            )

        except ImportError:
            logger.warning(
                "Notification module not available",
                hint="Install with: poetry install -E notifications"
            )
            self.notifier = None
            self.notification_engine = None

    async def start(self):
        """启动引擎"""
        if self._running:
            logger.warning("Engine already running")
            return

        self._running = True
        import time
        self.stats['start_time'] = time.time()

        # 保存事件循环引用（用于线程安全调用）
        self._loop = asyncio.get_running_loop()

        logger.info("Starting Sersync engine")

        try:
            # 启动各个组件
            await self.event_queue.start_auto_flush()

            # 启动通知引擎
            if self.notification_engine:
                await self.notification_engine.start()

            # 启动文件监控
            monitor_task = asyncio.create_task(self.monitor.start())
            self._tasks.append(monitor_task)

            # 启动事件处理器
            for i in range(self.threads):
                worker_task = asyncio.create_task(self._event_worker(i))
                self._tasks.append(worker_task)

            # 启动定期全量同步（如果启用）
            if self.config.crontab.enabled:
                crontab_task = asyncio.create_task(self._crontab_worker())
                self._tasks.append(crontab_task)

            # 启动双向同步任务
            if self.bidirectional_engines:
                for remote_key, bidir_engine in self.bidirectional_engines.items():
                    bidir_task = asyncio.create_task(self._bidirectional_worker(remote_key, bidir_engine))
                    self._tasks.append(bidir_task)

            # 启动 FailLog 执行器（如果启用）
            if self.faillog_executor:
                await self.faillog_executor.start()

            # 启动 Web 状态推送
            web_task = asyncio.create_task(self._web_status_worker())
            self._tasks.append(web_task)

            logger.info(
                "Sersync engine started",
                workers=self.threads,
                crontab_enabled=self.config.crontab.enabled,
                faillog_enabled=self.faillog_executor is not None,
                notification_enabled=self.notification_engine is not None,
                web_broadcast_enabled=self.web_broadcast_callback is not None
            )

            # 等待所有任务完成
            await asyncio.gather(*self._tasks, return_exceptions=True)

        except asyncio.CancelledError:
            logger.info("Engine cancelled")
        except Exception as e:
            logger.error("Engine error", error=str(e), exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """停止引擎"""
        if not self._running:
            return

        logger.info("Stopping Sersync engine")
        self._running = False

        # 停止文件监控
        await self.monitor.stop()

        # 停止事件队列
        await self.event_queue.stop()

        # 停止通知引擎
        if self.notification_engine:
            await self.notification_engine.stop()

        # 停止 FailLog 执行器
        if self.faillog_executor:
            await self.faillog_executor.stop()

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # 等待任务完成
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # 输出最终统计
        logger.info("Sersync engine stopped", stats=self.get_stats())

    def _on_file_event(self, event_type: str, file_path: str, **kwargs):
        """
        文件事件回调（同步方法）

        Args:
            event_type: 事件类型
            file_path: 文件路径
            **kwargs: 其他参数
        """
        # 过滤检查
        if self.file_filter.should_ignore(file_path):
            self.stats['files_filtered'] += 1
            return

        # 推送到事件队列（需要转换为异步）
        event = {
            'type': event_type,
            'path': file_path,
            **kwargs
        }

        # 线程安全：使用 call_soon_threadsafe 在主事件循环中调度任务
        if self._loop:
            self._loop.call_soon_threadsafe(
                asyncio.create_task,
                self.event_queue.push(event)
            )

            # 推送事件到 Web 客户端
            self._loop.call_soon_threadsafe(
                asyncio.create_task,
                self._broadcast_to_web('event', {
                    'type': event_type,
                    'path': file_path,
                    'timestamp': datetime.now().isoformat()
                })
            )

        if self.config.debug:
            logger.debug(
                "File event received",
                type=event_type,
                path=file_path
            )

    async def _event_worker(self, worker_id: int):
        """
        事件处理工作线程

        Args:
            worker_id: 工作线程 ID
        """
        logger.debug("Event worker started", worker_id=worker_id)

        while self._running:
            try:
                # 从队列获取事件
                event = await asyncio.wait_for(
                    self.event_queue.get(),
                    timeout=1.0
                )

                # 处理事件
                await self._process_event(event)
                self.stats['events_processed'] += 1

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Worker error",
                    worker_id=worker_id,
                    error=str(e),
                    exc_info=True
                )

        logger.debug("Event worker stopped", worker_id=worker_id)

    async def _process_event(self, event: dict):
        """
        处理单个事件

        Args:
            event: 事件字典
        """
        event_type = event['type']
        file_path = event['path']

        logger.info(
            "Processing event",
            type=event_type,
            path=file_path
        )

        # 记录开始时间（用于计算持续时间）
        import time
        start_time = time.time()

        # 执行同步
        result = await self.sync_engine.sync_file(file_path, event_type)

        # 计算持续时间
        duration_ms = int((time.time() - start_time) * 1000)

        # 记录同步日志到数据库
        try:
            if self.config.database.enabled:
                from sersync.web.database import get_db_manager
                db = get_db_manager()
                
                for remote_result in result['results']:
                    # 解析远程信息
                    remote_parts = remote_result['remote'].split('::')
                    remote_ip = remote_parts[0] if len(remote_parts) > 0 else 'unknown'
                    remote_module = remote_parts[1] if len(remote_parts) > 1 else 'unknown'
                    
                    # 记录到数据库
                    db.add_sync_log(
                        event_type=event_type,
                        file_path=file_path,
                        remote_ip=remote_ip,
                        remote_module=remote_module,
                        success=remote_result['success'],
                        error_message=remote_result.get('error', '') if not remote_result['success'] else None,
                        duration_ms=duration_ms
                    )
        except Exception as e:
            logger.error("Failed to record sync log to database", error=str(e))

        if result['all_success']:
            self.stats['files_synced'] += 1
            self.stats['sync_success'] += len(self.config.remotes)

            logger.info(
                "File synced successfully",
                path=file_path,
                remotes=len(self.config.remotes)
            )

            # 发送成功通知（批量）
            if self.notification_engine:
                for remote_result in result['results']:
                    await self.notification_engine.trigger_event(
                        'sync_success',
                        file_path=file_path,
                        remote_ip=remote_result['remote'].split('::')[0],
                        remote_module=remote_result['remote'].split('::')[1] if '::' in remote_result['remote'] else '',
                        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
        else:
            # 记录失败
            failed_remotes = [r for r in result['results'] if not r['success']]
            self.stats['sync_failed'] += len(failed_remotes)

            logger.warning(
                "File sync failed",
                path=file_path,
                failures=len(failed_remotes)
            )

            # 发送失败通知（立即）
            if self.notification_engine:
                for remote_result in failed_remotes:
                    await self.notification_engine.trigger_event(
                        'sync_failed',
                        file_path=file_path,
                        remote_ip=remote_result['remote'].split('::')[0],
                        remote_module=remote_result['remote'].split('::')[1] if '::' in remote_result['remote'] else '',
                        error_message=remote_result.get('error', 'Unknown error'),
                        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )

    async def _crontab_worker(self):
        """定期全量同步工作线程"""
        schedule_minutes = self.config.crontab.schedule
        schedule_seconds = schedule_minutes * 60

        logger.info(
            "Crontab worker started",
            interval_minutes=schedule_minutes
        )

        while self._running:
            try:
                await asyncio.sleep(schedule_seconds)

                if not self._running:
                    break

                logger.info("Starting scheduled full sync")

                # 提取 crontab 过滤规则
                filters = (
                    self.config.crontab.filter.patterns
                    if self.config.crontab.filter and self.config.crontab.filter.enabled
                    else None
                )

                # 执行全量同步
                result = await self.sync_engine.sync_full_directory(filters)

                if result['all_success']:
                    logger.info("Scheduled full sync completed successfully")
                else:
                    logger.warning(
                        "Scheduled full sync had failures",
                        failures=sum(1 for r in result['results'] if not r['success'])
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Crontab worker error", error=str(e), exc_info=True)

        logger.info("Crontab worker stopped")

    async def _web_status_worker(self):
        """Web 状态推送工作线程"""
        logger.info("Web status worker started")

        while self._running:
            try:
                await asyncio.sleep(2)  # 每 2 秒推送一次状态

                if not self._running:
                    break

                # 获取系统指标
                try:
                    import psutil
                    cpu_percent = psutil.cpu_percent(interval=0.1)
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage(self.config.watch_path)
                except ImportError:
                    cpu_percent = 0
                    memory = type('obj', (object,), {'percent': 0})()
                    disk = type('obj', (object,), {'percent': 0})()

                # 计算运行时间
                import time
                uptime_seconds = int(time.time() - self.stats['start_time']) if self.stats['start_time'] else 0
                hours = uptime_seconds // 3600
                minutes = (uptime_seconds % 3600) // 60
                seconds = uptime_seconds % 60
                uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                # 计算成功率
                total_syncs = self.stats['sync_success'] + self.stats['sync_failed']
                success_rate = (self.stats['sync_success'] / total_syncs * 100) if total_syncs > 0 else 100

                # 获取队列大小
                queue_stats = self.event_queue.get_stats()

                # 推送状态到 Web 客户端
                await self._broadcast_to_web('status', {
                    'running': self._running,
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'disk_usage_percent': disk.percent,
                    'uptime': uptime_str,
                    'total_events': self.stats['events_processed'],
                    'files_synced': self.stats['files_synced'],
                    'queue_size': queue_stats.get('pending_events', 0),
                    'success_rate': success_rate
                })

                # 每30秒记录一次系统指标到数据库
                if uptime_seconds % 30 == 0:
                    try:
                        if self.config.database.enabled:
                            from sersync.web.database import get_db_manager
                            db = get_db_manager()
                            db.add_system_metric(
                                cpu_percent=cpu_percent,
                                memory_percent=memory.percent,
                                disk_usage_percent=disk.percent,
                                events_processed=self.stats['events_processed'],
                                files_synced=self.stats['files_synced'],
                                queue_size=queue_stats.get('pending_events', 0)
                            )
                    except Exception as e:
                        logger.error("Failed to record system metrics", error=str(e))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Web status worker error", error=str(e), exc_info=True)

        logger.info("Web status worker stopped")

    async def _bidirectional_worker(self, remote_key: str, bidir_engine):
        """双向同步工作线程"""
        logger.info("Bidirectional sync worker started", remote=remote_key)
        
        # 获取同步间隔
        sync_interval = bidir_engine.remote_config.sync_interval
        
        while self._running:
            try:
                await asyncio.sleep(sync_interval)
                
                if not self._running:
                    break
                
                logger.debug("Starting bidirectional sync", remote=remote_key)
                
                # 执行双向同步
                result = await bidir_engine.sync_bidirectional()
                
                if result['success']:
                    logger.debug(
                        "Bidirectional sync completed",
                        remote=remote_key,
                        changes=result['changes_detected'],
                        conflicts=result['conflicts_resolved'],
                        files_synced=result['files_synced']
                    )
                    
                    # 推送同步结果到Web客户端
                    await self._broadcast_to_web('bidirectional_sync', {
                        'remote': remote_key,
                        'success': True,
                        'changes_detected': result['changes_detected'],
                        'conflicts_resolved': result['conflicts_resolved'],
                        'files_synced': result['files_synced']
                    })
                else:
                    logger.warning(
                        "Bidirectional sync failed",
                        remote=remote_key,
                        error=result.get('error', 'Unknown error')
                    )
                    
                    # 推送失败通知
                    await self._broadcast_to_web('bidirectional_sync', {
                        'remote': remote_key,
                        'success': False,
                        'error': result.get('error', 'Unknown error')
                    })
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Bidirectional sync worker error",
                    remote=remote_key,
                    error=str(e),
                    exc_info=True
                )
        
        logger.info("Bidirectional sync worker stopped", remote=remote_key)

    async def full_sync(self):
        """
        执行一次全量同步（-r 参数）

        Returns:
            同步结果
        """
        logger.info("Performing initial full sync")
        result = await self.sync_engine.sync_full_directory()

        if result['all_success']:
            logger.info("Initial full sync completed successfully")
        else:
            logger.warning("Initial full sync had failures")

        return result

    def get_stats(self) -> dict:
        """获取统计信息"""
        import time
        uptime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0

        return {
            **self.stats,
            'uptime_seconds': int(uptime),
            'monitor_running': self.monitor.is_running(),
            'queue_stats': self.event_queue.get_stats(),
            'sync_stats': self.sync_engine.get_stats(),
            'filter_stats': self.file_filter.get_stats(),
        }

    def is_running(self) -> bool:
        """检查引擎是否正在运行"""
        return self._running


# 全局引擎实例（用于 Web 界面访问）
_engine_instance: Optional[SersyncEngine] = None


def get_engine_instance() -> Optional[SersyncEngine]:
    """获取全局引擎实例"""
    return _engine_instance


def set_engine_instance(engine: SersyncEngine):
    """设置全局引擎实例"""
    global _engine_instance
    _engine_instance = engine
