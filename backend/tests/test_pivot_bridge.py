"""
PivotBridge适配器测试
"""

import pytest
import polars as pl
from datetime import datetime
from unittest.mock import Mock, patch

from backend.adapters.pivot_bridge import PivotBridge, ARTable, ARTableMetadata
from backend.models.api.response_models import JoinResult, JoinStatistics, QualityMetrics


@pytest.fixture
def sample_join_result():
    """创建示例连接结果"""
    # 创建示例数据
    df = pl.DataFrame({
        "customer_id": ["C001", "C002", "C003", "C001"],
        "customer_name": ["张三", "李四", "王五", "张三"],
        "order_id": ["O001", "O002", "O003", "O004"],
        "order_amount": [299.99, 159.50, 89.99, 199.00],
        "order_date": ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"],
        "city": ["北京", "上海", "广州", "北京"]
    })
    
    # 创建统计信息
    join_stats = JoinStatistics(
        total_records=4,
        matched_records=4,
        unmatched_records=0,
        execution_time_ms=1500,
        memory_peak_mb=12.5
    )
    
    # 创建质量指标
    quality_metrics = QualityMetrics(
        completeness=0.95,
        accuracy=0.90,
        consistency=0.92,
        uniqueness=0.88
    )
    
    return JoinResult(
        result_id="test_result_001",
        data=df,
        source_info=[
            {"name": "customers", "type": "mongodb", "records": 100},
            {"name": "orders", "type": "csv", "records": 150}
        ],
        join_statistics=join_stats,
        quality_metrics=quality_metrics,
        created_at=datetime(2023, 10, 15, 14, 30, 0)
    )


@pytest.fixture
def pivot_bridge():
    """创建PivotBridge实例"""
    return PivotBridge()


class TestARTableMetadata:
    """ARTable元数据测试"""
    
    def test_ar_table_metadata_creation(self):
        """测试ARTable元数据创建"""
        source_info = [{"name": "test", "type": "csv"}]
        join_stats = Mock()
        quality_metrics = Mock()
        created_at = datetime.now()
        
        metadata = ARTableMetadata(
            source_info=source_info,
            join_statistics=join_stats,
            quality_metrics=quality_metrics,
            created_at=created_at
        )
        
        assert metadata.source_info == source_info
        assert metadata.join_statistics == join_stats
        assert metadata.quality_metrics == quality_metrics
        assert metadata.created_at == created_at
        assert metadata.version == "1.0"


class TestARTable:
    """ARTable测试"""
    
    def test_ar_table_creation(self, sample_join_result):
        """测试ARTable创建"""
        metadata = ARTableMetadata(
            source_info=sample_join_result.source_info,
            join_statistics=sample_join_result.join_statistics,
            quality_metrics=sample_join_result.quality_metrics,
            created_at=sample_join_result.created_at
        )
        
        ar_table = ARTable(metadata, sample_join_result.data)
        
        assert ar_table.metadata == metadata
        assert ar_table.data.equals(sample_join_result.data)
        assert "allowed_operations" in ar_table.pivot_config
        assert "recommended_dimensions" in ar_table.pivot_config
        assert "recommended_measures" in ar_table.pivot_config
    
    def test_default_pivot_config_generation(self, sample_join_result):
        """测试默认透视配置生成"""
        metadata = Mock()
        ar_table = ARTable(metadata, sample_join_result.data)
        
        config = ar_table.pivot_config
        
        # 检查数值字段推荐
        assert "order_amount" in config["recommended_measures"]
        
        # 检查字符串字段推荐
        string_dims = config["recommended_dimensions"]
        assert any(col in string_dims for col in ["customer_name", "city"])
        
        # 检查操作类型
        assert "sum" in config["allowed_operations"]
        assert "mean" in config["allowed_operations"]
    
    def test_to_dict_conversion(self, sample_join_result):
        """测试转换为字典格式"""
        metadata = ARTableMetadata(
            source_info=sample_join_result.source_info,
            join_statistics=sample_join_result.join_statistics,
            quality_metrics=sample_join_result.quality_metrics,
            created_at=sample_join_result.created_at
        )
        
        ar_table = ARTable(metadata, sample_join_result.data)
        result_dict = ar_table.to_dict()
        
        assert "metadata" in result_dict
        assert "data" in result_dict
        assert "pivot_config" in result_dict
        
        # 检查数据结构
        data_section = result_dict["data"]
        assert "columns" in data_section
        assert "rows" in data_section
        assert "row_count" in data_section
        assert data_section["row_count"] == 4


