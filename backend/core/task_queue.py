"""
任务队列管理系统
实现任务队列管理、并发控制、状态跟踪和用户会话管理
"""

import asyncio
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
from collections import defaultdict, deque
import json


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class Task:
    """任务数据结构"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    name: str = ""
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout_seconds: Optional[int] = None
    max_retries: int = 0
    retry_count: int = 0
    
    # 任务执行相关
    func: Optional[Callable] = field(default=None, repr=False)
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    
    # 结果和错误信息
    result: Any = None
    error: Optional[str] = None
    
    # 任务元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """确保ID和时间戳的正确性"""
        if not self.id:
            self.id = str(uuid.uuid4())
        if not isinstance(self.created_at, datetime):
            self.created_at = datetime.now()
    
    @property
    def elapsed_time(self) -> Optional[float]:
        """获取任务执行时间（秒）"""
        if not self.started_at:
            return None
        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds()
    
    @property
    def is_expired(self) -> bool:
        """检查任务是否超时"""
        if not self.timeout_seconds or not self.started_at:
            return False
        return (datetime.now() - self.started_at).total_seconds() > self.timeout_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'priority': self.priority.name,
            'status': self.status.name,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'timeout_seconds': self.timeout_seconds,
            'max_retries': self.max_retries,
            'retry_count': self.retry_count,
            'elapsed_time': self.elapsed_time,
            'is_expired': self.is_expired,
            'error': self.error,
            'metadata': self.metadata
        }


@dataclass
class UserSession:
    """用户会话管理"""
    user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    max_concurrent_tasks: int = 2
    max_queue_depth: int = 5
    session_timeout_minutes: int = 30
    
    # 会话状态
    running_tasks: Set[str] = field(default_factory=set)
    queued_tasks: deque = field(default_factory=deque)
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    
    # 统计信息
    total_tasks_submitted: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    
    def __post_init__(self):
        """初始化后处理"""
        if not isinstance(self.queued_tasks, deque):
            self.queued_tasks = deque(self.queued_tasks)
    
    @property
    def is_expired(self) -> bool:
        """检查会话是否过期"""
        timeout_delta = timedelta(minutes=self.session_timeout_minutes)
        return datetime.now() - self.last_activity > timeout_delta
    
    @property
    def can_accept_task(self) -> bool:
        """检查是否可以接受新任务"""
        total_tasks = len(self.running_tasks) + len(self.queued_tasks)
        return total_tasks < (self.max_concurrent_tasks + self.max_queue_depth)
    
    @property
    def can_start_task(self) -> bool:
        """检查是否可以开始执行任务"""
        return len(self.running_tasks) < self.max_concurrent_tasks
    
    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = datetime.now()
    
    def add_task(self, task_id: str) -> bool:
        """添加任务到队列"""
        if not self.can_accept_task:
            return False
        
        self.queued_tasks.append(task_id)
        self.total_tasks_submitted += 1
        self.update_activity()
        return True
    
    def start_task(self, task_id: str) -> bool:
        """开始执行任务"""
        if not self.can_start_task:
            return False
        
        # 从队列中移除并添加到运行中
        try:
            self.queued_tasks.remove(task_id)
        except ValueError:
            pass  # 任务可能不在队列中
        
        self.running_tasks.add(task_id)
        self.update_activity()
        return True
    
    def complete_task(self, task_id: str, success: bool = True):
        """完成任务"""
        self.running_tasks.discard(task_id)
        
        if success:
            self.completed_tasks.append(task_id)
            self.total_tasks_completed += 1
        else:
            self.failed_tasks.append(task_id)
            self.total_tasks_failed += 1
        
        self.update_activity()
    
    def cancel_task(self, task_id: str):
        """取消任务"""
        # 从队列或运行中移除
        try:
            self.queued_tasks.remove(task_id)
        except ValueError:
            pass
        
        self.running_tasks.discard(task_id)
        self.update_activity()
    
    def get_next_task(self) -> Optional[str]:
        """获取下一个待执行任务"""
        if not self.can_start_task or not self.queued_tasks:
            return None
        return self.queued_tasks[0]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'max_queue_depth': self.max_queue_depth,
            'session_timeout_minutes': self.session_timeout_minutes,
            'is_expired': self.is_expired,
            'can_accept_task': self.can_accept_task,
            'can_start_task': self.can_start_task,
            'running_tasks': list(self.running_tasks),
            'queued_tasks_count': len(self.queued_tasks),
            'completed_tasks_count': len(self.completed_tasks),
            'failed_tasks_count': len(self.failed_tasks),
            'total_tasks_submitted': self.total_tasks_submitted,
            'total_tasks_completed': self.total_tasks_completed,
            'total_tasks_failed': self.total_tasks_failed
        }


class TaskQueue:
    """任务队列实现"""
    
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._priority_queues: Dict[TaskPriority, deque] = {
            priority: deque() for priority in TaskPriority
        }
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
    
    async def enqueue(self, task: Task) -> bool:
        """将任务加入队列"""
        async with self._lock:
            self._tasks[task.id] = task
            self._priority_queues[task.priority].append(task.id)
            self.logger.info(f"任务 {task.id} 已加入 {task.priority.name} 优先级队列")
            return True
    
    async def dequeue(self) -> Optional[Task]:
        """从队列中取出最高优先级任务"""
        async with self._lock:
            # 按优先级从高到低检查
            for priority in sorted(TaskPriority, key=lambda x: x.value, reverse=True):
                queue = self._priority_queues[priority]
                if queue:
                    task_id = queue.popleft()
                    task = self._tasks.get(task_id)
                    if task and task.status == TaskStatus.PENDING:
                        return task
                    
            return None
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """获取指定任务"""
        return self._tasks.get(task_id)
    
    async def update_task(self, task: Task):
        """更新任务信息"""
        async with self._lock:
            self._tasks[task.id] = task
    
    async def remove_task(self, task_id: str) -> Optional[Task]:
        """移除任务"""
        async with self._lock:
            task = self._tasks.pop(task_id, None)
            if task:
                # 从优先级队列中移除
                try:
                    self._priority_queues[task.priority].remove(task_id)
                except ValueError:
                    pass  # 任务可能已经被取出
            return task
    
    async def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """获取指定状态的任务"""
        return [task for task in self._tasks.values() if task.status == status]
    
    async def get_tasks_by_user(self, user_id: str) -> List[Task]:
        """获取用户的所有任务"""
        return [task for task in self._tasks.values() if task.user_id == user_id]
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        stats = {
            'total_tasks': len(self._tasks),
            'by_status': defaultdict(int),
            'by_priority': defaultdict(int),
            'by_user': defaultdict(int)
        }
        
        for task in self._tasks.values():
            stats['by_status'][task.status.name] += 1
            stats['by_priority'][task.priority.name] += 1
            stats['by_user'][task.user_id] += 1
        
        return dict(stats)


class TaskManager:
    """任务管理器"""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self._task_queue = TaskQueue()
        self._user_sessions: Dict[str, UserSession] = {}
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger(__name__)
        
        # 统计信息
        self._stats = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'tasks_cancelled': 0,
            'workers_active': 0,
            'start_time': datetime.now()
        }
    
    async def start(self):
        """启动任务管理器"""
        if self._running:
            return
        
        self._running = True
        self.logger.info(f"启动任务管理器，工作线程数: {self.max_workers}")
        
        # 启动工作线程
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)
        
        # 启动会话清理任务
        cleanup_task = asyncio.create_task(self._cleanup_sessions())
        self._workers.append(cleanup_task)
    
    async def stop(self):
        """停止任务管理器"""
        if not self._running:
            return
        
        self._running = False
        self.logger.info("停止任务管理器")
        
        # 取消所有工作线程
        for worker in self._workers:
            worker.cancel()
        
        # 等待所有工作线程完成
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
    
    def get_or_create_session(self, user_id: str) -> UserSession:
        """获取或创建用户会话"""
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = UserSession(user_id=user_id)
        return self._user_sessions[user_id]
    
    async def submit_task(
        self,
        user_id: str,
        name: str,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout_seconds: Optional[int] = None,
        max_retries: int = 0,
        description: str = "",
        metadata: dict = None
    ) -> Optional[str]:
        """提交任务"""
        kwargs = kwargs or {}
        metadata = metadata or {}
        
        # 获取用户会话
        session = self.get_or_create_session(user_id)
        
        # 检查是否可以接受新任务
        if not session.can_accept_task:
            self.logger.warning(f"用户 {user_id} 队列已满，无法接受新任务")
            return None
        
        # 创建任务
        task = Task(
            user_id=user_id,
            name=name,
            description=description,
            priority=priority,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            func=func,
            args=args,
            kwargs=kwargs,
            metadata=metadata
        )
        
        # 添加任务到用户会话
        if not session.add_task(task.id):
            self.logger.warning(f"无法将任务 {task.id} 添加到用户 {user_id} 的会话")
            return None
        
        # 添加任务到队列
        await self._task_queue.enqueue(task)
        
        self._stats['tasks_submitted'] += 1
        self.logger.info(f"任务 {task.id} 已提交，用户: {user_id}, 优先级: {priority.name}")
        
        return task.id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task = await self._task_queue.get_task(task_id)
        return task.to_dict() if task else None
    
    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """取消任务"""
        task = await self._task_queue.get_task(task_id)
        if not task or task.user_id != user_id:
            return False
        
        # 更新任务状态
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        await self._task_queue.update_task(task)
        
        # 更新用户会话
        session = self.get_or_create_session(user_id)
        session.cancel_task(task_id)
        
        self._stats['tasks_cancelled'] += 1
        self.logger.info(f"任务 {task_id} 已取消")
        
        return True
    
    async def get_user_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的所有任务"""
        tasks = await self._task_queue.get_tasks_by_user(user_id)
        return [task.to_dict() for task in tasks]
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户会话信息"""
        session = self._user_sessions.get(user_id)
        return session.to_dict() if session else None
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        queue_stats = await self._task_queue.get_queue_stats()
        
        return {
            **self._stats,
            'workers_count': len(self._workers),
            'running': self._running,
            'active_sessions': len(self._user_sessions),
            'uptime_seconds': (datetime.now() - self._stats['start_time']).total_seconds(),
            'queue_stats': queue_stats
        }
    
    async def _worker(self, worker_id: str):
        """工作线程"""
        self.logger.info(f"工作线程 {worker_id} 已启动")
        
        while self._running:
            try:
                # 获取任务
                task = await self._task_queue.dequeue()
                if not task:
                    await asyncio.sleep(0.1)  # 短暂休眠
                    continue
                
                # 检查用户会话是否可以执行任务
                session = self.get_or_create_session(task.user_id)
                if not session.start_task(task.id):
                    # 重新加入队列
                    await self._task_queue.enqueue(task)
                    continue
                
                self._stats['workers_active'] += 1
                
                try:
                    await self._execute_task(task, worker_id)
                finally:
                    self._stats['workers_active'] -= 1
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"工作线程 {worker_id} 发生错误: {e}")
                await asyncio.sleep(1)
        
        self.logger.info(f"工作线程 {worker_id} 已停止")
    
    async def _execute_task(self, task: Task, worker_id: str):
        """执行任务"""
        self.logger.info(f"工作线程 {worker_id} 开始执行任务 {task.id}")
        
        # 更新任务状态
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        await self._task_queue.update_task(task)
        
        session = self.get_or_create_session(task.user_id)
        success = False
        
        try:
            # 执行任务函数
            if asyncio.iscoroutinefunction(task.func):
                result = await task.func(*task.args, **task.kwargs)
            else:
                result = task.func(*task.args, **task.kwargs)
            
            # 任务成功完成
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            success = True
            
            self._stats['tasks_completed'] += 1
            self.logger.info(f"任务 {task.id} 执行成功，耗时: {task.elapsed_time:.2f}秒")
            
        except Exception as e:
            # 任务执行失败
            error_msg = f"任务执行失败: {str(e)}"
            task.error = error_msg
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            
            self._stats['tasks_failed'] += 1
            self.logger.error(f"任务 {task.id} 执行失败: {e}")
            
            # 检查是否需要重试
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.PENDING
                task.started_at = None
                task.completed_at = None
                task.error = None
                
                # 重新加入队列
                await self._task_queue.enqueue(task)
                self.logger.info(f"任务 {task.id} 将进行第 {task.retry_count} 次重试")
                
                # 不更新会话状态，让任务重新排队
                return
        
        finally:
            # 更新任务状态
            await self._task_queue.update_task(task)
            
            # 更新用户会话
            session.complete_task(task.id, success)
    
    async def _cleanup_sessions(self):
        """清理过期会话"""
        while self._running:
            try:
                current_time = datetime.now()
                expired_sessions = []
                
                for user_id, session in self._user_sessions.items():
                    if session.is_expired:
                        expired_sessions.append(user_id)
                
                for user_id in expired_sessions:
                    del self._user_sessions[user_id]
                    self.logger.info(f"清理过期会话: {user_id}")
                
                # 每分钟清理一次
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"清理会话时发生错误: {e}")
                await asyncio.sleep(60)
    
    @asynccontextmanager
    async def lifespan(self):
        """生命周期管理器"""
        await self.start()
        try:
            yield self
        finally:
            await self.stop()


# 全局任务管理器实例
task_manager = TaskManager()