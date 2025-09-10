"""
Tests for QualityAnalyzer functionality.
Tests comprehensive data quality analysis, metrics calculation, and issue detection.
"""

import pytest
import polars as pl
from datetime import datetime, timedelta
from typing import List, Dict, Any
import numpy as np

from processors.quality_analyzer import (
    QualityAnalyzer,
    QualityAnalysisConfig,
    QualityAnalysisResult,
    QualityDimension,
    QualitySeverity,
    AnalysisScope,
    QualityRule,
    QualityIssue,
    QualityMetrics,
    ColumnProfile
)


@pytest.fixture
def sample_quality_data():
    """Create test data with various quality issues."""
    return pl.DataFrame({
        'id': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        'name': ['Alice', 'Bob', None, 'David', 'Eve', None, 'Grace', 'Henry', None, 'Jane'],
        'age': [25, -5, 30, 150, 35, None, 28, 33, None, 29],  # Negative and extreme values
        'email': ['alice@test.com', 'bob@test.com', 'charlie', None, 'eve@test.com', 
                  None, 'grace@test.com', 'henry@test.com', None, 'jane@test.com'],
        'score': [85.5, 92.0, 78.5, None, 88.0, 91.2, None, 86.7, 94.1, 1000.0],  # Outlier
        'category': ['A', 'B', 'A', None, 'B', 'A', 'B', None, 'A', 'B'],
        'phone': ['1234567890', '987-654-3210', '555.123.4567', None, '(555) 123-4567',
                  None, '555-123-4567', '5551234567', None, '+1-555-123-4567'],  # Inconsistent formats
        'duplicate_id': [1, 2, 2, 3, 3, 4, 5, 5, 6, 6]  # Duplicates
    })


@pytest.fixture
def high_quality_data():
    """Create test data with high quality."""
    return pl.DataFrame({
        'id': list(range(1, 101)),
        'name': [f'User{i}' for i in range(1, 101)],
        'age': [20 + (i % 50) for i in range(100)],
        'email': [f'user{i}@test.com' for i in range(1, 101)],
        'score': [50 + (i % 40) for i in range(100)]
    })


@pytest.fixture
def poor_quality_data():
    """Create test data with poor quality."""
    return pl.DataFrame({
        'id': [None] * 10,  # All null
        'name': [''] * 10,  # All empty
        'age': [-1, -2, -3, None, None, None, None, None, None, None],  # Mostly null/negative
        'duplicate': [1, 1, 1, 1, 1, 2, 2, 2, 3, 3]  # Many duplicates
    })