class TestPivotBridge:
    """PivotBridge核心功能测试"""
    
    def test_pivot_bridge_initialization(self):
        """测试PivotBridge初始化"""
        bridge = PivotBridge()
        assert bridge.data_engine is not None
        assert bridge.logger is not None
    
    def test_convert_join_result_to_ar_table(self, pivot_bridge, sample_join_result):
        """测试连接结果转AR Table"""
        ar_table = pivot_bridge.convert_join_result_to_ar_table(sample_join_result)
        
        assert isinstance(ar_table, ARTable)
        assert ar_table.data.equals(sample_join_result.data)
        assert ar_table.metadata.source_info == sample_join_result.source_info
        assert len(ar_table.pivot_config["recommended_measures"]) > 0
    
    def test_performance_modes(self, pivot_bridge, sample_join_result):
        """测试不同性能模式"""
        # 创建大数据集用于测试
        large_df = pl.concat([sample_join_result.data] * 20000)  # 80,000 rows
        large_result = JoinResult(
            result_id="large_test",
            data=large_df,
            source_info=sample_join_result.source_info,
            join_statistics=sample_join_result.join_statistics,
            quality_metrics=sample_join_result.quality_metrics,
            created_at=sample_join_result.created_at
        )
        
        # 测试快速模式
        ar_table_fast = pivot_bridge.convert_join_result_to_ar_table(large_result, "fast")
        assert len(ar_table_fast.data) <= 50000
        
        # 测试平衡模式
        ar_table_balanced = pivot_bridge.convert_join_result_to_ar_table(large_result, "balanced")
        assert len(ar_table_balanced.data) <= 100000
        
        # 测试精确模式
        ar_table_accurate = pivot_bridge.convert_join_result_to_ar_table(large_result, "accurate")
        assert len(ar_table_accurate.data) == len(large_df)
    
    def test_convert_to_pivot_format(self, pivot_bridge, sample_join_result):
        """测试转换为透视格式"""
        ar_table = pivot_bridge.convert_join_result_to_ar_table(sample_join_result)
        pivot_format = pivot_bridge.convert_to_pivot_format(ar_table)
        
        assert "rows" in pivot_format
        assert "fields" in pivot_format
        assert "count" in pivot_format
        assert "total_count" in pivot_format
        assert "metadata" in pivot_format
        assert "pivot_config" in pivot_format
        
        # 检查数据格式
        assert len(pivot_format["rows"]) == 4
        assert pivot_format["count"] == 4
        assert pivot_format["total_count"] == 4
        
        # 检查字段类型
        fields = pivot_format["fields"]
        assert fields["order_amount"] == "number"
        assert fields["customer_name"] == "string"
    
    def test_convert_to_pivot_format_with_limit(self, pivot_bridge, sample_join_result):
        """测试带限制的转换"""
        ar_table = pivot_bridge.convert_join_result_to_ar_table(sample_join_result)
        pivot_format = pivot_bridge.convert_to_pivot_format(ar_table, limit=2)
        
        assert len(pivot_format["rows"]) == 2
        assert pivot_format["count"] == 2
        assert pivot_format["total_count"] == 4  # 原始总数不变
    
    def test_get_pivot_preview(self, pivot_bridge, sample_join_result):
        """测试获取透视预览"""
        ar_table = pivot_bridge.convert_join_result_to_ar_table(sample_join_result)
        preview = pivot_bridge.get_pivot_preview(ar_table, preview_rows=2)
        
        assert "preview" in preview
        assert "fields" in preview
        assert "sample_size" in preview
        assert "total_size" in preview
        assert "recommendations" in preview
        assert "measures" in preview
        assert "performance_hints" in preview
        
        assert len(preview["preview"]) == 2
        assert preview["sample_size"] == 2
        assert preview["total_size"] == 4
    
    def test_validate_ar_table(self, pivot_bridge, sample_join_result):
        """测试AR Table验证"""
        ar_table = pivot_bridge.convert_join_result_to_ar_table(sample_join_result)
        validation = pivot_bridge.validate_ar_table(ar_table)
        
        assert "valid" in validation
        assert "warnings" in validation
        assert "recommendations" in validation
        assert "performance_score" in validation
        
        assert validation["valid"] is True
        assert isinstance(validation["performance_score"], (int, float))
        assert 0 <= validation["performance_score"] <= 100
    
    def test_validate_large_dataset_warnings(self, pivot_bridge):
        """测试大数据集警告"""
        # 创建大数据集
        large_df = pl.DataFrame({
            "id": range(2000000),  # 200万行
            "value": [f"value_{i}" for i in range(2000000)]
        })
        
        metadata = Mock()
        metadata.quality_metrics = Mock()
        metadata.quality_metrics.completeness = 0.95
        
        ar_table = ARTable(metadata, large_df)
        validation = pivot_bridge.validate_ar_table(ar_table)
        
        assert len(validation["warnings"]) > 0
        assert any("数据集很大" in warning for warning in validation["warnings"])
        assert validation["performance_score"] < 100
    
    @patch('backend.adapters.pivot_bridge.DataEngine')
    def test_optimization_methods(self, mock_data_engine, pivot_bridge, sample_join_result):
        """测试优化方法"""
        # 测试类型优化
        optimized_df = pivot_bridge._optimize_types(sample_join_result.data)
        assert isinstance(optimized_df, pl.DataFrame)
        
        # 测试DataFrame优化
        optimized_df = pivot_bridge._optimize_dataframe(sample_join_result.data, "balanced")
        assert len(optimized_df) <= len(sample_join_result.data)
    
    def test_field_type_generation(self, pivot_bridge, sample_join_result):
        """测试字段类型生成"""
        field_types = pivot_bridge._generate_field_types(sample_join_result.data)
        
        assert field_types["order_amount"] == "number"
        assert field_types["customer_name"] == "string"
        assert field_types["order_date"] == "string"  # 作为字符串处理
        assert "customer_id" in field_types


