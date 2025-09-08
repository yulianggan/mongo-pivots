"""
ConfigManager测试
验证配置管理系统的功能
"""
import pytest
import os
from core.config import ConfigManager, MemoryConfig, PolarsConfig, PerformanceConfig


class TestConfigManager:
    """配置管理器测试"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ConfigManager()
        
        assert config.memory.max_memory_percent == 60.0
        assert config.memory.max_memory_gb == 8.0
        assert config.memory.chunk_size_rows == 200_000
        assert config.memory.gc_threshold_percent == 80.0
        
        assert config.polars.lazy_by_default is True
        assert config.polars.string_cache is True
        assert config.polars.collect_statistics is True
        
        assert config.performance.benchmark_threshold_seconds == 10.0
        assert config.performance.log_slow_operations is True
    
    def test_env_config_loading(self):
        """测试环境变量配置加载"""
        # 设置测试环境变量
        test_env = {
            'POLARS_MAX_MEMORY_PERCENT': '70.0',
            'POLARS_MAX_MEMORY_GB': '6.0',
            'POLARS_CHUNK_SIZE': '150000',
            'POLARS_N_THREADS': '4',
            'POLARS_LAZY_DEFAULT': 'false'
        }
        
        # 备份原有环境变量
        original_env = {}
        for key in test_env:
            if key in os.environ:
                original_env[key] = os.environ[key]
        
        try:
            # 设置测试环境变量
            for key, value in test_env.items():
                os.environ[key] = value
            
            # 创建新的配置管理器
            config = ConfigManager()
            
            assert config.memory.max_memory_percent == 70.0
            assert config.memory.max_memory_gb == 6.0
            assert config.memory.chunk_size_rows == 150_000
            assert config.polars.n_threads == 4
            assert config.polars.lazy_by_default is False
            
        finally:
            # 恢复原有环境变量
            for key in test_env:
                if key in original_env:
                    os.environ[key] = original_env[key]
                else:
                    del os.environ[key]
    
    def test_memory_limit_calculation(self):
        """测试内存限制计算"""
        config = ConfigManager()
        config.memory.max_memory_percent = 50.0
        config.memory.max_memory_gb = 4.0
        
        limit_bytes = config.get_memory_limit_bytes()
        
        # 应该取百分比和绝对值的最小值
        assert limit_bytes <= 4.0 * 1024 * 1024 * 1024  # 4GB硬限制
        assert isinstance(limit_bytes, int)
        assert limit_bytes > 0
    
    def test_config_to_dict(self):
        """测试配置转换为字典"""
        config = ConfigManager()
        config_dict = config.to_dict()
        
        assert 'memory' in config_dict
        assert 'polars' in config_dict
        assert 'performance' in config_dict
        
        # 检查关键字段
        assert 'max_memory_percent' in config_dict['memory']
        assert 'memory_limit_bytes' in config_dict['memory']
        assert 'lazy_by_default' in config_dict['polars']
        assert 'benchmark_threshold_seconds' in config_dict['performance']
    
    def test_polars_config_application(self):
        """测试Polars配置应用"""
        config = ConfigManager()
        config.polars.n_threads = 2
        config.polars.string_cache = True
        
        # 应用配置不应该抛出异常
        try:
            config.apply_polars_config()
        except Exception as e:
            pytest.fail(f"apply_polars_config() raised {e}")
    
    def test_memory_config_validation(self):
        """测试内存配置验证"""
        config = MemoryConfig()
        
        # 默认值应该合理
        assert 0 < config.max_memory_percent <= 100
        assert config.max_memory_gb > 0
        assert config.chunk_size_rows > 0
        assert 0 < config.gc_threshold_percent <= 100
    
    def test_polars_config_validation(self):
        """测试Polars配置验证"""
        config = PolarsConfig()
        
        # 检查默认值
        assert isinstance(config.lazy_by_default, bool)
        assert isinstance(config.string_cache, bool)
        assert isinstance(config.collect_statistics, bool)
    
    def test_performance_config_validation(self):
        """测试性能配置验证"""
        config = PerformanceConfig()
        
        assert config.benchmark_threshold_seconds > 0
        assert isinstance(config.enable_profiling, bool)
        assert isinstance(config.log_slow_operations, bool)
        assert config.slow_operation_threshold_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])