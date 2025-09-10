"""
Issue #5集成测试 - Redis缓存系统
测试所有5个并行流的集成：
- Stream A: Redis缓存管理器
- Stream B: 任务队列管理
- Stream C: 内存护栏机制
- Stream D: 分块处理器增强
- Stream E: 性能监控配置
"""

import pytest
import asyncio
import time
import polars as pl
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from core.redis_cache import CacheManager, cache_manager
from core.task_queue import TaskManager, Task, TaskPriority, UserSession
from core.memory_guard import MemoryGuard, memory_guard
from core.chunk_processor import chunk_processor
from core.performance_monitor import PerformanceMonitor, MetricType


class TestIssue5Integration:
    """Issue #5集成测试"""
    
    def setup_method(self):
        """测试设置"""
        # 重置所有组件状态
        chunk_processor.reset_performance_metrics()
        chunk_processor.clear_cache()
        # memory_guard没有reset_stats方法，只能获取当前状态
        
        # 设置性能监控（禁用系统指标和告警避免测试干扰）
        self.performance_monitor = PerformanceMonitor({
            'enable_system_metrics': False,
            'enable_alerts': False
        })
    
    @patch('core.redis_cache.redis.Redis')
    def test_redis_cache_integration(self, mock_redis_class):
        """测试Redis缓存管理器集成"""
        # 模拟Redis客户端
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.keys.return_value = [b'test_key1', b'test_key2']
        mock_redis_class.return_value = mock_redis
        
        # 创建缓存管理器
        cache = CacheManager()
        
        # 测试缓存可用性
        assert cache.is_available()
        
        # 测试设置和获取
        assert cache.set("test_key", {"data": "test_value"}, ttl_hours=1)
        
        # 模拟缓存命中
        mock_redis.get.return_value = b'{"data": "test_value"}'
        result = cache.get("test_key")
        assert result == {"data": "test_value"}
        
        # 测试删除
        assert cache.delete("test_key")
        
        # 测试统计信息
        stats = cache.get_stats()
        assert 'redis_version' in stats or 'error' in stats
    
    @pytest.mark.asyncio
    async def test_task_queue_integration(self):
        """测试任务队列管理集成"""
        # 创建任务管理器
        task_manager = TaskManager(max_workers=2)
        
        # 启动任务管理器
        await task_manager.start()
        
        try:
            # 创建用户会话
            session = task_manager.get_or_create_session("test_user")
            assert session.user_id == "test_user"
            assert session.can_accept_task
            assert session.can_start_task
            
            # 创建测试任务
            def test_function(x, y):
                return x + y
            
            task = Task(
                user_id="test_user",
                name="test_task",
                description="Test addition task",
                priority=TaskPriority.NORMAL,
                func=test_function,
                args=(3, 5),
                timeout_seconds=10
            )
            
            # 提交任务
            success = await task_manager._task_queue.enqueue(task)
            assert success
            
            # 等待任务执行
            await asyncio.sleep(0.5)
            
            # 检查任务状态
            task_status = await task_manager.get_task_status(task.id)
            assert task_status is not None
            
            # 获取统计信息
            stats = await task_manager.get_stats()
            assert 'tasks_submitted' in stats
            assert stats['workers_active'] <= 2
            
        finally:
            await task_manager.stop()
    
    def test_memory_guard_integration(self):
        """测试内存护栏机制集成"""
        # 测试内存检查
        try:
            memory_guard.ensure_memory_available(1024*1024)  # 1MB
            memory_available = True
        except RuntimeError:
            memory_available = False
        assert memory_available  # 在正常情况下应该有足够内存
        
        # 测试内存使用监控
        with memory_guard.memory_guard("test_operation", estimated_bytes=1024*1024):
            # 模拟一些内存使用
            test_data = [i for i in range(1000)]
            assert len(test_data) == 1000
        
        # 测试内存估算
        df_memory = memory_guard.estimate_dataframe_memory(1000, 10)
        assert df_memory > 0
        
        # 测试内存压力检测
        memory_pressure = memory_guard.get_memory_pressure()
        assert 0 <= memory_pressure <= 1.0
        
        # 测试统计信息
        stats = memory_guard.get_memory_stats()
        assert hasattr(stats, 'used_bytes')
        assert hasattr(stats, 'available_bytes')
        assert hasattr(stats, 'used_percent')
        assert hasattr(stats, 'pressure_level')
    
    def test_enhanced_chunk_processor_integration(self):
        """测试增强分块处理器集成"""
        # 创建测试数据
        df = pl.DataFrame({
            "id": range(1000),
            "value": [i * 2 for i in range(1000)],
            "category": [f"cat_{i % 10}" for i in range(1000)]
        })
        
        def test_operation(chunk_df):
            """测试操作：计算value的平方"""
            return chunk_df.with_columns(
                pl.col("value").pow(2).alias("value_squared")
            )
        
        # 设置较小的chunk_size进行测试
        original_chunk_size = chunk_processor.chunk_size
        chunk_processor.chunk_size = 200
        
        try:
            # 测试缓存功能（禁用缓存）
            results = chunk_processor.process_and_aggregate(
                df, test_operation, enable_cache=False, user_id="test_user"
            )
            
            # 验证结果
            assert isinstance(results, pl.DataFrame)
            assert len(results) == 1000
            assert "value_squared" in results.columns
            
            # 验证计算正确性
            expected_first_value = (0 * 2) ** 2  # 0
            expected_last_value = (999 * 2) ** 2  # (1998)^2
            assert results[0, "value_squared"] == expected_first_value
            assert results[999, "value_squared"] == expected_last_value
            
            # 测试性能指标
            metrics = chunk_processor.get_performance_metrics()
            assert metrics['chunks_processed'] > 0
            assert metrics['processing_time'] > 0
            assert metrics['avg_processing_time'] > 0
            
            # 测试缓存统计
            cache_stats = chunk_processor.get_cache_stats()
            assert 'total_chunk_cache_keys' in cache_stats
            assert 'cache_enabled' in cache_stats
            
        finally:
            chunk_processor.chunk_size = original_chunk_size
    
    def test_performance_monitor_integration(self):
        """测试性能监控配置集成"""
        # 记录不同类型的指标
        self.performance_monitor.record_metric("test.counter", 5, MetricType.COUNTER)
        self.performance_monitor.record_metric("test.gauge", 42.5, MetricType.GAUGE)
        self.performance_monitor.record_metric("test.histogram", 100, MetricType.HISTOGRAM)
        
        # 测试计时器
        with self.performance_monitor.timer("test.operation"):
            time.sleep(0.01)
        
        # 获取指标汇总
        summary = self.performance_monitor.get_metrics_summary()
        assert 'timestamp' in summary
        assert 'total_metrics' in summary
        assert summary['total_metrics'] > 0
        
        # 生成性能报告
        report = self.performance_monitor.get_performance_report(hours=1)
        assert 'timestamp' in report
        assert 'metrics' in report
        assert 'alerts' in report
        assert 'summary' in report
        
        # 导出指标
        exported = self.performance_monitor.export_metrics()
        assert isinstance(exported, str)
        assert '"test.counter"' in exported
    
    def test_csv_processing_with_all_components(self):
        """测试CSV处理与所有组件的集成"""
        # 创建临时CSV文件
        csv_data = """id,name,value,category
1,item1,10.5,A
2,item2,20.3,B
3,item3,15.7,A
4,item4,25.1,C
5,item5,30.9,B
6,item6,12.3,A
7,item7,18.5,C
8,item8,22.7,B
9,item9,35.2,A
10,item10,28.4,C"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            temp_csv_path = f.name
        
        try:
            def processing_operation(df):
                """处理操作：计算value的统计信息"""
                return df.with_columns([
                    (pl.col("value") * 2).alias("value_doubled"),
                    pl.col("category").str.to_lowercase().alias("category_lower")
                ])
            
            # 使用性能监控装饰器
            with self.performance_monitor.timer("csv_processing"):
                # 使用内存护栏
                with memory_guard.memory_guard("csv_processing", estimated_bytes=1024*1024):
                    # 使用增强分块处理器（禁用缓存避免Redis依赖）
                    result = chunk_processor.process_and_aggregate(
                        temp_csv_path,
                        processing_operation,
                        enable_cache=False,
                        user_id="test_user"
                    )
            
            # 验证处理结果
            assert isinstance(result, pl.DataFrame)
            assert len(result) == 10
            assert "value_doubled" in result.columns
            assert "category_lower" in result.columns
            
            # 验证数据正确性
            first_row = result[0]
            assert first_row["value_doubled"][0] == 21.0  # 10.5 * 2
            assert first_row["category_lower"][0] == "a"
            
            # 检查性能指标
            timer_value = self.performance_monitor.collector.get_latest_value("csv_processing")
            assert timer_value is not None
            assert timer_value > 0
            
            # 检查内存使用统计
            memory_stats = memory_guard.get_memory_stats()
            assert memory_stats.used_bytes >= 0
            
            # 检查分块处理器指标
            chunk_metrics = chunk_processor.get_performance_metrics()
            assert chunk_metrics['chunks_processed'] > 0
            
        finally:
            os.unlink(temp_csv_path)
    
    @patch('core.redis_cache.redis.Redis')
    def test_full_system_integration(self, mock_redis_class):
        """测试完整系统集成"""
        # 模拟Redis
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        mock_redis.setex.return_value = True
        mock_redis_class.return_value = mock_redis
        
        # 创建测试数据
        df = pl.DataFrame({
            "sensor_id": [f"sensor_{i%5}" for i in range(500)],
            "timestamp": [f"2024-01-{i%30+1:02d}T10:00:00" for i in range(500)],
            "temperature": [20 + (i % 50) + (i * 0.1) for i in range(500)],
            "humidity": [40 + (i % 40) + (i * 0.05) for i in range(500)]
        })
        
        def complex_processing(chunk_df):
            """复杂数据处理操作"""
            return chunk_df.with_columns([
                # 温度转换为华氏度
                (pl.col("temperature") * 9/5 + 32).alias("temp_fahrenheit"),
                # 计算舒适度指数
                (pl.col("temperature") + pl.col("humidity") / 10).alias("comfort_index"),
                # 传感器类型
                pl.col("sensor_id").str.extract(r"sensor_(\d+)").alias("sensor_type")
            ])
        
        # 设置小的chunk_size
        original_chunk_size = chunk_processor.chunk_size
        chunk_processor.chunk_size = 100
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 使用所有组件进行处理
            with self.performance_monitor.timer("full_system_processing"):
                with memory_guard.memory_guard("full_system", estimated_bytes=2*1024*1024):
                    result = chunk_processor.process_and_aggregate(
                        df, 
                        complex_processing,
                        enable_cache=True,  # 启用缓存
                        user_id="integration_test_user"
                    )
            
            processing_time = time.time() - start_time
            
            # 验证处理结果
            assert isinstance(result, pl.DataFrame)
            assert len(result) == 500
            assert "temp_fahrenheit" in result.columns
            assert "comfort_index" in result.columns
            assert "sensor_type" in result.columns
            
            # 验证数据正确性
            first_temp_c = result[0, "temperature"]
            first_temp_f = result[0, "temp_fahrenheit"]
            expected_temp_f = first_temp_c * 9/5 + 32
            assert abs(first_temp_f - expected_temp_f) < 0.001
            
            # 记录处理完成指标
            self.performance_monitor.record_metric(
                "integration.records_processed", 
                len(result), 
                MetricType.COUNTER
            )
            self.performance_monitor.record_metric(
                "integration.processing_time", 
                processing_time, 
                MetricType.TIMER
            )
            
            # 生成综合报告
            performance_report = self.performance_monitor.get_performance_report()
            memory_stats = memory_guard.get_memory_stats()
            chunk_metrics = chunk_processor.get_performance_metrics()
            
            # 验证所有组件都有活动
            assert performance_report['summary']['total_metrics'] > 0
            assert memory_stats.used_bytes >= 0
            assert chunk_metrics['chunks_processed'] > 0
            
            # 打印集成测试摘要
            print(f"\n=== Issue #5集成测试摘要 ===")
            print(f"处理记录数: {len(result)}")
            print(f"处理时间: {processing_time:.3f}秒")
            print(f"分块数量: {chunk_metrics['chunks_processed']}")
            print(f"内存使用: {memory_stats.used_bytes / 1024 / 1024:.1f}MB ({memory_stats.used_percent:.1f}%)")
            print(f"性能指标: {performance_report['summary']['total_metrics']}")
            print(f"缓存命中率: {chunk_metrics['cache_hit_rate']:.2%}")
            
        finally:
            chunk_processor.chunk_size = original_chunk_size
    
    def test_error_handling_integration(self):
        """测试错误处理集成"""
        def failing_operation(df):
            """故意失败的操作"""
            raise ValueError("Simulated processing error")
        
        df = pl.DataFrame({"col1": [1, 2, 3]})
        
        # 测试错误处理
        with pytest.raises(ValueError):
            chunk_processor.process_and_aggregate(
                df, failing_operation, enable_cache=False
            )
        
        # 验证性能监控记录了错误
        # 这里可以扩展添加错误指标的检查
    
    def test_concurrent_processing(self):
        """测试并发处理能力"""
        import threading
        
        results = []
        errors = []
        
        def worker_function(worker_id):
            """工作线程函数"""
            try:
                df = pl.DataFrame({
                    "worker_id": [worker_id] * 100,
                    "data": range(100),
                    "timestamp": [f"2024-01-01T{i%24:02d}:00:00" for i in range(100)]
                })
                
                def process_data(chunk_df):
                    return chunk_df.with_columns(
                        (pl.col("data") * worker_id).alias("processed_data")
                    )
                
                with self.performance_monitor.timer(f"worker_{worker_id}"):
                    result = chunk_processor.process_and_aggregate(
                        df, process_data, enable_cache=False, user_id=f"worker_{worker_id}"
                    )
                
                results.append((worker_id, len(result)))
                
            except Exception as e:
                errors.append((worker_id, str(e)))
        
        # 启动多个工作线程
        threads = []
        for i in range(3):
            thread = threading.Thread(target=worker_function, args=(i,))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join(timeout=10)
        
        # 验证结果
        assert len(results) == 3
        assert len(errors) == 0
        
        # 验证每个worker都处理了正确数量的记录
        for worker_id, record_count in results:
            assert record_count == 100
        
        # 检查性能指标
        for i in range(3):
            timer_value = self.performance_monitor.collector.get_latest_value(f"worker_{i}")
            assert timer_value is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])