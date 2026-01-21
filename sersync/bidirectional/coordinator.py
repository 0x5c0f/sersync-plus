"""
双向同步协调器

功能:
- 协调本地和远程事件
- 合并事件流
- 冲突检测和解决
- 触发 Unison 同步
"""

import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import structlog

from sersync.bidirectional.conflict_detector import (
    ConflictDetector,
    ConflictType,
    FileMetadata,
    ConflictInfo
)
from sersync.bidirectional.conflict_resolver import (
    ConflictResolver,
    ResolutionStrategy,
    ResolutionResult
)
from sersync.bidirectional.unison_engine import (
    UnisonEngine,
    UnisonProfile,
    UnisonSyncResult
)

logger = structlog.get_logger()


class SyncEvent:
    """同步事件"""

    def __init__(
        self,
        event_type: str,
        file_path: str,
        source: str,  # "local" 或 "remote"
        timestamp: Optional[datetime] = None,
        metadata: Optional[FileMetadata] = None
    ):
        """
        初始化同步事件

        Args:
            event_type: 事件类型 (CREATE, MODIFY, DELETE, MOVE)
            file_path: 文件路径
            source: 事件来源
            timestamp: 事件时间戳
            metadata: 文件元数据
        """
        self.event_type = event_type
        self.file_path = file_path
        self.source = source
        self.timestamp = timestamp or datetime.now()
        self.metadata = metadata

    def __repr__(self):
        return f"SyncEvent({self.source}:{self.event_type}:{self.file_path})"


