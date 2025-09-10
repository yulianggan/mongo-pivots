"""
参数验证基础设施

提供通用的参数验证函数和验证器装饰器
"""
import re
import os
import mimetypes
from typing import Any, List, Optional, Dict, Callable, Union
from datetime import datetime, timedelta
import logging

from fastapi import UploadFile, HTTPException
from pydantic import validator, ValidationError

from .middleware.error_handler import ValidationAPIError

logger = logging.getLogger(__name__)


class ValidationConfig:
    """验证配置类"""
    
    # 文件上传限制
    MAX_FILE_SIZE_MB = 500
    ALLOWED_FILE_EXTENSIONS = ["csv", "xlsx", "xls", "tsv", "txt", "json", "parquet"]
    ALLOWED_MIME_TYPES = [
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/json",
        "application/octet-stream"
    ]
    
    # 数据限制
    MAX_DATASET_ROWS = 10_000_000
    MAX_DATASET_COLUMNS = 1000
    MAX_JOIN_OPERATIONS = 10
    MAX_RESULT_ROWS = 1_000_000
    
    # 字符串限制
    MAX_STRING_LENGTH = 1000
    MAX_NAME_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 2000
    
    # 分页限制
    MAX_PAGE_SIZE = 1000
    DEFAULT_PAGE_SIZE = 100
    
    # 连接相关限制
    MAX_SSE_CONNECTIONS_PER_USER = 10
    SSE_CONNECTION_TIMEOUT_SECONDS = 3600  # 1小时
    
    # 任务相关限制
    MAX_CONCURRENT_TASKS_PER_USER = 5
    TASK_RESULT_RETENTION_DAYS = 30


def validate_file_upload(file: UploadFile) -> None:
    """
    验证上传文件
    
    Args:
        file: 上传的文件对象
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not file.filename:
        raise ValidationAPIError("文件名不能为空")
    
    # 验证文件扩展名
    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in ValidationConfig.ALLOWED_FILE_EXTENSIONS:
        raise ValidationAPIError(
            f"不支持的文件格式 '.{file_ext}'。"
            f"支持的格式: {', '.join(ValidationConfig.ALLOWED_FILE_EXTENSIONS)}"
        )
    
    # 验证文件大小
    max_size_bytes = ValidationConfig.MAX_FILE_SIZE_MB * 1024 * 1024
    if hasattr(file, 'size') and file.size and file.size > max_size_bytes:
        raise ValidationAPIError(
            f"文件大小超过限制，最大允许 {ValidationConfig.MAX_FILE_SIZE_MB}MB"
        )
    
    # 验证MIME类型（如果可用）
    if file.content_type and file.content_type not in ValidationConfig.ALLOWED_MIME_TYPES:
        logger.warning(f"未知的MIME类型: {file.content_type}，文件: {file.filename}")
        # 不抛出异常，只记录警告


def validate_dataset_id(dataset_id: str) -> str:
    """
    验证数据集ID格式
    
    Args:
        dataset_id: 数据集ID
        
    Returns:
        验证通过的数据集ID
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not dataset_id or not dataset_id.strip():
        raise ValidationAPIError("数据集ID不能为空")
    
    dataset_id = dataset_id.strip()
    
    # 检查ID格式（字母、数字、下划线、连字符）
    if not re.match(r'^[a-zA-Z0-9_\-]+$', dataset_id):
        raise ValidationAPIError(
            "数据集ID只能包含字母、数字、下划线和连字符"
        )
    
    if len(dataset_id) > 50:
        raise ValidationAPIError("数据集ID长度不能超过50个字符")
    
    return dataset_id


def validate_task_id(task_id: str) -> str:
    """
    验证任务ID格式
    
    Args:
        task_id: 任务ID
        
    Returns:
        验证通过的任务ID
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not task_id or not task_id.strip():
        raise ValidationAPIError("任务ID不能为空")
    
    task_id = task_id.strip()
    
    # 任务ID格式验证
    if not re.match(r'^task_[a-zA-Z0-9]+$', task_id):
        raise ValidationAPIError("任务ID格式不正确")
    
    if len(task_id) > 50:
        raise ValidationAPIError("任务ID长度不能超过50个字符")
    
    return task_id


def validate_column_name(column_name: str) -> str:
    """
    验证列名格式
    
    Args:
        column_name: 列名
        
    Returns:
        验证通过的列名
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not column_name or not column_name.strip():
        raise ValidationAPIError("列名不能为空")
    
    column_name = column_name.strip()
    
    # 列名可以包含点号（用于表别名）
    if not re.match(r'^[a-zA-Z0-9_\.\u4e00-\u9fff]+$', column_name):
        raise ValidationAPIError(
            "列名只能包含字母、数字、下划线、点号和中文字符"
        )
    
    if len(column_name) > ValidationConfig.MAX_NAME_LENGTH:
        raise ValidationAPIError(f"列名长度不能超过{ValidationConfig.MAX_NAME_LENGTH}个字符")
    
    return column_name


