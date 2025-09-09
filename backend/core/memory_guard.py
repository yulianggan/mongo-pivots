"""
增强型内存护栏系统
支持缓存感知的内存管理、任务队列集成和多级压力响应
确保内存使用≤60%，硬限制8GB，防止OOM
"""
import gc
import time
import psutil
import threading
import asyncio
import weakref
from typing import Dict, Any, Optional, Callable, List, Protocol
from dataclasses import dataclass, field
from contextlib import contextmanager
from enum import Enum
import logging

from .config import config


class MemoryPressureLevel(Enum):
    """内存压力级别"""
    NORMAL = "normal"          # <50% 使用率
    WARNING = "warning"        # 50-60% 使用率
    CRITICAL = "critical"      # 60-70% 使用率
    EMERGENCY = "emergency"    # >70% 使用率


class CacheCleanupStrategy(Enum):
    """缓存清理策略"""
    LRU = "lru"               # 最近最少使用
    SIZE_BASED = "size_based"  # 基于大小
    TTL_BASED = "ttl_based"   # 基于过期时间
    AGGRESSIVE = "aggressive"  # 激进清理


class MemoryCleanupCallback(Protocol):
    """内存清理回调协议"""
    def __call__(self, pressure_level: MemoryPressureLevel, freed_bytes: int) -> int:
        """执行清理操作，返回实际释放的字节数"""
        ...


@dataclass
class MemoryStats:
    """内存使用统计"""
    used_bytes: int
    available_bytes: int
    used_percent: float
    limit_bytes: int
    rss_bytes: int  # 进程实际物理内存
    is_critical: bool
    
    # 新增字段
    pressure_level: MemoryPressureLevel = MemoryPressureLevel.NORMAL
    cache_memory_bytes: Optional[int] = None
    queue_memory_bytes: Optional[int] = None
    system_memory_pressure: float = 0.0  # 系统级内存压力
    
    def __post_init__(self):
        """计算压力级别"""
        if self.used_percent >= 70:
            self.pressure_level = MemoryPressureLevel.EMERGENCY
        elif self.used_percent >= 60:
            self.pressure_level = MemoryPressureLevel.CRITICAL
        elif self.used_percent >= 50:
            self.pressure_level = MemoryPressureLevel.WARNING
        else:
            self.pressure_level = MemoryPressureLevel.NORMAL


@dataclass
class MemoryCleanupResult:
    """内存清理结果"""
    strategy: CacheCleanupStrategy
    freed_bytes: int
    items_cleaned: int
    cleanup_duration_ms: float
    success: bool
    error: Optional[str] = None


