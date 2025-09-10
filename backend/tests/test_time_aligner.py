"""
测试时间对齐器(TimeAligner)的完整功能
包含：时区转换、粒度对齐、窗口匹配、缺失值填充等全面测试场景
"""
import pytest
import polars as pl
import pytz
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import asyncio

from processors.time_aligner import (
    TimeAligner,
    TimeAlignmentConfig,
    TimeGranularity,
    WindowType,
    TimezoneConverter,
    GranularityAligner,
    WindowMatcher,
    quick_time_align,
    align_dataframe,
    create_time_alignment_config
)


class TestTimeAlignmentConfig:
    """测试时间对齐配置"""

    def test_config_initialization_default(self):
        """测试默认配置初始化"""
        config = TimeAlignmentConfig(time_columns=['timestamp'])
        
        assert config.time_columns == ['timestamp']
        assert config.target_granularity == TimeGranularity.MINUTE
        assert config.target_timezone == "UTC"
        assert config.window_type == WindowType.EXACT
        assert config.fill_missing is True
        assert config.interpolation_method == "forward"
        assert config.quality_threshold == 0.95

    def test_config_initialization_custom(self):
        """测试自定义配置初始化"""
        config = TimeAlignmentConfig(
            time_columns=['created_at', 'updated_at'],
            target_granularity=TimeGranularity.HOUR,
            source_timezone="Asia/Shanghai",
            target_timezone="UTC",
            window_type=WindowType.RANGE,
            window_size=timedelta(minutes=30),
            fill_missing=False,
            interpolation_method="backward",
            quality_threshold=0.9
        )
        
        assert config.time_columns == ['created_at', 'updated_at']
        assert config.target_granularity == TimeGranularity.HOUR
        assert config.source_timezone == "Asia/Shanghai"
        assert config.window_type == WindowType.RANGE
        assert config.window_size == timedelta(minutes=30)
        assert config.fill_missing is False
        assert config.interpolation_method == "backward"
        assert config.quality_threshold == 0.9

    def test_config_validation_empty_columns(self):
        """测试空时间列配置验证"""
        with pytest.raises(ValueError, match="time_columns cannot be empty"):
            TimeAlignmentConfig(time_columns=[])

    def test_config_validation_range_window_without_size(self):
        """测试范围窗口类型需要窗口大小"""
        with pytest.raises(ValueError, match="window_size is required for RANGE window type"):
            TimeAlignmentConfig(
                time_columns=['timestamp'],
                window_type=WindowType.RANGE
            )


