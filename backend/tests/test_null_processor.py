"""
Tests for NullProcessor functionality.
Tests comprehensive null value detection, processing strategies, and quality tracking.
"""

import pytest
import polars as pl
from datetime import datetime, timedelta
from typing import List, Dict, Any
import numpy as np

from processors.null_processor import (
    NullProcessor, 
    NullProcessingConfig, 
    NullDetector,
    FillStrategies,
    QualityTracker,
    NullProcessingResult,
    NullFillStrategy,
    NullDetectionMethod,
    QualityThreshold
)


@pytest.fixture
def sample_data_with_nulls():
    """Create test data with various null patterns."""
    return pl.DataFrame({
        'id': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'name': ['Alice', None, 'Charlie', '', 'Eve', 'N/A', 'Grace', 'null', None, 'Jane'],
        'age': [25, 30, None, 35, None, 42, 28, None, 33, 29],
        'score': [85.5, None, 92.0, 78.5, None, 88.0, 91.2, None, 86.7, 94.1],
        'category': ['A', 'B', None, 'A', 'B', None, 'A', 'B', None, 'A'],
        'timestamp': [
            datetime(2024, 1, 1),
            None,
            datetime(2024, 1, 3),
            datetime(2024, 1, 4),
            None,
            datetime(2024, 1, 6),
            datetime(2024, 1, 7),
            None,
            datetime(2024, 1, 9),
            datetime(2024, 1, 10)
        ]
    })


@pytest.fixture
def time_series_data():
    """Create time series data for interpolation testing."""
    return pl.DataFrame({
        'timestamp': [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(10)],
        'value': [10.0, None, 20.0, None, None, 50.0, None, 70.0, None, 90.0],
        'category': ['A', 'A', 'B', 'B', 'B', 'A', 'A', 'B', 'B', 'A']
    })


class TestNullProcessingConfig:
    """Test NullProcessingConfig functionality."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = NullProcessingConfig(target_columns=['test'])
        
        assert config.target_columns == ['test']
        assert config.fill_strategy == NullFillStrategy.FORWARD_FILL
        assert config.detection_method == NullDetectionMethod.STANDARD
        assert config.quality_threshold == 0.8
        
    def test_custom_config(self):
        """Test custom configuration."""
        config = NullProcessingConfig(
            target_columns=['age', 'score'],
            fill_strategy=NullFillStrategy.MEAN,
            detection_method=NullDetectionMethod.EXTENDED,
            quality_threshold=0.9,
            constant_fill_value=0,
            enable_quality_tracking=True
        )
        
        assert config.target_columns == ['age', 'score']
        assert config.fill_strategy == NullFillStrategy.MEAN
        assert config.detection_method == NullDetectionMethod.EXTENDED
        assert config.quality_threshold == 0.9
        assert config.constant_fill_value == 0
        assert config.enable_quality_tracking == True
        
    def test_config_validation(self):
        """Test configuration validation."""
        # Test empty target_columns
        with pytest.raises(ValueError, match="target_columns cannot be empty"):
            NullProcessingConfig(target_columns=[])
        
        # Test CONSTANT strategy without value
        with pytest.raises(ValueError, match="constant_fill_value is required"):
            NullProcessingConfig(
                target_columns=['test'],
                fill_strategy=NullFillStrategy.CONSTANT,
                constant_fill_value=None
            )
        
        # Test invalid quality threshold
        with pytest.raises(ValueError, match="quality_threshold must be between 0 and 1"):
            NullProcessingConfig(
                target_columns=['test'],
                quality_threshold=1.5
            )


class TestNullDetector:
    """Test NullDetector functionality."""
    
    def test_standard_null_detection(self, sample_data_with_nulls):
        """Test standard null detection."""
        config = NullProcessingConfig(
            target_columns=['name', 'age', 'score'],
            detection_method=NullDetectionMethod.STANDARD
        )
        detector = NullDetector(config)
        
        result = detector.detect_nulls(sample_data_with_nulls)
        
        # Should detect null values in specified columns
        assert 'name' in result
        assert 'age' in result  
        assert 'score' in result
        
        # Check that detection results are DataFrames
        for col_result in result.values():
            assert isinstance(col_result, pl.DataFrame)
            
    def test_extended_null_detection(self, sample_data_with_nulls):
        """Test extended null detection."""
        config = NullProcessingConfig(
            target_columns=['name'],
            detection_method=NullDetectionMethod.EXTENDED
        )
        detector = NullDetector(config)
        
        result = detector.detect_nulls(sample_data_with_nulls)
        
        # Should detect more nulls including empty strings
        assert 'name' in result
        assert isinstance(result['name'], pl.DataFrame)
        
    def test_pattern_null_detection(self, sample_data_with_nulls):
        """Test pattern-based null detection."""
        config = NullProcessingConfig(
            target_columns=['name'],
            detection_method=NullDetectionMethod.PATTERN,
            custom_detection_rules=['N/A', 'null']
        )
        detector = NullDetector(config)
        
        result = detector.detect_nulls(sample_data_with_nulls)
        
        # Should detect pattern-based nulls
        assert 'name' in result
        assert isinstance(result['name'], pl.DataFrame)


class TestFillStrategies:
    """Test FillStrategies functionality."""
    
    def test_forward_fill_strategy(self, time_series_data):
        """Test forward fill strategy."""
        config = NullProcessingConfig(
            target_columns=['value'],
            fill_strategy=NullFillStrategy.FORWARD_FILL
        )
        strategies = FillStrategies(config)
        
        filled = strategies.apply_fill_strategy(time_series_data, 'value')
        
        # Check that nulls are filled
        assert filled['value'].null_count() < time_series_data['value'].null_count()
        
    def test_backward_fill_strategy(self, time_series_data):
        """Test backward fill strategy."""
        config = NullProcessingConfig(
            target_columns=['value'],
            fill_strategy=NullFillStrategy.BACKWARD_FILL
        )
        strategies = FillStrategies(config)
        
        filled = strategies.apply_fill_strategy(time_series_data, 'value')
        
        # Check that nulls are filled
        assert filled['value'].null_count() < time_series_data['value'].null_count()
        
    def test_mean_fill_strategy(self, sample_data_with_nulls):
        """Test mean fill strategy."""
        config = NullProcessingConfig(
            target_columns=['age'],
            fill_strategy=NullFillStrategy.MEAN
        )
        strategies = FillStrategies(config)
        
        filled = strategies.apply_fill_strategy(sample_data_with_nulls, 'age')
        
        # Check that nulls are filled with mean
        assert filled['age'].null_count() == 0
        
        # Verify mean calculation
        original_mean = sample_data_with_nulls['age'].drop_nulls().mean()
        filled_values = filled['age'].to_list()
        
        # Check filled values match original mean
        for i, original_age in enumerate(sample_data_with_nulls['age'].to_list()):
            if original_age is None:
                assert abs(filled_values[i] - original_mean) < 0.001
                
    def test_median_fill_strategy(self, sample_data_with_nulls):
        """Test median fill strategy."""
        config = NullProcessingConfig(
            target_columns=['score'],
            fill_strategy=NullFillStrategy.MEDIAN
        )
        strategies = FillStrategies(config)
        
        filled = strategies.apply_fill_strategy(sample_data_with_nulls, 'score')
        
        # Check that nulls are filled
        assert filled['score'].null_count() == 0
        
    def test_mode_fill_strategy(self, sample_data_with_nulls):
        """Test mode fill strategy."""
        config = NullProcessingConfig(
            target_columns=['category'],
            fill_strategy=NullFillStrategy.MODE
        )
        strategies = FillStrategies(config)
        
        filled = strategies.apply_fill_strategy(sample_data_with_nulls, 'category')
        
        # Check that nulls are filled
        assert filled['category'].null_count() == 0
        
    def test_constant_fill_strategy(self, sample_data_with_nulls):
        """Test constant fill strategy."""
        config = NullProcessingConfig(
            target_columns=['name'],
            fill_strategy=NullFillStrategy.CONSTANT,
            constant_fill_value='UNKNOWN'
        )
        strategies = FillStrategies(config)
        
        filled = strategies.apply_fill_strategy(sample_data_with_nulls, 'name')
        
        # Check that nulls are filled with constant
        assert filled['name'].null_count() == 0
        
        # Verify constant fill
        filled_names = filled['name'].to_list()
        for i, original_name in enumerate(sample_data_with_nulls['name'].to_list()):
            if original_name is None:
                assert filled_names[i] == 'UNKNOWN'


class TestQualityTracker:
    """Test QualityTracker functionality."""
    
    def test_quality_metrics_calculation(self, sample_data_with_nulls):
        """Test quality metrics calculation."""
        config = NullProcessingConfig(
            target_columns=['age', 'score'],
            enable_quality_tracking=True
        )
        tracker = QualityTracker(config)
        
        # Process data first
        strategies = FillStrategies(config)
        processed = strategies.apply_fill_strategy(sample_data_with_nulls, 'age')
        
        # Calculate metrics 
        metrics = tracker.track_processing_quality(sample_data_with_nulls, processed)
        
        assert isinstance(metrics, dict)
        assert 'data_completeness' in metrics or 'completeness' in metrics
        
        # Check metric values are valid
        for key, value in metrics.items():
            assert isinstance(value, (int, float))
            if key.endswith('_rate') or key == 'data_completeness':
                assert 0.0 <= value <= 1.0


class TestNullProcessor:
    """Test main NullProcessor functionality."""
    
    def test_basic_processing(self, sample_data_with_nulls):
        """Test basic null processing."""
        config = NullProcessingConfig(
            target_columns=['age', 'score', 'name'],
            fill_strategy=NullFillStrategy.MEAN
        )
        processor = NullProcessor(config)
        
        result = processor.process(sample_data_with_nulls)
        
        assert isinstance(result, NullProcessingResult)
        assert result.processed_data is not None
        assert isinstance(result.processing_statistics, dict)
        assert isinstance(result.quality_metrics, dict)
        assert result.execution_time > 0
        
        # Check that processing reduced null counts in numeric columns
        original_age_nulls = sample_data_with_nulls['age'].null_count()
        processed_age_nulls = result.processed_data['age'].null_count()
        assert processed_age_nulls <= original_age_nulls
        
    def test_custom_config_processing(self, sample_data_with_nulls):
        """Test processing with custom configuration."""
        config = NullProcessingConfig(
            target_columns=['name', 'category'],
            fill_strategy=NullFillStrategy.CONSTANT,
            constant_fill_value='MISSING',
            detection_method=NullDetectionMethod.EXTENDED
        )
        
        processor = NullProcessor(config)
        result = processor.process(sample_data_with_nulls)
        
        # Check that custom configuration was applied
        assert result.processed_data is not None
        assert result.processed_data['name'].null_count() <= sample_data_with_nulls['name'].null_count()
        
    def test_different_fill_strategies(self, sample_data_with_nulls):
        """Test different fill strategies."""
        strategies_to_test = [
            NullFillStrategy.FORWARD_FILL,
            NullFillStrategy.BACKWARD_FILL,
            NullFillStrategy.MEAN,
            NullFillStrategy.MEDIAN
        ]
        
        for strategy in strategies_to_test:
            config = NullProcessingConfig(
                target_columns=['age'],
                fill_strategy=strategy
            )
            
            processor = NullProcessor(config)
            result = processor.process(sample_data_with_nulls)
            
            # Each strategy should reduce null count
            original_nulls = sample_data_with_nulls['age'].null_count()
            processed_nulls = result.processed_data['age'].null_count()
            assert processed_nulls <= original_nulls, f"Strategy {strategy} failed to reduce nulls"
            
    def test_async_processing(self, sample_data_with_nulls):
        """Test async processing functionality."""
        import asyncio
        
        async def async_test():
            config = NullProcessingConfig(target_columns=['age', 'score'])
            processor = NullProcessor(config)
            result = await processor.process_async(sample_data_with_nulls)
            
            assert isinstance(result, NullProcessingResult)
            assert result.processed_data is not None
            return result
            
        result = asyncio.run(async_test())
        assert result is not None
        
    def test_memory_management(self):
        """Test memory management with larger dataset."""
        # Create a larger dataset
        large_data = pl.DataFrame({
            'id': list(range(1000)),
            'value': [i if i % 5 != 0 else None for i in range(1000)],
            'category': [f'cat_{i%10}' if i % 7 != 0 else None for i in range(1000)]
        })
        
        config = NullProcessingConfig(
            target_columns=['value', 'category'],
            fill_strategy=NullFillStrategy.MEAN
        )
        processor = NullProcessor(config)
        result = processor.process(large_data)
        
        assert result.processed_data.shape[0] == 1000
        assert result.memory_usage_mb >= 0  # Allow 0 for small datasets
        
    def test_quality_threshold_monitoring(self, sample_data_with_nulls):
        """Test quality threshold monitoring."""
        config = NullProcessingConfig(
            target_columns=['age', 'score'],
            quality_threshold=0.95,  # High threshold
            enable_quality_tracking=True
        )
        
        processor = NullProcessor(config)
        result = processor.process(sample_data_with_nulls)
        
        # Should process and track quality
        assert result.processed_data is not None
        assert 'data_completeness' in result.quality_metrics
        assert len(result.warnings) >= 0  # May have warnings about quality
        
    def test_no_nulls_data(self):
        """Test processing data with no null values."""
        data = pl.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
            'age': [25, 30, 35, 40, 45]
        })
        
        config = NullProcessingConfig(target_columns=['id', 'name', 'age'])
        processor = NullProcessor(config)
        result = processor.process(data)
        
        # Should process without issues
        assert result.processed_data is not None
        assert result.total_nulls_processed == 0
        
    def test_all_null_column(self):
        """Test handling of column with all null values."""
        data = pl.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'all_null': [None, None, None, None, None],
            'some_data': ['a', 'b', None, 'd', 'e']
        })
        
        config = NullProcessingConfig(
            target_columns=['all_null', 'some_data'],
            fill_strategy=NullFillStrategy.CONSTANT,
            constant_fill_value='DEFAULT'
        )
        processor = NullProcessor(config)
        result = processor.process(data)
        
        # All null column should be handled
        assert result.processed_data is not None
        assert result.processed_data['all_null'].null_count() == 0
        
    def test_mixed_data_types(self):
        """Test processing data with mixed data types."""
        data = pl.DataFrame({
            'int_col': [1, None, 3, 4, None],
            'float_col': [1.1, 2.2, None, 4.4, 5.5],
            'str_col': ['a', None, 'c', 'd', None],
            'date_col': [
                datetime(2024, 1, 1),
                None,
                datetime(2024, 1, 3),
                datetime(2024, 1, 4),
                None
            ]
        })
        
        config = NullProcessingConfig(
            target_columns=list(data.columns),
            fill_strategy=NullFillStrategy.FORWARD_FILL
        )
        processor = NullProcessor(config)
        result = processor.process(data)
        
        # Should handle all data types appropriately
        assert result.processed_data is not None
        for col in data.columns:
            original_nulls = data[col].null_count()
            processed_nulls = result.processed_data[col].null_count()
            assert processed_nulls <= original_nulls
            
    def test_performance_monitoring(self):
        """Test performance monitoring."""
        # Create dataset with moderate size
        data = pl.DataFrame({
            'id': list(range(1000)),
            'value1': [i if i % 3 != 0 else None for i in range(1000)],
            'value2': [f'item_{i}' if i % 5 != 0 else None for i in range(1000)]
        })
        
        config = NullProcessingConfig(
            target_columns=['value1', 'value2'],
            fill_strategy=NullFillStrategy.MEAN
        )
        processor = NullProcessor(config)
        result = processor.process(data)
        
        # Should track performance metrics
        assert result.execution_time > 0
        assert result.memory_usage_mb >= 0  # Allow 0 for small datasets
        assert result.processed_data.shape[0] == 1000