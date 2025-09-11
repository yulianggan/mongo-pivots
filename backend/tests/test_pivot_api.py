"""
透视API测试
"""

import pytest
import asyncio
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock

# 修复导入路径
sys.path.append(str(Path(__file__).parent.parent))

from api.main import create_app
from models.api.request_models import PivotConfigRequest, AggregationType, PerformanceMode


@pytest.fixture
def app():
    """创建测试应用"""
    return create_app(enable_docs=False)


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_pivot_bridge():
    """Mock PivotBridge适配器"""
    with patch('backend.api.routers.pivot.pivot_bridge') as mock:
        mock.get_pivot_preview.return_value = {
            "preview": [{"city": "北京", "order_amount": 299.99}],
            "fields": {"city": "string", "order_amount": "float"},
            "sample_size": 1,
            "total_size": 3,
            "recommendations": ["city"],
            "measures": ["order_amount"],
            "performance_hints": []
        }
        mock.convert_to_pivot.return_value = {
            "pivot_data": [{"city": "北京", "order_amount_sum": 299.99}],
            "processing_time_ms": 50,
            "performance_stats": {"memory_mb": 5.2}
        }
        yield mock


@pytest.fixture
def mock_join_result():
    """模拟连接结果"""
    import polars as pl
    from datetime import datetime
    from models.api.response_models import JoinResult, JoinStatistics, QualityMetrics
    
    df = pl.DataFrame({
        "customer_id": ["C001", "C002", "C003"],
        "customer_name": ["张三", "李四", "王五"],
        "city": ["北京", "上海", "广州"],
        "order_amount": [299.99, 159.50, 89.99]
    })
    
    return JoinResult(
        result_id="test_result_123",
        data=df,
        source_info=[{"name": "customers"}, {"name": "orders"}],
        join_statistics=JoinStatistics(
            total_records=3,
            matched_records=3,
            unmatched_records=0,
            execution_time_ms=1000,
            memory_peak_mb=10.5
        ),
        quality_metrics=QualityMetrics(
            completeness=0.95,
            accuracy=0.90,
            consistency=0.92,
            uniqueness=0.88
        ),
        created_at=datetime.now()
    )


class TestPivotPreviewAPI:
    """透视预览API测试"""
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_get_pivot_preview_success(self, mock_get_result, client, mock_join_result, mock_pivot_bridge):
        """测试获取透视预览成功"""
        mock_get_result.return_value = mock_join_result
        
        response = client.get("/api/pivot/result/test_result_123/pivot-preview?limit=50")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["result_id"] == "test_result_123"
        assert "preview_data" in data
        assert "fields" in data
        assert "sample_size" in data
        assert "total_size" in data
        assert "recommended_dimensions" in data
        assert "recommended_measures" in data
        assert data["sample_size"] <= 50  # 符合限制
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_get_pivot_preview_not_found(self, mock_get_result, client):
        """测试连接结果不存在"""
        mock_get_result.return_value = None
        
        response = client.get("/api/pivot/result/nonexistent/pivot-preview")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_get_pivot_preview_invalid_limit(self, client):
        """测试无效的限制参数"""
        # 测试超出范围的limit
        response = client.get("/api/pivot/result/test/pivot-preview?limit=2000")
        assert response.status_code == 422  # 验证错误
        
        # 测试负数limit
        response = client.get("/api/pivot/result/test/pivot-preview?limit=-1")
        assert response.status_code == 422  # 验证错误


