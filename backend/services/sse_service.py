"""
SSE (Server-Sent Events) 服务

提供实时进度推送、任务状态广播、Redis发布订阅机制等功能
与JoinService集成，实现分布式任务状态管理
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, asdict

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from ..core.config import config

logger = logging.getLogger(__name__)


@dataclass
class SSEMessage:
    """SSE消息结构"""
    event_type: str  # progress, completed, error, heartbeat, status
    task_id: str
    user_id: str
    timestamp: str
    data: Dict[str, Any]
    
    def to_sse_format(self) -> Dict[str, str]:
        """转换为SSE事件格式"""
        return {
            "event": self.event_type,
            "data": json.dumps({
                "task_id": self.task_id,
                "user_id": self.user_id,
                "timestamp": self.timestamp,
                "data": self.data
            })
        }


@dataclass
class ConnectionInfo:
    """连接信息"""
    connection_id: str
    task_id: str
    user_id: str
    connected_at: datetime
    last_heartbeat: datetime
    queue: asyncio.Queue
    is_active: bool = True


class SSEService:
    """SSE服务主类"""
    
    def __init__(self):
        """初始化SSE服务"""
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # Redis连接配置
        self._redis_url = config.redis.url
        self._redis_pool: Optional[ConnectionPool] = None
        self._redis_client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        
        # 连接管理
        self._connections: Dict[str, ConnectionInfo] = {}  # connection_id -> ConnectionInfo
        self._task_connections: Dict[str, Set[str]] = {}  # task_id -> set(connection_ids)
        self._user_connections: Dict[str, Set[str]] = {}  # user_id -> set(connection_ids)
        
        # 配置
        self._heartbeat_interval = config.redis.heartbeat_interval  # 心跳间隔（秒）
        self._connection_timeout = config.redis.connection_timeout_sse  # 连接超时（秒）
        self._message_buffer_size = config.redis.message_buffer_size  # 消息缓冲区大小
        
        # 内部任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._redis_listener_task: Optional[asyncio.Task] = None
        
        # 统计信息
        self._stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_failed": 0,
            "redis_connected": False,
            "started_at": datetime.utcnow()
        }
        
        self._logger.info("SSEService initialized")
    
    async def initialize(self):
        """初始化Redis连接和后台任务"""
        try:
            # 初始化Redis连接池
            self._redis_pool = redis.ConnectionPool.from_url(
                self._redis_url,
                max_connections=config.redis.max_connections,
                retry_on_timeout=config.redis.retry_on_timeout,
                decode_responses=config.redis.decode_responses,
                socket_timeout=config.redis.socket_timeout,
                socket_connect_timeout=config.redis.connection_timeout
            )
            
            self._redis_client = redis.Redis(connection_pool=self._redis_pool)
            
            # 测试Redis连接
            await self._redis_client.ping()
            self._stats["redis_connected"] = True
            
            # 初始化发布订阅
            self._pubsub = self._redis_client.pubsub()
            await self._pubsub.subscribe("task_progress", "task_status", "task_completed", "task_error")
            
            # 启动后台任务
            self._redis_listener_task = asyncio.create_task(self._redis_message_listener())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_worker())
            self._cleanup_task = asyncio.create_task(self._cleanup_worker())
            
            self._logger.info("SSEService initialized successfully with Redis connection")
            
        except Exception as e:
            self._logger.error(f"Failed to initialize SSEService: {e}")
            self._stats["redis_connected"] = False
            # 继续运行，但只使用本地连接管理
            self._heartbeat_task = asyncio.create_task(self._heartbeat_worker())
            self._cleanup_task = asyncio.create_task(self._cleanup_worker())
    
    async def shutdown(self):
        """关闭服务，清理资源"""
        self._logger.info("Shutting down SSEService")
        
        # 取消后台任务
        for task in [self._heartbeat_task, self._cleanup_task, self._redis_listener_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 关闭所有连接
        for connection_id in list(self._connections.keys()):
            await self._disconnect_client(connection_id)
        
        # 关闭Redis连接
        if self._pubsub:
            await self._pubsub.close()
        if self._redis_client:
            await self._redis_client.close()
        if self._redis_pool:
            await self._redis_pool.disconnect()
        
        self._logger.info("SSEService shutdown completed")
    
    async def register_connection(
        self, 
        connection_id: str, 
        task_id: str, 
        user_id: str
    ) -> asyncio.Queue:
        """
        注册新的SSE连接
        
        Args:
            connection_id: 连接ID
            task_id: 任务ID
            user_id: 用户ID
            
        Returns:
            消息队列
        """
        now = datetime.utcnow()
        
        # 创建消息队列
        message_queue = asyncio.Queue(maxsize=self._message_buffer_size)
        
        # 创建连接信息
        connection_info = ConnectionInfo(
            connection_id=connection_id,
            task_id=task_id,
            user_id=user_id,
            connected_at=now,
            last_heartbeat=now,
            queue=message_queue
        )
        
        # 存储连接信息
        self._connections[connection_id] = connection_info
        
        # 更新索引
        if task_id not in self._task_connections:
            self._task_connections[task_id] = set()
        self._task_connections[task_id].add(connection_id)
        
        if user_id not in self._user_connections:
            self._user_connections[user_id] = set()
        self._user_connections[user_id].add(connection_id)
        
        # 更新统计
        self._stats["total_connections"] += 1
        self._stats["active_connections"] = len(self._connections)
        
        self._logger.info(f"Registered SSE connection: {connection_id} for task {task_id}, user {user_id}")
        
        # 发送连接确认消息
        await self._send_to_connection(connection_id, SSEMessage(
            event_type="connected",
            task_id=task_id,
            user_id=user_id,
            timestamp=now.isoformat() + "Z",
            data={
                "connection_id": connection_id,
                "task_id": task_id,
                "message": "SSE连接已建立"
            }
        ))
        
        return message_queue
    
    async def disconnect_client(self, connection_id: str):
        """断开客户端连接"""
        await self._disconnect_client(connection_id)
    
    async def _disconnect_client(self, connection_id: str):
        """内部断开连接方法"""
        if connection_id not in self._connections:
            return
        
        connection_info = self._connections[connection_id]
        task_id = connection_info.task_id
        user_id = connection_info.user_id
        
        # 移除连接
        del self._connections[connection_id]
        
        # 更新索引
        if task_id in self._task_connections:
            self._task_connections[task_id].discard(connection_id)
            if not self._task_connections[task_id]:
                del self._task_connections[task_id]
        
        if user_id in self._user_connections:
            self._user_connections[user_id].discard(connection_id)
            if not self._user_connections[user_id]:
                del self._user_connections[user_id]
        
        # 更新统计
        self._stats["active_connections"] = len(self._connections)
        
        self._logger.info(f"Disconnected SSE connection: {connection_id}")
    
    async def notify_task_progress(self, task_id: str, progress_data: Dict[str, Any]):
        """发送任务进度通知"""
        message = SSEMessage(
            event_type="progress",
            task_id=task_id,
            user_id="",  # 会在发送时填充
            timestamp=datetime.utcnow().isoformat() + "Z",
            data=progress_data
        )
        
        await self._broadcast_to_task(task_id, message)
        
        # 通过Redis广播（如果可用）
        if self._redis_client and self._stats["redis_connected"]:
            try:
                await self._redis_client.publish(
                    "task_progress",
                    json.dumps({
                        "task_id": task_id,
                        "data": progress_data,
                        "timestamp": message.timestamp
                    })
                )
            except Exception as e:
                self._logger.warning(f"Failed to publish progress to Redis: {e}")
    
    async def notify_task_completed(self, task_id: str, result_data: Dict[str, Any]):
        """发送任务完成通知"""
        message = SSEMessage(
            event_type="completed",
            task_id=task_id,
            user_id="",
            timestamp=datetime.utcnow().isoformat() + "Z",
            data=result_data
        )
        
        await self._broadcast_to_task(task_id, message)
        
        # 通过Redis广播
        if self._redis_client and self._stats["redis_connected"]:
            try:
                await self._redis_client.publish(
                    "task_completed",
                    json.dumps({
                        "task_id": task_id,
                        "data": result_data,
                        "timestamp": message.timestamp
                    })
                )
            except Exception as e:
                self._logger.warning(f"Failed to publish completion to Redis: {e}")
    
    async def notify_task_error(self, task_id: str, error_data: Dict[str, Any]):
        """发送任务错误通知"""
        message = SSEMessage(
            event_type="error",
            task_id=task_id,
            user_id="",
            timestamp=datetime.utcnow().isoformat() + "Z",
            data=error_data
        )
        
        await self._broadcast_to_task(task_id, message)
        
        # 通过Redis广播
        if self._redis_client and self._stats["redis_connected"]:
            try:
                await self._redis_client.publish(
                    "task_error",
                    json.dumps({
                        "task_id": task_id,
                        "data": error_data,
                        "timestamp": message.timestamp
                    })
                )
            except Exception as e:
                self._logger.warning(f"Failed to publish error to Redis: {e}")
    
    async def notify_task_status(self, task_id: str, status_data: Dict[str, Any]):
        """发送任务状态通知"""
        message = SSEMessage(
            event_type="status",
            task_id=task_id,
            user_id="",
            timestamp=datetime.utcnow().isoformat() + "Z",
            data=status_data
        )
        
        await self._broadcast_to_task(task_id, message)
        
        # 通过Redis广播
        if self._redis_client and self._stats["redis_connected"]:
            try:
                await self._redis_client.publish(
                    "task_status",
                    json.dumps({
                        "task_id": task_id,
                        "data": status_data,
                        "timestamp": message.timestamp
                    })
                )
            except Exception as e:
                self._logger.warning(f"Failed to publish status to Redis: {e}")
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        stats = self._stats.copy()
        stats.update({
            "uptime_seconds": int((datetime.utcnow() - stats["started_at"]).total_seconds()),
            "task_connections": len(self._task_connections),
            "user_connections": len(self._user_connections),
            "connection_details": {}
        })
        
        # 详细连接信息
        for task_id, connection_ids in self._task_connections.items():
            stats["connection_details"][task_id] = {
                "connection_count": len(connection_ids),
                "connections": [
                    {
                        "connection_id": conn_id,
                        "user_id": self._connections[conn_id].user_id,
                        "connected_at": self._connections[conn_id].connected_at.isoformat() + "Z",
                        "last_heartbeat": self._connections[conn_id].last_heartbeat.isoformat() + "Z"
                    }
                    for conn_id in connection_ids
                    if conn_id in self._connections
                ]
            }
        
        return stats
    
    async def _broadcast_to_task(self, task_id: str, message: SSEMessage):
        """向任务的所有连接广播消息"""
        if task_id not in self._task_connections:
            return
        
        connection_ids = self._task_connections[task_id].copy()
        
        for connection_id in connection_ids:
            if connection_id in self._connections:
                # 填充用户ID
                connection_info = self._connections[connection_id]
                message.user_id = connection_info.user_id
                
                await self._send_to_connection(connection_id, message)
    
    async def _send_to_connection(self, connection_id: str, message: SSEMessage):
        """向单个连接发送消息"""
        if connection_id not in self._connections:
            return
        
        connection_info = self._connections[connection_id]
        
        try:
            # 非阻塞方式放入队列
            connection_info.queue.put_nowait(message)
            self._stats["messages_sent"] += 1
            
        except asyncio.QueueFull:
            self._logger.warning(f"Message queue full for connection {connection_id}, dropping message")
            self._stats["messages_failed"] += 1
            
        except Exception as e:
            self._logger.error(f"Failed to send message to connection {connection_id}: {e}")
            self._stats["messages_failed"] += 1
            # 标记连接为非活跃状态
            connection_info.is_active = False
    
    async def _redis_message_listener(self):
        """Redis消息监听器"""
        if not self._pubsub:
            return
        
        self._logger.info("Starting Redis message listener")
        
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        channel = message["channel"]
                        data = json.loads(message["data"])
                        task_id = data.get("task_id")
                        
                        if not task_id:
                            continue
                        
                        # 根据频道类型创建不同的消息
                        if channel == "task_progress":
                            sse_message = SSEMessage(
                                event_type="progress",
                                task_id=task_id,
                                user_id="",
                                timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                                data=data.get("data", {})
                            )
                        elif channel == "task_completed":
                            sse_message = SSEMessage(
                                event_type="completed",
                                task_id=task_id,
                                user_id="",
                                timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                                data=data.get("data", {})
                            )
                        elif channel == "task_error":
                            sse_message = SSEMessage(
                                event_type="error",
                                task_id=task_id,
                                user_id="",
                                timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                                data=data.get("data", {})
                            )
                        elif channel == "task_status":
                            sse_message = SSEMessage(
                                event_type="status",
                                task_id=task_id,
                                user_id="",
                                timestamp=data.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                                data=data.get("data", {})
                            )
                        else:
                            continue
                        
                        # 广播到本地连接
                        await self._broadcast_to_task(task_id, sse_message)
                        
                    except Exception as e:
                        self._logger.error(f"Error processing Redis message: {e}")
                        
        except Exception as e:
            self._logger.error(f"Redis message listener error: {e}")
            self._stats["redis_connected"] = False
    
    async def _heartbeat_worker(self):
        """心跳工作者"""
        self._logger.info("Starting heartbeat worker")
        
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                now = datetime.utcnow()
                heartbeat_message = SSEMessage(
                    event_type="heartbeat",
                    task_id="",
                    user_id="",
                    timestamp=now.isoformat() + "Z",
                    data={
                        "active_connections": len(self._connections),
                        "server_time": now.isoformat() + "Z"
                    }
                )
                
                # 向所有连接发送心跳
                for connection_id, connection_info in list(self._connections.items()):
                    if connection_info.is_active:
                        heartbeat_message.task_id = connection_info.task_id
                        heartbeat_message.user_id = connection_info.user_id
                        
                        await self._send_to_connection(connection_id, heartbeat_message)
                        connection_info.last_heartbeat = now
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Heartbeat worker error: {e}")
    
    async def _cleanup_worker(self):
        """清理工作者，处理超时连接"""
        self._logger.info("Starting cleanup worker")
        
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                
                now = datetime.utcnow()
                timeout_threshold = now - timedelta(seconds=self._connection_timeout)
                
                # 查找超时连接
                timeout_connections = []
                for connection_id, connection_info in self._connections.items():
                    if (connection_info.last_heartbeat < timeout_threshold or 
                        not connection_info.is_active):
                        timeout_connections.append(connection_id)
                
                # 清理超时连接
                for connection_id in timeout_connections:
                    self._logger.info(f"Cleaning up timeout connection: {connection_id}")
                    await self._disconnect_client(connection_id)
                
                if timeout_connections:
                    self._logger.info(f"Cleaned up {len(timeout_connections)} timeout connections")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Cleanup worker error: {e}")


# 全局SSE服务实例
sse_service = SSEService()