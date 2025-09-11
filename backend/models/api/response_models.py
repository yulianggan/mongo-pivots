"""
API响应数据模型

定义所有REST API端点的响应格式模型
"""
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """API基础响应模型"""
    
    success: bool = Field(True, description="请求是否成功")
    message: Optional[str] = Field(None, description="响应消息")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="响应时间戳")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class ErrorResponse(APIResponse):
    """错误响应模型"""
    
    success: bool = Field(False, description="请求失败")
    error: Dict[str, Any] = Field(..., description="错误详情")
    
    class Config:
        schema_extra = {
            "example": {
                "success": False,
                "message": "Validation error",
                "timestamp": "2025-09-10T10:00:00Z",
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {
                        "validation_errors": [
                            {
                                "field": "dataset_id",
                                "message": "field required",
                                "type": "value_error.missing"
                            }
                        ]
                    },
                    "path": "/api/dataset/preview",
                    "method": "POST",
                    "status": 422
                }
            }
        }


class PaginatedResponse(APIResponse):
    """分页响应基础模型"""
    
    total: int = Field(..., description="总记录数")
    offset: int = Field(..., description="当前偏移量")
    limit: int = Field(..., description="每页记录数")
    has_more: bool = Field(..., description="是否有更多数据")
    
    @property
    def current_page(self) -> int:
        """当前页码（从1开始）"""
        return (self.offset // self.limit) + 1
    
    @property
    def total_pages(self) -> int:
        """总页数"""
        return (self.total + self.limit - 1) // self.limit


class DatasetInfo(BaseModel):
    """数据集信息模型"""
    
    dataset_id: str = Field(..., description="数据集ID")
    name: str = Field(..., description="数据集名称")
    description: Optional[str] = Field(None, description="数据集描述")
    rows: int = Field(..., description="行数")
    columns: int = Field(..., description="列数")
    size_bytes: int = Field(..., description="大小（字节）")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    file_type: str = Field(..., description="文件类型")
    encoding: Optional[str] = Field(None, description="文件编码")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
        schema_extra = {
            "example": {
                "dataset_id": "ds_12345",
                "name": "users.csv",
                "description": "用户数据集",
                "rows": 10000,
                "columns": 8,
                "size_bytes": 2048000,
                "created_at": "2025-09-10T10:00:00Z",
                "updated_at": "2025-09-10T10:00:00Z",
                "file_type": "csv",
                "encoding": "utf-8"
            }
        }


class FieldInfo(BaseModel):
    """字段信息模型"""
    
    name: str = Field(..., description="字段名称")
    data_type: str = Field(..., description="数据类型")
    nullable: bool = Field(..., description="是否可为空")
    unique_count: Optional[int] = Field(None, description="唯一值数量")
    null_count: int = Field(..., description="空值数量")
    sample_values: List[Any] = Field(..., description="样本值")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "user_id",
                "data_type": "Int64",
                "nullable": False,
                "unique_count": 9876,
                "null_count": 0,
                "sample_values": [1, 2, 3, 4, 5]
            }
        }


class DatasetUploadResponse(APIResponse):
    """数据集上传响应模型"""
    
    dataset: DatasetInfo = Field(..., description="数据集信息")
    fields: List[FieldInfo] = Field(..., description="字段信息列表")
    preview: List[Dict[str, Any]] = Field(..., description="数据预览（前10行）")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Dataset uploaded successfully",
                "timestamp": "2025-09-10T10:00:00Z",
                "dataset": {
                    "dataset_id": "ds_12345",
                    "name": "users.csv",
                    "rows": 10000,
                    "columns": 5,
                    "size_bytes": 1024000,
                    "created_at": "2025-09-10T10:00:00Z",
                    "file_type": "csv"
                },
                "fields": [
                    {
                        "name": "id",
                        "data_type": "Int64",
                        "nullable": False,
                        "unique_count": 10000,
                        "null_count": 0,
                        "sample_values": [1, 2, 3]
                    }
                ],
                "preview": [
                    {"id": 1, "name": "Alice", "email": "alice@example.com"},
                    {"id": 2, "name": "Bob", "email": "bob@example.com"}
                ]
            }
        }


