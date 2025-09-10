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

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter()

# 全局连接管理器
class SSEConnectionManager:
    """SSE连接管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, task_id: str, user_id: str, connection_id: str):
        """添加新连接"""
        if task_id not in self.active_connections:
            self.active_connections[task_id] = {}
        
        self.active_connections[task_id][connection_id] = {
            "user_id": user_id,
            "connected_at": datetime.utcnow(),
            "queue": asyncio.Queue()
        }
        
        logger.info(f"SSE连接建立: task_id={task_id}, user_id={user_id}, connection_id={connection_id}")
    
    async def disconnect(self, task_id: str, connection_id: str):
        """移除连接"""
        if task_id in self.active_connections and connection_id in self.active_connections[task_id]:
            del self.active_connections[task_id][connection_id]
            
            # 如果没有更多连接，清理任务
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
            
            logger.info(f"SSE连接断开: task_id={task_id}, connection_id={connection_id}")
    
    async def send_progress_update(self, task_id: str, progress_data: Dict[str, Any]):
        """向指定任务的所有连接发送进度更新"""
        if task_id not in self.active_connections:
            return
        
        message = {
            "type": "progress",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": progress_data
        }
        
        # 向所有连接发送消息
        for connection_id, connection_info in self.active_connections[task_id].items():
            try:
                await connection_info["queue"].put(message)
            except Exception as e:
                logger.error(f"发送进度更新失败: {e}")
    
    async def send_task_completion(self, task_id: str, result_data: Dict[str, Any]):
        """发送任务完成通知"""
        if task_id not in self.active_connections:
            return
        
        message = {
            "type": "completed",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": result_data
        }
        
        # 向所有连接发送完成消息
        for connection_id, connection_info in self.active_connections[task_id].items():
            try:
                await connection_info["queue"].put(message)
            except Exception as e:
                logger.error(f"发送完成通知失败: {e}")
    
    async def send_error(self, task_id: str, error_data: Dict[str, Any]):
        """发送错误通知"""
        if task_id not in self.active_connections:
            return
        
        message = {
            "type": "error",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": error_data
        }
        
        # 向所有连接发送错误消息
        for connection_id, connection_info in self.active_connections[task_id].items():
            try:
                await connection_info["queue"].put(message)
            except Exception as e:
                logger.error(f"发送错误通知失败: {e}")
    
    def get_connection_count(self, task_id: str) -> int:
        """获取指定任务的连接数"""
        return len(self.active_connections.get(task_id, {}))
    
    def get_total_connections(self) -> int:
        """获取总连接数"""
        return sum(len(connections) for connections in self.active_connections.values())

# 全局连接管理器实例
connection_manager = SSEConnectionManager()


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
        # TODO: 实现任务验证
        # task = await task_service.get_task(task_id, current_user.user_id)
        # if not task:
        #     raise NotFoundAPIError("Task", task_id)
        
        # 生成连接ID
        connection_id = f"{current_user.user_id}_{datetime.utcnow().timestamp()}"
        
        # 创建事件生成器
        async def event_generator():
            try:
                # 注册连接
                await connection_manager.connect(task_id, current_user.user_id, connection_id)
                
                # 发送连接确认消息
                yield {
                    "event": "connected",
                    "data": json.dumps({
                        "task_id": task_id,
                        "connection_id": connection_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    })
                }
                
                # 发送当前任务状态（如果任务已存在）
                # TODO: 获取当前任务状态
                # current_status = await task_service.get_current_status(task_id)
                # if current_status:
                #     yield {
                #         "event": "status",
                #         "data": json.dumps(current_status)
                #     }
                
                # 监听进度更新
                connection_info = connection_manager.active_connections[task_id][connection_id]
                
                while True:
                    # 检查客户端是否断开连接
                    if await request.is_disconnected():
                        logger.info(f"客户端断开连接: {connection_id}")
                        break
                    
                    try:
                        # 等待消息，设置超时避免长时间阻塞
                        message = await asyncio.wait_for(
                            connection_info["queue"].get(),
                            timeout=30.0  # 30秒超时
                        )
                        
                        yield {
                            "event": message["type"],
                            "data": json.dumps(message)
                        }
                        
                        # 如果是完成或错误消息，结束连接
                        if message["type"] in ["completed", "error"]:
                            break
                            
                    except asyncio.TimeoutError:
                        # 发送心跳保持连接
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps({
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                                "connections": connection_manager.get_connection_count(task_id)
                            })
                        }
                    
            except Exception as e:
                logger.error(f"SSE事件生成器错误: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error_code": "SSE_ERROR",
                        "message": str(e),
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    })
                }
            finally:
                # 清理连接
                await connection_manager.disconnect(task_id, connection_id)
        
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
    """
    # 这里可以添加管理员权限检查
    # if not current_user.has_permission("admin"):
    #     raise AuthorizationAPIError("需要管理员权限")
    
    stats = {
        "total_connections": connection_manager.get_total_connections(),
        "active_tasks": len(connection_manager.active_connections),
        "task_connections": {}
    }
    
    for task_id, connections in connection_manager.active_connections.items():
        stats["task_connections"][task_id] = {
            "connection_count": len(connections),
            "connections": [
                {
                    "connection_id": conn_id,
                    "user_id": conn_info["user_id"],
                    "connected_at": conn_info["connected_at"].isoformat() + "Z"
                }
                for conn_id, conn_info in connections.items()
            ]
        }
    
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
        
        await connection_manager.send_progress_update(task_id, progress_data)
        
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
            await connection_manager.send_task_completion(task_id, completion_data)
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


# 提供给其他模块使用的接口
async def notify_task_progress(task_id: str, progress_data: Dict[str, Any]):
    """
    发送任务进度通知（供其他模块调用）
    
    Args:
        task_id: 任务ID
        progress_data: 进度数据
    """
    await connection_manager.send_progress_update(task_id, progress_data)


async def notify_task_completion(task_id: str, result_data: Dict[str, Any]):
    """
    发送任务完成通知（供其他模块调用）
    
    Args:
        task_id: 任务ID
        result_data: 结果数据
    """
    await connection_manager.send_task_completion(task_id, result_data)


async def notify_task_error(task_id: str, error_data: Dict[str, Any]):
    """
    发送任务错误通知（供其他模块调用）
    
    Args:
        task_id: 任务ID
        error_data: 错误数据
    """
    await connection_manager.send_error(task_id, error_data)