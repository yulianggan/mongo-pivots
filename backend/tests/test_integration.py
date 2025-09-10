"""
Integration tests for all data processors.
Tests the integration and pipeline functionality of all processors working together.
"""

import pytest
import polars as pl
from datetime import datetime, timedelta
import asyncio

from processors.deduplication import DeduplicationEngine, DeduplicationConfig, MatchType
from processors.time_aligner import TimeAligner, TimeAlignmentConfig, TimeGranularity
from processors.null_processor import NullProcessor, NullProcessingConfig, NullFillStrategy
from processors.quality_analyzer import QualityAnalyzer, QualityAnalysisConfig


@pytest.fixture
def complex_test_data():
    """Create complex test data with various issues."""
    return pl.DataFrame({
        'id': [1, 2, 2, 3, 4, 4, 5, None, 6, 7],  # Duplicates and nulls
        'timestamp': [
            datetime(2024, 1, 1, 10, 0, 0),
            datetime(2024, 1, 1, 10, 5, 0), 
            datetime(2024, 1, 1, 10, 5, 0),  # Duplicate time
            None,  # Missing timestamp
            datetime(2024, 1, 1, 10, 15, 0),
            datetime(2024, 1, 1, 10, 15, 0),  # Duplicate time
            datetime(2024, 1, 1, 10, 20, 0),
            datetime(2024, 1, 1, 10, 25, 0),
            datetime(2024, 1, 1, 10, 30, 0),
            datetime(2024, 1, 1, 10, 35, 0)
        ],
        'value': [100.0, 200.0, 200.0, None, 300.0, 300.0, None, 400.0, 500.0, 600.0],
        'category': ['A', 'B', 'B', 'A', None, 'C', 'A', 'B', 'C', None],
        'score': [85, 92, 92, None, 78, 78, 88, None, 94, 87]
    })


class TestBasicIntegration:
    """Test basic integration between processors."""
    
    def test_deduplication_integration(self, complex_test_data):
        """Test deduplication engine with realistic data."""
        config = DeduplicationConfig(
            columns=['id'],
            match_type=MatchType.EXACT
        )
        
        engine = DeduplicationEngine(config)
        result = engine.deduplicate(complex_test_data)
        
        # Should have fewer rows after deduplication
        assert result.deduplicated_data.height < complex_test_data.height
        assert result.duplicates_removed > 0
        
    def test_time_alignment_integration(self, complex_test_data):
        """Test time aligner with realistic data."""
        config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE
        )
        
        aligner = TimeAligner(config)
        result = aligner.align(complex_test_data)
        
        # Should handle time alignment
        assert result.aligned_data is not None
        assert result.alignment_statistics is not None
        
    def test_null_processing_integration(self, complex_test_data):
        """Test null processor with realistic data."""
        config = NullProcessingConfig(
            target_columns=['value', 'category', 'score'],
            fill_strategy=NullFillStrategy.FORWARD_FILL
        )
        
        processor = NullProcessor(config)
        result = processor.process(complex_test_data)
        
        # Should reduce null count
        original_nulls = sum(col.null_count() for col in [
            complex_test_data['value'], 
            complex_test_data['category'], 
            complex_test_data['score']
        ])
        processed_nulls = sum(col.null_count() for col in [
            result.processed_data['value'], 
            result.processed_data['category'], 
            result.processed_data['score']
        ])
        
        assert processed_nulls <= original_nulls
        
    def test_quality_analysis_integration(self, complex_test_data):
        """Test quality analyzer with realistic data."""
        config = QualityAnalysisConfig(
            quality_threshold=70.0,
            enable_profiling=True,
            enable_outlier_detection=True
        )
        
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(complex_test_data)
        
        # Should generate comprehensive analysis
        assert result.quality_metrics is not None
        assert len(result.column_profiles) > 0
        assert isinstance(result.quality_issues, list)
        assert len(result.recommendations) > 0
        assert 0 <= result.quality_metrics.overall_score <= 100


