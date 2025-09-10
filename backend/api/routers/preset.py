"""
配置预设路由器

提供连接配置预设的CRUD操作API端点
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, Body

from ..middleware.auth import get_current_user, User
from ..middleware.error_handler import APIError, ValidationAPIError, NotFoundAPIError
from ...models.api.request_models import PresetSaveRequest, PresetListRequest
from ...models.api.response_models import (
    PresetSaveResponse, PresetListResponse, APIResponse, PresetInfo
)

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter()


@router.post(
    "/save",
    response_model=PresetSaveResponse,
    summary="保存连接预设",
    description="保存连接操作配置为预设，便于重复使用",
    response_description="返回保存的预设信息"
)
async def save_preset(
    request: PresetSaveRequest = Body(..., description="预设保存请求"),
    current_user: User = Depends(get_current_user)
):
    """
    保存连接配置预设
    
    功能：
    - 保存连接操作配置
    - 支持公开/私有预设
    - 标签分类管理
    - 描述信息记录
    
    预设可以被重复使用，提高工作效率
    """
    logger.info(f"用户 {current_user.user_id} 保存预设: {request.name}")
    
    try:
        # 验证预设名称唯一性（用户范围内）
        # TODO: 实现预设服务调用
        # existing_preset = await preset_service.get_preset_by_name(
        #     name=request.name,
        #     user_id=current_user.user_id
        # )
        # if existing_preset:
        #     raise ValidationAPIError(f"预设名称 '{request.name}' 已存在")
        
        # 验证连接操作的有效性
        await _validate_preset_operations(request.operations, current_user.user_id)
        
        # 保存预设
        # TODO: 实现预设服务调用
        # preset = await preset_service.save_preset(
        #     name=request.name,
        #     description=request.description,
        #     operations=request.operations,
        #     output_columns=request.output_columns,
        #     tags=request.tags,
        #     is_public=request.is_public,
        #     user_id=current_user.user_id
        # )
        
        # 临时模拟预设信息
        preset_info = PresetInfo(
            preset_id="preset_temp_123",
            name=request.name,
            description=request.description,
            user_id=current_user.user_id,
            is_public=request.is_public,
            tags=request.tags or [],
            usage_count=0,
            created_at="2025-09-10T10:00:00Z",
            updated_at="2025-09-10T10:00:00Z"
        )
        
        logger.info(f"预设保存成功: {preset_info.preset_id}")
        
        return PresetSaveResponse(
            message=f"预设 '{request.name}' 保存成功",
            preset=preset_info
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"预设保存失败: {str(e)}")
        raise APIError(
            message=f"预设保存失败: {str(e)}",
            error_code="PRESET_SAVE_FAILED",
            status_code=500
        )


@router.get(
    "/list",
    response_model=PresetListResponse,
    summary="列出配置预设",
    description="获取用户的配置预设列表，支持搜索和分页",
    response_description="返回预设列表和分页信息"
)
async def list_presets(
    offset: int = Query(0, ge=0, description="分页偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数（最大100）"),
    search: Optional[str] = Query(None, description="搜索关键词（名称、描述、标签）"),
    tags: Optional[List[str]] = Query(None, description="标签过滤"),
    is_public: Optional[bool] = Query(None, description="是否只显示公开预设"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序顺序 (asc, desc)"),
    current_user: User = Depends(get_current_user)
):
    """
    获取配置预设列表
    
    功能：
    - 分页查询
    - 关键词搜索
    - 标签过滤
    - 公开/私有筛选
    - 多种排序选项
    """
    logger.info(f"用户 {current_user.user_id} 获取预设列表")
    
    try:
        # 验证排序参数
        allowed_sort_fields = ["name", "created_at", "updated_at", "usage_count"]
        if sort_by not in allowed_sort_fields:
            raise ValidationAPIError(f"无效的排序字段: {sort_by}")
        
        if sort_order not in ["asc", "desc"]:
            raise ValidationAPIError(f"无效的排序顺序: {sort_order}")
        
        # 获取预设列表
        # TODO: 实现预设服务调用
        # presets_result = await preset_service.list_presets(
        #     user_id=current_user.user_id,
        #     offset=offset,
        #     limit=limit,
        #     search=search,
        #     tags=tags,
        #     is_public=is_public,
        #     sort_by=sort_by,
        #     sort_order=sort_order
        # )
        
        # 临时模拟预设列表
        presets = [
            PresetInfo(
                preset_id=f"preset_{i}",
                name=f"预设配置 {i}",
                description=f"这是第 {i} 个预设配置的描述",
                user_id=current_user.user_id,
                is_public=i % 3 == 0,  # 每三个一个公开
                tags=["数据连接", f"标签{i}"],
                usage_count=i * 5,
                created_at="2025-09-10T10:00:00Z",
                updated_at="2025-09-10T10:00:00Z"
            )
            for i in range(1, min(limit + 1, 11))
        ]
        
        # 如果有搜索关键词，过滤结果
        if search:
            search_lower = search.lower()
            presets = [
                p for p in presets 
                if search_lower in p.name.lower() 
                or (p.description and search_lower in p.description.lower())
                or any(search_lower in tag.lower() for tag in p.tags)
            ]
        
        total = 50  # 临时总数
        
        return PresetListResponse(
            total=total,
            offset=offset,
            limit=limit,
            has_more=(offset + limit) < total,
            presets=presets
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"获取预设列表失败: {str(e)}")
        raise APIError(
            message=f"获取预设列表失败: {str(e)}",
            error_code="PRESET_LIST_FAILED",
            status_code=500
        )


@router.get(
    "/{preset_id}",
    response_model=dict,  # 预设详情包含完整的操作配置
    summary="获取预设详情",
    description="获取指定预设的完整配置信息",
    response_description="返回预设的详细信息和操作配置"
)
async def get_preset(
    preset_id: str = Path(..., description="预设ID"),
    current_user: User = Depends(get_current_user)
):
    """
    获取预设的详细信息
    
    返回预设的完整配置，包括：
    - 基础信息
    - 连接操作配置
    - 输出列配置
    - 标签和描述
    """
    logger.info(f"用户 {current_user.user_id} 获取预设详情: {preset_id}")
    
    try:
        # 获取预设详情
        # TODO: 实现预设服务调用
        # preset = await preset_service.get_preset_detail(preset_id, current_user.user_id)
        # if not preset:
        #     raise NotFoundAPIError("Preset", preset_id)
        
        # 检查访问权限（公开预设或用户自己的预设）
        # if not preset.is_public and preset.user_id != current_user.user_id:
        #     raise APIError(
        #         message="没有访问此预设的权限",
        #         error_code="PRESET_ACCESS_DENIED",
        #         status_code=403
        #     )
        
        # 临时模拟预设详情
        preset_detail = {
            "preset_info": {
                "preset_id": preset_id,
                "name": "用户订单关联查询",
                "description": "关联用户表和订单表，获取用户的订单信息",
                "user_id": current_user.user_id,
                "is_public": False,
                "tags": ["用户", "订单", "关联查询"],
                "usage_count": 15,
                "created_at": "2025-09-10T09:00:00Z",
                "updated_at": "2025-09-10T10:00:00Z"
            },
            "operations": [
                {
                    "left_dataset": {
                        "dataset_id": "ds_users",
                        "alias": "u",
                        "columns": ["id", "name", "email"]
                    },
                    "right_dataset": {
                        "dataset_id": "ds_orders",
                        "alias": "o",
                        "columns": ["user_id", "amount", "created_at"]
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
            ],
            "output_columns": ["u.name", "u.email", "o.amount", "o.created_at"]
        }
        
        # 增加使用次数
        # TODO: 实现使用次数更新
        # await preset_service.increment_usage_count(preset_id)
        
        return preset_detail
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"获取预设详情失败: {str(e)}")
        raise APIError(
            message=f"获取预设详情失败: {str(e)}",
            error_code="PRESET_GET_FAILED",
            status_code=500
        )


@router.put(
    "/{preset_id}",
    response_model=PresetSaveResponse,
    summary="更新预设",
    description="更新指定预设的配置信息",
    response_description="返回更新后的预设信息"
)
async def update_preset(
    preset_id: str = Path(..., description="预设ID"),
    request: PresetSaveRequest = Body(..., description="预设更新请求"),
    current_user: User = Depends(get_current_user)
):
    """
    更新配置预设
    
    只有预设的创建者可以更新预设
    更新后的预设保持相同的ID和创建时间
    """
    logger.info(f"用户 {current_user.user_id} 更新预设: {preset_id}")
    
    try:
        # 获取现有预设并验证权限
        # TODO: 实现预设服务调用
        # existing_preset = await preset_service.get_preset(preset_id)
        # if not existing_preset:
        #     raise NotFoundAPIError("Preset", preset_id)
        
        # if existing_preset.user_id != current_user.user_id:
        #     raise APIError(
        #         message="只能更新自己创建的预设",
        #         error_code="PRESET_UPDATE_DENIED",
        #         status_code=403
        #     )
        
        # 检查名称冲突（排除当前预设）
        # existing_name_preset = await preset_service.get_preset_by_name(
        #     name=request.name,
        #     user_id=current_user.user_id,
        #     exclude_preset_id=preset_id
        # )
        # if existing_name_preset:
        #     raise ValidationAPIError(f"预设名称 '{request.name}' 已存在")
        
        # 验证连接操作
        await _validate_preset_operations(request.operations, current_user.user_id)
        
        # 更新预设
        # TODO: 实现预设服务调用
        # preset = await preset_service.update_preset(
        #     preset_id=preset_id,
        #     name=request.name,
        #     description=request.description,
        #     operations=request.operations,
        #     output_columns=request.output_columns,
        #     tags=request.tags,
        #     is_public=request.is_public,
        #     user_id=current_user.user_id
        # )
        
        # 临时模拟更新后的预设
        preset_info = PresetInfo(
            preset_id=preset_id,
            name=request.name,
            description=request.description,
            user_id=current_user.user_id,
            is_public=request.is_public,
            tags=request.tags or [],
            usage_count=15,  # 保持原有使用次数
            created_at="2025-09-10T09:00:00Z",  # 保持原有创建时间
            updated_at="2025-09-10T10:00:00Z"   # 更新时间
        )
        
        logger.info(f"预设更新成功: {preset_id}")
        
        return PresetSaveResponse(
            message=f"预设 '{request.name}' 更新成功",
            preset=preset_info
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"预设更新失败: {str(e)}")
        raise APIError(
            message=f"预设更新失败: {str(e)}",
            error_code="PRESET_UPDATE_FAILED",
            status_code=500
        )


@router.delete(
    "/{preset_id}",
    response_model=APIResponse,
    summary="删除预设",
    description="删除指定的配置预设",
    response_description="返回删除操作结果"
)
async def delete_preset(
    preset_id: str = Path(..., description="预设ID"),
    current_user: User = Depends(get_current_user)
):
    """
    删除配置预设
    
    只有预设的创建者可以删除预设
    删除操作不可恢复
    """
    logger.info(f"用户 {current_user.user_id} 删除预设: {preset_id}")
    
    try:
        # 获取预设并验证权限
        # TODO: 实现预设服务调用
        # preset = await preset_service.get_preset(preset_id)
        # if not preset:
        #     raise NotFoundAPIError("Preset", preset_id)
        
        # if preset.user_id != current_user.user_id:
        #     raise APIError(
        #         message="只能删除自己创建的预设",
        #         error_code="PRESET_DELETE_DENIED",
        #         status_code=403
        #     )
        
        # 删除预设
        # TODO: 实现预设服务调用
        # await preset_service.delete_preset(preset_id, current_user.user_id)
        
        logger.info(f"预设删除成功: {preset_id}")
        
        return APIResponse(
            message=f"预设 {preset_id} 删除成功"
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"预设删除失败: {str(e)}")
        raise APIError(
            message=f"预设删除失败: {str(e)}",
            error_code="PRESET_DELETE_FAILED",
            status_code=500
        )


@router.post(
    "/{preset_id}/clone",
    response_model=PresetSaveResponse,
    summary="克隆预设",
    description="克隆指定预设创建新的预设副本",
    response_description="返回新创建的预设信息"
)
async def clone_preset(
    preset_id: str = Path(..., description="要克隆的预设ID"),
    new_name: str = Body(..., description="新预设名称", embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    克隆配置预设
    
    可以克隆任何可访问的预设（自己的或公开的）
    克隆的预设会成为当前用户的私有预设
    """
    logger.info(f"用户 {current_user.user_id} 克隆预设: {preset_id} -> {new_name}")
    
    try:
        # 获取源预设
        # TODO: 实现预设服务调用
        # source_preset = await preset_service.get_preset_detail(preset_id, current_user.user_id)
        # if not source_preset:
        #     raise NotFoundAPIError("Preset", preset_id)
        
        # 检查访问权限
        # if not source_preset.is_public and source_preset.user_id != current_user.user_id:
        #     raise APIError(
        #         message="没有访问此预设的权限",
        #         error_code="PRESET_ACCESS_DENIED",
        #         status_code=403
        #     )
        
        # 检查新名称是否冲突
        # existing_preset = await preset_service.get_preset_by_name(
        #     name=new_name,
        #     user_id=current_user.user_id
        # )
        # if existing_preset:
        #     raise ValidationAPIError(f"预设名称 '{new_name}' 已存在")
        
        # 克隆预设
        # TODO: 实现预设服务调用
        # cloned_preset = await preset_service.clone_preset(
        #     source_preset_id=preset_id,
        #     new_name=new_name,
        #     user_id=current_user.user_id
        # )
        
        # 临时模拟克隆的预设
        preset_info = PresetInfo(
            preset_id="preset_cloned_456",
            name=new_name,
            description=f"克隆自预设 {preset_id}",
            user_id=current_user.user_id,
            is_public=False,  # 克隆的预设默认为私有
            tags=["克隆", "数据连接"],
            usage_count=0,
            created_at="2025-09-10T10:00:00Z",
            updated_at="2025-09-10T10:00:00Z"
        )
        
        logger.info(f"预设克隆成功: {preset_info.preset_id}")
        
        return PresetSaveResponse(
            message=f"预设 '{new_name}' 克隆成功",
            preset=preset_info
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"预设克隆失败: {str(e)}")
        raise APIError(
            message=f"预设克隆失败: {str(e)}",
            error_code="PRESET_CLONE_FAILED",
            status_code=500
        )


async def _validate_preset_operations(operations: list, user_id: str) -> None:
    """
    验证预设中连接操作的有效性
    
    Args:
        operations: 连接操作列表
        user_id: 用户ID
        
    Raises:
        ValidationAPIError: 验证失败
    """
    if not operations:
        raise ValidationAPIError("预设必须包含至少一个连接操作")
    
    if len(operations) > 10:
        raise ValidationAPIError("连接操作数量不能超过10个")
    
    # 验证每个操作的基本结构
    for i, operation in enumerate(operations):
        if not hasattr(operation, 'left_dataset') or not hasattr(operation, 'right_dataset'):
            raise ValidationAPIError(f"操作 {i+1} 缺少数据集信息")
        
        if not hasattr(operation, 'conditions') or not operation.conditions:
            raise ValidationAPIError(f"操作 {i+1} 缺少连接条件")
        
        # TODO: 这里可以进一步验证数据集是否存在、列是否有效等
        # 但由于我们还没有实现服务层，暂时跳过这些验证