"""
双向同步引擎

功能:
- 基于元信息的双向同步
- 冲突检测和解决
- 循环同步避免
"""

import asyncio
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import structlog

from sersync.bidirectional.metadata_manager import MetadataManager
from sersync.core.sync_engine import SyncEngine
from sersync.config.models import RemoteConfig, RsyncConfig

logger = structlog.get_logger()


class ConflictType(Enum):
    """冲突类型"""
    NO_CONFLICT = "no_conflict"
    BOTH_MODIFIED = "both_modified"
    LOCAL_DELETED_REMOTE_MODIFIED = "local_deleted_remote_modified"
    REMOTE_DELETED_LOCAL_MODIFIED = "remote_deleted_local_modified"
    BOTH_CREATED = "both_created"


class ConflictResolution(Enum):
    """冲突解决策略"""
    KEEP_NEWER = "keep_newer"
    KEEP_OLDER = "keep_older"
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"
    BACKUP_BOTH = "backup_both"


class FileChange:
    """文件变化信息"""
    
    def __init__(self, file_path: str, change_type: str, source: str):
        self.file_path = file_path
        self.change_type = change_type  # CREATE, MODIFY, DELETE
        self.source = source  # local, remote
        self.timestamp = datetime.now()


class BidirectionalSyncEngine:
    """双向同步引擎"""
    
    def __init__(
        self,
        watch_path: str,
        remote_config: RemoteConfig,
        rsync_config: RsyncConfig,
        metadata_config: Optional[Dict] = None
    ):
        """
        初始化双向同步引擎
        
        Args:
            watch_path: 监控目录
            remote_config: 远程配置
            rsync_config: Rsync配置
            metadata_config: 元信息配置
        """
        self.watch_path = Path(watch_path)
        self.remote_config = remote_config
        self.rsync_config = rsync_config
        
        # 初始化元信息管理器
        self.metadata_manager = MetadataManager(
            watch_path=str(self.watch_path),
            remote_name=remote_config.name,
            metadata_config=metadata_config
        )
        
        # 初始化单向同步引擎（用于实际的文件传输）
        self.sync_engine = SyncEngine(
            config=rsync_config,
            remotes=[remote_config],
            watch_path=str(self.watch_path),
            fail_log=None  # 双向同步有自己的错误处理
        )
        
        # 冲突解决策略
        self.conflict_strategy = ConflictResolution(remote_config.conflict_strategy)
        
        # 同步锁
        self._sync_lock = asyncio.Lock()
        
        logger.info(
            "Bidirectional sync engine initialized",
            watch_path=str(self.watch_path),
            remote=f"{remote_config.ip}::{remote_config.name}",
            node_id=self.metadata_manager.node_id,
            conflict_strategy=self.conflict_strategy.value
        )
    
    async def sync_bidirectional(self) -> Dict[str, Any]:
        """
        执行双向同步
        
        Returns:
            同步结果
        """
        async with self._sync_lock:
            try:
                logger.info("Starting bidirectional sync")
                
                # 1. 获取本地和远程状态
                local_state = self.metadata_manager.load_sync_state()
                remote_state = await self._fetch_remote_state()
                
                # 2. 检测变化和冲突
                changes = self._detect_changes(local_state, remote_state)
                conflicts = self._detect_conflicts(changes)
                
                # 3. 解决冲突
                resolved_changes = await self._resolve_conflicts(conflicts)
                
                # 4. 执行同步操作
                sync_results = await self._execute_sync_operations(resolved_changes)
                
                # 5. 更新本地状态
                await self._update_local_state(resolved_changes)
                
                # 6. 清理旧备份
                self.metadata_manager.cleanup_old_backups()
                
                result = {
                    'success': True,
                    'changes_detected': len(changes),
                    'conflicts_resolved': len(conflicts),
                    'files_synced': sync_results.get('files_synced', 0),
                    'sync_results': sync_results
                }
                
                logger.info(
                    "Bidirectional sync completed",
                    **{k: v for k, v in result.items() if k != 'sync_results'}
                )
                
                return result
                
            except Exception as e:
                logger.error("Bidirectional sync failed", error=str(e), exc_info=True)
                return {
                    'success': False,
                    'error': str(e),
                    'changes_detected': 0,
                    'conflicts_resolved': 0,
                    'files_synced': 0
                }
    
    async def _fetch_remote_state(self) -> Dict[str, Any]:
        """
        获取远程同步状态
        
        Returns:
            远程状态字典
        """
        try:
            # 通过rsync获取远程元信息文件
            remote_state_path = self.metadata_manager.get_sync_state_file().with_suffix('.remote')
            
            # 构建rsync命令获取远程状态文件
            cmd = self._build_fetch_remote_state_cmd(str(remote_state_path))
            
            # 执行命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and remote_state_path.exists():
                # 成功获取远程状态
                import json
                with open(remote_state_path, 'r', encoding='utf-8') as f:
                    remote_state = json.load(f)
                
                # 清理临时文件
                remote_state_path.unlink()
                
                return remote_state
            else:
                # 远程状态不存在或获取失败，返回空状态
                logger.debug("Remote state not found or fetch failed", stderr=stderr.decode())
                return self._create_empty_remote_state()
                
        except Exception as e:
            logger.error("Failed to fetch remote state", error=str(e))
            return self._create_empty_remote_state()
    
    def _build_fetch_remote_state_cmd(self, local_path: str) -> List[str]:
        """构建获取远程状态的rsync命令"""
        cmd = ['rsync']
        
        # 添加基本参数
        cmd.extend(['-v'])  # 详细输出
        
        # 认证配置
        if self.rsync_config.auth_enabled and self.rsync_config.auth_passwordfile:
            cmd.append(f'--password-file={self.rsync_config.auth_passwordfile}')
        
        # SSH配置
        if self.rsync_config.ssh_enabled:
            cmd.extend(['-e', 'ssh'])
        
        # 构建远程路径 - 获取远程的元信息文件
        # 注意：这里需要特殊处理，因为元信息文件不在watch目录内
        # 我们需要通过特殊的方式获取远程节点的状态文件
        
        # 临时方案：通过约定的路径获取
        remote_metadata_path = f"/var/sersync/bidirectional/{self._get_path_hash()}/state/sync_state.json"
        
        if self.rsync_config.ssh_enabled:
            remote_source = f"{self.remote_config.ip}:{remote_metadata_path}"
        else:
            user_prefix = f'{self.rsync_config.auth_users}@' if self.rsync_config.auth_users else ''
            remote_source = f"{user_prefix}{self.remote_config.ip}::{self.remote_config.name}_metadata/sync_state.json"
        
        cmd.extend([remote_source, local_path])
        
        return cmd
    
    def _get_path_hash(self) -> str:
        """获取路径哈希（与MetadataManager保持一致）"""
        unique_string = f"{self.watch_path}:{self.remote_config.name}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:8]
    
    def _create_empty_remote_state(self) -> Dict[str, Any]:
        """创建空的远程状态"""
        return {
            'node_id': 'unknown',
            'version': 0,
            'files': {},
            'last_updated': None
        }
    
    def _detect_changes(self, local_state: Dict[str, Any], remote_state: Dict[str, Any]) -> List[FileChange]:
        """
        检测本地和远程的变化
        
        Args:
            local_state: 本地状态
            remote_state: 远程状态
            
        Returns:
            变化列表
        """
        changes = []
        
        local_files = local_state.get('files', {})
        remote_files = remote_state.get('files', {})
        
        # 检查所有文件（本地和远程的并集）
        all_files = set(local_files.keys()) | set(remote_files.keys())
        
        for file_path in all_files:
            local_info = local_files.get(file_path)
            remote_info = remote_files.get(file_path)
            
            # 检查本地文件实际状态
            actual_file_path = self.watch_path / file_path
            file_exists = actual_file_path.exists()
            
            if local_info and remote_info:
                # 文件在两边都存在，检查是否有变化
                if self._is_file_modified(local_info, remote_info):
                    # 检查哪一边更新
                    local_mtime = local_info.get('mtime', 0)
                    remote_mtime = remote_info.get('mtime', 0)
                    
                    if local_mtime > remote_mtime:
                        changes.append(FileChange(file_path, 'MODIFY', 'local'))
                    elif remote_mtime > local_mtime:
                        changes.append(FileChange(file_path, 'MODIFY', 'remote'))
                    
            elif local_info and not remote_info:
                # 文件只在本地存在
                if file_exists:
                    changes.append(FileChange(file_path, 'CREATE', 'local'))
                else:
                    # 本地文件已删除，但状态未更新
                    changes.append(FileChange(file_path, 'DELETE', 'local'))
                    
            elif not local_info and remote_info:
                # 文件只在远程存在
                changes.append(FileChange(file_path, 'CREATE', 'remote'))
        
        return changes
    
    def _is_file_modified(self, local_info: Dict, remote_info: Dict) -> bool:
        """检查文件是否被修改"""
        # 比较修改时间和大小
        local_mtime = local_info.get('mtime', 0)
        remote_mtime = remote_info.get('mtime', 0)
        local_size = local_info.get('size', 0)
        remote_size = remote_info.get('size', 0)
        
        return local_mtime != remote_mtime or local_size != remote_size
    
    def _detect_conflicts(self, changes: List[FileChange]) -> List[Tuple[FileChange, FileChange, ConflictType]]:
        """
        检测冲突
        
        Args:
            changes: 变化列表
            
        Returns:
            冲突列表，每个元素是 (local_change, remote_change, conflict_type)
        """
        conflicts = []
        
        # 按文件路径分组变化
        changes_by_file = {}
        for change in changes:
            if change.file_path not in changes_by_file:
                changes_by_file[change.file_path] = []
            changes_by_file[change.file_path].append(change)
        
        # 检测每个文件的冲突
        for file_path, file_changes in changes_by_file.items():
            if len(file_changes) > 1:
                # 有多个变化，可能存在冲突
                local_changes = [c for c in file_changes if c.source == 'local']
                remote_changes = [c for c in file_changes if c.source == 'remote']
                
                if local_changes and remote_changes:
                    local_change = local_changes[0]
                    remote_change = remote_changes[0]
                    
                    # 确定冲突类型
                    conflict_type = self._determine_conflict_type(local_change, remote_change)
                    
                    if conflict_type != ConflictType.NO_CONFLICT:
                        conflicts.append((local_change, remote_change, conflict_type))
        
        return conflicts
    
    def _determine_conflict_type(self, local_change: FileChange, remote_change: FileChange) -> ConflictType:
        """确定冲突类型"""
        if local_change.change_type == 'MODIFY' and remote_change.change_type == 'MODIFY':
            return ConflictType.BOTH_MODIFIED
        elif local_change.change_type == 'DELETE' and remote_change.change_type == 'MODIFY':
            return ConflictType.LOCAL_DELETED_REMOTE_MODIFIED
        elif local_change.change_type == 'MODIFY' and remote_change.change_type == 'DELETE':
            return ConflictType.REMOTE_DELETED_LOCAL_MODIFIED
        elif local_change.change_type == 'CREATE' and remote_change.change_type == 'CREATE':
            return ConflictType.BOTH_CREATED
        else:
            return ConflictType.NO_CONFLICT
    
    async def _resolve_conflicts(self, conflicts: List[Tuple[FileChange, FileChange, ConflictType]]) -> List[FileChange]:
        """
        解决冲突
        
        Args:
            conflicts: 冲突列表
            
        Returns:
            解决后的变化列表
        """
        resolved_changes = []
        
        for local_change, remote_change, conflict_type in conflicts:
            try:
                resolution = await self._resolve_single_conflict(
                    local_change, remote_change, conflict_type
                )
                
                if resolution:
                    resolved_changes.extend(resolution)
                    
                logger.info(
                    "Conflict resolved",
                    file=local_change.file_path,
                    conflict_type=conflict_type.value,
                    strategy=self.conflict_strategy.value
                )
                
            except Exception as e:
                logger.error(
                    "Failed to resolve conflict",
                    file=local_change.file_path,
                    error=str(e)
                )
        
        return resolved_changes
    
    async def _resolve_single_conflict(
        self,
        local_change: FileChange,
        remote_change: FileChange,
        conflict_type: ConflictType
    ) -> Optional[List[FileChange]]:
        """解决单个冲突"""
        
        if self.conflict_strategy == ConflictResolution.KEEP_NEWER:
            return await self._resolve_keep_newer(local_change, remote_change)
        elif self.conflict_strategy == ConflictResolution.KEEP_OLDER:
            return await self._resolve_keep_older(local_change, remote_change)
        elif self.conflict_strategy == ConflictResolution.KEEP_LOCAL:
            return [local_change]
        elif self.conflict_strategy == ConflictResolution.KEEP_REMOTE:
            return [remote_change]
        elif self.conflict_strategy == ConflictResolution.BACKUP_BOTH:
            return await self._resolve_backup_both(local_change, remote_change)
        else:
            logger.warning(f"Unknown conflict strategy: {self.conflict_strategy}")
            return [local_change]  # 默认保留本地
    
    async def _resolve_keep_newer(self, local_change: FileChange, remote_change: FileChange) -> List[FileChange]:
        """保留较新的文件"""
        # 这里需要比较文件的实际修改时间
        # 简化实现：比较变化的时间戳
        if local_change.timestamp > remote_change.timestamp:
            return [local_change]
        else:
            return [remote_change]
    
    async def _resolve_keep_older(self, local_change: FileChange, remote_change: FileChange) -> List[FileChange]:
        """保留较旧的文件"""
        if local_change.timestamp < remote_change.timestamp:
            return [local_change]
        else:
            return [remote_change]
    
    async def _resolve_backup_both(self, local_change: FileChange, remote_change: FileChange) -> List[FileChange]:
        """备份双方文件"""
        # 创建冲突备份
        file_path = self.watch_path / local_change.file_path
        if file_path.exists():
            content = file_path.read_bytes()
            self.metadata_manager.create_conflict_backup(local_change.file_path, content)
        
        # 保留远程版本
        return [remote_change]
    
    async def _execute_sync_operations(self, changes: List[FileChange]) -> Dict[str, Any]:
        """
        执行同步操作
        
        Args:
            changes: 要同步的变化列表
            
        Returns:
            同步结果
        """
        results = {
            'files_synced': 0,
            'files_failed': 0,
            'operations': []
        }
        
        for change in changes:
            try:
                if change.source == 'local':
                    # 本地变化，同步到远程
                    result = await self._sync_local_to_remote(change)
                else:
                    # 远程变化，同步到本地
                    result = await self._sync_remote_to_local(change)
                
                if result['success']:
                    results['files_synced'] += 1
                else:
                    results['files_failed'] += 1
                
                results['operations'].append(result)
                
            except Exception as e:
                logger.error(
                    "Sync operation failed",
                    file=change.file_path,
                    source=change.source,
                    error=str(e)
                )
                results['files_failed'] += 1
        
        return results
    
    async def _sync_local_to_remote(self, change: FileChange) -> Dict[str, Any]:
        """同步本地变化到远程"""
        file_path = change.file_path
        
        # 使用现有的sync_engine进行同步
        result = await self.sync_engine.sync_file(file_path, change.change_type)
        
        return {
            'file': file_path,
            'direction': 'local_to_remote',
            'operation': change.change_type,
            'success': result['all_success'],
            'details': result
        }
    
    async def _sync_remote_to_local(self, change: FileChange) -> Dict[str, Any]:
        """同步远程变化到本地"""
        # 这里需要实现从远程拉取文件的逻辑
        # 可以使用rsync的拉取模式
        
        file_path = change.file_path
        local_file_path = self.watch_path / file_path
        
        try:
            # 构建rsync拉取命令
            cmd = self._build_pull_command(file_path)
            
            # 执行命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            success = process.returncode == 0
            
            return {
                'file': file_path,
                'direction': 'remote_to_local',
                'operation': change.change_type,
                'success': success,
                'stdout': stdout.decode(),
                'stderr': stderr.decode()
            }
            
        except Exception as e:
            return {
                'file': file_path,
                'direction': 'remote_to_local',
                'operation': change.change_type,
                'success': False,
                'error': str(e)
            }
    
    def _build_pull_command(self, file_path: str) -> List[str]:
        """构建从远程拉取文件的rsync命令"""
        cmd = ['rsync']
        
        # 基本参数
        cmd.extend(['-avz'])
        
        # 认证
        if self.rsync_config.auth_enabled and self.rsync_config.auth_passwordfile:
            cmd.append(f'--password-file={self.rsync_config.auth_passwordfile}')
        
        # SSH
        if self.rsync_config.ssh_enabled:
            cmd.extend(['-e', 'ssh'])
        
        # 构建远程源路径和本地目标路径
        if self.rsync_config.ssh_enabled:
            remote_source = f"{self.remote_config.ip}:{self.remote_config.name}/{file_path}"
        else:
            user_prefix = f'{self.rsync_config.auth_users}@' if self.rsync_config.auth_users else ''
            remote_source = f"{user_prefix}{self.remote_config.ip}::{self.remote_config.name}/{file_path}"
        
        local_target = str(self.watch_path / file_path)
        
        cmd.extend([remote_source, local_target])
        
        return cmd
    
    async def _update_local_state(self, changes: List[FileChange]):
        """更新本地状态"""
        for change in changes:
            file_path = change.file_path
            actual_file_path = self.watch_path / file_path
            
            if actual_file_path.exists():
                # 文件存在，更新状态
                stat = actual_file_path.stat()
                self.metadata_manager.update_file_state(
                    file_path=file_path,
                    mtime=stat.st_mtime,
                    size=stat.st_size
                )
            else:
                # 文件不存在，移除状态
                self.metadata_manager.remove_file_state(file_path)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取同步统计信息"""
        return {
            'metadata_stats': self.metadata_manager.get_stats(),
            'conflict_strategy': self.conflict_strategy.value,
            'sync_interval': self.remote_config.sync_interval
        }