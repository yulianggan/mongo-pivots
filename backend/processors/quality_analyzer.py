"""
QualityAnalyzer - 数据质量分析器
提供全面的数据质量分析、指标计算、异常检测和质量报告生成功能
"""

import polars as pl
import numpy as np
from typing import Dict, List, Any, Optional, Union, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import logging
import time
import asyncio
import json
import statistics
from collections import defaultdict, Counter
import hashlib

# 尝试导入，如果失败则使用Mock
try:
    from backend.core.memory_guard import MemoryGuard
    memory_guard = MemoryGuard()
except ImportError:
    # 测试环境中的Mock
    class MockMemoryGuard:
        def memory_guard(self, operation):
            from contextlib import contextmanager
            @contextmanager
            def mock_context():
                yield
            return mock_context()
        
        def get_memory_stats(self):
            class MockStats:
                rss_bytes = 100 * 1024 * 1024  # 100MB
            return MockStats()
    
    memory_guard = MockMemoryGuard()


class QualityDimension(Enum):
    """质量维度枚举"""
    COMPLETENESS = "completeness"          # 完整性
    ACCURACY = "accuracy"                  # 准确性
    CONSISTENCY = "consistency"            # 一致性
    VALIDITY = "validity"                  # 有效性
    UNIQUENESS = "uniqueness"              # 唯一性
    TIMELINESS = "timeliness"              # 及时性


class QualitySeverity(Enum):
    """质量问题严重程度"""
    CRITICAL = "critical"    # 严重问题，影响数据使用
    HIGH = "high"            # 高优先级问题
    MEDIUM = "medium"        # 中等问题
    LOW = "low"              # 低优先级问题
    INFO = "info"            # 仅提示信息


class AnalysisScope(Enum):
    """分析范围"""
    COLUMN = "column"        # 列级分析
    TABLE = "table"          # 表级分析
    DATASET = "dataset"      # 数据集级分析
    CROSS_TABLE = "cross"    # 跨表分析


@dataclass
class QualityRule:
    """数据质量规则定义"""
    name: str                              # 规则名称
    dimension: QualityDimension            # 质量维度
    scope: AnalysisScope                   # 分析范围
    severity: QualitySeverity              # 严重程度
    description: str                       # 规则描述
    check_function: str                    # 检查函数名
    threshold: Optional[float] = None      # 阈值
    parameters: Dict[str, Any] = field(default_factory=dict)  # 参数


@dataclass
class QualityIssue:
    """质量问题记录"""
    rule_name: str                         # 触发的规则名称
    dimension: QualityDimension            # 质量维度
    severity: QualitySeverity              # 严重程度
    scope: AnalysisScope                   # 问题范围
    column: Optional[str] = None           # 相关列名
    table: Optional[str] = None            # 相关表名
    description: str = ""                  # 问题描述
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息
    affected_rows: int = 0                 # 影响行数
    affected_percentage: float = 0.0       # 影响百分比
    recommendation: str = ""               # 修复建议
    timestamp: datetime = field(default_factory=datetime.now)  # 发现时间


@dataclass
class QualityMetrics:
    """质量指标汇总"""
    overall_score: float                   # 整体质量分数 (0-100)
    dimension_scores: Dict[QualityDimension, float]  # 各维度分数
    completeness_rate: float               # 完整性比率
    accuracy_score: float                  # 准确性分数
    consistency_rate: float                # 一致性比率
    validity_rate: float                   # 有效性比率
    uniqueness_rate: float                 # 唯一性比率
    timeliness_score: float                # 及时性分数
    total_records: int                     # 总记录数
    valid_records: int                     # 有效记录数
    invalid_records: int                   # 无效记录数
    duplicate_records: int                 # 重复记录数
    missing_values: int                    # 缺失值数量
    outliers: int                          # 异常值数量
    issues_by_severity: Dict[QualitySeverity, int]  # 按严重程度统计问题


