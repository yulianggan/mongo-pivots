"""
类型转换器 - 安全的数据类型转换和格式化
提供高效、安全的类型转换，支持精度保持和错误处理
"""
import re
import json
import math
from datetime import datetime, date, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Any, List, Optional, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

import polars as pl
from schema.inferencer import DetectedDataType, DateTimeParser, NullHandler


class ConversionStrategy(Enum):
    """转换策略"""
    STRICT = "strict"           # 严格模式，转换失败时抛出异常
    COERCIVE = "coercive"      # 强制转换，尽力转换，失败时使用默认值
    BEST_EFFORT = "best_effort" # 尽力而为，失败时保留原值


class ConversionMode(Enum):
    """转换模式"""
    SAFE = "safe"              # 安全模式，保证数据完整性
    LOSSY = "lossy"            # 有损模式，允许精度损失
    PRESERVE = "preserve"      # 保持模式，尽量保持原始精度


@dataclass
class ConversionResult:
    """转换结果"""
    success: bool
    converted_value: Any
    original_value: Any
    target_type: str
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    precision_lost: bool = False
    
    def __post_init__(self):
        if not self.success and self.converted_value is None:
            self.converted_value = self.original_value


@dataclass
class BatchConversionResult:
    """批量转换结果"""
    success_count: int = 0
    failure_count: int = 0
    warning_count: int = 0
    converted_values: List[Any] = field(default_factory=list)
    failed_indices: List[int] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def total_count(self) -> int:
        return self.success_count + self.failure_count
    
    @property
    def success_rate(self) -> float:
        return (self.success_count / self.total_count) if self.total_count > 0 else 0.0