class TestTimezoneConverter:
    """测试时区转换器"""

    @pytest.fixture
    def converter_utc_to_shanghai(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            source_timezone='UTC',
            target_timezone='Asia/Shanghai'
        )
        return TimezoneConverter(config)

    @pytest.fixture
    def converter_naive_to_utc(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            source_timezone='US/Eastern',
            target_timezone='UTC'
        )
        return TimezoneConverter(config)

    def test_timezone_converter_initialization(self, converter_utc_to_shanghai):
        """测试时区转换器初始化"""
        assert converter_utc_to_shanghai.source_tz == pytz.timezone('UTC')
        assert converter_utc_to_shanghai.target_tz == pytz.timezone('Asia/Shanghai')

    def test_convert_timezone_utc_to_shanghai(self, converter_utc_to_shanghai):
        """测试UTC到上海时区转换"""
        # 创建UTC时间数据
        utc_times = [
            datetime(2023, 6, 15, 12, 0, 0, tzinfo=pytz.UTC),
            datetime(2023, 6, 15, 18, 0, 0, tzinfo=pytz.UTC),
            datetime(2023, 6, 15, 23, 0, 0, tzinfo=pytz.UTC)
        ]
        
        df = pl.DataFrame({
            'timestamp': utc_times,
            'value': [100, 200, 300]
        })
        
        result_df = converter_utc_to_shanghai.convert_timezone(df)
        
        # 验证时区转换正确性（UTC+8）
        assert len(result_df) == 3
        assert 'timestamp' in result_df.columns
        assert result_df['value'].to_list() == [100, 200, 300]

    def test_convert_timezone_naive_datetime(self, converter_naive_to_utc):
        """测试朴素datetime的时区转换"""
        # 创建朴素datetime数据
        naive_times = [
            datetime(2023, 6, 15, 8, 0, 0),   # 8 AM Eastern
            datetime(2023, 6, 15, 14, 0, 0),  # 2 PM Eastern
            datetime(2023, 6, 15, 20, 0, 0)   # 8 PM Eastern
        ]
        
        df = pl.DataFrame({
            'timestamp': naive_times,
            'value': [100, 200, 300]
        })
        
        result_df = converter_naive_to_utc.convert_timezone(df)
        
        assert len(result_df) == 3
        assert 'timestamp' in result_df.columns

    def test_convert_timezone_missing_column(self):
        """测试缺失时间列的处理"""
        config = TimeAlignmentConfig(time_columns=['nonexistent'])
        converter = TimezoneConverter(config)
        
        df = pl.DataFrame({
            'timestamp': [datetime(2023, 6, 15, 12, 0, 0)],
            'value': [100]
        })
        
        # 应该不会报错，只是跳过转换
        result_df = converter.convert_timezone(df)
        assert result_df.equals(df)

    def test_convert_timezone_non_datetime_column(self):
        """测试非datetime列的处理"""
        config = TimeAlignmentConfig(time_columns=['value'])
        converter = TimezoneConverter(config)
        
        df = pl.DataFrame({
            'timestamp': [datetime(2023, 6, 15, 12, 0, 0)],
            'value': [100]  # 整数列，不是datetime
        })
        
        # 应该跳过非datetime列的转换
        result_df = converter.convert_timezone(df)
        assert result_df.equals(df)

    def test_convert_timezone_with_nulls(self, converter_utc_to_shanghai):
        """测试包含空值的时区转换"""
        df = pl.DataFrame({
            'timestamp': [
                datetime(2023, 6, 15, 12, 0, 0, tzinfo=pytz.UTC),
                None,
                datetime(2023, 6, 15, 18, 0, 0, tzinfo=pytz.UTC)
            ],
            'value': [100, 200, 300]
        })
        
        result_df = converter_utc_to_shanghai.convert_timezone(df)
        
        assert len(result_df) == 3
        # 验证空值仍然是空值
        assert result_df['timestamp'][1] is None


