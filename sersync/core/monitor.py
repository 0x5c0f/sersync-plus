"""
文件监控模块

支持:
- Linux: pyinotify (支持 CLOSE_WRITE 事件)
- 其他系统: watchdog (降级方案)
"""

import sys
import asyncio
from pathlib import Path
from typing import Callable, Optional
import structlog

from sersync.config.models import InotifyConfig

logger = structlog.get_logger()


class FileMonitor:
    """文件监控器（跨平台）"""

    def __init__(
        self,
        watch_path: str,
        config: InotifyConfig,
        event_callback: Callable,
        recursive: bool = True
    ):
        self.watch_path = Path(watch_path)
        self.config = config
        self.event_callback = event_callback
        self.recursive = recursive
        self.observer = None
        self._running = False

        # 根据平台选择实现
        if sys.platform.startswith('linux'):
            try:
                import pyinotify
                self.backend = "pyinotify"
                self._setup_pyinotify()
                logger.info("Using pyinotify backend (full CLOSE_WRITE support)")
            except ImportError:
                logger.warning("pyinotify not available, falling back to watchdog")
                self.backend = "watchdog"
                self._setup_watchdog()
        else:
            self.backend = "watchdog"
            self._setup_watchdog()
            logger.warning(
                "Non-Linux platform detected, using watchdog (CLOSE_WRITE downgraded to MODIFY)",
                platform=sys.platform
            )

    def _setup_pyinotify(self):
        """设置 pyinotify 监控（Linux）"""
        import pyinotify

        # 构建事件掩码
        mask = 0
        if self.config.delete:
            mask |= pyinotify.IN_DELETE
        if self.config.create_folder:
            mask |= pyinotify.IN_CREATE | pyinotify.IN_ISDIR
        if self.config.create_file:
            mask |= pyinotify.IN_CREATE
        if self.config.close_write:
            mask |= pyinotify.IN_CLOSE_WRITE
        if self.config.move_from:
            mask |= pyinotify.IN_MOVED_FROM
        if self.config.move_to:
            mask |= pyinotify.IN_MOVED_TO
        if self.config.attrib:
            mask |= pyinotify.IN_ATTRIB
        if self.config.modify:
            mask |= pyinotify.IN_MODIFY

        self.mask = mask

        # 事件处理器
        class EventHandler(pyinotify.ProcessEvent):
            def __init__(self, callback, config):
                super().__init__()
                self.callback = callback
                self.config = config
                self.move_buffer = {}  # 缓存 MOVE_FROM 事件

            def process_IN_DELETE(self, event):
                if not self.config.delete:
                    return
                event_type = 'DELETE_FOLDER' if event.dir else 'DELETE_FILE'
                self.callback(event_type, event.pathname)

            def process_IN_CREATE(self, event):
                if event.dir and self.config.create_folder:
                    self.callback('CREATE_FOLDER', event.pathname)
                elif not event.dir and self.config.create_file:
                    self.callback('CREATE_FILE', event.pathname)

            def process_IN_CLOSE_WRITE(self, event):
                if self.config.close_write and not event.dir:
                    self.callback('CLOSE_WRITE', event.pathname)

            def process_IN_MODIFY(self, event):
                if self.config.modify and not event.dir:
                    self.callback('MODIFY', event.pathname)

            def process_IN_ATTRIB(self, event):
                if self.config.attrib:
                    self.callback('ATTRIB', event.pathname)

            def process_IN_MOVED_FROM(self, event):
                """文件移出事件"""
                if not self.config.move_from:
                    return
                # 缓存 MOVE_FROM 事件，等待配对的 MOVE_TO
                self.move_buffer[event.cookie] = {
                    'src_path': event.pathname,
                    'is_dir': event.dir
                }

            def process_IN_MOVED_TO(self, event):
                """文件移入事件"""
                if not self.config.move_to:
                    return

                # 检查是否有配对的 MOVE_FROM
                if event.cookie in self.move_buffer:
                    move_from = self.move_buffer.pop(event.cookie)
                    # 内部移动
                    self.callback(
                        'MOVE',
                        move_from['src_path'],
                        dest_path=event.pathname,
                        is_dir=event.dir
                    )
                else:
                    # 从外部移入，视为新建
                    event_type = 'CREATE_FOLDER' if event.dir else 'CREATE_FILE'
                    self.callback(event_type, event.pathname)

        self.handler = EventHandler(self.event_callback, self.config)

    def _setup_watchdog(self):
        """设置 watchdog 监控（跨平台降级方案）"""
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class EventHandler(FileSystemEventHandler):
            def __init__(self, callback, config):
                super().__init__()
                self.callback = callback
                self.config = config

            def on_created(self, event):
                if event.is_directory and self.config.create_folder:
                    self.callback('CREATE_FOLDER', event.src_path)
                elif not event.is_directory and self.config.create_file:
                    self.callback('CREATE_FILE', event.src_path)

            def on_modified(self, event):
                # watchdog 不支持 CLOSE_WRITE，降级为 MODIFY
                if not event.is_directory:
                    if self.config.close_write or self.config.modify:
                        self.callback('MODIFY', event.src_path)

            def on_deleted(self, event):
                if self.config.delete:
                    event_type = 'DELETE_FOLDER' if event.is_directory else 'DELETE_FILE'
                    self.callback(event_type, event.src_path)

            def on_moved(self, event):
                if self.config.move_from and self.config.move_to:
                    self.callback(
                        'MOVE',
                        event.src_path,
                        dest_path=event.dest_path,
                        is_dir=event.is_directory
                    )

        self.handler = EventHandler(self.event_callback, self.config)
        self.observer = Observer()

    async def start(self):
        """启动监控"""
        if self._running:
            logger.warning("Monitor already running")
            return

        self._running = True
        logger.info(
            "Starting file monitor",
            path=str(self.watch_path),
            backend=self.backend,
            recursive=self.recursive
        )

        if self.backend == "pyinotify":
            await self._start_pyinotify()
        else:
            await self._start_watchdog()

    async def _start_pyinotify(self):
        """启动 pyinotify 监控"""
        import pyinotify

        wm = pyinotify.WatchManager()
        notifier = pyinotify.AsyncioNotifier(wm, asyncio.get_event_loop(), default_proc_fun=self.handler)

        # 添加监控路径
        wm.add_watch(
            str(self.watch_path),
            self.mask,
            rec=self.recursive,
            auto_add=True  # 自动添加新创建的子目录
        )

        self.wm = wm
        self.notifier = notifier

        logger.info("pyinotify monitor started", watches=len(wm.watches))

    async def _start_watchdog(self):
        """启动 watchdog 监控"""
        self.observer.schedule(
            self.handler,
            str(self.watch_path),
            recursive=self.recursive
        )
        self.observer.start()

        logger.info("watchdog monitor started")

        # 保持运行
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Monitor cancelled")

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping file monitor")

        if self.backend == "pyinotify":
            if hasattr(self, 'notifier'):
                self.notifier.stop()
        else:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)

        logger.info("File monitor stopped")

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running