class NumericConverter:
    """数值类型转换器"""
    
    @staticmethod
    def to_integer(
        value: Any, 
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE
    ) -> ConversionResult:
        """转换为整数"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "integer")
        
        try:
            if isinstance(value, bool):
                return ConversionResult(True, int(value), value, "integer")
            
            if isinstance(value, int):
                return ConversionResult(True, value, value, "integer")
            
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    if strategy == ConversionStrategy.STRICT:
                        return ConversionResult(
                            False, None, value, "integer",
                            error_message="无法将NaN或Infinity转换为整数"
                        )
                    else:
                        return ConversionResult(True, 0, value, "integer", 
                                               warning_message="NaN/Infinity转换为0")
                
                # 检查是否会丢失精度
                int_value = int(value)
                precision_lost = abs(value - int_value) > 1e-10
                
                if precision_lost and strategy == ConversionStrategy.STRICT:
                    return ConversionResult(
                        False, None, value, "integer",
                        error_message=f"转换会丢失小数部分: {value - int_value}"
                    )
                
                return ConversionResult(
                    True, int_value, value, "integer",
                    warning_message="丢失小数部分" if precision_lost else None,
                    precision_lost=precision_lost
                )
            
            if isinstance(value, Decimal):
                int_value = int(value)
                precision_lost = value != Decimal(int_value)
                
                return ConversionResult(
                    True, int_value, value, "integer",
                    warning_message="丢失小数部分" if precision_lost else None,
                    precision_lost=precision_lost
                )
            
            # 字符串转换
            str_value = str(value).strip().replace(',', '')  # 移除千位分隔符
            
            # 尝试直接转换
            try:
                return ConversionResult(True, int(str_value), value, "integer")
            except ValueError:
                pass
            
            # 尝试先转换为浮点数再转换为整数
            try:
                float_value = float(str_value)
                int_value = int(float_value)
                precision_lost = abs(float_value - int_value) > 1e-10
                
                if precision_lost and strategy == ConversionStrategy.STRICT:
                    return ConversionResult(
                        False, None, value, "integer",
                        error_message=f"转换会丢失小数部分: {float_value - int_value}"
                    )
                
                return ConversionResult(
                    True, int_value, value, "integer",
                    warning_message="丢失小数部分" if precision_lost else None,
                    precision_lost=precision_lost
                )
            except ValueError:
                pass
            
            # 尝试处理特殊格式（如科学计数法）
            try:
                # 移除所有非数字字符（除了小数点、负号、科学计数法）
                cleaned = re.sub(r'[^\d\.\-+eE]', '', str_value)
                if cleaned:
                    float_value = float(cleaned)
                    int_value = int(float_value)
                    return ConversionResult(
                        True, int_value, value, "integer",
                        warning_message="已清理非数字字符并转换"
                    )
            except (ValueError, OverflowError):
                pass
            
            # 转换失败
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "integer",
                    error_message=f"无法将 '{value}' 转换为整数"
                )
            else:
                return ConversionResult(
                    True, 0, value, "integer",
                    warning_message=f"转换失败，使用默认值0"
                )
                
        except Exception as e:
            return ConversionResult(
                False, None, value, "integer",
                error_message=f"转换异常: {str(e)}"
            )
    
    @staticmethod
    def to_float(
        value: Any, 
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        precision: Optional[int] = None
    ) -> ConversionResult:
        """转换为浮点数"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "float")
        
        try:
            if isinstance(value, bool):
                return ConversionResult(True, float(value), value, "float")
            
            if isinstance(value, (int, float)):
                float_value = float(value)
                if precision is not None:
                    float_value = round(float_value, precision)
                return ConversionResult(True, float_value, value, "float")
            
            if isinstance(value, Decimal):
                float_value = float(value)
                if precision is not None:
                    float_value = round(float_value, precision)
                return ConversionResult(True, float_value, value, "float")
            
            # 字符串转换
            str_value = str(value).strip().replace(',', '')
            
            try:
                float_value = float(str_value)
                if math.isnan(float_value) or math.isinf(float_value):
                    if strategy == ConversionStrategy.STRICT:
                        return ConversionResult(
                            False, None, value, "float",
                            error_message="结果为NaN或Infinity"
                        )
                
                if precision is not None:
                    float_value = round(float_value, precision)
                
                return ConversionResult(True, float_value, value, "float")
            except ValueError:
                pass
            
            # 尝试清理和重新转换
            try:
                cleaned = re.sub(r'[^\d\.\-+eE]', '', str_value)
                if cleaned:
                    float_value = float(cleaned)
                    if precision is not None:
                        float_value = round(float_value, precision)
                    return ConversionResult(
                        True, float_value, value, "float",
                        warning_message="已清理非数字字符并转换"
                    )
            except (ValueError, OverflowError):
                pass
            
            # 转换失败
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "float",
                    error_message=f"无法将 '{value}' 转换为浮点数"
                )
            else:
                return ConversionResult(
                    True, 0.0, value, "float",
                    warning_message="转换失败，使用默认值0.0"
                )
                
        except Exception as e:
            return ConversionResult(
                False, None, value, "float",
                error_message=f"转换异常: {str(e)}"
            )
    
    @staticmethod
    def to_decimal(
        value: Any,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        precision: int = 28,
        scale: int = 10
    ) -> ConversionResult:
        """转换为高精度Decimal"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "decimal")
        
        try:
            if isinstance(value, Decimal):
                # 调整精度和标度
                decimal_value = value.quantize(
                    Decimal('0.' + '0' * scale), 
                    rounding=ROUND_HALF_UP
                )
                return ConversionResult(True, decimal_value, value, "decimal")
            
            if isinstance(value, bool):
                return ConversionResult(True, Decimal(int(value)), value, "decimal")
            
            if isinstance(value, (int, float)):
                try:
                    decimal_value = Decimal(str(value)).quantize(
                        Decimal('0.' + '0' * scale),
                        rounding=ROUND_HALF_UP
                    )
                    return ConversionResult(True, decimal_value, value, "decimal")
                except InvalidOperation:
                    if strategy == ConversionStrategy.STRICT:
                        return ConversionResult(
                            False, None, value, "decimal",
                            error_message=f"无法精确表示为Decimal: {value}"
                        )
                    return ConversionResult(
                        True, Decimal('0'), value, "decimal",
                        warning_message="转换失败，使用默认值0"
                    )
            
            # 字符串转换
            str_value = str(value).strip().replace(',', '')
            
            try:
                decimal_value = Decimal(str_value).quantize(
                    Decimal('0.' + '0' * scale),
                    rounding=ROUND_HALF_UP
                )
                return ConversionResult(True, decimal_value, value, "decimal")
            except InvalidOperation:
                pass
            
            # 尝试清理后转换
            try:
                cleaned = re.sub(r'[^\d\.\-+eE]', '', str_value)
                if cleaned:
                    decimal_value = Decimal(cleaned).quantize(
                        Decimal('0.' + '0' * scale),
                        rounding=ROUND_HALF_UP
                    )
                    return ConversionResult(
                        True, decimal_value, value, "decimal",
                        warning_message="已清理非数字字符并转换"
                    )
            except InvalidOperation:
                pass
            
            # 转换失败
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "decimal",
                    error_message=f"无法将 '{value}' 转换为Decimal"
                )
            else:
                return ConversionResult(
                    True, Decimal('0'), value, "decimal",
                    warning_message="转换失败，使用默认值0"
                )
                
        except Exception as e:
            return ConversionResult(
                False, None, value, "decimal",
                error_message=f"转换异常: {str(e)}"
            )


class TextConverter:
    """文本类型转换器"""
    
    @staticmethod
    def to_string(
        value: Any,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        encoding: str = 'utf-8',
        max_length: Optional[int] = None
    ) -> ConversionResult:
        """转换为字符串"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "string")
        
        try:
            if isinstance(value, str):
                result_value = value
            elif isinstance(value, bytes):
                try:
                    result_value = value.decode(encoding)
                except UnicodeDecodeError as e:
                    if strategy == ConversionStrategy.STRICT:
                        return ConversionResult(
                            False, None, value, "string",
                            error_message=f"字节解码失败: {str(e)}"
                        )
                    else:
                        result_value = value.decode(encoding, errors='replace')
            else:
                result_value = str(value)
            
            # 长度限制
            if max_length and len(result_value) > max_length:
                if strategy == ConversionStrategy.STRICT:
                    return ConversionResult(
                        False, None, value, "string",
                        error_message=f"字符串长度 {len(result_value)} 超过限制 {max_length}"
                    )
                else:
                    result_value = result_value[:max_length]
                    return ConversionResult(
                        True, result_value, value, "string",
                        warning_message=f"字符串被截断到 {max_length} 字符",
                        precision_lost=True
                    )
            
            return ConversionResult(True, result_value, value, "string")
            
        except Exception as e:
            return ConversionResult(
                False, None, value, "string",
                error_message=f"转换异常: {str(e)}"
            )
    
    @staticmethod
    def to_categorical(
        value: Any,
        categories: List[str],
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        case_sensitive: bool = True
    ) -> ConversionResult:
        """转换为分类类型"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "categorical")
        
        try:
            str_value = str(value).strip()
            
            # 精确匹配
            if case_sensitive:
                if str_value in categories:
                    return ConversionResult(True, str_value, value, "categorical")
            else:
                # 不区分大小写匹配
                lower_categories = {cat.lower(): cat for cat in categories}
                lower_value = str_value.lower()
                if lower_value in lower_categories:
                    return ConversionResult(
                        True, lower_categories[lower_value], value, "categorical"
                    )
            
            # 模糊匹配（相似度）
            if strategy != ConversionStrategy.STRICT:
                best_match = None
                best_similarity = 0
                
                for category in categories:
                    # 简单的相似度计算（基于公共字符数）
                    common_chars = set(str_value.lower()) & set(category.lower())
                    similarity = len(common_chars) / max(len(str_value), len(category))
                    
                    if similarity > best_similarity and similarity > 0.6:  # 60%相似度阈值
                        best_similarity = similarity
                        best_match = category
                
                if best_match:
                    return ConversionResult(
                        True, best_match, value, "categorical",
                        warning_message=f"模糊匹配到 '{best_match}' (相似度: {best_similarity:.2f})"
                    )
            
            # 无法匹配
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "categorical",
                    error_message=f"'{str_value}' 不在允许的分类列表中"
                )
            else:
                # 使用第一个分类作为默认值，或保持原值
                default_value = categories[0] if categories else str_value
                return ConversionResult(
                    True, default_value, value, "categorical",
                    warning_message=f"无法匹配，使用默认值 '{default_value}'"
                )
                
        except Exception as e:
            return ConversionResult(
                False, None, value, "categorical",
                error_message=f"转换异常: {str(e)}"
            )


class TemporalConverter:
    """时间类型转换器"""
    
    @staticmethod
    def to_datetime(
        value: Any,
        format_hint: Optional[str] = None,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE
    ) -> ConversionResult:
        """转换为datetime"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "datetime")
        
        try:
            if isinstance(value, datetime):
                return ConversionResult(True, value, value, "datetime")
            
            if isinstance(value, date):
                dt_value = datetime.combine(value, time.min)
                return ConversionResult(True, dt_value, value, "datetime")
            
            if isinstance(value, (int, float)):
                # 尝试时间戳转换
                timestamp_result = DateTimeParser.detect_timestamp(value)
                if timestamp_result and timestamp_result.sample_parsed_values:
                    return ConversionResult(
                        True, timestamp_result.sample_parsed_values[0], value, "datetime"
                    )
            
            # 字符串转换
            str_value = str(value).strip()
            
            # 优先使用格式提示
            if format_hint:
                try:
                    dt_value = datetime.strptime(str_value, format_hint)
                    return ConversionResult(True, dt_value, value, "datetime")
                except ValueError:
                    if strategy == ConversionStrategy.STRICT:
                        return ConversionResult(
                            False, None, value, "datetime",
                            error_message=f"无法使用格式 '{format_hint}' 解析 '{str_value}'"
                        )
            
            # 使用DateTimeParser进行推断
            datetime_result = DateTimeParser.infer_datetime_format([value])
            if datetime_result and datetime_result.sample_parsed_values:
                return ConversionResult(
                    True, datetime_result.sample_parsed_values[0], value, "datetime"
                )
            
            # 尝试常见格式
            common_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%d',
                '%m/%d/%Y',
                '%d/%m/%Y',
                '%Y/%m/%d'
            ]
            
            for fmt in common_formats:
                try:
                    dt_value = datetime.strptime(str_value, fmt)
                    return ConversionResult(True, dt_value, value, "datetime")
                except ValueError:
                    continue
            
            # 转换失败
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "datetime",
                    error_message=f"无法解析日期时间格式: '{str_value}'"
                )
            else:
                # 使用当前时间作为默认值
                default_dt = datetime.now()
                return ConversionResult(
                    True, default_dt, value, "datetime",
                    warning_message=f"转换失败，使用当前时间"
                )
                
        except Exception as e:
            return ConversionResult(
                False, None, value, "datetime",
                error_message=f"转换异常: {str(e)}"
            )
    
    @staticmethod
    def to_date(
        value: Any,
        format_hint: Optional[str] = None,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE
    ) -> ConversionResult:
        """转换为date"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "date")
        
        # 先转换为datetime，然后提取日期部分
        dt_result = TemporalConverter.to_datetime(value, format_hint, strategy)
        
        if dt_result.success and dt_result.converted_value:
            try:
                date_value = dt_result.converted_value.date()
                return ConversionResult(
                    True, date_value, value, "date",
                    warning_message=dt_result.warning_message,
                    precision_lost=True  # 丢失时间部分
                )
            except AttributeError:
                pass
        
        return ConversionResult(
            dt_result.success, dt_result.converted_value, value, "date",
            error_message=dt_result.error_message,
            warning_message=dt_result.warning_message
        )


class BooleanConverter:
    """布尔类型转换器"""
    
    TRUE_VALUES = {'true', '1', 'yes', 'y', 'on', 't', 'True', 'TRUE', 'YES', 'Y', 'ON', 'T', 1, True}
    FALSE_VALUES = {'false', '0', 'no', 'n', 'off', 'f', 'False', 'FALSE', 'NO', 'N', 'OFF', 'F', 0, False}
    
    @staticmethod
    def to_boolean(
        value: Any,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        strict_mode: bool = False
    ) -> ConversionResult:
        """转换为布尔值"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "boolean")
        
        try:
            if isinstance(value, bool):
                return ConversionResult(True, value, value, "boolean")
            
            # 数字转换
            if isinstance(value, (int, float)):
                if value == 0:
                    return ConversionResult(True, False, value, "boolean")
                elif value == 1:
                    return ConversionResult(True, True, value, "boolean")
                elif not strict_mode:
                    # 非严格模式下，非零为True
                    return ConversionResult(
                        True, bool(value), value, "boolean",
                        warning_message=f"数值 {value} 转换为 {bool(value)}"
                    )
            
            # 字符串转换
            str_value = str(value).strip()
            
            if str_value in BooleanConverter.TRUE_VALUES:
                return ConversionResult(True, True, value, "boolean")
            
            if str_value in BooleanConverter.FALSE_VALUES:
                return ConversionResult(True, False, value, "boolean")
            
            # 尝试数字解析
            try:
                num_value = float(str_value)
                if num_value == 0:
                    return ConversionResult(True, False, value, "boolean")
                elif num_value == 1:
                    return ConversionResult(True, True, value, "boolean")
                elif not strict_mode:
                    return ConversionResult(
                        True, bool(num_value), value, "boolean",
                        warning_message=f"数值字符串 '{str_value}' 转换为 {bool(num_value)}"
                    )
            except ValueError:
                pass
            
            # 转换失败
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "boolean",
                    error_message=f"无法将 '{value}' 转换为布尔值"
                )
            else:
                # 默认为False
                return ConversionResult(
                    True, False, value, "boolean",
                    warning_message=f"转换失败，使用默认值False"
                )
                
        except Exception as e:
            return ConversionResult(
                False, None, value, "boolean",
                error_message=f"转换异常: {str(e)}"
            )


class ComplexConverter:
    """复杂类型转换器"""
    
    @staticmethod
    def to_json(
        value: Any,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        ensure_ascii: bool = False
    ) -> ConversionResult:
        """转换为JSON字符串"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "json")
        
        try:
            if isinstance(value, str):
                # 验证是否为有效JSON
                try:
                    json.loads(value)
                    return ConversionResult(True, value, value, "json")
                except json.JSONDecodeError:
                    if strategy == ConversionStrategy.STRICT:
                        return ConversionResult(
                            False, None, value, "json",
                            error_message=f"字符串不是有效的JSON格式"
                        )
            
            # 尝试序列化为JSON
            try:
                json_str = json.dumps(value, ensure_ascii=ensure_ascii, default=str)
                return ConversionResult(True, json_str, value, "json")
            except (TypeError, ValueError) as e:
                if strategy == ConversionStrategy.STRICT:
                    return ConversionResult(
                        False, None, value, "json",
                        error_message=f"无法序列化为JSON: {str(e)}"
                    )
                else:
                    # 转换为字符串形式的JSON
                    json_str = json.dumps(str(value), ensure_ascii=ensure_ascii)
                    return ConversionResult(
                        True, json_str, value, "json",
                        warning_message="对象无法直接序列化，已转换为字符串"
                    )
                    
        except Exception as e:
            return ConversionResult(
                False, None, value, "json",
                error_message=f"转换异常: {str(e)}"
            )
    
    @staticmethod
    def from_json(
        value: Any,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE
    ) -> ConversionResult:
        """从JSON字符串转换为Python对象"""
        if NullHandler.is_null_value(value):
            return ConversionResult(True, None, value, "object")
        
        try:
            if not isinstance(value, str):
                str_value = str(value)
            else:
                str_value = value
            
            # 解析JSON
            parsed_object = json.loads(str_value)
            return ConversionResult(True, parsed_object, value, "object")
            
        except json.JSONDecodeError as e:
            if strategy == ConversionStrategy.STRICT:
                return ConversionResult(
                    False, None, value, "object",
                    error_message=f"JSON解析失败: {str(e)}"
                )
            else:
                # 返回原字符串
                return ConversionResult(
                    True, str_value, value, "object",
                    warning_message="JSON解析失败，返回原字符串"
                )
        except Exception as e:
            return ConversionResult(
                False, None, value, "object",
                error_message=f"转换异常: {str(e)}"
            )


class TypeConverter:
    """类型转换器 - 主要转换器类"""
    
    def __init__(self):
        self.numeric_converter = NumericConverter()
        self.text_converter = TextConverter()
        self.temporal_converter = TemporalConverter()
        self.boolean_converter = BooleanConverter()
        self.complex_converter = ComplexConverter()
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def convert_value(
        self,
        value: Any,
        target_type: DetectedDataType,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        **kwargs
    ) -> ConversionResult:
        """转换单个值"""
        try:
            if target_type == DetectedDataType.INTEGER:
                return self.numeric_converter.to_integer(value, strategy)
            elif target_type == DetectedDataType.FLOAT:
                return self.numeric_converter.to_float(value, strategy, kwargs.get('precision'))
            elif target_type == DetectedDataType.DECIMAL:
                return self.numeric_converter.to_decimal(
                    value, strategy, 
                    kwargs.get('precision', 28),
                    kwargs.get('scale', 10)
                )
            elif target_type == DetectedDataType.STRING:
                return self.text_converter.to_string(
                    value, strategy,
                    kwargs.get('encoding', 'utf-8'),
                    kwargs.get('max_length')
                )
            elif target_type == DetectedDataType.CATEGORICAL:
                return self.text_converter.to_categorical(
                    value, 
                    kwargs.get('categories', []),
                    strategy,
                    kwargs.get('case_sensitive', True)
                )
            elif target_type == DetectedDataType.DATETIME:
                return self.temporal_converter.to_datetime(
                    value, kwargs.get('format_hint'), strategy
                )
            elif target_type == DetectedDataType.DATE:
                return self.temporal_converter.to_date(
                    value, kwargs.get('format_hint'), strategy
                )
            elif target_type == DetectedDataType.BOOLEAN:
                return self.boolean_converter.to_boolean(
                    value, strategy, kwargs.get('strict_mode', False)
                )
            elif target_type in [DetectedDataType.JSON_OBJECT, DetectedDataType.JSON_ARRAY]:
                return self.complex_converter.to_json(
                    value, strategy, kwargs.get('ensure_ascii', False)
                )
            else:
                # 默认转换为字符串
                return self.text_converter.to_string(value, strategy)
                
        except Exception as e:
            self._logger.error(f"Unexpected error in value conversion: {e}")
            return ConversionResult(
                False, None, value, target_type.value,
                error_message=f"转换器内部错误: {str(e)}"
            )
    
    def convert_batch(
        self,
        values: List[Any],
        target_type: DetectedDataType,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        **kwargs
    ) -> BatchConversionResult:
        """批量转换值"""
        result = BatchConversionResult()
        
        for i, value in enumerate(values):
            conversion_result = self.convert_value(value, target_type, strategy, **kwargs)
            
            result.converted_values.append(conversion_result.converted_value)
            
            if conversion_result.success:
                result.success_count += 1
                if conversion_result.warning_message:
                    result.warning_count += 1
                    result.warnings.append(f"行 {i}: {conversion_result.warning_message}")
            else:
                result.failure_count += 1
                result.failed_indices.append(i)
                if conversion_result.error_message:
                    result.error_messages.append(f"行 {i}: {conversion_result.error_message}")
        
        return result
    
    def convert_dataframe_column(
        self,
        df: pl.DataFrame,
        column_name: str,
        target_type: DetectedDataType,
        strategy: ConversionStrategy = ConversionStrategy.COERCIVE,
        **kwargs
    ) -> Tuple[pl.DataFrame, BatchConversionResult]:
        """转换DataFrame中的一列"""
        if column_name not in df.columns:
            raise ValueError(f"Column '{column_name}' not found in DataFrame")
        
        # 获取列值
        column_values = df[column_name].to_list()
        
        # 批量转换
        conversion_result = self.convert_batch(column_values, target_type, strategy, **kwargs)
        
        # 创建新的DataFrame
        new_df = df.with_columns([
            pl.Series(column_name, conversion_result.converted_values)
        ])
        
        return new_df, conversion_result
    
    def get_conversion_suggestions(
        self, 
        schema: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """基于schema获取转换建议"""
        suggestions = {}
        
        for column_name, column_info in schema.get('columns', {}).items():
            detected_type = column_info.get('detected_type')
            confidence = column_info.get('confidence')
            metadata = column_info.get('metadata', {})
            
            column_suggestions = {
                'current_type': detected_type,
                'confidence': confidence,
                'alternative_types': [],
                'conversion_strategy': ConversionStrategy.COERCIVE.value,
                'special_parameters': {}
            }
            
            # 基于置信度和元数据提供建议
            if confidence in ['low', 'very_low']:
                # 低置信度时建议检查其他可能的类型
                if detected_type == 'string':
                    column_suggestions['alternative_types'].extend([
                        'integer', 'float', 'datetime', 'boolean', 'categorical'
                    ])
                elif detected_type in ['integer', 'float']:
                    column_suggestions['alternative_types'].append('string')
                
                column_suggestions['conversion_strategy'] = ConversionStrategy.BEST_EFFORT.value
            
            # 特殊参数建议
            if detected_type == 'categorical':
                unique_values = metadata.get('unique_values', [])
                column_suggestions['special_parameters']['categories'] = unique_values
            
            elif detected_type in ['datetime', 'date']:
                detected_format = metadata.get('detected_format')
                if detected_format:
                    column_suggestions['special_parameters']['format_hint'] = detected_format
            
            elif detected_type == 'decimal':
                max_decimal_places = metadata.get('max_decimal_places', 10)
                column_suggestions['special_parameters']['scale'] = max_decimal_places
            
            suggestions[column_name] = column_suggestions
        
        return suggestions