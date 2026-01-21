"""
XML 配置文件解析器
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict
import structlog

from sersync.config.models import (
    SersyncConfig,
    HostConfig,
    RemoteConfig,
    RsyncConfig,
    InotifyConfig,
    FilterConfig,
    FailLogConfig,
    CrontabConfig,
    PluginConfig,
    NotificationConfig,
    WebConfig,
    BidirectionalConfig,
    DatabaseConfig,
    LoggingConfig,
)

logger = structlog.get_logger()


class ConfigParser:
    """XML 配置文件解析器"""

    def parse(self, config_path: str) -> SersyncConfig:
        """
        解析 confxml.xml 配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            SersyncConfig 对象
        """
        logger.info("Parsing configuration", path=config_path)

        tree = ET.parse(config_path)
        root = tree.getroot()

        # 解析各个配置节点
        version = root.attrib.get('version', '2.5')

        host = self._parse_host(root.find('host'))
        debug = self._parse_bool(root.find('debug'))
        xfs = self._parse_bool(root.find('fileSystem'), attr='xfs')
        filter_config = self._parse_filter(root.find('filter'))
        inotify = self._parse_inotify(root.find('inotify'))

        # 解析 sersync 节点
        sersync_node = root.find('sersync')
        localpath = sersync_node.find('localpath')
        watch_path = localpath.attrib.get('watch', '/')
        remotes = self._parse_remotes(localpath.findall('remote'))

        rsync = self._parse_rsync(sersync_node.find('rsync'))
        fail_log = self._parse_fail_log(sersync_node.find('failLog'))
        crontab = self._parse_crontab(sersync_node.find('crontab'))
        plugins = self._parse_plugins(root.findall('plugin'))

        # 扩展配置（可选）
        notification = self._parse_notification(root.find('notification'))
        web = self._parse_web(root.find('web'))
        bidirectional = self._parse_bidirectional(root.find('bidirectional'))
        database = self._parse_database(root.find('database'))
        logging_config = self._parse_logging(root.find('logging'))

        config = SersyncConfig(
            version=version,
            host=host,
            debug=debug,
            xfs_filesystem=xfs,
            filter=filter_config,
            inotify=inotify,
            watch_path=watch_path,
            remotes=remotes,
            rsync=rsync,
            fail_log=fail_log,
            crontab=crontab,
            plugins=plugins,
            notification=notification,
            web=web,
            bidirectional=bidirectional,
            database=database,
            logging=logging_config,
        )

        logger.info("Configuration parsed successfully", watch_path=watch_path, remotes=len(remotes))
        return config

    def _parse_host(self, node) -> HostConfig:
        """解析 host 节点"""
        return HostConfig(
            hostip=node.attrib.get('hostip', 'localhost'),
            port=int(node.attrib.get('port', 8008))
        )

    def _parse_bool(self, node, attr='start', default=False) -> bool:
        """解析布尔值"""
        if node is None:
            return default
        value = node.attrib.get(attr, 'false' if not default else 'true')
        return value.lower() == 'true'

    def _parse_filter(self, node) -> FilterConfig:
        """解析 filter 节点"""
        if node is None:
            return FilterConfig()

        enabled = self._parse_bool(node)
        patterns = [
            e.attrib.get('expression', '')
            for e in node.findall('exclude')
        ]

        return FilterConfig(enabled=enabled, patterns=patterns)

    def _parse_inotify(self, node) -> InotifyConfig:
        """解析 inotify 节点"""
        if node is None:
            return InotifyConfig()

        return InotifyConfig(
            delete=self._parse_bool(node.find('delete')),
            create_folder=self._parse_bool(node.find('createFolder')),
            create_file=self._parse_bool(node.find('createFile')),
            close_write=self._parse_bool(node.find('closeWrite')),
            move_from=self._parse_bool(node.find('moveFrom')),
            move_to=self._parse_bool(node.find('moveTo')),
            attrib=self._parse_bool(node.find('attrib')),
            modify=self._parse_bool(node.find('modify')),
        )

    def _parse_remotes(self, nodes) -> List[RemoteConfig]:
        """解析 remote 节点"""
        remotes = []
        
        for node in nodes:
            # 基本配置
            remote = RemoteConfig(
                ip=node.attrib.get('ip', ''),
                name=node.attrib.get('name', ''),
                mode=node.attrib.get('mode', 'unidirectional'),
                node_id=node.attrib.get('node_id'),
                conflict_strategy=node.attrib.get('conflict_strategy', 'keep_newer'),
                sync_interval=int(node.attrib.get('sync_interval', '60'))
            )
            
            # 解析双向同步的元信息配置
            if remote.mode == 'bidirectional':
                metadata_node = node.find('metadata')
                if metadata_node is not None:
                    remote.metadata_dir = metadata_node.get('sync_state_dir')
                    remote.conflict_backup_dir = metadata_node.get('conflict_backup_dir')
                    remote.lock_file = metadata_node.get('lock_file')
            
            remotes.append(remote)
        
        return remotes

    def _parse_rsync(self, node) -> RsyncConfig:
        """解析 rsync 节点"""
        if node is None:
            return RsyncConfig()

        common_params = node.find('commonParams')
        auth = node.find('auth')
        port = node.find('userDefinedPort')
        timeout = node.find('timeout')
        ssh = node.find('ssh')

        return RsyncConfig(
            common_params=common_params.attrib.get('params', '-artuz') if common_params is not None else '-artuz',
            auth_enabled=self._parse_bool(auth) if auth is not None else False,
            auth_users=auth.attrib.get('users', None) if auth is not None else None,
            auth_passwordfile=auth.attrib.get('passwordfile', None) if auth is not None else None,
            custom_port_enabled=self._parse_bool(port) if port is not None else False,
            custom_port=int(port.attrib.get('port', 874)) if port is not None else 874,
            timeout_enabled=self._parse_bool(timeout) if timeout is not None else False,
            timeout=int(timeout.attrib.get('time', 100)) if timeout is not None else 100,
            ssh_enabled=self._parse_bool(ssh) if ssh is not None else False,
        )

    def _parse_fail_log(self, node) -> FailLogConfig:
        """解析 failLog 节点"""
        if node is None:
            return FailLogConfig()

        return FailLogConfig(
            path=node.attrib.get('path', '/tmp/rsync_fail_log.sh'),
            time_to_execute=int(node.attrib.get('timeToExecute', 60))
        )

    def _parse_crontab(self, node) -> CrontabConfig:
        """解析 crontab 节点"""
        if node is None:
            return CrontabConfig()

        enabled = self._parse_bool(node)
        schedule = int(node.attrib.get('schedule', 600))

        filter_node = node.find('crontabfilter')
        cron_filter = self._parse_filter(filter_node) if filter_node is not None else None

        return CrontabConfig(
            enabled=enabled,
            schedule=schedule,
            filter=cron_filter
        )

    def _parse_plugins(self, nodes) -> List[PluginConfig]:
        """解析 plugin 节点"""
        return [
            PluginConfig(
                enabled=self._parse_bool(node),
                name=node.attrib.get('name', ''),
                params={}  # TODO: 解析插件参数
            )
            for node in nodes
        ]

    def _parse_notification(self, node) -> NotificationConfig:
        """解析 notification 节点（扩展功能）"""
        if node is None:
            return NotificationConfig()

        enabled = self._parse_bool(node.find('enabled'))
        apprise_config = node.find('apprise_config')

        # 解析规则
        rules = []
        rules_node = node.find('rules')
        if rules_node is not None:
            for rule_node in rules_node.findall('rule'):
                rule = {
                    'event': rule_node.attrib.get('event', ''),
                    'notify': rule_node.attrib.get('notify', 'immediate'),
                    'tags': rule_node.attrib.get('tags', '').split(','),
                    'batch_size': int(rule_node.attrib.get('batch_size', 100)),
                    'batch_interval': int(rule_node.attrib.get('batch_interval', 600)),
                    'cron': rule_node.attrib.get('cron', '0 9 * * *'),
                }
                rules.append(rule)

        # 解析模板
        templates = {}
        templates_node = node.find('templates')
        if templates_node is not None:
            for template_node in templates_node.findall('template'):
                name = template_node.attrib.get('name', '')
                title_node = template_node.find('title')
                body_node = template_node.find('body')

                templates[name] = {
                    'title': title_node.text.strip() if title_node is not None else '',
                    'body': body_node.text.strip() if body_node is not None else '',
                }

        return NotificationConfig(
            enabled=enabled,
            apprise_config=apprise_config.attrib.get('path', '/etc/sersync/apprise.yml') if apprise_config is not None else '/etc/sersync/apprise.yml',
            rules=rules,
            templates=templates
        )

    def _parse_web(self, node) -> WebConfig:
        """解析 web 节点（扩展功能）"""
        if node is None:
            return WebConfig()

        enabled = self._parse_bool(node)
        port = int(node.attrib.get('port', 8000))

        return WebConfig(
            enabled=enabled,
            port=port
        )

    def _parse_bidirectional(self, node) -> BidirectionalConfig:
        """解析 bidirectional 节点（全局配置）"""
        if node is None:
            return BidirectionalConfig()

        enabled = self._parse_bool(node)
        
        # 解析全局双向同步配置
        default_conflict_strategy = node.attrib.get('default_conflict_strategy', 'keep_newer')
        default_sync_interval = int(node.attrib.get('default_sync_interval', '60'))
        metadata_base_dir = node.attrib.get('metadata_base_dir', '/var/sersync/bidirectional')
        enable_conflict_backup = node.attrib.get('enable_conflict_backup', 'true').lower() == 'true'
        max_conflict_backups = int(node.attrib.get('max_conflict_backups', '10'))

        return BidirectionalConfig(
            enabled=enabled,
            default_conflict_strategy=default_conflict_strategy,
            default_sync_interval=default_sync_interval,
            metadata_base_dir=metadata_base_dir,
            enable_conflict_backup=enable_conflict_backup,
            max_conflict_backups=max_conflict_backups
        )

    def _parse_database(self, node) -> DatabaseConfig:
        """解析 database 节点（扩展功能）"""
        if node is None:
            return DatabaseConfig()

        enabled = self._parse_bool(node)
        db_type = node.attrib.get('type', 'sqlite')
        path = node.attrib.get('path', '/var/sersync/sersync.db')

        # 解析自动清理配置
        cleanup_node = node.find('cleanup')
        auto_cleanup = True
        cleanup_days = 7
        max_records = 100000

        if cleanup_node is not None:
            auto_cleanup = self._parse_bool(cleanup_node, 'enabled')
            days_node = cleanup_node.find('days')
            cleanup_days = int(days_node.text) if days_node is not None else 7
            
            max_records_node = cleanup_node.find('max_records')
            max_records = int(max_records_node.text) if max_records_node is not None else 100000

        return DatabaseConfig(
            enabled=enabled,
            type=db_type,
            path=path,
            auto_cleanup=auto_cleanup,
            cleanup_days=cleanup_days,
            max_records=max_records
        )

    def _parse_logging(self, node) -> LoggingConfig:
        """解析 logging 节点（扩展功能）"""
        if node is None:
            return LoggingConfig()

        level = node.attrib.get('level', 'INFO')
        format_type = node.attrib.get('format', 'text')

        # 解析控制台日志
        console_node = node.find('console')
        console_enabled = True
        if console_node is not None:
            console_enabled = self._parse_bool(console_node, 'enabled')

        # 解析文件日志
        file_node = node.find('file')
        file_enabled = False
        file_path = '/var/sersync/sersync.log'
        file_max_size = '10MB'
        file_backup_count = 5

        if file_node is not None:
            file_enabled = self._parse_bool(file_node, 'enabled')
            file_path = file_node.attrib.get('path', file_path)
            file_max_size = file_node.attrib.get('max_size', file_max_size)
            
            backup_count_node = file_node.find('backup_count')
            file_backup_count = int(backup_count_node.text) if backup_count_node is not None else 5

        return LoggingConfig(
            level=level,
            format=format_type,
            console_enabled=console_enabled,
            file_enabled=file_enabled,
            file_path=file_path,
            file_max_size=file_max_size,
            file_backup_count=file_backup_count
        )