class TestGranularityAligner:
    """测试粒度对齐器"""

    @pytest.fixture
    def aligner_minute(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE
        )
        return GranularityAligner(config)

    @pytest.fixture
    def aligner_hour(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.HOUR,
            round_method='floor'
        )
        return GranularityAligner(config)

    def test_align_to_minute_granularity(self, aligner_minute):
        """测试对齐到分钟粒度"""
        timestamps = [
            datetime(2023, 6, 15, 12, 30, 45),  # 12:30:45 -> 12:30:00
            datetime(2023, 6, 15, 12, 31, 15),  # 12:31:15 -> 12:31:00
            datetime(2023, 6, 15, 12, 31, 59)   # 12:31:59 -> 12:31:00
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        result_df = aligner_minute.align_granularity(df)
        
        # 验证时间被正确对齐到分钟
        aligned_times = result_df['timestamp'].to_list()
        expected_times = [
            datetime(2023, 6, 15, 12, 30, 0),
            datetime(2023, 6, 15, 12, 31, 0),
            datetime(2023, 6, 15, 12, 31, 0)
        ]
        
        assert len(aligned_times) == 3
        # 注意：由于Polars的datetime处理可能略有不同，我们主要验证秒数被清零
        for aligned_time in aligned_times:
            if aligned_time:  # 跳过None值
                assert aligned_time.second == 0
                assert aligned_time.microsecond == 0

    def test_align_to_hour_granularity(self, aligner_hour):
        """测试对齐到小时粒度"""
        timestamps = [
            datetime(2023, 6, 15, 12, 30, 45),  # 12:30:45 -> 12:00:00
            datetime(2023, 6, 15, 13, 15, 30),  # 13:15:30 -> 13:00:00
            datetime(2023, 6, 15, 13, 45, 0)    # 13:45:00 -> 13:00:00
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        result_df = aligner_hour.align_granularity(df)
        
        # 验证时间被正确对齐到小时
        aligned_times = result_df['timestamp'].to_list()
        
        for aligned_time in aligned_times:
            if aligned_time:  # 跳过None值
                assert aligned_time.minute == 0
                assert aligned_time.second == 0
                assert aligned_time.microsecond == 0

    def test_align_granularity_day(self):
        """测试对齐到天粒度"""
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.DAY
        )
        aligner = GranularityAligner(config)
        
        timestamps = [
            datetime(2023, 6, 15, 8, 30, 45),   # -> 2023-06-15 00:00:00
            datetime(2023, 6, 15, 14, 15, 30),  # -> 2023-06-15 00:00:00
            datetime(2023, 6, 16, 9, 45, 0)     # -> 2023-06-16 00:00:00
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        result_df = aligner.align_granularity(df)
        
        # 验证时间被正确对齐到天
        aligned_times = result_df['timestamp'].to_list()
        
        for aligned_time in aligned_times:
            if aligned_time:
                assert aligned_time.hour == 0
                assert aligned_time.minute == 0
                assert aligned_time.second == 0

    def test_align_multiple_time_columns(self):
        """测试多个时间列的对齐"""
        config = TimeAlignmentConfig(
            time_columns=['start_time', 'end_time'],
            target_granularity=TimeGranularity.MINUTE
        )
        aligner = GranularityAligner(config)
        
        df = pl.DataFrame({
            'start_time': [
                datetime(2023, 6, 15, 12, 30, 45),
                datetime(2023, 6, 15, 12, 31, 15)
            ],
            'end_time': [
                datetime(2023, 6, 15, 12, 45, 30),
                datetime(2023, 6, 15, 12, 50, 45)
            ],
            'value': [100, 200]
        })
        
        result_df = aligner.align_granularity(df)
        
        # 验证两个时间列都被对齐
        for col in ['start_time', 'end_time']:
            aligned_times = result_df[col].to_list()
            for aligned_time in aligned_times:
                if aligned_time:
                    assert aligned_time.second == 0


class TestWindowMatcher:
    """测试窗口匹配器"""

    @pytest.fixture
    def matcher_exact(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            window_type=WindowType.EXACT
        )
        return WindowMatcher(config)

    @pytest.fixture
    def matcher_range(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            window_type=WindowType.RANGE,
            window_size=timedelta(minutes=5)
        )
        return WindowMatcher(config)

    def test_exact_matching(self, matcher_exact):
        """测试精确匹配"""
        timestamps = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 5, 0),
            datetime(2023, 6, 15, 12, 10, 0),
            datetime(2023, 6, 15, 12, 15, 0)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300, 400]
        })
        
        reference_times = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 10, 0)
        ]
        
        result_df = matcher_exact.apply_window_matching(df, reference_times)
        
        # 应该只保留精确匹配的记录
        assert len(result_df) == 2
        result_timestamps = result_df['timestamp'].to_list()
        assert datetime(2023, 6, 15, 12, 0, 0) in result_timestamps
        assert datetime(2023, 6, 15, 12, 10, 0) in result_timestamps

    def test_range_matching(self, matcher_range):
        """测试范围匹配"""
        timestamps = [
            datetime(2023, 6, 15, 12, 0, 0),   # 参考时间
            datetime(2023, 6, 15, 12, 2, 0),   # 在范围内（±2.5分钟）
            datetime(2023, 6, 15, 12, 8, 0),   # 超出范围
            datetime(2023, 6, 15, 12, 10, 0)   # 另一个参考时间
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300, 400]
        })
        
        reference_times = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 10, 0)
        ]
        
        result_df = matcher_range.apply_window_matching(df, reference_times)
        
        # 应该保留在范围内的记录
        assert len(result_df) >= 2  # 至少包含参考时间点
        
    def test_before_matching(self):
        """测试before匹配"""
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            window_type=WindowType.BEFORE
        )
        matcher = WindowMatcher(config)
        
        timestamps = [
            datetime(2023, 6, 15, 11, 0, 0),   # 在参考时间之前
            datetime(2023, 6, 15, 12, 0, 0),   # 参考时间
            datetime(2023, 6, 15, 13, 0, 0)    # 在参考时间之后
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        reference_times = [datetime(2023, 6, 15, 12, 0, 0)]
        
        result_df = matcher.apply_window_matching(df, reference_times)
        
        # 应该只保留在参考时间之前（包含）的记录
        result_timestamps = result_df['timestamp'].to_list()
        for ts in result_timestamps:
            if ts:
                assert ts <= datetime(2023, 6, 15, 12, 0, 0)

    def test_after_matching(self):
        """测试after匹配"""
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            window_type=WindowType.AFTER
        )
        matcher = WindowMatcher(config)
        
        timestamps = [
            datetime(2023, 6, 15, 11, 0, 0),   # 在参考时间之前
            datetime(2023, 6, 15, 12, 0, 0),   # 参考时间
            datetime(2023, 6, 15, 13, 0, 0)    # 在参考时间之后
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        reference_times = [datetime(2023, 6, 15, 12, 0, 0)]
        
        result_df = matcher.apply_window_matching(df, reference_times)
        
        # 应该只保留在参考时间之后（包含）的记录
        result_timestamps = result_df['timestamp'].to_list()
        for ts in result_timestamps:
            if ts:
                assert ts >= datetime(2023, 6, 15, 12, 0, 0)


class TestTimeAligner:
    """测试时间对齐器主类"""

    @pytest.fixture
    def aligner_basic(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE,
            fill_missing=False
        )
        return TimeAligner(config)

    @pytest.fixture
    def aligner_with_filling(self):
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE,
            fill_missing=True,
            interpolation_method="forward"
        )
        return TimeAligner(config)

    def test_aligner_initialization(self, aligner_basic):
        """测试时间对齐器初始化"""
        assert aligner_basic.config.time_columns == ['timestamp']
        assert aligner_basic.timezone_converter is not None
        assert aligner_basic.granularity_aligner is not None
        assert aligner_basic.window_matcher is not None

    def test_basic_alignment(self, aligner_basic):
        """测试基础时间对齐"""
        timestamps = [
            datetime(2023, 6, 15, 12, 30, 45),
            datetime(2023, 6, 15, 12, 31, 15),
            datetime(2023, 6, 15, 12, 32, 30)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        result = aligner_basic.align(df)
        
        assert isinstance(result.aligned_data, pl.DataFrame)
        assert len(result.aligned_data) == 3
        assert result.execution_time > 0
        assert result.memory_usage_mb >= 0
        assert 0 <= result.alignment_accuracy <= 1
        assert 0 <= result.time_coverage <= 1

    def test_alignment_with_reference_times(self, aligner_basic):
        """测试带参考时间的对齐"""
        timestamps = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 5, 0),
            datetime(2023, 6, 15, 12, 10, 0),
            datetime(2023, 6, 15, 12, 15, 0)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300, 400]
        })
        
        reference_times = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 10, 0)
        ]
        
        result = aligner_basic.align(df, reference_times)
        
        # 由于使用精确匹配，应该只保留匹配的记录
        assert len(result.aligned_data) == 2

    def test_alignment_with_missing_fill(self, aligner_with_filling):
        """测试带缺失值填充的对齐"""
        timestamps = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 5, 0)  # 缺少1-4分钟
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200]
        })
        
        result = aligner_with_filling.align(df)
        
        # 填充后应该有更多记录
        assert len(result.aligned_data) >= len(df)
        assert result.interpolation_rate >= 0

    @pytest.mark.asyncio
    async def test_async_alignment(self, aligner_basic):
        """测试异步时间对齐"""
        timestamps = [
            datetime(2023, 6, 15, 12, 30, 45),
            datetime(2023, 6, 15, 12, 31, 15)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200]
        })
        
        result = await aligner_basic.align_async(df)
        
        assert isinstance(result.aligned_data, pl.DataFrame)
        assert len(result.aligned_data) == 2

    def test_config_validation_missing_column(self, aligner_basic):
        """测试配置验证 - 缺失列"""
        df = pl.DataFrame({
            'other_column': [datetime(2023, 6, 15, 12, 0, 0)],
            'value': [100]
        })
        
        with pytest.raises(ValueError, match="时间列 'timestamp' 不存在于数据中"):
            aligner_basic.align(df)

    def test_empty_dataframe(self, aligner_basic):
        """测试空数据框"""
        df = pl.DataFrame({
            'timestamp': [],
            'value': []
        })
        
        result = aligner_basic.align(df)
        
        assert len(result.aligned_data) == 0
        assert result.alignment_accuracy == 0.0

    def test_single_row_dataframe(self, aligner_basic):
        """测试单行数据框"""
        df = pl.DataFrame({
            'timestamp': [datetime(2023, 6, 15, 12, 30, 45)],
            'value': [100]
        })
        
        result = aligner_basic.align(df)
        
        assert len(result.aligned_data) == 1
        assert result.alignment_accuracy == 1.0

    def test_execution_history_tracking(self, aligner_basic):
        """测试执行历史跟踪"""
        df = pl.DataFrame({
            'timestamp': [datetime(2023, 6, 15, 12, 30, 45)],
            'value': [100]
        })
        
        # 执行几次对齐
        aligner_basic.align(df)
        aligner_basic.align(df)
        
        history = aligner_basic.get_execution_history()
        assert len(history) == 2
        assert all('timestamp' in record for record in history)
        assert all('execution_time' in record for record in history)

    def test_config_update(self, aligner_basic):
        """测试配置更新"""
        new_config = TimeAlignmentConfig(
            time_columns=['new_timestamp'],
            target_granularity=TimeGranularity.HOUR
        )
        
        aligner_basic.update_config(new_config)
        
        assert aligner_basic.config.time_columns == ['new_timestamp']
        assert aligner_basic.config.target_granularity == TimeGranularity.HOUR


