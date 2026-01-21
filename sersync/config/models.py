"""
配置数据模型
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class HostConfig:
    """主机配置"""
    hostip: str
    port: int


@dataclass
class RemoteConfig:
    """远程目标配置"""
    ip: str
    name: str  # rsync module name
    mode: str = "unidirectional"  # unidirectional, bidirectional
    
    # 双向同步配置
    node_id: Optional[str] = None  # 节点标识，默认自动生成
    conflict_strategy: str = "keep_newer"  # keep_newer, keep_older, keep_local, keep_remote, backup_both
    sync_interval: int = 60  # 双向同步间隔（秒）
    
    # 元信息配置（可选，默认自动生成安全路径）
    metadata_dir: Optional[str] = None
    conflict_backup_dir: Optional[str] = None
    lock_file: Optional[str] = None


@dataclass
class RsyncConfig:
    """Rsync 配置"""
    common_params: str = "-artuz"
    auth_enabled: bool = False
    auth_users: Optional[str] = None
    auth_passwordfile: Optional[str] = None
    custom_port_enabled: bool = False
    custom_port: int = 874
    timeout_enabled: bool = False
    timeout: int = 100
    ssh_enabled: bool = False


@dataclass
class InotifyConfig:
    """Inotify 事件配置"""
    delete: bool = True
    create_folder: bool = True
    create_file: bool = False
    close_write: bool = True
    move_from: bool = True
    move_to: bool = True
    attrib: bool = False
    modify: bool = False


@dataclass
class FilterConfig:
    """过滤配置"""
    enabled: bool = False
    patterns: List[str] = field(default_factory=list)


@dataclass
class FailLogConfig:
    """失败日志配置"""
    path: str = "/tmp/rsync_fail_log.sh"
    time_to_execute: int = 60  # seconds


@dataclass
class CrontabConfig:
    """定期全量同步配置"""
    enabled: bool = False
    schedule: int = 600  # minutes
    filter: Optional[FilterConfig] = None


@dataclass
class PluginConfig:
    """插件配置"""
    name: str  # 必须参数放在前面
    enabled: bool = False
    params: Dict = field(default_factory=dict)


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = False
    apprise_config: str = "/etc/sersync/apprise.yml"
    rules: List[Dict] = field(default_factory=list)
    templates: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class WebConfig:
    """Web 界面配置"""
    enabled: bool = False
    port: int = 8000
    auth_method: str = "basic"  # basic, jwt, none
    users: List[Dict] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    """数据库配置"""
    enabled: bool = True
    type: str = "sqlite"  # 目前只支持 sqlite
    path: str = "/var/sersync/sersync.db"
    auto_cleanup: bool = True
    cleanup_days: int = 7  # 自动清理超过N天的记录
    max_records: int = 100000  # 最大记录数，超过时自动清理最旧的记录


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    format: str = "text"  # text, json
    file_enabled: bool = False
    file_path: str = "/var/sersync/sersync.log"
    file_max_size: str = "10MB"  # 日志文件最大大小
    file_backup_count: int = 5  # 保留的日志文件数量
    console_enabled: bool = True


@dataclass
class BidirectionalConfig:
    """双向同步全局配置"""
    enabled: bool = False
    default_conflict_strategy: str = "keep_newer"
    default_sync_interval: int = 60
    metadata_base_dir: str = "/var/sersync/bidirectional"
    enable_conflict_backup: bool = True
    max_conflict_backups: int = 10  # 最大冲突备份数量


@dataclass
class SersyncConfig:
    """Sersync 主配置"""
    version: str
    host: HostConfig
    debug: bool
    xfs_filesystem: bool
    filter: FilterConfig
    inotify: InotifyConfig
    watch_path: str
    remotes: List[RemoteConfig]
    rsync: RsyncConfig
    fail_log: FailLogConfig
    crontab: CrontabConfig
    plugins: List[PluginConfig]
    notification: NotificationConfig = field(default_factory=lambda: NotificationConfig())
    web: WebConfig = field(default_factory=lambda: WebConfig())
    bidirectional: BidirectionalConfig = field(default_factory=lambda: BidirectionalConfig())
    database: DatabaseConfig = field(default_factory=lambda: DatabaseConfig())
    logging: LoggingConfig = field(default_factory=lambda: LoggingConfig())
