#!/usr/bin/env python3
"""
简化版后端服务 - 用于演示和测试
提供基础API响应，无复杂依赖
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
from datetime import datetime, timezone
import time


# 创建FastAPI应用
app = FastAPI(
    title="Mongo Pivot Suite API",
    description="简化版API服务",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 基础响应模型
class StatusResponse(BaseModel):
    status: str
    message: str
    timestamp: str


class DatasetResponse(BaseModel):
    success: bool
    dataset_id: str
    name: str
    rows: int
    columns: int


class JoinResultResponse(BaseModel):
    success: bool
    result_id: str
    message: str
    processing_time_ms: int


class QualityReportResponse(BaseModel):
    result_id: str
    source_info: List[Dict[str, Any]]
    join_statistics: Dict[str, Any]
    quality_metrics: Dict[str, float]
    schema: Dict[str, Any]
    pivot_recommendations: Dict[str, List[str]]


# API端点

@app.get("/")
async def root():
    """根路径健康检查"""
    return {"message": "Mongo Pivot Suite API", "status": "ok"}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return StatusResponse(
        status="ok",
        message="API服务运行正常",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/api/collections")
async def get_collections():
    """获取可用集合列表"""
    return {
        "success": True,
        "collections": [
            {"name": "customers", "count": 1000, "description": "客户数据"},
            {"name": "orders", "count": 2500, "description": "订单数据"},
            {"name": "products", "count": 150, "description": "产品数据"}
        ]
    }


@app.post("/api/dataset/upload")
async def upload_dataset():
    """模拟数据集上传"""
    dataset_id = f"ds_{int(time.time())}"
    return DatasetResponse(
        success=True,
        dataset_id=dataset_id,
        name="示例数据集",
        rows=1000,
        columns=8
    )


@app.get("/api/dataset/list")
async def list_datasets():
    """获取数据集列表"""
    return {
        "success": True,
        "datasets": [
            {
                "id": "ds_customers",
                "name": "客户数据",
                "upload_time": "2024-03-01T10:00:00Z",
                "rows": 1000,
                "columns": 5,
                "size_mb": 2.5
            },
            {
                "id": "ds_orders", 
                "name": "订单数据",
                "upload_time": "2024-03-01T11:00:00Z",
                "rows": 2500,
                "columns": 8,
                "size_mb": 5.2
            }
        ]
    }


@app.post("/api/join/preview")
async def join_preview():
    """连接预览"""
    return {
        "success": True,
        "preview_data": [
            {"customer_id": "C001", "customer_name": "张三", "order_amount": 299.99},
            {"customer_id": "C002", "customer_name": "李四", "order_amount": 159.50},
            {"customer_id": "C003", "customer_name": "王五", "order_amount": 89.99}
        ],
        "sample_size": 3,
        "total_estimated": 1000,
        "join_type": "inner"
    }


@app.post("/api/join/execute")
async def execute_join():
    """执行连接"""
    result_id = f"result_{int(time.time())}"
    return JoinResultResponse(
        success=True,
        result_id=result_id,
        message="连接任务已启动",
        processing_time_ms=1500
    )


@app.get("/api/pivot/result/{result_id}/metadata")
async def get_pivot_metadata(result_id: str):
    """获取透视元数据"""
    return QualityReportResponse(
        result_id=result_id,
        source_info=[
            {"name": "customers", "type": "dataset", "records": 1000},
            {"name": "orders", "type": "dataset", "records": 2500}
        ],
        join_statistics={
            "total_records": 1000,
            "matched_records": 950,
            "execution_time_ms": 1500,
            "memory_peak_mb": 15.5
        },
        quality_metrics={
            "completeness": 0.95,
            "accuracy": 0.92,
            "consistency": 0.88,
            "uniqueness": 0.93
        },
        schema={
            "columns": ["customer_id", "customer_name", "city", "order_amount", "order_date"],
            "column_types": {
                "customer_id": "string",
                "customer_name": "string", 
                "city": "string",
                "order_amount": "float64",
                "order_date": "datetime"
            },
            "row_count": 1000
        },
        pivot_recommendations={
            "recommended_dimensions": ["city", "customer_name"],
            "recommended_measures": ["order_amount"],
            "performance_hints": ["考虑为大数据集启用分页", "建议使用聚合视图提升性能"]
        }
    )


@app.get("/api/pivot/result/{result_id}/validate")
async def validate_pivot(result_id: str):
    """验证透视数据"""
    return {
        "success": True,
        "result_id": result_id,
        "valid": True,
        "warnings": ["数据量较大，透视分析可能需要较长时间"],
        "recommendations": ["建议选择合适的聚合字段", "可考虑添加过滤条件减少数据量"],
        "performance_score": 85.5,
        "data_summary": {
            "total_rows": 1000,
            "total_columns": 5,
            "numeric_columns": 1,
            "estimated_memory_mb": 8.2
        }
    }


@app.get("/api/pivot/result/{result_id}/pivot-preview")
async def get_pivot_preview(result_id: str, limit: int = 100):
    """获取透视预览"""
    return {
        "success": True,
        "result_id": result_id,
        "preview_data": [
            {"city": "北京", "order_amount": 1299.99},
            {"city": "上海", "order_amount": 2159.50}, 
            {"city": "广州", "order_amount": 989.99}
        ],
        "fields": {
            "city": "string",
            "order_amount": "float64"
        },
        "sample_size": 3,
        "total_size": 1000,
        "recommended_dimensions": ["city"],
        "recommended_measures": ["order_amount"]
    }


@app.post("/api/pivot/result/{result_id}/create-pivot")
async def create_pivot(result_id: str):
    """创建透视表"""
    return {
        "success": True,
        "result_id": result_id,
        "pivot_data": [
            {"city": "北京", "order_amount_sum": 3299.99, "order_count": 12},
            {"city": "上海", "order_amount_sum": 4159.50, "order_count": 18},
            {"city": "广州", "order_amount_sum": 2989.99, "order_count": 15}
        ],
        "row_fields": ["city"],
        "col_fields": [],
        "value_fields": ["order_amount"],
        "aggregation_type": "sum",
        "processing_time_ms": 250
    }


if __name__ == "__main__":
    print("🚀 启动简化版后端服务...")
    print("前端访问: http://localhost:3001/")
    print("后端API: http://localhost:8000/")
    print("API文档: http://localhost:8000/docs")
    
    uvicorn.run(
        "simple_backend:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )