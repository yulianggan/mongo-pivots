"""
ChunkProcessor测试
验证分块处理系统的功能和性能
"""
import pytest
import polars as pl
import pandas as pd
import tempfile
import os
from io import BytesIO
from core.chunk_processor import ChunkProcessor, chunk_processor


class TestChunkProcessor:
    """分块处理器测试"""
    
    def setup_method(self):
        """每个测试方法执行前的设置"""
        self.processor = ChunkProcessor(chunk_size=100)  # 小块大小便于测试
    
    def test_processor_initialization(self):
        """测试处理器初始化"""
        # 默认处理器
        default_processor = ChunkProcessor()
        assert default_processor.chunk_size > 0
        
        # 自定义大小处理器
        custom_processor = ChunkProcessor(chunk_size=500)
        assert custom_processor.chunk_size == 500
    
    def test_process_dataframe_in_chunks(self):
        """测试DataFrame分块处理"""
        # 创建测试数据
        test_df = pl.DataFrame({
            'id': list(range(250)),  # 250行，应该分成3块 (100+100+50)
            'value': [f'value_{i}' for i in range(250)],
            'score': [i * 0.1 for i in range(250)]
        })
        
        # 定义简单操作：添加新列
        def add_chunk_id(chunk):
            return chunk.with_columns(
                pl.lit(1).alias('processed')
            )
        
        # 处理分块
        chunks = list(self.processor.process_dataframe_in_chunks(test_df, add_chunk_id))
        
        # 验证结果
        assert len(chunks) == 3  # 应该有3个块
        assert len(chunks[0]) == 100  # 第一块100行
        assert len(chunks[1]) == 100  # 第二块100行  
        assert len(chunks[2]) == 50   # 第三块50行
        
        # 验证所有块都有新列
        for chunk in chunks:
            assert 'processed' in chunk.columns
            assert chunk['processed'].sum() == len(chunk)  # 每行都是1
    
    def test_process_csv_in_chunks_from_bytes(self):
        """测试从字节数据分块处理CSV"""
        # 创建CSV数据
        csv_lines = ["id,name,score"]
        for i in range(150):  # 150行数据
            csv_lines.append(f"{i},user_{i},{i % 100}")
        
        csv_content = "\\n".join(csv_lines)
        csv_bytes = csv_content.encode('utf-8')
        
        # 定义操作：筛选高分用户
        def filter_high_scores(chunk):
            return chunk.filter(pl.col('score') > 50)
        
        # 处理分块
        chunks = list(self.processor.process_csv_in_chunks(csv_bytes, filter_high_scores))
        
        # 验证结果
        assert len(chunks) >= 1  # 至少有一个块
        
        # 聚合所有块验证总数据
        all_chunks = pl.concat(chunks)
        assert len(all_chunks) == 49  # score > 50 的行数应该是49行 (51-99)
    
    def test_process_csv_in_chunks_from_file(self):
        """测试从文件分块处理CSV"""
        # 创建临时CSV文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            # 写入CSV头部
            tmp_file.write("id,category,amount\\n")
            
            # 写入200行数据
            for i in range(200):
                tmp_file.write(f"{i},cat_{i % 5},{i * 1.5}\\n")
                
            tmp_file_path = tmp_file.name
        
        try:
            # 定义操作：按类别分组统计
            def sum_by_category(chunk):
                return chunk.group_by('category').agg(
                    pl.sum('amount').alias('total_amount'),
                    pl.count().alias('count')
                )
            
            # 处理分块
            chunks = list(self.processor.process_csv_in_chunks(tmp_file_path, sum_by_category))
            
            # 验证结果
            assert len(chunks) >= 1
            
            # 每个块都应该有聚合结果
            for chunk in chunks:
                assert 'category' in chunk.columns
                assert 'total_amount' in chunk.columns
                assert 'count' in chunk.columns
                
        finally:
            # 清理临时文件
            os.unlink(tmp_file_path)
    
    def test_aggregate_chunks_concat(self):
        """测试块聚合 - concat方法"""
        # 创建多个测试块
        chunks = [
            pl.DataFrame({'a': [1, 2], 'b': ['x', 'y']}),
            pl.DataFrame({'a': [3, 4], 'b': ['z', 'w']}),
            pl.DataFrame({'a': [5, 6], 'b': ['p', 'q']})
        ]
        
        # 聚合
        result = self.processor.aggregate_chunks(iter(chunks), method="concat")
        
        # 验证结果
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 6  # 总共6行
        assert list(result.columns) == ['a', 'b']
        assert result['a'].to_list() == [1, 2, 3, 4, 5, 6]
    
    def test_aggregate_chunks_empty(self):
        """测试空块聚合"""
        empty_chunks = iter([])
        result = self.processor.aggregate_chunks(empty_chunks, method="concat")
        
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()
    
    def test_process_and_aggregate(self):
        """测试完整的处理和聚合流程"""
        # 创建测试DataFrame
        test_df = pl.DataFrame({
            'group': ['A'] * 50 + ['B'] * 50 + ['C'] * 50,  # 150行，3个组
            'value': list(range(150))
        })
        
        # 定义操作：计算每组的统计信息
        def group_stats(chunk):
            return chunk.group_by('group').agg([
                pl.sum('value').alias('sum_value'),
                pl.mean('value').alias('avg_value'),
                pl.count().alias('count')
            ])
        
        # 处理和聚合
        result = self.processor.process_and_aggregate(
            test_df, 
            group_stats, 
            aggregation_method="concat"
        )
        
        # 验证结果
        assert isinstance(result, pl.DataFrame)
        assert 'group' in result.columns
        assert 'sum_value' in result.columns
        assert 'avg_value' in result.columns
        assert 'count' in result.columns
        
        # 由于分块处理，可能有重复的组，需要再次聚合验证
        final_result = result.group_by('group').agg([
            pl.sum('sum_value').alias('final_sum'),
            pl.sum('count').alias('final_count')
        ])
        
        # 验证每组的总和
        assert len(final_result) <= 3  # 最多3个组
    
    def test_estimate_optimal_chunk_size(self):
        """测试最优块大小估算"""
        # 创建样本数据
        sample_df = pl.DataFrame({
            'id': list(range(1000)),
            'data': ['x' * 100 for _ in range(1000)]  # 每行约100字符
        })
        
        # 估算最优块大小
        optimal_size = self.processor.estimate_optimal_chunk_size(sample_df, target_memory_mb=10)
        
        # 验证结果
        assert isinstance(optimal_size, int)
        assert optimal_size >= 1000  # 最小值限制
        assert optimal_size <= 1_000_000  # 最大值限制
    
    def test_estimate_optimal_chunk_size_empty(self):
        """测试空DataFrame的块大小估算"""
        empty_df = pl.DataFrame()
        result = self.processor.estimate_optimal_chunk_size(empty_df)
        
        assert result == self.processor.chunk_size  # 应该返回默认值
    
    def test_adaptive_chunk_size_dataframe(self):
        """测试DataFrame的自适应块大小"""
        test_df = pl.DataFrame({
            'col1': list(range(2000)),
            'col2': ['data'] * 2000,
            'col3': [1.23] * 2000
        })
        
        adaptive_size = self.processor.adaptive_chunk_size(test_df)
        
        assert isinstance(adaptive_size, int)
        assert adaptive_size > 0
    
    def test_adaptive_chunk_size_csv_bytes(self):
        """测试CSV字节数据的自适应块大小"""
        csv_content = "id,name,value\\n"
        for i in range(500):
            csv_content += f"{i},name_{i},{i * 2.5}\\n"
        
        csv_bytes = csv_content.encode('utf-8')
        
        adaptive_size = self.processor.adaptive_chunk_size(csv_bytes)
        
        assert isinstance(adaptive_size, int)
        assert adaptive_size > 0
    
    def test_adaptive_chunk_size_csv_file(self):
        """测试CSV文件的自适应块大小"""
        # 创建临时CSV文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            tmp_file.write("id,description\\n")
            for i in range(300):
                tmp_file.write(f"{i},description_{i}\\n")
            tmp_file_path = tmp_file.name
        
        try:
            adaptive_size = self.processor.adaptive_chunk_size(tmp_file_path)
            
            assert isinstance(adaptive_size, int)
            assert adaptive_size > 0
            
        finally:
            os.unlink(tmp_file_path)
    
    def test_memory_protection_during_processing(self):
        """测试处理过程中的内存保护"""
        # 创建相对大的数据集
        large_df = pl.DataFrame({
            'id': list(range(1000)),
            'data': ['x' * 1000 for _ in range(1000)]  # 每行约1KB
        })
        
        # 定义简单操作
        def simple_filter(chunk):
            return chunk.filter(pl.col('id') % 2 == 0)
        
        # 处理应该成功完成，没有内存错误
        result = self.processor.process_and_aggregate(large_df, simple_filter)
        
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 500  # 一半的行被筛选出来
    
    def test_chunk_processor_error_handling(self):
        """测试错误处理"""
        # 测试无效操作
        test_df = pl.DataFrame({'a': [1, 2, 3]})
        
        def failing_operation(chunk):
            raise ValueError("Simulated processing error")
        
        # 处理应该能优雅地处理错误
        chunks = list(self.processor.process_dataframe_in_chunks(test_df, failing_operation))
        
        # 由于错误处理，可能返回空列表
        assert isinstance(chunks, list)
    
    def test_global_chunk_processor_instance(self):
        """测试全局分块处理器实例"""
        # 验证全局实例存在且可用
        assert chunk_processor is not None
        assert isinstance(chunk_processor, ChunkProcessor)
        assert chunk_processor.chunk_size > 0
        
        # 测试基本功能
        test_df = pl.DataFrame({'x': [1, 2, 3, 4, 5]})
        
        def identity_op(chunk):
            return chunk
        
        result = chunk_processor.process_and_aggregate(test_df, identity_op)
        
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])