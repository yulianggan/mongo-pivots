"""
NullProcessor - 空值处理器
支持多种空值填充策略、质量跟踪和智能空值检测，为数据连接提供高质量的数据处理
"""
import polars as pl
import numpy as np
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import logging
import time
import asyncio
import statistics
from collections import defaultdict

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


class NullFillStrategy(Enum):
    """空值填充策略枚举"""
    KEEP = "keep"                    # 保持空值不变
    DROP = "drop"                    # 删除含空值的行
    FORWARD_FILL = "forward"         # 前向填充
    BACKWARD_FILL = "backward"       # 后向填充
    MEAN = "mean"                    # 均值填充
    MEDIAN = "median"                # 中位数填充
    MODE = "mode"                    # 众数填充
    INTERPOLATE = "interpolate"      # 插值填充
    CONSTANT = "constant"            # 常数填充
    CUSTOM = "custom"                # 自定义填充


class NullDetectionMethod(Enum):
    """空值检测方法枚举"""
    STANDARD = "standard"            # 标准空值检测 (None, NaN)
    EXTENDED = "extended"            # 扩展检测 (包括空字符串, 0等)
    PATTERN = "pattern"              # 基于模式的检测
    STATISTICAL = "statistical"     # 统计学异常值检测
    CUSTOM = "custom"                # 自定义检测规则


class QualityThreshold(Enum):
    """质量阈值等级枚举"""
    STRICT = 0.95     # 严格模式 - 95%完整性
    STANDARD = 0.8    # 标准模式 - 80%完整性
    LENIENT = 0.6     # 宽松模式 - 60%完整性
    CUSTOM = 0.0      # 自定义阈值


@dataclass
class NullProcessingConfig:
    """空值处理配置"""
    target_columns: List[str]                           # 目标处理列
    fill_strategy: NullFillStrategy = NullFillStrategy.FORWARD_FILL  # 填充策略
    detection_method: NullDetectionMethod = NullDetectionMethod.STANDARD  # 检测方法
    quality_threshold: float = 0.8                     # 质量阈值
    constant_fill_value: Any = 0                       # 常数填充值
    custom_fill_function: Optional[Callable] = None    # 自定义填充函数
    custom_detection_rules: Optional[List[str]] = None # 自定义检测规则
    enable_quality_tracking: bool = True               # 启用质量跟踪
    interpolation_method: str = "linear"               # 插值方法
    handle_infinite: bool = True                       # 处理无穷值
    handle_outliers: bool = False                      # 处理异常值
    outlier_threshold: float = 3.0                     # 异常值阈值(标准差倍数)
    preserve_data_types: bool = True                   # 保持数据类型
    
    def __post_init__(self):
        """后处理初始化，验证配置"""
        if not self.target_columns:
            raise ValueError("target_columns cannot be empty")
        
        if self.fill_strategy == NullFillStrategy.CONSTANT and self.constant_fill_value is None:
            raise ValueError("constant_fill_value is required for CONSTANT fill strategy")
        
        if self.fill_strategy == NullFillStrategy.CUSTOM and self.custom_fill_function is None:
            raise ValueError("custom_fill_function is required for CUSTOM fill strategy")
        
        if not 0 <= self.quality_threshold <= 1:
            raise ValueError("quality_threshold must be between 0 and 1")


@dataclass
class NullProcessingResult:
    """空值处理结果"""
    processed_data: pl.DataFrame                        # 处理后的数据
    processing_statistics: Dict[str, Any]              # 处理统计信息
    quality_metrics: Dict[str, float]                  # 质量指标
    execution_time: float                              # 执行时间
    memory_usage_mb: float                             # 内存使用量
    warnings: List[str]                                # 警告信息
    null_distribution: Dict[str, Dict[str, int]]       # 空值分布统计
    
    @property
    def data_completeness(self) -> float:
        """数据完整性"""
        return self.quality_metrics.get('data_completeness', 0.0)
    
    @property
    def fill_success_rate(self) -> float:
        """填充成功率"""
        return self.quality_metrics.get('fill_success_rate', 0.0)
    
    @property
    def outlier_detection_rate(self) -> float:
        """异常值检测率"""
        return self.quality_metrics.get('outlier_detection_rate', 0.0)
    
    @property
    def total_nulls_processed(self) -> int:
        """处理的空值总数"""
        return self.processing_statistics.get('total_nulls_processed', 0)