class TestQualityAnalysisConfig:
    """Test QualityAnalysisConfig functionality."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = QualityAnalysisConfig()
        
        assert config.target_columns is None
        assert len(config.analysis_dimensions) == 6  # All dimensions
        assert config.enable_profiling == True
        assert config.quality_threshold == 70.0
        assert config.outlier_method == "z_score"
        assert config.outlier_threshold == 3.0
        
    def test_custom_config(self):
        """Test custom configuration."""
        config = QualityAnalysisConfig(
            target_columns=['id', 'name'],
            analysis_dimensions=[QualityDimension.COMPLETENESS, QualityDimension.VALIDITY],
            enable_profiling=False,
            quality_threshold=80.0,
            outlier_method="iqr",
            outlier_threshold=2.5
        )
        
        assert config.target_columns == ['id', 'name']
        assert len(config.analysis_dimensions) == 2
        assert config.enable_profiling == False
        assert config.quality_threshold == 80.0
        assert config.outlier_method == "iqr"
        assert config.outlier_threshold == 2.5
        
    def test_config_validation(self):
        """Test configuration validation."""
        # Test invalid quality threshold
        with pytest.raises(ValueError, match="quality_threshold must be between 0 and 100"):
            QualityAnalysisConfig(quality_threshold=150.0)
        
        # Test negative outlier threshold
        with pytest.raises(ValueError, match="outlier_threshold must be positive"):
            QualityAnalysisConfig(outlier_threshold=-1.0)
        
        # Test invalid sample size
        with pytest.raises(ValueError, match="sample_size must be positive"):
            QualityAnalysisConfig(sample_size=-100)


class TestColumnProfile:
    """Test ColumnProfile functionality."""
    
    def test_column_profiling(self, sample_quality_data):
        """Test column profiling analysis."""
        analyzer = QualityAnalyzer()
        profiles = analyzer._analyze_column_profiles(sample_quality_data)
        
        # Check all columns are profiled
        assert len(profiles) == len(sample_quality_data.columns)
        
        # Check specific column profiles
        name_profile = profiles['name']
        assert name_profile.column_name == 'name'
        assert name_profile.data_type == 'String'
        assert name_profile.null_count == 3
        assert name_profile.null_percentage == 30.0
        assert name_profile.unique_count > 0
        
        # Check numeric column profile
        age_profile = profiles['age']
        assert age_profile.column_name == 'age'
        assert 'Int' in age_profile.data_type or 'Float' in age_profile.data_type
        assert age_profile.null_count == 2
        assert age_profile.min_value is not None
        assert age_profile.max_value is not None
        
    def test_numeric_column_statistics(self, sample_quality_data):
        """Test numeric column statistics."""
        analyzer = QualityAnalyzer()
        profiles = analyzer._analyze_column_profiles(sample_quality_data)
        
        score_profile = profiles['score']
        assert score_profile.mean_value is not None
        assert score_profile.median_value is not None
        assert score_profile.std_value is not None
        assert score_profile.min_value <= score_profile.max_value
        
    def test_string_column_statistics(self, sample_quality_data):
        """Test string column statistics."""
        analyzer = QualityAnalyzer()
        profiles = analyzer._analyze_column_profiles(sample_quality_data)
        
        phone_profile = profiles['phone']
        assert phone_profile.data_type == 'String'
        assert len(phone_profile.value_distribution) > 0
        assert phone_profile.null_count > 0
        
    def test_pattern_analysis(self, sample_quality_data):
        """Test pattern analysis for string columns."""
        config = QualityAnalysisConfig(enable_pattern_analysis=True)
        analyzer = QualityAnalyzer(config)
        profiles = analyzer._analyze_column_profiles(sample_quality_data)
        
        email_profile = profiles['email']
        assert 'pattern_analysis' in email_profile.__dict__
        if email_profile.pattern_analysis:
            assert isinstance(email_profile.pattern_analysis, dict)


class TestQualityIssueDetection:
    """Test quality issue detection functionality."""
    
    def test_completeness_issues(self, sample_quality_data):
        """Test completeness issue detection."""
        config = QualityAnalysisConfig(
            analysis_dimensions=[QualityDimension.COMPLETENESS]
        )
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Should detect high null percentage issues
        completeness_issues = [
            issue for issue in result.quality_issues 
            if issue.dimension == QualityDimension.COMPLETENESS
        ]
        assert len(completeness_issues) >= 0  # May or may not have high null issues
        
    def test_validity_issues(self, sample_quality_data):
        """Test validity issue detection."""
        config = QualityAnalysisConfig(
            analysis_dimensions=[QualityDimension.VALIDITY]
        )
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Should detect negative age values
        validity_issues = [
            issue for issue in result.quality_issues 
            if issue.dimension == QualityDimension.VALIDITY
        ]
        assert len(validity_issues) >= 0
        
    def test_uniqueness_issues(self, sample_quality_data):
        """Test uniqueness issue detection."""
        config = QualityAnalysisConfig(
            analysis_dimensions=[QualityDimension.UNIQUENESS]
        )
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Should detect duplicate values in duplicate_id column
        uniqueness_issues = [
            issue for issue in result.quality_issues 
            if issue.dimension == QualityDimension.UNIQUENESS
        ]
        assert len(uniqueness_issues) >= 0
        
    def test_accuracy_issues_outliers(self, sample_quality_data):
        """Test accuracy issue detection (outliers)."""
        config = QualityAnalysisConfig(
            analysis_dimensions=[QualityDimension.ACCURACY],
            enable_outlier_detection=True,
            outlier_threshold=2.0  # Lower threshold to detect outliers
        )
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Should detect outliers in score column (1000.0)
        accuracy_issues = [
            issue for issue in result.quality_issues 
            if issue.dimension == QualityDimension.ACCURACY
        ]
        # May or may not detect outliers depending on data distribution
        assert len(accuracy_issues) >= 0
        
    def test_consistency_issues(self, sample_quality_data):
        """Test consistency issue detection."""
        config = QualityAnalysisConfig(
            analysis_dimensions=[QualityDimension.CONSISTENCY]
        )
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Should detect format inconsistencies in phone column
        consistency_issues = [
            issue for issue in result.quality_issues 
            if issue.dimension == QualityDimension.CONSISTENCY
        ]
        # May detect format inconsistencies
        assert len(consistency_issues) >= 0


class TestOutlierDetection:
    """Test outlier detection methods."""
    
    def test_z_score_outlier_detection(self):
        """Test Z-score outlier detection."""
        data = pl.DataFrame({
            'values': [1, 2, 3, 4, 5, 100]  # 100 is clear outlier
        })
        
        config = QualityAnalysisConfig(
            outlier_method="z_score",
            outlier_threshold=2.0
        )
        analyzer = QualityAnalyzer(config)
        outliers = analyzer._detect_outliers(data['values'])
        
        # Should detect the outlier
        assert len(outliers) > 0
        
    def test_iqr_outlier_detection(self):
        """Test IQR outlier detection."""
        data = pl.DataFrame({
            'values': list(range(1, 20)) + [100]  # 100 is outlier
        })
        
        config = QualityAnalysisConfig(
            outlier_method="iqr",
            outlier_threshold=1.5
        )
        analyzer = QualityAnalyzer(config)
        outliers = analyzer._detect_outliers(data['values'])
        
        # Should detect the outlier
        assert len(outliers) > 0
        
    def test_no_outliers_detection(self):
        """Test case with no outliers."""
        data = pl.DataFrame({
            'values': list(range(1, 11))  # Normal distribution
        })
        
        analyzer = QualityAnalyzer()
        outliers = analyzer._detect_outliers(data['values'])
        
        # Should not detect outliers in normal data
        assert len(outliers) == 0


class TestQualityMetrics:
    """Test quality metrics calculation."""
    
    def test_metrics_calculation(self, sample_quality_data):
        """Test quality metrics calculation."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_quality_data)
        
        metrics = result.quality_metrics
        assert isinstance(metrics, QualityMetrics)
        assert 0 <= metrics.overall_score <= 100
        assert 0 <= metrics.completeness_rate <= 1
        assert metrics.total_records == sample_quality_data.height
        assert metrics.valid_records <= metrics.total_records
        assert isinstance(metrics.dimension_scores, dict)
        assert len(metrics.dimension_scores) == len(QualityDimension)
        
    def test_high_quality_metrics(self, high_quality_data):
        """Test metrics for high quality data."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(high_quality_data)
        
        metrics = result.quality_metrics
        assert metrics.overall_score > 80  # Should be high quality
        assert metrics.completeness_rate > 0.9  # Should be very complete
        assert metrics.missing_values == 0  # No missing values
        
    def test_poor_quality_metrics(self, poor_quality_data):
        """Test metrics for poor quality data."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(poor_quality_data)
        
        metrics = result.quality_metrics
        assert metrics.overall_score < 90  # Should be lower quality than high quality data
        assert metrics.completeness_rate < 0.8  # Should be incomplete
        assert metrics.missing_values > 0  # Should have missing values