class BidirectionalCoordinator:
    """双向同步协调器"""

    def __init__(
        self,
        local_root: str,
        remote_root: str,
        remote_host: str,
        remote_user: Optional[str] = None,
        ssh_port: int = 22,
        conflict_strategy: ResolutionStrategy = ResolutionStrategy.KEEP_NEWER,
        sync_interval: int = 60,
        enable_unison: bool = True,
        ignore_patterns: Optional[List[str]] = None
    ):
        """
        初始化双向同步协调器

        Args:
            local_root: 本地根目录
            remote_root: 远程根目录
            remote_host: 远程主机
            remote_user: 远程用户
            ssh_port: SSH 端口
            conflict_strategy: 冲突解决策略
            sync_interval: 同步间隔（秒）
            enable_unison: 是否启用 Unison 同步
            ignore_patterns: 忽略模式列表
        """
        self.local_root = Path(local_root)
        self.remote_root = remote_root
        self.remote_host = remote_host
        self.remote_user = remote_user
        self.ssh_port = ssh_port
        self.conflict_strategy = conflict_strategy
        self.sync_interval = sync_interval
        self.enable_unison = enable_unison

        # 事件队列
        self.local_events: asyncio.Queue = asyncio.Queue()
        self.remote_events: asyncio.Queue = asyncio.Queue()

        # 冲突检测和解决
        self.conflict_detector = ConflictDetector(
            time_tolerance_seconds=2,
            enable_content_hash=True
        )

        self.conflict_resolver = ConflictResolver(
            default_strategy=conflict_strategy,
            backup_dir="/var/sersync/bidirectional/conflicts",
            enable_backup=True
        )

        # Unison 引擎
        self.unison_engine = None
        if enable_unison:
            profile = UnisonProfile(
                name="sersync_bidirectional",
                local_root=str(local_root),
                remote_root=remote_root,
                remote_host=remote_host,
                remote_user=remote_user,
                ssh_port=ssh_port,
                ignore_patterns=ignore_patterns or [],
                prefer=self._strategy_to_prefer(conflict_strategy),
                batch=True,
                times=True,
                fastcheck=True,
                copyonconflict=True
            )

            self.unison_engine = UnisonEngine(
                profile=profile,
                timeout_seconds=3600,
                retry_count=3
            )

        # 状态跟踪
        self._running = False
        self._tasks = []
        self.stats = {
            'local_events': 0,
            'remote_events': 0,
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'syncs_completed': 0,
            'syncs_failed': 0,
        }

        # 事件缓冲（用于合并短时间内的多个事件）
        self.event_buffer: Dict[str, SyncEvent] = {}
        self.buffer_timeout = 5  # 秒

        logger.info(
            "Bidirectional coordinator initialized",
            local_root=str(local_root),
            remote_host=remote_host,
            strategy=conflict_strategy.value,
            sync_interval=sync_interval
        )

    def _strategy_to_prefer(self, strategy: ResolutionStrategy) -> str:
        """将解决策略转换为 Unison prefer 选项"""
        strategy_map = {
            ResolutionStrategy.KEEP_NEWER: "newer",
            ResolutionStrategy.KEEP_OLDER: "older",
            ResolutionStrategy.KEEP_LOCAL: "local",
            ResolutionStrategy.KEEP_REMOTE: "remote",
        }
        return strategy_map.get(strategy, "newer")

    async def start(self):
        """启动协调器"""
        if self._running:
            logger.warning("Coordinator already running")
            return

        self._running = True
        logger.info("Starting bidirectional coordinator")

        # 初始全量同步
        if self.enable_unison:
            await self._perform_initial_sync()

        # 启动事件处理器
        local_processor = asyncio.create_task(self._process_local_events())
        remote_processor = asyncio.create_task(self._process_remote_events())
        self._tasks.extend([local_processor, remote_processor])

        # 启动定期同步
        periodic_sync = asyncio.create_task(self._periodic_sync_worker())
        self._tasks.append(periodic_sync)

        # 启动事件缓冲刷新
        buffer_flush = asyncio.create_task(self._buffer_flush_worker())
        self._tasks.append(buffer_flush)

        logger.info("Bidirectional coordinator started")

    async def stop(self):
        """停止协调器"""
        if not self._running:
            return

        logger.info("Stopping bidirectional coordinator")
        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

        logger.info(
            "Bidirectional coordinator stopped",
            stats=self.stats
        )

    async def on_local_event(self, event_type: str, file_path: str):
        """
        处理本地文件事件

        Args:
            event_type: 事件类型
            file_path: 文件路径
        """
        # 转换为相对路径
        try:
            rel_path = Path(file_path).relative_to(self.local_root)
        except ValueError:
            # 不在监控目录内
            return

        # 获取文件元数据
        metadata = FileMetadata.from_local_file(file_path)

        event = SyncEvent(
            event_type=event_type,
            file_path=str(rel_path),
            source="local",
            metadata=metadata
        )

        await self.local_events.put(event)
        self.stats['local_events'] += 1

        logger.debug(
            "Local event received",
            event_type=event_type,
            path=str(rel_path)
        )

    async def on_remote_event(self, event_type: str, file_path: str):
        """
        处理远程文件事件

        Args:
            event_type: 事件类型
            file_path: 文件路径（相对路径）
        """
        event = SyncEvent(
            event_type=event_type,
            file_path=file_path,
            source="remote",
            metadata=None  # 远程元数据需要通过 SSH 获取
        )

        await self.remote_events.put(event)
        self.stats['remote_events'] += 1

        logger.debug(
            "Remote event received",
            event_type=event_type,
            path=file_path
        )

    async def _perform_initial_sync(self):
        """执行初始全量同步"""
        if not self.unison_engine or not self.unison_engine.is_available():
            logger.warning("Unison not available, skipping initial sync")
            return

        logger.info("Performing initial bidirectional sync")

        try:
            result = await self.unison_engine.sync()

            if result.success:
                logger.info(
                    "Initial sync completed",
                    files_updated=result.files_updated,
                    files_deleted=result.files_deleted
                )
                self.stats['syncs_completed'] += 1
            else:
                logger.error(
                    "Initial sync failed",
                    stderr=result.stderr
                )
                self.stats['syncs_failed'] += 1

        except Exception as e:
            logger.error("Initial sync error", error=str(e), exc_info=True)
            self.stats['syncs_failed'] += 1

    async def _process_local_events(self):
        """处理本地事件队列"""
        logger.debug("Local event processor started")

        while self._running:
            try:
                event = await asyncio.wait_for(
                    self.local_events.get(),
                    timeout=1.0
                )

                # 添加到缓冲区（合并短时间内的多个事件）
                self.event_buffer[event.file_path] = event

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Local event processing error", error=str(e))

        logger.debug("Local event processor stopped")

    async def _process_remote_events(self):
        """处理远程事件队列"""
        logger.debug("Remote event processor started")

        while self._running:
            try:
                event = await asyncio.wait_for(
                    self.remote_events.get(),
                    timeout=1.0
                )

                # 添加到缓冲区
                self.event_buffer[event.file_path] = event

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Remote event processing error", error=str(e))

        logger.debug("Remote event processor stopped")

    async def _buffer_flush_worker(self):
        """事件缓冲刷新工作线程"""
        logger.debug("Buffer flush worker started")

        while self._running:
            try:
                await asyncio.sleep(self.buffer_timeout)

                if not self.event_buffer:
                    continue

                # 获取缓冲的事件
                buffered_events = list(self.event_buffer.values())
                self.event_buffer.clear()

                # 处理事件
                await self._handle_buffered_events(buffered_events)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Buffer flush error", error=str(e), exc_info=True)

        logger.debug("Buffer flush worker stopped")

    async def _handle_buffered_events(self, events: List[SyncEvent]):
        """
        处理缓冲的事件

        Args:
            events: 事件列表
        """
        if not events:
            return

        logger.info(
            "Processing buffered events",
            count=len(events)
        )

        # 检测冲突
        conflicts = await self._detect_conflicts_for_events(events)

        if conflicts:
            logger.info(
                "Conflicts detected",
                count=len(conflicts)
            )
            self.stats['conflicts_detected'] += len(conflicts)

            # 解决冲突
            await self._resolve_conflicts(conflicts)

        # 触发同步
        if self.enable_unison:
            await self._trigger_sync()

    async def _detect_conflicts_for_events(
        self,
        events: List[SyncEvent]
    ) -> Dict[str, ConflictInfo]:
        """
        为事件检测冲突

        Args:
            events: 事件列表

        Returns:
            冲突字典 {路径: ConflictInfo}
        """
        conflicts = {}

        # 按文件路径分组事件
        events_by_path: Dict[str, List[SyncEvent]] = {}
        for event in events:
            if event.file_path not in events_by_path:
                events_by_path[event.file_path] = []
            events_by_path[event.file_path].append(event)

        # 检测每个文件的冲突
        for file_path, file_events in events_by_path.items():
            # 查找本地和远程事件
            local_event = next(
                (e for e in file_events if e.source == "local"),
                None
            )
            remote_event = next(
                (e for e in file_events if e.source == "remote"),
                None
            )

            # 如果同时有本地和远程事件，可能有冲突
            if local_event and remote_event:
                # 获取文件元数据
                local_meta = local_event.metadata or FileMetadata(
                    path=str(self.local_root / file_path),
                    exists=False
                )

                # 远程元数据（简化处理，实际应通过 SSH 获取）
                remote_meta = FileMetadata(
                    path=file_path,
                    exists=remote_event.event_type != "DELETE"
                )

                # 检测冲突
                conflict = self.conflict_detector.detect_conflict(
                    local_meta,
                    remote_meta
                )

                if conflict:
                    conflicts[file_path] = conflict

        return conflicts

    async def _resolve_conflicts(self, conflicts: Dict[str, ConflictInfo]):
        """
        解决冲突

        Args:
            conflicts: 冲突字典
        """
        results = self.conflict_resolver.batch_resolve(conflicts)

        successful = sum(1 for r in results.values() if r.success)
        self.stats['conflicts_resolved'] += successful

        logger.info(
            "Conflicts resolved",
            total=len(conflicts),
            successful=successful,
            failed=len(conflicts) - successful
        )

        # 记录备份文件
        for path, result in results.items():
            if result.backup_paths:
                logger.info(
                    "Conflict files backed up",
                    path=path,
                    backups=result.backup_paths
                )

    async def _periodic_sync_worker(self):
        """定期同步工作线程"""
        logger.debug("Periodic sync worker started")

        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)

                if not self._running:
                    break

                await self._trigger_sync()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Periodic sync error", error=str(e), exc_info=True)

        logger.debug("Periodic sync worker stopped")

    async def _trigger_sync(self):
        """触发同步"""
        if not self.enable_unison:
            return

        if not self.unison_engine or not self.unison_engine.is_available():
            logger.warning("Unison not available")
            return

        logger.info("Triggering bidirectional sync")

        try:
            result = await self.unison_engine.sync()

            if result.success:
                logger.info(
                    "Bidirectional sync completed",
                    files_updated=result.files_updated,
                    files_deleted=result.files_deleted,
                    duration=f"{result.duration_seconds:.2f}s"
                )
                self.stats['syncs_completed'] += 1

                # 如果有冲突，记录
                if result.conflicts > 0:
                    logger.warning(
                        "Unison reported conflicts",
                        conflicts=result.conflicts
                    )
                    self.stats['conflicts_detected'] += result.conflicts

            else:
                logger.error(
                    "Bidirectional sync failed",
                    exit_code=result.exit_code,
                    stderr=result.stderr[:500] if result.stderr else ""
                )
                self.stats['syncs_failed'] += 1

        except Exception as e:
            logger.error("Sync trigger error", error=str(e), exc_info=True)
            self.stats['syncs_failed'] += 1

    async def manual_sync(
        self,
        path_filter: Optional[str] = None,
        force_direction: Optional[str] = None
    ) -> Optional[UnisonSyncResult]:
        """
        手动触发同步

        Args:
            path_filter: 路径过滤器
            force_direction: 强制同步方向

        Returns:
            UnisonSyncResult 或 None
        """
        if not self.enable_unison or not self.unison_engine:
            logger.warning("Unison not enabled")
            return None

        logger.info(
            "Manual sync triggered",
            path_filter=path_filter,
            force_direction=force_direction
        )

        try:
            result = await self.unison_engine.sync(
                path_filter=path_filter,
                force_direction=force_direction
            )

            if result.success:
                self.stats['syncs_completed'] += 1
            else:
                self.stats['syncs_failed'] += 1

            return result

        except Exception as e:
            logger.error("Manual sync error", error=str(e), exc_info=True)
            self.stats['syncs_failed'] += 1
            return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'running': self._running,
            'event_buffer_size': len(self.event_buffer),
            'local_queue_size': self.local_events.qsize(),
            'remote_queue_size': self.remote_events.qsize()
        }

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running
