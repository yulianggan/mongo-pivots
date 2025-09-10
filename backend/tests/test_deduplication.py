"""
测试去重引擎(DeduplicationEngine)的完整功能
包含：基础功能、边界条件、性能测试、内存管理、错误处理等全面测试场景
"""
import pytest
import polars as pl
import hashlib
from decimal import Decimal
from datetime import datetime, date
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import gc
import psutil
import os

from processors.deduplication import (
    DeduplicationEngine,
    DeduplicationConfig,
    MatchType,
    MergeStrategy,
    DeduplicationResult,
    KeyGenerator,
    DuplicateDetector,
    MergeProcessor
)
from backend.core.memory_guard import MemoryGuard
from backend.core.chunk_processor import ChunkProcessor
from backend.core.data_engine import DataEngine


class TestKeyGenerator:
    """测试MD5键生成器"""

    @pytest.fixture
    def generator(self):
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        return KeyGenerator(config)

    def test_generate_simple_key(self, generator):
        """测试简单键生成"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob'],
            'email': ['alice@test.com', 'bob@test.com'],
            'age': [25, 30]
        })
        
        keys = generator.generate_keys(df)
        assert len(keys) == 2
        assert all(isinstance(key, str) for key in keys)
        assert all(len(key) == 32 for key in keys)  # MD5长度

    def test_generate_key_with_nulls(self, generator):
        """测试包含空值的键生成"""
        df = pl.DataFrame({
            'name': ['Alice', None, 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', None],
            'age': [25, 30, 35]
        })
        
        keys = generator.generate_keys(df)
        assert len(keys) == 3
        # 空值应该被替换为配置的占位符
        assert keys[1] != keys[0]  # 不同的键值

    def test_generate_key_ignore_case(self):
        """测试忽略大小写的键生成"""
        config = DeduplicationConfig(
            columns=['name'],
            ignore_case=True,
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        generator = KeyGenerator(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'ALICE', 'alice'],
            'email': ['a@test.com', 'b@test.com', 'c@test.com']
        })
        
        keys = generator.generate_keys(df)
        # 所有键应该相同（忽略大小写）
        assert keys[0] == keys[1] == keys[2]

    def test_generate_key_multiple_columns(self, generator):
        """测试多列键生成"""
        df = pl.DataFrame({
            'name': ['Alice', 'Alice', 'Bob'],
            'email': ['alice@test.com', 'alice2@test.com', 'bob@test.com'],
            'age': [25, 25, 30]
        })
        
        keys = generator.generate_keys(df)
        # 同名但不同邮箱应该有不同键
        assert keys[0] != keys[1]
        assert keys[1] != keys[2]

    def test_generate_key_empty_dataframe(self, generator):
        """测试空数据框的键生成"""
        df = pl.DataFrame({
            'name': [],
            'email': []
        })
        
        keys = generator.generate_keys(df)
        assert len(keys) == 0

    def test_generate_key_special_characters(self, generator):
        """测试特殊字符的键生成"""
        df = pl.DataFrame({
            'name': ['O\'Reilly', 'Smith & Co', 'Test,Inc.'],
            'email': ['test@test.com', 'test2@test.com', 'test3@test.com']
        })
        
        keys = generator.generate_keys(df)
        assert len(keys) == 3
        assert all(len(key) == 32 for key in keys)


class TestDuplicateDetector:
    """测试重复记录检测器"""

    @pytest.fixture
    def detector(self):
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        return DuplicateDetector(config)

    def test_detect_exact_duplicates(self, detector):
        """测试精确重复检测"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice', 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', 'alice@test.com', 'charlie@test.com'],
            'age': [25, 30, 25, 35]
        })
        
        duplicate_groups = detector.detect_duplicates(df)
        
        # 应该有一个重复组（Alice）
        assert len(duplicate_groups) == 1
        assert set(duplicate_groups[0]) == {0, 2}  # 行索引0和2

    def test_detect_no_duplicates(self, detector):
        """测试无重复数据"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', 'charlie@test.com'],
            'age': [25, 30, 35]
        })
        
        duplicate_groups = detector.detect_duplicates(df)
        assert len(duplicate_groups) == 0

    def test_detect_multiple_duplicate_groups(self, detector):
        """测试多个重复组"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice', 'Bob', 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', 'alice@test.com', 'bob@test.com', 'charlie@test.com'],
            'age': [25, 30, 25, 30, 35]
        })
        
        duplicate_groups = detector.detect_duplicates(df)
        
        # 应该有两个重复组
        assert len(duplicate_groups) == 2
        groups_set = {frozenset(group) for group in duplicate_groups}
        expected_groups = {frozenset([0, 2]), frozenset([1, 3])}
        assert groups_set == expected_groups

    @patch('backend.processors.deduplication.DuplicateDetector._detect_similarity_duplicates')
    def test_detect_similarity_duplicates(self, mock_similarity, detector):
        """测试相似度重复检测"""
        detector.config.match_type = MatchType.SIMILARITY
        
        df = pl.DataFrame({
            'name': ['Alice', 'Allice', 'Bob'],  # Alice 和 Allice 相似
            'email': ['alice@test.com', 'alice2@test.com', 'bob@test.com']
        })
        
        # Mock相似度检测返回结果
        mock_similarity.return_value = [[0, 1]]
        
        duplicate_groups = detector.detect_duplicates(df)
        
        mock_similarity.assert_called_once_with(df)
        assert len(duplicate_groups) == 1
        assert set(duplicate_groups[0]) == {0, 1}

    def test_detect_duplicates_single_row(self, detector):
        """测试单行数据"""
        df = pl.DataFrame({
            'name': ['Alice'],
            'email': ['alice@test.com']
        })
        
        duplicate_groups = detector.detect_duplicates(df)
        assert len(duplicate_groups) == 0


