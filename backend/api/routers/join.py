"""
连接操作路由器

提供数据连接预览、执行、状态查询和结果获取功能的API端点
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Body
from fastapi.responses import StreamingResponse

from ..middleware.auth import get_current_user, User
from ..middleware.error_handler import APIError, ValidationAPIError, NotFoundAPIError
from ...models.api.request_models import (
    JoinPreviewRequest, JoinExecuteRequest, TaskStatusRequest, ResultRequest
)
from ...models.api.response_models import (
    JoinPreviewResponse, JoinExecuteResponse, TaskStatusResponse, 
    ResultResponse, ResourceEstimate, TaskProgress, TaskStatus
)
from ...services.join_service import JoinService
from ...join_engine import JoinEngineError, JoinPlanningError, JoinExecutionError

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter()

# 创建连接服务实例
join_service = JoinService()


@router.post(
    "/preview",
    response_model=JoinPreviewResponse,
    summary="预览连接结果",
    description="预览数据连接操作的结果样本和资源估算，不执行完整连接",
    response_description="返回预览数据、资源估算和执行计划"
)
async def preview_join(
    request: JoinPreviewRequest = Body(..., description="连接预览请求"),
    current_user: User = Depends(get_current_user)
):
    """
    预览数据连接结果
    
    功能：
    - 连接操作预览
    - 资源使用估算
    - 执行计划生成
    - 潜在问题警告
    
    注意：仅返回样本数据，不会执行完整的连接操作
    """
    logger.info(f"用户 {current_user.user_id} 预览连接操作")
    
    try:
        # 验证连接请求
        await _validate_join_request(request.operations, current_user.user_id)
        
        # 调用连接服务生成预览
        preview_result = await join_service.generate_preview(
            operations=request.operations,
            output_columns=request.output_columns,
            sample_size=request.sample_size,
            user_id=current_user.user_id
        )
        
        logger.info(f"连接预览生成成功，预估 {preview_result['resource_estimate'].estimated_rows} 行结果")
        
        return JoinPreviewResponse(
            message=f"连接预览生成成功，预估产生 {preview_result['resource_estimate'].estimated_rows} 行结果",
            preview_data=preview_result["preview_data"],
            resource_estimate=preview_result["resource_estimate"],
            plan=preview_result["plan"],
            warnings=preview_result["warnings"]
        )
        
    except APIError:
        raise
    except JoinPlanningError as e:
        logger.error(f"连接计划失败: {str(e)}")
        raise ValidationAPIError(f"连接计划失败: {str(e)}")
    except JoinExecutionError as e:
        logger.error(f"连接预览执行失败: {str(e)}")
        raise APIError(
            message=f"连接预览执行失败: {str(e)}",
            error_code="PREVIEW_EXECUTION_FAILED",
            status_code=500
        )
    except JoinEngineError as e:
        logger.error(f"连接引擎错误: {str(e)}")
        raise APIError(
            message=f"连接引擎错误: {str(e)}",
            error_code="JOIN_ENGINE_ERROR",
            status_code=500
        )
    except Exception as e:
        logger.error(f"连接预览失败: {str(e)}")
        raise APIError(
            message=f"连接预览失败: {str(e)}",
            error_code="PREVIEW_FAILED",
            status_code=500
        )


@router.post(
    "/execute",
    response_model=JoinExecuteResponse,
    summary="执行连接任务",
    description="创建并启动数据连接任务，返回任务ID用于状态追踪",
    response_description="返回任务ID和初始状态信息"
)
async def execute_join(
    request: JoinExecuteRequest = Body(..., description="连接执行请求"),
    current_user: User = Depends(get_current_user)
):
    """
    执行数据连接任务
    
    功能：
    - 创建异步连接任务
    - 支持大数据集处理
    - 分块处理和进度跟踪
    - 结果持久化存储
    
    返回任务ID，可通过状态查询API跟踪进度
    """
    logger.info(f"用户 {current_user.user_id} 执行连接任务")
    
    try:
        # 验证连接请求
        await _validate_join_request(request.operations, current_user.user_id)
        
        # 检查用户权限和资源配额
        # TODO: 实现配额检查
        # await quota_service.check_user_quota(current_user.user_id)
        
        # 创建连接任务
        task_id = await join_service.create_join_task(
            operations=request.operations,
            output_columns=request.output_columns,
            result_name=request.result_name,
            save_result=request.save_result,
            chunk_size=request.chunk_size,
            user_id=current_user.user_id
        )
        
        # 获取任务状态信息
        task_info = await join_service.get_task_status(task_id, current_user.user_id)
        
        # 估算完成时间（基于资源估算）
        from datetime import datetime, timedelta
        estimated_completion = datetime.utcnow() + timedelta(minutes=5)  # 默认5分钟
        
        logger.info(f"连接任务创建成功: {task_id}")
        
        return JoinExecuteResponse(
            message=f"连接任务 {task_id} 创建成功，正在处理中",
            task_id=task_id,
            estimated_completion=estimated_completion.isoformat() + "Z",
            status=task_info.status if task_info else TaskStatus.PENDING,
            progress=task_info.progress if task_info else TaskProgress(
                current_step="初始化任务",
                step_index=1,
                total_steps=6,
                progress_percent=0.0,
                processed_rows=0,
                total_rows=None
            )
        )
        
    except APIError:
        raise
    except RuntimeError as e:
        logger.error(f"任务创建失败: {str(e)}")
        raise APIError(
            message=str(e),
            error_code="TASK_CREATION_FAILED",
            status_code=409
        )
    except JoinPlanningError as e:
        logger.error(f"连接计划失败: {str(e)}")
        raise ValidationAPIError(f"连接计划失败: {str(e)}")
    except JoinEngineError as e:
        logger.error(f"连接引擎错误: {str(e)}")
        raise APIError(
            message=f"连接引擎错误: {str(e)}",
            error_code="JOIN_ENGINE_ERROR",
            status_code=500
        )
    except Exception as e:
        logger.error(f"连接任务创建失败: {str(e)}")
        raise APIError(
            message=f"连接任务创建失败: {str(e)}",
            error_code="EXECUTION_FAILED",
            status_code=500
        )


@router.get(
    "/status/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询任务状态",
    description="获取连接任务的当前状态和进度信息",
    response_description="返回任务状态、进度和结果信息"
)
async def get_task_status(
    task_id: str = Path(..., description="任务ID"),
    current_user: User = Depends(get_current_user)
):
    """
    查询连接任务状态
    
    返回信息：
    - 任务执行状态
    - 当前进度百分比
    - 处理步骤信息
    - 错误信息（如果失败）
    - 结果ID（如果完成）
    """
    logger.debug(f"用户 {current_user.user_id} 查询任务状态: {task_id}")
    
    try:
        # 获取任务状态
        task_info = await join_service.get_task_status(task_id, current_user.user_id)
        if not task_info:
            raise NotFoundAPIError("Task", task_id)
        
        return TaskStatusResponse(
            task_id=task_id,
            status=task_info.status,
            progress=task_info.progress,
            started_at=task_info.started_at.isoformat() + "Z" if task_info.started_at else None,
            completed_at=task_info.completed_at.isoformat() + "Z" if task_info.completed_at else None,
            result_id=task_info.result_id,
            error_message=task_info.error_message
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        raise APIError(
            message=f"查询任务状态失败: {str(e)}",
            error_code="STATUS_QUERY_FAILED",
            status_code=500
        )


@router.get(
    "/result/{result_id}",
    response_model=ResultResponse,
    summary="获取连接结果",
    description="分页获取连接任务的结果数据",
    response_description="返回结果元数据和分页数据"
)
async def get_join_result(
    result_id: str = Path(..., description="结果ID"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
    limit: int = Query(100, ge=1, le=1000, description="每页记录数（最大1000）"),
    columns: Optional[str] = Query(None, description="指定输出列，逗号分隔"),
    format: str = Query("json", description="输出格式 (json, csv, parquet)"),
    current_user: User = Depends(get_current_user)
):
    """
    获取连接结果数据
    
    功能：
    - 分页查询结果
    - 列筛选
    - 多种导出格式
    - 结果缓存机制
    """
    logger.info(f"用户 {current_user.user_id} 获取连接结果: {result_id}")
    
    try:
        # 验证格式
        if format not in ["json", "csv", "parquet"]:
            raise ValidationAPIError("不支持的输出格式")
        
        # 解析列参数
        selected_columns = None
        if columns:
            selected_columns = [col.strip() for col in columns.split(",")]
        
        # 获取结果数据
        result = await join_service.get_result(
            result_id=result_id,
            offset=offset,
            limit=limit,
            columns=selected_columns,
            user_id=current_user.user_id
        )
        if not result:
            raise NotFoundAPIError("Result", result_id)
        
        # 如果请求非JSON格式，返回文件流
        if format != "json":
            return await _export_result_as_file(
                result_id=result_id,
                format=format,
                offset=offset,
                limit=limit,
                columns=selected_columns,
                current_user=current_user
            )
        
        return ResultResponse(
            total=result["metadata"].rows,
            offset=offset,
            limit=limit,
            has_more=(offset + limit) < result["metadata"].rows,
            metadata=result["metadata"],
            data=result["data"],
            columns=result["columns"]
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"获取连接结果失败: {str(e)}")
        raise APIError(
            message=f"获取连接结果失败: {str(e)}",
            error_code="RESULT_FETCH_FAILED",
            status_code=500
        )


@router.delete(
    "/task/{task_id}",
    summary="取消任务",
    description="取消正在执行的连接任务",
    response_description="返回取消操作结果"
)
async def cancel_task(
    task_id: str = Path(..., description="任务ID"),
    current_user: User = Depends(get_current_user)
):
    """
    取消连接任务
    
    只有正在执行的任务可以被取消
    已完成或失败的任务无法取消
    """
    logger.info(f"用户 {current_user.user_id} 取消任务: {task_id}")
    
    try:
        # 获取任务信息并验证权限
        task_info = await join_service.get_task_status(task_id, current_user.user_id)
        if not task_info:
            raise NotFoundAPIError("Task", task_id)
        
        # 检查任务状态
        if task_info.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise APIError(
                message=f"任务状态为 {task_info.status.value}，无法取消",
                error_code="TASK_NOT_CANCELLABLE",
                status_code=409
            )
        
        # 取消任务
        success = await join_service.cancel_task(task_id, current_user.user_id)
        
        if not success:
            raise APIError(
                message="任务取消失败",
                error_code="CANCELLATION_FAILED",
                status_code=500
            )
        
        logger.info(f"任务取消成功: {task_id}")
        
        return {"message": f"任务 {task_id} 已取消"}
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"任务取消失败: {str(e)}")
        raise APIError(
            message=f"任务取消失败: {str(e)}",
            error_code="CANCELLATION_FAILED",
            status_code=500
        )


async def _validate_join_request(operations: list, user_id: str) -> None:
    """
    验证连接请求的有效性
    
    Args:
        operations: 连接操作列表
        user_id: 用户ID
        
    Raises:
        ValidationAPIError: 验证失败
        NotFoundAPIError: 数据集不存在
    """
    if not operations:
        raise ValidationAPIError("连接操作列表不能为空")
    
    if len(operations) > 10:
        raise ValidationAPIError("连接操作数量不能超过10个")
    
    # 验证每个操作
    for i, operation in enumerate(operations):
        # 验证数据集存在
        # TODO: 实现数据集验证
        # left_dataset_exists = await dataset_service.dataset_exists(
        #     operation.left_dataset.dataset_id, user_id
        # )
        # right_dataset_exists = await dataset_service.dataset_exists(
        #     operation.right_dataset.dataset_id, user_id
        # )
        # 
        # if not left_dataset_exists:
        #     raise NotFoundAPIError(
        #         "Dataset", 
        #         operation.left_dataset.dataset_id
        #     )
        # if not right_dataset_exists:
        #     raise NotFoundAPIError(
        #         "Dataset", 
        #         operation.right_dataset.dataset_id
        #     )
        
        # 验证连接条件
        if not operation.conditions:
            raise ValidationAPIError(f"操作 {i+1} 缺少连接条件")
        
        # TODO: 验证列是否存在于相应的数据集中
        pass


async def _export_result_as_file(
    result_id: str,
    format: str,
    offset: int,
    limit: int,
    columns: Optional[list],
    current_user: User
) -> StreamingResponse:
    """
    将结果导出为文件流
    
    Args:
        result_id: 结果ID
        format: 导出格式
        offset: 偏移量
        limit: 限制数量
        columns: 选择的列
        current_user: 当前用户
        
    Returns:
        文件流响应
    """
    # TODO: 实现结果导出
    # file_stream = await result_service.export_result(
    #     result_id=result_id,
    #     format=format,
    #     offset=offset,
    #     limit=limit,
    #     columns=columns,
    #     user_id=current_user.user_id
    # )
    
    # 临时模拟文件内容
    if format == "csv":
        content = "u.id,u.name,u.email,o.amount\n1,Alice,alice@example.com,99.99\n"
        content_type = "text/csv"
    elif format == "parquet":
        content = "binary_parquet_data"  # 实际应该是二进制数据
        content_type = "application/octet-stream"
    
    filename = f"{result_id}_{offset}_{limit}.{format}"
    
    def generate():
        yield content.encode() if isinstance(content, str) else content
    
    return StreamingResponse(
        generate(),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )