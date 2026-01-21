"""
文件过滤引擎

功能:
- 正则表达式过滤
- 临时文件自动过滤
- 路径前缀匹配
"""

import re
from pathlib import Path
from typing import List
import structlog

from sersync.config.models import FilterConfig

logger = structlog.get_logger()


class FileFilter:
    """文件过滤器"""

    # 默认临时文件模式（自动过滤）
    DEFAULT_TEMP_PATTERNS = [
        r'.*\.swp$',           # Vim swap files
        r'.*\.swo$',           # Vim swap files
        r'.*~$',               # Backup files
        r'.*\.tmp$',           # Temporary files
        r'.*\.temp$',          # Temporary files
        r'.*\.bak$',           # Backup files
        r'\.DS_Store$',        # macOS metadata
        r'Thumbs\.db$',        # Windows thumbnail cache
        r'desktop\.ini$',      # Windows folder settings
        r'.*\.crdownload$',    # Chrome partial downloads
        r'.*\.part$',          # Partial downloads
        r'.*\.filepart$',      # Firefox partial downloads
    ]

    def __init__(self, config: FilterConfig, enable_auto_temp_filter: bool = True):
        """
        初始化过滤器

        Args:
            config: 过滤配置
            enable_auto_temp_filter: 是否自动过滤临时文件
        """
        self.config = config
        self.enabled = config.enabled
        self.patterns: List[re.Pattern] = []

        # 编译用户定义的正则表达式
        if self.enabled:
            for pattern_str in config.patterns:
                try:
                    pattern = re.compile(pattern_str)
                    self.patterns.append(pattern)
                    logger.debug("Filter pattern compiled", pattern=pattern_str)
                except re.error as e:
                    logger.error(
                        "Invalid regex pattern",
                        pattern=pattern_str,
                        error=str(e)
                    )

        # 编译临时文件模式
        self.temp_patterns: List[re.Pattern] = []
        if enable_auto_temp_filter:
            for pattern_str in self.DEFAULT_TEMP_PATTERNS:
                self.temp_patterns.append(re.compile(pattern_str))

        logger.info(
            "File filter initialized",
            enabled=self.enabled,
            user_patterns=len(self.patterns),
            temp_patterns=len(self.temp_patterns)
        )

    def should_ignore(self, file_path: str) -> bool:
        """
        检查文件是否应该被过滤

        Args:
            file_path: 文件路径

        Returns:
            True 如果应该忽略，False 否则
        """
        # 临时文件过滤（始终启用）
        if self._is_temp_file(file_path):
            logger.debug("File filtered (temp file)", path=file_path)
            return True

        # 用户定义的过滤规则
        if self.enabled and self._matches_user_patterns(file_path):
            logger.debug("File filtered (user pattern)", path=file_path)
            return True

        return False

    def _is_temp_file(self, file_path: str) -> bool:
        """检查是否是临时文件"""
        filename = Path(file_path).name

        for pattern in self.temp_patterns:
            if pattern.match(filename):
                return True

        return False

    def _matches_user_patterns(self, file_path: str) -> bool:
        """检查是否匹配用户定义的过滤模式"""
        # 获取相对路径进行匹配
        path_str = str(file_path)

        for pattern in self.patterns:
            # 尝试匹配完整路径
            if pattern.match(path_str):
                return True

            # 尝试匹配文件名
            filename = Path(file_path).name
            if pattern.match(filename):
                return True

        return False

    def filter_files(self, file_paths: List[str]) -> List[str]:
        """
        批量过滤文件列表

        Args:
            file_paths: 文件路径列表

        Returns:
            过滤后的文件路径列表
        """
        filtered = [
            path for path in file_paths
            if not self.should_ignore(path)
        ]

        filtered_count = len(file_paths) - len(filtered)
        if filtered_count > 0:
            logger.debug(
                "Batch filter completed",
                total=len(file_paths),
                filtered=filtered_count,
                remaining=len(filtered)
            )

        return filtered

    def add_pattern(self, pattern_str: str):
        """
        动态添加过滤模式

        Args:
            pattern_str: 正则表达式字符串
        """
        try:
            pattern = re.compile(pattern_str)
            self.patterns.append(pattern)
            logger.info("Filter pattern added", pattern=pattern_str)
        except re.error as e:
            logger.error(
                "Failed to add filter pattern",
                pattern=pattern_str,
                error=str(e)
            )

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'enabled': self.enabled,
            'user_patterns': len(self.patterns),
            'temp_patterns': len(self.temp_patterns),
            'total_patterns': len(self.patterns) + len(self.temp_patterns),
        }