class DatasetPreviewResponse(PaginatedResponse):
    """数据集预览响应模型"""
    
    dataset: DatasetInfo = Field(..., description="数据集信息")
    data: List[Dict[str, Any]] = Field(..., description="数据行")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:00:00Z",
                "total": 10000,
                "offset": 0,
                "limit": 100,
                "has_more": True,
                "dataset": {
                    "dataset_id": "ds_12345",
                    "name": "users.csv",
                    "rows": 10000,
                    "columns": 5
                },
                "data": [
                    {"id": 1, "name": "Alice", "email": "alice@example.com"},
                    {"id": 2, "name": "Bob", "email": "bob@example.com"}
                ]
            }
        }


class ResourceEstimate(BaseModel):
    """资源估算模型"""
    
    estimated_rows: int = Field(..., description="预估结果行数")
    estimated_size_mb: float = Field(..., description="预估结果大小（MB）")
    estimated_time_seconds: float = Field(..., description="预估执行时间（秒）")
    memory_required_mb: float = Field(..., description="所需内存（MB）")
    complexity_score: float = Field(..., description="复杂度评分（1-10）")
    
    class Config:
        schema_extra = {
            "example": {
                "estimated_rows": 50000,
                "estimated_size_mb": 12.5,
                "estimated_time_seconds": 30.0,
                "memory_required_mb": 256.0,
                "complexity_score": 6.5
            }
        }


class JoinPreviewResponse(APIResponse):
    """连接预览响应模型"""
    
    preview_data: List[Dict[str, Any]] = Field(..., description="预览数据")
    resource_estimate: ResourceEstimate = Field(..., description="资源估算")
    plan: Dict[str, Any] = Field(..., description="执行计划")
    warnings: List[str] = Field(default_factory=list, description="警告信息")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Join preview generated successfully",
                "timestamp": "2025-09-10T10:00:00Z",
                "preview_data": [
                    {"u.name": "Alice", "u.email": "alice@example.com", "o.amount": 99.99},
                    {"u.name": "Bob", "u.email": "bob@example.com", "o.amount": 149.99}
                ],
                "resource_estimate": {
                    "estimated_rows": 50000,
                    "estimated_size_mb": 12.5,
                    "estimated_time_seconds": 30.0,
                    "memory_required_mb": 256.0,
                    "complexity_score": 6.5
                },
                "plan": {
                    "steps": ["Load datasets", "Apply filters", "Execute join", "Select columns"],
                    "optimizations": ["Index scan on join columns"]
                },
                "warnings": []
            }
        }


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskProgress(BaseModel):
    """任务进度模型"""
    
    current_step: str = Field(..., description="当前步骤")
    step_index: int = Field(..., description="步骤索引")
    total_steps: int = Field(..., description="总步骤数")
    progress_percent: float = Field(..., description="进度百分比")
    processed_rows: int = Field(0, description="已处理行数")
    total_rows: Optional[int] = Field(None, description="总行数")
    
    class Config:
        schema_extra = {
            "example": {
                "current_step": "Executing join operation",
                "step_index": 3,
                "total_steps": 5,
                "progress_percent": 60.0,
                "processed_rows": 30000,
                "total_rows": 50000
            }
        }


class JoinExecuteResponse(APIResponse):
    """连接执行响应模型"""
    
    task_id: str = Field(..., description="任务ID")
    estimated_completion: datetime = Field(..., description="预估完成时间")
    status: TaskStatus = Field(..., description="任务状态")
    progress: TaskProgress = Field(..., description="任务进度")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
        schema_extra = {
            "example": {
                "success": True,
                "message": "Join task started successfully",
                "timestamp": "2025-09-10T10:00:00Z",
                "task_id": "task_abc123def456",
                "estimated_completion": "2025-09-10T10:05:00Z",
                "status": "pending",
                "progress": {
                    "current_step": "Initializing task",
                    "step_index": 1,
                    "total_steps": 5,
                    "progress_percent": 0.0,
                    "processed_rows": 0
                }
            }
        }


