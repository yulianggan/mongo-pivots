"""
SSE进度推送路由器

提供Server-Sent Events实时进度推送功能
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from ..middleware.auth import get_current_user, User
from ..middleware.error_handler import APIError, NotFoundAPIError
from ...services.sse_service import sse_service
from ...services.join_service import JoinService

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter()

# 创建JoinService实例
join_service = JoinService()


@router.get(
    "/progress/{task_id}",
    summary="SSE进度推送",
    description="建立Server-Sent Events连接，实时接收任务进度更新",
    response_description="SSE事件流"
)
async def stream_progress(
    request: Request,
    task_id: str = Path(..., description="任务ID"),
    current_user: User = Depends(get_current_user)
):
    """
    SSE进度推送端点
    
    建立与客户端的实时连接，推送任务进度信息：
    - 任务状态变更
    - 进度百分比更新
    - 错误和警告信息
    - 任务完成通知
    
    事件格式：
    ```
    event: progress
    data: {"current_step": "...", "progress_percent": 50.0, ...}
    
    event: completed
    data: {"result_id": "...", "summary": {...}}
    
    event: error
    data: {"error_code": "...", "message": "..."}
    ```
    """
    logger.info(f"用户 {current_user.user_id} 建立SSE连接，任务: {task_id}")
    
    try:
        # 验证任务存在且用户有权限访问
        task_info = await join_service.get_task_status(task_id, current_user.user_id)
        if not task_info:
            raise NotFoundAPIError("Task", task_id)
        
        # 生成连接ID
        connection_id = f"{current_user.user_id}_{datetime.utcnow().timestamp()}"
        
        # 注册SSE连接
        message_queue = await sse_service.register_connection(
            connection_id, task_id, current_user.user_id
        )
        
        # 创建事件生成器
        async def event_generator():
            try:
                # 发送当前任务状态
                current_status = {
                    "status": task_info.status.value,
                    "progress": {
                        "current_step": task_info.progress.current_step,
                        "step_index": task_info.progress.step_index,
                        "total_steps": task_info.progress.total_steps,
                        "progress_percent": task_info.progress.progress_percent,
                        "processed_rows": task_info.progress.processed_rows,
                        "total_rows": task_info.progress.total_rows
                    } if task_info.progress else None,
                    "created_at": task_info.created_at.isoformat() + "Z",
                    "started_at": task_info.started_at.isoformat() + "Z" if task_info.started_at else None,
                    "completed_at": task_info.completed_at.isoformat() + "Z" if task_info.completed_at else None,
                    "result_id": task_info.result_id,
                    "error_message": task_info.error_message
                }
                
                yield {
                    "event": "status",
                    "data": json.dumps({
                        "task_id": task_id,
                        "user_id": current_user.user_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "data": current_status
                    })
                }
                
                # 监听进度更新
                while True:
                    # 检查客户端是否断开连接
                    if await request.is_disconnected():
                        logger.info(f"客户端断开连接: {connection_id}")
                        break
                    
                    try:
                        # 等待消息，设置超时避免长时间阻塞
                        message = await asyncio.wait_for(
                            message_queue.get(),
                            timeout=30.0  # 30秒超时
                        )
                        
                        # 转换为SSE格式并发送
                        sse_event = message.to_sse_format()
                        yield sse_event
                        
                        # 如果是完成或错误消息，结束连接
                        if message.event_type in ["completed", "error"]:
                            break
                            
                    except asyncio.TimeoutError:
                        # 超时时继续循环，心跳由SSE服务处理
                        continue
                    
            except Exception as e:
                logger.error(f"SSE事件生成器错误: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "task_id": task_id,
                        "user_id": current_user.user_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "data": {
                            "error_code": "SSE_ERROR",
                            "message": str(e)
                        }
                    })
                }
            finally:
                # 清理连接
                await sse_service.disconnect_client(connection_id)
        
        return EventSourceResponse(
            event_generator(),
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control"
            }
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"建立SSE连接失败: {str(e)}")
        raise APIError(
            message=f"建立SSE连接失败: {str(e)}",
            error_code="SSE_CONNECTION_FAILED",
            status_code=500
        )


@router.get(
    "/connections",
    summary="获取连接统计",
    description="获取当前SSE连接的统计信息（管理员功能）",
    response_description="返回连接统计信息"
)
async def get_connection_stats(
    current_user: User = Depends(get_current_user)
):
    """
    获取SSE连接统计信息
    
    返回：
    - 总连接数
    - 各任务的连接数
    - 活跃连接信息
    - Redis连接状态
    - 系统统计信息
    """
    # 这里可以添加管理员权限检查
    # if not current_user.has_permission("admin"):
    #     raise AuthorizationAPIError("需要管理员权限")
    
    # 获取SSE服务统计信息
    stats = await sse_service.get_connection_stats()
    
    return stats


# 辅助函数：模拟进度推送（用于测试）
async def simulate_task_progress(task_id: str):
    """
    模拟任务进度推送（用于测试目的）
    在实际应用中，这些更新会由任务执行器发送
    """
    steps = [
        ("初始化任务", 0),
        ("加载数据集", 20),
        ("数据预处理", 40),
        ("执行连接操作", 60),
        ("后处理和优化", 80),
        ("生成结果", 95),
        ("完成", 100)
    ]
    
    for step_name, progress in steps:
        await asyncio.sleep(2)  # 模拟处理时间
        
        # 发送进度更新
        progress_data = {
            "task_id": task_id,
            "current_step": step_name,
            "progress_percent": float(progress),
            "step_index": steps.index((step_name, progress)) + 1,
            "total_steps": len(steps),
            "processed_rows": int(progress * 500),  # 模拟处理行数
            "total_rows": 50000 if progress < 100 else 50000
        }
        
        await sse_service.notify_task_progress(task_id, progress_data)
        
        if progress == 100:
            # 发送完成通知
            completion_data = {
                "task_id": task_id,
                "result_id": f"result_{task_id}_completed",
                "summary": {
                    "total_rows": 50000,
                    "total_time_seconds": len(steps) * 2,
                    "success": True
                }
            }
            await sse_service.notify_task_completed(task_id, completion_data)
            break


@router.post(
    "/test/{task_id}",
    summary="测试进度推送",
    description="启动模拟任务进度推送（仅用于测试）",
    response_description="返回测试启动确认"
)
async def test_progress_push(
    task_id: str = Path(..., description="任务ID"),
    current_user: User = Depends(get_current_user)
):
    """
    启动模拟任务进度推送
    
    仅用于测试SSE功能，在生产环境中应该移除
    """
    logger.info(f"用户 {current_user.user_id} 启动测试进度推送: {task_id}")
    
    # 启动异步任务模拟进度
    asyncio.create_task(simulate_task_progress(task_id))
    
    return {
        "message": f"测试进度推送已启动，任务ID: {task_id}",
        "task_id": task_id,
        "test_mode": True
    }


# 提供给其他模块使用的接口（向后兼容）
async def notify_task_progress(task_id: str, progress_data: Dict[str, Any]):
    """
    发送任务进度通知（供其他模块调用）
    
    Args:
        task_id: 任务ID
        progress_data: 进度数据
    """
    await sse_service.notify_task_progress(task_id, progress_data)


async def notify_task_completion(task_id: str, result_data: Dict[str, Any]):
    """
    发送任务完成通知（供其他模块调用）
    
    Args:
        task_id: 任务ID
        result_data: 结果数据
    """
    await sse_service.notify_task_completed(task_id, result_data)


async def notify_task_error(task_id: str, error_data: Dict[str, Any]):
    """
    发送任务错误通知（供其他模块调用）
    
    Args:
        task_id: 任务ID
        error_data: 错误数据
    """
    await sse_service.notify_task_error(task_id, error_data)