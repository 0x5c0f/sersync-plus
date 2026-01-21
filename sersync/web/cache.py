"""
简单的内存缓存机制
用于缓存同步历史查询结果，提高页面响应速度
"""

import time
import hashlib
import json
from typing import Any, Optional
import structlog

logger = structlog.get_logger()


class SimpleCache:
    """简单的内存缓存"""
    
    def __init__(self, default_ttl: int = 30):
        """
        初始化缓存
        
        Args:
            default_ttl: 默认缓存时间（秒）
        """
        self.cache = {}
        self.default_ttl = default_ttl
    
    def _generate_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self.cache:
            value, expire_time = self.cache[key]
            if time.time() < expire_time:
                return value
            else:
                # 缓存过期，删除
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        if ttl is None:
            ttl = self.default_ttl
        
        expire_time = time.time() + ttl
        self.cache[key] = (value, expire_time)
    
    def delete(self, key: str) -> None:
        """删除缓存"""
        if key in self.cache:
            del self.cache[key]
    
    def clear(self) -> None:
        """清空所有缓存"""
        self.cache.clear()
    
    def cleanup_expired(self) -> int:
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = []
        
        for key, (value, expire_time) in self.cache.items():
            if current_time >= expire_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug("Cleaned up expired cache entries", count=len(expired_keys))
        
        return len(expired_keys)
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        current_time = time.time()
        total_entries = len(self.cache)
        expired_entries = sum(1 for _, expire_time in self.cache.values() if current_time >= expire_time)
        
        return {
            'total_entries': total_entries,
            'active_entries': total_entries - expired_entries,
            'expired_entries': expired_entries
        }


class CachedQuery:
    """缓存查询装饰器"""
    
    def __init__(self, cache: SimpleCache, ttl: Optional[int] = None):
        self.cache = cache
        self.ttl = ttl
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = self.cache._generate_key(func.__name__, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                logger.debug("Cache hit", function=func.__name__, key=cache_key[:8])
                return cached_result
            
            # 执行查询
            result = func(*args, **kwargs)
            
            # 存储到缓存
            self.cache.set(cache_key, result, self.ttl)
            logger.debug("Cache miss, stored result", function=func.__name__, key=cache_key[:8])
            
            return result
        
        return wrapper


# 全局缓存实例
_sync_history_cache = SimpleCache(default_ttl=30)  # 30秒缓存


def get_sync_history_cache() -> SimpleCache:
    """获取同步历史缓存实例"""
    return _sync_history_cache


def cached_sync_query(ttl: Optional[int] = None):
    """同步查询缓存装饰器"""
    return CachedQuery(_sync_history_cache, ttl)


def clear_sync_history_cache():
    """清空同步历史缓存"""
    _sync_history_cache.clear()
    logger.info("Sync history cache cleared")


def cleanup_expired_cache():
    """清理过期缓存"""
    return _sync_history_cache.cleanup_expired()