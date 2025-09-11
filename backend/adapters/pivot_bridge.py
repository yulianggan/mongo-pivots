"""
PivotBridge - 透视适配器
将多源连接结果转换为透视分析兼容格式的核心适配器
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import polars as pl
import logging

from backend.core.data_engine import DataEngine
from backend.models.api.response_models import JoinResult, JoinStatistics, QualityMetrics
from backend.utils import flatten_doc, safe_convert_value

logger = logging.getLogger(__name__)


class ARTableMetadata:
    """分析就绪表格元数据"""
    
    def __init__(
        self,
        source_info: List[Dict[str, Any]],
        join_statistics: JoinStatistics,
        quality_metrics: QualityMetrics,
        created_at: datetime,
        version: str = "1.0"
    ):
        self.source_info = source_info
        self.join_statistics = join_statistics
        self.quality_metrics = quality_metrics
        self.created_at = created_at
        self.version = version


class ARTable:
    """分析就绪表格格式 - 透视分析的标准化数据格式"""
    
    def __init__(
        self,
        metadata: ARTableMetadata,
        data: pl.DataFrame,
        pivot_config: Optional[Dict[str, Any]] = None
    ):
        self.metadata = metadata
        self.data = data
        self.pivot_config = pivot_config or self._generate_default_pivot_config()
    
    def _generate_default_pivot_config(self) -> Dict[str, Any]:
        """生成默认透视配置"""
        columns = self.data.columns
        numeric_cols = [col for col in columns if self.data[col].dtype in [pl.Int64, pl.Float64, pl.Int32, pl.Float32]]
        string_cols = [col for col in columns if self.data[col].dtype == pl.Utf8]
        
        return {
            "allowed_operations": ["sum", "mean", "count", "min", "max"],
            "recommended_dimensions": string_cols[:5],  # 推荐的维度字段
            "recommended_measures": numeric_cols[:5],   # 推荐的度量字段
            "performance_hints": [
                f"表包含 {len(self.data)} 行数据",
                f"建议使用 {len(string_cols)} 个维度字段进行分组",
                f"可用 {len(numeric_cols)} 个数值字段进行聚合"
            ],
            "limitations": [
                f"最大建议行数: {min(len(self.data), 100000)}",
                "复杂嵌套透视可能影响性能",
                "超大数据集建议使用过滤器"
            ]
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，兼容现有透视系统"""
        return {
            "metadata": {
                "source_info": self.metadata.source_info,
                "join_statistics": self.metadata.join_statistics.__dict__,
                "quality_metrics": self.metadata.quality_metrics.__dict__,
                "created_at": self.metadata.created_at.isoformat(),
                "version": self.metadata.version
            },
            "data": {
                "columns": self.data.columns,
                "rows": self.data.to_dicts(),
                "row_count": len(self.data),
                "column_types": {col: str(dtype) for col, dtype in zip(self.data.columns, self.data.dtypes)}
            },
            "pivot_config": self.pivot_config
        }


