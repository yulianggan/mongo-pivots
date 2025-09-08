"""
数据验证器 - 数据完整性验证和质量检查
提供全面的数据验证、约束检查和异常值检测功能
"""
import re
import math
import time
import statistics
from typing import Dict, Any, List, Optional, Union, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, date
import logging

import polars as pl
from schema.inferencer import DetectedDataType, DataTypeCategory, TypeInferenceResult


class ValidationSeverity(Enum):
    """验证问题严重程度"""
    INFO = "info"           # 信息，不影响数据使用
    WARNING = "warning"     # 警告，可能影响数据质量
    ERROR = "error"         # 错误，影响数据正确性
    CRITICAL = "critical"   # 严重错误，数据不可用


class ValidationRule(Enum):
    """验证规则类型"""
    # 基本验证
    NOT_NULL = "not_null"
    NOT_EMPTY = "not_empty" 
    UNIQUE = "unique"
    
    # 类型验证
    DATA_TYPE = "data_type"
    FORMAT = "format"
    
    # 范围验证
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    
    # 枚举验证
    IN_LIST = "in_list"
    NOT_IN_LIST = "not_in_list"
    
    # 模式验证
    REGEX_MATCH = "regex_match"
    REGEX_NOT_MATCH = "regex_not_match"
    
    # 统计验证
    OUTLIER_DETECTION = "outlier_detection"
    DISTRIBUTION_CHECK = "distribution_check"
    
    # 关系验证
    FOREIGN_KEY = "foreign_key"
    CONDITIONAL = "conditional"


@dataclass
class ValidationResult:
    """单个验证结果"""
    rule: ValidationRule
    severity: ValidationSeverity
    passed: bool
    message: str
    affected_rows: List[int] = field(default_factory=list)  # 受影响的行号
    affected_count: int = 0
    total_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ColumnValidationReport:
    """列验证报告"""
    column_name: str
    data_type: str
    total_rows: int
    validation_results: List[ValidationResult] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    passed_validations: int = 0
    quality_score: float = 0.0  # 0-100
    
    def add_result(self, result: ValidationResult):
        """添加验证结果"""
        self.validation_results.append(result)
        
        if result.severity == ValidationSeverity.ERROR:
            self.error_count += 1
        elif result.severity == ValidationSeverity.WARNING:
            self.warning_count += 1
        
        if result.passed:
            self.passed_validations += 1
    
    def calculate_quality_score(self):
        """计算质量评分"""
        if not self.validation_results:
            self.quality_score = 100.0
            return
        
        total_validations = len(self.validation_results)
        
        # 基础分数：通过的验证比例
        base_score = (self.passed_validations / total_validations) * 70
        
        # 错误扣分
        error_penalty = self.error_count * 15
        warning_penalty = self.warning_count * 5
        
        # 计算最终分数
        self.quality_score = max(0, min(100, base_score + 30 - error_penalty - warning_penalty))


