"""
智能推断系统测试套件 - 验证准确性和性能
测试所有类型推断、数据验证和类型转换功能
"""
import pytest
import asyncio
import tempfile
import json
import time
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, List

import polars as pl

from schema.inferencer import (
    SchemaInferencer, TypeDetector, DateTimeParser, NullHandler,
    DetectedDataType, InferenceConfidence, DataTypeCategory
)
from schema.validators import DataValidator, ValidationSeverity
from schema.converters import TypeConverter, ConversionStrategy
from connectors.base import DataSourceConnector, DataSourceType


class TestTypeDetector:
    """类型检测器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.detector = TypeDetector(sample_size=100, confidence_threshold=0.7)
    
    def test_integer_detection(self):
        """测试整数类型检测"""
        # 纯整数
        values = [1, 2, 3, 100, -50, 0]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.INTEGER
        assert result.confidence in [InferenceConfidence.HIGH, InferenceConfidence.VERY_HIGH]
        assert result.category == DataTypeCategory.NUMERIC
        assert result.null_count == 0
    
    def test_float_detection(self):
        """测试浮点数类型检测"""
        values = [1.1, 2.5, 3.14, 100.0, -50.25]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.FLOAT
        assert result.confidence in [InferenceConfidence.HIGH, InferenceConfidence.VERY_HIGH]
        assert result.category == DataTypeCategory.NUMERIC
    
    def test_boolean_detection(self):
        """测试布尔类型检测"""
        # 标准布尔值
        values = [True, False, True, True, False]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.BOOLEAN
        assert result.confidence in [InferenceConfidence.HIGH, InferenceConfidence.VERY_HIGH]
        
        # 字符串布尔值
        values = ["true", "false", "TRUE", "FALSE", "1", "0"]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.BOOLEAN
        assert result.confidence in [InferenceConfidence.HIGH, InferenceConfidence.VERY_HIGH]
    
    def test_datetime_detection(self):
        """测试日期时间类型检测"""
        # ISO格式
        values = ["2023-01-01T12:00:00", "2023-02-15T15:30:45", "2023-03-20T08:15:30"]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.DATETIME
        assert result.confidence in [InferenceConfidence.MEDIUM, InferenceConfidence.HIGH]
        assert result.category == DataTypeCategory.TEMPORAL
    
    def test_date_detection(self):
        """测试日期类型检测"""
        values = ["2023-01-01", "2023-02-15", "2023-03-20"]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.DATE
        assert result.category == DataTypeCategory.TEMPORAL
    
    def test_timestamp_detection(self):
        """测试时间戳检测"""
        # 秒级时间戳
        values = [1640995200, 1641081600, 1641168000]  # 2022年1月的时间戳
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.TIMESTAMP
        assert result.category == DataTypeCategory.TEMPORAL
    
    def test_categorical_detection(self):
        """测试分类数据检测"""
        # 重复值较多
        values = ["A", "B", "A", "C", "B", "A", "A", "B", "C", "A"]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.CATEGORICAL
        assert result.category == DataTypeCategory.TEXT
    
    def test_string_detection(self):
        """测试字符串类型检测"""
        # 唯一值较多
        values = [f"text_{i}" for i in range(50)]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.STRING
        assert result.category == DataTypeCategory.TEXT
    
    def test_json_detection(self):
        """测试JSON类型检测"""
        # JSON对象
        values = [
            '{"name": "John", "age": 30}',
            '{"name": "Jane", "age": 25}',
            '{"name": "Bob", "age": 35}'
        ]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.JSON_OBJECT
        assert result.category == DataTypeCategory.COMPLEX
        
        # JSON数组
        values = ['[1, 2, 3]', '[4, 5, 6]', '[7, 8, 9]']
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.JSON_ARRAY
    
    def test_null_detection(self):
        """测试空值检测"""
        values = [None, None, None]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.NULL
        assert result.category == DataTypeCategory.NULL
        assert result.null_percentage == 100.0
    
    def test_mixed_types_with_nulls(self):
        """测试含空值的混合类型"""
        values = [1, 2, None, 4, 5, None, 7]
        result = self.detector.detect_type(values, "test_column")
        
        assert result.detected_type == DetectedDataType.INTEGER
        assert result.null_count == 2
        assert result.null_percentage > 0


class TestDateTimeParser:
    """时间解析器测试"""
    
    def test_iso_format_detection(self):
        """测试ISO格式检测"""
        values = ["2023-01-01T12:00:00Z", "2023-02-15T15:30:45Z"]
        result = DateTimeParser.infer_datetime_format(values)
        
        assert result is not None
        assert "T" in result.detected_format
        assert result.confidence > 0.8
    
    def test_date_format_detection(self):
        """测试日期格式检测"""
        values = ["2023-01-01", "2023-02-15", "2023-03-20"]
        result = DateTimeParser.infer_datetime_format(values)
        
        assert result is not None
        assert result.detected_format == "%Y-%m-%d"
        assert result.confidence > 0.9
    
    def test_timestamp_detection(self):
        """测试时间戳检测"""
        # 秒级时间戳
        timestamp_result = DateTimeParser.detect_timestamp(1640995200)
        assert timestamp_result is not None
        assert timestamp_result.is_timestamp
        assert timestamp_result.timestamp_unit == "seconds"
        
        # 毫秒级时间戳
        timestamp_result = DateTimeParser.detect_timestamp(1640995200000)
        assert timestamp_result is not None
        assert timestamp_result.timestamp_unit == "milliseconds"
    
    def test_multiple_formats(self):
        """测试多种日期格式"""
        test_cases = [
            (["01/01/2023", "02/15/2023"], "%m/%d/%Y"),
            (["01-01-2023", "02-15-2023"], "%m-%d-%Y"),
            (["2023/01/01", "2023/02/15"], "%Y/%m/%d"),
            (["20230101", "20230215"], "%Y%m%d"),
        ]
        
        for values, expected_format in test_cases:
            result = DateTimeParser.infer_datetime_format(values)
            assert result is not None, f"Failed to detect format for {values}"
            assert result.detected_format == expected_format


class TestNullHandler:
    """空值处理器测试"""
    
    def test_null_value_recognition(self):
        """测试空值识别"""
        null_values = [None, "", " ", "NULL", "null", "N/A", "na", "-", "?", float('nan')]
        
        for value in null_values:
            assert NullHandler.is_null_value(value), f"Failed to recognize {value} as null"
    
    def test_non_null_values(self):
        """测试非空值识别"""
        non_null_values = [0, "0", False, "false", "text", 123, []]
        
        for value in non_null_values:
            assert not NullHandler.is_null_value(value), f"Incorrectly identified {value} as null"
    
    def test_null_statistics(self):
        """测试空值统计"""
        values = [1, 2, None, "NULL", 5, "", 7, "N/A", 9, 10]
        stats = NullHandler.get_null_statistics(values)
        
        assert stats['total_count'] == 10
        assert stats['null_count'] == 4  # None, "NULL", "", "N/A"
        assert stats['null_percentage'] == 40.0
        assert stats['has_nulls'] is True


class TestSchemaInferencer:
    """结构推断器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.inferencer = SchemaInferencer(sample_size=100)
    
    def test_simple_dataframe_inference(self):
        """测试简单DataFrame推断"""
        # 创建测试数据
        data = {
            'id': [1, 2, 3, 4, 5],
            'name': ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve'],
            'age': [25, 30, 35, 28, 32],
            'salary': [50000.5, 60000.0, 70000.75, 55000.0, 65000.25],
            'active': [True, False, True, True, False],
            'join_date': ['2023-01-01', '2023-02-15', '2023-03-10', '2023-04-05', '2023-05-20']
        }
        
        df = pl.DataFrame(data)
        schema = self.inferencer.infer_schema(df)
        
        # 验证基本信息
        assert schema['row_count'] == 5
        assert schema['column_count'] == 6
        assert 'columns' in schema
        assert 'quality_metrics' in schema
        
        # 验证列类型推断
        columns = schema['columns']
        assert columns['id']['detected_type'] == 'integer'
        assert columns['name']['detected_type'] in ['string', 'categorical']  # 可能被识别为分类
        assert columns['age']['detected_type'] == 'integer'
        assert columns['salary']['detected_type'] == 'float'
        assert columns['active']['detected_type'] == 'boolean'
        assert columns['join_date']['detected_type'] == 'date'
    
    def test_complex_dataframe_inference(self):
        """测试复杂DataFrame推断"""
        # 创建包含各种数据类型的复杂数据
        data = {
            'mixed_numbers': ['123', 45.6, '789', None, 0],
            'categories': ['A', 'B', 'A', 'C', 'B'],  # 分类数据
            'timestamps': [1640995200, 1641081600, 1641168000, 1641254400, 1641340800],
            'json_data': [
                '{"name": "John"}',
                '{"name": "Jane"}', 
                '{"name": "Bob"}',
                '{"name": "Alice"}',
                '{"name": "Charlie"}'
            ],
            'nullable_text': ['hello', None, 'world', '', 'test']
        }
        
        df = pl.DataFrame(data)
        schema = self.inferencer.infer_schema(df)
        
        columns = schema['columns']
        
        # 验证混合数字被正确识别
        assert columns['mixed_numbers']['detected_type'] in ['float', 'string']
        
        # 验证分类数据
        assert columns['categories']['detected_type'] == 'categorical'
        
        # 验证时间戳
        assert columns['timestamps']['detected_type'] == 'timestamp'
        
        # 验证JSON数据
        assert columns['json_data']['detected_type'] == 'json_object'
        
        # 验证空值统计
        assert columns['nullable_text']['null_count'] >= 1  # 至少有一个空值
    
    def test_quality_metrics_calculation(self):
        """测试数据质量指标计算"""
        # 创建质量不同的数据
        data = {
            'good_column': [1, 2, 3, 4, 5],  # 高质量
            'bad_column': [None, "", "?", "N/A", None],  # 低质量，全空值
            'mixed_column': [1, "text", 3.14, True, None]  # 混合类型，中等质量
        }
        
        df = pl.DataFrame(data)
        schema = self.inferencer.infer_schema(df)
        
        quality_metrics = schema['quality_metrics']
        
        assert 'data_quality_score' in quality_metrics
        assert 'confidence_distribution' in quality_metrics
        assert 'type_distribution' in quality_metrics
        assert quality_metrics['total_columns'] == 3
        
        # 数据质量分数应该是0-100之间
        assert 0 <= quality_metrics['data_quality_score'] <= 100
    
    def test_type_conversion_suggestions(self):
        """测试类型转换建议"""
        data = {
            'string_numbers': ['123', '456', '789'],  # 应该建议转换为整数
            'float_strings': ['12.3', '45.6', '78.9'],  # 应该建议转换为浮点数
            'boolean_strings': ['true', 'false', 'true']  # 应该建议转换为布尔值
        }
        
        df = pl.DataFrame(data)
        schema = self.inferencer.infer_schema(df)
        suggestions = self.inferencer.get_type_conversion_suggestions(schema)
        
        assert len(suggestions) > 0
        
        # 检查是否有转换建议
        for column_name, column_suggestions in suggestions.items():
            assert len(column_suggestions) > 0


