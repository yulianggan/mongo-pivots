"""
增强型MemoryGuard测试
验证内存监控、压力检测、缓存集成和清理机制
"""
import pytest
import time
import threading
import asyncio
from unittest.mock import Mock, patch, MagicMock
from core.memory_guard import (
    EnhancedMemoryGuard, 
    MemoryGuard,  # 向后兼容别名
    MemoryStats, 
    MemoryPressureLevel, 
    CacheCleanupStrategy,
    MemoryCleanupResult
)


class TestEnhancedMemoryGuard:
    """增强型内存守护测试"""
    
    def test_memory_stats_creation(self):
        """测试增强型内存统计创建"""
        guard = EnhancedMemoryGuard()
        stats = guard.get_memory_stats()
        
        assert isinstance(stats, MemoryStats)
        assert stats.used_bytes >= 0
        assert stats.available_bytes >= 0
        assert 0 <= stats.used_percent <= 100
        assert stats.limit_bytes > 0
        assert stats.rss_bytes >= 0
        assert isinstance(stats.is_critical, bool)
        
        # 新增字段测试
        assert isinstance(stats.pressure_level, MemoryPressureLevel)
        assert stats.cache_memory_bytes is None  # 未注册缓存管理器
        assert stats.queue_memory_bytes is None  # 未注册任务管理器
        assert isinstance(stats.system_memory_pressure, float)
        assert 0 <= stats.system_memory_pressure <= 100
    
    def test_pressure_level_detection(self):
        """测试压力级别检测"""
        guard = EnhancedMemoryGuard()
        
        # 测试压力级别检测
        pressure_level = guard.get_pressure_level()
        assert isinstance(pressure_level, MemoryPressureLevel)
        
        # 测试内存限制检查
        within_limit = guard.check_memory_limit()
        assert isinstance(within_limit, bool)
    
    def test_thresholds_configuration(self):
        """测试阈值配置"""
        guard = EnhancedMemoryGuard()
        
        # 检查所有阈值都被正确设置
        assert guard.warning_threshold > 0
        assert guard.critical_threshold > guard.warning_threshold
        assert guard.emergency_threshold > guard.critical_threshold
        assert guard.gc_threshold_bytes > 0
        
        # 验证百分比关系
        assert guard.warning_threshold == int(guard.limit_bytes * 0.50)
        assert guard.critical_threshold == int(guard.limit_bytes * 0.60)
        assert guard.emergency_threshold == int(guard.limit_bytes * 0.70)
        
        # 测试GC阈值检查
        threshold_reached = guard.check_gc_threshold()
        assert isinstance(threshold_reached, bool)
    
    def test_force_gc(self):
        """测试强制垃圾回收"""
        guard = EnhancedMemoryGuard()
        
        # 创建一些垃圾数据
        garbage_data = [list(range(1000)) for _ in range(100)]
        
        freed_bytes = guard.force_gc()
        assert isinstance(freed_bytes, int)
        assert freed_bytes >= 0  # 释放字节数不能为负
        
        # 删除引用让垃圾数据可被回收
        del garbage_data
    
    def test_ensure_memory_available(self):
        """测试确保内存可用"""
        guard = EnhancedMemoryGuard()
        
        # 请求合理的内存量应该成功
        small_request = 1024 * 1024  # 1MB
        available = guard.ensure_memory_available(small_request)
        assert isinstance(available, bool)
        
        # 请求过大的内存应该失败
        huge_request = guard.limit_bytes + 1
        available = guard.ensure_memory_available(huge_request)
        assert available is False
    
    def test_memory_guard_context_manager(self):
        """测试增强型内存保护上下文管理器"""
        guard = EnhancedMemoryGuard()
        
        # 正常操作应该成功
        with guard.memory_guard("test_operation") as start_stats:
            assert isinstance(start_stats, MemoryStats)
            assert isinstance(start_stats.pressure_level, MemoryPressureLevel)
            time.sleep(0.1)  # 模拟一些工作
    
    def test_memory_guard_with_estimate(self):
        """测试带估算的内存保护"""
        guard = EnhancedMemoryGuard()
        
        # 合理的内存估算应该成功
        with guard.memory_guard("test_operation", estimated_bytes=1024):
            pass
    
    def test_memory_guard_insufficient_memory(self):
        """测试内存不足情况"""
        guard = EnhancedMemoryGuard()
        
        # 请求过多内存应该抛出MemoryError
        with pytest.raises(MemoryError) as exc_info:
            with guard.memory_guard("test_operation", estimated_bytes=guard.limit_bytes + 1):
                pass
        
        # 检查错误消息包含更多信息
        error_msg = str(exc_info.value)
        assert "test_operation" in error_msg
        assert "内存不足" in error_msg
    
    def test_dataframe_memory_estimation(self):
        """测试DataFrame内存估算"""
        guard = EnhancedMemoryGuard()
        
        # 测试不同大小的估算
        small_estimate = guard.estimate_dataframe_memory(1000, 10)
        large_estimate = guard.estimate_dataframe_memory(10000, 20)
        
        assert isinstance(small_estimate, int)
        assert isinstance(large_estimate, int)
        assert large_estimate > small_estimate
        assert small_estimate > 0
    
    def test_callback_system(self):
        """测试回调系统"""
        guard = EnhancedMemoryGuard()
        callback_called = []
        
        def test_callback(stats):
            callback_called.append(stats)
        
        # 添加回调
        guard.add_callback(test_callback)
        
        # 模拟内存状态变化
        stats = guard.get_memory_stats()
        guard._notify_callbacks(stats)
        
        assert len(callback_called) == 1
        assert isinstance(callback_called[0], MemoryStats)
        
        # 移除回调
        guard.remove_callback(test_callback)
        guard._notify_callbacks(stats)
        
        # 应该没有新的调用
        assert len(callback_called) == 1
    
    def test_monitoring_start_stop(self):
        """测试监控启动和停止"""
        guard = EnhancedMemoryGuard()
        
        # 确保初始状态
        assert guard._monitoring is False
        
        # 启动监控
        guard.start_monitoring(interval_seconds=0.1)
        assert guard._monitoring is True
        assert guard._monitor_thread is not None
        
        # 等待一小段时间让监控运行
        time.sleep(0.2)
        
        # 停止监控
        guard.stop_monitoring()
        assert guard._monitoring is False
    
    def test_to_dict_representation(self):
        """测试增强型字典表示"""
        guard = EnhancedMemoryGuard()
        data_dict = guard.to_dict()
        
        # 检查基本结构
        required_keys = ['memory_stats', 'thresholds', 'monitoring', 'statistics', 'recent_cleanups', 'integrations']
        for key in required_keys:
            assert key in data_dict
        
        # 检查增强型内存统计字段
        stats = data_dict['memory_stats']
        enhanced_fields = ['pressure_level', 'cache_memory_bytes', 'queue_memory_bytes', 'system_memory_pressure']
        for field in enhanced_fields:
            assert field in stats
        
        # 检查增强型阈值字段
        thresholds = data_dict['thresholds']
        enhanced_thresholds = ['warning_threshold', 'critical_threshold', 'emergency_threshold']
        for threshold in enhanced_thresholds:
            assert threshold in thresholds
        
        # 检查统计信息
        statistics = data_dict['statistics']
        stat_fields = ['total_cleanups', 'total_freed_bytes', 'pressure_level_changes', 'emergency_cleanups']
        for field in stat_fields:
            assert field in statistics
        
        # 检查集成信息
        integrations = data_dict['integrations']
        assert 'cache_manager_registered' in integrations
        assert 'task_manager_registered' in integrations
        assert 'cleanup_callbacks_count' in integrations
    
    @patch('core.memory_guard.psutil.virtual_memory')
    def test_memory_stats_with_mock(self, mock_virtual_memory):
        """测试使用模拟数据的增强型内存统计"""
        # 设置模拟内存信息
        mock_memory = Mock()
        mock_memory.total = 8 * 1024 * 1024 * 1024  # 8GB
        mock_memory.used = 4 * 1024 * 1024 * 1024   # 4GB
        mock_memory.available = 4 * 1024 * 1024 * 1024  # 4GB
        mock_memory.percent = 50.0
        mock_virtual_memory.return_value = mock_memory
        
        guard = EnhancedMemoryGuard()
        stats = guard.get_memory_stats()
        
        assert stats.used_bytes == 4 * 1024 * 1024 * 1024
        assert stats.available_bytes == 4 * 1024 * 1024 * 1024
        assert stats.used_percent == 50.0
        
        # 测试压力级别自动检测
        assert stats.pressure_level == MemoryPressureLevel.WARNING  # 50% -> WARNING


    def test_cache_integration(self):
        """测试缓存管理器集成"""
        guard = EnhancedMemoryGuard()
        
        # 创建模拟缓存管理器
        mock_cache_manager = Mock()
        mock_cache_manager.get_stats.return_value = {
            'used_memory_human': '100MB',
            'total_keys': 1000
        }
        mock_cache_manager.clear_all.return_value = 500
        mock_cache_manager.cleanup_expired.return_value = 100
        
        # 注册缓存管理器
        guard.register_cache_manager(mock_cache_manager)
        
        # 获取统计信息
        stats = guard.get_memory_stats()
        assert stats.cache_memory_bytes is not None
        assert stats.cache_memory_bytes == 100 * 1024 * 1024  # 100MB
        
        # 测试缓存清理
        result = guard.cleanup_cache(CacheCleanupStrategy.LRU)
        assert isinstance(result, MemoryCleanupResult)
        assert result.success is True
        
        # 测试激进清理
        result = guard.cleanup_cache(CacheCleanupStrategy.AGGRESSIVE)
        assert result.items_cleaned == 500
        mock_cache_manager.clear_all.assert_called()
        
    def test_task_manager_integration(self):
        """测试任务管理器集成"""
        guard = EnhancedMemoryGuard()
        
        # 创建模拟任务管理器
        mock_task_manager = Mock()
        
        async def mock_get_stats():
            return {
                'queue_stats': {
                    'total_tasks': 50
                }
            }
        
        mock_task_manager.get_stats = mock_get_stats
        
        # 注册任务管理器
        guard.register_task_manager(mock_task_manager)
        
        # 获取统计信息
        stats = guard.get_memory_stats()
        assert stats.queue_memory_bytes is not None
        assert stats.queue_memory_bytes == 50 * 1024  # 50 tasks * 1KB each
        
    def test_cleanup_callbacks(self):
        """测试清理回调系统"""
        guard = EnhancedMemoryGuard()
        
        callback_calls = []
        
        def mock_cleanup_callback(pressure_level, freed_bytes):
            callback_calls.append((pressure_level, freed_bytes))
            return 1024 * 1024  # 模拟释放1MB
        
        # 添加清理回调
        guard.add_cleanup_callback(mock_cleanup_callback)
        
        # 模拟内存压力
        mock_stats = MemoryStats(
            used_bytes=0, available_bytes=0, used_percent=65.0,
            limit_bytes=guard.limit_bytes, rss_bytes=int(guard.limit_bytes * 0.65),
            is_critical=True
        )
        
        # 触发清理
        results = guard.handle_memory_pressure(mock_stats)
        
        # 检查回调是否被调用
        assert len(callback_calls) > 0
        pressure_level, freed_bytes = callback_calls[0]
        assert pressure_level == MemoryPressureLevel.CRITICAL
        
        # 移除回调
        guard.remove_cleanup_callback(mock_cleanup_callback)
        
    @patch('core.memory_guard.psutil.virtual_memory')
    def test_pressure_level_transitions(self, mock_virtual_memory):
        """测试内存压力级别过渡"""
        guard = EnhancedMemoryGuard()
        
        # 测试不同压力级别
        test_cases = [
            (40.0, MemoryPressureLevel.NORMAL),
            (55.0, MemoryPressureLevel.WARNING),
            (65.0, MemoryPressureLevel.CRITICAL),
            (75.0, MemoryPressureLevel.EMERGENCY)
        ]
        
        for used_percent, expected_level in test_cases:
            # 设置模拟内存信息
            mock_memory = Mock()
            mock_memory.total = 8 * 1024 * 1024 * 1024  # 8GB
            mock_memory.used = int(mock_memory.total * (used_percent / 100))
            mock_memory.available = mock_memory.total - mock_memory.used
            mock_memory.percent = used_percent
            mock_virtual_memory.return_value = mock_memory
            
            stats = guard.get_memory_stats()
            assert stats.pressure_level == expected_level, f"使用率{used_percent}%时应该是{expected_level.value}"
            
    def test_cleanup_history_tracking(self):
        """测试清理历史记录"""
        guard = EnhancedMemoryGuard()
        
        # 创建模拟缓存管理器
        mock_cache_manager = Mock()
        mock_cache_manager.clear_all.return_value = 100
        guard.register_cache_manager(mock_cache_manager)
        
        # 执行清理
        result = guard.cleanup_cache(CacheCleanupStrategy.AGGRESSIVE)
        
        # 检查历史记录
        history = guard.get_cleanup_history()
        assert len(history) == 1
        assert history[0]['strategy'] == CacheCleanupStrategy.AGGRESSIVE.value
        assert history[0]['items_cleaned'] == 100
        assert history[0]['success'] is True
        
        # 检查统计信息更新
        assert guard._stats['total_cleanups'] == 1
        
    def test_backward_compatibility(self):
        """测试向后兼容性"""
        # 确保别名正常工作
        guard = MemoryGuard()  # 使用别名
        assert isinstance(guard, EnhancedMemoryGuard)
        
        # 确保原有API仍然可用
        stats = guard.get_memory_stats()
        assert hasattr(stats, 'used_bytes')
        assert hasattr(stats, 'is_critical')
        
        # 新增功能也可用
        assert hasattr(stats, 'pressure_level')
        

if __name__ == "__main__":
    pytest.main([__file__, "-v"])