class TestMergeProcessor:
    """测试合并处理器"""

    @pytest.fixture
    def processor(self):
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.MERGE_FIELDS
        )
        return MergeProcessor(config)

    def test_merge_keep_first(self):
        """测试保持第一条策略"""
        config = DeduplicationConfig(
            columns=['name'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        processor = MergeProcessor(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'Alice', 'Alice'],
            'age': [25, 30, 35],
            'city': ['NY', 'LA', 'SF']
        })
        
        duplicate_groups = [[0, 1, 2]]
        result_df = processor.process_duplicates(df, duplicate_groups)
        
        assert len(result_df) == 1
        assert result_df['age'][0] == 25  # 保持第一条
        assert result_df['city'][0] == 'NY'

    def test_merge_keep_last(self):
        """测试保持最后条策略"""
        config = DeduplicationConfig(
            columns=['name'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_LAST
        )
        processor = MergeProcessor(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'Alice', 'Alice'],
            'age': [25, 30, 35],
            'city': ['NY', 'LA', 'SF']
        })
        
        duplicate_groups = [[0, 1, 2]]
        result_df = processor.process_duplicates(df, duplicate_groups)
        
        assert len(result_df) == 1
        assert result_df['age'][0] == 35  # 保持最后条
        assert result_df['city'][0] == 'SF'

    def test_merge_fields_strategy(self, processor):
        """测试字段合并策略"""
        df = pl.DataFrame({
            'name': ['Alice', 'Alice'],
            'age': [None, 30],
            'city': ['NY', None],
            'score': [85, 90]
        })
        
        duplicate_groups = [[0, 1]]
        result_df = processor.process_duplicates(df, duplicate_groups)
        
        assert len(result_df) == 1
        assert result_df['name'][0] == 'Alice'
        assert result_df['age'][0] == 30  # 非空值
        assert result_df['city'][0] == 'NY'  # 非空值
        assert result_df['score'][0] == 85  # 第一个非空值

    def test_merge_custom_strategy(self):
        """测试自定义合并策略"""
        def custom_merge(group_df: pl.DataFrame) -> pl.DataFrame:
            # 自定义逻辑：取最大年龄的记录
            max_age_idx = group_df['age'].arg_max()
            return group_df.slice(max_age_idx, 1)
        
        config = DeduplicationConfig(
            columns=['name'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.CUSTOM,
            custom_merge_func=custom_merge
        )
        processor = MergeProcessor(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'Alice', 'Alice'],
            'age': [25, 35, 30],
            'city': ['NY', 'LA', 'SF']
        })
        
        duplicate_groups = [[0, 1, 2]]
        result_df = processor.process_duplicates(df, duplicate_groups)
        
        assert len(result_df) == 1
        assert result_df['age'][0] == 35  # 最大年龄
        assert result_df['city'][0] == 'LA'

    def test_merge_no_duplicates(self, processor):
        """测试无重复数据的合并"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Charlie'],
            'age': [25, 30, 35]
        })
        
        duplicate_groups = []
        result_df = processor.process_duplicates(df, duplicate_groups)
        
        assert len(result_df) == 3  # 保持原样
        assert result_df.equals(df)

    def test_merge_multiple_groups(self, processor):
        """测试多个重复组的合并"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice', 'Bob', 'Charlie'],
            'age': [25, None, None, 35, 40],
            'city': [None, 'NY', 'LA', None, 'SF']
        })
        
        duplicate_groups = [[0, 2], [1, 3]]
        result_df = processor.process_duplicates(df, duplicate_groups)
        
        assert len(result_df) == 3  # 5行 -> 3行（两个组合并）
        
        # 验证合并结果
        names = result_df['name'].to_list()
        assert 'Alice' in names
        assert 'Bob' in names
        assert 'Charlie' in names


