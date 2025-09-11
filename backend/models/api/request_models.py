"""
API请求数据模型

定义所有REST API端点的请求参数模型
"""
from typing import List, Dict, Any, Optional, Union
from enum import Enum
from datetime import datetime

from pydantic import BaseModel, Field, validator, model_validator
from pydantic.types import conint, constr


class PerformanceMode(str, Enum):
    """性能模式枚举"""
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"


class AggregationType(str, Enum):
    """聚合类型枚举"""
    SUM = "sum"
    MEAN = "mean"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


class DatasetUploadRequest(BaseModel):
    """数据集上传请求模型"""
    
    # 文件信息通过FastAPI的UploadFile处理
    # 这里定义其他上传参数
    sheet: Optional[str] = Field(None, description="Excel工作表名称或索引")
    start_row: conint(ge=1) = Field(1, description="数据起始行号（从1开始）")
    encoding: Optional[str] = Field(None, description="文件编码，留空自动检测")
    separator: Optional[str] = Field(None, description="CSV分隔符，留空自动检测")
    
    class Config:
        schema_extra = {
            "example": {
                "sheet": "Sheet1",
                "start_row": 2,
                "encoding": "utf-8",
                "separator": ","
            }
        }


class DatasetPreviewRequest(BaseModel):
    """数据集预览请求模型"""
    
    dataset_id: constr(min_length=1) = Field(..., description="数据集ID")
    offset: conint(ge=0) = Field(0, description="分页偏移量")
    limit: conint(ge=1, le=1000) = Field(100, description="每页记录数（最大1000）")
    columns: Optional[List[str]] = Field(None, description="指定要预览的列名")
    
    class Config:
        schema_extra = {
            "example": {
                "dataset_id": "ds_12345",
                "offset": 0,
                "limit": 100,
                "columns": ["id", "name", "email"]
            }
        }


class JoinType(str, Enum):
    """连接类型枚举"""
    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"
    CROSS = "cross"
    ANTI = "anti"


class JoinCondition(BaseModel):
    """连接条件模型"""
    
    left_column: constr(min_length=1) = Field(..., description="左表连接列")
    right_column: constr(min_length=1) = Field(..., description="右表连接列")
    operator: str = Field("=", description="比较操作符")
    
    @validator('operator')
    def validate_operator(cls, v):
        allowed_operators = ["=", "!=", "<", "<=", ">", ">=", "like", "ilike"]
        if v not in allowed_operators:
            raise ValueError(f"操作符必须是以下之一: {allowed_operators}")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "left_column": "user_id",
                "right_column": "id",
                "operator": "="
            }
        }


class DatasetReference(BaseModel):
    """数据集引用模型"""
    
    dataset_id: constr(min_length=1) = Field(..., description="数据集ID")
    alias: Optional[constr(min_length=1)] = Field(None, description="数据集别名")
    columns: Optional[List[str]] = Field(None, description="选择的列（留空选择所有列）")
    filters: Optional[Dict[str, Any]] = Field(None, description="数据过滤条件")
    
    class Config:
        schema_extra = {
            "example": {
                "dataset_id": "ds_12345",
                "alias": "users",
                "columns": ["id", "name", "email"],
                "filters": {"status": "active"}
            }
        }


class JoinOperation(BaseModel):
    """连接操作模型"""
    
    left_dataset: DatasetReference = Field(..., description="左数据集")
    right_dataset: DatasetReference = Field(..., description="右数据集")
    join_type: JoinType = Field(JoinType.INNER, description="连接类型")
    conditions: List[JoinCondition] = Field(..., min_items=1, description="连接条件列表")
    
    class Config:
        schema_extra = {
            "example": {
                "left_dataset": {
                    "dataset_id": "ds_users",
                    "alias": "u",
                    "columns": ["id", "name"]
                },
                "right_dataset": {
                    "dataset_id": "ds_orders",
                    "alias": "o",
                    "columns": ["user_id", "amount"]
                },
                "join_type": "inner",
                "conditions": [
                    {
                        "left_column": "id",
                        "right_column": "user_id",
                        "operator": "="
                    }
                ]
            }
        }


