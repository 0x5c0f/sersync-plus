"""
通知服务模块（基于 Apprise）

功能:
- 支持 100+ 通知服务（Telegram, 钉钉, 企业微信, 邮件等）
- 即时/批量/定时通知
- 模板系统
- 失败重试
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import structlog

try:
    import apprise
    APPRISE_AVAILABLE = True
except ImportError:
    APPRISE_AVAILABLE = False

logger = structlog.get_logger()


class NotificationService:
    """通知服务（基于 Apprise）"""

    def __init__(
        self,
        config_path: str,
        templates: Optional[Dict[str, Dict]] = None,
        enabled: bool = True
    ):
        """
        初始化通知服务

        Args:
            config_path: Apprise 配置文件路径
            templates: 通知模板字典
            enabled: 是否启用通知
        """
        self.config_path = config_path
        self.templates = templates or {}
        self.enabled = enabled
        self.batch_queue: Dict[str, List[dict]] = {}

        if not APPRISE_AVAILABLE:
            logger.error(
                "Apprise not installed. Install with: pip install apprise",
                hint="Run: poetry install -E notifications"
            )
            self.enabled = False
            return

        if not self.enabled:
            logger.info("Notification service disabled")
            return

        # 初始化 Apprise
        self.apobj = apprise.Apprise()
        self._load_config()

        logger.info(
            "Notification service initialized",
            services=len(self.apobj),
            templates=len(self.templates)
        )

    def _load_config(self):
        """加载 Apprise 配置文件"""
        config_path = Path(self.config_path)

        if not config_path.exists():
            logger.warning(
                "Apprise config file not found",
                path=str(config_path),
                hint="Create config file with notification service URLs"
            )
            return

        try:
            config = apprise.AppriseConfig()
            config.add(str(config_path))
            self.apobj.add(config)

            logger.info(
                "Apprise config loaded",
                path=str(config_path),
                services=len(self.apobj)
            )
        except Exception as e:
            logger.error(
                "Failed to load Apprise config",
                path=str(config_path),
                error=str(e)
            )

    async def notify_immediate(
        self,
        event: str,
        tags: Optional[List[str]] = None,
        **kwargs
    ) -> bool:
        """
        立即发送通知

        Args:
            event: 事件类型
            tags: 通知标签列表（用于筛选服务）
            **kwargs: 模板变量

        Returns:
            是否发送成功
        """
        if not self.enabled or not APPRISE_AVAILABLE:
            return False

        # 获取模板
        template = self.templates.get(event, {})
        title = template.get('title', f'Sersync Event: {event}')
        body = template.get('body', str(kwargs))

        # 格式化模板
        try:
            title = title.format(**kwargs)
            body = body.format(**kwargs)
        except KeyError as e:
            logger.warning(
                "Template variable missing",
                event=event,
                missing_var=str(e)
            )

        # 发送通知
        return await self._send_notification(
            title=title,
            body=body,
            tags=tags,
            notify_type=self._get_notify_type(event)
        )

    async def notify_batch(
        self,
        event: str,
        tags: Optional[List[str]] = None,
        batch_key: str = 'default',
        **kwargs
    ):
        """
        批量通知（累积后发送）

        Args:
            event: 事件类型
            tags: 通知标签列表
            batch_key: 批量队列键
            **kwargs: 事件数据
        """
        if not self.enabled or not APPRISE_AVAILABLE:
            return

        if batch_key not in self.batch_queue:
            self.batch_queue[batch_key] = []

        self.batch_queue[batch_key].append({
            'event': event,
            'tags': tags,
            'data': kwargs,
            'timestamp': datetime.now()
        })

        logger.debug(
            "Event added to batch queue",
            event=event,
            batch_key=batch_key,
            queue_size=len(self.batch_queue[batch_key])
        )

    async def flush_batch(
        self,
        batch_key: str,
        tags: Optional[List[str]] = None,
        max_display: int = 50
    ) -> bool:
        """
        刷新批量通知队列

        Args:
            batch_key: 批量队列键
            tags: 通知标签列表
            max_display: 最大显示条目数

        Returns:
            是否发送成功
        """
        if not self.enabled or not APPRISE_AVAILABLE:
            return False

        if batch_key not in self.batch_queue or not self.batch_queue[batch_key]:
            return True

        events = self.batch_queue[batch_key]
        count = len(events)

        # 构建批量通知消息
        title = f"📦 Sersync 批量通知 ({count} 个事件)"

        body_lines = []
        for i, item in enumerate(events[:max_display]):
            data = item['data']
            timestamp = item['timestamp'].strftime('%H:%M:%S')
            file_path = data.get('file_path', 'N/A')
            remote = data.get('remote_ip', data.get('remote', 'N/A'))
            status = '✅' if data.get('success', True) else '❌'

            body_lines.append(f"{status} {timestamp} | {file_path} → {remote}")

        if count > max_display:
            body_lines.append(f"\n... 还有 {count - max_display} 个事件")

        body = "\n".join(body_lines)

        # 发送通知
        success = await self._send_notification(
            title=title,
            body=body,
            tags=tags,
            notify_type=apprise.NotifyType.INFO
        )

        if success:
            # 清空队列
            self.batch_queue[batch_key] = []
            logger.info("Batch notification sent", count=count, tags=tags)

        return success

    async def schedule_report(
        self,
        report_type: str,
        stats: Dict,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        发送定时报告

        Args:
            report_type: 报告类型（daily_report, weekly_report）
            stats: 统计数据
            tags: 通知标签列表

        Returns:
            是否发送成功
        """
        if not self.enabled or not APPRISE_AVAILABLE:
            return False

        # 获取报告模板
        template = self.templates.get(report_type, {})
        title = template.get('title', f'📊 Sersync {report_type}')
        body = template.get('body', str(stats))

        # 格式化统计数据
        try:
            formatted_stats = {
                'success_count': stats.get('success_count', 0),
                'failed_count': stats.get('failed_count', 0),
                'total_bytes': self._format_bytes(stats.get('total_bytes', 0)),
                'uptime': self._format_uptime(stats.get('uptime_seconds', 0)),
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                **stats
            }

            title = title.format(**formatted_stats)
            body = body.format(**formatted_stats)
        except Exception as e:
            logger.error("Failed to format report", error=str(e))
            body = str(stats)

        return await self._send_notification(
            title=title,
            body=body,
            tags=tags,
            notify_type=apprise.NotifyType.INFO
        )

    async def _send_notification(
        self,
        title: str,
        body: str,
        tags: Optional[List[str]] = None,
        notify_type: 'apprise.NotifyType' = None
    ) -> bool:
        """
        发送通知（底层方法）

        Args:
            title: 通知标题
            body: 通知正文
            tags: 标签列表
            notify_type: 通知类型

        Returns:
            是否发送成功
        """
        if not APPRISE_AVAILABLE:
            return False

        notify_type = notify_type or apprise.NotifyType.INFO

        try:
            # 异步发送通知
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self.apobj.notify(
                    body=body,
                    title=title,
                    notify_type=notify_type,
                    tag=tags
                )
            )

            if success:
                logger.debug(
                    "Notification sent successfully",
                    title=title,
                    tags=tags
                )
            else:
                logger.warning(
                    "Notification failed",
                    title=title,
                    tags=tags
                )

            return success

        except Exception as e:
            logger.error(
                "Notification error",
                title=title,
                error=str(e),
                exc_info=True
            )
            return False

    def _get_notify_type(self, event: str) -> 'apprise.NotifyType':
        """
        根据事件类型获取通知类型

        Args:
            event: 事件类型

        Returns:
            Apprise 通知类型
        """
        if 'failed' in event.lower() or 'error' in event.lower():
            return apprise.NotifyType.FAILURE
        elif 'conflict' in event.lower():
            return apprise.NotifyType.WARNING
        elif 'success' in event.lower():
            return apprise.NotifyType.SUCCESS
        else:
            return apprise.NotifyType.INFO

    @staticmethod
    def _format_bytes(size: int) -> str:
        """格式化字节大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    @staticmethod
    def _format_uptime(seconds: int) -> str:
        """格式化运行时长"""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        return f"{days}天 {hours}小时 {minutes}分钟"

    def get_batch_stats(self) -> Dict[str, int]:
        """获取批量队列统计"""
        return {
            key: len(events)
            for key, events in self.batch_queue.items()
        }

    def is_enabled(self) -> bool:
        """检查通知服务是否启用"""
        return self.enabled and APPRISE_AVAILABLE
