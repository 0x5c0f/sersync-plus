"""
独立 Web 服务入口

用于独立运行 Web 管理界面（不启动同步引擎）
"""

import click
import uvicorn
import structlog
from pathlib import Path

logger = structlog.get_logger()


@click.command()
@click.option(
    '--config',
    '-c',
    type=click.Path(exists=True),
    default='./confxml.xml',
    help='配置文件路径 [默认: ./confxml.xml]'
)
@click.option(
    '--port',
    '-p',
    type=int,
    default=8000,
    help='Web 服务端口 [默认: 8000]'
)
@click.option(
    '--host',
    '-h',
    default='0.0.0.0',
    help='监听主机地址 [默认: 0.0.0.0]'
)
@click.option(
    '--no-auth',
    is_flag=True,
    help='禁用 Basic Auth 认证'
)
@click.option(
    '--reload',
    is_flag=True,
    help='开发模式（自动重载）'
)
def main(config: str, port: int, host: str, no_auth: bool, reload: bool):
    """
    Sersync Web 管理界面（独立模式）

    示例:

    \b
    # 启动 Web 服务（默认端口 8000）
    sersync-web

    \b
    # 指定端口和配置文件
    sersync-web -p 9000 -c /etc/sersync.xml

    \b
    # 禁用认证（仅开发环境）
    sersync-web --no-auth

    \b
    # 开发模式（自动重载）
    sersync-web --reload
    """

    # 配置日志
    from sersync.utils.logger import setup_logging
    setup_logging(level="INFO", log_format="text")

    logger.info(
        "Starting Sersync Web (standalone mode)",
        port=port,
        host=host,
        auth_enabled=not no_auth,
        reload=reload
    )

    # 加载配置（可选）
    config_path = Path(config)
    if config_path.exists():
        try:
            from sersync.config.parser import ConfigParser
            parser = ConfigParser()
            sersync_config = parser.parse(str(config_path))
            logger.info("Configuration loaded", watch_path=sersync_config.watch_path)

            # TODO: 可以在这里创建只读的引擎实例
            # 用于查看配置，但不启动监控

        except Exception as e:
            logger.warning("Failed to load config", error=str(e))
    else:
        logger.warning("Config file not found", path=str(config_path))

    # 创建 FastAPI 应用
    from sersync.web import create_app
    app = create_app(enable_auth=not no_auth)

    # 启动服务器
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        reload=reload,
        access_log=True
    )


if __name__ == '__main__':
    main()