def validate_column_list(columns: List[str]) -> List[str]:
    """
    验证列名列表
    
    Args:
        columns: 列名列表
        
    Returns:
        验证通过的列名列表
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not columns:
        return []
    
    if len(columns) > ValidationConfig.MAX_DATASET_COLUMNS:
        raise ValidationAPIError(f"列数不能超过{ValidationConfig.MAX_DATASET_COLUMNS}")
    
    validated_columns = []
    seen_columns = set()
    
    for column in columns:
        validated_column = validate_column_name(column)
        
        # 检查重复
        if validated_column in seen_columns:
            raise ValidationAPIError(f"列名重复: {validated_column}")
        
        seen_columns.add(validated_column)
        validated_columns.append(validated_column)
    
    return validated_columns


def validate_pagination_params(offset: int, limit: int) -> tuple:
    """
    验证分页参数
    
    Args:
        offset: 偏移量
        limit: 每页大小
        
    Returns:
        (验证通过的offset, limit)
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if offset < 0:
        raise ValidationAPIError("偏移量不能为负数")
    
    if limit <= 0:
        raise ValidationAPIError("每页大小必须大于0")
    
    if limit > ValidationConfig.MAX_PAGE_SIZE:
        raise ValidationAPIError(f"每页大小不能超过{ValidationConfig.MAX_PAGE_SIZE}")
    
    return offset, limit


def validate_search_query(search: Optional[str]) -> Optional[str]:
    """
    验证搜索查询参数
    
    Args:
        search: 搜索关键词
        
    Returns:
        验证通过的搜索关键词
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not search:
        return None
    
    search = search.strip()
    if not search:
        return None
    
    # 检查长度
    if len(search) > ValidationConfig.MAX_STRING_LENGTH:
        raise ValidationAPIError(f"搜索关键词长度不能超过{ValidationConfig.MAX_STRING_LENGTH}个字符")
    
    # 基本的SQL注入防护
    dangerous_patterns = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)',
        r'(--|/\*|\*/)',
        r'(\bOR\b.*=.*\b|\bAND\b.*=.*\b)'
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, search, re.IGNORECASE):
            raise ValidationAPIError("搜索关键词包含不允许的字符或关键词")
    
    return search


def validate_tags(tags: Optional[List[str]]) -> Optional[List[str]]:
    """
    验证标签列表
    
    Args:
        tags: 标签列表
        
    Returns:
        验证通过的标签列表
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not tags:
        return None
    
    if len(tags) > 20:  # 最多20个标签
        raise ValidationAPIError("标签数量不能超过20个")
    
    validated_tags = []
    seen_tags = set()
    
    for tag in tags:
        if not tag or not tag.strip():
            continue
        
        tag = tag.strip()
        
        # 标签长度检查
        if len(tag) > 50:
            raise ValidationAPIError("单个标签长度不能超过50个字符")
        
        # 标签格式检查
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff\s]+$', tag):
            raise ValidationAPIError("标签只能包含字母、数字、下划线、中文字符和空格")
        
        # 检查重复
        tag_lower = tag.lower()
        if tag_lower in seen_tags:
            continue  # 跳过重复标签
        
        seen_tags.add(tag_lower)
        validated_tags.append(tag)
    
    return validated_tags if validated_tags else None


def validate_preset_name(name: str) -> str:
    """
    验证预设名称
    
    Args:
        name: 预设名称
        
    Returns:
        验证通过的预设名称
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not name or not name.strip():
        raise ValidationAPIError("预设名称不能为空")
    
    name = name.strip()
    
    if len(name) > ValidationConfig.MAX_NAME_LENGTH:
        raise ValidationAPIError(f"预设名称长度不能超过{ValidationConfig.MAX_NAME_LENGTH}个字符")
    
    # 预设名称允许更多字符
    if not re.match(r'^[a-zA-Z0-9_\-\u4e00-\u9fff\s]+$', name):
        raise ValidationAPIError(
            "预设名称只能包含字母、数字、下划线、连字符、中文字符和空格"
        )
    
    return name


def validate_description(description: Optional[str]) -> Optional[str]:
    """
    验证描述文本
    
    Args:
        description: 描述文本
        
    Returns:
        验证通过的描述文本
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not description:
        return None
    
    description = description.strip()
    if not description:
        return None
    
    if len(description) > ValidationConfig.MAX_DESCRIPTION_LENGTH:
        raise ValidationAPIError(f"描述长度不能超过{ValidationConfig.MAX_DESCRIPTION_LENGTH}个字符")
    
    return description


