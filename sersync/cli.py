"""
Sersync CLI Entry Point
"""

import sys
import logging
import asyncio
import platform
import click
import structlog
from pathlib import Path

# 修复 Python 3.12 在 Linux 上的 asyncio 子进程问题
if sys.version_info >= (3, 12) and platform.system() == 'Linux':
    try:
        # 在 Python 3.12+ 中，默认的事件循环策略可能不支持子进程
        # 设置为 ThreadedChildWatcher 来解决这个问题
        if hasattr(asyncio, 'ThreadedChildWatcher'):
            asyncio.set_child_watcher(asyncio.ThreadedChildWatcher())
        elif hasattr(asyncio, 'PidfdChildWatcher'):
            # 如果系统支持 pidfd，使用 PidfdChildWatcher
            asyncio.set_child_watcher(asyncio.PidfdChildWatcher())
        else:
            # 回退到 ThreadedChildWatcher
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    except (AttributeError, NotImplementedError):
        # 如果上述方法都不可用，设置默认策略
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# 配置 structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@click.command()
@click.option(
    '-o', '--config',
    default='./confxml.xml',
    type=click.Path(exists=True),
    help='配置文件路径 [默认: ./confxml.xml]'
)
@click.option(
    '-r', '--initial-sync',
    is_flag=True,
    help='启动前执行一次全量同步'
)
@click.option(
    '-d', '--daemon',
    is_flag=True,
    help='后台守护进程模式'
)
@click.option(
    '-n', '--threads',
    default=10,
    type=int,
    help='线程池大小 [默认: 10]'
)
@click.option(
    '-m', '--plugin',
    type=str,
    help='仅运行指定插件（不同步）'
)
@click.option(
    '--web',
    is_flag=True,
    help='启用 Web 管理界面'
)
@click.option(
    '--web-port',
    default=8000,
    type=int,
    help='Web 界面端口 [默认: 8000]'
)
@click.option(
    '--log-level',
    default='INFO',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    help='日志级别 [默认: INFO]'
)
@click.option(
    '--log-format',
    default='text',
    type=click.Choice(['text', 'json'], case_sensitive=False),
    help='日志格式 [默认: text]'
)
@click.option(
    '--bidirectional',
    is_flag=True,
    help='启用双向同步模式'
)
@click.option(
    '--bidir-host',
    type=str,
    help='双向同步远程主机'
)
@click.option(
    '--bidir-root',
    type=str,
    help='双向同步远程根目录'
)
@click.option(
    '--conflict-strategy',
    default='keep_newer',
    type=click.Choice(['keep_newer', 'keep_older', 'keep_local', 'keep_remote', 'backup_both', 'manual', 'skip'], case_sensitive=False),
    help='冲突解决策略 [默认: keep_newer]'
)
@click.option(
    '--db-path',
    type=str,
    help='数据库文件路径 [默认: /var/sersync/sersync.db]'
)
@click.option(
    '--log-file',
    type=str,
    help='日志文件路径（启用文件日志）'
)
@click.version_option(version='0.1.0', prog_name='sersync-python')
def main(
    config: str,
    initial_sync: bool,
    daemon: bool,
    threads: int,
    plugin: str,
    web: bool,
    web_port: int,
    log_level: str,
    log_format: str,
    bidirectional: bool,
    bidir_host: str,
    bidir_root: str,
    conflict_strategy: str,
    db_path: str,
    log_file: str
):
    """
    Sersync Python - 实时文件同步工具

    示例:

    \b
    # 前台运行，初始全量同步
    sersync -r -o /etc/sersync.xml

    \b
    # 后台运行，20 线程，启用 Web 界面
    sersync -d -n 20 --web --web-port 8000

    \b
    # 启用双向同步
    sersync --bidirectional --bidir-host 192.168.1.100 --bidir-root /data/remote

    \b
    # 双向同步 + 冲突策略
    sersync --bidirectional --bidir-host 192.168.1.100 --bidir-root /data/remote --conflict-strategy keep_newer

    \b
    # 仅运行插件
    sersync -m refreshCDN -o /etc/sersync.xml
    """

    # 配置日志级别
    import logging
    log_level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
    }
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level_map[log_level])
    )

    logger.info(
        "Sersync starting",
        version="0.1.0",
        config=config,
        daemon=daemon,
        threads=threads,
        web=web,
        bidirectional=bidirectional,
    )

    try:
        # 加载配置
        from sersync.config.parser import ConfigParser
        config_parser = ConfigParser()
        sersync_config = config_parser.parse(config)

        logger.info("Configuration loaded", watch_path=sersync_config.watch_path)

        # 覆盖配置文件中的数据库设置（如果通过命令行指定）
        if db_path:
            sersync_config.database.path = db_path
            logger.info("Database path overridden via CLI", path=db_path)

        # 覆盖配置文件中的日志设置（如果通过命令行指定）
        if log_file:
            sersync_config.logging.file_enabled = True
            sersync_config.logging.file_path = log_file
            logger.info("Log file enabled via CLI", path=log_file)

        # 覆盖日志级别和格式
        sersync_config.logging.level = log_level.upper()
        sersync_config.logging.format = log_format

        # 覆盖配置文件中的双向同步设置（如果通过命令行指定）
        if bidirectional:
            if bidir_host:
                sersync_config.bidirectional.enabled = True
                sersync_config.bidirectional.remote_host = bidir_host
                if bidir_root:
                    sersync_config.bidirectional.remote_root = bidir_root
                sersync_config.bidirectional.conflict_strategy = conflict_strategy
                logger.info(
                    "Bidirectional sync enabled via CLI",
                    remote_host=bidir_host,
                    remote_root=bidir_root,
                    conflict_strategy=conflict_strategy
                )
            else:
                logger.error("Bidirectional sync requires --bidir-host")
                sys.exit(1)

        # 仅运行插件模式
        if plugin:
            logger.info("Plugin-only mode", plugin=plugin)
            from sersync.plugins import run_plugin_standalone
            run_plugin_standalone(plugin, sersync_config)
            return

        # 守护进程模式
        if daemon:
            logger.info("Running in daemon mode")
            from sersync.utils.daemon import daemonize
            daemonize()

        # 启动核心引擎
        from sersync.core.engine import SersyncEngine, set_engine_instance
        engine = SersyncEngine(sersync_config, threads=threads)
        set_engine_instance(engine)

        # 启动双向同步协调器（如果启用）
        bidirectional_coordinator = None
        if sersync_config.bidirectional.enabled:
            logger.info("Initializing bidirectional sync coordinator")
            from sersync.bidirectional import BidirectionalCoordinator, ResolutionStrategy

            # 将字符串策略转换为枚举
            strategy_map = {
                "keep_newer": ResolutionStrategy.KEEP_NEWER,
                "keep_older": ResolutionStrategy.KEEP_OLDER,
                "keep_local": ResolutionStrategy.KEEP_LOCAL,
                "keep_remote": ResolutionStrategy.KEEP_REMOTE,
                "backup_both": ResolutionStrategy.BACKUP_BOTH,
                "manual": ResolutionStrategy.MANUAL,
                "skip": ResolutionStrategy.SKIP,
            }
            strategy = strategy_map.get(
                sersync_config.bidirectional.conflict_strategy,
                ResolutionStrategy.KEEP_NEWER
            )

            bidirectional_coordinator = BidirectionalCoordinator(
                local_root=sersync_config.watch_path,
                remote_root=sersync_config.bidirectional.remote_root,
                remote_host=sersync_config.bidirectional.remote_host,
                remote_user=sersync_config.bidirectional.remote_user,
                ssh_port=sersync_config.bidirectional.ssh_port,
                conflict_strategy=strategy,
                sync_interval=sersync_config.bidirectional.sync_interval,
                enable_unison=sersync_config.bidirectional.enable_unison,
                ignore_patterns=sersync_config.bidirectional.ignore_patterns
            )

            logger.info(
                "Bidirectional coordinator initialized",
                remote_host=sersync_config.bidirectional.remote_host,
                strategy=strategy.value
            )

        # 初始全量同步
        if initial_sync:
            logger.info("Performing initial full sync")
            import asyncio
            asyncio.run(engine.full_sync())

        # 启动 Web 界面（如果启用）
        if web or sersync_config.web.enabled:
            actual_port = web_port if web else sersync_config.web.port
            logger.info("Starting Web dashboard", port=actual_port)

            from sersync.web import create_app, setup_engine_integration
            import uvicorn
            import threading

            # 创建 Web 应用
            app = create_app(enable_auth=True)

            # 连接引擎和 WebSocket
            setup_engine_integration(app)

            # 在后台线程启动 Web 服务器
            web_thread = threading.Thread(
                target=lambda: uvicorn.run(app, host='0.0.0.0', port=actual_port, log_level="error"),
                daemon=True
            )
            web_thread.start()
            logger.info("Web dashboard started", port=actual_port, url=f"http://localhost:{actual_port}")

        # 启动双向同步协调器（如果启用）
        if bidirectional_coordinator:
            logger.info("Starting bidirectional sync coordinator")
            import asyncio

            async def run_with_bidirectional():
                # 启动协调器
                await bidirectional_coordinator.start()

                # 将本地事件转发到协调器
                original_on_event = engine._on_file_event

                def on_file_event_with_bidir(event_type: str, file_path: str, **kwargs):
                    # 调用原始处理器
                    original_on_event(event_type, file_path, **kwargs)
                    # 转发到双向协调器
                    asyncio.create_task(
                        bidirectional_coordinator.on_local_event(event_type, file_path)
                    )

                engine._on_file_event = on_file_event_with_bidir

                # 启动引擎
                await engine.start()

                # 停止协调器
                await bidirectional_coordinator.stop()

            asyncio.run(run_with_bidirectional())
        else:
            # 启动实时监控（常规模式）
            logger.info("Starting real-time monitoring")
            import asyncio
            asyncio.run(engine.start())

    except KeyboardInterrupt:
        logger.info("Received shutdown signal, stopping...")
    except Exception as e:
        logger.error("Fatal error", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
