"""
Web 配置管理器

用于管理 Web 相关的全局配置，包括数据库路径等
"""

import structlog

logger = structlog.get_logger()


class WebConfigManager:
    """Web 配置管理器"""
    
    def __init__(self):
        self._db_path = "/var/sersync/sersync.db"  # 默认路径
        self._config = None
    
    def set_config(self, config):
        """设置 Sersync 配置对象"""
        self._config = config
        if config and config.database:
            self._db_path = config.database.path
            logger.info("Web config updated", db_path=self._db_path)
    
    def get_db_path(self) -> str:
        """获取数据库路径"""
        return self._db_path
    
    def set_db_path(self, path: str):
        """设置数据库路径"""
        self._db_path = path
        logger.info("Database path updated", path=path)
    
    def get_config(self):
        """获取配置对象"""
        return self._config


# 全局配置管理器实例
_web_config_manager = WebConfigManager()


def get_web_config_manager() -> WebConfigManager:
    """获取全局 Web 配置管理器"""
    return _web_config_manager


def set_web_config(config):
    """设置 Web 配置"""
    _web_config_manager.set_config(config)


def get_db_path() -> str:
    """获取数据库路径"""
    return _web_config_manager.get_db_path()