@dataclass 
class DataValidationReport:
    """数据验证总报告"""
    dataset_name: str
    total_rows: int
    total_columns: int
    validation_timestamp: float
    column_reports: Dict[str, ColumnValidationReport] = field(default_factory=dict)
    overall_quality_score: float = 0.0
    
    def add_column_report(self, report: ColumnValidationReport):
        """添加列验证报告"""
        self.column_reports[report.column_name] = report
    
    def calculate_overall_score(self):
        """计算整体质量评分"""
        if not self.column_reports:
            self.overall_quality_score = 0.0
            return
        
        # 计算每列质量分数的加权平均
        total_score = sum(report.quality_score for report in self.column_reports.values())
        self.overall_quality_score = total_score / len(self.column_reports)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取验证摘要"""
        total_errors = sum(r.error_count for r in self.column_reports.values())
        total_warnings = sum(r.warning_count for r in self.column_reports.values())
        total_validations = sum(len(r.validation_results) for r in self.column_reports.values())
        
        return {
            'overall_quality_score': self.overall_quality_score,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'total_validations': total_validations,
            'columns_with_errors': [name for name, report in self.column_reports.items() if report.error_count > 0],
            'columns_with_warnings': [name for name, report in self.column_reports.items() if report.warning_count > 0],
            'best_quality_columns': sorted(
                self.column_reports.items(),
                key=lambda x: x[1].quality_score,
                reverse=True
            )[:5],  # 前5名最好的列
            'worst_quality_columns': sorted(
                self.column_reports.items(),
                key=lambda x: x[1].quality_score
            )[:5]  # 前5名最差的列
        }


class OutlierDetector:
    """异常值检测器"""
    
    @staticmethod
    def detect_statistical_outliers(
        values: List[Union[int, float]], 
        method: str = 'iqr',
        threshold: float = 1.5
    ) -> Tuple[List[int], Dict[str, Any]]:
        """使用统计方法检测异常值
        
        Args:
            values: 数值列表
            method: 检测方法 ('iqr', 'zscore', 'modified_zscore')
            threshold: 异常值阈值
            
        Returns:
            Tuple[异常值索引列表, 检测统计信息]
        """
        if not values or len(values) < 4:
            return [], {}
        
        numeric_values = [v for v in values if isinstance(v, (int, float)) and not math.isnan(v)]
        if len(numeric_values) < 4:
            return [], {}
        
        outlier_indices = []
        stats = {}
        
        if method == 'iqr':
            # 使用四分位距方法
            q1 = statistics.quantiles(numeric_values, n=4)[0]  # 25%分位数
            q3 = statistics.quantiles(numeric_values, n=4)[2]  # 75%分位数
            iqr = q3 - q1
            lower_bound = q1 - threshold * iqr
            upper_bound = q3 + threshold * iqr
            
            for i, value in enumerate(values):
                if isinstance(value, (int, float)) and not math.isnan(value):
                    if value < lower_bound or value > upper_bound:
                        outlier_indices.append(i)
            
            stats = {
                'method': 'iqr',
                'q1': q1,
                'q3': q3,
                'iqr': iqr,
                'lower_bound': lower_bound,
                'upper_bound': upper_bound,
                'threshold': threshold
            }
            
        elif method == 'zscore':
            # 使用Z分数方法
            mean_val = statistics.mean(numeric_values)
            std_dev = statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0
            
            if std_dev > 0:
                for i, value in enumerate(values):
                    if isinstance(value, (int, float)) and not math.isnan(value):
                        z_score = abs((value - mean_val) / std_dev)
                        if z_score > threshold:
                            outlier_indices.append(i)
            
            stats = {
                'method': 'zscore',
                'mean': mean_val,
                'std_dev': std_dev,
                'threshold': threshold
            }
            
        elif method == 'modified_zscore':
            # 使用修正Z分数方法（基于中位数绝对偏差）
            median_val = statistics.median(numeric_values)
            mad = statistics.median([abs(v - median_val) for v in numeric_values])
            
            if mad > 0:
                for i, value in enumerate(values):
                    if isinstance(value, (int, float)) and not math.isnan(value):
                        modified_z_score = 0.6745 * (value - median_val) / mad
                        if abs(modified_z_score) > threshold:
                            outlier_indices.append(i)
            
            stats = {
                'method': 'modified_zscore',
                'median': median_val,
                'mad': mad,
                'threshold': threshold
            }
        
        return outlier_indices, stats


class ConstraintValidator:
    """约束验证器"""
    
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def validate_not_null(self, values: List[Any], column_name: str) -> ValidationResult:
        """验证非空约束"""
        null_indices = []
        for i, value in enumerate(values):
            if value is None or (isinstance(value, float) and math.isnan(value)):
                null_indices.append(i)
        
        passed = len(null_indices) == 0
        
        return ValidationResult(
            rule=ValidationRule.NOT_NULL,
            severity=ValidationSeverity.ERROR if not passed else ValidationSeverity.INFO,
            passed=passed,
            message=f"列 '{column_name}' 检测到 {len(null_indices)} 个空值" if not passed else f"列 '{column_name}' 无空值",
            affected_rows=null_indices,
            affected_count=len(null_indices),
            total_count=len(values)
        )
    
    def validate_unique(self, values: List[Any], column_name: str) -> ValidationResult:
        """验证唯一性约束"""
        seen = set()
        duplicate_indices = []
        
        for i, value in enumerate(values):
            if value is not None:
                str_value = str(value)
                if str_value in seen:
                    duplicate_indices.append(i)
                else:
                    seen.add(str_value)
        
        passed = len(duplicate_indices) == 0
        
        return ValidationResult(
            rule=ValidationRule.UNIQUE,
            severity=ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO,
            passed=passed,
            message=f"列 '{column_name}' 检测到 {len(duplicate_indices)} 个重复值" if not passed else f"列 '{column_name}' 所有值唯一",
            affected_rows=duplicate_indices,
            affected_count=len(duplicate_indices),
            total_count=len(values),
            details={'unique_count': len(seen)}
        )
    
    def validate_range(
        self, 
        values: List[Any], 
        column_name: str,
        min_value: Optional[Union[int, float]] = None,
        max_value: Optional[Union[int, float]] = None
    ) -> List[ValidationResult]:
        """验证数值范围约束"""
        results = []
        
        if min_value is not None:
            below_min_indices = []
            for i, value in enumerate(values):
                if isinstance(value, (int, float)) and not math.isnan(value) and value < min_value:
                    below_min_indices.append(i)
            
            passed = len(below_min_indices) == 0
            results.append(ValidationResult(
                rule=ValidationRule.MIN_VALUE,
                severity=ValidationSeverity.ERROR if not passed else ValidationSeverity.INFO,
                passed=passed,
                message=f"列 '{column_name}' 有 {len(below_min_indices)} 个值小于最小值 {min_value}" if not passed 
                       else f"列 '{column_name}' 所有值都 >= {min_value}",
                affected_rows=below_min_indices,
                affected_count=len(below_min_indices),
                total_count=len(values),
                details={'min_value': min_value}
            ))
        
        if max_value is not None:
            above_max_indices = []
            for i, value in enumerate(values):
                if isinstance(value, (int, float)) and not math.isnan(value) and value > max_value:
                    above_max_indices.append(i)
            
            passed = len(above_max_indices) == 0
            results.append(ValidationResult(
                rule=ValidationRule.MAX_VALUE,
                severity=ValidationSeverity.ERROR if not passed else ValidationSeverity.INFO,
                passed=passed,
                message=f"列 '{column_name}' 有 {len(above_max_indices)} 个值大于最大值 {max_value}" if not passed 
                       else f"列 '{column_name}' 所有值都 <= {max_value}",
                affected_rows=above_max_indices,
                affected_count=len(above_max_indices),
                total_count=len(values),
                details={'max_value': max_value}
            ))
        
        return results
    
    def validate_length(
        self, 
        values: List[Any], 
        column_name: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None
    ) -> List[ValidationResult]:
        """验证字符串长度约束"""
        results = []
        
        if min_length is not None:
            short_indices = []
            for i, value in enumerate(values):
                if value is not None and len(str(value)) < min_length:
                    short_indices.append(i)
            
            passed = len(short_indices) == 0
            results.append(ValidationResult(
                rule=ValidationRule.MIN_LENGTH,
                severity=ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO,
                passed=passed,
                message=f"列 '{column_name}' 有 {len(short_indices)} 个值长度小于 {min_length}" if not passed
                       else f"列 '{column_name}' 所有值长度都 >= {min_length}",
                affected_rows=short_indices,
                affected_count=len(short_indices),
                total_count=len(values),
                details={'min_length': min_length}
            ))
        
        if max_length is not None:
            long_indices = []
            for i, value in enumerate(values):
                if value is not None and len(str(value)) > max_length:
                    long_indices.append(i)
            
            passed = len(long_indices) == 0
            results.append(ValidationResult(
                rule=ValidationRule.MAX_LENGTH,
                severity=ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO,
                passed=passed,
                message=f"列 '{column_name}' 有 {len(long_indices)} 个值长度大于 {max_length}" if not passed
                       else f"列 '{column_name}' 所有值长度都 <= {max_length}",
                affected_rows=long_indices,
                affected_count=len(long_indices),
                total_count=len(values),
                details={'max_length': max_length}
            ))
        
        return results
    
    def validate_regex(
        self, 
        values: List[Any], 
        column_name: str,
        pattern: str,
        should_match: bool = True
    ) -> ValidationResult:
        """验证正则表达式约束"""
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ValidationResult(
                rule=ValidationRule.REGEX_MATCH if should_match else ValidationRule.REGEX_NOT_MATCH,
                severity=ValidationSeverity.CRITICAL,
                passed=False,
                message=f"正则表达式语法错误: {e}",
                total_count=len(values),
                details={'pattern': pattern, 'error': str(e)}
            )
        
        mismatch_indices = []
        for i, value in enumerate(values):
            if value is not None:
                str_value = str(value)
                matches = bool(regex.search(str_value))
                if matches != should_match:  # 不符合预期
                    mismatch_indices.append(i)
        
        passed = len(mismatch_indices) == 0
        action = "匹配" if should_match else "不匹配"
        
        return ValidationResult(
            rule=ValidationRule.REGEX_MATCH if should_match else ValidationRule.REGEX_NOT_MATCH,
            severity=ValidationSeverity.WARNING if not passed else ValidationSeverity.INFO,
            passed=passed,
            message=f"列 '{column_name}' 有 {len(mismatch_indices)} 个值不符合正则表达式{action}要求" if not passed
                   else f"列 '{column_name}' 所有值都符合正则表达式{action}要求",
            affected_rows=mismatch_indices,
            affected_count=len(mismatch_indices),
            total_count=len(values),
            details={'pattern': pattern, 'should_match': should_match}
        )
    
    def validate_enum(
        self, 
        values: List[Any], 
        column_name: str,
        allowed_values: List[Any],
        case_sensitive: bool = True
    ) -> ValidationResult:
        """验证枚举约束"""
        if case_sensitive:
            allowed_set = set(str(v) for v in allowed_values)
        else:
            allowed_set = set(str(v).lower() for v in allowed_values)
        
        invalid_indices = []
        for i, value in enumerate(values):
            if value is not None:
                str_value = str(value) if case_sensitive else str(value).lower()
                if str_value not in allowed_set:
                    invalid_indices.append(i)
        
        passed = len(invalid_indices) == 0
        
        return ValidationResult(
            rule=ValidationRule.IN_LIST,
            severity=ValidationSeverity.ERROR if not passed else ValidationSeverity.INFO,
            passed=passed,
            message=f"列 '{column_name}' 有 {len(invalid_indices)} 个值不在允许的枚举列表中" if not passed
                   else f"列 '{column_name}' 所有值都在允许的枚举列表中",
            affected_rows=invalid_indices,
            affected_count=len(invalid_indices),
            total_count=len(values),
            details={
                'allowed_values': allowed_values,
                'case_sensitive': case_sensitive,
                'found_invalid_values': list(set(
                    str(values[i]) for i in invalid_indices[:10]  # 最多显示10个无效值样本
                ))
            }
        )


class DataValidator:
    """数据验证器 - 主要验证器类"""
    
    def __init__(self):
        self.constraint_validator = ConstraintValidator()
        self.outlier_detector = OutlierDetector()
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def validate_dataframe(
        self, 
        df: pl.DataFrame,
        schema: Optional[Dict[str, Any]] = None,
        custom_rules: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        dataset_name: str = "unknown"
    ) -> DataValidationReport:
        """验证整个DataFrame
        
        Args:
            df: 要验证的DataFrame
            schema: 推断的schema信息（可选）
            custom_rules: 自定义验证规则（可选）
            dataset_name: 数据集名称
            
        Returns:
            DataValidationReport: 完整验证报告
        """
        start_time = time.time()
        
        report = DataValidationReport(
            dataset_name=dataset_name,
            total_rows=len(df),
            total_columns=len(df.columns),
            validation_timestamp=start_time
        )
        
        # 验证每个列
        for column_name in df.columns:
            try:
                column_values = df[column_name].to_list()
                column_schema = None
                if schema and 'columns' in schema:
                    column_schema = schema['columns'].get(column_name, {})
                
                column_rules = []
                if custom_rules and column_name in custom_rules:
                    column_rules = custom_rules[column_name]
                
                column_report = self.validate_column(
                    column_values, 
                    column_name, 
                    column_schema, 
                    column_rules
                )
                
                report.add_column_report(column_report)
                
            except Exception as e:
                self._logger.error(f"Failed to validate column {column_name}: {e}")
                # 创建错误报告
                error_report = ColumnValidationReport(
                    column_name=column_name,
                    data_type="unknown",
                    total_rows=len(df)
                )
                error_report.add_result(ValidationResult(
                    rule=ValidationRule.DATA_TYPE,
                    severity=ValidationSeverity.CRITICAL,
                    passed=False,
                    message=f"验证过程中发生错误: {str(e)}",
                    total_count=len(df)
                ))
                error_report.calculate_quality_score()
                report.add_column_report(error_report)
        
        # 计算整体质量分数
        report.calculate_overall_score()
        
        validation_duration = time.time() - start_time
        self._logger.info(
            f"Data validation completed for {len(df.columns)} columns "
            f"in {validation_duration:.2f}s. Overall quality score: {report.overall_quality_score:.1f}"
        )
        
        return report
    
    def validate_column(
        self, 
        values: List[Any], 
        column_name: str,
        column_schema: Optional[Dict[str, Any]] = None,
        custom_rules: Optional[List[Dict[str, Any]]] = None
    ) -> ColumnValidationReport:
        """验证单个列
        
        Args:
            values: 列值列表
            column_name: 列名
            column_schema: 列schema信息
            custom_rules: 自定义验证规则
            
        Returns:
            ColumnValidationReport: 列验证报告
        """
        data_type = column_schema.get('detected_type', 'string') if column_schema else 'string'
        
        report = ColumnValidationReport(
            column_name=column_name,
            data_type=data_type,
            total_rows=len(values)
        )
        
        # 基础验证：非空检查
        if column_schema and not column_schema.get('nullable', True):
            result = self.constraint_validator.validate_not_null(values, column_name)
            report.add_result(result)
        
        # 基础验证：唯一性检查（如果推断为唯一）
        if column_schema and column_schema.get('unique_percentage', 0) >= 99:
            result = self.constraint_validator.validate_unique(values, column_name)
            report.add_result(result)
        
        # 根据数据类型进行特定验证
        if data_type in ['integer', 'float', 'decimal']:
            self._validate_numeric_column(values, column_name, column_schema, report)
        elif data_type in ['string', 'categorical']:
            self._validate_text_column(values, column_name, column_schema, report)
        elif data_type in ['date', 'datetime', 'timestamp']:
            self._validate_temporal_column(values, column_name, column_schema, report)
        elif data_type == 'boolean':
            self._validate_boolean_column(values, column_name, column_schema, report)
        
        # 应用自定义验证规则
        if custom_rules:
            for rule_config in custom_rules:
                self._apply_custom_rule(values, column_name, rule_config, report)
        
        # 计算列质量分数
        report.calculate_quality_score()
        
        return report
    
    def _validate_numeric_column(
        self, 
        values: List[Any], 
        column_name: str, 
        column_schema: Optional[Dict[str, Any]],
        report: ColumnValidationReport
    ):
        """验证数值类型列"""
        # 异常值检测
        outlier_indices, outlier_stats = self.outlier_detector.detect_statistical_outliers(
            values, method='iqr', threshold=2.0
        )
        
        if outlier_indices:
            severity = ValidationSeverity.WARNING if len(outlier_indices) <= len(values) * 0.1 else ValidationSeverity.ERROR
            report.add_result(ValidationResult(
                rule=ValidationRule.OUTLIER_DETECTION,
                severity=severity,
                passed=len(outlier_indices) == 0,
                message=f"列 '{column_name}' 检测到 {len(outlier_indices)} 个统计异常值 ({len(outlier_indices)/len(values)*100:.1f}%)",
                affected_rows=outlier_indices,
                affected_count=len(outlier_indices),
                total_count=len(values),
                details=outlier_stats
            ))
        
        # 数值范围验证（基于推断的元数据）
        if column_schema and 'metadata' in column_schema:
            metadata = column_schema['metadata']
            min_val = metadata.get('min_value')
            max_val = metadata.get('max_value')
            
            # 检查极值是否合理
            if min_val is not None and max_val is not None:
                range_val = max_val - min_val
                if range_val <= 0:
                    report.add_result(ValidationResult(
                        rule=ValidationRule.DISTRIBUTION_CHECK,
                        severity=ValidationSeverity.WARNING,
                        passed=False,
                        message=f"列 '{column_name}' 的数值范围异常: min={min_val}, max={max_val}",
                        total_count=len(values),
                        details={'min_value': min_val, 'max_value': max_val, 'range': range_val}
                    ))
    
    def _validate_text_column(
        self, 
        values: List[Any], 
        column_name: str, 
        column_schema: Optional[Dict[str, Any]],
        report: ColumnValidationReport
    ):
        """验证文本类型列"""
        # 检查空字符串
        empty_indices = []
        for i, value in enumerate(values):
            if isinstance(value, str) and value.strip() == '':
                empty_indices.append(i)
        
        if empty_indices:
            report.add_result(ValidationResult(
                rule=ValidationRule.NOT_EMPTY,
                severity=ValidationSeverity.WARNING,
                passed=len(empty_indices) == 0,
                message=f"列 '{column_name}' 有 {len(empty_indices)} 个空字符串",
                affected_rows=empty_indices,
                affected_count=len(empty_indices),
                total_count=len(values)
            ))
        
        # 文本长度分布检查
        if column_schema and 'metadata' in column_schema:
            metadata = column_schema['metadata']
            avg_length = metadata.get('avg_length', 0)
            max_length = metadata.get('max_length', 0)
            
            # 检查异常长度的文本
            if avg_length > 0:
                long_threshold = avg_length * 3  # 超过平均长度3倍认为异常
                long_indices = []
                for i, value in enumerate(values):
                    if value is not None and len(str(value)) > long_threshold:
                        long_indices.append(i)
                
                if long_indices:
                    report.add_result(ValidationResult(
                        rule=ValidationRule.MAX_LENGTH,
                        severity=ValidationSeverity.WARNING,
                        passed=len(long_indices) == 0,
                        message=f"列 '{column_name}' 有 {len(long_indices)} 个异常长度的文本（超过平均长度3倍）",
                        affected_rows=long_indices,
                        affected_count=len(long_indices),
                        total_count=len(values),
                        details={'avg_length': avg_length, 'threshold': long_threshold}
                    ))
    
    def _validate_temporal_column(
        self, 
        values: List[Any], 
        column_name: str, 
        column_schema: Optional[Dict[str, Any]],
        report: ColumnValidationReport
    ):
        """验证时间类型列"""
        # 检查日期范围合理性
        valid_dates = []
        invalid_indices = []
        
        for i, value in enumerate(values):
            if value is not None:
                try:
                    if isinstance(value, (datetime, date)):
                        valid_dates.append(value)
                    else:
                        # 尝试解析字符串日期
                        # 这里可以使用schema中的格式信息
                        if column_schema and 'metadata' in column_schema:
                            detected_format = column_schema['metadata'].get('detected_format')
                            if detected_format and not column_schema['metadata'].get('is_timestamp', False):
                                try:
                                    parsed_date = datetime.strptime(str(value), detected_format)
                                    valid_dates.append(parsed_date)
                                except ValueError:
                                    invalid_indices.append(i)
                            else:
                                invalid_indices.append(i)
                        else:
                            invalid_indices.append(i)
                except Exception:
                    invalid_indices.append(i)
        
        # 检查日期范围合理性
        if valid_dates:
            current_year = datetime.now().year
            future_dates = []
            ancient_dates = []
            
            for i, dt in enumerate(valid_dates):
                if hasattr(dt, 'year'):
                    if dt.year > current_year + 10:  # 未来10年后
                        future_dates.append(i)
                    elif dt.year < 1900:  # 1900年之前
                        ancient_dates.append(i)
            
            if future_dates:
                report.add_result(ValidationResult(
                    rule=ValidationRule.MAX_VALUE,
                    severity=ValidationSeverity.WARNING,
                    passed=False,
                    message=f"列 '{column_name}' 有 {len(future_dates)} 个过于未来的日期",
                    affected_rows=future_dates,
                    affected_count=len(future_dates),
                    total_count=len(values)
                ))
            
            if ancient_dates:
                report.add_result(ValidationResult(
                    rule=ValidationRule.MIN_VALUE,
                    severity=ValidationSeverity.WARNING,
                    passed=False,
                    message=f"列 '{column_name}' 有 {len(ancient_dates)} 个过于古老的日期",
                    affected_rows=ancient_dates,
                    affected_count=len(ancient_dates),
                    total_count=len(values)
                ))
        
        if invalid_indices:
            report.add_result(ValidationResult(
                rule=ValidationRule.FORMAT,
                severity=ValidationSeverity.ERROR,
                passed=False,
                message=f"列 '{column_name}' 有 {len(invalid_indices)} 个无法解析的日期格式",
                affected_rows=invalid_indices,
                affected_count=len(invalid_indices),
                total_count=len(values)
            ))
    
    def _validate_boolean_column(
        self, 
        values: List[Any], 
        column_name: str, 
        column_schema: Optional[Dict[str, Any]],
        report: ColumnValidationReport
    ):
        """验证布尔类型列"""
        # 检查布尔值表示的一致性
        if column_schema and 'metadata' in column_schema:
            boolean_representations = column_schema['metadata'].get('boolean_representations', [])
            
            # 如果布尔表示过多，可能存在数据不一致
            if len(boolean_representations) > 4:  # 超过4种表示方式
                report.add_result(ValidationResult(
                    rule=ValidationRule.FORMAT,
                    severity=ValidationSeverity.WARNING,
                    passed=False,
                    message=f"列 '{column_name}' 布尔值表示方式过多 ({len(boolean_representations)}种)，可能存在数据不一致",
                    total_count=len(values),
                    details={'representations': boolean_representations}
                ))
    
    def _apply_custom_rule(
        self, 
        values: List[Any], 
        column_name: str, 
        rule_config: Dict[str, Any],
        report: ColumnValidationReport
    ):
        """应用自定义验证规则"""
        try:
            rule_type = rule_config.get('type')
            params = rule_config.get('params', {})
            
            if rule_type == 'range':
                results = self.constraint_validator.validate_range(
                    values, column_name,
                    params.get('min_value'),
                    params.get('max_value')
                )
                for result in results:
                    report.add_result(result)
                    
            elif rule_type == 'length':
                results = self.constraint_validator.validate_length(
                    values, column_name,
                    params.get('min_length'),
                    params.get('max_length')
                )
                for result in results:
                    report.add_result(result)
                    
            elif rule_type == 'regex':
                result = self.constraint_validator.validate_regex(
                    values, column_name,
                    params.get('pattern', ''),
                    params.get('should_match', True)
                )
                report.add_result(result)
                
            elif rule_type == 'enum':
                result = self.constraint_validator.validate_enum(
                    values, column_name,
                    params.get('allowed_values', []),
                    params.get('case_sensitive', True)
                )
                report.add_result(result)
                
        except Exception as e:
            self._logger.error(f"Failed to apply custom rule {rule_config} to column {column_name}: {e}")
            report.add_result(ValidationResult(
                rule=ValidationRule.CONDITIONAL,
                severity=ValidationSeverity.ERROR,
                passed=False,
                message=f"自定义规则执行失败: {str(e)}",
                total_count=len(values)
            ))