class PivotBridge:
    """透视适配器 - 连接多源数据处理和透视分析系统的桥梁"""
    
    def __init__(self):
        self.data_engine = DataEngine()
        self.logger = logging.getLogger(__name__)
    
    def convert_join_result_to_ar_table(
        self, 
        join_result: JoinResult,
        performance_mode: str = "balanced"
    ) -> ARTable:
        """
        将连接结果转换为分析就绪表格(AR Table)格式
        
        Args:
            join_result: 多源连接的结果
            performance_mode: 性能模式 ('fast', 'accurate', 'balanced')
            
        Returns:
            ARTable: 标准化的分析就绪表格
        """
        self.logger.info(f"Converting join result to AR Table, mode: {performance_mode}")
        
        try:
            # 1. 提取Polars DataFrame
            df = join_result.data
            
            # 2. 根据性能模式进行优化
            optimized_df = self._optimize_dataframe(df, performance_mode)
            
            # 3. 创建元数据
            metadata = ARTableMetadata(
                source_info=join_result.source_info,
                join_statistics=join_result.join_statistics,
                quality_metrics=join_result.quality_metrics,
                created_at=join_result.created_at
            )
            
            # 4. 生成AR Table
            ar_table = ARTable(metadata, optimized_df)
            
            self.logger.info(f"AR Table created successfully: {len(optimized_df)} rows, {len(optimized_df.columns)} columns")
            return ar_table
            
        except Exception as e:
            self.logger.error(f"Failed to convert join result to AR Table: {e}")
            raise
    
    def _optimize_dataframe(self, df: pl.DataFrame, mode: str) -> pl.DataFrame:
        """根据性能模式优化DataFrame"""
        if mode == "fast":
            # 快速模式：数据采样
            if len(df) > 50000:
                return df.sample(n=50000)
        elif mode == "accurate":
            # 精确模式：保持所有数据，进行类型优化
            return self._optimize_types(df)
        else:
            # 平衡模式：适度优化
            optimized = self._optimize_types(df)
            if len(optimized) > 100000:
                return optimized.slice(0, 100000)
            return optimized
        
        return df
    
    def _optimize_types(self, df: pl.DataFrame) -> pl.DataFrame:
        """优化数据类型以提高性能"""
        optimized = df
        
        for col in df.columns:
            dtype = df[col].dtype
            
            # 优化整数类型
            if dtype == pl.Int64:
                max_val = df[col].max()
                min_val = df[col].min()
                if max_val < 2**31 and min_val > -2**31:
                    optimized = optimized.with_columns(optimized[col].cast(pl.Int32))
            
            # 优化字符串类型
            elif dtype == pl.Utf8:
                unique_ratio = df[col].n_unique() / len(df)
                if unique_ratio < 0.1:  # 低基数字符串转换为分类
                    optimized = optimized.with_columns(optimized[col].cast(pl.Categorical))
        
        return optimized
    
    def convert_to_pivot_format(self, ar_table: ARTable, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        将AR Table转换为现有透视系统兼容的格式
        
        Args:
            ar_table: 分析就绪表格
            limit: 返回数据的行数限制
            
        Returns:
            Dict: 透视系统兼容的数据格式
        """
        self.logger.info("Converting AR Table to pivot format")
        
        try:
            df = ar_table.data
            
            # 应用行数限制
            if limit:
                df = df.limit(limit)
            
            # 使用现有的数据引擎进行清理和优化
            cleaned_df = self.data_engine.clean_dataframe(df)
            
            # 转换为记录格式（兼容现有透视系统）
            records = []
            for row in cleaned_df.to_dicts():
                # 应用现有的扁平化和安全转换逻辑
                flattened = flatten_doc(row)
                safe_record = {k: safe_convert_value(v) for k, v in flattened.items()}
                records.append(safe_record)
            
            # 生成字段类型信息
            fields = self._generate_field_types(cleaned_df)
            
            return {
                "rows": records,
                "fields": fields,
                "count": len(records),
                "total_count": len(ar_table.data),  # 原始总数
                "metadata": ar_table.metadata.__dict__,
                "pivot_config": ar_table.pivot_config
            }
            
        except Exception as e:
            self.logger.error(f"Failed to convert AR Table to pivot format: {e}")
            raise
    
    def _generate_field_types(self, df: pl.DataFrame) -> Dict[str, str]:
        """生成字段类型映射，兼容现有透视系统"""
        field_types = {}
        
        for col in df.columns:
            dtype = df[col].dtype
            
            if dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
                field_types[col] = "number"
            elif dtype in [pl.Date, pl.Datetime]:
                field_types[col] = "date"
            elif dtype == pl.Boolean:
                field_types[col] = "boolean"
            else:
                field_types[col] = "string"
        
        return field_types
    
    def get_pivot_preview(
        self, 
        ar_table: ARTable, 
        preview_rows: int = 100
    ) -> Dict[str, Any]:
        """
        获取透视预览数据
        
        Args:
            ar_table: 分析就绪表格
            preview_rows: 预览行数
            
        Returns:
            Dict: 预览数据和元信息
        """
        self.logger.info(f"Generating pivot preview for {preview_rows} rows")
        
        preview_data = self.convert_to_pivot_format(ar_table, limit=preview_rows)
        
        return {
            "preview": preview_data["rows"],
            "fields": preview_data["fields"],
            "sample_size": len(preview_data["rows"]),
            "total_size": preview_data["total_count"],
            "recommendations": ar_table.pivot_config["recommended_dimensions"],
            "measures": ar_table.pivot_config["recommended_measures"],
            "performance_hints": ar_table.pivot_config["performance_hints"]
        }
    
    def validate_ar_table(self, ar_table: ARTable) -> Dict[str, Any]:
        """
        验证AR Table的有效性和性能特征
        
        Args:
            ar_table: 分析就绪表格
            
        Returns:
            Dict: 验证结果和建议
        """
        validation_result = {
            "valid": True,
            "warnings": [],
            "recommendations": [],
            "performance_score": 100
        }
        
        df = ar_table.data
        
        # 检查数据大小
        row_count = len(df)
        if row_count > 1000000:
            validation_result["warnings"].append("数据集很大，透视操作可能较慢")
            validation_result["performance_score"] -= 20
            validation_result["recommendations"].append("考虑使用数据过滤或采样")
        
        # 检查字段数量
        col_count = len(df.columns)
        if col_count > 50:
            validation_result["warnings"].append("字段数量较多，建议选择关键字段进行分析")
            validation_result["performance_score"] -= 10
        
        # 检查内存使用
        estimated_memory_mb = (row_count * col_count * 8) / (1024 * 1024)  # 估算
        if estimated_memory_mb > 500:
            validation_result["warnings"].append(f"预估内存使用: {estimated_memory_mb:.1f}MB")
            validation_result["performance_score"] -= 15
        
        # 检查数据质量
        quality_metrics = ar_table.metadata.quality_metrics
        if quality_metrics.completeness < 0.8:
            validation_result["warnings"].append("数据完整性较低，可能影响分析结果")
            validation_result["recommendations"].append("考虑处理缺失值")
        
        return validation_result