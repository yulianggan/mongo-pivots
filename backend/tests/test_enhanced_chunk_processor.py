"""
测试增强分块处理器 - 支持缓存和任务队列的功能
"""
import pytest
import polars as pl
import tempfile
import os
from unittest.mock import Mock, patch
from core.chunk_processor import chunk_processor


class TestEnhancedChunkProcessor:
    """测试增强分块处理器"""
    
    def setup_method(self):
        """测试设置"""
        # 重置性能指标
        chunk_processor.reset_performance_metrics()
        # 启用缓存
        chunk_processor.set_cache_enabled(True)
        # 清理缓存
        chunk_processor.clear_cache()
    
    def test_cache_key_generation_for_files(self):
        """测试文件的缓存键生成"""
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("col1,col2\n1,a\n2,b\n")
            temp_path = f.name
        
        try:
            # 定义操作函数
            def simple_operation(df):
                return df.with_columns(pl.col("col1") * 2)
            
            kwargs = {"separator": ","}
            
            # 生成缓存键
            cache_key1 = chunk_processor._generate_cache_key(temp_path, simple_operation, kwargs)
            cache_key2 = chunk_processor._generate_cache_key(temp_path, simple_operation, kwargs)
            
            # 相同输入应生成相同缓存键
            assert cache_key1 == cache_key2
            assert len(cache_key1) == 32  # MD5哈希长度
            
            # 不同操作应生成不同缓存键
            def different_operation(df):
                return df.with_columns(pl.col("col1") * 3)
            
            cache_key3 = chunk_processor._generate_cache_key(temp_path, different_operation, kwargs)
            assert cache_key1 != cache_key3
            
        finally:
            os.unlink(temp_path)
    
    def test_cache_key_generation_for_dataframes(self):
        """测试DataFrame的缓存键生成"""
        
        df = pl.DataFrame({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"]
        })
        
        def simple_operation(df):
            return df.with_columns(pl.col("col1") * 2)
        
        # 生成缓存键
        cache_key1 = chunk_processor._generate_dataframe_cache_key(df, simple_operation)
        cache_key2 = chunk_processor._generate_dataframe_cache_key(df, simple_operation)
        
        # 相同输入应生成相同缓存键
        assert cache_key1 == cache_key2
        assert len(cache_key1) == 32
        
        # 不同DataFrame应生成不同缓存键
        df2 = pl.DataFrame({
            "col1": [1, 2, 3, 4],
            "col2": ["a", "b", "c", "d"]
        })
        
        cache_key3 = chunk_processor._generate_dataframe_cache_key(df2, simple_operation)
        assert cache_key1 != cache_key3
    
    def test_bytes_cache_key_generation(self):
        """测试字节数据的缓存键生成"""
        
        data1 = b"col1,col2\n1,a\n2,b\n"
        data2 = b"col1,col2\n1,a\n2,b\n"
        data3 = b"col1,col2\n3,c\n4,d\n"
        
        def simple_operation(df):
            return df
        
        kwargs = {}
        
        # 相同字节数据应生成相同缓存键
        cache_key1 = chunk_processor._generate_cache_key(data1, simple_operation, kwargs)
        cache_key2 = chunk_processor._generate_cache_key(data2, simple_operation, kwargs)
        assert cache_key1 == cache_key2
        
        # 不同字节数据应生成不同缓存键
        cache_key3 = chunk_processor._generate_cache_key(data3, simple_operation, kwargs)
        assert cache_key1 != cache_key3
    
    @patch('core.chunk_processor.cache_manager')
    def test_dataframe_processing_with_cache_hit(self, mock_cache_manager):
        """测试DataFrame处理时的缓存命中"""
        
        df = pl.DataFrame({
            "col1": [1, 2, 3, 4, 5],
            "col2": ["a", "b", "c", "d", "e"]
        })
        
        def simple_operation(df):
            return df.with_columns(pl.col("col1") * 2)
        
        # 模拟缓存命中
        cached_result = [
            pl.DataFrame({"col1": [2, 4], "col2": ["a", "b"]}),
            pl.DataFrame({"col1": [6, 8], "col2": ["c", "d"]}),
            pl.DataFrame({"col1": [10], "col2": ["e"]})
        ]
        mock_cache_manager.get_bulk.return_value = cached_result
        
        # 设置小的chunk_size以触发分块
        chunk_processor.chunk_size = 2
        
        # 处理DataFrame
        results = list(chunk_processor.process_dataframe_in_chunks(df, simple_operation))
        
        # 验证结果
        assert len(results) == 3
        assert mock_cache_manager.get_bulk.called
        
        # 验证性能指标
        metrics = chunk_processor.get_performance_metrics()
        assert metrics['cache_hits'] == 1
        assert metrics['cache_misses'] == 0
    
    @patch('core.chunk_processor.cache_manager')
    def test_dataframe_processing_with_cache_miss(self, mock_cache_manager):
        """测试DataFrame处理时的缓存未命中"""
        
        df = pl.DataFrame({
            "col1": [1, 2, 3, 4, 5],
            "col2": ["a", "b", "c", "d", "e"]
        })
        
        def simple_operation(df):
            return df.with_columns(pl.col("col1") * 2)
        
        # 模拟缓存未命中
        mock_cache_manager.get_bulk.return_value = None
        
        # 设置小的chunk_size以触发分块
        chunk_processor.chunk_size = 2
        
        # 处理DataFrame
        results = list(chunk_processor.process_dataframe_in_chunks(df, simple_operation))
        
        # 验证结果
        assert len(results) == 3
        for result in results:
            assert isinstance(result, pl.DataFrame)
        
        # 验证缓存调用
        assert mock_cache_manager.get_bulk.called
        assert mock_cache_manager.set_bulk.called
        
        # 验证性能指标
        metrics = chunk_processor.get_performance_metrics()
        assert metrics['cache_hits'] == 0
        assert metrics['cache_misses'] == 1
        assert metrics['chunks_processed'] == 3
    
    @patch('core.chunk_processor.task_manager')
    def test_task_queue_limit_check(self, mock_task_manager):
        """测试任务队列限制检查"""
        
        df = pl.DataFrame({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"]
        })
        
        def simple_operation(df):
            return df
        
        # 模拟用户达到任务限制
        mock_session = Mock()
        mock_session.can_accept_task = False
        mock_task_manager.get_or_create_session.return_value = mock_session
        
        # 尝试处理应该抛出异常
        with pytest.raises(RuntimeError, match="has reached maximum concurrent tasks"):
            list(chunk_processor.process_dataframe_in_chunks(
                df, simple_operation, user_id="test_user"
            ))
        
        mock_task_manager.get_or_create_session.assert_called_with("test_user")
    
    def test_csv_processing_with_bytes(self):
        """测试字节数据的CSV处理"""
        
        csv_data = b"col1,col2\n1,a\n2,b\n3,c\n4,d\n5,e\n"
        
        def simple_operation(df):
            return df.with_columns(pl.col("col1") * 2)
        
        # 设置小的chunk_size
        original_chunk_size = chunk_processor.chunk_size
        chunk_processor.chunk_size = 2
        
        try:
            # 处理字节数据
            results = list(chunk_processor.process_csv_in_chunks(
                csv_data, simple_operation, enable_cache=False
            ))
            
            # 验证结果
            assert len(results) > 0
            for result in results:
                assert isinstance(result, pl.DataFrame)
                assert "col1" in result.columns
                assert "col2" in result.columns
        
        finally:
            chunk_processor.chunk_size = original_chunk_size
    
    def test_performance_metrics_tracking(self):
        """测试性能指标跟踪"""
        
        df = pl.DataFrame({
            "col1": [1, 2, 3, 4, 5],
            "col2": ["a", "b", "c", "d", "e"]
        })
        
        def simple_operation(df):
            return df.with_columns(pl.col("col1") * 2)
        
        # 重置指标
        chunk_processor.reset_performance_metrics()
        
        # 设置小的chunk_size
        original_chunk_size = chunk_processor.chunk_size
        chunk_processor.chunk_size = 2
        
        try:
            # 处理DataFrame（禁用缓存以确保处理）
            list(chunk_processor.process_dataframe_in_chunks(
                df, simple_operation, enable_cache=False
            ))
            
            # 检查性能指标
            metrics = chunk_processor.get_performance_metrics()
            
            assert metrics['chunks_processed'] == 3
            assert metrics['processing_time'] > 0
            assert metrics['avg_processing_time'] > 0
            assert 'timestamp' in metrics
            assert 'cache_hit_rate' in metrics
        
        finally:
            chunk_processor.chunk_size = original_chunk_size
    
    def test_cache_management_methods(self):
        """测试缓存管理方法"""
        
        # 测试缓存启用/禁用
        chunk_processor.set_cache_enabled(False)
        assert not chunk_processor._enable_cache
        
        chunk_processor.set_cache_enabled(True)
        assert chunk_processor._enable_cache
        
        # 测试TTL设置
        chunk_processor.set_cache_ttl(7200)
        assert chunk_processor._cache_ttl == 7200
        
        # 测试性能指标重置
        chunk_processor._performance_metrics['cache_hits'] = 10
        chunk_processor.reset_performance_metrics()
        assert chunk_processor._performance_metrics['cache_hits'] == 0
    
    @patch('core.chunk_processor.cache_manager')
    def test_cache_stats_retrieval(self, mock_cache_manager):
        """测试缓存统计获取"""
        
        # 模拟缓存键
        mock_cache_manager.get_keys_by_pattern.return_value = [
            "chunk_csv:key1", "chunk_df:key2", "chunk_csv:key3"
        ]
        
        # 获取缓存统计
        stats = chunk_processor.get_cache_stats()
        
        # 验证统计信息
        assert stats['total_chunk_cache_keys'] == 3
        assert stats['cache_enabled'] == chunk_processor._enable_cache
        assert stats['cache_ttl'] == chunk_processor._cache_ttl
        assert 'performance_metrics' in stats
        
        mock_cache_manager.get_keys_by_pattern.assert_called_with("chunk_*")
    
    @patch('core.chunk_processor.cache_manager')
    def test_cache_clearing(self, mock_cache_manager):
        """测试缓存清理"""
        
        # 清理所有分块缓存
        chunk_processor.clear_cache()
        mock_cache_manager.delete_pattern.assert_called_with("chunk_*")
        
        # 清理特定模式的缓存
        chunk_processor.clear_cache("csv")
        mock_cache_manager.delete_pattern.assert_called_with("chunk_*csv*")
    
    def test_process_and_aggregate_with_cache(self):
        """测试带缓存的处理和聚合"""
        
        df = pl.DataFrame({
            "col1": [1, 2, 3, 4, 5],
            "col2": ["a", "b", "c", "d", "e"]
        })
        
        def simple_operation(df):
            return df.with_columns(pl.col("col1") * 2)
        
        # 设置小的chunk_size
        original_chunk_size = chunk_processor.chunk_size
        chunk_processor.chunk_size = 2
        
        try:
            # 处理并聚合
            result = chunk_processor.process_and_aggregate(
                df, simple_operation, enable_cache=False, user_id="test_user"
            )
            
            # 验证结果
            assert isinstance(result, pl.DataFrame)
            assert len(result) == 5
            assert "col1" in result.columns
            assert "col2" in result.columns
            
            # 验证col1被乘以2
            expected_col1 = [2, 4, 6, 8, 10]
            assert result["col1"].to_list() == expected_col1
        
        finally:
            chunk_processor.chunk_size = original_chunk_size


if __name__ == "__main__":
    pytest.main([__file__, "-v"])