class NullDetector:
    """空值检测器"""
    
    def __init__(self, config: NullProcessingConfig):
        """初始化空值检测器
        
        Args:
            config: 空值处理配置
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def detect_nulls(self, df: pl.DataFrame) -> Dict[str, pl.DataFrame]:
        """检测空值
        
        Args:
            df: 输入数据框
            
        Returns:
            按列分组的空值检测结果
        """
        with memory_guard.memory_guard("detect_nulls"):
            self.logger.info(f"开始空值检测，检测方法: {self.config.detection_method.value}")
            
            detection_results = {}
            
            for col in self.config.target_columns:
                if col not in df.columns:
                    self.logger.warning(f"目标列 '{col}' 不存在，跳过检测")
                    continue
                
                if self.config.detection_method == NullDetectionMethod.STANDARD:
                    null_mask = self._detect_standard_nulls(df, col)
                elif self.config.detection_method == NullDetectionMethod.EXTENDED:
                    null_mask = self._detect_extended_nulls(df, col)
                elif self.config.detection_method == NullDetectionMethod.PATTERN:
                    null_mask = self._detect_pattern_nulls(df, col)
                elif self.config.detection_method == NullDetectionMethod.STATISTICAL:
                    null_mask = self._detect_statistical_nulls(df, col)
                elif self.config.detection_method == NullDetectionMethod.CUSTOM:
                    null_mask = self._detect_custom_nulls(df, col)
                else:
                    null_mask = self._detect_standard_nulls(df, col)
                
                # 生成包含空值位置的DataFrame
                detection_results[col] = df.with_columns([
                    null_mask.alias(f"{col}_is_null")
                ]).filter(pl.col(f"{col}_is_null"))
            
            self.logger.info(f"空值检测完成，检测到 {len(detection_results)} 列有空值")
            return detection_results
    
    def _detect_standard_nulls(self, df: pl.DataFrame, col: str) -> pl.Expr:
        """检测标准空值 (None, NaN)"""
        null_condition = pl.col(col).is_null()
        
        # 对于数值列，同时检测NaN
        if df[col].dtype in [pl.Float32, pl.Float64]:
            null_condition = null_condition | pl.col(col).is_nan()
        
        # 处理无穷值
        if self.config.handle_infinite and df[col].dtype in [pl.Float32, pl.Float64]:
            null_condition = null_condition | pl.col(col).is_infinite()
        
        return null_condition
    
    def _detect_extended_nulls(self, df: pl.DataFrame, col: str) -> pl.Expr:
        """检测扩展空值 (包括空字符串、零值等)"""
        null_condition = self._detect_standard_nulls(df, col)
        
        # 字符串列检测空字符串和空白字符
        if df[col].dtype == pl.Utf8:
            null_condition = (
                null_condition | 
                (pl.col(col) == "") | 
                (pl.col(col).str.strip_chars() == "")
            )
        
        # 数值列检测零值(可选)
        elif df[col].dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                               pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                               pl.Float32, pl.Float64]:
            # 通常不将0视为空值，除非特别配置
            pass
        
        return null_condition
    
    def _detect_pattern_nulls(self, df: pl.DataFrame, col: str) -> pl.Expr:
        """基于模式检测空值"""
        null_condition = self._detect_standard_nulls(df, col)
        
        # 如果有自定义检测规则
        if self.config.custom_detection_rules:
            for pattern in self.config.custom_detection_rules:
                if df[col].dtype == pl.Utf8:
                    # 字符串模式匹配
                    null_condition = null_condition | pl.col(col).str.contains(pattern)
        
        return null_condition
    
    def _detect_statistical_nulls(self, df: pl.DataFrame, col: str) -> pl.Expr:
        """基于统计学方法检测空值（异常值）"""
        null_condition = self._detect_standard_nulls(df, col)
        
        # 只对数值列进行异常值检测
        if (self.config.handle_outliers and 
            df[col].dtype in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]):
            
            # 计算统计量
            mean_val = df[col].mean()
            std_val = df[col].std()
            
            if mean_val is not None and std_val is not None and std_val > 0:
                threshold = self.config.outlier_threshold
                
                # 检测异常值（超出均值 ± threshold*标准差的值）
                outlier_condition = (
                    (pl.col(col) < (mean_val - threshold * std_val)) |
                    (pl.col(col) > (mean_val + threshold * std_val))
                )
                
                null_condition = null_condition | outlier_condition
        
        return null_condition
    
    def _detect_custom_nulls(self, df: pl.DataFrame, col: str) -> pl.Expr:
        """自定义空值检测"""
        # 默认使用标准检测，可以通过配置扩展
        return self._detect_standard_nulls(df, col)
    
    def get_null_statistics(self, df: pl.DataFrame) -> Dict[str, Dict[str, Any]]:
        """获取空值统计信息"""
        statistics = {}
        
        for col in self.config.target_columns:
            if col not in df.columns:
                continue
            
            col_stats = {
                'total_rows': len(df),
                'null_count': 0,
                'null_percentage': 0.0,
                'data_type': str(df[col].dtype)
            }
            
            # 计算空值数量
            null_mask = self._detect_standard_nulls(df, col)
            null_count = df.filter(null_mask).height
            
            col_stats['null_count'] = null_count
            col_stats['null_percentage'] = (null_count / len(df) * 100) if len(df) > 0 else 0
            
            statistics[col] = col_stats
        
        return statistics


class FillStrategies:
    """空值填充策略集合"""
    
    def __init__(self, config: NullProcessingConfig):
        """初始化填充策略
        
        Args:
            config: 空值处理配置
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def apply_fill_strategy(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """应用填充策略
        
        Args:
            df: 输入数据框
            col: 目标列名
            
        Returns:
            填充后的数据框
        """
        strategy = self.config.fill_strategy
        
        if strategy == NullFillStrategy.KEEP:
            return df
        elif strategy == NullFillStrategy.DROP:
            return self._drop_nulls(df, col)
        elif strategy == NullFillStrategy.FORWARD_FILL:
            return self._forward_fill(df, col)
        elif strategy == NullFillStrategy.BACKWARD_FILL:
            return self._backward_fill(df, col)
        elif strategy == NullFillStrategy.MEAN:
            return self._mean_fill(df, col)
        elif strategy == NullFillStrategy.MEDIAN:
            return self._median_fill(df, col)
        elif strategy == NullFillStrategy.MODE:
            return self._mode_fill(df, col)
        elif strategy == NullFillStrategy.INTERPOLATE:
            return self._interpolate_fill(df, col)
        elif strategy == NullFillStrategy.CONSTANT:
            return self._constant_fill(df, col)
        elif strategy == NullFillStrategy.CUSTOM:
            return self._custom_fill(df, col)
        else:
            self.logger.warning(f"未知填充策略: {strategy}，使用前向填充")
            return self._forward_fill(df, col)
    
    def _drop_nulls(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """删除含空值的行"""
        return df.filter(pl.col(col).is_not_null())
    
    def _forward_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """前向填充"""
        return df.with_columns([
            pl.col(col).fill_null(strategy="forward").alias(col)
        ])
    
    def _backward_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """后向填充"""
        return df.with_columns([
            pl.col(col).fill_null(strategy="backward").alias(col)
        ])
    
    def _mean_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """均值填充"""
        if df[col].dtype not in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]:
            self.logger.warning(f"列 '{col}' 不是数值类型，无法使用均值填充")
            return df
        
        mean_value = df[col].mean()
        if mean_value is None:
            self.logger.warning(f"列 '{col}' 无法计算均值，保持空值")
            return df
        
        return df.with_columns([
            pl.col(col).fill_null(mean_value).alias(col)
        ])
    
    def _median_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """中位数填充"""
        if df[col].dtype not in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]:
            self.logger.warning(f"列 '{col}' 不是数值类型，无法使用中位数填充")
            return df
        
        median_value = df[col].median()
        if median_value is None:
            self.logger.warning(f"列 '{col}' 无法计算中位数，保持空值")
            return df
        
        return df.with_columns([
            pl.col(col).fill_null(median_value).alias(col)
        ])
    
    def _mode_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """众数填充"""
        try:
            # 计算众数（最频繁的值）
            mode_result = df[col].value_counts().sort('count', descending=True).head(1)
            
            if len(mode_result) == 0:
                self.logger.warning(f"列 '{col}' 无法计算众数，保持空值")
                return df
            
            mode_value = mode_result[col][0]
            
            return df.with_columns([
                pl.col(col).fill_null(mode_value).alias(col)
            ])
        except Exception as e:
            self.logger.warning(f"列 '{col}' 众数填充失败: {e}，保持空值")
            return df
    
    def _interpolate_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """插值填充"""
        if df[col].dtype not in [pl.Float32, pl.Float64, pl.Int32, pl.Int64]:
            self.logger.warning(f"列 '{col}' 不是数值类型，无法使用插值填充")
            return df
        
        # 简单的线性插值（使用前后值的平均）
        return df.with_columns([
            pl.col(col).interpolate(method="linear").alias(col)
        ])
    
    def _constant_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """常数填充"""
        fill_value = self.config.constant_fill_value
        
        # 类型转换检查
        if self.config.preserve_data_types:
            try:
                # 尝试将填充值转换为列的数据类型
                if df[col].dtype == pl.Int32:
                    fill_value = int(fill_value) if fill_value is not None else 0
                elif df[col].dtype == pl.Float64:
                    fill_value = float(fill_value) if fill_value is not None else 0.0
                elif df[col].dtype == pl.Utf8:
                    fill_value = str(fill_value) if fill_value is not None else ""
            except (ValueError, TypeError) as e:
                self.logger.warning(f"填充值类型转换失败: {e}，使用原值")
        
        return df.with_columns([
            pl.col(col).fill_null(fill_value).alias(col)
        ])
    
    def _custom_fill(self, df: pl.DataFrame, col: str) -> pl.DataFrame:
        """自定义填充"""
        if self.config.custom_fill_function is None:
            self.logger.warning("自定义填充函数未设置，使用前向填充")
            return self._forward_fill(df, col)
        
        try:
            # 应用自定义函数
            return self.config.custom_fill_function(df, col)
        except Exception as e:
            self.logger.error(f"自定义填充函数执行失败: {e}，使用前向填充")
            return self._forward_fill(df, col)


