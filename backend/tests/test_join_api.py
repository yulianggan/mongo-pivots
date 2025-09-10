"""
连接操作API测试

测试连接预览、执行、状态查询、结果获取等API端点
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime

from api.routers.join import router, join_service
from api.middleware.auth import User
from models.api.request_models import (
    JoinPreviewRequest, JoinExecuteRequest, 
    JoinOperation, DatasetReference, JoinCondition, JoinType
)
from models.api.response_models import TaskStatus, TaskProgress
from services.join_service import TaskInfo, ResultInfo
from join_engine import JoinPlanningError, JoinExecutionError


# 模拟用户
@pytest.fixture
def mock_user():
    return User(
        user_id="test_user_123",
        username="testuser",
        email="test@example.com",
        roles=["user"]
    )


# 模拟连接操作请求
@pytest.fixture
def sample_join_operation():
    return JoinOperation(
        left_dataset=DatasetReference(
            dataset_id="ds_users",
            alias="u"
        ),
        right_dataset=DatasetReference(
            dataset_id="ds_orders", 
            alias="o"
        ),
        join_type=JoinType.INNER,
        conditions=[
            JoinCondition(
                left_column="id",
                right_column="user_id",
                operator="="
            )
        ]
    )


@pytest.fixture
def sample_preview_request(sample_join_operation):
    return JoinPreviewRequest(
        operations=[sample_join_operation],
        sample_size=100
    )


@pytest.fixture
def sample_execute_request(sample_join_operation):
    return JoinExecuteRequest(
        operations=[sample_join_operation],
        result_name="test_join_result",
        save_result=True
    )


class TestJoinPreviewAPI:
    """连接预览API测试"""
    
    @pytest.mark.asyncio
    async def test_preview_success(self, sample_preview_request, mock_user):
        """测试成功的连接预览"""
        # 模拟join_service.generate_preview返回
        mock_preview_result = {
            "preview_data": [
                {"u.id": 1, "u.name": "Alice", "o.amount": 99.99},
                {"u.id": 2, "u.name": "Bob", "o.amount": 149.99}
            ],
            "resource_estimate": {
                "estimated_rows": 50000,
                "estimated_size_mb": 12.5,
                "estimated_time_seconds": 30.0,
                "memory_required_mb": 256.0,
                "complexity_score": 6.5
            },
            "plan": {
                "steps": ["Load left dataset", "Load right dataset", "Join"],
                "optimizations": ["Index optimization"],
                "join_algorithm": "hash_join"
            },
            "warnings": []
        }
        
        with patch.object(join_service, 'generate_preview', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = mock_preview_result
            
            # 导入路由处理函数
            from api.routers.join import preview_join
            
            # 调用API
            response = await preview_join(sample_preview_request, mock_user)
            
            # 验证结果
            assert response.success is True
            assert len(response.preview_data) == 2
            assert response.resource_estimate.estimated_rows == 50000
            assert len(response.plan["steps"]) == 3
            assert response.warnings == []
            
            # 验证服务调用
            mock_generate.assert_called_once_with(
                operations=sample_preview_request.operations,
                output_columns=None,
                sample_size=100,
                user_id="test_user_123"
            )
    
    @pytest.mark.asyncio
    async def test_preview_join_planning_error(self, sample_preview_request, mock_user):
        """测试连接计划错误"""
        with patch.object(join_service, 'generate_preview', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = JoinPlanningError("Invalid join condition")
            
            from api.routers.join import preview_join
            from api.middleware.error_handler import ValidationAPIError
            
            # 应该抛出ValidationAPIError
            with pytest.raises(ValidationAPIError):
                await preview_join(sample_preview_request, mock_user)
    
    @pytest.mark.asyncio  
    async def test_preview_join_execution_error(self, sample_preview_request, mock_user):
        """测试连接执行错误"""
        with patch.object(join_service, 'generate_preview', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = JoinExecutionError("Execution failed")
            
            from api.routers.join import preview_join
            from api.middleware.error_handler import APIError
            
            # 应该抛出APIError
            with pytest.raises(APIError):
                await preview_join(sample_preview_request, mock_user)


class TestJoinExecuteAPI:
    """连接执行API测试"""
    
    @pytest.mark.asyncio
    async def test_execute_success(self, sample_execute_request, mock_user):
        """测试成功的连接执行"""
        task_id = "task_abc123"
        
        # 模拟任务信息
        mock_task_info = TaskInfo(
            task_id=task_id,
            user_id="test_user_123",
            status=TaskStatus.PENDING,
            progress=TaskProgress(
                current_step="初始化任务",
                step_index=1,
                total_steps=6,
                progress_percent=0.0,
                processed_rows=0,
                total_rows=50000
            ),
            created_at=datetime.utcnow()
        )
        
        with patch.object(join_service, 'create_join_task', new_callable=AsyncMock) as mock_create, \
             patch.object(join_service, 'get_task_status', new_callable=AsyncMock) as mock_status:
            
            mock_create.return_value = task_id
            mock_status.return_value = mock_task_info
            
            from api.routers.join import execute_join
            
            # 调用API
            response = await execute_join(sample_execute_request, mock_user)
            
            # 验证结果
            assert response.success is True
            assert response.task_id == task_id
            assert response.status == TaskStatus.PENDING
            assert response.progress.current_step == "初始化任务"
            
            # 验证服务调用
            mock_create.assert_called_once_with(
                operations=sample_execute_request.operations,
                output_columns=None,
                result_name="test_join_result",
                save_result=True,
                chunk_size=10000,
                user_id="test_user_123"
            )
    
    @pytest.mark.asyncio
    async def test_execute_concurrent_limit_error(self, sample_execute_request, mock_user):
        """测试并发任务限制错误"""
        with patch.object(join_service, 'create_join_task', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RuntimeError("用户并发任务数量已达到上限 5")
            
            from api.routers.join import execute_join
            from api.middleware.error_handler import APIError
            
            # 应该抛出APIError with 409状态码
            with pytest.raises(APIError) as exc_info:
                await execute_join(sample_execute_request, mock_user)
            
            assert exc_info.value.status_code == 409


class TestTaskStatusAPI:
    """任务状态查询API测试"""
    
    @pytest.mark.asyncio
    async def test_get_task_status_success(self, mock_user):
        """测试成功获取任务状态"""
        task_id = "task_abc123"
        
        mock_task_info = TaskInfo(
            task_id=task_id,
            user_id="test_user_123",
            status=TaskStatus.RUNNING,
            progress=TaskProgress(
                current_step="执行连接操作",
                step_index=4,
                total_steps=6,
                progress_percent=75.0,
                processed_rows=37500,
                total_rows=50000
            ),
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow()
        )
        
        with patch.object(join_service, 'get_task_status', new_callable=AsyncMock) as mock_status:
            mock_status.return_value = mock_task_info
            
            from api.routers.join import get_task_status
            
            # 调用API
            response = await get_task_status(task_id, mock_user)
            
            # 验证结果
            assert response.task_id == task_id
            assert response.status == TaskStatus.RUNNING
            assert response.progress.progress_percent == 75.0
            assert response.result_id is None
            
            # 验证服务调用
            mock_status.assert_called_once_with(task_id, "test_user_123")
    
    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, mock_user):
        """测试任务不存在"""
        task_id = "nonexistent_task"
        
        with patch.object(join_service, 'get_task_status', new_callable=AsyncMock) as mock_status:
            mock_status.return_value = None
            
            from api.routers.join import get_task_status
            from api.middleware.error_handler import NotFoundAPIError
            
            # 应该抛出NotFoundAPIError
            with pytest.raises(NotFoundAPIError):
                await get_task_status(task_id, mock_user)


class TestJoinResultAPI:
    """连接结果获取API测试"""
    
    @pytest.mark.asyncio
    async def test_get_result_success(self, mock_user):
        """测试成功获取连接结果"""
        result_id = "result_xyz789"
        
        # 模拟结果数据
        from models.api.response_models import ResultMetadata
        
        mock_result = {
            "metadata": ResultMetadata(
                result_id=result_id,
                task_id="task_abc123",
                rows=50000,
                columns=5,
                size_bytes=12582912,
                created_at=datetime.utcnow()
            ),
            "data": [
                {"u.id": 1, "u.name": "Alice", "o.amount": 99.99},
                {"u.id": 2, "u.name": "Bob", "o.amount": 149.99}
            ],
            "columns": ["u.id", "u.name", "o.amount"]
        }
        
        with patch.object(join_service, 'get_result', new_callable=AsyncMock) as mock_get_result:
            mock_get_result.return_value = mock_result
            
            from api.routers.join import get_join_result
            
            # 调用API
            response = await get_join_result(
                result_id=result_id,
                offset=0,
                limit=100,
                columns=None,
                format="json",
                current_user=mock_user
            )
            
            # 验证结果
            assert response.total == 50000
            assert response.offset == 0
            assert response.limit == 100
            assert len(response.data) == 2
            assert response.metadata.result_id == result_id
            
            # 验证服务调用
            mock_get_result.assert_called_once_with(
                result_id=result_id,
                offset=0,
                limit=100,
                columns=None,
                user_id="test_user_123"
            )
    
    @pytest.mark.asyncio
    async def test_get_result_not_found(self, mock_user):
        """测试结果不存在"""
        result_id = "nonexistent_result"
        
        with patch.object(join_service, 'get_result', new_callable=AsyncMock) as mock_get_result:
            mock_get_result.return_value = None
            
            from api.routers.join import get_join_result
            from api.middleware.error_handler import NotFoundAPIError
            
            # 应该抛出NotFoundAPIError
            with pytest.raises(NotFoundAPIError):
                await get_join_result(
                    result_id=result_id,
                    offset=0,
                    limit=100,
                    columns=None,
                    format="json",
                    current_user=mock_user
                )


class TestCancelTaskAPI:
    """取消任务API测试"""
    
    @pytest.mark.asyncio
    async def test_cancel_task_success(self, mock_user):
        """测试成功取消任务"""
        task_id = "task_abc123"
        
        mock_task_info = TaskInfo(
            task_id=task_id,
            user_id="test_user_123",
            status=TaskStatus.RUNNING,
            progress=TaskProgress(
                current_step="执行中",
                step_index=3,
                total_steps=6,
                progress_percent=50.0,
                processed_rows=25000,
                total_rows=50000
            ),
            created_at=datetime.utcnow()
        )
        
        with patch.object(join_service, 'get_task_status', new_callable=AsyncMock) as mock_status, \
             patch.object(join_service, 'cancel_task', new_callable=AsyncMock) as mock_cancel:
            
            mock_status.return_value = mock_task_info
            mock_cancel.return_value = True
            
            from api.routers.join import cancel_task
            
            # 调用API
            response = await cancel_task(task_id, mock_user)
            
            # 验证结果
            assert response["message"] == f"任务 {task_id} 已取消"
            
            # 验证服务调用
            mock_status.assert_called_once_with(task_id, "test_user_123")
            mock_cancel.assert_called_once_with(task_id, "test_user_123")
    
    @pytest.mark.asyncio
    async def test_cancel_task_not_cancellable(self, mock_user):
        """测试不可取消的任务"""
        task_id = "task_abc123"
        
        mock_task_info = TaskInfo(
            task_id=task_id,
            user_id="test_user_123",
            status=TaskStatus.COMPLETED,  # 已完成，不可取消
            progress=TaskProgress(
                current_step="完成",
                step_index=6,
                total_steps=6,
                progress_percent=100.0,
                processed_rows=50000,
                total_rows=50000
            ),
            created_at=datetime.utcnow()
        )
        
        with patch.object(join_service, 'get_task_status', new_callable=AsyncMock) as mock_status:
            mock_status.return_value = mock_task_info
            
            from api.routers.join import cancel_task
            from api.middleware.error_handler import APIError
            
            # 应该抛出APIError with 409状态码
            with pytest.raises(APIError) as exc_info:
                await cancel_task(task_id, mock_user)
            
            assert exc_info.value.status_code == 409
            assert "无法取消" in str(exc_info.value.message)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])