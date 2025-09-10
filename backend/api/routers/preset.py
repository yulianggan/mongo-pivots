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
from ...services.preset_service import preset_service

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
        # 验证连接操作的有效性
        await _validate_preset_operations(request.operations, current_user.user_id)
        
        # 保存预设
        preset_info = await preset_service.save_preset(
            name=request.name,
            description=request.description,
            operations=request.operations,
            output_columns=request.output_columns,
            tags=request.tags,
            is_public=request.is_public,
            user_id=current_user.user_id
        )
        
        logger.info(f"预设保存成功: {preset_info.preset_id}")
        
        return PresetSaveResponse(
            message=f"预设 '{request.name}' 保存成功",
            preset=preset_info
        )
        
    except APIError:
        raise
    except ValueError as e:
        logger.warning(f"预设保存验证失败: {str(e)}")
        raise ValidationAPIError(str(e))
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
        presets_result = await preset_service.list_presets(
            user_id=current_user.user_id,
            offset=offset,
            limit=limit,
            search=search,
            tags=tags,
            is_public=is_public,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return PresetListResponse(
            total=presets_result["total"],
            offset=presets_result["offset"],
            limit=presets_result["limit"],
            has_more=presets_result["has_more"],
            presets=presets_result["presets"]
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
        preset_detail = await preset_service.get_preset_detail(preset_id, current_user.user_id)
        if not preset_detail:
            raise NotFoundAPIError("Preset", preset_id)
        
        # 增加使用次数
        await preset_service.increment_usage_count(preset_id)
        
        # 格式化返回数据
        return {
            "preset_info": {
                k: v for k, v in preset_detail.items() 
                if k not in ["operations", "output_columns"]
            },
            "operations": preset_detail["operations"],
            "output_columns": preset_detail["output_columns"]
        }
        
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
        # 验证连接操作
        await _validate_preset_operations(request.operations, current_user.user_id)
        
        # 更新预设
        preset_info = await preset_service.update_preset(
            preset_id=preset_id,
            name=request.name,
            description=request.description,
            operations=request.operations,
            output_columns=request.output_columns,
            tags=request.tags,
            is_public=request.is_public,
            user_id=current_user.user_id
        )
        
        logger.info(f"预设更新成功: {preset_id}")
        
        return PresetSaveResponse(
            message=f"预设 '{request.name}' 更新成功",
            preset=preset_info
        )
        
    except APIError:
        raise
    except ValueError as e:
        logger.warning(f"预设更新验证失败: {str(e)}")
        raise ValidationAPIError(str(e))
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
        # 删除预设
        await preset_service.delete_preset(preset_id, current_user.user_id)
        
        logger.info(f"预设删除成功: {preset_id}")
        
        return APIResponse(
            message=f"预设 {preset_id} 删除成功"
        )
        
    except APIError:
        raise
    except ValueError as e:
        logger.warning(f"预设删除验证失败: {str(e)}")
        raise ValidationAPIError(str(e))
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
        # 克隆预设
        cloned_preset = await preset_service.clone_preset(
            source_preset_id=preset_id,
            new_name=new_name,
            user_id=current_user.user_id
        )
        
        logger.info(f"预设克隆成功: {cloned_preset.preset_id}")
        
        return PresetSaveResponse(
            message=f"预设 '{new_name}' 克隆成功",
            preset=cloned_preset
        )
        
    except APIError:
        raise
    except ValueError as e:
        logger.warning(f"预设克隆验证失败: {str(e)}")
        raise ValidationAPIError(str(e))
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


@router.get(
    "/templates",
    response_model=dict,
    summary="获取预设模板",
    description="获取可用的预设模板列表",
    response_description="返回预设模板列表"
)
async def get_preset_templates(
    current_user: User = Depends(get_current_user)
):
    """
    获取预设模板列表
    
    返回系统提供的预设模板，用户可以基于这些模板快速创建预设
    """
    logger.info(f"用户 {current_user.user_id} 获取预设模板")
    
    try:
        templates = await preset_service.get_preset_templates()
        
        return {
            "success": True,
            "message": "获取预设模板成功",
            "templates": templates
        }
        
    except Exception as e:
        logger.error(f"获取预设模板失败: {str(e)}")
        raise APIError(
            message=f"获取预设模板失败: {str(e)}",
            error_code="PRESET_TEMPLATES_FAILED",
            status_code=500
        )


@router.get(
    "/popular",
    response_model=dict,
    summary="获取热门预设",
    description="获取使用次数最多的预设列表",
    response_description="返回热门预设列表"
)
async def get_popular_presets(
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    current_user: User = Depends(get_current_user)
):
    """
    获取热门预设
    
    返回按使用次数排序的热门预设列表
    """
    logger.info(f"用户 {current_user.user_id} 获取热门预设")
    
    try:
        popular_presets = await preset_service.get_popular_presets(
            user_id=current_user.user_id,
            limit=limit
        )
        
        return {
            "success": True,
            "message": "获取热门预设成功",
            "presets": popular_presets
        }
        
    except Exception as e:
        logger.error(f"获取热门预设失败: {str(e)}")
        raise APIError(
            message=f"获取热门预设失败: {str(e)}",
            error_code="POPULAR_PRESETS_FAILED",
            status_code=500
        )


@router.get(
    "/recent",
    response_model=dict,
    summary="获取最近预设",
    description="获取最近创建的预设列表",
    response_description="返回最近预设列表"
)
async def get_recent_presets(
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    current_user: User = Depends(get_current_user)
):
    """
    获取最近创建的预设
    
    返回按创建时间排序的最近预设列表
    """
    logger.info(f"用户 {current_user.user_id} 获取最近预设")
    
    try:
        recent_presets = await preset_service.get_recent_presets(
            user_id=current_user.user_id,
            limit=limit
        )
        
        return {
            "success": True,
            "message": "获取最近预设成功",
            "presets": recent_presets
        }
        
    except Exception as e:
        logger.error(f"获取最近预设失败: {str(e)}")
        raise APIError(
            message=f"获取最近预设失败: {str(e)}",
            error_code="RECENT_PRESETS_FAILED",
            status_code=500
        )