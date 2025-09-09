"""
任务队列管理系统测试
测试TaskQueue、TaskManager、UserSession等核心功能
"""

import pytest
import pytest_asyncio
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

from core.task_queue import (
    Task, TaskStatus, TaskPriority, UserSession, TaskQueue, TaskManager,
    task_manager as global_task_manager
)


class TestTask:
    """测试Task类"""
    
    def test_task_creation(self):
        """测试任务创建"""
        task = Task(
            user_id="user1",
            name="test_task",
            description="测试任务",
            priority=TaskPriority.HIGH
        )
        
        assert task.user_id == "user1"
        assert task.name == "test_task"
        assert task.description == "测试任务"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.PENDING
        assert task.id is not None
        assert isinstance(task.created_at, datetime)
    
    def test_task_elapsed_time(self):
        """测试任务执行时间计算"""
        task = Task(user_id="user1", name="test")
        
        # 未开始的任务
        assert task.elapsed_time is None
        
        # 已开始的任务
        task.started_at = datetime.now() - timedelta(seconds=5)
        assert task.elapsed_time >= 4.9  # 允许一些时间误差
        
        # 已完成的任务
        task.completed_at = task.started_at + timedelta(seconds=3)
        assert abs(task.elapsed_time - 3.0) < 0.1
    
    def test_task_timeout(self):
        """测试任务超时检查"""
        task = Task(
            user_id="user1",
            name="test",
            timeout_seconds=2
        )
        
        # 未开始的任务
        assert not task.is_expired
        
        # 刚开始的任务
        task.started_at = datetime.now()
        assert not task.is_expired
        
        # 超时的任务
        task.started_at = datetime.now() - timedelta(seconds=3)
        assert task.is_expired
    
    def test_task_to_dict(self):
        """测试任务序列化"""
        task = Task(
            user_id="user1",
            name="test_task",
            description="测试任务",
            priority=TaskPriority.NORMAL,
            timeout_seconds=30,
            metadata={"key": "value"}
        )
        
        data = task.to_dict()
        
        assert data['user_id'] == "user1"
        assert data['name'] == "test_task"
        assert data['description'] == "测试任务"
        assert data['priority'] == "NORMAL"
        assert data['status'] == "PENDING"
        assert data['timeout_seconds'] == 30
        assert data['metadata'] == {"key": "value"}
        assert 'id' in data
        assert 'created_at' in data


class TestUserSession:
    """测试UserSession类"""
    
    def test_session_creation(self):
        """测试会话创建"""
        session = UserSession(user_id="user1")
        
        assert session.user_id == "user1"
        assert session.max_concurrent_tasks == 2
        assert session.max_queue_depth == 5
        assert len(session.running_tasks) == 0
        assert len(session.queued_tasks) == 0
    
    def test_session_task_management(self):
        """测试会话任务管理"""
        session = UserSession(user_id="user1")
        
        # 测试添加任务
        assert session.can_accept_task
        assert session.add_task("task1")
        assert len(session.queued_tasks) == 1
        assert session.total_tasks_submitted == 1
        
        # 测试开始任务
        assert session.can_start_task
        assert session.start_task("task1")
        assert len(session.running_tasks) == 1
        assert len(session.queued_tasks) == 0
        
        # 测试完成任务
        session.complete_task("task1", success=True)
        assert len(session.running_tasks) == 0
        assert len(session.completed_tasks) == 1
        assert session.total_tasks_completed == 1
    
    def test_session_capacity_limits(self):
        """测试会话容量限制"""
        session = UserSession(
            user_id="user1",
            max_concurrent_tasks=2,
            max_queue_depth=3
        )
        
        # 填满运行任务
        session.add_task("task1")
        session.add_task("task2")
        session.start_task("task1")
        session.start_task("task2")
        assert not session.can_start_task
        
        # 填满队列
        session.add_task("task3")
        session.add_task("task4")
        session.add_task("task5")
        assert not session.can_accept_task
        
        # 完成一个任务后可以接受新任务
        session.complete_task("task1")
        assert session.can_start_task
    
    def test_session_expiration(self):
        """测试会话过期"""
        session = UserSession(
            user_id="user1",
            session_timeout_minutes=1
        )
        
        # 新会话不应该过期
        assert not session.is_expired
        
        # 手动设置过期时间
        session.last_activity = datetime.now() - timedelta(minutes=2)
        assert session.is_expired
    
    def test_session_to_dict(self):
        """测试会话序列化"""
        session = UserSession(user_id="user1")
        session.add_task("task1")
        
        data = session.to_dict()
        
        assert data['user_id'] == "user1"
        assert data['max_concurrent_tasks'] == 2
        assert data['max_queue_depth'] == 5
        assert data['queued_tasks_count'] == 1
        assert data['total_tasks_submitted'] == 1
        assert 'created_at' in data
        assert 'last_activity' in data