class QualityTracker:
    """质量跟踪器"""
    
    def __init__(self, config: NullProcessingConfig):
        """初始化质量跟踪器
        
        Args:
            config: 空值处理配置
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def track_processing_quality(
        self, 
        original_df: pl.DataFrame, 
        processed_df: pl.DataFrame
    ) -> Dict[str, float]:
        """跟踪处理质量
        
        Args:
            original_df: 原始数据框
            processed_df: 处理后数据框
            
        Returns:
            质量指标字典
        """
        with memory_guard.memory_guard("track_quality"):
            quality_metrics = {}
            
            # 数据完整性
            original_total_cells = len(original_df) * len(self.config.target_columns)
            processed_total_cells = len(processed_df) * len(self.config.target_columns)
            
            if original_total_cells > 0:
                # 计算原始空值数量
                original_nulls = self._count_total_nulls(original_df)
                processed_nulls = self._count_total_nulls(processed_df)
                
                # 数据完整性 = 1 - (处理后空值 / 总cells)
                data_completeness = 1 - (processed_nulls / processed_total_cells) if processed_total_cells > 0 else 0
                quality_metrics['data_completeness'] = data_completeness
                
                # 填充成功率 = (原始空值 - 处理后空值) / 原始空值
                fill_success_rate = ((original_nulls - processed_nulls) / original_nulls) if original_nulls > 0 else 1.0
                quality_metrics['fill_success_rate'] = max(0, fill_success_rate)
                
                # 数据保持率 = 处理后行数 / 原始行数
                data_retention_rate = len(processed_df) / len(original_df) if len(original_df) > 0 else 1.0
                quality_metrics['data_retention_rate'] = data_retention_rate
                
                # 质量通过率 = 数据完整性是否达到阈值
                quality_pass = 1.0 if data_completeness >= self.config.quality_threshold else 0.0
                quality_metrics['quality_threshold_passed'] = quality_pass
                
                # 异常值检测率（如果启用了异常值处理）
                if self.config.handle_outliers:
                    outlier_detection_rate = self._calculate_outlier_detection_rate(original_df, processed_df)
                    quality_metrics['outlier_detection_rate'] = outlier_detection_rate
                
            else:
                # 空数据的默认质量指标
                quality_metrics.update({
                    'data_completeness': 1.0,
                    'fill_success_rate': 1.0,
                    'data_retention_rate': 1.0,
                    'quality_threshold_passed': 1.0,
                    'outlier_detection_rate': 0.0
                })
            
            return quality_metrics
    
    def _count_total_nulls(self, df: pl.DataFrame) -> int:
        """计算总空值数量"""
        total_nulls = 0
        
        for col in self.config.target_columns:
            if col in df.columns:
                null_count = df[col].null_count()
                total_nulls += null_count
        
        return total_nulls
    
    def _calculate_outlier_detection_rate(
        self, 
        original_df: pl.DataFrame, 
        processed_df: pl.DataFrame
    ) -> float:
        """计算异常值检测率"""
        # 简化实现：比较处理前后的数据分布变化
        if len(original_df) == 0 or len(processed_df) == 0:
            return 0.0
        
        # 计算行数变化（如果异常值被移除）
        row_change_rate = abs(len(processed_df) - len(original_df)) / len(original_df)
        
        # 异常值检测率基于数据变化程度
        return min(row_change_rate, 1.0)
    
    def generate_quality_report(
        self, 
        quality_metrics: Dict[str, float],
        processing_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成质量报告
        
        Args:
            quality_metrics: 质量指标
            processing_stats: 处理统计
            
        Returns:
            质量报告
        """
        report = {
            "quality_summary": {
                "overall_score": self._calculate_overall_score(quality_metrics),
                "pass_threshold": quality_metrics.get('quality_threshold_passed', 0.0) == 1.0,
                "completeness_level": self._categorize_completeness(quality_metrics.get('data_completeness', 0)),
            },
            "detailed_metrics": quality_metrics,
            "processing_summary": processing_stats,
            "recommendations": self._generate_recommendations(quality_metrics, processing_stats)
        }
        
        return report
    
    def _calculate_overall_score(self, quality_metrics: Dict[str, float]) -> float:
        """计算综合质量分数"""
        weights = {
            'data_completeness': 0.4,
            'fill_success_rate': 0.3,
            'data_retention_rate': 0.2,
            'quality_threshold_passed': 0.1
        }
        
        weighted_score = 0.0
        total_weight = 0.0
        
        for metric, weight in weights.items():
            if metric in quality_metrics:
                weighted_score += quality_metrics[metric] * weight
                total_weight += weight
        
        return weighted_score / total_weight if total_weight > 0 else 0.0
    
    def _categorize_completeness(self, completeness: float) -> str:
        """分类完整性等级"""
        if completeness >= 0.95:
            return "Excellent"
        elif completeness >= 0.8:
            return "Good"
        elif completeness >= 0.6:
            return "Fair"
        else:
            return "Poor"
    
    def _generate_recommendations(
        self, 
        quality_metrics: Dict[str, float],
        processing_stats: Dict[str, Any]
    ) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        completeness = quality_metrics.get('data_completeness', 0)
        fill_success = quality_metrics.get('fill_success_rate', 0)
        retention = quality_metrics.get('data_retention_rate', 0)
        
        if completeness < self.config.quality_threshold:
            recommendations.append(
                f"数据完整性({completeness:.1%})低于阈值({self.config.quality_threshold:.1%})，"
                "建议检查填充策略或调整质量阈值"
            )
        
        if fill_success < 0.7:
            recommendations.append(
                f"填充成功率({fill_success:.1%})较低，建议尝试其他填充策略"
            )
        
        if retention < 0.9:
            recommendations.append(
                f"数据保持率({retention:.1%})较低，可能删除了过多数据"
            )
        
        if not recommendations:
            recommendations.append("数据质量良好，无需特殊改进")
        
        return recommendations


