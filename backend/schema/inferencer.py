"""
智能类型推断器 - SchemaInferencer 核心类
提供高准确率的数据类型推断和结构分析功能
"""
import re
import math
import json
import time
import logging
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional, Union, Tuple, Set
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from enum import Enum

import polars as pl
from core.memory_guard import memory_guard
from core.config import config


class InferenceConfidence(Enum):
    """推断置信度等级"""
    VERY_LOW = "very_low"      # < 50%
    LOW = "low"                # 50-70%
    MEDIUM = "medium"          # 70-85%
    HIGH = "high"              # 85-95%
    VERY_HIGH = "very_high"    # > 95%


class DataTypeCategory(Enum):
    """数据类型分类"""
    NUMERIC = "numeric"        # 数字类型
    TEXT = "text"             # 文本类型
    TEMPORAL = "temporal"     # 时间类型
    BOOLEAN = "boolean"       # 布尔类型
    COMPLEX = "complex"       # 复杂类型 (JSON, Array)
    NULL = "null"             # 空值类型


class DetectedDataType(Enum):
    """检测到的数据类型"""
    # 数字类型
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    
    # 文本类型
    STRING = "string"
    CATEGORICAL = "categorical"
    
    # 时间类型
    DATE = "date"
    DATETIME = "datetime" 
    TIME = "time"
    TIMESTAMP = "timestamp"
    
    # 布尔类型
    BOOLEAN = "boolean"
    
    # 复杂类型
    JSON_OBJECT = "json_object"
    JSON_ARRAY = "json_array"
    LIST = "list"
    
    # 空值
    NULL = "null"
    MIXED = "mixed"           # 混合类型


@dataclass
class TypeInferenceResult:
    """类型推断结果"""
    detected_type: DetectedDataType
    confidence: InferenceConfidence
    category: DataTypeCategory
    sample_values: List[Any] = field(default_factory=list)
    null_count: int = 0
    total_count: int = 0
    null_percentage: float = 0.0
    unique_count: int = 0
    unique_percentage: float = 0.0
    
    # 类型特定的元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 推断过程中的统计信息
    statistics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DateTimeInferenceResult:
    """时间类型推断结果"""
    detected_format: str
    confidence: float
    sample_parsed_values: List[datetime] = field(default_factory=list)
    timezone_info: Optional[str] = None
    is_timestamp: bool = False
    timestamp_unit: Optional[str] = None  # 'seconds', 'milliseconds', 'microseconds'


class NullHandler:
    """空值处理策略类"""
    
    # 常见的空值表示
    NULL_REPRESENTATIONS = {
        # 标准空值
        'null', 'none', 'nil', 'nan', 'na', 'n/a',
        # 大写变体
        'NULL', 'NONE', 'NIL', 'NAN', 'NA', 'N/A',
        # 空字符串和空白
        '', ' ', '\t', '\n', '\r', '\r\n',
        # 特殊标记
        '-', '?', 'unknown', 'UNKNOWN', 'missing', 'MISSING',
        # 数字表示
        'inf', '-inf', 'infinity', '-infinity', 'INF', '-INF'
    }
    
    @classmethod
    def is_null_value(cls, value: Any) -> bool:
        """判断值是否为空值"""
        if value is None:
            return True
        
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return True
        
        if isinstance(value, str):
            # 去除前后空白后判断
            cleaned = value.strip()
            return cleaned in cls.NULL_REPRESENTATIONS
        
        return False
    
    @classmethod
    def get_null_statistics(cls, values: List[Any]) -> Dict[str, Any]:
        """获取空值统计信息"""
        total_count = len(values)
        null_count = sum(1 for v in values if cls.is_null_value(v))
        
        # 统计不同空值表示的分布
        null_representations = Counter()
        for v in values:
            if cls.is_null_value(v):
                if v is None:
                    null_representations['None'] += 1
                elif isinstance(v, float) and math.isnan(v):
                    null_representations['NaN'] += 1
                elif isinstance(v, float) and math.isinf(v):
                    null_representations['Infinity'] += 1
                else:
                    null_representations[str(v)] += 1
        
        return {
            'total_count': total_count,
            'null_count': null_count,
            'null_percentage': (null_count / total_count * 100) if total_count > 0 else 0.0,
            'null_representations': dict(null_representations),
            'has_nulls': null_count > 0
        }


