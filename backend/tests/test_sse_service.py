"""
SSE服务测试

测试Server-Sent Events实时进度推送服务的核心功能
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.sse_service import (
    SSEService, SSEMessage, ConnectionInfo, sse_service
)


class TestSSEMessage:
    """SSE消息测试类"""
    
    def test_sse_message_creation(self):
        """测试SSE消息创建"""
        message = SSEMessage(
            event_type="progress",
            task_id="task_123",
            user_id="user_456", 
            timestamp="2025-09-10T10:00:00Z",
            data={"progress": 50.0, "step": "processing"}
        )
        
        assert message.event_type == "progress"
        assert message.task_id == "task_123"
        assert message.user_id == "user_456"
        assert message.data["progress"] == 50.0
    
    def test_sse_message_to_sse_format(self):
        """测试SSE消息格式转换"""
        message = SSEMessage(
            event_type="completed",
            task_id="task_123",
            user_id="user_456",
            timestamp="2025-09-10T10:00:00Z",
            data={"result_id": "result_789"}
        )
        
        sse_format = message.to_sse_format()
        
        assert sse_format["event"] == "completed"
        
        data = json.loads(sse_format["data"])
        assert data["task_id"] == "task_123"
        assert data["user_id"] == "user_456"
        assert data["data"]["result_id"] == "result_789"


class TestSSEService:
    """SSE服务测试类"""
    
    @pytest.fixture
    async def sse_service_instance(self):
        """创建SSE服务测试实例"""
        service = SSEService()
        yield service
        # 清理
        await service.shutdown()
    
    @pytest.mark.asyncio
    async def test_service_initialization(self, sse_service_instance):
        """测试服务初始化"""
        service = sse_service_instance
        
        # 模拟Redis连接
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            
            await service.initialize()
            
            assert service._stats["redis_connected"] is True
            assert service._heartbeat_task is not None
            assert service._cleanup_task is not None
    
    @pytest.mark.asyncio
    async def test_service_initialization_without_redis(self, sse_service_instance):
        """测试无Redis情况下的服务初始化"""
        service = sse_service_instance
        
        # 模拟Redis连接失败
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")
            
            await service.initialize()
            
            assert service._stats["redis_connected"] is False
            assert service._heartbeat_task is not None
            assert service._cleanup_task is not None
    
    @pytest.mark.asyncio
    async def test_register_connection(self, sse_service_instance):
        """测试连接注册"""
        service = sse_service_instance
        
        connection_id = "conn_123"
        task_id = "task_456" 
        user_id = "user_789"
        
        queue = await service.register_connection(connection_id, task_id, user_id)
        
        assert connection_id in service._connections
        assert task_id in service._task_connections
        assert user_id in service._user_connections
        assert connection_id in service._task_connections[task_id]
        assert connection_id in service._user_connections[user_id]
        assert service._stats["active_connections"] == 1
        
        # 验证队列中有连接确认消息
        assert not queue.empty()
        message = await queue.get()
        assert message.event_type == "connected"
    
    @pytest.mark.asyncio
    async def test_disconnect_client(self, sse_service_instance):
        """测试客户端断开连接"""
        service = sse_service_instance
        
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        
        # 先注册连接
        await service.register_connection(connection_id, task_id, user_id)
        assert service._stats["active_connections"] == 1
        
        # 断开连接
        await service.disconnect_client(connection_id)
        
        assert connection_id not in service._connections
        assert task_id not in service._task_connections
        assert user_id not in service._user_connections
        assert service._stats["active_connections"] == 0
    
    @pytest.mark.asyncio
    async def test_notify_task_progress(self, sse_service_instance):
        """测试任务进度通知"""
        service = sse_service_instance
        
        # 注册连接
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        queue = await service.register_connection(connection_id, task_id, user_id)
        
        # 清空连接确认消息
        await queue.get()
        
        # 发送进度通知
        progress_data = {"progress_percent": 75.0, "current_step": "processing"}
        await service.notify_task_progress(task_id, progress_data)
        
        # 验证消息
        message = await queue.get()
        assert message.event_type == "progress"
        assert message.data == progress_data
    
    @pytest.mark.asyncio
    async def test_notify_task_completed(self, sse_service_instance):
        """测试任务完成通知"""
        service = sse_service_instance
        
        # 注册连接
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        queue = await service.register_connection(connection_id, task_id, user_id)
        
        # 清空连接确认消息
        await queue.get()
        
        # 发送完成通知
        result_data = {"result_id": "result_123", "summary": {"total_rows": 1000}}
        await service.notify_task_completed(task_id, result_data)
        
        # 验证消息
        message = await queue.get()
        assert message.event_type == "completed"
        assert message.data == result_data
    
    @pytest.mark.asyncio
    async def test_notify_task_error(self, sse_service_instance):
        """测试任务错误通知"""
        service = sse_service_instance
        
        # 注册连接
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        queue = await service.register_connection(connection_id, task_id, user_id)
        
        # 清空连接确认消息
        await queue.get()
        
        # 发送错误通知
        error_data = {"error_code": "TASK_FAILED", "message": "Task execution failed"}
        await service.notify_task_error(task_id, error_data)
        
        # 验证消息
        message = await queue.get()
        assert message.event_type == "error"
        assert message.data == error_data
    
    @pytest.mark.asyncio
    async def test_multiple_connections_same_task(self, sse_service_instance):
        """测试同一任务的多个连接"""
        service = sse_service_instance
        
        task_id = "task_456"
        
        # 注册多个连接
        queue1 = await service.register_connection("conn_1", task_id, "user_1")
        queue2 = await service.register_connection("conn_2", task_id, "user_2")
        
        # 清空连接确认消息
        await queue1.get()
        await queue2.get()
        
        # 发送进度通知
        progress_data = {"progress_percent": 50.0}
        await service.notify_task_progress(task_id, progress_data)
        
        # 验证两个连接都收到消息
        message1 = await queue1.get()
        message2 = await queue2.get()
        
        assert message1.event_type == "progress"
        assert message2.event_type == "progress"
        assert message1.data == progress_data
        assert message2.data == progress_data
    
    @pytest.mark.asyncio
    async def test_get_connection_stats(self, sse_service_instance):
        """测试获取连接统计"""
        service = sse_service_instance
        
        # 注册几个连接
        await service.register_connection("conn_1", "task_1", "user_1")
        await service.register_connection("conn_2", "task_1", "user_2")
        await service.register_connection("conn_3", "task_2", "user_1")
        
        stats = await service.get_connection_stats()
        
        assert stats["active_connections"] == 3
        assert stats["task_connections"] == 2  # 2个不同的任务
        assert stats["user_connections"] == 2   # 2个不同的用户
        
        # 验证详细连接信息
        assert "task_1" in stats["connection_details"]
        assert "task_2" in stats["connection_details"]
        assert stats["connection_details"]["task_1"]["connection_count"] == 2
        assert stats["connection_details"]["task_2"]["connection_count"] == 1
    
    @pytest.mark.asyncio
    async def test_redis_message_broadcasting(self, sse_service_instance):
        """测试Redis消息广播"""
        service = sse_service_instance
        
        # 模拟Redis连接
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping = AsyncMock()
            mock_redis_instance.publish = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            
            await service.initialize()
            
            # 发送进度通知
            task_id = "task_123"
            progress_data = {"progress_percent": 60.0}
            await service.notify_task_progress(task_id, progress_data)
            
            # 验证Redis发布调用
            mock_redis_instance.publish.assert_called_once()
            call_args = mock_redis_instance.publish.call_args
            assert call_args[0][0] == "task_progress"
            
            published_data = json.loads(call_args[0][1])
            assert published_data["task_id"] == task_id
            assert published_data["data"] == progress_data
    
    @pytest.mark.asyncio
    async def test_message_queue_overflow(self, sse_service_instance):
        """测试消息队列溢出处理"""
        service = sse_service_instance
        service._message_buffer_size = 2  # 设置小的缓冲区大小
        
        # 注册连接
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        queue = await service.register_connection(connection_id, task_id, user_id)
        
        # 清空连接确认消息
        await queue.get()
        
        # 填满队列
        await service.notify_task_progress(task_id, {"progress": 1})
        await service.notify_task_progress(task_id, {"progress": 2})
        
        # 尝试发送更多消息（应该丢弃）
        await service.notify_task_progress(task_id, {"progress": 3})
        
        # 验证统计信息
        assert service._stats["messages_failed"] > 0
    
    @pytest.mark.asyncio
    async def test_heartbeat_mechanism(self, sse_service_instance):
        """测试心跳机制"""
        service = sse_service_instance
        service._heartbeat_interval = 0.1  # 设置短的心跳间隔用于测试
        
        # 启动服务
        await service.initialize()
        
        # 注册连接
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        queue = await service.register_connection(connection_id, task_id, user_id)
        
        # 清空连接确认消息
        await queue.get()
        
        # 等待心跳消息
        await asyncio.sleep(0.2)
        
        # 检查是否收到心跳消息
        try:
            message = await asyncio.wait_for(queue.get(), timeout=0.1)
            assert message.event_type == "heartbeat"
        except asyncio.TimeoutError:
            pytest.fail("No heartbeat message received")
    
    @pytest.mark.asyncio
    async def test_connection_timeout_cleanup(self, sse_service_instance):
        """测试连接超时清理"""
        service = sse_service_instance
        service._connection_timeout = 0.1  # 设置短的超时时间用于测试
        
        # 启动服务
        await service.initialize()
        
        # 注册连接
        connection_id = "conn_123"
        task_id = "task_456"
        user_id = "user_789"
        await service.register_connection(connection_id, task_id, user_id)
        
        # 手动设置过期的心跳时间
        connection_info = service._connections[connection_id]
        connection_info.last_heartbeat = datetime.utcnow() - timedelta(seconds=1)
        connection_info.is_active = False
        
        # 等待清理工作者运行
        await asyncio.sleep(0.2)
        
        # 验证连接已被清理
        assert connection_id not in service._connections


@pytest.mark.asyncio
async def test_global_sse_service():
    """测试全局SSE服务实例"""
    # 验证全局实例存在
    assert sse_service is not None
    assert isinstance(sse_service, SSEService)
    
    # 测试基本功能
    stats = await sse_service.get_connection_stats()
    assert "active_connections" in stats
    assert "redis_connected" in stats


class TestSSEIntegration:
    """SSE集成测试类"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_progress_flow(self):
        """测试端到端进度流程"""
        service = SSEService()
        
        try:
            # 注册连接
            connection_id = "conn_e2e"
            task_id = "task_e2e"
            user_id = "user_e2e"
            queue = await service.register_connection(connection_id, task_id, user_id)
            
            # 清空连接确认消息
            await queue.get()
            
            # 模拟完整的任务执行流程
            # 1. 发送进度更新
            await service.notify_task_progress(task_id, {
                "current_step": "初始化",
                "progress_percent": 10.0
            })
            
            await service.notify_task_progress(task_id, {
                "current_step": "数据处理",
                "progress_percent": 50.0
            })
            
            await service.notify_task_progress(task_id, {
                "current_step": "完成处理",
                "progress_percent": 90.0
            })
            
            # 2. 发送完成通知
            await service.notify_task_completed(task_id, {
                "result_id": "result_e2e",
                "summary": {"total_rows": 1000, "success": True}
            })
            
            # 验证消息接收
            messages = []
            for _ in range(4):  # 3个进度 + 1个完成
                message = await queue.get()
                messages.append(message)
            
            # 验证消息类型和顺序
            assert messages[0].event_type == "progress"
            assert messages[1].event_type == "progress"
            assert messages[2].event_type == "progress"
            assert messages[3].event_type == "completed"
            
            # 验证进度数据
            assert messages[0].data["progress_percent"] == 10.0
            assert messages[1].data["progress_percent"] == 50.0
            assert messages[2].data["progress_percent"] == 90.0
            assert messages[3].data["result_id"] == "result_e2e"
            
        finally:
            await service.shutdown()
    
    @pytest.mark.asyncio
    async def test_error_handling_flow(self):
        """测试错误处理流程"""
        service = SSEService()
        
        try:
            # 注册连接
            connection_id = "conn_error"
            task_id = "task_error"
            user_id = "user_error"
            queue = await service.register_connection(connection_id, task_id, user_id)
            
            # 清空连接确认消息
            await queue.get()
            
            # 模拟任务执行过程中的错误
            await service.notify_task_progress(task_id, {
                "current_step": "开始处理",
                "progress_percent": 20.0
            })
            
            # 发送错误通知
            await service.notify_task_error(task_id, {
                "error_code": "DATA_CORRUPTION",
                "message": "数据损坏，无法继续处理",
                "failed_at": datetime.utcnow().isoformat() + "Z"
            })
            
            # 验证消息接收
            progress_message = await queue.get()
            error_message = await queue.get()
            
            assert progress_message.event_type == "progress"
            assert error_message.event_type == "error"
            assert error_message.data["error_code"] == "DATA_CORRUPTION"
            
        finally:
            await service.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])