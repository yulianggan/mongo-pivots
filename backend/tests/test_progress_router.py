"""
进度路由器测试

测试SSE进度推送API端点的功能
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient

from backend.api.main import create_app
from backend.models.api.response_models import TaskStatus, TaskProgress
from backend.services.join_service import TaskInfo
from backend.services.sse_service import sse_service


class TestProgressRouter:
    """进度路由器测试类"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        return create_app(enable_docs=False)
    
    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        return TestClient(app)
    
    @pytest.fixture
    async def async_client(self, app):
        """创建异步测试客户端"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = MagicMock()
        user.user_id = "test_user_123"
        user.email = "test@example.com"
        return user
    
    @pytest.fixture
    def mock_task_info(self):
        """模拟任务信息"""
        progress = TaskProgress(
            current_step="数据处理中",
            step_index=3,
            total_steps=5,
            progress_percent=60.0,
            processed_rows=6000,
            total_rows=10000
        )
        
        return TaskInfo(
            task_id="task_123",
            user_id="test_user_123",
            status=TaskStatus.RUNNING,
            progress=progress,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=None,
            result_id=None,
            error_message=None,
            execution_plan={"steps": ["init", "load", "process", "save", "complete"]}
        )
    
    def test_get_connection_stats_success(self, client, mock_user):
        """测试获取连接统计成功"""
        with patch('backend.api.routers.progress.get_current_user', return_value=mock_user):
            with patch.object(sse_service, 'get_connection_stats') as mock_stats:
                mock_stats.return_value = {
                    "total_connections": 5,
                    "active_connections": 3,
                    "task_connections": 2,
                    "user_connections": 2,
                    "redis_connected": True,
                    "uptime_seconds": 3600,
                    "connection_details": {
                        "task_123": {
                            "connection_count": 2,
                            "connections": [
                                {
                                    "connection_id": "conn_1",
                                    "user_id": "user_1",
                                    "connected_at": "2025-09-10T10:00:00Z",
                                    "last_heartbeat": "2025-09-10T10:05:00Z"
                                }
                            ]
                        }
                    }
                }
                
                response = client.get("/api/join/connections")
                assert response.status_code == status.HTTP_200_OK
                
                data = response.json()
                assert data["total_connections"] == 5
                assert data["active_connections"] == 3
                assert data["redis_connected"] is True
                assert "task_123" in data["connection_details"]
    
    def test_test_progress_push_success(self, client, mock_user):
        """测试启动模拟进度推送成功"""
        with patch('backend.api.routers.progress.get_current_user', return_value=mock_user):
            with patch('backend.api.routers.progress.simulate_task_progress') as mock_simulate:
                response = client.post("/api/join/test/test_task_456")
                assert response.status_code == status.HTTP_200_OK
                
                data = response.json()
                assert data["task_id"] == "test_task_456"
                assert data["test_mode"] is True
                assert "已启动" in data["message"]
    
    @pytest.mark.asyncio
    async def test_stream_progress_task_not_found(self, async_client, mock_user):
        """测试SSE流 - 任务不存在"""
        with patch('backend.api.routers.progress.get_current_user', return_value=mock_user):
            with patch('backend.api.routers.progress.join_service') as mock_join_service:
                mock_join_service.get_task_status.return_value = None
                
                async with async_client.stream("GET", "/api/join/progress/nonexistent_task") as response:
                    assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_stream_progress_success(self, async_client, mock_user, mock_task_info):
        """测试SSE流成功建立"""
        with patch('backend.api.routers.progress.get_current_user', return_value=mock_user):
            with patch('backend.api.routers.progress.join_service') as mock_join_service:
                with patch.object(sse_service, 'register_connection') as mock_register:
                    mock_join_service.get_task_status.return_value = mock_task_info
                    
                    # 创建模拟消息队列
                    mock_queue = AsyncMock()
                    mock_queue.get.side_effect = [
                        # 模拟一些消息后超时
                        asyncio.TimeoutError(),
                        asyncio.TimeoutError(),
                    ]
                    mock_register.return_value = mock_queue
                    
                    # 模拟客户端断开连接
                    async with async_client.stream("GET", "/api/join/progress/task_123") as response:
                        assert response.status_code == status.HTTP_200_OK
                        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
                        
                        # 读取初始状态消息
                        events = []
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                event_data = json.loads(line[6:])  # 去掉 "data: " 前缀
                                events.append(event_data)
                                break  # 只读取第一个事件
                        
                        # 验证初始状态消息
                        assert len(events) > 0
                        first_event = events[0]
                        assert first_event["task_id"] == "task_123"
                        assert first_event["user_id"] == "test_user_123"
                        assert first_event["data"]["status"] == "running"
                        assert first_event["data"]["progress"]["progress_percent"] == 60.0
    
    @pytest.mark.asyncio
    async def test_stream_progress_with_messages(self, async_client, mock_user, mock_task_info):
        """测试SSE流接收消息"""
        from backend.services.sse_service import SSEMessage
        
        with patch('backend.api.routers.progress.get_current_user', return_value=mock_user):
            with patch('backend.api.routers.progress.join_service') as mock_join_service:
                with patch.object(sse_service, 'register_connection') as mock_register:
                    with patch.object(sse_service, 'disconnect_client') as mock_disconnect:
                        mock_join_service.get_task_status.return_value = mock_task_info
                        
                        # 创建模拟消息
                        progress_message = SSEMessage(
                            event_type="progress",
                            task_id="task_123",
                            user_id="test_user_123",
                            timestamp=datetime.utcnow().isoformat() + "Z",
                            data={"progress_percent": 80.0, "current_step": "最终处理"}
                        )
                        
                        completed_message = SSEMessage(
                            event_type="completed",
                            task_id="task_123", 
                            user_id="test_user_123",
                            timestamp=datetime.utcnow().isoformat() + "Z",
                            data={"result_id": "result_123", "summary": {"total_rows": 10000}}
                        )
                        
                        # 创建模拟消息队列
                        mock_queue = AsyncMock()
                        mock_queue.get.side_effect = [
                            progress_message,
                            completed_message
                        ]
                        mock_register.return_value = mock_queue
                        
                        async with async_client.stream("GET", "/api/join/progress/task_123") as response:
                            assert response.status_code == status.HTTP_200_OK
                            
                            events = []
                            async for line in response.aiter_lines():
                                if line.startswith("event: "):
                                    event_type = line[7:]  # 去掉 "event: " 前缀
                                elif line.startswith("data: "):
                                    event_data = json.loads(line[6:])
                                    events.append((event_type, event_data))
                                    
                                    # 收到完成消息后停止
                                    if event_type == "completed":
                                        break
                            
                            # 验证接收到的事件
                            assert len(events) >= 3  # 至少有状态、进度、完成三个事件
                            
                            # 查找进度和完成事件
                            progress_event = next((e for e in events if e[0] == "progress"), None)
                            completed_event = next((e for e in events if e[0] == "completed"), None)
                            
                            assert progress_event is not None
                            assert completed_event is not None
                            
                            assert progress_event[1]["data"]["progress_percent"] == 80.0
                            assert completed_event[1]["data"]["result_id"] == "result_123"
    
    @pytest.mark.asyncio
    async def test_stream_progress_error_handling(self, async_client, mock_user, mock_task_info):
        """测试SSE流错误处理"""
        with patch('backend.api.routers.progress.get_current_user', return_value=mock_user):
            with patch('backend.api.routers.progress.join_service') as mock_join_service:
                with patch.object(sse_service, 'register_connection') as mock_register:
                    mock_join_service.get_task_status.return_value = mock_task_info
                    
                    # 模拟注册连接时出错
                    mock_register.side_effect = Exception("Connection registration failed")
                    
                    async with async_client.stream("GET", "/api/join/progress/task_123") as response:
                        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    
    def test_notify_functions_backward_compatibility(self):
        """测试向后兼容的通知函数"""
        from backend.api.routers.progress import (
            notify_task_progress, notify_task_completion, notify_task_error
        )
        
        with patch.object(sse_service, 'notify_task_progress') as mock_progress:
            with patch.object(sse_service, 'notify_task_completed') as mock_completed:
                with patch.object(sse_service, 'notify_task_error') as mock_error:
                    
                    # 测试进度通知
                    asyncio.run(notify_task_progress("task_123", {"progress": 50.0}))
                    mock_progress.assert_called_once_with("task_123", {"progress": 50.0})
                    
                    # 测试完成通知
                    asyncio.run(notify_task_completion("task_123", {"result_id": "result_123"}))
                    mock_completed.assert_called_once_with("task_123", {"result_id": "result_123"})
                    
                    # 测试错误通知
                    asyncio.run(notify_task_error("task_123", {"error": "failed"}))
                    mock_error.assert_called_once_with("task_123", {"error": "failed"})


class TestSimulateTaskProgress:
    """模拟任务进度测试类"""
    
    @pytest.mark.asyncio
    async def test_simulate_task_progress_complete_flow(self):
        """测试完整的模拟任务进度流程"""
        from backend.api.routers.progress import simulate_task_progress
        
        task_id = "test_simulation_task"
        
        with patch.object(sse_service, 'notify_task_progress') as mock_progress:
            with patch.object(sse_service, 'notify_task_completed') as mock_completed:
                with patch('asyncio.sleep', new_callable=AsyncMock):  # 加速测试
                    
                    await simulate_task_progress(task_id)
                    
                    # 验证进度通知调用
                    assert mock_progress.call_count == 7  # 7个步骤
                    
                    # 验证完成通知调用
                    mock_completed.assert_called_once()
                    
                    # 验证最后一次进度调用
                    last_progress_call = mock_progress.call_args_list[-1]
                    assert last_progress_call[0][0] == task_id
                    assert last_progress_call[0][1]["progress_percent"] == 100.0
                    
                    # 验证完成通知内容
                    completed_call = mock_completed.call_args
                    assert completed_call[0][0] == task_id
                    assert completed_call[0][1]["result_id"] == f"result_{task_id}_completed"
                    assert completed_call[0][1]["summary"]["success"] is True


class TestProgressRouterIntegration:
    """进度路由器集成测试"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_sse_flow(self):
        """测试端到端SSE流程"""
        # 这个测试需要真实的SSE连接，比较复杂
        # 在实际项目中，可能需要使用专门的SSE测试工具
        pass
    
    @pytest.mark.asyncio
    async def test_multiple_clients_same_task(self):
        """测试多个客户端连接同一任务"""
        # 测试多个客户端同时监听同一任务的进度
        pass
    
    @pytest.mark.asyncio
    async def test_client_disconnect_cleanup(self):
        """测试客户端断开连接的清理"""
        # 测试客户端断开连接后的资源清理
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])