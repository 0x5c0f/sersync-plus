"""
冲突解决器

功能:
- 提供多种冲突解决策略
- 自动解决或提示手动介入
- 支持备份冲突文件
"""

from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import shutil
import structlog

from sersync.bidirectional.conflict_detector import ConflictInfo, ConflictType, FileMetadata

logger = structlog.get_logger()


class ResolutionStrategy(Enum):
    """冲突解决策略"""
    KEEP_NEWER = "keep_newer"  # 保留较新的文件（基于时间戳）
    KEEP_OLDER = "keep_older"  # 保留较旧的文件
    KEEP_LARGER = "keep_larger"  # 保留较大的文件
    KEEP_LOCAL = "keep_local"  # 总是保留本地版本
    KEEP_REMOTE = "keep_remote"  # 总是保留远程版本
    BACKUP_BOTH = "backup_both"  # 备份双方，保留两个版本
    MANUAL = "manual"  # 需要手动介入
    SKIP = "skip"  # 跳过同步


class ResolutionResult:
    """解决结果"""

    def __init__(
        self,
        success: bool,
        strategy_used: ResolutionStrategy,
        action_taken: str,
        backup_paths: Optional[Dict[str, str]] = None,
        error_message: Optional[str] = None
    ):
        """
        初始化解决结果

        Args:
            success: 是否成功解决
            strategy_used: 使用的策略
            action_taken: 采取的行动描述
            backup_paths: 备份文件路径字典 {"local": path, "remote": path}
            error_message: 错误消息（如果失败）
        """
        self.success = success
        self.strategy_used = strategy_used
        self.action_taken = action_taken
        self.backup_paths = backup_paths or {}
        self.error_message = error_message
        self.resolved_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'success': self.success,
            'strategy_used': self.strategy_used.value,
            'action_taken': self.action_taken,
            'backup_paths': self.backup_paths,
            'error_message': self.error_message,
            'resolved_at': self.resolved_at.isoformat()
        }

    def __repr__(self):
        return f"ResolutionResult(success={self.success}, strategy={self.strategy_used.value})"