class DateTimeParser:
    """时间格式识别和解析器"""
    
    # 常见日期时间格式（按优先级排序）
    DATETIME_FORMATS = [
        # ISO 8601 标准格式
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ', 
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        
        # 常见日期格式
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%m-%d-%Y',
        '%d-%m-%Y',
        
        # 时间格式
        '%H:%M:%S',
        '%H:%M:%S.%f',
        '%H:%M',
        
        # 其他常见格式
        '%Y%m%d',
        '%Y%m%d%H%M%S',
        '%d.%m.%Y',
        '%m.%d.%Y',
        '%Y.%m.%d',
        
        # 带文字的格式
        '%B %d, %Y',
        '%b %d, %Y',
        '%d %B %Y',
        '%d %b %Y',
    ]
    
    # 时间戳范围检查（合理的时间戳范围）
    MIN_TIMESTAMP_SECONDS = 0           # 1970-01-01
    MAX_TIMESTAMP_SECONDS = 4102444800  # 2100-01-01
    MIN_TIMESTAMP_MILLISECONDS = MIN_TIMESTAMP_SECONDS * 1000
    MAX_TIMESTAMP_MILLISECONDS = MAX_TIMESTAMP_SECONDS * 1000
    MIN_TIMESTAMP_MICROSECONDS = MIN_TIMESTAMP_SECONDS * 1000000
    MAX_TIMESTAMP_MICROSECONDS = MAX_TIMESTAMP_SECONDS * 1000000
    
    @classmethod
    def parse_datetime(cls, value: str, format_str: str) -> Optional[datetime]:
        """尝试解析单个时间值"""
        try:
            return datetime.strptime(str(value).strip(), format_str)
        except (ValueError, TypeError):
            return None
    
    @classmethod
    def detect_timestamp(cls, value: Union[int, float, str]) -> Optional[DateTimeInferenceResult]:
        """检测时间戳格式"""
        try:
            if isinstance(value, str):
                if not value.replace('.', '').replace('-', '').isdigit():
                    return None
                num_value = float(value)
            else:
                num_value = float(value)
            
            # 检测时间戳精度
            if cls.MIN_TIMESTAMP_SECONDS <= num_value <= cls.MAX_TIMESTAMP_SECONDS:
                # 秒级时间戳
                dt = datetime.fromtimestamp(num_value)
                return DateTimeInferenceResult(
                    detected_format="timestamp_seconds",
                    confidence=0.9,
                    sample_parsed_values=[dt],
                    is_timestamp=True,
                    timestamp_unit="seconds"
                )
            elif cls.MIN_TIMESTAMP_MILLISECONDS <= num_value <= cls.MAX_TIMESTAMP_MILLISECONDS:
                # 毫秒级时间戳
                dt = datetime.fromtimestamp(num_value / 1000)
                return DateTimeInferenceResult(
                    detected_format="timestamp_milliseconds",
                    confidence=0.9,
                    sample_parsed_values=[dt],
                    is_timestamp=True,
                    timestamp_unit="milliseconds"
                )
            elif cls.MIN_TIMESTAMP_MICROSECONDS <= num_value <= cls.MAX_TIMESTAMP_MICROSECONDS:
                # 微秒级时间戳
                dt = datetime.fromtimestamp(num_value / 1000000)
                return DateTimeInferenceResult(
                    detected_format="timestamp_microseconds",
                    confidence=0.8,
                    sample_parsed_values=[dt],
                    is_timestamp=True,
                    timestamp_unit="microseconds"
                )
                    
        except (ValueError, OverflowError, OSError):
            pass
        
        return None
    
    @classmethod
    def infer_datetime_format(cls, values: List[Any], sample_size: int = 100) -> Optional[DateTimeInferenceResult]:
        """推断时间格式"""
        if not values:
            return None
        
        # 过滤掉空值
        non_null_values = [v for v in values if not NullHandler.is_null_value(v)]
        if not non_null_values:
            return None
        
        # 采样处理
        sample_values = non_null_values[:sample_size] if len(non_null_values) > sample_size else non_null_values
        
        # 首先尝试时间戳检测
        timestamp_results = []
        for value in sample_values[:10]:  # 只检测前10个值
            timestamp_result = cls.detect_timestamp(value)
            if timestamp_result:
                timestamp_results.append(timestamp_result)
        
        if len(timestamp_results) >= len(sample_values[:10]) * 0.8:  # 80%以上成功识别为时间戳
            # 合并时间戳结果
            unit_counter = Counter(r.timestamp_unit for r in timestamp_results)
            most_common_unit = unit_counter.most_common(1)[0][0]
            
            all_parsed = []
            for result in timestamp_results:
                all_parsed.extend(result.sample_parsed_values)
            
            return DateTimeInferenceResult(
                detected_format=f"timestamp_{most_common_unit}",
                confidence=0.9,
                sample_parsed_values=all_parsed[:5],
                is_timestamp=True,
                timestamp_unit=most_common_unit
            )
        
        # 尝试字符串格式检测
        format_scores = defaultdict(int)
        format_parsed_values = defaultdict(list)
        
        for format_str in cls.DATETIME_FORMATS:
            for value in sample_values:
                parsed = cls.parse_datetime(str(value), format_str)
                if parsed:
                    format_scores[format_str] += 1
                    if len(format_parsed_values[format_str]) < 5:
                        format_parsed_values[format_str].append(parsed)
        
        if not format_scores:
            return None
        
        # 找到最匹配的格式
        best_format = max(format_scores.items(), key=lambda x: x[1])
        format_str, success_count = best_format
        
        confidence = success_count / len(sample_values)
        if confidence < 0.5:  # 成功率低于50%不认为是时间格式
            return None
        
        return DateTimeInferenceResult(
            detected_format=format_str,
            confidence=confidence,
            sample_parsed_values=format_parsed_values[format_str],
            is_timestamp=False
        )


