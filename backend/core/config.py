"""
配置管理系统
提供引擎参数和性能调优配置管理
"""
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class MemoryConfig:
    """内存配置"""
    max_memory_percent: float = 60.0  # 最大内存使用百分比
    max_memory_gb: float = 8.0  # 硬限制，最大8GB
    chunk_size_rows: int = 200_000  # 分块处理行数
    gc_threshold_percent: float = 80.0  # 触发垃圾回收的内存阈值


@dataclass
class PolarsConfig:
    """Polars引擎配置"""
    n_threads: Optional[int] = None  # None表示使用所有可用CPU
    lazy_by_default: bool = True  # 默认使用懒计算
    string_cache: bool = True  # 启用字符串缓存优化
    collect_statistics: bool = True  # 收集查询统计信息


@dataclass
class PerformanceConfig:
    """性能配置"""
    benchmark_threshold_seconds: float = 10.0  # 100万行操作阈值（秒）
    enable_profiling: bool = False  # 是否启用性能分析
    log_slow_operations: bool = True  # 记录慢操作
    slow_operation_threshold_ms: int = 1000  # 慢操作阈值（毫秒）


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.memory = MemoryConfig()
        self.polars = PolarsConfig()
        self.performance = PerformanceConfig()
        self._load_from_env()
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        # 内存配置
        if os.getenv('POLARS_MAX_MEMORY_PERCENT'):
            self.memory.max_memory_percent = float(os.getenv('POLARS_MAX_MEMORY_PERCENT'))
        
        if os.getenv('POLARS_MAX_MEMORY_GB'):
            self.memory.max_memory_gb = float(os.getenv('POLARS_MAX_MEMORY_GB'))
        
        if os.getenv('POLARS_CHUNK_SIZE'):
            self.memory.chunk_size_rows = int(os.getenv('POLARS_CHUNK_SIZE'))
        
        if os.getenv('POLARS_GC_THRESHOLD'):
            self.memory.gc_threshold_percent = float(os.getenv('POLARS_GC_THRESHOLD'))
        
        # Polars配置
        if os.getenv('POLARS_N_THREADS'):
            self.polars.n_threads = int(os.getenv('POLARS_N_THREADS'))
        
        if os.getenv('POLARS_LAZY_DEFAULT'):
            self.polars.lazy_by_default = os.getenv('POLARS_LAZY_DEFAULT').lower() == 'true'
        
        if os.getenv('POLARS_STRING_CACHE'):
            self.polars.string_cache = os.getenv('POLARS_STRING_CACHE').lower() == 'true'
        
        # 性能配置
        if os.getenv('POLARS_BENCHMARK_THRESHOLD'):
            self.performance.benchmark_threshold_seconds = float(os.getenv('POLARS_BENCHMARK_THRESHOLD'))
        
        if os.getenv('POLARS_ENABLE_PROFILING'):
            self.performance.enable_profiling = os.getenv('POLARS_ENABLE_PROFILING').lower() == 'true'
    
    def get_memory_limit_bytes(self) -> int:
        """获取内存限制（字节）"""
        import psutil
        
        # 获取系统总内存
        total_memory = psutil.virtual_memory().total
        percent_limit = int(total_memory * (self.memory.max_memory_percent / 100.0))
        
        # 硬限制
        gb_limit = int(self.memory.max_memory_gb * 1024 * 1024 * 1024)
        
        return min(percent_limit, gb_limit)
    
    def apply_polars_config(self):
        """应用Polars配置到全局设置"""
        import polars as pl
        
        # 设置线程数
        if self.polars.n_threads is not None:
            pl.Config.set_tbl_cols(20)  # 设置显示列数
            # 线程数通过环境变量设置
            import os
            os.environ['POLARS_MAX_THREADS'] = str(self.polars.n_threads)
        
        # 启用字符串缓存
        if self.polars.string_cache:
            pl.enable_string_cache()
        else:
            pl.disable_string_cache()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'memory': {
                'max_memory_percent': self.memory.max_memory_percent,
                'max_memory_gb': self.memory.max_memory_gb,
                'chunk_size_rows': self.memory.chunk_size_rows,
                'gc_threshold_percent': self.memory.gc_threshold_percent,
                'memory_limit_bytes': self.get_memory_limit_bytes()
            },
            'polars': {
                'n_threads': self.polars.n_threads,
                'lazy_by_default': self.polars.lazy_by_default,
                'string_cache': self.polars.string_cache,
                'collect_statistics': self.polars.collect_statistics
            },
            'performance': {
                'benchmark_threshold_seconds': self.performance.benchmark_threshold_seconds,
                'enable_profiling': self.performance.enable_profiling,
                'log_slow_operations': self.performance.log_slow_operations,
                'slow_operation_threshold_ms': self.performance.slow_operation_threshold_ms
            }
        }


# 全局配置实例
config = ConfigManager()