class TestTaskQueue:
    """测试TaskQueue类"""
    
    @pytest_asyncio.fixture
    async def task_queue(self):
        """创建任务队列实例"""
        return TaskQueue()
    
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, task_queue):
        """测试任务入队出队"""
        task = Task(
            user_id="user1",
            name="test_task",
            priority=TaskPriority.HIGH
        )
        
        # 测试入队
        await task_queue.enqueue(task)
        
        # 测试出队
        dequeued_task = await task_queue.dequeue()
        assert dequeued_task is not None
        assert dequeued_task.id == task.id
        assert dequeued_task.priority == TaskPriority.HIGH
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, task_queue):
        """测试优先级排序"""
        # 创建不同优先级的任务
        low_task = Task(user_id="user1", name="low", priority=TaskPriority.LOW)
        high_task = Task(user_id="user1", name="high", priority=TaskPriority.HIGH)
        normal_task = Task(user_id="user1", name="normal", priority=TaskPriority.NORMAL)
        
        # 按非优先级顺序入队
        await task_queue.enqueue(low_task)
        await task_queue.enqueue(normal_task)
        await task_queue.enqueue(high_task)
        
        # 出队应该按优先级顺序
        first = await task_queue.dequeue()
        second = await task_queue.dequeue()
        third = await task_queue.dequeue()
        
        assert first.name == "high"
        assert second.name == "normal"
        assert third.name == "low"
    
    @pytest.mark.asyncio
    async def test_task_operations(self, task_queue):
        """测试任务操作"""
        task = Task(user_id="user1", name="test")
        await task_queue.enqueue(task)
        
        # 测试获取任务
        retrieved = await task_queue.get_task(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id
        
        # 测试更新任务
        task.status = TaskStatus.RUNNING
        await task_queue.update_task(task)
        
        updated = await task_queue.get_task(task.id)
        assert updated.status == TaskStatus.RUNNING
        
        # 测试移除任务
        removed = await task_queue.remove_task(task.id)
        assert removed is not None
        assert removed.id == task.id
        
        # 任务应该已经不存在
        not_found = await task_queue.get_task(task.id)
        assert not_found is None
    
    @pytest.mark.asyncio
    async def test_task_filtering(self, task_queue):
        """测试任务过滤"""
        # 创建不同状态和用户的任务
        task1 = Task(user_id="user1", name="task1", status=TaskStatus.RUNNING)
        task2 = Task(user_id="user2", name="task2", status=TaskStatus.COMPLETED)
        task3 = Task(user_id="user1", name="task3", status=TaskStatus.RUNNING)
        
        await task_queue.enqueue(task1)
        await task_queue.enqueue(task2)
        await task_queue.enqueue(task3)
        
        # 按状态过滤
        running_tasks = await task_queue.get_tasks_by_status(TaskStatus.RUNNING)
        assert len(running_tasks) == 2
        
        # 按用户过滤
        user1_tasks = await task_queue.get_tasks_by_user("user1")
        assert len(user1_tasks) == 2
    
    @pytest.mark.asyncio
    async def test_queue_stats(self, task_queue):
        """测试队列统计"""
        # 添加一些任务
        task1 = Task(user_id="user1", name="task1", priority=TaskPriority.HIGH)
        task2 = Task(user_id="user2", name="task2", priority=TaskPriority.LOW)
        
        await task_queue.enqueue(task1)
        await task_queue.enqueue(task2)
        
        stats = await task_queue.get_queue_stats()
        
        assert stats['total_tasks'] == 2
        assert stats['by_status']['PENDING'] == 2
        assert stats['by_priority']['HIGH'] == 1
        assert stats['by_priority']['LOW'] == 1
        assert stats['by_user']['user1'] == 1
        assert stats['by_user']['user2'] == 1


class TestTaskManager:
    """测试TaskManager类"""
    
    @pytest_asyncio.fixture
    async def task_manager(self):
        """创建任务管理器实例"""
        manager = TaskManager(max_workers=2)
        await manager.start()
        yield manager
        await manager.stop()
    
    @pytest.mark.asyncio
    async def test_task_submission(self, task_manager):
        """测试任务提交"""
        def simple_task(x, y):
            return x + y
        
        # 提交任务
        task_id = await task_manager.submit_task(
            user_id="user1",
            name="add_task",
            func=simple_task,
            args=(2, 3),
            priority=TaskPriority.HIGH
        )
        
        assert task_id is not None
        
        # 等待任务完成
        await asyncio.sleep(0.1)
        
        # 检查任务状态
        status = await task_manager.get_task_status(task_id)
        assert status is not None
        assert status['status'] in ['RUNNING', 'COMPLETED']
        
        # 等待更长时间确保完成
        await asyncio.sleep(0.5)
        
        status = await task_manager.get_task_status(task_id)
        assert status['status'] == 'COMPLETED'
        # 注意：由于result可能包含不可序列化的对象，我们这里不检查具体结果
    
    @pytest.mark.asyncio
    async def test_async_task_execution(self, task_manager):
        """测试异步任务执行"""
        async def async_task(delay):
            await asyncio.sleep(delay)
            return f"completed after {delay}s"
        
        task_id = await task_manager.submit_task(
            user_id="user1",
            name="async_task",
            func=async_task,
            args=(0.1,)
        )
        
        assert task_id is not None
        
        # 等待任务完成
        await asyncio.sleep(0.3)
        
        status = await task_manager.get_task_status(task_id)
        assert status['status'] == 'COMPLETED'
    
    @pytest.mark.asyncio
    async def test_task_failure_and_retry(self, task_manager):
        """测试任务失败和重试"""
        def failing_task():
            raise ValueError("Task failed intentionally")
        
        task_id = await task_manager.submit_task(
            user_id="user1",
            name="failing_task",
            func=failing_task,
            max_retries=2
        )
        
        assert task_id is not None
        
        # 等待任务失败和重试完成
        await asyncio.sleep(1.0)
        
        status = await task_manager.get_task_status(task_id)
        assert status['status'] == 'FAILED'
        assert status['retry_count'] == 2
        assert 'Task failed intentionally' in status['error']
    
    @pytest.mark.asyncio
    async def test_user_session_limits(self, task_manager):
        """测试用户会话限制"""
        def slow_task(delay):
            time.sleep(delay)
            return "done"
        
        # 提交多个任务超过用户限制
        task_ids = []
        for i in range(8):  # 超过max_concurrent_tasks(2) + max_queue_depth(5)
            task_id = await task_manager.submit_task(
                user_id="user1",
                name=f"slow_task_{i}",
                func=slow_task,
                args=(0.1,)
            )
            if task_id:
                task_ids.append(task_id)
        
        # 应该只接受7个任务（2个并发 + 5个排队）
        assert len(task_ids) == 7
        
        # 等待任务完成
        await asyncio.sleep(2.0)
        
        # 检查用户会话
        session = await task_manager.get_user_session("user1")
        assert session is not None
        assert session['total_tasks_submitted'] == 7
    
    @pytest.mark.asyncio
    async def test_task_cancellation(self, task_manager):
        """测试任务取消"""
        def long_running_task():
            time.sleep(10)  # 长时间运行的任务
            return "should not complete"
        
        # 提交长时间运行的任务
        task_id = await task_manager.submit_task(
            user_id="user1",
            name="long_task",
            func=long_running_task
        )
        
        # 等待任务开始
        await asyncio.sleep(0.1)
        
        # 取消任务
        cancelled = await task_manager.cancel_task(task_id, "user1")
        assert cancelled
        
        # 检查任务状态
        status = await task_manager.get_task_status(task_id)
        assert status['status'] == 'CANCELLED'
    
    @pytest.mark.asyncio
    async def test_user_tasks_retrieval(self, task_manager):
        """测试用户任务检索"""
        def simple_task(value):
            return value
        
        # 提交多个任务
        task_ids = []
        for i in range(3):
            task_id = await task_manager.submit_task(
                user_id="user1",
                name=f"task_{i}",
                func=simple_task,
                args=(i,)
            )
            task_ids.append(task_id)
        
        # 获取用户任务
        user_tasks = await task_manager.get_user_tasks("user1")
        assert len(user_tasks) == 3
        
        retrieved_ids = {task['id'] for task in user_tasks}
        assert retrieved_ids == set(task_ids)
    
    @pytest.mark.asyncio
    async def test_manager_stats(self, task_manager):
        """测试管理器统计信息"""
        def simple_task():
            return "done"
        
        # 提交一些任务
        for i in range(3):
            await task_manager.submit_task(
                user_id=f"user{i}",
                name=f"task_{i}",
                func=simple_task
            )
        
        # 等待任务完成
        await asyncio.sleep(0.5)
        
        stats = await task_manager.get_stats()
        
        assert stats['tasks_submitted'] == 3
        assert stats['running'] is True
        assert stats['workers_count'] >= 1
        assert 'uptime_seconds' in stats
        assert 'queue_stats' in stats
    
    @pytest.mark.asyncio
    async def test_manager_lifecycle(self):
        """测试管理器生命周期"""
        manager = TaskManager(max_workers=1)
        
        # 初始状态
        assert not manager._running
        
        # 启动
        await manager.start()
        assert manager._running
        assert len(manager._workers) > 0
        
        # 停止
        await manager.stop()
        assert not manager._running
        assert len(manager._workers) == 0


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """测试完整工作流程"""
        manager = TaskManager(max_workers=2)
        
        try:
            await manager.start()
            
            # 定义测试任务
            def compute_task(a, b, operation="add"):
                if operation == "add":
                    return a + b
                elif operation == "multiply":
                    return a * b
                else:
                    raise ValueError(f"Unsupported operation: {operation}")
            
            # 提交多个不同优先级的任务
            tasks = [
                ("user1", "add_task", (5, 3), {"operation": "add"}, TaskPriority.HIGH),
                ("user1", "multiply_task", (4, 7), {"operation": "multiply"}, TaskPriority.NORMAL),
                ("user2", "another_add", (2, 8), {"operation": "add"}, TaskPriority.LOW),
            ]
            
            task_ids = []
            for user_id, name, args, kwargs, priority in tasks:
                task_id = await manager.submit_task(
                    user_id=user_id,
                    name=name,
                    func=compute_task,
                    args=args,
                    kwargs=kwargs,
                    priority=priority,
                    timeout_seconds=5
                )
                if task_id:
                    task_ids.append(task_id)
            
            # 等待所有任务完成
            await asyncio.sleep(1.0)
            
            # 验证任务结果
            completed_tasks = 0
            for task_id in task_ids:
                status = await manager.get_task_status(task_id)
                if status and status['status'] == 'COMPLETED':
                    completed_tasks += 1
            
            assert completed_tasks == len(task_ids)
            
            # 验证用户会话统计
            user1_session = await manager.get_user_session("user1")
            user2_session = await manager.get_user_session("user2")
            
            assert user1_session['total_tasks_submitted'] == 2
            assert user2_session['total_tasks_submitted'] == 1
            
            # 验证管理器统计
            stats = await manager.get_stats()
            assert stats['tasks_submitted'] == 3
            assert stats['tasks_completed'] == 3
            
        finally:
            await manager.stop()


if __name__ == "__main__":
    # 运行基础测试
    pytest.main([__file__, "-v"])