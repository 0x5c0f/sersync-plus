"""
通知规则引擎

功能:
- 即时通知规则
- 批量通知规则（阈值触发）
- 定时报告规则
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, time as dt_time
import structlog

from sersync.notification.notifier import NotificationService

logger = structlog.get_logger()


class NotificationRule:
    """通知规则基类"""

    def __init__(
        self,
        event: str,
        notify_type: str,
        tags: List[str],
        enabled: bool = True
    ):
        """
        初始化通知规则

        Args:
            event: 事件类型
            notify_type: 通知类型（immediate, batch, schedule）
            tags: 通知标签列表
            enabled: 是否启用
        """
        self.event = event
        self.notify_type = notify_type
        self.tags = tags
        self.enabled = enabled


class ImmediateRule(NotificationRule):
    """立即通知规则"""

    def __init__(self, event: str, tags: List[str], enabled: bool = True):
        super().__init__(event, 'immediate', tags, enabled)


class BatchRule(NotificationRule):
    """批量通知规则"""

    def __init__(
        self,
        event: str,
        tags: List[str],
        batch_size: int = 100,
        batch_interval: int = 600,  # 秒
        enabled: bool = True
    ):
        """
        初始化批量通知规则

        Args:
            event: 事件类型
            tags: 通知标签列表
            batch_size: 批量大小（达到此数量立即发送）
            batch_interval: 批量间隔（秒）
            enabled: 是否启用
        """
        super().__init__(event, 'batch', tags, enabled)
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.last_flush_time = datetime.now()
        self.event_count = 0


class ScheduleRule(NotificationRule):
    """定时报告规则"""

    def __init__(
        self,
        event: str,
        tags: List[str],
        cron: str,
        timezone: str = 'Asia/Shanghai',
        enabled: bool = True
    ):
        """
        初始化定时报告规则

        Args:
            event: 事件类型（通常是 daily_report, weekly_report）
            tags: 通知标签列表
            cron: Cron 表达式（简化版，仅支持时间）
            timezone: 时区
            enabled: 是否启用
        """
        super().__init__(event, 'schedule', tags, enabled)
        self.cron = cron
        self.timezone = timezone
        self.schedule_time = self._parse_cron(cron)

    def _parse_cron(self, cron: str) -> dt_time:
        """
        解析 cron 表达式（简化版）

        Args:
            cron: Cron 表达式，如 "0 9 * * *"（每天 09:00）

        Returns:
            datetime.time 对象
        """
        parts = cron.split()
        if len(parts) < 2:
            logger.warning("Invalid cron expression", cron=cron)
            return dt_time(9, 0)  # 默认 09:00

        try:
            minute = int(parts[0])
            hour = int(parts[1])
            return dt_time(hour, minute)
        except ValueError:
            logger.warning("Failed to parse cron time", cron=cron)
            return dt_time(9, 0)


class NotificationRuleEngine:
    """通知规则引擎"""

    def __init__(
        self,
        notifier: NotificationService,
        rules: Optional[List[NotificationRule]] = None
    ):
        """
        初始化规则引擎

        Args:
            notifier: 通知服务实例
            rules: 规则列表
        """
        self.notifier = notifier
        self.rules: Dict[str, List[NotificationRule]] = {}
        self._running = False
        self._tasks = []

        # 注册规则
        if rules:
            for rule in rules:
                self.register_rule(rule)

        logger.info(
            "Notification rule engine initialized",
            total_rules=sum(len(r) for r in self.rules.values())
        )

    def register_rule(self, rule: NotificationRule):
        """
        注册通知规则

        Args:
            rule: 通知规则
        """
        if rule.event not in self.rules:
            self.rules[rule.event] = []

        self.rules[rule.event].append(rule)

        logger.debug(
            "Rule registered",
            event=rule.event,
            type=rule.notify_type,
            tags=rule.tags
        )

    async def trigger_event(self, event: str, **kwargs):
        """
        触发事件，执行匹配的规则

        Args:
            event: 事件类型
            **kwargs: 事件数据
        """
        if event not in self.rules:
            return

        for rule in self.rules[event]:
            if not rule.enabled:
                continue

            try:
                if rule.notify_type == 'immediate':
                    await self._handle_immediate(rule, **kwargs)
                elif rule.notify_type == 'batch':
                    await self._handle_batch(rule, **kwargs)

            except Exception as e:
                logger.error(
                    "Rule execution error",
                    event=event,
                    rule_type=rule.notify_type,
                    error=str(e)
                )

    async def _handle_immediate(self, rule: ImmediateRule, **kwargs):
        """处理立即通知规则"""
        await self.notifier.notify_immediate(
            event=rule.event,
            tags=rule.tags,
            **kwargs
        )

    async def _handle_batch(self, rule: BatchRule, **kwargs):
        """处理批量通知规则"""
        batch_key = f"{rule.event}_{','.join(rule.tags)}"

        # 添加到批量队列
        await self.notifier.notify_batch(
            event=rule.event,
            tags=rule.tags,
            batch_key=batch_key,
            **kwargs
        )

        rule.event_count += 1

        # 检查是否需要刷新
        now = datetime.now()
        time_elapsed = (now - rule.last_flush_time).total_seconds()

        should_flush = (
            rule.event_count >= rule.batch_size or
            time_elapsed >= rule.batch_interval
        )

        if should_flush:
            await self.notifier.flush_batch(batch_key, tags=rule.tags)
            rule.event_count = 0
            rule.last_flush_time = now

            logger.debug(
                "Batch flushed",
                event=rule.event,
                reason='size' if rule.event_count >= rule.batch_size else 'timeout'
            )

    async def start(self):
        """启动规则引擎"""
        if self._running:
            logger.warning("Rule engine already running")
            return

        self._running = True
        logger.info("Starting notification rule engine")

        # 启动定时报告任务
        for event, rules in self.rules.items():
            for rule in rules:
                if isinstance(rule, ScheduleRule) and rule.enabled:
                    task = asyncio.create_task(self._schedule_worker(rule))
                    self._tasks.append(task)

        # 启动批量刷新任务
        task = asyncio.create_task(self._batch_flush_worker())
        self._tasks.append(task)

    async def stop(self):
        """停止规则引擎"""
        if not self._running:
            return

        logger.info("Stopping notification rule engine")
        self._running = False

        # 取消所有任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

        # 刷新所有批量队列
        for event, rules in self.rules.items():
            for rule in rules:
                if isinstance(rule, BatchRule):
                    batch_key = f"{rule.event}_{','.join(rule.tags)}"
                    await self.notifier.flush_batch(batch_key, tags=rule.tags)

        logger.info("Notification rule engine stopped")

    async def _schedule_worker(self, rule: ScheduleRule):
        """定时报告工作线程"""
        logger.info(
            "Schedule worker started",
            event=rule.event,
            time=rule.schedule_time.strftime('%H:%M')
        )

        while self._running:
            try:
                # 计算下次执行时间
                now = datetime.now()
                target = now.replace(
                    hour=rule.schedule_time.hour,
                    minute=rule.schedule_time.minute,
                    second=0,
                    microsecond=0
                )

                # 如果今天的时间已过，调整到明天
                if now >= target:
                    from datetime import timedelta
                    target += timedelta(days=1)

                # 等待到执行时间
                wait_seconds = (target - now).total_seconds()
                logger.debug(
                    "Waiting for next scheduled report",
                    event=rule.event,
                    wait_seconds=int(wait_seconds)
                )

                await asyncio.sleep(wait_seconds)

                if not self._running:
                    break

                # 执行定时报告
                logger.info("Sending scheduled report", event=rule.event)

                # 获取统计数据（需要从引擎获取）
                from sersync.core.engine import get_engine_instance
                engine = get_engine_instance()

                if engine:
                    stats = engine.get_stats()
                    await self.notifier.schedule_report(
                        report_type=rule.event,
                        stats=stats,
                        tags=rule.tags
                    )
                else:
                    logger.warning("Engine instance not available for report")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Schedule worker error",
                    event=rule.event,
                    error=str(e)
                )

        logger.info("Schedule worker stopped", event=rule.event)

    async def _batch_flush_worker(self):
        """批量刷新工作线程（定期检查）"""
        logger.info("Batch flush worker started")

        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次

                if not self._running:
                    break

                # 检查所有批量规则
                for event, rules in self.rules.items():
                    for rule in rules:
                        if not isinstance(rule, BatchRule) or not rule.enabled:
                            continue

                        now = datetime.now()
                        time_elapsed = (now - rule.last_flush_time).total_seconds()

                        # 超时自动刷新
                        if time_elapsed >= rule.batch_interval and rule.event_count > 0:
                            batch_key = f"{rule.event}_{','.join(rule.tags)}"
                            await self.notifier.flush_batch(batch_key, tags=rule.tags)
                            rule.event_count = 0
                            rule.last_flush_time = now

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Batch flush worker error", error=str(e))

        logger.info("Batch flush worker stopped")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_rules': sum(len(r) for r in self.rules.values()),
            'immediate_rules': sum(
                1 for rules in self.rules.values()
                for r in rules if isinstance(r, ImmediateRule)
            ),
            'batch_rules': sum(
                1 for rules in self.rules.values()
                for r in rules if isinstance(r, BatchRule)
            ),
            'schedule_rules': sum(
                1 for rules in self.rules.values()
                for r in rules if isinstance(r, ScheduleRule)
            ),
            'batch_queue': self.notifier.get_batch_stats(),
        }