class TaskStatusResponse(APIResponse):
    """任务状态查询响应模型"""
    
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: TaskProgress = Field(..., description="任务进度")
    started_at: datetime = Field(..., description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    result_id: Optional[str] = Field(None, description="结果ID（任务完成后可用）")
    error_message: Optional[str] = Field(None, description="错误消息（任务失败时）")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:03:00Z",
                "task_id": "task_abc123def456",
                "status": "running",
                "progress": {
                    "current_step": "Executing join operation",
                    "step_index": 3,
                    "total_steps": 5,
                    "progress_percent": 60.0,
                    "processed_rows": 30000,
                    "total_rows": 50000
                },
                "started_at": "2025-09-10T10:00:00Z",
                "completed_at": None,
                "result_id": None,
                "error_message": None
            }
        }


class ResultMetadata(BaseModel):
    """结果元数据模型"""
    
    result_id: str = Field(..., description="结果ID")
    task_id: str = Field(..., description="任务ID")
    rows: int = Field(..., description="结果行数")
    columns: int = Field(..., description="结果列数")
    size_bytes: int = Field(..., description="结果大小（字节）")
    created_at: datetime = Field(..., description="创建时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }


class ResultResponse(PaginatedResponse):
    """结果获取响应模型"""
    
    metadata: ResultMetadata = Field(..., description="结果元数据")
    data: List[Dict[str, Any]] = Field(..., description="结果数据")
    columns: List[str] = Field(..., description="列名列表")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:05:00Z",
                "total": 50000,
                "offset": 0,
                "limit": 100,
                "has_more": True,
                "metadata": {
                    "result_id": "result_xyz789",
                    "task_id": "task_abc123def456",
                    "rows": 50000,
                    "columns": 5,
                    "size_bytes": 12582912,
                    "created_at": "2025-09-10T10:05:00Z"
                },
                "data": [
                    {"u.name": "Alice", "u.email": "alice@example.com", "o.amount": 99.99},
                    {"u.name": "Bob", "u.email": "bob@example.com", "o.amount": 149.99}
                ],
                "columns": ["u.name", "u.email", "o.amount", "o.created_at", "o.status"]
            }
        }


class PresetInfo(BaseModel):
    """预设信息模型"""
    
    preset_id: str = Field(..., description="预设ID")
    name: str = Field(..., description="预设名称")
    description: Optional[str] = Field(None, description="预设描述")
    user_id: str = Field(..., description="创建用户ID")
    is_public: bool = Field(..., description="是否公开")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    usage_count: int = Field(0, description="使用次数")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }
        schema_extra = {
            "example": {
                "preset_id": "preset_123",
                "name": "用户订单关联查询",
                "description": "关联用户表和订单表，获取用户的订单信息",
                "user_id": "user_456",
                "is_public": False,
                "tags": ["用户", "订单", "关联查询"],
                "usage_count": 15,
                "created_at": "2025-09-10T09:00:00Z",
                "updated_at": "2025-09-10T10:00:00Z"
            }
        }


class PresetSaveResponse(APIResponse):
    """预设保存响应模型"""
    
    preset: PresetInfo = Field(..., description="预设信息")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "message": "Preset saved successfully",
                "timestamp": "2025-09-10T10:00:00Z",
                "preset": {
                    "preset_id": "preset_123",
                    "name": "用户订单关联查询",
                    "description": "关联用户表和订单表，获取用户的订单信息",
                    "user_id": "user_456",
                    "is_public": False,
                    "tags": ["用户", "订单", "关联查询"],
                    "usage_count": 0,
                    "created_at": "2025-09-10T10:00:00Z",
                    "updated_at": "2025-09-10T10:00:00Z"
                }
            }
        }


class PresetListResponse(PaginatedResponse):
    """预设列表响应模型"""
    
    presets: List[PresetInfo] = Field(..., description="预设列表")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:00:00Z",
                "total": 25,
                "offset": 0,
                "limit": 20,
                "has_more": True,
                "presets": [
                    {
                        "preset_id": "preset_123",
                        "name": "用户订单关联查询",
                        "description": "关联用户表和订单表",
                        "user_id": "user_456",
                        "is_public": False,
                        "tags": ["用户", "订单"],
                        "usage_count": 15,
                        "created_at": "2025-09-10T09:00:00Z",
                        "updated_at": "2025-09-10T10:00:00Z"
                    }
                ]
            }
        }


