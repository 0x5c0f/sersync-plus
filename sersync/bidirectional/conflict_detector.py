"""
冲突检测器

功能:
- 检测本地和远程文件的冲突
- 支持多种冲突类型检测
- 基于时间戳、文件大小、内容哈希
"""

from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib
import structlog

logger = structlog.get_logger()


class ConflictType(Enum):
    """冲突类型"""
    NO_CONFLICT = "no_conflict"  # 无冲突
    BOTH_MODIFIED = "both_modified"  # 双方都修改了
    LOCAL_DELETED_REMOTE_MODIFIED = "local_deleted_remote_modified"  # 本地删除，远程修改
    REMOTE_DELETED_LOCAL_MODIFIED = "remote_deleted_local_modified"  # 远程删除，本地修改
    BOTH_CREATED = "both_created"  # 双方都创建了
    MOVE_CONFLICT = "move_conflict"  # 移动冲突


class FileMetadata:
    """文件元数据"""

    def __init__(
        self,
        path: str,
        exists: bool = True,
        mtime: Optional[float] = None,
        size: Optional[int] = None,
        content_hash: Optional[str] = None
    ):
        """
        初始化文件元数据

        Args:
            path: 文件路径
            exists: 文件是否存在
            mtime: 修改时间戳
            size: 文件大小（字节）
            content_hash: 内容哈希值（MD5）
        """
        self.path = path
        self.exists = exists
        self.mtime = mtime
        self.size = size
        self.content_hash = content_hash

    @classmethod
    def from_local_file(cls, file_path: str) -> 'FileMetadata':
        """
        从本地文件创建元数据

        Args:
            file_path: 本地文件路径

        Returns:
            FileMetadata 实例
        """
        path = Path(file_path)

        if not path.exists():
            return cls(path=file_path, exists=False)

        # 获取文件统计信息
        stat = path.stat()

        # 计算文件哈希（仅对小文件，< 10MB）
        content_hash = None
        if stat.st_size < 10 * 1024 * 1024:  # 10MB
            try:
                with open(path, 'rb') as f:
                    content_hash = hashlib.md5(f.read()).hexdigest()
            except Exception as e:
                logger.warning("Failed to compute hash", path=file_path, error=str(e))

        return cls(
            path=file_path,
            exists=True,
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=content_hash
        )

    def __repr__(self):
        return (
            f"FileMetadata(path={self.path}, exists={self.exists}, "
            f"mtime={self.mtime}, size={self.size})"
        )


class ConflictInfo:
    """冲突信息"""

    def __init__(
        self,
        conflict_type: ConflictType,
        local_meta: FileMetadata,
        remote_meta: FileMetadata,
        base_meta: Optional[FileMetadata] = None,
        details: Optional[str] = None
    ):
        """
        初始化冲突信息

        Args:
            conflict_type: 冲突类型
            local_meta: 本地文件元数据
            remote_meta: 远程文件元数据
            base_meta: 基准版本元数据（用于三方合并）
            details: 冲突详情描述
        """
        self.conflict_type = conflict_type
        self.local_meta = local_meta
        self.remote_meta = remote_meta
        self.base_meta = base_meta
        self.details = details
        self.detected_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'conflict_type': self.conflict_type.value,
            'local_path': self.local_meta.path,
            'local_exists': self.local_meta.exists,
            'local_mtime': self.local_meta.mtime,
            'local_size': self.local_meta.size,
            'remote_exists': self.remote_meta.exists,
            'remote_mtime': self.remote_meta.mtime,
            'remote_size': self.remote_meta.size,
            'details': self.details,
            'detected_at': self.detected_at.isoformat()
        }

    def __repr__(self):
        return f"ConflictInfo(type={self.conflict_type.value}, path={self.local_meta.path})"