class TestDeduplicationEngine:
    """测试去重引擎主类"""

    @pytest.fixture
    def engine(self):
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        return DeduplicationEngine(config)

    def test_engine_initialization(self, engine):
        """测试引擎初始化"""
        assert engine.config is not None
        assert engine.key_generator is not None
        assert engine.duplicate_detector is not None
        assert engine.merge_processor is not None
        assert engine.memory_guard is not None

    def test_deduplicate_simple_case(self, engine):
        """测试简单去重场景"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice', 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', 'alice@test.com', 'charlie@test.com'],
            'age': [25, 30, 28, 35]
        })
        
        result = engine.deduplicate(df)
        
        assert isinstance(result, DeduplicationResult)
        assert len(result.deduplicated_df) == 3  # 去除1个重复
        assert result.duplicates_removed == 1
        assert result.duplicates_found == 1
        assert 'Alice' in result.deduplicated_df['name'].to_list()

    def test_deduplicate_no_duplicates(self, engine):
        """测试无重复数据"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', 'charlie@test.com'],
            'age': [25, 30, 35]
        })
        
        result = engine.deduplicate(df)
        
        assert len(result.deduplicated_df) == 3
        assert result.duplicates_removed == 0
        assert result.duplicates_found == 0

    def test_deduplicate_empty_dataframe(self, engine):
        """测试空数据框"""
        df = pl.DataFrame({
            'name': [],
            'email': []
        })
        
        result = engine.deduplicate(df)
        
        assert len(result.deduplicated_df) == 0
        assert result.duplicates_removed == 0
        assert result.duplicates_found == 0

    def test_deduplicate_all_duplicates(self, engine):
        """测试全部为重复的数据"""
        df = pl.DataFrame({
            'name': ['Alice'] * 5,
            'email': ['alice@test.com'] * 5,
            'age': [25, 26, 27, 28, 29]
        })
        
        result = engine.deduplicate(df)
        
        assert len(result.deduplicated_df) == 1
        assert result.duplicates_removed == 4
        assert result.duplicates_found == 1  # 一个重复组

    def test_deduplicate_single_row(self, engine):
        """测试单行数据"""
        df = pl.DataFrame({
            'name': ['Alice'],
            'email': ['alice@test.com'],
            'age': [25]
        })
        
        result = engine.deduplicate(df)
        
        assert len(result.deduplicated_df) == 1
        assert result.duplicates_removed == 0
        assert result.duplicates_found == 0

    @pytest.mark.asyncio
    async def test_deduplicate_async(self, engine):
        """测试异步去重"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice'],
            'email': ['alice@test.com', 'bob@test.com', 'alice@test.com'],
            'age': [25, 30, 28]
        })
        
        result = await engine.deduplicate_async(df)
        
        assert isinstance(result, DeduplicationResult)
        assert len(result.deduplicated_df) == 2
        assert result.duplicates_removed == 1

    def test_statistics_tracking(self, engine):
        """测试统计信息跟踪"""
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice', 'Charlie'],
            'email': ['alice@test.com', 'bob@test.com', 'alice@test.com', 'charlie@test.com'],
            'age': [25, 30, 28, 35]
        })
        
        result = engine.deduplicate(df)
        
        # 验证统计信息
        assert result.execution_time_ms > 0
        assert result.memory_used_mb >= 0
        assert result.accuracy_estimate > 0
        assert result.original_rows == 4
        assert result.final_rows == 3
        assert result.duplicates_removed == 1
        assert result.duplicates_found == 1

    def test_memory_estimation(self, engine):
        """测试内存估算"""
        df = pl.DataFrame({
            'name': ['Alice'] * 1000,
            'email': ['alice@test.com'] * 1000,
            'age': list(range(1000))
        })
        
        estimated_memory = engine._estimate_operation_memory(df)
        assert estimated_memory > 0
        
        # 内存估算应该合理（不过大或过小）
        df_size = df.estimated_size()
        assert 0.5 * df_size <= estimated_memory <= 5 * df_size

    @patch('backend.processors.deduplication.MemoryGuard')
    def test_memory_protection(self, mock_memory_guard, engine):
        """测试内存保护机制"""
        mock_guard_instance = Mock()
        mock_memory_guard.return_value = mock_guard_instance
        
        df = pl.DataFrame({
            'name': ['Alice', 'Bob'],
            'email': ['alice@test.com', 'bob@test.com']
        })
        
        engine.deduplicate(df)
        
        # 验证内存保护被调用
        mock_guard_instance.check_memory.assert_called()
        mock_guard_instance.cleanup_if_needed.assert_called()


class TestDeduplicationBenchmark:
    """性能基准测试"""

    def test_large_dataset_performance(self):
        """测试大数据集性能"""
        # 创建10万行数据，20%重复率
        size = 100_000
        duplicate_rate = 0.2
        unique_count = int(size * (1 - duplicate_rate))
        
        # 生成基础数据
        base_names = [f'User_{i}' for i in range(unique_count)]
        base_emails = [f'user{i}@test.com' for i in range(unique_count)]
        
        # 添加重复数据
        names = base_names + base_names[:int(size * duplicate_rate)]
        emails = base_emails + base_emails[:int(size * duplicate_rate)]
        ages = list(range(len(names)))
        
        df = pl.DataFrame({
            'name': names,
            'email': emails,
            'age': ages
        })
        
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        # 执行去重并测量时间
        import time
        start_time = time.time()
        result = engine.deduplicate(df)
        execution_time = time.time() - start_time
        
        # 性能断言（应该在合理时间内完成）
        assert execution_time < 30  # 30秒内完成10万行
        assert result.duplicates_removed == int(size * duplicate_rate)
        assert len(result.deduplicated_df) == unique_count
        
        print(f"大数据集性能测试: {size}行处理耗时 {execution_time:.2f}秒")

    def test_memory_usage_large_dataset(self):
        """测试大数据集的内存使用"""
        # 创建50万行数据测试内存使用
        size = 500_000
        
        df = pl.DataFrame({
            'name': [f'User_{i % 100_000}' for i in range(size)],  # 20%重复率
            'email': [f'user{i % 100_000}@test.com' for i in range(size)],
            'age': list(range(size))
        })
        
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        # 测量内存使用
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        result = engine.deduplicate(df)
        
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_used = memory_after - memory_before
        
        # 内存使用应该在合理范围内（不超过2GB）
        assert memory_used < 2048
        assert result.memory_used_mb > 0
        
        print(f"内存使用测试: {size}行数据使用内存 {memory_used:.2f}MB")

    def test_chunked_processing(self):
        """测试分块处理功能"""
        # 创建大数据集以触发分块处理
        size = 200_000
        
        df = pl.DataFrame({
            'name': [f'User_{i % 50_000}' for i in range(size)],  # 25%重复率
            'email': [f'user{i % 50_000}@test.com' for i in range(size)],
            'value': list(range(size))
        })
        
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST,
            chunk_size=50_000  # 强制分块
        )
        engine = DeduplicationEngine(config)
        
        result = engine.deduplicate(df)
        
        # 验证分块处理结果正确
        assert result.duplicates_removed == 150_000  # 75%的数据是重复的
        assert len(result.deduplicated_df) == 50_000
        
        print(f"分块处理测试: {size}行数据分块处理完成")


class TestDeduplicationEdgeCases:
    """边界条件和异常情况测试"""

    def test_missing_columns_error(self):
        """测试缺少指定列的错误处理"""
        config = DeduplicationConfig(
            columns=['name', 'email', 'nonexistent'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'Bob'],
            'email': ['alice@test.com', 'bob@test.com']
        })
        
        with pytest.raises(Exception):  # 应该抛出列不存在的错误
            engine.deduplicate(df)

    def test_empty_columns_config(self):
        """测试空列配置"""
        config = DeduplicationConfig(
            columns=[],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'Bob'],
            'email': ['alice@test.com', 'bob@test.com']
        })
        
        with pytest.raises(ValueError):  # 应该抛出配置错误
            engine.deduplicate(df)

    def test_all_null_columns(self):
        """测试全空值列"""
        df = pl.DataFrame({
            'name': [None, None, None],
            'email': [None, None, None],
            'age': [25, 30, 35]
        })
        
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        result = engine.deduplicate(df)
        
        # 全空值应该被认为是重复的
        assert result.duplicates_found == 1
        assert len(result.deduplicated_df) == 1

    def test_mixed_data_types(self):
        """测试混合数据类型"""
        df = pl.DataFrame({
            'id': [1, 2, 1, 3],
            'value': ['a', 'b', 'a', 'c'],
            'date': [datetime(2023, 1, 1), datetime(2023, 1, 2), 
                    datetime(2023, 1, 1), datetime(2023, 1, 3)],
            'decimal': [Decimal('1.1'), Decimal('2.2'), 
                       Decimal('1.1'), Decimal('3.3')]
        })
        
        config = DeduplicationConfig(
            columns=['id', 'value', 'date', 'decimal'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        result = engine.deduplicate(df)
        
        assert result.duplicates_found == 1
        assert result.duplicates_removed == 1
        assert len(result.deduplicated_df) == 3

    def test_unicode_handling(self):
        """测试Unicode字符处理"""
        df = pl.DataFrame({
            'name': ['张三', '李四', '张三', '王五', '李四'],
            'email': ['zhangsan@test.com', 'lisi@test.com', 'zhangsan@test.com',
                     'wangwu@test.com', 'lisi@test.com'],
            'desc': ['测试用户1', '测试用户2', '测试用户1', '测试用户3', '测试用户2']
        })
        
        config = DeduplicationConfig(
            columns=['name', 'email'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        result = engine.deduplicate(df)
        
        assert result.duplicates_found == 2  # 张三和李四各有重复
        assert result.duplicates_removed == 2
        assert len(result.deduplicated_df) == 3

    def test_very_long_strings(self):
        """测试极长字符串处理"""
        long_string = 'A' * 10000  # 10K字符
        
        df = pl.DataFrame({
            'name': ['Alice', 'Bob', 'Alice'],
            'description': [long_string, 'Short desc', long_string],
            'id': [1, 2, 3]
        })
        
        config = DeduplicationConfig(
            columns=['name', 'description'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        result = engine.deduplicate(df)
        
        assert result.duplicates_found == 1
        assert result.duplicates_removed == 1
        assert len(result.deduplicated_df) == 2

    @patch('backend.processors.deduplication.DeduplicationEngine._estimate_operation_memory')
    def test_memory_limit_exceeded(self, mock_estimate):
        """测试内存限制超出的处理"""
        # Mock内存估算返回极大值
        mock_estimate.return_value = 1024 * 1024 * 1024 * 100  # 100GB
        
        config = DeduplicationConfig(
            columns=['name'],
            match_type=MatchType.EXACT,
            merge_strategy=MergeStrategy.KEEP_FIRST
        )
        engine = DeduplicationEngine(config)
        
        df = pl.DataFrame({
            'name': ['Alice', 'Bob']
        })
        
        # 应该处理内存不足的情况
        with pytest.raises((MemoryError, RuntimeError)):
            engine.deduplicate(df)


# 便捷函数测试
def test_quick_deduplicate_function():
    """测试快速去重便捷函数"""
    from backend.processors.deduplication import quick_deduplicate
    
    df = pl.DataFrame({
        'name': ['Alice', 'Bob', 'Alice'],
        'email': ['alice@test.com', 'bob@test.com', 'alice@test.com']
    })
    
    result_df = quick_deduplicate(df, ['name', 'email'])
    
    assert len(result_df) == 2
    assert 'Alice' in result_df['name'].to_list()
    assert 'Bob' in result_df['name'].to_list()


if __name__ == '__main__':
    # 运行所有测试
    pytest.main([__file__, '-v', '--tb=short'])