class HealthResponse(APIResponse):
    """健康检查响应模型"""
    
    status: str = Field("ok", description="服务状态")
    version: str = Field(..., description="API版本")
    uptime_seconds: float = Field(..., description="运行时间（秒）")
    memory_usage_mb: float = Field(..., description="内存使用量（MB）")
    active_connections: int = Field(..., description="活跃连接数")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:00:00Z",
                "status": "ok",
                "version": "1.0.0",
                "uptime_seconds": 3600.5,
                "memory_usage_mb": 512.3,
                "active_connections": 25
            }
        }


# 透视分析相关响应模型

class PivotPreviewResponse(APIResponse):
    """透视预览响应模型"""
    
    result_id: str = Field(..., description="连接结果ID")
    preview_data: List[Dict[str, Any]] = Field(..., description="预览数据")
    fields: Dict[str, str] = Field(..., description="字段类型映射")
    sample_size: int = Field(..., description="样本大小")
    total_size: int = Field(..., description="总数据量")
    recommended_dimensions: List[str] = Field(..., description="推荐维度字段")
    recommended_measures: List[str] = Field(..., description="推荐度量字段")
    performance_hints: List[str] = Field(..., description="性能提示")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:00:00Z",
                "result_id": "join_result_123",
                "preview_data": [
                    {"customer_name": "张三", "city": "北京", "order_amount": 299.99},
                    {"customer_name": "李四", "city": "上海", "order_amount": 159.50}
                ],
                "fields": {
                    "customer_name": "string",
                    "city": "string", 
                    "order_amount": "number"
                },
                "sample_size": 100,
                "total_size": 15847,
                "recommended_dimensions": ["city", "customer_name"],
                "recommended_measures": ["order_amount"],
                "performance_hints": ["数据集较大，建议使用过滤条件"]
            }
        }


class PivotDataResponse(APIResponse):
    """透视数据响应模型"""
    
    result_id: str = Field(..., description="连接结果ID")
    pivot_data: Dict[str, Any] = Field(..., description="透视计算结果")
    row_fields: List[str] = Field(..., description="行字段")
    col_fields: List[str] = Field(..., description="列字段")
    value_fields: List[str] = Field(..., description="数值字段")
    aggregation_type: str = Field(..., description="聚合类型")
    total_records: int = Field(..., description="处理记录总数")
    processing_time_ms: float = Field(..., description="处理时间（毫秒）")
    warnings: List[str] = Field(default_factory=list, description="警告信息")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据信息")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:00:00Z",
                "result_id": "join_result_123",
                "pivot_data": {
                    "pivot_table": [
                        {"city": "北京", "order_amount_sum": 1299.99, "order_count": 5},
                        {"city": "上海", "order_amount_sum": 899.50, "order_count": 3}
                    ],
                    "group_count": 2,
                    "total_records": 15847
                },
                "row_fields": ["city"],
                "col_fields": [],
                "value_fields": ["order_amount"],
                "aggregation_type": "sum",
                "total_records": 15847,
                "processing_time_ms": 1250.5,
                "warnings": ["数据集较大，已应用性能优化"],
                "metadata": {
                    "source_info": [{"name": "customers"}, {"name": "orders"}],
                    "quality_score": 92.3
                }
            }
        }


class ValidationResponse(APIResponse):
    """数据验证响应模型"""
    
    result_id: str = Field(..., description="连接结果ID")
    valid: bool = Field(..., description="是否验证通过")
    warnings: List[str] = Field(..., description="警告信息")
    recommendations: List[str] = Field(..., description="优化建议")
    performance_score: float = Field(..., description="性能评分(0-100)")
    data_summary: Dict[str, Any] = Field(..., description="数据概要")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-09-10T10:00:00Z",
                "result_id": "join_result_123",
                "valid": True,
                "warnings": ["数据集较大，透视操作可能较慢"],
                "recommendations": ["考虑使用数据过滤", "选择关键字段进行分析"],
                "performance_score": 75.5,
                "data_summary": {
                    "total_rows": 15847,
                    "total_columns": 12,
                    "numeric_columns": 5,
                    "estimated_memory_mb": 12.5
                }
            }
        }