class ConflictDetector:
    """冲突检测器"""

    def __init__(
        self,
        time_tolerance_seconds: int = 2,
        enable_content_hash: bool = True
    ):
        """
        初始化冲突检测器

        Args:
            time_tolerance_seconds: 时间戳容差（秒），用于处理网络延迟
            enable_content_hash: 是否启用内容哈希比较
        """
        self.time_tolerance = time_tolerance_seconds
        self.enable_content_hash = enable_content_hash

        logger.info(
            "Conflict detector initialized",
            time_tolerance=time_tolerance_seconds,
            content_hash=enable_content_hash
        )

    def detect_conflict(
        self,
        local_meta: FileMetadata,
        remote_meta: FileMetadata,
        base_meta: Optional[FileMetadata] = None
    ) -> Optional[ConflictInfo]:
        """
        检测文件冲突

        Args:
            local_meta: 本地文件元数据
            remote_meta: 远程文件元数据
            base_meta: 基准版本元数据（可选，用于三方合并）

        Returns:
            ConflictInfo 如果检测到冲突，否则返回 None
        """
        # 场景 1: 双方都不存在 - 无冲突
        if not local_meta.exists and not remote_meta.exists:
            return None

        # 场景 2: 本地存在，远程不存在
        if local_meta.exists and not remote_meta.exists:
            if base_meta and base_meta.exists:
                # 远程删除了文件，但本地修改了
                return ConflictInfo(
                    conflict_type=ConflictType.REMOTE_DELETED_LOCAL_MODIFIED,
                    local_meta=local_meta,
                    remote_meta=remote_meta,
                    base_meta=base_meta,
                    details="Remote deleted but local modified"
                )
            # 本地新建，远程不存在 - 无冲突，同步到远程
            return None

        # 场景 3: 远程存在，本地不存在
        if not local_meta.exists and remote_meta.exists:
            if base_meta and base_meta.exists:
                # 本地删除了文件，但远程修改了
                return ConflictInfo(
                    conflict_type=ConflictType.LOCAL_DELETED_REMOTE_MODIFIED,
                    local_meta=local_meta,
                    remote_meta=remote_meta,
                    base_meta=base_meta,
                    details="Local deleted but remote modified"
                )
            # 远程新建，本地不存在 - 无冲突，同步到本地
            return None

        # 场景 4: 双方都存在
        # 检查是否同时创建
        if base_meta and not base_meta.exists:
            # 基准版本不存在，说明是双方同时创建
            if not self._files_identical(local_meta, remote_meta):
                return ConflictInfo(
                    conflict_type=ConflictType.BOTH_CREATED,
                    local_meta=local_meta,
                    remote_meta=remote_meta,
                    base_meta=base_meta,
                    details="Both sides created different files"
                )

        # 检查文件是否相同
        if self._files_identical(local_meta, remote_meta):
            # 文件相同 - 无冲突
            return None

        # 检查是否双方都修改了
        if base_meta and base_meta.exists:
            local_modified = not self._files_identical(local_meta, base_meta)
            remote_modified = not self._files_identical(remote_meta, base_meta)

            if local_modified and remote_modified:
                return ConflictInfo(
                    conflict_type=ConflictType.BOTH_MODIFIED,
                    local_meta=local_meta,
                    remote_meta=remote_meta,
                    base_meta=base_meta,
                    details="Both sides modified the file"
                )

        # 单方修改 - 无冲突，使用新版本
        return None

    def _files_identical(self, meta1: FileMetadata, meta2: FileMetadata) -> bool:
        """
        判断两个文件是否相同

        Args:
            meta1: 第一个文件元数据
            meta2: 第二个文件元数据

        Returns:
            True 如果文件相同
        """
        # 如果存在性不同，肯定不相同
        if meta1.exists != meta2.exists:
            return False

        # 如果都不存在，认为相同
        if not meta1.exists and not meta2.exists:
            return True

        # 检查文件大小
        if meta1.size != meta2.size:
            return False

        # 检查修改时间（带容差）
        if meta1.mtime and meta2.mtime:
            time_diff = abs(meta1.mtime - meta2.mtime)
            if time_diff > self.time_tolerance:
                # 时间不同，但如果启用了内容哈希，继续检查
                if not self.enable_content_hash:
                    return False

        # 检查内容哈希（如果可用）
        if self.enable_content_hash and meta1.content_hash and meta2.content_hash:
            return meta1.content_hash == meta2.content_hash

        # 如果没有哈希，只能根据大小和时间判断
        return True

    def batch_detect_conflicts(
        self,
        local_files: Dict[str, FileMetadata],
        remote_files: Dict[str, FileMetadata],
        base_files: Optional[Dict[str, FileMetadata]] = None
    ) -> Dict[str, ConflictInfo]:
        """
        批量检测冲突

        Args:
            local_files: 本地文件字典 {路径: 元数据}
            remote_files: 远程文件字典 {路径: 元数据}
            base_files: 基准版本文件字典（可选）

        Returns:
            冲突字典 {路径: ConflictInfo}
        """
        conflicts = {}

        # 获取所有文件路径
        all_paths = set(local_files.keys()) | set(remote_files.keys())

        for path in all_paths:
            local_meta = local_files.get(path, FileMetadata(path, exists=False))
            remote_meta = remote_files.get(path, FileMetadata(path, exists=False))
            base_meta = base_files.get(path) if base_files else None

            conflict = self.detect_conflict(local_meta, remote_meta, base_meta)
            if conflict:
                conflicts[path] = conflict

        logger.info(
            "Batch conflict detection completed",
            total_files=len(all_paths),
            conflicts_found=len(conflicts)
        )

        return conflicts