class TestIntegrationScenarios:
    """集成场景测试"""
    
    def test_complete_conversion_workflow(self, pivot_bridge, sample_join_result):
        """测试完整转换工作流"""
        # 1. 转换为AR Table
        ar_table = pivot_bridge.convert_join_result_to_ar_table(sample_join_result)
        
        # 2. 验证AR Table
        validation = pivot_bridge.validate_ar_table(ar_table)
        assert validation["valid"]
        
        # 3. 获取预览
        preview = pivot_bridge.get_pivot_preview(ar_table)
        assert len(preview["preview"]) > 0
        
        # 4. 转换为透视格式
        pivot_format = pivot_bridge.convert_to_pivot_format(ar_table)
        assert len(pivot_format["rows"]) > 0
        
        # 5. 验证数据一致性
        original_row_count = len(sample_join_result.data)
        converted_row_count = len(pivot_format["rows"])
        assert original_row_count == converted_row_count
    
    def test_error_handling(self, pivot_bridge):
        """测试错误处理"""
        # 测试无效输入
        with pytest.raises(Exception):
            pivot_bridge.convert_join_result_to_ar_table(None)
        
        # 测试空数据
        empty_df = pl.DataFrame()
        metadata = Mock()
        ar_table = ARTable(metadata, empty_df)
        
        # 应该能处理空数据而不崩溃
        validation = pivot_bridge.validate_ar_table(ar_table)
        assert isinstance(validation, dict)


if __name__ == "__main__":
    pytest.main([__file__])