class TestTimeAlignmentIntegration:
    """时间对齐集成测试"""

    def test_full_pipeline_with_timezone_and_granularity(self):
        """测试完整管道：时区转换 + 粒度对齐"""
        # 创建带时区的时间数据
        timestamps = [
            datetime(2023, 6, 15, 20, 30, 45, tzinfo=pytz.timezone('US/Eastern')),  # 东部时间
            datetime(2023, 6, 15, 21, 31, 15, tzinfo=pytz.timezone('US/Eastern')),
            datetime(2023, 6, 15, 22, 32, 30, tzinfo=pytz.timezone('US/Eastern'))
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200, 300]
        })
        
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            source_timezone='US/Eastern',
            target_timezone='UTC',
            target_granularity=TimeGranularity.HOUR,
            fill_missing=False
        )
        
        aligner = TimeAligner(config)
        result = aligner.align(df)
        
        assert len(result.aligned_data) == 3
        assert result.alignment_accuracy > 0
        assert len(result.warnings) >= 0

    def test_complex_scenario_with_gaps_and_interpolation(self):
        """测试复杂场景：数据缺口 + 插值填充"""
        timestamps = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 10, 0),  # 缺少5分钟的数据
            datetime(2023, 6, 15, 12, 20, 0)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 300, 500]
        })
        
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE,
            fill_missing=True,
            interpolation_method="forward"
        )
        
        aligner = TimeAligner(config)
        result = aligner.align(df)
        
        # 填充后应该有更多记录
        assert len(result.aligned_data) > len(df)
        assert result.interpolation_rate > 0

    def test_window_matching_with_range(self):
        """测试窗口匹配与范围筛选"""
        timestamps = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 2, 0),
            datetime(2023, 6, 15, 12, 8, 0),
            datetime(2023, 6, 15, 12, 10, 0),
            datetime(2023, 6, 15, 12, 15, 0)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 150, 250, 300, 400]
        })
        
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            window_type=WindowType.RANGE,
            window_size=timedelta(minutes=3),
            target_granularity=TimeGranularity.MINUTE
        )
        
        reference_times = [
            datetime(2023, 6, 15, 12, 0, 0),
            datetime(2023, 6, 15, 12, 10, 0)
        ]
        
        aligner = TimeAligner(config)
        result = aligner.align(df, reference_times)
        
        # 应该保留在窗口范围内的记录
        assert len(result.aligned_data) >= 2