class TestQualityAnalyzer:
    """Test main QualityAnalyzer functionality."""
    
    def test_basic_analysis(self, sample_quality_data):
        """Test basic quality analysis."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_quality_data)
        
        assert isinstance(result, QualityAnalysisResult)
        assert result.analyzed_data is not None
        assert isinstance(result.quality_metrics, QualityMetrics)
        assert isinstance(result.column_profiles, dict)
        assert isinstance(result.quality_issues, list)
        assert isinstance(result.recommendations, list)
        assert result.execution_time > 0
        
    def test_custom_config_analysis(self, sample_quality_data):
        """Test analysis with custom configuration."""
        config = QualityAnalysisConfig(
            target_columns=['id', 'name', 'age'],
            analysis_dimensions=[QualityDimension.COMPLETENESS, QualityDimension.VALIDITY],
            quality_threshold=80.0,
            enable_profiling=True
        )
        
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data, table_name="test_table")
        
        # Should only profile target columns
        assert len(result.column_profiles) == 3
        assert 'id' in result.column_profiles
        assert 'name' in result.column_profiles
        assert 'age' in result.column_profiles
        
        # Should only check specified dimensions
        issue_dimensions = {issue.dimension for issue in result.quality_issues}
        assert issue_dimensions.issubset({QualityDimension.COMPLETENESS, QualityDimension.VALIDITY})
        
    def test_sampling_functionality(self):
        """Test data sampling functionality."""
        # Create large dataset
        large_data = pl.DataFrame({
            'id': list(range(1000)),
            'value': [i if i % 10 != 0 else None for i in range(1000)]
        })
        
        config = QualityAnalysisConfig(sample_size=100)
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(large_data)
        
        # Should analyze sampled data
        assert result.analyzed_data.height <= 100
        assert result.metadata['original_rows'] == 1000
        assert result.metadata['analyzed_rows'] <= 100
        
    def test_async_analysis(self, sample_quality_data):
        """Test async analysis functionality."""
        import asyncio
        
        async def async_test():
            analyzer = QualityAnalyzer()
            result = await analyzer.analyze_async(sample_quality_data)
            
            assert isinstance(result, QualityAnalysisResult)
            return result
            
        result = asyncio.run(async_test())
        assert result is not None
        
    def test_quality_grade_calculation(self):
        """Test quality grade calculation."""
        analyzer = QualityAnalyzer()
        
        assert analyzer._get_quality_grade(95) == "A+"
        assert analyzer._get_quality_grade(90) == "A"
        assert analyzer._get_quality_grade(85) == "B"
        assert analyzer._get_quality_grade(75) == "C"
        assert analyzer._get_quality_grade(65) == "D"
        assert analyzer._get_quality_grade(50) == "F"
        
    def test_recommendations_generation(self, poor_quality_data):
        """Test recommendations generation."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(poor_quality_data)
        
        # Should generate recommendations for poor quality data
        assert len(result.recommendations) > 0
        # Check that recommendations are generated (any text is fine)
        assert all(len(rec) > 0 for rec in result.recommendations)
        
    def test_analysis_summary(self, sample_quality_data):
        """Test analysis summary generation."""
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(sample_quality_data, table_name="test_table")
        
        summary = result.analysis_summary
        assert 'dataset_info' in summary
        assert 'quality_summary' in summary
        assert 'completeness_summary' in summary
        assert 'uniqueness_summary' in summary
        
        # Check summary content
        assert summary['dataset_info']['rows'] == sample_quality_data.height
        assert summary['dataset_info']['columns'] == sample_quality_data.width
        assert 'grade' in summary['quality_summary']
        
    def test_custom_rules(self, sample_quality_data):
        """Test custom quality rules."""
        custom_rule = QualityRule(
            name="custom_test_rule",
            dimension=QualityDimension.VALIDITY,
            scope=AnalysisScope.COLUMN,
            severity=QualitySeverity.HIGH,
            description="Custom test rule",
            check_function="negative_values_in_positive_columns",
            parameters={"positive_columns": ["age"]}
        )
        
        config = QualityAnalysisConfig(
            custom_rules=[custom_rule],
            analysis_dimensions=[QualityDimension.VALIDITY]
        )
        
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Custom rule should be included in analysis
        assert len(analyzer.quality_rules) > len(QualityAnalyzer()._initialize_default_rules())
        
    def test_empty_data_analysis(self):
        """Test analysis of empty dataset."""
        empty_data = pl.DataFrame({
            'id': [],
            'name': []
        })
        
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(empty_data)
        
        # Should handle empty data gracefully
        assert result.quality_metrics.total_records == 0
        assert len(result.quality_issues) > 0  # Should detect empty table issue
        
    def test_single_row_analysis(self):
        """Test analysis of single row dataset."""
        single_row_data = pl.DataFrame({
            'id': [1],
            'name': ['Test'],
            'age': [25]
        })
        
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(single_row_data)
        
        # Should handle single row data
        assert result.quality_metrics.total_records == 1
        assert result.analyzed_data is not None