@dataclass
class ColumnProfile:
    """列数据轮廓"""
    column_name: str                       # 列名
    data_type: str                         # 数据类型
    nullable: bool                         # 是否可为空
    unique_count: int                      # 唯一值数量
    null_count: int                        # 空值数量
    null_percentage: float                 # 空值百分比
    min_value: Any = None                  # 最小值
    max_value: Any = None                  # 最大值
    mean_value: Optional[float] = None     # 平均值
    median_value: Optional[float] = None   # 中位数
    std_value: Optional[float] = None      # 标准差
    mode_values: List[Any] = field(default_factory=list)  # 众数
    value_distribution: Dict[str, int] = field(default_factory=dict)  # 值分布
    pattern_analysis: Dict[str, Any] = field(default_factory=dict)    # 模式分析
    quality_issues: List[QualityIssue] = field(default_factory=list) # 质量问题


@dataclass
class QualityAnalysisResult:
    """质量分析结果"""
    analyzed_data: pl.DataFrame            # 分析后的数据
    quality_metrics: QualityMetrics        # 质量指标
    column_profiles: Dict[str, ColumnProfile]  # 列轮廓
    quality_issues: List[QualityIssue]     # 发现的质量问题
    recommendations: List[str]             # 改进建议
    analysis_summary: Dict[str, Any]       # 分析摘要
    execution_time: float                  # 执行时间
    memory_usage_mb: float                 # 内存使用量
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据


@dataclass
class QualityAnalysisConfig:
    """质量分析配置"""
    target_columns: Optional[List[str]] = None        # 目标列（None为所有列）
    analysis_dimensions: List[QualityDimension] = field(default_factory=lambda: list(QualityDimension))
    enable_profiling: bool = True                     # 启用数据轮廓
    enable_pattern_analysis: bool = True              # 启用模式分析
    enable_outlier_detection: bool = True             # 启用异常值检测
    enable_cross_column_analysis: bool = True         # 启用跨列分析
    outlier_method: str = "z_score"                   # 异常值检测方法
    outlier_threshold: float = 3.0                    # 异常值阈值
    sample_size: Optional[int] = None                 # 采样大小（None为全量）
    quality_threshold: float = 70.0                   # 质量阈值（0-100）
    custom_rules: List[QualityRule] = field(default_factory=list)  # 自定义规则
    output_format: str = "detailed"                   # 输出格式
    generate_report: bool = True                      # 生成报告
    
    def __post_init__(self):
        """后处理初始化，验证配置"""
        if not 0 <= self.quality_threshold <= 100:
            raise ValueError("quality_threshold must be between 0 and 100")
        
        if self.outlier_threshold <= 0:
            raise ValueError("outlier_threshold must be positive")
        
        if self.sample_size is not None and self.sample_size <= 0:
            raise ValueError("sample_size must be positive when specified")