class NullProcessor:
    """空值处理器主类"""
    
    def __init__(self, config: Optional[NullProcessingConfig] = None):
        """初始化空值处理器
        
        Args:
            config: 空值处理配置，如果未提供则使用默认配置
        """
        self.config = config or NullProcessingConfig(target_columns=[])
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化组件
        self.null_detector = NullDetector(self.config)
        self.fill_strategies = FillStrategies(self.config)
        self.quality_tracker = QualityTracker(self.config)
        
        # 执行历史
        self._execution_history: List[Dict[str, Any]] = []
    
    def process(self, df: pl.DataFrame) -> NullProcessingResult:
        """执行空值处理
        
        Args:
            df: 输入数据框
            
        Returns:
            空值处理结果
        """
        start_time = time.time()
        start_memory = memory_guard.get_memory_stats().rss_bytes / (1024 * 1024)
        warnings = []
        
        try:
            self.logger.info(f"开始空值处理: {len(df)} 行, {len(df.columns)} 列")
            
            # 验证配置
            self._validate_config(df)
            
            # 1. 空值检测
            null_detection_results = self.null_detector.detect_nulls(df)
            null_statistics = self.null_detector.get_null_statistics(df)
            
            # 2. 应用填充策略
            processed_df = df.clone()
            
            for col in self.config.target_columns:
                if col not in df.columns:
                    continue
                
                try:
                    processed_df = self.fill_strategies.apply_fill_strategy(processed_df, col)
                except Exception as e:
                    warning_msg = f"列 '{col}' 处理失败: {e}"
                    warnings.append(warning_msg)
                    self.logger.warning(warning_msg)
            
            # 3. 质量跟踪
            if self.config.enable_quality_tracking:
                quality_metrics = self.quality_tracker.track_processing_quality(df, processed_df)
            else:
                quality_metrics = {"data_completeness": 1.0, "fill_success_rate": 1.0}
            
            # 4. 生成统计信息
            end_time = time.time()
            end_memory = memory_guard.get_memory_stats().rss_bytes / (1024 * 1024)
            
            processing_statistics = self._generate_processing_statistics(
                len(df), len(processed_df), null_statistics
            )
            
            # 5. 空值分布统计
            null_distribution = self._generate_null_distribution(null_detection_results)
            
            result = NullProcessingResult(
                processed_data=processed_df,
                processing_statistics=processing_statistics,
                quality_metrics=quality_metrics,
                execution_time=end_time - start_time,
                memory_usage_mb=end_memory - start_memory,
                warnings=warnings,
                null_distribution=null_distribution
            )
            
            # 记录执行历史
            self._record_execution(result)
            
            self.logger.info(
                f"空值处理完成: 原始 {len(df)} 行 -> 处理后 {len(processed_df)} 行, "
                f"数据完整性 {result.data_completeness:.2%}, 耗时 {result.execution_time:.2f}s"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"空值处理失败: {e}")
            raise
    
    async def process_async(self, df: pl.DataFrame) -> NullProcessingResult:
        """异步执行空值处理
        
        Args:
            df: 输入数据框
            
        Returns:
            空值处理结果
        """
        return await asyncio.get_event_loop().run_in_executor(None, self.process, df)
    
    def _validate_config(self, df: pl.DataFrame) -> None:
        """验证配置"""
        for col in self.config.target_columns:
            if col not in df.columns:
                raise ValueError(f"目标列 '{col}' 不存在于数据中")
    
    def _generate_processing_statistics(
        self, 
        original_count: int, 
        processed_count: int,
        null_statistics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生成处理统计信息"""
        total_nulls_found = sum(
            stats.get('null_count', 0) for stats in null_statistics.values()
        )
        
        return {
            "original_rows": original_count,
            "processed_rows": processed_count,
            "rows_removed": max(0, original_count - processed_count),
            "total_nulls_processed": total_nulls_found,
            "columns_processed": len(self.config.target_columns),
            "processing_config": {
                "fill_strategy": self.config.fill_strategy.value,
                "detection_method": self.config.detection_method.value,
                "quality_threshold": self.config.quality_threshold
            },
            "null_statistics_by_column": null_statistics
        }
    
    def _generate_null_distribution(
        self, 
        null_detection_results: Dict[str, pl.DataFrame]
    ) -> Dict[str, Dict[str, int]]:
        """生成空值分布统计"""
        distribution = {}
        
        for col, null_df in null_detection_results.items():
            col_distribution = {
                "total_nulls": len(null_df),
                "null_positions": list(null_df.select(pl.int_range(len(null_df))).to_series()) if len(null_df) > 0 else []
            }
            distribution[col] = col_distribution
        
        return distribution
    
    def _record_execution(self, result: NullProcessingResult) -> None:
        """记录执行历史"""
        execution_record = {
            "timestamp": time.time(),
            "original_rows": result.processing_statistics["original_rows"],
            "processed_rows": result.processing_statistics["processed_rows"],
            "execution_time": result.execution_time,
            "memory_usage_mb": result.memory_usage_mb,
            "data_completeness": result.data_completeness,
            "fill_success_rate": result.fill_success_rate
        }
        
        self._execution_history.append(execution_record)
        
        # 保留最近100次执行记录
        if len(self._execution_history) > 100:
            self._execution_history = self._execution_history[-100:]
    
    def get_execution_history(self) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self._execution_history.copy()
    
    def update_config(self, config: NullProcessingConfig) -> None:
        """更新配置
        
        Args:
            config: 新的空值处理配置
        """
        self.config = config
        self.null_detector = NullDetector(config)
        self.fill_strategies = FillStrategies(config)
        self.quality_tracker = QualityTracker(config)
        self.logger.info("空值处理器配置已更新")


# 便捷函数
def quick_null_process(
    df: pl.DataFrame,
    target_columns: List[str],
    fill_strategy: NullFillStrategy = NullFillStrategy.FORWARD_FILL,
    **kwargs
) -> pl.DataFrame:
    """快速空值处理便捷函数
    
    Args:
        df: 输入数据框
        target_columns: 目标处理列
        fill_strategy: 填充策略
        **kwargs: 其他配置参数
        
    Returns:
        处理后的数据框
    """
    config = NullProcessingConfig(
        target_columns=target_columns,
        fill_strategy=fill_strategy,
        **kwargs
    )
    processor = NullProcessor(config)
    result = processor.process(df)
    return result.processed_data


async def process_nulls_async(
    df: pl.DataFrame,
    target_columns: List[str],
    fill_strategy: NullFillStrategy = NullFillStrategy.FORWARD_FILL,
    **kwargs
) -> NullProcessingResult:
    """异步空值处理便捷函数
    
    Args:
        df: 输入数据框
        target_columns: 目标处理列
        fill_strategy: 填充策略
        **kwargs: 其他配置参数
        
    Returns:
        空值处理结果
    """
    config = NullProcessingConfig(
        target_columns=target_columns,
        fill_strategy=fill_strategy,
        **kwargs
    )
    processor = NullProcessor(config)
    return await processor.process_async(df)


def create_null_processing_config(
    target_columns: List[str],
    fill_strategy: NullFillStrategy = NullFillStrategy.FORWARD_FILL,
    **kwargs
) -> NullProcessingConfig:
    """创建空值处理配置的便捷函数
    
    Args:
        target_columns: 目标处理列
        fill_strategy: 填充策略
        **kwargs: 其他配置参数
        
    Returns:
        空值处理配置对象
    """
    return NullProcessingConfig(
        target_columns=target_columns,
        fill_strategy=fill_strategy,
        **kwargs
    )