class TestProcessorPipeline:
    """Test processors working together in a pipeline."""
    
    def test_sequential_processing_pipeline(self, complex_test_data):
        """Test running processors in sequence."""
        # Step 1: Quality analysis on original data
        quality_analyzer = QualityAnalyzer()
        initial_quality = quality_analyzer.analyze(complex_test_data, "original")
        
        # Step 2: Deduplication
        dedup_config = DeduplicationConfig(
            columns=['id'],
            match_type=MatchType.EXACT
        )
        dedup_engine = DeduplicationEngine(dedup_config)
        dedup_result = dedup_engine.deduplicate(complex_test_data)
        
        # Step 3: Null processing
        null_config = NullProcessingConfig(
            target_columns=['value', 'category', 'score'],
            fill_strategy=NullFillStrategy.MEAN
        )
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(dedup_result.deduplicated_data)
        
        # Step 4: Time alignment
        time_config = TimeAlignmentConfig(
            time_columns=['timestamp'],
            target_granularity=TimeGranularity.MINUTE
        )
        time_aligner = TimeAligner(time_config)
        time_result = time_aligner.align(null_result.processed_data)
        
        # Step 5: Final quality analysis
        final_quality = quality_analyzer.analyze(time_result.aligned_data, "processed")
        
        # Verify pipeline results
        assert dedup_result.deduplicated_data.height <= complex_test_data.height
        assert null_result.processed_data is not None
        assert time_result.aligned_data is not None
        assert final_quality.quality_metrics is not None
        
        # Time alignment may increase records by filling missing time points
        # Quality should be maintained or improved
        assert final_quality.quality_metrics is not None
        
    @pytest.mark.asyncio
    async def test_async_processing_pipeline(self, complex_test_data):
        """Test async processing pipeline."""
        # Run multiple processors asynchronously
        quality_task = QualityAnalyzer().analyze_async(complex_test_data)
        
        dedup_config = DeduplicationConfig(columns=['id'])
        dedup_task = DeduplicationEngine(dedup_config).deduplicate_async(complex_test_data)
        
        null_config = NullProcessingConfig(target_columns=['value'])
        null_task = NullProcessor(null_config).process_async(complex_test_data)
        
        # Wait for all tasks
        quality_result, dedup_result, null_result = await asyncio.gather(
            quality_task, dedup_task, null_task
        )
        
        # Verify all results
        assert quality_result.quality_metrics is not None
        assert dedup_result.deduplicated_data is not None
        assert null_result.processed_data is not None
        
    def test_processor_interoperability(self, complex_test_data):
        """Test that processed data from one processor works with others."""
        # Process with deduplication first
        dedup_config = DeduplicationConfig(columns=['id'])
        dedup_engine = DeduplicationEngine(dedup_config)
        dedup_result = dedup_engine.deduplicate(complex_test_data)
        
        # Use deduplication result in quality analyzer
        quality_analyzer = QualityAnalyzer()
        quality_result = quality_analyzer.analyze(dedup_result.deduplicated_data)
        
        # Use deduplication result in null processor
        null_config = NullProcessingConfig(target_columns=['value'])
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(dedup_result.deduplicated_data)
        
        # Verify interoperability
        assert quality_result.analyzed_data is not None
        assert null_result.processed_data is not None
        
        # Data should maintain structure
        assert set(dedup_result.deduplicated_data.columns) == set(quality_result.analyzed_data.columns)
        assert set(dedup_result.deduplicated_data.columns) == set(null_result.processed_data.columns)


class TestPerformanceScenarios:
    """Test performance and scalability scenarios."""
    
    def test_large_dataset_processing(self):
        """Test processing with larger dataset."""
        # Create large dataset (5000 rows)
        large_data = pl.DataFrame({
            'id': list(range(5000)) + list(range(100)),  # Some duplicates
            'timestamp': [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(5100)],
            'value': [i * 1.5 if i % 50 != 0 else None for i in range(5100)],  # Some nulls
            'category': [f'cat_{i%10}' if i % 30 != 0 else None for i in range(5100)]
        })
        
        # Test each processor with large data
        # Deduplication
        dedup_config = DeduplicationConfig(columns=['id'])
        dedup_engine = DeduplicationEngine(dedup_config)
        dedup_result = dedup_engine.deduplicate(large_data)
        assert dedup_result.deduplicated_data.height < large_data.height
        
        # Quality analysis (with sampling)
        quality_config = QualityAnalysisConfig(sample_size=1000)
        quality_analyzer = QualityAnalyzer(quality_config)
        quality_result = quality_analyzer.analyze(large_data)
        assert quality_result.analyzed_data.height <= 1000
        
        # Null processing
        null_config = NullProcessingConfig(target_columns=['value', 'category'])
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(large_data)
        assert null_result.processed_data.height == large_data.height
        
    def test_memory_usage_monitoring(self, complex_test_data):
        """Test memory usage monitoring across processors."""
        processors_results = []
        
        # Test each processor and collect memory usage
        quality_analyzer = QualityAnalyzer()
        quality_result = quality_analyzer.analyze(complex_test_data)
        processors_results.append(('Quality', quality_result.memory_usage_mb))
        
        dedup_config = DeduplicationConfig(columns=['id'])
        dedup_engine = DeduplicationEngine(dedup_config)
        dedup_result = dedup_engine.deduplicate(complex_test_data)
        processors_results.append(('Deduplication', dedup_result.memory_usage_mb))
        
        null_config = NullProcessingConfig(target_columns=['value'])
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(complex_test_data)
        processors_results.append(('Null Processing', null_result.memory_usage_mb))
        
        # Verify memory usage is tracked
        for name, memory_mb in processors_results:
            assert memory_mb >= 0, f"{name} should track memory usage"
        
    def test_execution_time_monitoring(self, complex_test_data):
        """Test execution time monitoring across processors."""
        processors_times = []
        
        # Test each processor and collect execution times
        quality_analyzer = QualityAnalyzer()
        quality_result = quality_analyzer.analyze(complex_test_data)
        processors_times.append(('Quality', quality_result.execution_time))
        
        null_config = NullProcessingConfig(target_columns=['value'])
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(complex_test_data)
        processors_times.append(('Null Processing', null_result.execution_time))
        
        # Verify execution time is tracked
        for name, exec_time in processors_times:
            assert exec_time > 0, f"{name} should track execution time"