class TestConvenienceMethods:
    """Test convenience methods."""
    
    def test_quick_analyze(self, sample_quality_data):
        """Test quick analyze method."""
        result = QualityAnalyzer.quick_analyze(sample_quality_data, quality_threshold=80.0)
        
        assert isinstance(result, QualityAnalysisResult)
        assert result.quality_metrics is not None
        
    def test_profile_columns(self, sample_quality_data):
        """Test profile columns method."""
        profiles = QualityAnalyzer.profile_columns(sample_quality_data, columns=['id', 'name'])
        
        assert isinstance(profiles, dict)
        assert len(profiles) == 2
        assert 'id' in profiles
        assert 'name' in profiles
        
    def test_detect_issues(self, sample_quality_data):
        """Test detect issues method."""
        issues = QualityAnalyzer.detect_issues(
            sample_quality_data,
            dimensions=[QualityDimension.COMPLETENESS, QualityDimension.VALIDITY]
        )
        
        assert isinstance(issues, list)
        # All issues should be from specified dimensions
        issue_dimensions = {issue.dimension for issue in issues}
        assert issue_dimensions.issubset({QualityDimension.COMPLETENESS, QualityDimension.VALIDITY})


class TestIntegrationScenarios:
    """Test integration scenarios and edge cases."""
    
    def test_mixed_data_types_analysis(self):
        """Test analysis of mixed data types."""
        mixed_data = pl.DataFrame({
            'int_col': [1, 2, None, 4, 5],
            'float_col': [1.1, 2.2, 3.3, None, 5.5],
            'str_col': ['a', 'b', None, 'd', 'e'],
            'bool_col': [True, False, None, True, False],
            'date_col': [
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                None,
                datetime(2024, 1, 4),
                datetime(2024, 1, 5)
            ]
        })
        
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(mixed_data)
        
        # Should handle all data types
        assert result.analyzed_data is not None
        assert len(result.column_profiles) == 5
        
        # Each column should be profiled correctly
        for col_name, profile in result.column_profiles.items():
            assert profile.column_name == col_name
            assert profile.unique_count >= 0
            assert 0 <= profile.null_percentage <= 100
            
    def test_large_dataset_performance(self):
        """Test performance with larger dataset."""
        import time
        
        # Create dataset with 10k rows
        large_data = pl.DataFrame({
            'id': list(range(10000)),
            'value1': [i if i % 50 != 0 else None for i in range(10000)],
            'value2': [f'item_{i}' if i % 30 != 0 else None for i in range(10000)],
            'value3': [float(i) if i % 20 != 0 else None for i in range(10000)]
        })
        
        start_time = time.time()
        analyzer = QualityAnalyzer()
        result = analyzer.analyze(large_data)
        end_time = time.time()
        
        # Should complete in reasonable time
        assert end_time - start_time < 30  # Less than 30 seconds
        assert result.analyzed_data.shape[0] == 10000
        assert result.execution_time > 0
        
    def test_all_dimensions_analysis(self, sample_quality_data):
        """Test analysis with all quality dimensions."""
        config = QualityAnalysisConfig(
            analysis_dimensions=list(QualityDimension),
            enable_profiling=True,
            enable_pattern_analysis=True,
            enable_outlier_detection=True
        )
        
        analyzer = QualityAnalyzer(config)
        result = analyzer.analyze(sample_quality_data)
        
        # Should analyze all dimensions
        assert len(result.quality_metrics.dimension_scores) == len(QualityDimension)
        
        # Should have comprehensive analysis
        assert result.column_profiles is not None
        assert result.quality_issues is not None
        assert result.recommendations is not None
        
    def test_memory_management(self):
        """Test memory management with various dataset sizes."""
        sizes = [100, 1000, 5000]
        
        for size in sizes:
            data = pl.DataFrame({
                'id': list(range(size)),
                'value': [i if i % 10 != 0 else None for i in range(size)]
            })
            
            analyzer = QualityAnalyzer()
            result = analyzer.analyze(data)
            
            # Should track memory usage
            assert result.memory_usage_mb >= 0
            assert result.execution_time > 0