class JoinPreviewRequest(BaseModel):
    """连接预览请求模型"""
    
    operations: List[JoinOperation] = Field(..., min_items=1, description="连接操作列表")
    output_columns: Optional[List[str]] = Field(None, description="输出列（留空输出所有列）")
    sample_size: conint(ge=1, le=10000) = Field(1000, description="预览样本大小")
    
    @validator('operations')
    def validate_operations(cls, v):
        if len(v) > 10:  # 限制连接操作数量
            raise ValueError("连接操作数量不能超过10个")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "operations": [
                    {
                        "left_dataset": {"dataset_id": "ds_users"},
                        "right_dataset": {"dataset_id": "ds_orders"},
                        "join_type": "inner",
                        "conditions": [{"left_column": "id", "right_column": "user_id"}]
                    }
                ],
                "output_columns": ["u.name", "o.amount"],
                "sample_size": 100
            }
        }


class JoinExecuteRequest(BaseModel):
    """连接执行请求模型"""
    
    operations: List[JoinOperation] = Field(..., min_items=1, description="连接操作列表")
    output_columns: Optional[List[str]] = Field(None, description="输出列（留空输出所有列）")
    result_name: Optional[constr(min_length=1)] = Field(None, description="结果数据集名称")
    save_result: bool = Field(True, description="是否保存结果")
    chunk_size: conint(ge=1000, le=100000) = Field(10000, description="分块处理大小")
    
    @validator('operations')
    def validate_operations(cls, v):
        if len(v) > 10:
            raise ValueError("连接操作数量不能超过10个")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "operations": [
                    {
                        "left_dataset": {"dataset_id": "ds_users"},
                        "right_dataset": {"dataset_id": "ds_orders"},
                        "join_type": "inner",
                        "conditions": [{"left_column": "id", "right_column": "user_id"}]
                    }
                ],
                "output_columns": ["u.name", "o.amount", "o.created_at"],
                "result_name": "user_orders_joined",
                "save_result": True,
                "chunk_size": 10000
            }
        }


class TaskStatusRequest(BaseModel):
    """任务状态查询请求模型"""
    
    task_id: constr(min_length=1) = Field(..., description="任务ID")
    
    class Config:
        schema_extra = {
            "example": {
                "task_id": "task_abc123def456"
            }
        }


class ResultRequest(BaseModel):
    """结果获取请求模型"""
    
    result_id: constr(min_length=1) = Field(..., description="结果ID")
    offset: conint(ge=0) = Field(0, description="分页偏移量")
    limit: conint(ge=1, le=1000) = Field(100, description="每页记录数（最大1000）")
    format: str = Field("json", description="输出格式")
    columns: Optional[List[str]] = Field(None, description="指定输出列")
    
    @validator('format')
    def validate_format(cls, v):
        allowed_formats = ["json", "csv", "parquet"]
        if v not in allowed_formats:
            raise ValueError(f"格式必须是以下之一: {allowed_formats}")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "result_id": "result_xyz789",
                "offset": 0,
                "limit": 100,
                "format": "json",
                "columns": ["name", "amount"]
            }
        }


class PresetSaveRequest(BaseModel):
    """预设保存请求模型"""
    
    name: constr(min_length=1, max_length=100) = Field(..., description="预设名称")
    description: Optional[str] = Field(None, description="预设描述")
    operations: List[JoinOperation] = Field(..., min_items=1, description="连接操作列表")
    output_columns: Optional[List[str]] = Field(None, description="输出列配置")
    tags: Optional[List[str]] = Field(None, description="预设标签")
    is_public: bool = Field(False, description="是否公开预设")
    
    @validator('name')
    def validate_name(cls, v):
        # 预设名称不能包含特殊字符
        import re
        if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fff\s]+$', v):
            raise ValueError("预设名称只能包含字母、数字、下划线、横线、中文和空格")
        return v
    
    @validator('tags')
    def validate_tags(cls, v):
        if v and len(v) > 10:
            raise ValueError("标签数量不能超过10个")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "name": "用户订单关联查询",
                "description": "关联用户表和订单表，获取用户的订单信息",
                "operations": [
                    {
                        "left_dataset": {"dataset_id": "ds_users", "alias": "u"},
                        "right_dataset": {"dataset_id": "ds_orders", "alias": "o"},
                        "join_type": "inner",
                        "conditions": [{"left_column": "id", "right_column": "user_id"}]
                    }
                ],
                "output_columns": ["u.name", "u.email", "o.amount", "o.created_at"],
                "tags": ["用户", "订单", "关联查询"],
                "is_public": False
            }
        }