class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    def test_empty_dataset_handling(self):
        """Test all processors with empty dataset."""
        empty_data = pl.DataFrame({
            'id': [],
            'timestamp': [],
            'value': []
        })
        
        # Quality analysis should handle empty data
        quality_analyzer = QualityAnalyzer()
        quality_result = quality_analyzer.analyze(empty_data)
        assert quality_result.quality_metrics.total_records == 0
        
        # Null processor should handle empty data
        null_config = NullProcessingConfig(target_columns=['value'])
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(empty_data)
        assert null_result.processed_data.height == 0
        
    def test_single_row_dataset(self):
        """Test processors with single row dataset."""
        single_row_data = pl.DataFrame({
            'id': [1],
            'timestamp': [datetime(2024, 1, 1)],
            'value': [100.0],
            'category': ['A']
        })
        
        # All processors should handle single row
        quality_analyzer = QualityAnalyzer()
        quality_result = quality_analyzer.analyze(single_row_data)
        assert quality_result.quality_metrics.total_records == 1
        
        dedup_config = DeduplicationConfig(columns=['id'])
        dedup_engine = DeduplicationEngine(dedup_config)
        dedup_result = dedup_engine.deduplicate(single_row_data)
        assert dedup_result.deduplicated_data.height == 1
        
    def test_all_null_columns(self):
        """Test processors with all null columns."""
        all_null_data = pl.DataFrame({
            'id': [None, None, None],
            'value': [None, None, None],
            'category': [None, None, None]
        })
        
        # Quality analysis should detect poor quality
        quality_analyzer = QualityAnalyzer()
        quality_result = quality_analyzer.analyze(all_null_data)
        assert quality_result.quality_metrics.completeness_rate < 0.1
        
        # Null processor should handle all nulls
        null_config = NullProcessingConfig(
            target_columns=['value', 'category'],
            fill_strategy=NullFillStrategy.CONSTANT,
            constant_fill_value='DEFAULT'
        )
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(all_null_data)
        assert null_result.processed_data['value'].null_count() == 0
        assert null_result.processed_data['category'].null_count() == 0


class TestConfigurationIntegration:
    """Test configuration integration and compatibility."""
    
    def test_compatible_configurations(self, complex_test_data):
        """Test that processor configurations work well together."""
        # Create compatible configurations
        dedup_config = DeduplicationConfig(
            columns=['id']
        )
        
        null_config = NullProcessingConfig(
            target_columns=['value', 'score'],
            fill_strategy=NullFillStrategy.MEAN
        )
        
        quality_config = QualityAnalysisConfig(
            enable_profiling=True,
            quality_threshold=80.0
        )
        
        # Process sequentially with compatible configs
        dedup_engine = DeduplicationEngine(dedup_config)
        dedup_result = dedup_engine.deduplicate(complex_test_data)
        
        null_processor = NullProcessor(null_config)
        null_result = null_processor.process(dedup_result.deduplicated_data)
        
        quality_analyzer = QualityAnalyzer(quality_config)
        quality_result = quality_analyzer.analyze(null_result.processed_data)
        
        # Verify successful processing
        assert dedup_result.deduplicated_data is not None
        assert null_result.processed_data is not None
        assert quality_result.quality_metrics is not None
        
    def test_configuration_validation(self):
        """Test configuration validation across processors."""
        # Test invalid configurations are caught
        
        # Invalid null processing config
        with pytest.raises(ValueError):
            NullProcessingConfig(target_columns=[])
        
        # Invalid quality analysis config
        with pytest.raises(ValueError):
            QualityAnalysisConfig(quality_threshold=150.0)
        
        # These validations ensure configs are properly checked


# Run async test
def test_async_integration():
    """Test wrapper for async integration test."""
    async def run_test():
        complex_data = pl.DataFrame({
            'id': [1, 2, 2, 3],
            'value': [100, 200, 200, 300]
        })
        
        pipeline = TestProcessorPipeline()
        await pipeline.test_async_processing_pipeline(complex_data)
    
    asyncio.run(run_test())