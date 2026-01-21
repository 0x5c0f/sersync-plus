"""
事件队列模块

功能:
- 事件缓冲与时间窗口合并
- 事件优先级处理
- 批量刷新
"""

import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger()


class EventQueue:
    """
    事件队列（支持时间窗口合并）

    特性:
    - 5秒时间窗口内的同一文件事件合并
    - 事件优先级: DELETE > MOVE > MODIFY > CREATE
    - 目录删除时过滤内部文件事件
    """

    def __init__(self, window_size: int = 5, max_queue_size: int = 10000):
        """
        初始化事件队列

        Args:
            window_size: 时间窗口大小（秒）
            max_queue_size: 最大队列大小
        """
        self.window_size = window_size
        self.max_queue_size = max_queue_size

        self.pending_events: Dict[str, List[dict]] = defaultdict(list)
        self.output_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        self.last_flush = time.time()
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None

        self.stats = {
            'events_received': 0,
            'events_merged': 0,
            'events_output': 0,
            'events_filtered': 0,
        }

    async def push(self, event: dict):
        """
        推送事件到队列

        Args:
            event: 事件字典，必须包含 'type' 和 'path' 字段
        """
        if 'path' not in event or 'type' not in event:
            logger.error("Invalid event, missing required fields", event=event)
            return

        file_path = event['path']
        event['timestamp'] = time.time()

        self.pending_events[file_path].append(event)
        self.stats['events_received'] += 1

        logger.debug(
            "Event pushed to queue",
            type=event['type'],
            path=file_path,
            pending_count=len(self.pending_events[file_path])
        )

        # 检查是否需要立即刷新
        if time.time() - self.last_flush >= self.window_size:
            await self.flush()

    async def flush(self):
        """刷新待处理事件到输出队列"""
        if not self.pending_events:
            return

        current_time = time.time()
        flushed_count = 0
        filtered_count = 0

        # 首先收集所有目录删除事件
        directory_deletes = set()
        for file_path, events in self.pending_events.items():
            for event in events:
                if event['type'] == 'DELETE_FOLDER':
                    directory_deletes.add(file_path)

        for file_path, events in list(self.pending_events.items()):
            if not events:
                continue

            # 合并同一文件的多个事件
            merged_event = self._merge_events(events)

            # 检查是否被目录删除事件覆盖
            if self._is_filtered_by_parent_delete(file_path, merged_event, directory_deletes):
                filtered_count += 1
                self.stats['events_filtered'] += 1
                logger.debug(
                    "Event filtered by parent directory delete",
                    file=file_path,
                    parent=self._find_parent_delete(file_path, directory_deletes)
                )
            else:
                await self.output_queue.put(merged_event)
                self.stats['events_output'] += 1
                flushed_count += 1

            # 清空该文件的待处理事件
            del self.pending_events[file_path]

        self.last_flush = current_time

        if flushed_count > 0:
            logger.debug(
                "Events flushed",
                count=flushed_count,
                merged_events=self.stats['events_merged']
            )

    def _merge_events(self, events: List[dict]) -> dict:
        """
        合并事件逻辑

        优先级: DELETE > MOVE > CLOSE_WRITE/MODIFY > CREATE

        Args:
            events: 事件列表

        Returns:
            合并后的事件
        """
        if len(events) == 1:
            return events[0]

        self.stats['events_merged'] += len(events) - 1

        # 优先级排序
        priority_order = {
            'DELETE_FILE': 4,
            'DELETE_FOLDER': 4,
            'MOVE': 3,
            'CLOSE_WRITE': 2,
            'MODIFY': 2,
            'CREATE_FILE': 1,
            'CREATE_FOLDER': 1,
            'ATTRIB': 0,
        }

        # 找到最高优先级的事件
        events_sorted = sorted(
            events,
            key=lambda e: priority_order.get(e['type'], 0),
            reverse=True
        )

        merged = events_sorted[0]
        merged['merged_count'] = len(events)

        logger.debug(
            "Events merged",
            file=merged['path'],
            original_count=len(events),
            final_type=merged['type']
        )

        return merged

    def _is_filtered_by_parent_delete(self, file_path: str, event: dict, directory_deletes: set = None) -> bool:
        """
        检查事件是否被父目录删除事件覆盖

        Args:
            file_path: 文件路径
            event: 事件
            directory_deletes: 当前批次中的目录删除事件集合

        Returns:
            是否被过滤
        """
        # 如果事件本身就是目录删除，不过滤
        if event['type'] == 'DELETE_FOLDER':
            return False
            
        # 使用传入的目录删除集合（优先）或检查待处理事件
        deletes_to_check = directory_deletes if directory_deletes is not None else set()
        
        if not deletes_to_check:
            # 检查待处理事件中的目录删除
            for pending_path, pending_events in self.pending_events.items():
                if any(e['type'] == 'DELETE_FOLDER' for e in pending_events):
                    deletes_to_check.add(pending_path)

        # 检查是否有父目录的删除事件
        for delete_path in deletes_to_check:
            if file_path.startswith(delete_path + '/') or file_path == delete_path:
                return True

        return False

    def _find_parent_delete(self, file_path: str, directory_deletes: set) -> str:
        """
        找到删除该文件的父目录路径
        
        Args:
            file_path: 文件路径
            directory_deletes: 目录删除事件集合
            
        Returns:
            父目录路径，如果没有找到返回空字符串
        """
        for delete_path in directory_deletes:
            if file_path.startswith(delete_path + '/') or file_path == delete_path:
                return delete_path
        return ""

    async def get(self) -> dict:
        """
        从输出队列获取事件

        Returns:
            事件字典
        """
        event = await self.output_queue.get()
        self.output_queue.task_done()
        return event

    async def start_auto_flush(self):
        """启动自动刷新任务"""
        if self._running:
            logger.warning("Auto flush already running")
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._auto_flush_loop())
        logger.info("Auto flush started", window_size=self.window_size)

    async def _auto_flush_loop(self):
        """自动刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self.window_size)
                await self.flush()
            except asyncio.CancelledError:
                logger.info("Auto flush cancelled")
                break
            except Exception as e:
                logger.error("Error in auto flush loop", error=str(e), exc_info=True)

    async def stop(self):
        """停止自动刷新"""
        if not self._running:
            return

        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # 最后一次刷新
        await self.flush()

        logger.info("Event queue stopped", stats=self.stats)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self.stats,
            'pending_files': len(self.pending_events),
            'output_queue_size': self.output_queue.qsize(),
        }

    def is_empty(self) -> bool:
        """检查队列是否为空"""
        return len(self.pending_events) == 0 and self.output_queue.empty()