class PresetListRequest(BaseModel):
    """预设列表查询请求模型"""
    
    offset: conint(ge=0) = Field(0, description="分页偏移量")
    limit: conint(ge=1, le=100) = Field(20, description="每页记录数（最大100）")
    search: Optional[str] = Field(None, description="搜索关键词")
    tags: Optional[List[str]] = Field(None, description="标签过滤")
    is_public: Optional[bool] = Field(None, description="是否只显示公开预设")
    sort_by: str = Field("created_at", description="排序字段")
    sort_order: str = Field("desc", description="排序顺序")
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        allowed_fields = ["name", "created_at", "updated_at", "usage_count"]
        if v not in allowed_fields:
            raise ValueError(f"排序字段必须是以下之一: {allowed_fields}")
        return v
    
    @validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("排序顺序必须是 'asc' 或 'desc'")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "offset": 0,
                "limit": 20,
                "search": "用户",
                "tags": ["用户", "订单"],
                "is_public": False,
                "sort_by": "created_at",
                "sort_order": "desc"
            }
        }


# 验证基础设施
class ValidationConfig(BaseModel):
    """验证配置模型"""
    
    max_file_size_mb: int = Field(500, description="最大文件大小（MB）")
    max_dataset_rows: int = Field(10000000, description="数据集最大行数")
    max_join_operations: int = Field(10, description="最大连接操作数")


class PivotConfigRequest(BaseModel):
    """透视配置请求模型"""
    
    row_fields: List[str] = Field(default_factory=list, description="行字段列表")
    col_fields: List[str] = Field(default_factory=list, description="列字段列表")
    value_fields: List[str] = Field(..., min_items=1, description="数值字段列表")
    aggregation_type: AggregationType = Field(AggregationType.SUM, description="聚合类型")
    performance_mode: PerformanceMode = Field(PerformanceMode.BALANCED, description="性能模式")
    filters: Optional[Dict[str, Any]] = Field(None, description="数据过滤条件")
    sort_config: Optional[Dict[str, str]] = Field(None, description="排序配置")
    
    @validator('value_fields')
    def validate_value_fields(cls, v):
        if not v:
            raise ValueError("至少需要一个数值字段")
        return v
    
    @model_validator(mode='after')
    def validate_field_combinations(self):
        row_fields = self.row_fields or []
        col_fields = self.col_fields or []
        value_fields = self.value_fields or []
        
        # 检查字段重复
        all_fields = row_fields + col_fields + value_fields
        if len(all_fields) != len(set(all_fields)):
            raise ValueError("字段不能重复使用")
        
        # 检查字段数量限制
        if len(row_fields) + len(col_fields) > 10:
            raise ValueError("行字段和列字段总数不能超过10个")
        
        return self
    
    class Config:
        schema_extra = {
            "example": {
                "row_fields": ["customer_city", "product_category"],
                "col_fields": ["order_month"],
                "value_fields": ["order_amount", "order_count"],
                "aggregation_type": "sum",
                "performance_mode": "balanced",
                "filters": {
                    "order_amount": {"$gte": 100}
                },
                "sort_config": {
                    "field": "order_amount_sum",
                    "order": "desc"
                }
            }
        }
    max_result_rows: int = Field(1000000, description="结果最大行数")
    allowed_file_extensions: List[str] = Field(
        ["csv", "xlsx", "xls", "tsv", "txt"],
        description="允许的文件扩展名"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "max_file_size_mb": 500,
                "max_dataset_rows": 10000000,
                "max_join_operations": 10,
                "max_result_rows": 1000000,
                "allowed_file_extensions": ["csv", "xlsx", "xls", "tsv"]
            }
        }