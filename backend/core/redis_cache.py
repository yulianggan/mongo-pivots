"""
Redis缓存管理器
提供智能缓存键生成、TTL管理和缓存操作接口
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union, List
import redis
from redis.connection import ConnectionPool


logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """缓存配置类"""
    redis_url: str = "redis://localhost:6379/0"
    default_ttl_hours: int = 72  # 默认TTL为72小时
    key_prefix: str = "mongo_pivot"
    connection_pool_size: int = 10
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30  # 健康检查间隔（秒）
    
    @classmethod
    def from_env(cls) -> 'CacheConfig':
        """从环境变量创建配置"""
        import os
        return cls(
            redis_url=os.getenv('REDIS_URL', cls.redis_url),
            default_ttl_hours=int(os.getenv('REDIS_DEFAULT_TTL_HOURS', cls.default_ttl_hours)),
            key_prefix=os.getenv('REDIS_KEY_PREFIX', cls.key_prefix),
            connection_pool_size=int(os.getenv('REDIS_POOL_SIZE', cls.connection_pool_size)),
            socket_timeout=float(os.getenv('REDIS_SOCKET_TIMEOUT', cls.socket_timeout)),
            socket_connect_timeout=float(os.getenv('REDIS_CONNECT_TIMEOUT', cls.socket_connect_timeout)),
            health_check_interval=int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', cls.health_check_interval))
        )


class CacheKey:
    """缓存键管理类"""
    
    def __init__(self, prefix: str = "mongo_pivot"):
        self.prefix = prefix
    
    def generate_hash(self, data: Dict[str, Any]) -> str:
        """生成配置数据的MD5哈希"""
        # 创建一个确定性的JSON字符串
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.md5(json_str.encode('utf-8')).hexdigest()
    
    def create_key(self, config_hash: str, timestamp: Optional[int] = None) -> str:
        """创建缓存键
        
        格式: mongo_pivot:{hash}:{timestamp}
        """
        if timestamp is None:
            timestamp = int(time.time())
        return f"{self.prefix}:{config_hash}:{timestamp}"
    
    def parse_key(self, key: str) -> Dict[str, str]:
        """解析缓存键"""
        try:
            parts = key.split(':')
            if len(parts) >= 3:
                return {
                    'prefix': parts[0],
                    'hash': parts[1], 
                    'timestamp': parts[2]
                }
            else:
                raise ValueError(f"Invalid key format: {key}")
        except Exception as e:
            logger.error(f"Failed to parse cache key {key}: {e}")
            raise
    
    def get_pattern(self, config_hash: Optional[str] = None) -> str:
        """获取键匹配模式"""
        if config_hash:
            return f"{self.prefix}:{config_hash}:*"
        return f"{self.prefix}:*"


class CacheManager:
    """Redis缓存管理器核心类"""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig.from_env()
        self.key_manager = CacheKey(self.config.key_prefix)
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._last_health_check = 0
        self._is_healthy = False
        
    def _get_client(self) -> redis.Redis:
        """获取Redis客户端连接"""
        if self._client is None or not self._is_connection_healthy():
            self._initialize_connection()
        return self._client
    
    def _initialize_connection(self):
        """初始化Redis连接"""
        try:
            # 创建连接池
            self._pool = redis.ConnectionPool.from_url(
                self.config.redis_url,
                max_connections=self.config.connection_pool_size,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout
            )
            
            # 创建客户端
            self._client = redis.Redis(connection_pool=self._pool)
            
            # 测试连接
            self._client.ping()
            self._is_healthy = True
            self._last_health_check = time.time()
            
            logger.info("Redis connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            self._is_healthy = False
            self._client = None
            self._pool = None
            raise
    
    def _is_connection_healthy(self) -> bool:
        """检查连接健康状态"""
        now = time.time()
        if now - self._last_health_check > self.config.health_check_interval:
            try:
                if self._client:
                    self._client.ping()
                    self._is_healthy = True
                else:
                    self._is_healthy = False
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                self._is_healthy = False
            finally:
                self._last_health_check = now
        
        return self._is_healthy
    
    def is_available(self) -> bool:
        """检查Redis是否可用"""
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis is not available: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            client = self._get_client()
            value = client.get(key)
            if value is None:
                logger.debug(f"Cache miss for key: {key}")
                return None
            
            # 尝试解析JSON
            try:
                result = json.loads(value.decode('utf-8'))
                logger.debug(f"Cache hit for key: {key}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode cached value for key {key}: {e}")
                # 删除损坏的缓存条目
                self.delete(key)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get cache value for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl_hours: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            client = self._get_client()
            
            # 序列化值
            json_value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            
            # 计算TTL
            ttl_seconds = (ttl_hours or self.config.default_ttl_hours) * 3600
            
            # 设置缓存
            result = client.setex(key, ttl_seconds, json_value)
            
            if result:
                logger.debug(f"Cache set for key: {key} (TTL: {ttl_hours or self.config.default_ttl_hours}h)")
            else:
                logger.warning(f"Failed to set cache for key: {key}")
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to set cache value for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存条目"""
        try:
            client = self._get_client()
            result = client.delete(key)
            
            if result > 0:
                logger.debug(f"Cache deleted for key: {key}")
                return True
            else:
                logger.debug(f"Cache key not found: {key}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """按模式清除缓存条目"""
        try:
            client = self._get_client()
            
            # 获取匹配的键
            keys = client.keys(pattern)
            if not keys:
                logger.debug(f"No keys found for pattern: {pattern}")
                return 0
            
            # 删除键
            result = client.delete(*keys)
            logger.info(f"Cleared {result} cache entries for pattern: {pattern}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to clear cache for pattern {pattern}: {e}")
            return 0
    
    def clear_all(self) -> int:
        """清除所有相关缓存"""
        pattern = self.key_manager.get_pattern()
        return self.clear_pattern(pattern)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            client = self._get_client()
            info = client.info()
            
            # 获取我们的键数量
            pattern = self.key_manager.get_pattern()
            our_keys = client.keys(pattern)
            
            return {
                'redis_version': info.get('redis_version'),
                'connected_clients': info.get('connected_clients'),
                'used_memory_human': info.get('used_memory_human'),
                'total_keys': info.get('db0', {}).get('keys', 0) if 'db0' in info else 0,
                'our_keys_count': len(our_keys),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'is_healthy': self._is_healthy,
                'last_health_check': datetime.fromtimestamp(self._last_health_check).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {
                'error': str(e),
                'is_healthy': False
            }
    
    def get_cache_by_config(self, config_data: Dict[str, Any]) -> Optional[Any]:
        """根据配置数据获取缓存"""
        config_hash = self.key_manager.generate_hash(config_data)
        pattern = self.key_manager.get_pattern(config_hash)
        
        try:
            client = self._get_client()
            keys = client.keys(pattern)
            
            if not keys:
                return None
            
            # 获取最新的缓存条目（按时间戳排序）
            latest_key = max(keys, key=lambda k: int(self.key_manager.parse_key(k.decode())['timestamp']))
            return self.get(latest_key.decode())
            
        except Exception as e:
            logger.error(f"Failed to get cache by config: {e}")
            return None
    
    def set_cache_by_config(self, config_data: Dict[str, Any], value: Any, ttl_hours: Optional[int] = None) -> Optional[str]:
        """根据配置数据设置缓存"""
        config_hash = self.key_manager.generate_hash(config_data)
        cache_key = self.key_manager.create_key(config_hash)
        
        if self.set(cache_key, value, ttl_hours):
            return cache_key
        return None
    
    def get_bulk(self, key: str) -> Optional[List[Any]]:
        """批量获取缓存值（用于分块处理）"""
        return self.get(key)
    
    def set_bulk(self, key: str, values: List[Any], ttl: int) -> bool:
        """批量设置缓存值（用于分块处理）"""
        ttl_hours = ttl // 3600
        return self.set(key, values, ttl_hours or 1)
    
    def delete_pattern(self, pattern: str) -> int:
        """按模式删除缓存条目"""
        return self.clear_pattern(pattern)
    
    def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """按模式获取所有键"""
        try:
            client = self._get_client()
            keys = client.keys(pattern)
            return [key.decode() for key in keys]
        except Exception as e:
            logger.error(f"Failed to get keys by pattern {pattern}: {e}")
            return []
    
    def cleanup_expired(self) -> int:
        """清理过期的缓存条目（Redis会自动处理TTL，这里主要用于统计）"""
        try:
            client = self._get_client()
            pattern = self.key_manager.get_pattern()
            keys = client.keys(pattern)
            
            expired_count = 0
            for key in keys:
                ttl = client.ttl(key)
                if ttl == -2:  # 键不存在
                    expired_count += 1
            
            logger.info(f"Found {expired_count} expired cache entries")
            return expired_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired cache: {e}")
            return 0
    
    def close(self):
        """关闭连接"""
        try:
            if self._client:
                self._client.close()
            if self._pool:
                self._pool.disconnect()
            logger.info("Redis connections closed")
        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")
        finally:
            self._client = None
            self._pool = None
            self._is_healthy = False


# 全局缓存实例（按需创建）
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def is_cache_available() -> bool:
    """检查缓存是否可用"""
    try:
        cache = get_cache_manager()
        return cache.is_available()
    except Exception:
        return False


# 全局缓存管理器实例
cache_manager = get_cache_manager()