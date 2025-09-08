"""
MemoryGuard测试
验证内存监控和保护机制
"""
import pytest
import time
import threading
from unittest.mock import Mock, patch
from core.memory_guard import MemoryGuard, MemoryStats


class TestMemoryGuard:
    """内存守护测试"""
    
    def test_memory_stats_creation(self):
        """测试内存统计创建"""
        guard = MemoryGuard()
        stats = guard.get_memory_stats()
        
        assert isinstance(stats, MemoryStats)
        assert stats.used_bytes >= 0
        assert stats.available_bytes >= 0
        assert 0 <= stats.used_percent <= 100
        assert stats.limit_bytes > 0
        assert stats.rss_bytes >= 0
        assert isinstance(stats.is_critical, bool)
    
    def test_memory_limit_check(self):
        """测试内存限制检查"""
        guard = MemoryGuard()
        
        # 正常情况下应该在限制内
        within_limit = guard.check_memory_limit()
        assert isinstance(within_limit, bool)
    
    def test_gc_threshold_check(self):
        """测试垃圾回收阈值检查"""
        guard = MemoryGuard()
        
        threshold_reached = guard.check_gc_threshold()
        assert isinstance(threshold_reached, bool)
    
    def test_force_gc(self):
        """测试强制垃圾回收"""
        guard = MemoryGuard()
        
        # 创建一些垃圾数据
        garbage_data = [list(range(1000)) for _ in range(100)]
        
        freed_bytes = guard.force_gc()
        assert isinstance(freed_bytes, int)
        
        # 删除引用让垃圾数据可被回收
        del garbage_data
    
    def test_ensure_memory_available(self):
        """测试确保内存可用"""
        guard = MemoryGuard()
        
        # 请求合理的内存量应该成功
        small_request = 1024 * 1024  # 1MB
        available = guard.ensure_memory_available(small_request)
        assert isinstance(available, bool)
        
        # 请求过大的内存应该失败
        huge_request = guard.limit_bytes + 1
        available = guard.ensure_memory_available(huge_request)
        assert available is False
    
    def test_memory_guard_context_manager(self):
        """测试内存保护上下文管理器"""
        guard = MemoryGuard()
        
        # 正常操作应该成功
        with guard.memory_guard("test_operation") as start_stats:
            assert isinstance(start_stats, MemoryStats)
            time.sleep(0.1)  # 模拟一些工作
    
    def test_memory_guard_with_estimate(self):
        """测试带估算的内存保护"""
        guard = MemoryGuard()
        
        # 合理的内存估算应该成功
        with guard.memory_guard("test_operation", estimated_bytes=1024):
            pass
    
    def test_memory_guard_insufficient_memory(self):
        """测试内存不足情况"""
        guard = MemoryGuard()
        
        # 请求过多内存应该抛出MemoryError
        with pytest.raises(MemoryError):
            with guard.memory_guard("test_operation", estimated_bytes=guard.limit_bytes + 1):
                pass
    
    def test_dataframe_memory_estimation(self):
        """测试DataFrame内存估算"""
        guard = MemoryGuard()
        
        # 测试不同大小的估算
        small_estimate = guard.estimate_dataframe_memory(1000, 10)
        large_estimate = guard.estimate_dataframe_memory(10000, 20)
        
        assert isinstance(small_estimate, int)
        assert isinstance(large_estimate, int)
        assert large_estimate > small_estimate
        assert small_estimate > 0
    
    def test_callback_system(self):
        """测试回调系统"""
        guard = MemoryGuard()
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
        guard = MemoryGuard()
        
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
        """测试字典表示"""
        guard = MemoryGuard()
        data_dict = guard.to_dict()
        
        assert 'memory_stats' in data_dict
        assert 'thresholds' in data_dict
        assert 'monitoring' in data_dict
        
        # 检查内存统计字段
        stats = data_dict['memory_stats']
        assert 'used_bytes' in stats
        assert 'available_bytes' in stats
        assert 'rss_bytes' in stats
        assert 'is_critical' in stats
        
        # 检查阈值字段
        thresholds = data_dict['thresholds']
        assert 'limit_bytes' in thresholds
        assert 'gc_threshold_bytes' in thresholds
    
    @patch('core.memory_guard.psutil.virtual_memory')
    def test_memory_stats_with_mock(self, mock_virtual_memory):
        """测试使用模拟数据的内存统计"""
        # 设置模拟内存信息
        mock_memory = Mock()
        mock_memory.total = 8 * 1024 * 1024 * 1024  # 8GB
        mock_memory.used = 4 * 1024 * 1024 * 1024   # 4GB
        mock_memory.available = 4 * 1024 * 1024 * 1024  # 4GB
        mock_memory.percent = 50.0
        mock_virtual_memory.return_value = mock_memory
        
        guard = MemoryGuard()
        stats = guard.get_memory_stats()
        
        assert stats.used_bytes == 4 * 1024 * 1024 * 1024
        assert stats.available_bytes == 4 * 1024 * 1024 * 1024
        assert stats.used_percent == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])