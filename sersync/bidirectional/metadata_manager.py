"""
双向同步元信息管理器

功能:
- 管理同步状态文件
- 处理节点标识和版本控制
- 提供安全的元信息存储
"""

import json
import hashlib
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()


class MetadataManager:
    """双向同步元信息管理器"""
    
    def __init__(self, watch_path: str, remote_name: str, metadata_config: Optional[Dict] = None):
        """
        初始化元信息管理器
        
        Args:
            watch_path: 监控目录路径
            remote_name: 远程目标名称
            metadata_config: 元信息配置（可选）
        """
        self.watch_path = Path(watch_path).resolve()
        self.remote_name = remote_name
        
        # 生成安全的元信息路径
        self.metadata_paths = self._generate_safe_paths(metadata_config)
        
        # 确保目录存在
        self._ensure_directories()
        
        # 节点ID
        self.node_id = self._get_or_create_node_id()
        
        logger.info(
            "Metadata manager initialized",
            watch_path=str(self.watch_path),
            remote_name=self.remote_name,
            node_id=self.node_id,
            metadata_dir=self.metadata_paths['state_dir']
        )
    
    def _generate_safe_paths(self, metadata_config: Optional[Dict] = None) -> Dict[str, str]:
        """
        生成安全的元信息路径，确保不在watch目录内
        
        Args:
            metadata_config: 用户自定义配置
            
        Returns:
            元信息路径字典
        """
        if metadata_config:
            # 验证用户配置的安全性
            for key, path in metadata_config.items():
                if path and self._is_path_inside_watch(path):
                    raise ValueError(
                        f"元信息路径 {key}='{path}' 不能在监控目录 '{self.watch_path}' 内。"
                        f"这会导致同步冲突。请使用watch目录外的路径。"
                    )
            
            return {
                'state_dir': metadata_config.get('metadata_dir', self._get_default_state_dir()),
                'conflict_dir': metadata_config.get('conflict_backup_dir', self._get_default_conflict_dir()),
                'lock_file': metadata_config.get('lock_file', self._get_default_lock_file()),
            }
        else:
            # 使用默认安全路径
            return {
                'state_dir': self._get_default_state_dir(),
                'conflict_dir': self._get_default_conflict_dir(),
                'lock_file': self._get_default_lock_file(),
            }
    
    def _is_path_inside_watch(self, path: str) -> bool:
        """检查路径是否在watch目录内"""
        try:
            path_resolved = Path(path).resolve()
            return str(path_resolved).startswith(str(self.watch_path))
        except Exception:
            return False
    
    def _get_default_state_dir(self) -> str:
        """获取默认状态目录"""
        path_hash = self._generate_path_hash()
        return f"/var/sersync/bidirectional/{path_hash}/state"
    
    def _get_default_conflict_dir(self) -> str:
        """获取默认冲突备份目录"""
        path_hash = self._generate_path_hash()
        return f"/var/sersync/bidirectional/{path_hash}/conflicts"
    
    def _get_default_lock_file(self) -> str:
        """获取默认锁文件路径"""
        path_hash = self._generate_path_hash()
        return f"/var/sersync/bidirectional/{path_hash}/sync.lock"
    
    def _generate_path_hash(self) -> str:
        """生成路径唯一标识"""
        unique_string = f"{self.watch_path}:{self.remote_name}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:8]
    
    def _ensure_directories(self):
        """确保所有必要的目录存在"""
        for path in [self.metadata_paths['state_dir'], self.metadata_paths['conflict_dir']]:
            Path(path).mkdir(parents=True, exist_ok=True)
    
    def _get_or_create_node_id(self) -> str:
        """获取或创建节点ID"""
        node_id_file = Path(self.metadata_paths['state_dir']) / 'node_id'
        
        if node_id_file.exists():
            return node_id_file.read_text().strip()
        else:
            # 生成新的节点ID
            import uuid
            node_id = f"node-{uuid.uuid4().hex[:8]}"
            node_id_file.write_text(node_id)
            return node_id
    
    def get_sync_state_file(self) -> Path:
        """获取同步状态文件路径"""
        return Path(self.metadata_paths['state_dir']) / 'sync_state.json'
    
    def load_sync_state(self) -> Dict[str, Any]:
        """
        加载同步状态
        
        Returns:
            同步状态字典
        """
        state_file = self.get_sync_state_file()
        
        if not state_file.exists():
            return self._create_initial_state()
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # 验证状态格式
            if not self._validate_state_format(state):
                logger.warning("Invalid state format, creating new state")
                return self._create_initial_state()
            
            return state
            
        except Exception as e:
            logger.error("Failed to load sync state", error=str(e))
            return self._create_initial_state()
    
    def save_sync_state(self, state: Dict[str, Any]):
        """
        保存同步状态
        
        Args:
            state: 同步状态字典
        """
        try:
            state_file = self.get_sync_state_file()
            
            # 更新时间戳和版本
            state['last_updated'] = datetime.now().isoformat()
            state['version'] = state.get('version', 0) + 1
            
            # 原子写入
            temp_file = state_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            temp_file.replace(state_file)
            
            logger.debug(
                "Sync state saved",
                version=state['version'],
                files_count=len(state.get('files', {}))
            )
            
        except Exception as e:
            logger.error("Failed to save sync state", error=str(e))
    
    def _create_initial_state(self) -> Dict[str, Any]:
        """创建初始同步状态"""
        return {
            'node_id': self.node_id,
            'version': 1,
            'created': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'files': {},
            'last_sync': None
        }
    
    def _validate_state_format(self, state: Dict[str, Any]) -> bool:
        """验证状态格式"""
        required_fields = ['node_id', 'version', 'files']
        return all(field in state for field in required_fields)
    
    def update_file_state(self, file_path: str, mtime: float, size: int, checksum: Optional[str] = None):
        """
        更新文件状态
        
        Args:
            file_path: 相对于watch目录的文件路径
            mtime: 修改时间戳
            size: 文件大小
            checksum: 文件校验和（可选）
        """
        state = self.load_sync_state()
        
        state['files'][file_path] = {
            'mtime': mtime,
            'size': size,
            'checksum': checksum,
            'last_modified_by': self.node_id,
            'updated_at': datetime.now().isoformat()
        }
        
        self.save_sync_state(state)
    
    def remove_file_state(self, file_path: str):
        """
        移除文件状态
        
        Args:
            file_path: 相对于watch目录的文件路径
        """
        state = self.load_sync_state()
        
        if file_path in state['files']:
            del state['files'][file_path]
            self.save_sync_state(state)
    
    def get_file_state(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        获取文件状态
        
        Args:
            file_path: 相对于watch目录的文件路径
            
        Returns:
            文件状态字典或None
        """
        state = self.load_sync_state()
        return state['files'].get(file_path)
    
    def create_conflict_backup(self, file_path: str, content: bytes) -> str:
        """
        创建冲突备份文件
        
        Args:
            file_path: 原文件路径
            content: 文件内容
            
        Returns:
            备份文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{Path(file_path).name}.conflict.{timestamp}.{self.node_id}"
        backup_path = Path(self.metadata_paths['conflict_dir']) / backup_name
        
        backup_path.write_bytes(content)
        
        logger.info(
            "Conflict backup created",
            original_file=file_path,
            backup_file=str(backup_path)
        )
        
        return str(backup_path)
    
    def cleanup_old_backups(self, max_backups: int = 10):
        """
        清理旧的冲突备份文件
        
        Args:
            max_backups: 保留的最大备份数量
        """
        try:
            conflict_dir = Path(self.metadata_paths['conflict_dir'])
            if not conflict_dir.exists():
                return
            
            # 获取所有备份文件，按修改时间排序
            backup_files = []
            for file_path in conflict_dir.glob('*.conflict.*'):
                backup_files.append((file_path.stat().st_mtime, file_path))
            
            backup_files.sort(reverse=True)  # 最新的在前
            
            # 删除超出数量限制的旧备份
            for _, file_path in backup_files[max_backups:]:
                file_path.unlink()
                logger.debug("Removed old conflict backup", file=str(file_path))
                
        except Exception as e:
            logger.error("Failed to cleanup old backups", error=str(e))
    
    def get_lock_file_path(self) -> str:
        """获取锁文件路径"""
        return self.metadata_paths['lock_file']
    
    def get_stats(self) -> Dict[str, Any]:
        """获取元信息统计"""
        state = self.load_sync_state()
        
        conflict_dir = Path(self.metadata_paths['conflict_dir'])
        conflict_count = len(list(conflict_dir.glob('*.conflict.*'))) if conflict_dir.exists() else 0
        
        return {
            'node_id': self.node_id,
            'version': state.get('version', 0),
            'files_tracked': len(state.get('files', {})),
            'last_updated': state.get('last_updated'),
            'conflict_backups': conflict_count,
            'metadata_dir': self.metadata_paths['state_dir'],
            'conflict_dir': self.metadata_paths['conflict_dir']
        }