class TypeDetector:
    """数据类型推断引擎"""
    
    def __init__(self, sample_size: int = 1000, confidence_threshold: float = 0.7):
        self.sample_size = sample_size
        self.confidence_threshold = confidence_threshold
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def detect_type(self, values: List[Any], column_name: str = "") -> TypeInferenceResult:
        """检测数据类型"""
        if not values:
            return self._create_null_result(0)
        
        # 获取空值统计
        null_stats = NullHandler.get_null_statistics(values)
        non_null_values = [v for v in values if not NullHandler.is_null_value(v)]
        
        if not non_null_values:
            return self._create_null_result(len(values))
        
        # 采样处理
        sample_values = self._get_sample_values(non_null_values)
        
        # 获取基本统计信息
        unique_values = list(set(str(v) for v in sample_values))
        unique_count = len(unique_values)
        unique_percentage = (unique_count / len(sample_values)) * 100 if sample_values else 0
        
        # 按优先级进行类型检测
        detection_results = [
            self._detect_boolean(sample_values),
            self._detect_numeric(sample_values),
            self._detect_datetime(sample_values),
            self._detect_json(sample_values),
            self._detect_categorical_or_string(sample_values, unique_percentage)
        ]
        
        # 选择置信度最高的结果
        best_result = max(detection_results, key=lambda r: self._confidence_to_score(r.confidence))
        
        # 填充统计信息
        best_result.null_count = null_stats['null_count']
        best_result.total_count = len(values)
        best_result.null_percentage = null_stats['null_percentage']
        best_result.unique_count = unique_count
        best_result.unique_percentage = unique_percentage
        best_result.sample_values = sample_values[:5]  # 只保留5个样本值
        
        # 添加详细统计
        best_result.statistics = {
            'sample_size': len(sample_values),
            'null_stats': null_stats,
            'column_name': column_name,
            'detection_timestamp': time.time()
        }
        
        return best_result
    
    def _get_sample_values(self, values: List[Any]) -> List[Any]:
        """获取采样值"""
        if len(values) <= self.sample_size:
            return values[:]
        
        # 使用系统采样确保代表性
        step = len(values) // self.sample_size
        return [values[i] for i in range(0, len(values), step)][:self.sample_size]
    
    def _detect_boolean(self, values: List[Any]) -> TypeInferenceResult:
        """检测布尔类型"""
        boolean_values = set()
        valid_count = 0
        
        # 常见的布尔值表示
        TRUE_VALUES = {'true', '1', 'yes', 'y', 'on', 't', 'True', 'TRUE', 'YES', 'Y', 'ON', 'T'}
        FALSE_VALUES = {'false', '0', 'no', 'n', 'off', 'f', 'False', 'FALSE', 'NO', 'N', 'OFF', 'F'}
        
        for value in values:
            str_value = str(value).strip()
            if str_value in TRUE_VALUES or str_value in FALSE_VALUES:
                boolean_values.add(str_value)
                valid_count += 1
            elif isinstance(value, bool):
                valid_count += 1
        
        confidence_score = valid_count / len(values) if values else 0
        
        # 布尔类型要求高置信度
        if confidence_score >= 0.9 and len(boolean_values) <= 10:  # 最多10种不同的布尔表示
            confidence = InferenceConfidence.VERY_HIGH if confidence_score >= 0.95 else InferenceConfidence.HIGH
            
            return TypeInferenceResult(
                detected_type=DetectedDataType.BOOLEAN,
                confidence=confidence,
                category=DataTypeCategory.BOOLEAN,
                metadata={
                    'boolean_representations': list(boolean_values),
                    'true_values': [v for v in boolean_values if v in TRUE_VALUES],
                    'false_values': [v for v in boolean_values if v in FALSE_VALUES]
                }
            )
        
        return TypeInferenceResult(
            detected_type=DetectedDataType.STRING,
            confidence=InferenceConfidence.VERY_LOW,
            category=DataTypeCategory.TEXT
        )
    
    def _detect_numeric(self, values: List[Any]) -> TypeInferenceResult:
        """检测数字类型"""
        integer_count = 0
        float_count = 0
        decimal_count = 0
        valid_numeric_count = 0
        
        numeric_values = []
        has_decimals = False
        max_decimal_places = 0
        
        for value in values:
            # 尝试转换为数字
            try:
                if isinstance(value, (int, float)):
                    numeric_values.append(value)
                    valid_numeric_count += 1
                    if isinstance(value, float) and not value.is_integer():
                        float_count += 1
                        has_decimals = True
                    else:
                        integer_count += 1
                    continue
                
                str_value = str(value).strip().replace(',', '')  # 去除千位分隔符
                
                # 尝试整数
                try:
                    int_val = int(str_value)
                    numeric_values.append(int_val)
                    integer_count += 1
                    valid_numeric_count += 1
                    continue
                except ValueError:
                    pass
                
                # 尝试浮点数
                try:
                    float_val = float(str_value)
                    if not math.isnan(float_val) and not math.isinf(float_val):
                        numeric_values.append(float_val)
                        float_count += 1
                        valid_numeric_count += 1
                        has_decimals = True
                        
                        # 计算小数位数
                        if '.' in str_value:
                            decimal_places = len(str_value.split('.')[1])
                            max_decimal_places = max(max_decimal_places, decimal_places)
                        continue
                except ValueError:
                    pass
                
                # 尝试Decimal（高精度）
                try:
                    decimal_val = Decimal(str_value)
                    numeric_values.append(decimal_val)
                    decimal_count += 1
                    valid_numeric_count += 1
                    has_decimals = True
                    
                    # 计算小数位数
                    if '.' in str_value:
                        decimal_places = len(str_value.split('.')[1])
                        max_decimal_places = max(max_decimal_places, decimal_places)
                except InvalidOperation:
                    pass
                    
            except Exception:
                continue
        
        confidence_score = valid_numeric_count / len(values) if values else 0
        
        if confidence_score < 0.5:  # 成功率低于50%不认为是数字类型
            return TypeInferenceResult(
                detected_type=DetectedDataType.STRING,
                confidence=InferenceConfidence.VERY_LOW,
                category=DataTypeCategory.TEXT
            )
        
        # 确定具体的数字类型
        if decimal_count > 0 and max_decimal_places > 2:  # 高精度小数
            detected_type = DetectedDataType.DECIMAL
        elif has_decimals or float_count > 0:
            detected_type = DetectedDataType.FLOAT
        else:
            detected_type = DetectedDataType.INTEGER
        
        confidence = self._score_to_confidence(confidence_score)
        
        # 计算数值统计
        if numeric_values:
            try:
                min_val = min(numeric_values)
                max_val = max(numeric_values)
                avg_val = sum(numeric_values) / len(numeric_values)
            except Exception:
                min_val = max_val = avg_val = None
        else:
            min_val = max_val = avg_val = None
        
        return TypeInferenceResult(
            detected_type=detected_type,
            confidence=confidence,
            category=DataTypeCategory.NUMERIC,
            metadata={
                'integer_count': integer_count,
                'float_count': float_count,
                'decimal_count': decimal_count,
                'has_decimals': has_decimals,
                'max_decimal_places': max_decimal_places,
                'min_value': min_val,
                'max_value': max_val,
                'average_value': avg_val,
                'range': (max_val - min_val) if (min_val is not None and max_val is not None) else None
            }
        )
    
    def _detect_datetime(self, values: List[Any]) -> TypeInferenceResult:
        """检测时间类型"""
        datetime_result = DateTimeParser.infer_datetime_format(values)
        
        if not datetime_result:
            return TypeInferenceResult(
                detected_type=DetectedDataType.STRING,
                confidence=InferenceConfidence.VERY_LOW,
                category=DataTypeCategory.TEXT
            )
        
        # 确定具体的时间类型
        if datetime_result.is_timestamp:
            detected_type = DetectedDataType.TIMESTAMP
        elif 'T' in datetime_result.detected_format or ' ' in datetime_result.detected_format:
            detected_type = DetectedDataType.DATETIME
        elif any(x in datetime_result.detected_format for x in ['%H', '%M', '%S']):
            if any(x in datetime_result.detected_format for x in ['%Y', '%m', '%d']):
                detected_type = DetectedDataType.DATETIME
            else:
                detected_type = DetectedDataType.TIME
        else:
            detected_type = DetectedDataType.DATE
        
        confidence = self._score_to_confidence(datetime_result.confidence)
        
        return TypeInferenceResult(
            detected_type=detected_type,
            confidence=confidence,
            category=DataTypeCategory.TEMPORAL,
            metadata={
                'detected_format': datetime_result.detected_format,
                'is_timestamp': datetime_result.is_timestamp,
                'timestamp_unit': datetime_result.timestamp_unit,
                'timezone_info': datetime_result.timezone_info,
                'sample_parsed_values': [str(dt) for dt in datetime_result.sample_parsed_values]
            }
        )
    
    def _detect_json(self, values: List[Any]) -> TypeInferenceResult:
        """检测JSON类型"""
        json_objects = 0
        json_arrays = 0
        valid_json_count = 0
        
        for value in values:
            try:
                str_value = str(value).strip()
                if not str_value:
                    continue
                
                parsed = json.loads(str_value)
                valid_json_count += 1
                
                if isinstance(parsed, dict):
                    json_objects += 1
                elif isinstance(parsed, list):
                    json_arrays += 1
                    
            except (json.JSONDecodeError, TypeError):
                continue
        
        confidence_score = valid_json_count / len(values) if values else 0
        
        if confidence_score < 0.8:  # JSON需要高置信度
            return TypeInferenceResult(
                detected_type=DetectedDataType.STRING,
                confidence=InferenceConfidence.VERY_LOW,
                category=DataTypeCategory.TEXT
            )
        
        # 确定JSON类型
        if json_objects > json_arrays:
            detected_type = DetectedDataType.JSON_OBJECT
        elif json_arrays > 0:
            detected_type = DetectedDataType.JSON_ARRAY
        else:
            detected_type = DetectedDataType.JSON_OBJECT  # 默认为对象
        
        confidence = self._score_to_confidence(confidence_score)
        
        return TypeInferenceResult(
            detected_type=detected_type,
            confidence=confidence,
            category=DataTypeCategory.COMPLEX,
            metadata={
                'json_objects': json_objects,
                'json_arrays': json_arrays,
                'valid_json_ratio': confidence_score
            }
        )
    
    def _detect_categorical_or_string(self, values: List[Any], unique_percentage: float) -> TypeInferenceResult:
        """检测分类或字符串类型"""
        # 基于唯一值比例判断是否为分类数据
        is_categorical = (
            unique_percentage < 10 or  # 唯一值比例小于10%
            (unique_percentage < 50 and len(set(str(v) for v in values)) <= 50)  # 或者唯一值少于50个且比例小于50%
        )
        
        if is_categorical:
            detected_type = DetectedDataType.CATEGORICAL
        else:
            detected_type = DetectedDataType.STRING
        
        # 分析文本特征
        avg_length = sum(len(str(v)) for v in values) / len(values) if values else 0
        max_length = max(len(str(v)) for v in values) if values else 0
        min_length = min(len(str(v)) for v in values) if values else 0
        
        return TypeInferenceResult(
            detected_type=detected_type,
            confidence=InferenceConfidence.HIGH,  # 文本类型作为默认兜底
            category=DataTypeCategory.TEXT,
            metadata={
                'is_categorical': is_categorical,
                'unique_percentage': unique_percentage,
                'avg_length': avg_length,
                'max_length': max_length,
                'min_length': min_length,
                'unique_values': list(set(str(v) for v in values))[:20]  # 最多保存20个唯一值样本
            }
        )
    
    def _create_null_result(self, total_count: int) -> TypeInferenceResult:
        """创建空值类型结果"""
        return TypeInferenceResult(
            detected_type=DetectedDataType.NULL,
            confidence=InferenceConfidence.VERY_HIGH,
            category=DataTypeCategory.NULL,
            null_count=total_count,
            total_count=total_count,
            null_percentage=100.0,
            unique_count=0,
            unique_percentage=0.0
        )
    
    def _confidence_to_score(self, confidence: InferenceConfidence) -> float:
        """将置信度枚举转换为数值分数"""
        confidence_scores = {
            InferenceConfidence.VERY_LOW: 0.25,
            InferenceConfidence.LOW: 0.6,
            InferenceConfidence.MEDIUM: 0.77,
            InferenceConfidence.HIGH: 0.9,
            InferenceConfidence.VERY_HIGH: 0.98
        }
        return confidence_scores.get(confidence, 0.5)
    
    def _score_to_confidence(self, score: float) -> InferenceConfidence:
        """将数值分数转换为置信度枚举"""
        if score >= 0.95:
            return InferenceConfidence.VERY_HIGH
        elif score >= 0.85:
            return InferenceConfidence.HIGH
        elif score >= 0.7:
            return InferenceConfidence.MEDIUM
        elif score >= 0.5:
            return InferenceConfidence.LOW
        else:
            return InferenceConfidence.VERY_LOW