def validate_join_operator(operator: str) -> str:
    """
    验证连接操作符
    
    Args:
        operator: 操作符
        
    Returns:
        验证通过的操作符
        
    Raises:
        ValidationAPIError: 验证失败
    """
    allowed_operators = ["=", "!=", "<", "<=", ">", ">=", "like", "ilike"]
    
    if operator not in allowed_operators:
        raise ValidationAPIError(
            f"不支持的操作符 '{operator}'。支持的操作符: {', '.join(allowed_operators)}"
        )
    
    return operator


def validate_export_format(format_type: str) -> str:
    """
    验证导出格式
    
    Args:
        format_type: 格式类型
        
    Returns:
        验证通过的格式类型
        
    Raises:
        ValidationAPIError: 验证失败
    """
    allowed_formats = ["json", "csv", "parquet", "xlsx"]
    
    if format_type not in allowed_formats:
        raise ValidationAPIError(
            f"不支持的导出格式 '{format_type}'。支持的格式: {', '.join(allowed_formats)}"
        )
    
    return format_type


def validate_sort_params(sort_by: str, sort_order: str, allowed_fields: List[str]) -> tuple:
    """
    验证排序参数
    
    Args:
        sort_by: 排序字段
        sort_order: 排序顺序
        allowed_fields: 允许的排序字段列表
        
    Returns:
        (验证通过的sort_by, sort_order)
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if sort_by not in allowed_fields:
        raise ValidationAPIError(
            f"不支持的排序字段 '{sort_by}'。支持的字段: {', '.join(allowed_fields)}"
        )
    
    if sort_order not in ["asc", "desc"]:
        raise ValidationAPIError(f"不支持的排序顺序 '{sort_order}'。支持: asc, desc")
    
    return sort_by, sort_order


# 装饰器：自动验证函数参数
def validate_params(**validators):
    """
    参数验证装饰器
    
    Args:
        **validators: 参数验证器字典，键为参数名，值为验证函数
    
    Example:
        @validate_params(
            dataset_id=validate_dataset_id,
            columns=validate_column_list
        )
        def my_function(dataset_id: str, columns: List[str]):
            pass
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # 验证kwargs中的参数
            for param_name, validator_func in validators.items():
                if param_name in kwargs:
                    try:
                        kwargs[param_name] = validator_func(kwargs[param_name])
                    except ValidationAPIError:
                        raise
                    except Exception as e:
                        raise ValidationAPIError(f"参数 '{param_name}' 验证失败: {str(e)}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Pydantic验证器工厂
def create_string_validator(
    min_length: int = 0,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    allow_empty: bool = False
):
    """
    创建字符串验证器
    
    Args:
        min_length: 最小长度
        max_length: 最大长度
        pattern: 正则表达式模式
        allow_empty: 是否允许空字符串
    
    Returns:
        Pydantic验证器函数
    """
    def string_validator(cls, v):
        if v is None:
            return v
        
        if not isinstance(v, str):
            raise ValueError("必须是字符串类型")
        
        if not allow_empty and not v.strip():
            raise ValueError("不能为空字符串")
        
        v = v.strip()
        
        if len(v) < min_length:
            raise ValueError(f"长度不能少于{min_length}个字符")
        
        if max_length and len(v) > max_length:
            raise ValueError(f"长度不能超过{max_length}个字符")
        
        if pattern and not re.match(pattern, v):
            raise ValueError("格式不符合要求")
        
        return v
    
    return validator('*', pre=True, allow_reuse=True)(string_validator)


def create_list_validator(
    min_items: int = 0,
    max_items: Optional[int] = None,
    item_validator: Optional[Callable] = None
):
    """
    创建列表验证器
    
    Args:
        min_items: 最少项目数
        max_items: 最多项目数
        item_validator: 项目验证函数
    
    Returns:
        Pydantic验证器函数
    """
    def list_validator(cls, v):
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("必须是列表类型")
        
        if len(v) < min_items:
            raise ValueError(f"列表项目不能少于{min_items}个")
        
        if max_items and len(v) > max_items:
            raise ValueError(f"列表项目不能超过{max_items}个")
        
        if item_validator:
            validated_items = []
            for i, item in enumerate(v):
                try:
                    validated_items.append(item_validator(item))
                except Exception as e:
                    raise ValueError(f"第{i+1}个项目验证失败: {str(e)}")
            return validated_items
        
        return v
    
    return validator('*', pre=True, allow_reuse=True)(list_validator)