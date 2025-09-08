"""
内存监控和保护机制
确保内存使用不超过容器限制，防止OOM
"""
import gc
import time
import psutil
import threading
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from contextlib import contextmanager

from .config import config


@dataclass
class MemoryStats:
    """内存使用统计"""
    used_bytes: int
    available_bytes: int
    used_percent: float
    limit_bytes: int
    rss_bytes: int  # 进程实际物理内存
    is_critical: bool


class MemoryGuard:
    """内存监控和保护器"""
    
    def __init__(self):
        self.limit_bytes = config.get_memory_limit_bytes()
        self.gc_threshold_bytes = int(self.limit_bytes * (config.memory.gc_threshold_percent / 100.0))
        self._monitoring = False
        self._monitor_thread = None
        self._callbacks = []
        self._process = psutil.Process()
    
    def get_memory_stats(self) -> MemoryStats:
        """获取内存使用统计"""
        memory = psutil.virtual_memory()
        process_memory = self._process.memory_info()
        
        used_bytes = memory.used
        available_bytes = memory.available
        used_percent = memory.percent
        rss_bytes = process_memory.rss
        is_critical = rss_bytes > self.gc_threshold_bytes
        
        return MemoryStats(
            used_bytes=used_bytes,
            available_bytes=available_bytes,
            used_percent=used_percent,
            limit_bytes=self.limit_bytes,
            rss_bytes=rss_bytes,
            is_critical=is_critical
        )
    
    def check_memory_limit(self) -> bool:
        """检查是否超过内存限制"""
        stats = self.get_memory_stats()
        return stats.rss_bytes <= self.limit_bytes
    
    def check_gc_threshold(self) -> bool:
        """检查是否达到垃圾回收阈值"""
        stats = self.get_memory_stats()
        return stats.rss_bytes > self.gc_threshold_bytes
    
    def force_gc(self) -> int:
        """强制垃圾回收"""
        before_stats = self.get_memory_stats()
        
        # 执行垃圾回收
        collected = gc.collect()
        
        after_stats = self.get_memory_stats()
        freed_bytes = before_stats.rss_bytes - after_stats.rss_bytes
        
        return freed_bytes
    
    def ensure_memory_available(self, required_bytes: int) -> bool:
        """确保有足够内存可用"""
        stats = self.get_memory_stats()
        
        # 检查是否有足够内存
        if stats.rss_bytes + required_bytes <= self.limit_bytes:
            return True
        
        # 尝试垃圾回收
        freed = self.force_gc()
        
        # 重新检查
        stats = self.get_memory_stats()
        return stats.rss_bytes + required_bytes <= self.limit_bytes
    
    def add_callback(self, callback: Callable[[MemoryStats], None]):
        """添加内存状态变化回调"""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[MemoryStats], None]):
        """移除内存状态变化回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self, stats: MemoryStats):
        """通知所有回调函数"""
        for callback in self._callbacks:
            try:
                callback(stats)
            except Exception as e:
                # 记录错误但不中断监控
                print(f"Memory callback error: {e}")
    
    def start_monitoring(self, interval_seconds: float = 1.0):
        """开始内存监控"""
        if self._monitoring:
            return
        
        self._monitoring = True
        
        def monitor():
            last_critical = False
            
            while self._monitoring:
                try:
                    stats = self.get_memory_stats()
                    
                    # 检查是否需要触发垃圾回收
                    if stats.is_critical and not last_critical:
                        print(f"Memory critical: {stats.rss_bytes / 1024 / 1024:.1f}MB / {self.limit_bytes / 1024 / 1024:.1f}MB")
                        freed = self.force_gc()
                        print(f"GC freed: {freed / 1024 / 1024:.1f}MB")
                    
                    # 通知回调
                    self._notify_callbacks(stats)
                    
                    last_critical = stats.is_critical
                    time.sleep(interval_seconds)
                    
                except Exception as e:
                    print(f"Memory monitoring error: {e}")
                    time.sleep(interval_seconds)
        
        self._monitor_thread = threading.Thread(target=monitor, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self):
        """停止内存监控"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
    
    @contextmanager
    def memory_guard(self, operation_name: str = "operation", estimated_bytes: Optional[int] = None):
        """内存保护上下文管理器"""
        start_stats = self.get_memory_stats()
        
        # 检查估计内存需求
        if estimated_bytes and not self.ensure_memory_available(estimated_bytes):
            raise MemoryError(f"Insufficient memory for {operation_name}. Required: {estimated_bytes / 1024 / 1024:.1f}MB")
        
        try:
            yield start_stats
        except MemoryError:
            # 内存错误时尝试垃圾回收
            self.force_gc()
            raise
        finally:
            # 操作完成后检查内存状态
            end_stats = self.get_memory_stats()
            memory_delta = end_stats.rss_bytes - start_stats.rss_bytes
            
            if config.performance.log_slow_operations:
                print(f"Memory delta for {operation_name}: {memory_delta / 1024 / 1024:.1f}MB")
            
            # 如果内存增长过多，触发垃圾回收
            if memory_delta > 100 * 1024 * 1024:  # 100MB
                self.force_gc()
    
    def estimate_dataframe_memory(self, rows: int, columns: int, avg_string_length: int = 50) -> int:
        """估算DataFrame内存使用量"""
        # 粗略估算：数值列8字节，字符串列按平均长度计算
        # 假设一半是数值列，一半是字符串列
        numeric_memory = (columns // 2) * rows * 8
        string_memory = (columns - columns // 2) * rows * avg_string_length
        
        # 加上Polars开销（约20%）
        total_memory = int((numeric_memory + string_memory) * 1.2)
        
        return total_memory
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        stats = self.get_memory_stats()
        return {
            'memory_stats': {
                'used_bytes': stats.used_bytes,
                'available_bytes': stats.available_bytes,
                'used_percent': stats.used_percent,
                'limit_bytes': stats.limit_bytes,
                'rss_bytes': stats.rss_bytes,
                'is_critical': stats.is_critical
            },
            'thresholds': {
                'limit_bytes': self.limit_bytes,
                'gc_threshold_bytes': self.gc_threshold_bytes
            },
            'monitoring': self._monitoring
        }


# 全局内存守护实例
memory_guard = MemoryGuard()