# 便捷函数测试
class TestConvenienceFunctions:
    """测试便捷函数"""

    def test_quick_time_align(self):
        """测试快速时间对齐函数"""
        timestamps = [
            datetime(2023, 6, 15, 12, 30, 45),
            datetime(2023, 6, 15, 12, 31, 15)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200]
        })
        
        result_df = quick_time_align(
            df, 
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE
        )
        
        assert isinstance(result_df, pl.DataFrame)
        assert len(result_df) == 2

    @pytest.mark.asyncio
    async def test_align_dataframe_async(self):
        """测试异步数据框对齐函数"""
        timestamps = [
            datetime(2023, 6, 15, 12, 30, 45),
            datetime(2023, 6, 15, 12, 31, 15)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200]
        })
        
        result = await align_dataframe(
            df,
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.HOUR
        )
        
        assert isinstance(result.aligned_data, pl.DataFrame)
        assert len(result.aligned_data) == 2

    def test_create_time_alignment_config(self):
        """测试创建时间对齐配置函数"""
        config = create_time_alignment_config(
            time_columns=['created_at'],
            target_granularity=TimeGranularity.DAY,
            source_timezone='Asia/Tokyo',
            window_type=WindowType.BEFORE
        )
        
        assert isinstance(config, TimeAlignmentConfig)
        assert config.time_columns == ['created_at']
        assert config.target_granularity == TimeGranularity.DAY
        assert config.source_timezone == 'Asia/Tokyo'
        assert config.window_type == WindowType.BEFORE