class TestDataValidator:
    """数据验证器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.validator = DataValidator()
    
    def test_basic_validation(self):
        """测试基本验证功能"""
        # 创建测试数据
        data = {
            'id': [1, 2, 3, 4, 5],
            'name': ['Alice', 'Bob', None, 'Diana', ''],  # 包含空值
            'age': [25, 30, 35, 150, -5],  # 包含异常值
            'email': ['alice@test.com', 'invalid-email', 'bob@test.com', 'charlie@test.com', 'diana@test.com']
        }
        
        df = pl.DataFrame(data)
        report = self.validator.validate_dataframe(df)
        
        # 验证报告基本信息
        assert report.total_rows == 5
        assert report.total_columns == 4
        assert 0 <= report.overall_quality_score <= 100
        
        # 验证列报告
        assert len(report.column_reports) == 4
        
        # 检查是否检测到问题
        name_report = report.column_reports['name']
        assert name_report.error_count > 0 or name_report.warning_count > 0  # 应该检测到空值问题
        
        age_report = report.column_reports['age']
        # 年龄列应该检测到异常值（150和-5）
        outlier_results = [r for r in age_report.validation_results if 'outlier' in r.rule.value.lower()]
        assert len(outlier_results) > 0 or age_report.warning_count > 0
    
    def test_custom_validation_rules(self):
        """测试自定义验证规则"""
        data = {
            'score': [85, 92, 78, 105, 88],  # 分数应在0-100之间
            'grade': ['A', 'B', 'C', 'X', 'A']  # 成绩应在特定列表中
        }
        
        df = pl.DataFrame(data)
        
        # 定义自定义规则
        custom_rules = {
            'score': [
                {'type': 'range', 'params': {'min_value': 0, 'max_value': 100}}
            ],
            'grade': [
                {'type': 'enum', 'params': {'allowed_values': ['A', 'B', 'C', 'D', 'F']}}
            ]
        }
        
        report = self.validator.validate_dataframe(df, custom_rules=custom_rules)
        
        # 验证分数范围检查
        score_report = report.column_reports['score']
        range_violations = [r for r in score_report.validation_results 
                          if 'max_value' in r.rule.value or r.affected_count > 0]
        assert len(range_violations) > 0  # 应该检测到105超出范围
        
        # 验证成绩枚举检查
        grade_report = report.column_reports['grade']
        enum_violations = [r for r in grade_report.validation_results 
                         if 'in_list' in r.rule.value and not r.passed]
        assert len(enum_violations) > 0  # 应该检测到'X'不在允许列表中
    
    def test_outlier_detection(self):
        """测试异常值检测"""
        from schema.validators import OutlierDetector
        
        # 正常数据加上异常值
        normal_values = [10, 12, 11, 13, 10, 12, 11, 14, 13, 12]
        outlier_values = normal_values + [100, -50]  # 添加明显异常值
        
        outlier_indices, stats = OutlierDetector.detect_statistical_outliers(
            outlier_values, method='iqr', threshold=1.5
        )
        
        # 应该检测到异常值
        assert len(outlier_indices) > 0
        assert 10 in outlier_indices  # 100的索引
        assert 11 in outlier_indices  # -50的索引
        
        # 验证统计信息
        assert 'method' in stats
        assert 'q1' in stats
        assert 'q3' in stats


class TestTypeConverter:
    """类型转换器测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.converter = TypeConverter()
    
    def test_integer_conversion(self):
        """测试整数转换"""
        test_cases = [
            ("123", 123, True),
            ("123.0", 123, True),
            ("123.5", 123, True),  # 会丢失精度但转换成功
            ("abc", None, False),  # 转换失败
            (123.7, 123, True)
        ]
        
        for input_value, expected, should_succeed in test_cases:
            result = self.converter.convert_value(input_value, DetectedDataType.INTEGER)
            
            if should_succeed:
                assert result.success, f"Failed to convert {input_value} to integer"
                if expected is not None:
                    assert result.converted_value == expected
            else:
                assert not result.success, f"Should have failed to convert {input_value}"
    
    def test_float_conversion(self):
        """测试浮点数转换"""
        test_cases = [
            ("123.45", 123.45, True),
            ("123", 123.0, True),
            ("abc", None, False),
            (123, 123.0, True)
        ]
        
        for input_value, expected, should_succeed in test_cases:
            result = self.converter.convert_value(input_value, DetectedDataType.FLOAT)
            
            if should_succeed:
                assert result.success
                if expected is not None:
                    assert abs(result.converted_value - expected) < 1e-10
            else:
                assert not result.success
    
    def test_boolean_conversion(self):
        """测试布尔值转换"""
        true_values = ["true", "TRUE", "1", "yes", "Y", True, 1]
        false_values = ["false", "FALSE", "0", "no", "N", False, 0]
        
        for value in true_values:
            result = self.converter.convert_value(value, DetectedDataType.BOOLEAN)
            assert result.success, f"Failed to convert {value} to boolean"
            assert result.converted_value is True
        
        for value in false_values:
            result = self.converter.convert_value(value, DetectedDataType.BOOLEAN)
            assert result.success, f"Failed to convert {value} to boolean"
            assert result.converted_value is False
    
    def test_datetime_conversion(self):
        """测试日期时间转换"""
        test_values = [
            "2023-01-01T12:00:00",
            "2023-01-01 12:00:00", 
            "2023-01-01",
            1640995200  # 时间戳
        ]
        
        for value in test_values:
            result = self.converter.convert_value(value, DetectedDataType.DATETIME)
            assert result.success, f"Failed to convert {value} to datetime"
            assert isinstance(result.converted_value, datetime)
    
    def test_batch_conversion(self):
        """测试批量转换"""
        values = ["1", "2", "3.5", "abc", "5"]
        result = self.converter.convert_batch(values, DetectedDataType.INTEGER)
        
        assert result.total_count == 5
        assert result.success_count >= 3  # 至少前3个应该成功
        assert result.failure_count >= 1  # "abc"应该失败
        assert len(result.converted_values) == 5
        assert len(result.failed_indices) >= 1
    
    def test_dataframe_column_conversion(self):
        """测试DataFrame列转换"""
        data = {'numbers': ['1', '2', '3', '4', '5']}
        df = pl.DataFrame(data)
        
        new_df, conversion_result = self.converter.convert_dataframe_column(
            df, 'numbers', DetectedDataType.INTEGER
        )
        
        assert conversion_result.success_count == 5
        assert conversion_result.failure_count == 0
        
        # 验证转换后的数据类型
        converted_values = new_df['numbers'].to_list()
        assert all(isinstance(v, int) for v in converted_values)


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    def test_inference_performance(self):
        """测试推断性能"""
        # 创建大数据集
        size = 10000
        data = {
            'integers': list(range(size)),
            'floats': [i * 0.1 for i in range(size)],
            'strings': [f"text_{i}" for i in range(size)],
            'booleans': [i % 2 == 0 for i in range(size)],
            'dates': [f"2023-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(size)]
        }
        
        df = pl.DataFrame(data)
        inferencer = SchemaInferencer(sample_size=1000)
        
        start_time = time.time()
        schema = inferencer.infer_schema(df)
        inference_time = time.time() - start_time
        
        # 性能要求：10万行数据推断应在10秒内完成
        assert inference_time < 10.0, f"Inference took too long: {inference_time:.2f}s"
        
        # 验证结果正确性
        assert schema['row_count'] == size
        assert schema['column_count'] == 5
        
        # 验证推断质量
        quality_score = schema['quality_metrics']['data_quality_score']
        assert quality_score > 80, f"Quality score too low: {quality_score}"
    
    def test_validation_performance(self):
        """测试验证性能"""
        # 创建测试数据
        size = 5000
        data = {
            'id': list(range(size)),
            'value': [i * 0.1 for i in range(size)],
            'category': [f"cat_{i % 10}" for i in range(size)]
        }
        
        df = pl.DataFrame(data)
        validator = DataValidator()
        
        start_time = time.time()
        report = validator.validate_dataframe(df)
        validation_time = time.time() - start_time
        
        # 验证性能要求
        assert validation_time < 5.0, f"Validation took too long: {validation_time:.2f}s"
        
        # 验证结果
        assert report.total_rows == size
        assert len(report.column_reports) == 3
    
    def test_conversion_performance(self):
        """测试转换性能"""
        # 创建大量需要转换的数据
        size = 10000
        string_numbers = [str(i) for i in range(size)]
        
        converter = TypeConverter()
        
        start_time = time.time()
        result = converter.convert_batch(string_numbers, DetectedDataType.INTEGER)
        conversion_time = time.time() - start_time
        
        # 转换性能要求
        assert conversion_time < 2.0, f"Conversion took too long: {conversion_time:.2f}s"
        
        # 验证转换结果
        assert result.success_count == size
        assert result.failure_count == 0


class TestAccuracyBenchmarks:
    """准确性基准测试"""
    
    def test_type_inference_accuracy(self):
        """测试类型推断准确率"""
        # 创建已知类型的测试数据集
        test_cases = [
            # (数据, 期望类型, 期望置信度阈值)
            ([1, 2, 3, 4, 5], DetectedDataType.INTEGER, 0.95),
            ([1.1, 2.2, 3.3, 4.4, 5.5], DetectedDataType.FLOAT, 0.95),
            ([True, False, True, True, False], DetectedDataType.BOOLEAN, 0.95),
            (['2023-01-01', '2023-02-15', '2023-03-20'], DetectedDataType.DATE, 0.8),
            (['A', 'B', 'A', 'C', 'B', 'A'], DetectedDataType.CATEGORICAL, 0.9),
            ([f"text_{i}" for i in range(20)], DetectedDataType.STRING, 0.9)
        ]
        
        detector = TypeDetector()
        correct_predictions = 0
        high_confidence_predictions = 0
        
        for values, expected_type, confidence_threshold in test_cases:
            result = detector.detect_type(values, "test_column")
            
            if result.detected_type == expected_type:
                correct_predictions += 1
            
            confidence_score = detector._confidence_to_score(result.confidence)
            if confidence_score >= confidence_threshold:
                high_confidence_predictions += 1
        
        # 准确率要求
        accuracy = correct_predictions / len(test_cases)
        confidence_rate = high_confidence_predictions / len(test_cases)
        
        assert accuracy >= 0.95, f"Accuracy too low: {accuracy:.2%}"
        assert confidence_rate >= 0.8, f"High confidence rate too low: {confidence_rate:.2%}"
    
    def test_datetime_format_detection_accuracy(self):
        """测试日期时间格式检测准确率"""
        test_formats = [
            (["2023-01-01", "2023-02-15"], "%Y-%m-%d"),
            (["01/01/2023", "02/15/2023"], "%m/%d/%Y"),
            (["2023-01-01T12:00:00", "2023-02-15T15:30:00"], "%Y-%m-%dT%H:%M:%S"),
            ([1640995200, 1641081600], "timestamp_seconds"),
            ([1640995200000, 1641081600000], "timestamp_milliseconds")
        ]
        
        correct_detections = 0
        
        for values, expected_format in test_formats:
            if isinstance(values[0], int):
                # 时间戳检测
                result = DateTimeParser.detect_timestamp(values[0])
                if result and result.detected_format == expected_format:
                    correct_detections += 1
            else:
                # 字符串格式检测
                result = DateTimeParser.infer_datetime_format(values)
                if result and result.detected_format == expected_format:
                    correct_detections += 1
        
        accuracy = correct_detections / len(test_formats)
        assert accuracy >= 0.8, f"DateTime detection accuracy too low: {accuracy:.2%}"


# 集成测试
class TestSchemaInferencerIntegration:
    """智能推断系统集成测试"""
    
    @pytest.mark.asyncio
    async def test_file_connector_integration(self):
        """测试与文件连接器的集成"""
        # 创建临时CSV文件
        test_data = """id,name,age,salary,active,join_date
1,Alice,25,50000.5,true,2023-01-01
2,Bob,30,60000.0,false,2023-02-15
3,Charlie,35,70000.75,true,2023-03-10
4,Diana,28,55000.0,true,2023-04-05
5,Eve,32,65000.25,false,2023-05-20"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(test_data)
            temp_file = f.name
        
        try:
            # 创建文件连接器（模拟）
            from connectors.file_connector import FileConnector
            
            connector = FileConnector(
                source_id="test_csv",
                source_type=DataSourceType.CSV,
                file_path=temp_file
            )
            
            # 连接并获取增强schema
            await connector.connect()
            schema = await connector.get_schema_with_inference()
            
            # 验证推断结果
            assert 'columns' in schema
            assert 'quality_metrics' in schema
            assert 'inference_metadata' in schema
            
            columns = schema['columns']
            assert columns['id']['detected_type'] == 'integer'
            assert columns['name']['detected_type'] in ['string', 'categorical']
            assert columns['age']['detected_type'] == 'integer'
            assert columns['salary']['detected_type'] == 'float'
            assert columns['active']['detected_type'] == 'boolean'
            assert columns['join_date']['detected_type'] == 'date'
            
            # 验证数据质量
            quality_score = schema['quality_metrics']['data_quality_score']
            assert quality_score > 80
            
            # 测试数据验证
            validation_report = await connector.validate_data()
            assert 'overall_quality_score' in validation_report
            assert validation_report['total_rows'] == 5
            
            # 测试转换建议
            suggestions = await connector.get_type_conversion_suggestions()
            assert 'suggestions' in suggestions
            
        finally:
            import os
            os.unlink(temp_file)


if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v", "--tb=short"])