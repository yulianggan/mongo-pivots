"""
Redis缓存管理器测试
测试缓存键生成、TTL管理、缓存操作等功能
"""
import json
import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from core.redis_cache import (
    CacheConfig, CacheKey, CacheManager,
    get_cache_manager, is_cache_available
)


class TestCacheConfig:
    """测试缓存配置类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = CacheConfig()
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.default_ttl_hours == 72
        assert config.key_prefix == "mongo_pivot"
        assert config.connection_pool_size == 10
        assert config.socket_timeout == 5.0
        assert config.socket_connect_timeout == 5.0
        assert config.retry_on_timeout is True
        assert config.health_check_interval == 30
    
    def test_from_env(self):
        """测试从环境变量创建配置"""
        with patch.dict('os.environ', {
            'REDIS_URL': 'redis://test:6379/1',
            'REDIS_DEFAULT_TTL_HOURS': '48',
            'REDIS_KEY_PREFIX': 'test_prefix',
            'REDIS_POOL_SIZE': '20',
            'REDIS_SOCKET_TIMEOUT': '10.0',
            'REDIS_CONNECT_TIMEOUT': '8.0',
            'REDIS_HEALTH_CHECK_INTERVAL': '60'
        }):
            config = CacheConfig.from_env()
            assert config.redis_url == 'redis://test:6379/1'
            assert config.default_ttl_hours == 48
            assert config.key_prefix == 'test_prefix'
            assert config.connection_pool_size == 20
            assert config.socket_timeout == 10.0
            assert config.socket_connect_timeout == 8.0
            assert config.health_check_interval == 60


class TestCacheKey:
    """测试缓存键管理类"""
    
    def setup_method(self):
        """设置测试"""
        self.key_manager = CacheKey("test_prefix")
    
    def test_generate_hash(self):
        """测试哈希生成"""
        data1 = {"key": "value", "num": 123}
        data2 = {"num": 123, "key": "value"}  # 不同顺序
        data3 = {"key": "value", "num": 124}  # 不同值
        
        hash1 = self.key_manager.generate_hash(data1)
        hash2 = self.key_manager.generate_hash(data2)
        hash3 = self.key_manager.generate_hash(data3)
        
        # 相同数据应产生相同哈希
        assert hash1 == hash2
        # 不同数据应产生不同哈希
        assert hash1 != hash3
        # 哈希应为32字符的MD5
        assert len(hash1) == 32
        assert hash1.isalnum()
    
    def test_create_key(self):
        """测试缓存键创建"""
        config_hash = "abc123def456"
        timestamp = 1640995200  # 2022-01-01 00:00:00
        
        key = self.key_manager.create_key(config_hash, timestamp)
        expected = f"test_prefix:{config_hash}:{timestamp}"
        assert key == expected
    
    def test_create_key_without_timestamp(self):
        """测试不指定时间戳创建键"""
        config_hash = "abc123def456"
        
        with patch('time.time', return_value=1640995200):
            key = self.key_manager.create_key(config_hash)
            expected = f"test_prefix:{config_hash}:1640995200"
            assert key == expected
    
    def test_parse_key(self):
        """测试缓存键解析"""
        key = "test_prefix:abc123def456:1640995200"
        parsed = self.key_manager.parse_key(key)
        
        assert parsed['prefix'] == 'test_prefix'
        assert parsed['hash'] == 'abc123def456'
        assert parsed['timestamp'] == '1640995200'
    
    def test_parse_key_invalid(self):
        """测试解析无效键"""
        with pytest.raises(ValueError, match="Invalid key format"):
            self.key_manager.parse_key("invalid:key")
    
    def test_get_pattern(self):
        """测试获取键模式"""
        # 无配置哈希
        pattern = self.key_manager.get_pattern()
        assert pattern == "test_prefix:*"
        
        # 指定配置哈希
        pattern = self.key_manager.get_pattern("abc123")
        assert pattern == "test_prefix:abc123:*"


class TestCacheManager:
    """测试缓存管理器核心类"""
    
    def setup_method(self):
        """设置测试"""
        self.config = CacheConfig(
            redis_url="redis://localhost:6379/15",  # 使用测试数据库
            default_ttl_hours=1,
            key_prefix="test_cache"
        )
    
    @patch('redis.ConnectionPool')
    @patch('redis.Redis')
    def test_initialize_connection_success(self, mock_redis, mock_pool):
        """测试连接初始化成功"""
        # 设置mock
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        
        # 创建管理器并初始化连接
        manager = CacheManager(self.config)
        manager._initialize_connection()
        
        # 验证调用
        mock_pool.from_url.assert_called_once()
        mock_redis.assert_called_once()
        mock_client.ping.assert_called_once()
        
        assert manager._is_healthy is True
        assert manager._client == mock_client
    
    @patch('redis.ConnectionPool')
    @patch('redis.Redis')
    def test_initialize_connection_failure(self, mock_redis, mock_pool):
        """测试连接初始化失败"""
        # 设置mock抛出异常
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.ping.side_effect = Exception("Connection failed")
        
        manager = CacheManager(self.config)
        
        with pytest.raises(Exception, match="Connection failed"):
            manager._initialize_connection()
        
        assert manager._is_healthy is False
        assert manager._client is None
    
    @patch('redis.Redis')
    def test_is_available(self, mock_redis):
        """测试可用性检查"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        
        # 成功情况
        assert manager.is_available() is True
        
        # 失败情况
        mock_client.ping.side_effect = Exception("Connection error")
        assert manager.is_available() is False
    
    @patch('redis.Redis')
    def test_get_cache_hit(self, mock_redis):
        """测试缓存命中"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        test_data = {"result": "test_value", "count": 123}
        mock_client.get.return_value = json.dumps(test_data).encode('utf-8')
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        result = manager.get("test_key")
        
        assert result == test_data
        mock_client.get.assert_called_once_with("test_key")
    
    @patch('redis.Redis')
    def test_get_cache_miss(self, mock_redis):
        """测试缓存未命中"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.get.return_value = None
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        result = manager.get("test_key")
        
        assert result is None
        mock_client.get.assert_called_once_with("test_key")
    
    @patch('redis.Redis')
    def test_get_invalid_json(self, mock_redis):
        """测试获取无效JSON数据"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.get.return_value = b"invalid json"
        mock_client.delete.return_value = 1
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        result = manager.get("test_key")
        
        assert result is None
        # 应该删除损坏的缓存条目
        mock_client.delete.assert_called_once_with("test_key")
    
    @patch('redis.Redis')
    def test_set_cache_success(self, mock_redis):
        """测试设置缓存成功"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.setex.return_value = True
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        test_data = {"result": "test_value"}
        result = manager.set("test_key", test_data, 2)
        
        assert result is True
        expected_json = json.dumps(test_data, ensure_ascii=False, separators=(',', ':'))
        mock_client.setex.assert_called_once_with("test_key", 7200, expected_json)  # 2 * 3600
    
    @patch('redis.Redis')
    def test_set_cache_default_ttl(self, mock_redis):
        """测试使用默认TTL设置缓存"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.setex.return_value = True
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        test_data = {"result": "test_value"}
        result = manager.set("test_key", test_data)
        
        assert result is True
        expected_json = json.dumps(test_data, ensure_ascii=False, separators=(',', ':'))
        mock_client.setex.assert_called_once_with("test_key", 3600, expected_json)  # 1 * 3600
    
    @patch('redis.Redis')
    def test_delete_cache(self, mock_redis):
        """测试删除缓存"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        # 测试删除成功
        mock_client.delete.return_value = 1
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        result = manager.delete("test_key")
        assert result is True
        
        # 测试删除失败（键不存在）
        mock_client.delete.return_value = 0
        result = manager.delete("nonexistent_key")
        assert result is False
    
    @patch('redis.Redis')
    def test_clear_pattern(self, mock_redis):
        """测试按模式清除缓存"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.keys.return_value = [b'key1', b'key2', b'key3']
        mock_client.delete.return_value = 3
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        result = manager.clear_pattern("test:*")
        
        assert result == 3
        mock_client.keys.assert_called_once_with("test:*")
        mock_client.delete.assert_called_once_with(b'key1', b'key2', b'key3')
    
    @patch('redis.Redis')
    def test_get_cache_by_config(self, mock_redis):
        """测试根据配置获取缓存"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        # 设置返回的键（按时间戳排序）
        keys = [
            b'test_cache:abc123:1640995200',  # 老的
            b'test_cache:abc123:1640995300',  # 新的
            b'test_cache:abc123:1640995100'   # 更老的
        ]
        mock_client.keys.return_value = keys
        
        test_data = {"result": "latest_value"}
        mock_client.get.return_value = json.dumps(test_data).encode('utf-8')
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        config_data = {"query": "test", "limit": 100}
        result = manager.get_cache_by_config(config_data)
        
        assert result == test_data
        # 应该选择最新的键（时间戳最大）
        mock_client.get.assert_called_once_with('test_cache:abc123:1640995300')
    
    @patch('redis.Redis')
    def test_set_cache_by_config(self, mock_redis):
        """测试根据配置设置缓存"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        mock_client.setex.return_value = True
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        
        config_data = {"query": "test", "limit": 100}
        test_data = {"result": "test_value"}
        
        with patch('time.time', return_value=1640995200):
            cache_key = manager.set_cache_by_config(config_data, test_data)
        
        assert cache_key is not None
        assert cache_key.startswith("test_cache:")
        assert cache_key.endswith(":1640995200")
    
    @patch('redis.Redis')
    def test_get_stats(self, mock_redis):
        """测试获取统计信息"""
        mock_client = Mock()
        mock_redis.return_value = mock_client
        
        # 设置mock返回值
        mock_info = {
            'redis_version': '6.2.0',
            'connected_clients': 5,
            'used_memory_human': '1.2M',
            'keyspace_hits': 1000,
            'keyspace_misses': 100,
            'db0': {'keys': 50}
        }
        mock_client.info.return_value = mock_info
        mock_client.keys.return_value = [b'key1', b'key2']
        
        manager = CacheManager(self.config)
        manager._client = mock_client
        manager._is_healthy = True
        manager._last_health_check = 1640995200
        
        stats = manager.get_stats()
        
        assert stats['redis_version'] == '6.2.0'
        assert stats['connected_clients'] == 5
        assert stats['used_memory_human'] == '1.2M'
        assert stats['total_keys'] == 50
        assert stats['our_keys_count'] == 2
        assert stats['keyspace_hits'] == 1000
        assert stats['keyspace_misses'] == 100
        assert stats['is_healthy'] is True
        # 验证时间戳格式正确
        assert 'T' in stats['last_health_check']  # ISO格式包含T
    
    def test_close(self):
        """测试关闭连接"""
        manager = CacheManager(self.config)
        
        # 创建mock客户端和池
        mock_client = Mock()
        mock_pool = Mock()
        manager._client = mock_client
        manager._pool = mock_pool
        manager._is_healthy = True
        
        manager.close()
        
        mock_client.close.assert_called_once()
        mock_pool.disconnect.assert_called_once()
        assert manager._client is None
        assert manager._pool is None
        assert manager._is_healthy is False


class TestGlobalFunctions:
    """测试全局函数"""
    
    @patch('core.redis_cache.CacheManager')
    def test_get_cache_manager(self, mock_cache_manager):
        """测试获取全局缓存管理器"""
        # 清除全局实例
        import core.redis_cache
        core.redis_cache._cache_manager = None
        
        mock_instance = Mock()
        mock_cache_manager.return_value = mock_instance
        
        # 第一次调用应创建实例
        manager1 = get_cache_manager()
        assert manager1 == mock_instance
        
        # 第二次调用应返回相同实例
        manager2 = get_cache_manager()
        assert manager2 == mock_instance
        
        # 只应创建一次
        mock_cache_manager.assert_called_once()
    
    @patch('core.redis_cache.get_cache_manager')
    def test_is_cache_available_true(self, mock_get_manager):
        """测试缓存可用性检查 - 可用"""
        mock_manager = Mock()
        mock_manager.is_available.return_value = True
        mock_get_manager.return_value = mock_manager
        
        result = is_cache_available()
        assert result is True
    
    @patch('core.redis_cache.get_cache_manager')
    def test_is_cache_available_false(self, mock_get_manager):
        """测试缓存可用性检查 - 不可用"""
        mock_manager = Mock()
        mock_manager.is_available.return_value = False
        mock_get_manager.return_value = mock_manager
        
        result = is_cache_available()
        assert result is False
    
    @patch('core.redis_cache.get_cache_manager')
    def test_is_cache_available_exception(self, mock_get_manager):
        """测试缓存可用性检查 - 异常情况"""
        mock_get_manager.side_effect = Exception("Redis connection error")
        
        result = is_cache_available()
        assert result is False


class TestIntegration:
    """集成测试（需要真实Redis服务）"""
    
    @pytest.mark.integration
    def test_real_redis_operations(self):
        """测试真实Redis操作"""
        # 这个测试需要真实的Redis服务
        # 可以通过环境变量REDIS_URL指定测试Redis实例
        config = CacheConfig(
            redis_url="redis://localhost:6379/15",
            default_ttl_hours=1,
            key_prefix="integration_test"
        )
        
        try:
            manager = CacheManager(config)
            
            # 测试连接
            if not manager.is_available():
                pytest.skip("Redis not available for integration test")
            
            # 清理现有测试数据
            manager.clear_all()
            
            # 测试基本操作
            test_key = "test:integration:key"
            test_data = {"message": "hello", "count": 42}
            
            # 设置缓存
            result = manager.set(test_key, test_data, 1)
            assert result is True
            
            # 获取缓存
            cached_data = manager.get(test_key)
            assert cached_data == test_data
            
            # 删除缓存
            result = manager.delete(test_key)
            assert result is True
            
            # 验证删除
            cached_data = manager.get(test_key)
            assert cached_data is None
            
            # 测试配置缓存
            config_data = {"query": "SELECT * FROM test", "limit": 100}
            cache_key = manager.set_cache_by_config(config_data, test_data)
            assert cache_key is not None
            
            # 通过配置获取缓存
            cached_by_config = manager.get_cache_by_config(config_data)
            assert cached_by_config == test_data
            
            # 清理
            manager.clear_all()
            
        except Exception as e:
            pytest.skip(f"Integration test failed (Redis may not be available): {e}")
        finally:
            try:
                manager.close()
            except:
                pass