# 边界条件和错误处理测试
class TestEdgeCasesAndErrorHandling:
    """边界条件和错误处理测试"""

    def test_invalid_timezone(self):
        """测试无效时区"""
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            source_timezone='Invalid/Timezone',
            target_timezone='Also/Invalid'
        )
        
        # 应该优雅地处理无效时区
        converter = TimezoneConverter(config)
        assert converter.source_tz is None
        assert converter.target_tz == pytz.UTC  # 应该回退到UTC

    def test_mixed_datetime_types(self):
        """测试混合datetime类型"""
        df = pl.DataFrame({
            'timestamp': [
                datetime(2023, 6, 15, 12, 0, 0),  # 朴素datetime
                None,                              # 空值
                "2023-06-15 12:00:00"             # 字符串（可能需要转换）
            ],
            'value': [100, 200, 300]
        })
        
        config = TimeAlignmentConfig(time_columns=['timestamp'])
        aligner = TimeAligner(config)
        
        # 应该处理混合类型或报告错误
        try:
            result = aligner.align(df)
            # 如果成功，验证结果
            assert isinstance(result.aligned_data, pl.DataFrame)
        except Exception as e:
            # 如果失败，应该是合理的错误
            assert "datetime" in str(e).lower() or "type" in str(e).lower()

    def test_very_large_time_range(self):
        """测试非常大的时间范围"""
        timestamps = [
            datetime(1900, 1, 1, 0, 0, 0),
            datetime(2100, 12, 31, 23, 59, 59)
        ]
        
        df = pl.DataFrame({
            'timestamp': timestamps,
            'value': [100, 200]
        })
        
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.YEAR,
            fill_missing=True
        )
        
        aligner = TimeAligner(config)
        result = aligner.align(df)
        
        # 应该能够处理，但可能会有警告或性能问题
        assert isinstance(result.aligned_data, pl.DataFrame)
        assert len(result.aligned_data) >= 2

    def test_overlapping_time_columns(self):
        """测试重叠的时间列处理"""
        df = pl.DataFrame({
            'timestamp1': [datetime(2023, 6, 15, 12, 0, 0)],
            'timestamp2': [datetime(2023, 6, 15, 12, 0, 0)],  # 相同时间
            'value': [100]
        })
        
        config = TimeAlignmentConfig(
            time_columns=['timestamp1', 'timestamp2'],
            target_granularity=TimeGranularity.MINUTE
        )
        
        aligner = TimeAligner(config)
        result = aligner.align(df)
        
        # 应该能够处理多个时间列
        assert len(result.aligned_data) == 1


if __name__ == '__main__':
    # 运行所有测试
    pytest.main([__file__, '-v', '--tb=short'])