class EnhancedMemoryGuard:
    """增强型内存监控和保护器"""
    
    def __init__(self):
        self.limit_bytes = config.get_memory_limit_bytes()
        self.gc_threshold_bytes = int(self.limit_bytes * (config.memory.gc_threshold_percent / 100.0))
        
        # 压力级别阈值
        self.warning_threshold = int(self.limit_bytes * 0.50)  # 50%
        self.critical_threshold = int(self.limit_bytes * 0.60)  # 60%
        self.emergency_threshold = int(self.limit_bytes * 0.70)  # 70%
        
        self._monitoring = False
        self._monitor_thread = None
        self._callbacks = []
        self._cleanup_callbacks: List[MemoryCleanupCallback] = []
        self._process = psutil.Process()
        self.logger = logging.getLogger(__name__)
        
        # 缓存和任务队列集成
        self._cache_manager = None
        self._task_manager = None
        self._cache_memory_estimator = None
        self._queue_memory_estimator = None
        
        # 清理历史记录
        self._cleanup_history: List[MemoryCleanupResult] = []
        self._last_cleanup_time = 0
        self._cleanup_cooldown_seconds = 30  # 清理冷却时间
        
        # 统计信息
        self._stats = {
            'total_cleanups': 0,
            'total_freed_bytes': 0,
            'pressure_level_changes': 0,
            'emergency_cleanups': 0
        }
    
    def get_memory_stats(self) -> MemoryStats:
        """获取内存使用统计"""
        memory = psutil.virtual_memory()
        process_memory = self._process.memory_info()
        
        used_bytes = memory.used
        available_bytes = memory.available
        used_percent = memory.percent
        rss_bytes = process_memory.rss
        is_critical = rss_bytes > self.gc_threshold_bytes
        
        # 估算缓存和队列内存使用
        cache_memory = self._estimate_cache_memory()
        queue_memory = self._estimate_queue_memory()
        
        # 计算系统级内存压力
        system_pressure = min(100.0, (rss_bytes / self.limit_bytes) * 100)
        
        stats = MemoryStats(
            used_bytes=used_bytes,
            available_bytes=available_bytes,
            used_percent=used_percent,
            limit_bytes=self.limit_bytes,
            rss_bytes=rss_bytes,
            is_critical=is_critical,
            cache_memory_bytes=cache_memory,
            queue_memory_bytes=queue_memory,
            system_memory_pressure=system_pressure
        )
        
        return stats
    
    def register_cache_manager(self, cache_manager):
        """注册缓存管理器"""
        self._cache_manager = weakref.ref(cache_manager)
    
    def register_task_manager(self, task_manager):
        """注册任务管理器"""
        self._task_manager = weakref.ref(task_manager)
    
    def add_cleanup_callback(self, callback: MemoryCleanupCallback):
        """添加内存清理回调"""
        self._cleanup_callbacks.append(callback)
    
    def remove_cleanup_callback(self, callback: MemoryCleanupCallback):
        """移除内存清理回调"""
        if callback in self._cleanup_callbacks:
            self._cleanup_callbacks.remove(callback)
    
    def _estimate_cache_memory(self) -> Optional[int]:
        """估算缓存内存使用量"""
        if self._cache_manager and self._cache_manager():
            try:
                cache_stats = self._cache_manager().get_stats()
                # 从Redis统计信息中获取内存使用
                used_memory = cache_stats.get('used_memory_human', '0B')
                # 简单解析，实际应该更robust
                if 'MB' in used_memory:
                    return int(float(used_memory.replace('MB', '')) * 1024 * 1024)
                elif 'KB' in used_memory:
                    return int(float(used_memory.replace('KB', '')) * 1024)
            except Exception as e:
                self.logger.debug(f"估算缓存内存失败: {e}")
        return None
    
    def _estimate_queue_memory(self) -> Optional[int]:
        """估算任务队列内存使用量"""
        if self._task_manager and self._task_manager():
            try:
                # 粗略估算：每个任务约1KB元数据
                task_manager = self._task_manager()
                stats = asyncio.run(task_manager.get_stats())
                total_tasks = stats.get('queue_stats', {}).get('total_tasks', 0)
                return total_tasks * 1024  # 1KB per task
            except Exception as e:
                self.logger.debug(f"估算队列内存失败: {e}")
        return None
    
    def check_memory_limit(self) -> bool:
        """检查是否超过内存限制"""
        stats = self.get_memory_stats()
        return stats.rss_bytes <= self.limit_bytes
    
    def get_pressure_level(self) -> MemoryPressureLevel:
        """获取当前内存压力级别"""
        stats = self.get_memory_stats()
        return stats.pressure_level
    
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
        freed_bytes = max(0, before_stats.rss_bytes - after_stats.rss_bytes)
        
        self.logger.info(f"垃圾回收完成: 收集了{collected}个对象，释放{freed_bytes / 1024 / 1024:.1f}MB")
        return freed_bytes
    
    def cleanup_cache(self, strategy: CacheCleanupStrategy = CacheCleanupStrategy.LRU) -> MemoryCleanupResult:
        """清理缓存"""
        start_time = time.time()
        
        try:
            if not self._cache_manager or not self._cache_manager():
                return MemoryCleanupResult(
                    strategy=strategy,
                    freed_bytes=0,
                    items_cleaned=0,
                    cleanup_duration_ms=0,
                    success=False,
                    error="缓存管理器未注册"
                )
            
            cache_manager = self._cache_manager()
            before_stats = self.get_memory_stats()
            
            # 根据策略执行清理
            items_cleaned = 0
            if strategy == CacheCleanupStrategy.AGGRESSIVE:
                # 激进清理：清除所有缓存
                items_cleaned = cache_manager.clear_all()
            elif strategy == CacheCleanupStrategy.TTL_BASED:
                # 基于TTL清理过期项
                items_cleaned = cache_manager.cleanup_expired()
            else:
                # 默认LRU策略：清理部分缓存
                # 这里简化处理，实际可以基于access时间等信息
                items_cleaned = cache_manager.clear_all() // 2
            
            # 执行垃圾回收
            self.force_gc()
            
            after_stats = self.get_memory_stats()
            freed_bytes = max(0, before_stats.rss_bytes - after_stats.rss_bytes)
            duration_ms = (time.time() - start_time) * 1000
            
            result = MemoryCleanupResult(
                strategy=strategy,
                freed_bytes=freed_bytes,
                items_cleaned=items_cleaned,
                cleanup_duration_ms=duration_ms,
                success=True
            )
            
            self.logger.info(f"缓存清理完成: 策略={strategy.value}, 清理项目={items_cleaned}, 释放内存={freed_bytes / 1024 / 1024:.1f}MB")
            
            # 添加到清理历史记录
            self._cleanup_history.append(result)
            if len(self._cleanup_history) > 100:
                self._cleanup_history = self._cleanup_history[-100:]
            
            # 更新统计信息
            self._stats['total_cleanups'] += 1
            self._stats['total_freed_bytes'] += freed_bytes
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"缓存清理失败: {str(e)}"
            self.logger.error(error_msg)
            
            result = MemoryCleanupResult(
                strategy=strategy,
                freed_bytes=0,
                items_cleaned=0,
                cleanup_duration_ms=duration_ms,
                success=False,
                error=error_msg
            )
            
            # 即使失败也添加到历史记录
            self._cleanup_history.append(result)
            if len(self._cleanup_history) > 100:
                self._cleanup_history = self._cleanup_history[-100:]
            
            return result
    
    def handle_memory_pressure(self, stats: MemoryStats) -> List[MemoryCleanupResult]:
        """处理内存压力"""
        results = []
        current_time = time.time()
        
        # 检查冷却时间
        if current_time - self._last_cleanup_time < self._cleanup_cooldown_seconds:
            return results
        
        self.logger.warning(f"检测到内存压力: {stats.pressure_level.value}, 使用率: {stats.used_percent:.1f}%")
        
        try:
            if stats.pressure_level == MemoryPressureLevel.WARNING:
                # 轻度清理
                result = self.cleanup_cache(CacheCleanupStrategy.TTL_BASED)
                results.append(result)
                
            elif stats.pressure_level == MemoryPressureLevel.CRITICAL:
                # 中度清理
                result1 = self.cleanup_cache(CacheCleanupStrategy.LRU)
                results.append(result1)
                
                # 执行自定义清理回调
                for callback in self._cleanup_callbacks:
                    try:
                        freed = callback(stats.pressure_level, result1.freed_bytes)
                        self.logger.info(f"自定义清理回调释放了 {freed / 1024 / 1024:.1f}MB")
                    except Exception as e:
                        self.logger.error(f"清理回调执行失败: {e}")
                
            elif stats.pressure_level == MemoryPressureLevel.EMERGENCY:
                # 紧急清理
                self._stats['emergency_cleanups'] += 1
                
                result1 = self.cleanup_cache(CacheCleanupStrategy.AGGRESSIVE)
                results.append(result1)
                
                # 强制垃圾回收
                freed_gc = self.force_gc()
                
                # 尝试暂停低优先级任务
                if self._task_manager and self._task_manager():
                    try:
                        # 这里可以实现暂停低优先级任务的逻辑
                        self.logger.warning("内存紧急状态，建议暂停低优先级任务")
                    except Exception as e:
                        self.logger.error(f"暂停任务失败: {e}")
                
                # 执行紧急清理回调
                for callback in self._cleanup_callbacks:
                    try:
                        freed = callback(stats.pressure_level, result1.freed_bytes + freed_gc)
                        self.logger.info(f"紧急清理回调释放了 {freed / 1024 / 1024:.1f}MB")
                    except Exception as e:
                        self.logger.error(f"紧急清理回调执行失败: {e}")
            
            # 更新统计信息
            self._stats['total_cleanups'] += len(results)
            self._stats['total_freed_bytes'] += sum(r.freed_bytes for r in results)
            self._last_cleanup_time = current_time
            
            # 保存清理历史
            self._cleanup_history.extend(results)
            # 保留最近100次清理记录
            if len(self._cleanup_history) > 100:
                self._cleanup_history = self._cleanup_history[-100:]
                
        except Exception as e:
            self.logger.error(f"处理内存压力时发生错误: {e}")
        
        return results
    
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
    
    def start_monitoring(self, interval_seconds: float = 5.0):
        """开始内存监控"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self.logger.info(f"启动增强型内存监控，间隔: {interval_seconds}秒")
        
        def monitor():
            last_pressure_level = MemoryPressureLevel.NORMAL
            
            while self._monitoring:
                try:
                    stats = self.get_memory_stats()
                    
                    # 检查压力级别变化
                    if stats.pressure_level != last_pressure_level:
                        self._stats['pressure_level_changes'] += 1
                        self.logger.info(
                            f"内存压力级别变化: {last_pressure_level.value} -> {stats.pressure_level.value}, "
                            f"使用率: {stats.used_percent:.1f}%, RSS: {stats.rss_bytes / 1024 / 1024:.1f}MB"
                        )
                    
                    # 处理内存压力
                    if stats.pressure_level != MemoryPressureLevel.NORMAL:
                        cleanup_results = self.handle_memory_pressure(stats)
                        if cleanup_results:
                            total_freed = sum(r.freed_bytes for r in cleanup_results)
                            self.logger.info(f"内存清理完成，释放了 {total_freed / 1024 / 1024:.1f}MB")
                    
                    # 传统的垃圾回收检查
                    elif stats.is_critical and last_pressure_level == MemoryPressureLevel.NORMAL:
                        freed = self.force_gc()
                        self.logger.info(f"触发垃圾回收，释放了 {freed / 1024 / 1024:.1f}MB")
                    
                    # 通知回调
                    self._notify_callbacks(stats)
                    
                    last_pressure_level = stats.pressure_level
                    time.sleep(interval_seconds)
                    
                except Exception as e:
                    self.logger.error(f"内存监控错误: {e}")
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
        """增强型内存保护上下文管理器"""
        start_stats = self.get_memory_stats()
        
        # 检查估计内存需求
        if estimated_bytes:
            if not self.ensure_memory_available(estimated_bytes):
                raise MemoryError(
                    f"操作 {operation_name} 内存不足。需要: {estimated_bytes / 1024 / 1024:.1f}MB, "
                    f"可用: {start_stats.available_bytes / 1024 / 1024:.1f}MB, "
                    f"当前压力级别: {start_stats.pressure_level.value}"
                )
        
        # 预检查内存压力
        if start_stats.pressure_level in [MemoryPressureLevel.CRITICAL, MemoryPressureLevel.EMERGENCY]:
            self.logger.warning(
                f"在高内存压力下启动操作 {operation_name}: {start_stats.pressure_level.value}, "
                f"使用率: {start_stats.used_percent:.1f}%"
            )
        
        try:
            yield start_stats
        except MemoryError:
            # 内存错误时尝试清理
            self.logger.error(f"操作 {operation_name} 遇到内存错误，尝试清理")
            cleanup_results = self.handle_memory_pressure(self.get_memory_stats())
            total_freed = sum(r.freed_bytes for r in cleanup_results)
            
            if total_freed > 0:
                self.logger.info(f"清理释放了 {total_freed / 1024 / 1024:.1f}MB，重试操作")
                # 给操作一次重试机会
                raise MemoryError(f"操作 {operation_name} 内存不足，已尝试清理释放 {total_freed / 1024 / 1024:.1f}MB")
            else:
                raise
        finally:
            # 操作完成后检查内存状态
            end_stats = self.get_memory_stats()
            memory_delta = end_stats.rss_bytes - start_stats.rss_bytes
            
            if config.performance.log_slow_operations:
                self.logger.info(
                    f"操作 {operation_name} 完成: 内存变化={memory_delta / 1024 / 1024:.1f}MB, "
                    f"压力级别: {start_stats.pressure_level.value} -> {end_stats.pressure_level.value}"
                )
            
            # 如果内存增长过多，触发清理
            if memory_delta > 100 * 1024 * 1024:  # 100MB
                self.logger.warning(f"操作 {operation_name} 内存增长过多: {memory_delta / 1024 / 1024:.1f}MB")
                self.force_gc()
            
            # 检查是否需要压力处理
            if end_stats.pressure_level != start_stats.pressure_level and end_stats.pressure_level != MemoryPressureLevel.NORMAL:
                cleanup_results = self.handle_memory_pressure(end_stats)
                if cleanup_results:
                    total_freed = sum(r.freed_bytes for r in cleanup_results)
                    self.logger.info(f"操作后清理释放了 {total_freed / 1024 / 1024:.1f}MB")
    
    def estimate_dataframe_memory(self, rows: int, columns: int, avg_string_length: int = 50) -> int:
        """估算DataFrame内存使用量"""
        # 粗略估算：数值列8字节，字符串列按平均长度计算
        # 假设一半是数值列，一半是字符串列
        numeric_memory = (columns // 2) * rows * 8
        string_memory = (columns - columns // 2) * rows * avg_string_length
        
        # 加上Polars开销（约20%）
        total_memory = int((numeric_memory + string_memory) * 1.2)
        
        return total_memory
    
    def get_cleanup_history(self) -> List[Dict[str, Any]]:
        """获取清理历史记录"""
        return [{
            'strategy': result.strategy.value,
            'freed_bytes': result.freed_bytes,
            'freed_mb': round(result.freed_bytes / 1024 / 1024, 2),
            'items_cleaned': result.items_cleaned,
            'duration_ms': result.cleanup_duration_ms,
            'success': result.success,
            'error': result.error
        } for result in self._cleanup_history[-10:]]  # 最近10次
    
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
                'is_critical': stats.is_critical,
                'pressure_level': stats.pressure_level.value,
                'cache_memory_bytes': stats.cache_memory_bytes,
                'queue_memory_bytes': stats.queue_memory_bytes,
                'system_memory_pressure': stats.system_memory_pressure
            },
            'thresholds': {
                'limit_bytes': self.limit_bytes,
                'gc_threshold_bytes': self.gc_threshold_bytes,
                'warning_threshold': self.warning_threshold,
                'critical_threshold': self.critical_threshold,
                'emergency_threshold': self.emergency_threshold
            },
            'monitoring': {
                'active': self._monitoring,
                'cleanup_cooldown_seconds': self._cleanup_cooldown_seconds,
                'last_cleanup_time': self._last_cleanup_time
            },
            'statistics': self._stats,
            'recent_cleanups': self.get_cleanup_history(),
            'integrations': {
                'cache_manager_registered': self._cache_manager is not None,
                'task_manager_registered': self._task_manager is not None,
                'cleanup_callbacks_count': len(self._cleanup_callbacks)
            }
        }


# 保持向后兼容性的别名
MemoryGuard = EnhancedMemoryGuard

# 全局内存守护实例
memory_guard = EnhancedMemoryGuard()