class ConflictResolver:
    """冲突解决器"""

    def __init__(
        self,
        default_strategy: ResolutionStrategy = ResolutionStrategy.KEEP_NEWER,
        backup_dir: Optional[str] = None,
        enable_backup: bool = True,
        manual_callback: Optional[Callable] = None
    ):
        """
        初始化冲突解决器

        Args:
            default_strategy: 默认解决策略
            backup_dir: 备份目录路径
            enable_backup: 是否启用备份
            manual_callback: 手动解决回调函数 (conflict_info) -> ResolutionStrategy
        """
        self.default_strategy = default_strategy
        self.backup_dir = Path(backup_dir) if backup_dir else Path("/var/sersync/conflicts")
        self.enable_backup = enable_backup
        self.manual_callback = manual_callback

        # 创建备份目录
        if self.enable_backup:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Conflict resolver initialized",
            default_strategy=default_strategy.value,
            backup_dir=str(self.backup_dir),
            enable_backup=enable_backup
        )

    def resolve(
        self,
        conflict: ConflictInfo,
        strategy: Optional[ResolutionStrategy] = None
    ) -> ResolutionResult:
        """
        解决冲突

        Args:
            conflict: 冲突信息
            strategy: 解决策略（如果为 None，使用默认策略）

        Returns:
            ResolutionResult
        """
        strategy = strategy or self.default_strategy

        logger.info(
            "Resolving conflict",
            conflict_type=conflict.conflict_type.value,
            path=conflict.local_meta.path,
            strategy=strategy.value
        )

        try:
            # 根据策略选择解决方法
            if strategy == ResolutionStrategy.KEEP_NEWER:
                return self._resolve_keep_newer(conflict)
            elif strategy == ResolutionStrategy.KEEP_OLDER:
                return self._resolve_keep_older(conflict)
            elif strategy == ResolutionStrategy.KEEP_LARGER:
                return self._resolve_keep_larger(conflict)
            elif strategy == ResolutionStrategy.KEEP_LOCAL:
                return self._resolve_keep_local(conflict)
            elif strategy == ResolutionStrategy.KEEP_REMOTE:
                return self._resolve_keep_remote(conflict)
            elif strategy == ResolutionStrategy.BACKUP_BOTH:
                return self._resolve_backup_both(conflict)
            elif strategy == ResolutionStrategy.MANUAL:
                return self._resolve_manual(conflict)
            elif strategy == ResolutionStrategy.SKIP:
                return self._resolve_skip(conflict)
            else:
                raise ValueError(f"Unknown strategy: {strategy}")

        except Exception as e:
            logger.error("Failed to resolve conflict", error=str(e), exc_info=True)
            return ResolutionResult(
                success=False,
                strategy_used=strategy,
                action_taken="Error occurred",
                error_message=str(e)
            )

    def _resolve_keep_newer(self, conflict: ConflictInfo) -> ResolutionResult:
        """保留较新的文件"""
        local_meta = conflict.local_meta
        remote_meta = conflict.remote_meta

        # 比较时间戳
        if not local_meta.exists:
            # 本地不存在，使用远程
            return ResolutionResult(
                success=True,
                strategy_used=ResolutionStrategy.KEEP_NEWER,
                action_taken="Use remote (local deleted)"
            )

        if not remote_meta.exists:
            # 远程不存在，使用本地
            return ResolutionResult(
                success=True,
                strategy_used=ResolutionStrategy.KEEP_NEWER,
                action_taken="Use local (remote deleted)"
            )

        # 比较修改时间
        if local_meta.mtime and remote_meta.mtime:
            if local_meta.mtime > remote_meta.mtime:
                # 本地较新
                backup_path = self._backup_file(remote_meta, "remote") if self.enable_backup else None
                return ResolutionResult(
                    success=True,
                    strategy_used=ResolutionStrategy.KEEP_NEWER,
                    action_taken="Use local (newer)",
                    backup_paths={"remote": backup_path} if backup_path else {}
                )
            else:
                # 远程较新
                backup_path = self._backup_file(local_meta, "local") if self.enable_backup else None
                return ResolutionResult(
                    success=True,
                    strategy_used=ResolutionStrategy.KEEP_NEWER,
                    action_taken="Use remote (newer)",
                    backup_paths={"local": backup_path} if backup_path else {}
                )

        # 无法判断，默认使用本地
        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.KEEP_NEWER,
            action_taken="Use local (default)"
        )

    def _resolve_keep_older(self, conflict: ConflictInfo) -> ResolutionResult:
        """保留较旧的文件"""
        local_meta = conflict.local_meta
        remote_meta = conflict.remote_meta

        if local_meta.mtime and remote_meta.mtime:
            if local_meta.mtime < remote_meta.mtime:
                # 本地较旧
                return ResolutionResult(
                    success=True,
                    strategy_used=ResolutionStrategy.KEEP_OLDER,
                    action_taken="Use local (older)"
                )
            else:
                # 远程较旧
                return ResolutionResult(
                    success=True,
                    strategy_used=ResolutionStrategy.KEEP_OLDER,
                    action_taken="Use remote (older)"
                )

        # 无法判断，默认使用本地
        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.KEEP_OLDER,
            action_taken="Use local (default)"
        )

    def _resolve_keep_larger(self, conflict: ConflictInfo) -> ResolutionResult:
        """保留较大的文件"""
        local_meta = conflict.local_meta
        remote_meta = conflict.remote_meta

        if local_meta.size and remote_meta.size:
            if local_meta.size > remote_meta.size:
                # 本地较大
                return ResolutionResult(
                    success=True,
                    strategy_used=ResolutionStrategy.KEEP_LARGER,
                    action_taken=f"Use local (larger: {local_meta.size} bytes)"
                )
            else:
                # 远程较大
                return ResolutionResult(
                    success=True,
                    strategy_used=ResolutionStrategy.KEEP_LARGER,
                    action_taken=f"Use remote (larger: {remote_meta.size} bytes)"
                )

        # 无法判断，默认使用本地
        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.KEEP_LARGER,
            action_taken="Use local (default)"
        )

    def _resolve_keep_local(self, conflict: ConflictInfo) -> ResolutionResult:
        """总是保留本地版本"""
        backup_path = None
        if self.enable_backup and conflict.remote_meta.exists:
            backup_path = self._backup_file(conflict.remote_meta, "remote")

        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.KEEP_LOCAL,
            action_taken="Use local (policy)",
            backup_paths={"remote": backup_path} if backup_path else {}
        )

    def _resolve_keep_remote(self, conflict: ConflictInfo) -> ResolutionResult:
        """总是保留远程版本"""
        backup_path = None
        if self.enable_backup and conflict.local_meta.exists:
            backup_path = self._backup_file(conflict.local_meta, "local")

        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.KEEP_REMOTE,
            action_taken="Use remote (policy)",
            backup_paths={"local": backup_path} if backup_path else {}
        )

    def _resolve_backup_both(self, conflict: ConflictInfo) -> ResolutionResult:
        """备份双方，保留两个版本"""
        backup_paths = {}

        # 备份本地文件
        if conflict.local_meta.exists:
            local_backup = self._backup_file(conflict.local_meta, "local")
            if local_backup:
                backup_paths["local"] = local_backup

        # 备份远程文件
        if conflict.remote_meta.exists:
            remote_backup = self._backup_file(conflict.remote_meta, "remote")
            if remote_backup:
                backup_paths["remote"] = remote_backup

        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.BACKUP_BOTH,
            action_taken=f"Backed up both versions to {self.backup_dir}",
            backup_paths=backup_paths
        )

    def _resolve_manual(self, conflict: ConflictInfo) -> ResolutionResult:
        """需要手动介入"""
        if self.manual_callback:
            try:
                # 调用手动解决回调
                chosen_strategy = self.manual_callback(conflict)
                if chosen_strategy != ResolutionStrategy.MANUAL:
                    # 使用回调返回的策略重新解决
                    return self.resolve(conflict, chosen_strategy)
            except Exception as e:
                logger.error("Manual callback failed", error=str(e))

        # 备份双方，等待手动处理
        return self._resolve_backup_both(conflict)

    def _resolve_skip(self, conflict: ConflictInfo) -> ResolutionResult:
        """跳过同步"""
        return ResolutionResult(
            success=True,
            strategy_used=ResolutionStrategy.SKIP,
            action_taken="Skipped synchronization"
        )

    def _backup_file(self, file_meta: FileMetadata, source: str) -> Optional[str]:
        """
        备份文件

        Args:
            file_meta: 文件元数据
            source: 来源标识 ("local" 或 "remote")

        Returns:
            备份文件路径，失败返回 None
        """
        if not file_meta.exists:
            return None

        try:
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = Path(file_meta.path)
            backup_name = f"{file_path.stem}_{source}_{timestamp}{file_path.suffix}"
            backup_path = self.backup_dir / backup_name

            # 复制文件
            shutil.copy2(file_path, backup_path)

            logger.info(
                "File backed up",
                source_path=file_meta.path,
                backup_path=str(backup_path)
            )

            return str(backup_path)

        except Exception as e:
            logger.error(
                "Failed to backup file",
                path=file_meta.path,
                error=str(e)
            )
            return None

    def batch_resolve(
        self,
        conflicts: Dict[str, ConflictInfo],
        strategy: Optional[ResolutionStrategy] = None
    ) -> Dict[str, ResolutionResult]:
        """
        批量解决冲突

        Args:
            conflicts: 冲突字典 {路径: ConflictInfo}
            strategy: 解决策略（如果为 None，使用默认策略）

        Returns:
            解决结果字典 {路径: ResolutionResult}
        """
        results = {}

        for path, conflict in conflicts.items():
            result = self.resolve(conflict, strategy)
            results[path] = result

        logger.info(
            "Batch conflict resolution completed",
            total_conflicts=len(conflicts),
            successful=sum(1 for r in results.values() if r.success),
            failed=sum(1 for r in results.values() if not r.success)
        )

        return results