class TestPivotCreateAPI:
    """透视创建API测试"""
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_create_pivot_success(self, mock_get_result, client, mock_join_result, mock_pivot_bridge):
        """测试创建透视成功"""
        mock_get_result.return_value = mock_join_result
        
        pivot_config = {
            "row_fields": ["city"],
            "col_fields": [],
            "value_fields": ["order_amount"],
            "aggregation_type": "sum",
            "performance_mode": "balanced"
        }
        
        response = client.post(
            "/api/pivot/result/test_result_123/create-pivot",
            json=pivot_config
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["result_id"] == "test_result_123"
        assert "pivot_data" in data
        assert data["row_fields"] == ["city"]
        assert data["value_fields"] == ["order_amount"]
        assert data["aggregation_type"] == "sum"
        assert "processing_time_ms" in data
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_create_pivot_with_limit(self, mock_get_result, client, mock_join_result, mock_pivot_bridge):
        """测试带限制的透视创建"""
        mock_get_result.return_value = mock_join_result
        
        pivot_config = {
            "row_fields": ["city"],
            "value_fields": ["order_amount"],
            "aggregation_type": "mean"
        }
        
        response = client.post(
            "/api/pivot/result/test_result_123/create-pivot?limit=1000",
            json=pivot_config
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["aggregation_type"] == "mean"
    
    def test_create_pivot_invalid_config(self, client):
        """测试无效的透视配置"""
        # 缺少必需字段
        invalid_config = {
            "row_fields": ["city"],
            "col_fields": []
            # 缺少value_fields
        }
        
        response = client.post(
            "/api/pivot/result/test/create-pivot",
            json=invalid_config
        )
        
        assert response.status_code == 422  # 验证错误
    
    def test_create_pivot_duplicate_fields(self, client):
        """测试重复字段配置"""
        invalid_config = {
            "row_fields": ["city"],
            "col_fields": ["city"],  # 重复使用city
            "value_fields": ["order_amount"],
            "aggregation_type": "sum"
        }
        
        response = client.post(
            "/api/pivot/result/test/create-pivot",
            json=invalid_config
        )
        
        assert response.status_code == 422  # 验证错误


class TestPivotValidationAPI:
    """透视验证API测试"""
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_validate_for_pivot_success(self, mock_get_result, client, mock_join_result):
        """测试验证成功"""
        mock_get_result.return_value = mock_join_result
        
        response = client.get("/api/pivot/result/test_result_123/validate")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["result_id"] == "test_result_123"
        assert "valid" in data
        assert "warnings" in data
        assert "recommendations" in data
        assert "performance_score" in data
        assert "data_summary" in data
        
        # 检查数据概要结构
        summary = data["data_summary"]
        assert "total_rows" in summary
        assert "total_columns" in summary
        assert "estimated_memory_mb" in summary


class TestPivotMetadataAPI:
    """透视元数据API测试"""
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_get_result_metadata_success(self, mock_get_result, client, mock_join_result):
        """测试获取元数据成功"""
        mock_get_result.return_value = mock_join_result
        
        response = client.get("/api/pivot/result/test_result_123/metadata")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["result_id"] == "test_result_123"
        assert "source_info" in data
        assert "join_statistics" in data
        assert "quality_metrics" in data
        assert "schema" in data
        assert "pivot_recommendations" in data
        
        # 检查schema结构
        schema = data["schema"]
        assert "columns" in schema
        assert "column_types" in schema
        assert "row_count" in schema
        
        # 检查质量指标
        quality = data["quality_metrics"]
        assert "completeness" in quality
        assert "accuracy" in quality
        assert "consistency" in quality
        assert "uniqueness" in quality


class TestPivotConfigRequestValidation:
    """透视配置请求验证测试"""
    
    def test_pivot_config_valid(self):
        """测试有效配置"""
        config = PivotConfigRequest(
            row_fields=["city"],
            col_fields=["month"],
            value_fields=["amount"],
            aggregation_type=AggregationType.SUM,
            performance_mode=PerformanceMode.BALANCED
        )
        
        assert config.row_fields == ["city"]
        assert config.col_fields == ["month"]
        assert config.value_fields == ["amount"]
        assert config.aggregation_type == AggregationType.SUM
        assert config.performance_mode == PerformanceMode.BALANCED
    
    def test_pivot_config_duplicate_fields(self):
        """测试重复字段验证"""
        with pytest.raises(ValueError, match="字段不能重复使用"):
            PivotConfigRequest(
                row_fields=["city"],
                col_fields=["city"],  # 重复
                value_fields=["amount"]
            )
    
    def test_pivot_config_too_many_fields(self):
        """测试字段数量限制"""
        many_fields = [f"field_{i}" for i in range(11)]  # 11个字段
        
        with pytest.raises(ValueError, match="字段总数不能超过10个"):
            PivotConfigRequest(
                row_fields=many_fields[:6],
                col_fields=many_fields[6:11],  # 总共11个
                value_fields=["amount"]
            )
    
    def test_pivot_config_empty_value_fields(self):
        """测试空值字段验证"""
        with pytest.raises(ValueError, match="至少需要一个数值字段"):
            PivotConfigRequest(
                row_fields=["city"],
                value_fields=[]  # 空列表
            )


class TestPivotAPIIntegration:
    """透视API集成测试"""
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_full_pivot_workflow(self, mock_get_result, client, mock_join_result, mock_pivot_bridge):
        """测试完整透视工作流"""
        mock_get_result.return_value = mock_join_result
        
        result_id = "test_result_123"
        
        # 1. 获取元数据
        metadata_response = client.get(f"/api/pivot/result/{result_id}/metadata")
        assert metadata_response.status_code == 200
        
        # 2. 验证数据
        validation_response = client.get(f"/api/pivot/result/{result_id}/validate")
        assert validation_response.status_code == 200
        
        # 3. 获取预览
        preview_response = client.get(f"/api/pivot/result/{result_id}/pivot-preview")
        assert preview_response.status_code == 200
        
        # 4. 创建透视
        pivot_config = {
            "row_fields": ["city"],
            "value_fields": ["order_amount"],
            "aggregation_type": "sum"
        }
        
        pivot_response = client.post(
            f"/api/pivot/result/{result_id}/create-pivot",
            json=pivot_config
        )
        assert pivot_response.status_code == 200
        
        # 验证所有响应都成功
        assert metadata_response.json()["result_id"] == result_id
        assert validation_response.json()["result_id"] == result_id
        assert preview_response.json()["result_id"] == result_id
        assert pivot_response.json()["result_id"] == result_id


class TestErrorHandling:
    """错误处理测试"""
    
    def test_invalid_result_id_format(self, client):
        """测试无效的结果ID格式"""
        response = client.get("/api/pivot/result/invalid-id/metadata")
        # 应该返回验证错误或404
        assert response.status_code in [404, 422]
    
@patch('backend.api.routers.pivot.join_service.get_result')
    def test_service_error_handling(self, mock_get_result, client):
        """测试服务层错误处理"""
        # 模拟服务异常
        mock_get_result.side_effect = Exception("Service error")
        
        response = client.get("/api/pivot/result/test/metadata")
        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__])