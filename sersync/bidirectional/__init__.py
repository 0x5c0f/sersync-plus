"""
双向同步模块

功能:
- 冲突检测
- 冲突解决
- Unison 集成
- 双向事件协调
"""

from sersync.bidirectional.conflict_detector import ConflictDetector, ConflictType, FileMetadata
from sersync.bidirectional.conflict_resolver import ConflictResolver, ResolutionStrategy
from sersync.bidirectional.unison_engine import UnisonEngine, UnisonProfile
from sersync.bidirectional.coordinator import BidirectionalCoordinator, SyncEvent

__all__ = [
    'ConflictDetector',
    'ConflictType',
    'FileMetadata',
    'ConflictResolver',
    'ResolutionStrategy',
    'UnisonEngine',
    'UnisonProfile',
    'BidirectionalCoordinator',
    'SyncEvent',
]