class QualityAnalyzer:
    """数据质量分析器主类"""
    
    def __init__(self, config: Optional[QualityAnalysisConfig] = None):
        """初始化质量分析器
        
        Args:
            config: 分析配置，如果为None则使用默认配置
        """
        self.config = config or QualityAnalysisConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.quality_rules = self._initialize_default_rules()
        self.quality_rules.extend(self.config.custom_rules)
        
    def analyze(self, df: pl.DataFrame, table_name: str = "default") -> QualityAnalysisResult:
        """执行数据质量分析
        
        Args:
            df: 输入数据框
            table_name: 表名
            
        Returns:
            质量分析结果
        """
        start_time = time.time()
        
        with memory_guard.memory_guard("quality_analysis"):
            self.logger.info(f"开始数据质量分析，表名: {table_name}, 行数: {df.height}, 列数: {df.width}")
            
            # 数据采样
            analyzed_df = self._sample_data(df) if self.config.sample_size else df
            
            # 列轮廓分析
            column_profiles = {}
            if self.config.enable_profiling:
                column_profiles = self._analyze_column_profiles(analyzed_df)
            
            # 质量问题检测
            quality_issues = self._detect_quality_issues(analyzed_df, column_profiles, table_name)
            
            # 计算质量指标
            quality_metrics = self._calculate_quality_metrics(analyzed_df, column_profiles, quality_issues)
            
            # 生成改进建议
            recommendations = self._generate_recommendations(quality_issues, quality_metrics)
            
            # 分析摘要
            analysis_summary = self._generate_analysis_summary(analyzed_df, quality_metrics, quality_issues)
            
            execution_time = time.time() - start_time
            memory_stats = memory_guard.get_memory_stats()
            memory_usage = memory_stats.rss_bytes / (1024 * 1024)  # MB
            
            result = QualityAnalysisResult(
                analyzed_data=analyzed_df,
                quality_metrics=quality_metrics,
                column_profiles=column_profiles,
                quality_issues=quality_issues,
                recommendations=recommendations,
                analysis_summary=analysis_summary,
                execution_time=execution_time,
                memory_usage_mb=memory_usage,
                metadata={
                    "table_name": table_name,
                    "original_rows": df.height,
                    "analyzed_rows": analyzed_df.height,
                    "config": self.config.__dict__
                }
            )
            
            self.logger.info(f"质量分析完成，整体质量分数: {quality_metrics.overall_score:.1f}, "
                           f"发现 {len(quality_issues)} 个问题, 耗时: {execution_time:.3f}s")
            
            return result
    
    async def analyze_async(self, df: pl.DataFrame, table_name: str = "default") -> QualityAnalysisResult:
        """异步执行数据质量分析"""
        return await asyncio.to_thread(self.analyze, df, table_name)
    
    def _sample_data(self, df: pl.DataFrame) -> pl.DataFrame:
        """数据采样"""
        if self.config.sample_size is None or df.height <= self.config.sample_size:
            return df
        
        self.logger.info(f"对数据进行采样，从 {df.height} 行采样 {self.config.sample_size} 行")
        return df.sample(n=self.config.sample_size, seed=42)
    
    def _analyze_column_profiles(self, df: pl.DataFrame) -> Dict[str, ColumnProfile]:
        """分析列数据轮廓"""
        profiles = {}
        target_columns = self.config.target_columns or df.columns
        
        for col in target_columns:
            if col not in df.columns:
                self.logger.warning(f"目标列 '{col}' 不存在，跳过分析")
                continue
            
            profiles[col] = self._analyze_single_column(df, col)
        
        return profiles
    
    def _analyze_single_column(self, df: pl.DataFrame, col: str) -> ColumnProfile:
        """分析单列数据轮廓"""
        column_data = df[col]
        data_type = str(column_data.dtype)
        
        # 基础统计
        null_count = column_data.null_count()
        total_count = df.height
        null_percentage = (null_count / total_count) * 100 if total_count > 0 else 0
        unique_count = column_data.n_unique()
        
        profile = ColumnProfile(
            column_name=col,
            data_type=data_type,
            nullable=null_count > 0,
            unique_count=unique_count,
            null_count=null_count,
            null_percentage=null_percentage
        )
        
        # 数值列统计
        if column_data.dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                                 pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                                 pl.Float32, pl.Float64]:
            non_null_data = column_data.drop_nulls()
            if len(non_null_data) > 0:
                profile.min_value = non_null_data.min()
                profile.max_value = non_null_data.max()
                profile.mean_value = non_null_data.mean()
                profile.median_value = non_null_data.median()
                profile.std_value = non_null_data.std()
        
        # 字符串列统计
        elif column_data.dtype == pl.Utf8:
            non_null_data = column_data.drop_nulls()
            if len(non_null_data) > 0:
                lengths = non_null_data.str.len_chars()
                profile.min_value = lengths.min()
                profile.max_value = lengths.max()
                profile.mean_value = lengths.mean()
        
        # 值分布统计（限制前10）
        value_counts = column_data.value_counts().limit(10)
        profile.value_distribution = {
            str(row[0]): row[1] for row in value_counts.rows()
        }
        
        # 众数计算
        if len(profile.value_distribution) > 0:
            max_count = max(profile.value_distribution.values())
            profile.mode_values = [k for k, v in profile.value_distribution.items() if v == max_count]
        
        # 模式分析
        if self.config.enable_pattern_analysis:
            profile.pattern_analysis = self._analyze_column_patterns(column_data)
        
        return profile
    
    def _analyze_column_patterns(self, column_data: pl.Expr) -> Dict[str, Any]:
        """分析列数据模式"""
        patterns = {}
        
        if column_data.dtype == pl.Utf8:
            non_null_data = column_data.drop_nulls()
            if len(non_null_data) > 0:
                # 检测常见模式
                patterns["has_email_pattern"] = any("@" in str(val) for val in non_null_data.to_list()[:100])
                patterns["has_phone_pattern"] = any(str(val).isdigit() and len(str(val)) >= 10 
                                                   for val in non_null_data.to_list()[:100])
                patterns["has_url_pattern"] = any(str(val).startswith(("http://", "https://"))
                                                 for val in non_null_data.to_list()[:100])
        
        return patterns
    
    def _detect_quality_issues(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        table_name: str
    ) -> List[QualityIssue]:
        """检测质量问题"""
        issues = []
        
        for rule in self.quality_rules:
            if QualityDimension.COMPLETENESS in self.config.analysis_dimensions and \
               rule.dimension == QualityDimension.COMPLETENESS:
                issues.extend(self._check_completeness_rules(df, column_profiles, rule, table_name))
            
            if QualityDimension.VALIDITY in self.config.analysis_dimensions and \
               rule.dimension == QualityDimension.VALIDITY:
                issues.extend(self._check_validity_rules(df, column_profiles, rule, table_name))
            
            if QualityDimension.UNIQUENESS in self.config.analysis_dimensions and \
               rule.dimension == QualityDimension.UNIQUENESS:
                issues.extend(self._check_uniqueness_rules(df, column_profiles, rule, table_name))
            
            if QualityDimension.CONSISTENCY in self.config.analysis_dimensions and \
               rule.dimension == QualityDimension.CONSISTENCY:
                issues.extend(self._check_consistency_rules(df, column_profiles, rule, table_name))
            
            if QualityDimension.ACCURACY in self.config.analysis_dimensions and \
               rule.dimension == QualityDimension.ACCURACY and \
               self.config.enable_outlier_detection:
                issues.extend(self._check_accuracy_rules(df, column_profiles, rule, table_name))
        
        return issues
    
    def _check_completeness_rules(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        rule: QualityRule, 
        table_name: str
    ) -> List[QualityIssue]:
        """检查完整性规则"""
        issues = []
        
        if rule.check_function == "high_null_percentage":
            threshold = rule.threshold or 50.0  # 默认50%阈值
            
            for col_name, profile in column_profiles.items():
                if profile.null_percentage > threshold:
                    issue = QualityIssue(
                        rule_name=rule.name,
                        dimension=rule.dimension,
                        severity=rule.severity,
                        scope=rule.scope,
                        column=col_name,
                        table=table_name,
                        description=f"列 '{col_name}' 的空值比例过高: {profile.null_percentage:.1f}%",
                        details={
                            "null_count": profile.null_count,
                            "null_percentage": profile.null_percentage,
                            "threshold": threshold
                        },
                        affected_rows=profile.null_count,
                        affected_percentage=profile.null_percentage,
                        recommendation=f"检查数据源和ETL过程，考虑数据填充或列删除策略"
                    )
                    issues.append(issue)
        
        elif rule.check_function == "empty_table":
            if df.height == 0:
                issue = QualityIssue(
                    rule_name=rule.name,
                    dimension=rule.dimension,
                    severity=QualitySeverity.CRITICAL,
                    scope=AnalysisScope.TABLE,
                    table=table_name,
                    description=f"表 '{table_name}' 为空",
                    details={"row_count": 0},
                    affected_rows=0,
                    affected_percentage=100.0,
                    recommendation="检查数据加载过程，确认数据源是否正确"
                )
                issues.append(issue)
        
        return issues
    
    def _check_validity_rules(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        rule: QualityRule, 
        table_name: str
    ) -> List[QualityIssue]:
        """检查有效性规则"""
        issues = []
        
        if rule.check_function == "negative_values_in_positive_columns":
            # 检查应该为正数的列中是否有负值
            for col_name in rule.parameters.get("positive_columns", []):
                if col_name in column_profiles and col_name in df.columns:
                    column_data = df[col_name]
                    if column_data.dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                                           pl.Float32, pl.Float64]:
                        negative_count = (column_data < 0).sum()
                        if negative_count > 0:
                            issue = QualityIssue(
                                rule_name=rule.name,
                                dimension=rule.dimension,
                                severity=rule.severity,
                                scope=rule.scope,
                                column=col_name,
                                table=table_name,
                                description=f"列 '{col_name}' 包含 {negative_count} 个负值",
                                details={"negative_count": negative_count},
                                affected_rows=negative_count,
                                affected_percentage=(negative_count / df.height) * 100,
                                recommendation="检查数据输入，修正或过滤负值"
                            )
                            issues.append(issue)
        
        return issues
    
    def _check_uniqueness_rules(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        rule: QualityRule, 
        table_name: str
    ) -> List[QualityIssue]:
        """检查唯一性规则"""
        issues = []
        
        if rule.check_function == "duplicate_values":
            for col_name in rule.parameters.get("unique_columns", []):
                if col_name in column_profiles:
                    profile = column_profiles[col_name]
                    expected_unique = df.height - profile.null_count
                    actual_unique = profile.unique_count
                    
                    if actual_unique < expected_unique:
                        duplicate_count = expected_unique - actual_unique
                        issue = QualityIssue(
                            rule_name=rule.name,
                            dimension=rule.dimension,
                            severity=rule.severity,
                            scope=rule.scope,
                            column=col_name,
                            table=table_name,
                            description=f"列 '{col_name}' 存在重复值",
                            details={
                                "expected_unique": expected_unique,
                                "actual_unique": actual_unique,
                                "duplicate_count": duplicate_count
                            },
                            affected_rows=duplicate_count,
                            affected_percentage=(duplicate_count / df.height) * 100,
                            recommendation="检查数据源，考虑去重或建立唯一性约束"
                        )
                        issues.append(issue)
        
        return issues
    
    def _check_consistency_rules(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        rule: QualityRule, 
        table_name: str
    ) -> List[QualityIssue]:
        """检查一致性规则"""
        issues = []
        
        if rule.check_function == "inconsistent_formats":
            # 检查格式不一致（简化实现）
            for col_name, profile in column_profiles.items():
                if profile.data_type == "Utf8" and len(profile.value_distribution) > 0:
                    # 检查值长度变化是否过大
                    if hasattr(profile, 'min_value') and hasattr(profile, 'max_value'):
                        if profile.min_value is not None and profile.max_value is not None:
                            length_variance = profile.max_value - profile.min_value
                            if length_variance > 50:  # 长度差异超过50字符
                                issue = QualityIssue(
                                    rule_name=rule.name,
                                    dimension=rule.dimension,
                                    severity=rule.severity,
                                    scope=rule.scope,
                                    column=col_name,
                                    table=table_name,
                                    description=f"列 '{col_name}' 格式不一致，长度变化范围: {profile.min_value}-{profile.max_value}",
                                    details={
                                        "min_length": profile.min_value,
                                        "max_length": profile.max_value,
                                        "length_variance": length_variance
                                    },
                                    affected_rows=0,  # 难以精确计算
                                    affected_percentage=0,
                                    recommendation="标准化数据格式，建立格式验证规则"
                                )
                                issues.append(issue)
        
        return issues
    
    def _check_accuracy_rules(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        rule: QualityRule, 
        table_name: str
    ) -> List[QualityIssue]:
        """检查准确性规则（异常值检测）"""
        issues = []
        
        if rule.check_function == "outlier_detection":
            for col_name, profile in column_profiles.items():
                if profile.data_type in ["Int64", "Float64", "Int32", "Float32"]:
                    outliers = self._detect_outliers(df[col_name])
                    
                    if len(outliers) > 0:
                        issue = QualityIssue(
                            rule_name=rule.name,
                            dimension=rule.dimension,
                            severity=rule.severity,
                            scope=rule.scope,
                            column=col_name,
                            table=table_name,
                            description=f"列 '{col_name}' 检测到 {len(outliers)} 个异常值",
                            details={
                                "outlier_count": len(outliers),
                                "detection_method": self.config.outlier_method,
                                "threshold": self.config.outlier_threshold
                            },
                            affected_rows=len(outliers),
                            affected_percentage=(len(outliers) / df.height) * 100,
                            recommendation="检查异常值原因，考虑数据清洗或异常值处理"
                        )
                        issues.append(issue)
        
        return issues
    
    def _detect_outliers(self, column_data: pl.Expr) -> List[int]:
        """检测异常值"""
        non_null_data = column_data.drop_nulls()
        
        if len(non_null_data) < 3:  # 数据量太小，不检测异常值
            return []
        
        if self.config.outlier_method == "z_score":
            mean_val = non_null_data.mean()
            std_val = non_null_data.std()
            
            if std_val is None or std_val == 0:
                return []
            
            # 直接计算z-scores并检测异常值
            z_scores_expr = ((column_data - mean_val) / std_val).abs()
            outlier_mask = z_scores_expr > self.config.outlier_threshold
            
            # 找到异常值的索引
            outlier_indices = []
            for i, (val, is_outlier) in enumerate(zip(column_data.to_list(), outlier_mask.to_list())):
                if val is not None and is_outlier:
                    outlier_indices.append(i)
            
            return outlier_indices
        
        elif self.config.outlier_method == "iqr":
            q1 = non_null_data.quantile(0.25)
            q3 = non_null_data.quantile(0.75)
            iqr = q3 - q1
            
            if iqr == 0:
                return []
            
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            outlier_mask = (non_null_data < lower_bound) | (non_null_data > upper_bound)
            outlier_indices = outlier_mask.arg_true().to_list()
            return outlier_indices
        
        return []
    
    def _calculate_quality_metrics(
        self, 
        df: pl.DataFrame, 
        column_profiles: Dict[str, ColumnProfile], 
        quality_issues: List[QualityIssue]
    ) -> QualityMetrics:
        """计算质量指标"""
        total_records = df.height
        
        # 统计各维度问题
        issues_by_severity = defaultdict(int)
        issues_by_dimension = defaultdict(int)
        
        for issue in quality_issues:
            issues_by_severity[issue.severity] += 1
            issues_by_dimension[issue.dimension] += 1
        
        # 计算完整性指标
        total_cells = df.height * df.width if df.width > 0 else 1
        missing_values = sum(profile.null_count for profile in column_profiles.values())
        completeness_rate = max(0, (total_cells - missing_values) / total_cells) if total_cells > 0 else 0
        
        # 计算各维度分数 (0-100)
        dimension_scores = {}
        for dimension in QualityDimension:
            issue_count = issues_by_dimension[dimension]
            critical_issues = sum(1 for issue in quality_issues 
                                if issue.dimension == dimension and issue.severity == QualitySeverity.CRITICAL)
            high_issues = sum(1 for issue in quality_issues 
                            if issue.dimension == dimension and issue.severity == QualitySeverity.HIGH)
            
            # 基础分数，根据问题数量和严重程度扣分
            base_score = 100.0
            penalty = (critical_issues * 30) + (high_issues * 20) + (issue_count * 5)  # 严重问题重扣分
            
            # 特殊处理完整性维度 - 基于实际完整性率
            if dimension == QualityDimension.COMPLETENESS:
                completeness_score = completeness_rate * 100
                dimension_scores[dimension] = min(completeness_score, max(0, base_score - penalty))
            else:
                dimension_scores[dimension] = max(0, base_score - penalty)
        
        # 计算整体分数（加权平均）
        weights = {
            QualityDimension.COMPLETENESS: 0.25,
            QualityDimension.ACCURACY: 0.20,
            QualityDimension.VALIDITY: 0.20,
            QualityDimension.CONSISTENCY: 0.15,
            QualityDimension.UNIQUENESS: 0.15,
            QualityDimension.TIMELINESS: 0.05
        }
        
        overall_score = sum(
            dimension_scores[dim] * weight 
            for dim, weight in weights.items()
        )
        
        # 统计记录数
        valid_records = total_records - issues_by_severity[QualitySeverity.CRITICAL]
        invalid_records = total_records - valid_records
        
        # 计算重复记录数
        duplicate_records = sum(
            issue.affected_rows for issue in quality_issues 
            if issue.dimension == QualityDimension.UNIQUENESS
        )
        
        # 计算异常值数
        outliers = sum(
            issue.affected_rows for issue in quality_issues 
            if issue.dimension == QualityDimension.ACCURACY
        )
        
        return QualityMetrics(
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            completeness_rate=completeness_rate,
            accuracy_score=dimension_scores[QualityDimension.ACCURACY] / 100,
            consistency_rate=dimension_scores[QualityDimension.CONSISTENCY] / 100,
            validity_rate=dimension_scores[QualityDimension.VALIDITY] / 100,
            uniqueness_rate=dimension_scores[QualityDimension.UNIQUENESS] / 100,
            timeliness_score=dimension_scores[QualityDimension.TIMELINESS] / 100,
            total_records=total_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            duplicate_records=duplicate_records,
            missing_values=missing_values,
            outliers=outliers,
            issues_by_severity=dict(issues_by_severity)
        )
    
    def _generate_recommendations(
        self, 
        quality_issues: List[QualityIssue], 
        quality_metrics: QualityMetrics
    ) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        # 基于整体分数的建议
        if quality_metrics.overall_score < 50:
            recommendations.append("数据质量较差，建议进行全面的数据清洗和质量改进")
        elif quality_metrics.overall_score < 70:
            recommendations.append("数据质量一般，建议重点关注主要质量问题")
        elif quality_metrics.overall_score < 90:
            recommendations.append("数据质量良好，建议进行细节优化")
        else:
            recommendations.append("数据质量优秀，保持现有数据管理标准")
        
        # 基于具体问题的建议
        critical_issues = [issue for issue in quality_issues if issue.severity == QualitySeverity.CRITICAL]
        if critical_issues:
            recommendations.append(f"发现 {len(critical_issues)} 个严重问题，需要立即处理")
        
        high_issues = [issue for issue in quality_issues if issue.severity == QualitySeverity.HIGH]
        if high_issues:
            recommendations.append(f"发现 {len(high_issues)} 个高优先级问题，建议优先处理")
        
        # 基于维度的建议
        if quality_metrics.completeness_rate < 0.8:
            recommendations.append("完整性较差，建议检查数据采集和ETL过程")
        
        if quality_metrics.accuracy_score < 0.8:
            recommendations.append("准确性需要改进，建议加强数据验证和异常值检测")
        
        if quality_metrics.consistency_rate < 0.8:
            recommendations.append("一致性有待提升，建议标准化数据格式和编码规范")
        
        return recommendations
    
    def _generate_analysis_summary(
        self, 
        df: pl.DataFrame, 
        quality_metrics: QualityMetrics, 
        quality_issues: List[QualityIssue]
    ) -> Dict[str, Any]:
        """生成分析摘要"""
        return {
            "dataset_info": {
                "rows": df.height,
                "columns": df.width,
                "memory_usage_mb": df.estimated_size("mb")
            },
            "quality_summary": {
                "overall_score": quality_metrics.overall_score,
                "grade": self._get_quality_grade(quality_metrics.overall_score),
                "total_issues": len(quality_issues),
                "critical_issues": quality_metrics.issues_by_severity.get(QualitySeverity.CRITICAL, 0),
                "high_issues": quality_metrics.issues_by_severity.get(QualitySeverity.HIGH, 0)
            },
            "completeness_summary": {
                "completeness_rate": quality_metrics.completeness_rate,
                "missing_values": quality_metrics.missing_values,
                "missing_percentage": (quality_metrics.missing_values / (df.height * df.width)) * 100 if (df.width > 0 and df.height > 0) else 0
            },
            "uniqueness_summary": {
                "duplicate_records": quality_metrics.duplicate_records,
                "duplicate_percentage": (quality_metrics.duplicate_records / df.height) * 100 if df.height > 0 else 0
            }
        }
    
    def _get_quality_grade(self, score: float) -> str:
        """根据分数获取质量等级"""
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def _initialize_default_rules(self) -> List[QualityRule]:
        """初始化默认质量规则"""
        return [
            # 完整性规则
            QualityRule(
                name="high_null_percentage",
                dimension=QualityDimension.COMPLETENESS,
                scope=AnalysisScope.COLUMN,
                severity=QualitySeverity.HIGH,
                description="检测空值比例过高的列",
                check_function="high_null_percentage",
                threshold=50.0
            ),
            QualityRule(
                name="empty_table",
                dimension=QualityDimension.COMPLETENESS,
                scope=AnalysisScope.TABLE,
                severity=QualitySeverity.CRITICAL,
                description="检测空表",
                check_function="empty_table"
            ),
            
            # 有效性规则
            QualityRule(
                name="negative_values",
                dimension=QualityDimension.VALIDITY,
                scope=AnalysisScope.COLUMN,
                severity=QualitySeverity.MEDIUM,
                description="检测应为正数列中的负值",
                check_function="negative_values_in_positive_columns",
                parameters={"positive_columns": ["id", "age", "price", "quantity", "amount"]}
            ),
            
            # 唯一性规则
            QualityRule(
                name="duplicate_values",
                dimension=QualityDimension.UNIQUENESS,
                scope=AnalysisScope.COLUMN,
                severity=QualitySeverity.HIGH,
                description="检测应唯一列中的重复值",
                check_function="duplicate_values",
                parameters={"unique_columns": ["id", "email", "phone", "ssn"]}
            ),
            
            # 一致性规则
            QualityRule(
                name="inconsistent_formats",
                dimension=QualityDimension.CONSISTENCY,
                scope=AnalysisScope.COLUMN,
                severity=QualitySeverity.MEDIUM,
                description="检测格式不一致的数据",
                check_function="inconsistent_formats"
            ),
            
            # 准确性规则
            QualityRule(
                name="outlier_detection",
                dimension=QualityDimension.ACCURACY,
                scope=AnalysisScope.COLUMN,
                severity=QualitySeverity.LOW,
                description="检测数值异常值",
                check_function="outlier_detection"
            )
        ]
    
    # 便利方法
    @classmethod
    def quick_analyze(cls, df: pl.DataFrame, quality_threshold: float = 70.0) -> QualityAnalysisResult:
        """快速质量分析"""
        config = QualityAnalysisConfig(quality_threshold=quality_threshold)
        analyzer = cls(config)
        return analyzer.analyze(df)
    
    @classmethod
    def profile_columns(cls, df: pl.DataFrame, columns: Optional[List[str]] = None) -> Dict[str, ColumnProfile]:
        """快速列轮廓分析"""
        config = QualityAnalysisConfig(
            target_columns=columns,
            analysis_dimensions=[QualityDimension.COMPLETENESS],
            enable_profiling=True
        )
        analyzer = cls(config)
        result = analyzer.analyze(df)
        return result.column_profiles
    
    @classmethod
    def detect_issues(cls, df: pl.DataFrame, dimensions: Optional[List[QualityDimension]] = None) -> List[QualityIssue]:
        """快速问题检测"""
        config = QualityAnalysisConfig(
            analysis_dimensions=dimensions or list(QualityDimension),
            enable_profiling=False
        )
        analyzer = cls(config)
        result = analyzer.analyze(df)
        return result.quality_issues