class SchemaInferencer:
    """智能结构推断器 - 核心类"""
    
    def __init__(self, sample_size: int = 1000, confidence_threshold: float = 0.7):
        self.sample_size = sample_size
        self.confidence_threshold = confidence_threshold
        self.type_detector = TypeDetector(sample_size, confidence_threshold)
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def infer_schema(self, df: pl.DataFrame, source_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """推断DataFrame的完整schema"""
        start_time = time.time()
        
        with memory_guard.memory_guard("schema_inference", estimated_bytes=len(df) * 100):
            # 基本信息
            schema = {
                'row_count': len(df),
                'column_count': len(df.columns),
                'columns': {},
                'inference_metadata': {
                    'inference_timestamp': start_time,
                    'sample_size': self.sample_size,
                    'confidence_threshold': self.confidence_threshold,
                    'source_info': source_info or {}
                }
            }
            
            # 对每列进行类型推断
            for column_name in df.columns:
                try:
                    column_values = df[column_name].to_list()
                    inference_result = self.type_detector.detect_type(column_values, column_name)
                    
                    schema['columns'][column_name] = {
                        'name': column_name,
                        'detected_type': inference_result.detected_type.value,
                        'category': inference_result.category.value,
                        'confidence': inference_result.confidence.value,
                        'nullable': inference_result.null_count > 0,
                        'null_count': inference_result.null_count,
                        'null_percentage': inference_result.null_percentage,
                        'unique_count': inference_result.unique_count,
                        'unique_percentage': inference_result.unique_percentage,
                        'sample_values': [str(v) for v in inference_result.sample_values],
                        'metadata': inference_result.metadata,
                        'statistics': inference_result.statistics
                    }
                    
                except Exception as e:
                    self._logger.error(f"Failed to infer type for column {column_name}: {e}")
                    # 设置默认值
                    schema['columns'][column_name] = {
                        'name': column_name,
                        'detected_type': DetectedDataType.STRING.value,
                        'category': DataTypeCategory.TEXT.value,
                        'confidence': InferenceConfidence.VERY_LOW.value,
                        'nullable': True,
                        'error': str(e)
                    }
            
            # 计算整体质量指标
            schema['quality_metrics'] = self._calculate_quality_metrics(schema['columns'])
            
            # 记录推断耗时
            inference_duration = time.time() - start_time
            schema['inference_metadata']['duration_seconds'] = inference_duration
            
            self._logger.info(
                f"Schema inference completed for {len(df.columns)} columns in {inference_duration:.2f}s"
            )
            
            return schema
    
    def _calculate_quality_metrics(self, columns: Dict[str, Any]) -> Dict[str, Any]:
        """计算数据质量指标"""
        if not columns:
            return {}
        
        # 统计置信度分布
        confidence_counts = Counter(col.get('confidence', 'unknown') for col in columns.values())
        
        # 统计类型分布
        type_counts = Counter(col.get('detected_type', 'unknown') for col in columns.values())
        
        # 计算整体空值比例
        total_null_percentage = sum(col.get('null_percentage', 0) for col in columns.values()) / len(columns)
        
        # 计算高置信度列的比例
        high_confidence_count = sum(
            1 for col in columns.values() 
            if col.get('confidence') in ['high', 'very_high']
        )
        high_confidence_ratio = high_confidence_count / len(columns)
        
        return {
            'total_columns': len(columns),
            'high_confidence_ratio': high_confidence_ratio,
            'average_null_percentage': total_null_percentage,
            'confidence_distribution': dict(confidence_counts),
            'type_distribution': dict(type_counts),
            'data_quality_score': self._calculate_quality_score(
                high_confidence_ratio, 
                total_null_percentage, 
                columns
            )
        }
    
    def _calculate_quality_score(
        self, 
        high_confidence_ratio: float, 
        avg_null_percentage: float, 
        columns: Dict[str, Any]
    ) -> float:
        """计算数据质量综合评分 (0-100)"""
        # 置信度得分 (40%权重)
        confidence_score = high_confidence_ratio * 40
        
        # 完整性得分 (30%权重) - 空值越少得分越高
        completeness_score = max(0, (100 - avg_null_percentage)) * 0.3
        
        # 多样性得分 (20%权重) - 类型多样性
        type_diversity = len(set(col.get('category', 'unknown') for col in columns.values()))
        diversity_score = min(type_diversity * 5, 20)  # 最多20分
        
        # 一致性得分 (10%权重) - 无错误列的比例
        error_count = sum(1 for col in columns.values() if 'error' in col)
        consistency_score = max(0, (len(columns) - error_count) / len(columns)) * 10
        
        total_score = confidence_score + completeness_score + diversity_score + consistency_score
        return round(min(total_score, 100), 2)
    
    def get_type_conversion_suggestions(self, schema: Dict[str, Any]) -> Dict[str, List[str]]:
        """获取类型转换建议"""
        suggestions = {}
        
        for column_name, column_info in schema.get('columns', {}).items():
            column_suggestions = []
            detected_type = column_info.get('detected_type')
            confidence = column_info.get('confidence')
            metadata = column_info.get('metadata', {})
            
            # 低置信度的转换建议
            if confidence in ['very_low', 'low']:
                column_suggestions.append(f"建议手动验证类型推断结果 (当前置信度: {confidence})")
            
            # 数字类型建议
            if detected_type == 'integer' and metadata.get('max_value', 0) > 2147483647:
                column_suggestions.append("建议使用BigInt类型存储大整数")
            
            # 分类数据建议
            if detected_type == 'categorical':
                unique_count = metadata.get('unique_values', [])
                if len(unique_count) < 10:
                    column_suggestions.append(f"检测到分类数据，建议使用枚举类型 ({len(unique_count)}个值)")
            
            # 时间类型建议
            if detected_type in ['timestamp', 'datetime', 'date']:
                format_info = metadata.get('detected_format')
                if format_info:
                    column_suggestions.append(f"建议使用统一时间格式: {format_info}")
            
            # JSON类型建议
            if detected_type in ['json_object', 'json_array']:
                column_suggestions.append("建议考虑拆分JSON为独立列以提高查询性能")
            
            # 空值处理建议
            null_percentage = column_info.get('null_percentage', 0)
            if null_percentage > 50:
                column_suggestions.append(f"该列空值比例过高 ({null_percentage:.1f}%)，建议检查数据质量")
            elif null_percentage > 0:
                column_suggestions.append(f"该列存在 {null_percentage:.1f}% 空值，建议设置默认值策略")
            
            if column_suggestions:
                suggestions[column_name] = column_suggestions
        
        return suggestions