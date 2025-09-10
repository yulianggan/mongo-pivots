"""
连接服务 - 数据连接的业务逻辑层

提供数据连接预览、执行、状态管理、结果获取等核心功能
"""
import logging
import asyncio
import uuid
import time
from typing import Dict, List, Any, Optional, Tuple, AsyncIterator
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import polars as pl
from pydantic import BaseModel

from ..join_engine import (
    JoinEngine, JoinEngineFactory, 
    JoinType, JoinCondition, ExecutionPlan, ResourceEstimate,
    ExecutionProgress, ExecutionStats, 
    JoinEngineError, JoinPlanningError, JoinExecutionError
)
from ..core.config import settings
from ..connectors.registry import registry
from ..models.api.request_models import (
    JoinOperation, JoinPreviewRequest, JoinExecuteRequest
)
from ..models.api.response_models import (
    ResourceEstimate as APIResourceEstimate,
    TaskProgress, TaskStatus,
    ResultMetadata
)

logger = logging.getLogger(__name__)


class TaskInfo(BaseModel):
    """任务信息模型"""
    task_id: str
    user_id: str
    status: TaskStatus
    progress: TaskProgress
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_plan: Optional[Dict[str, Any]] = None


class ResultInfo(BaseModel):
    """结果信息模型"""
    result_id: str
    task_id: str
    user_id: str
    metadata: ResultMetadata
    data_location: str  # 数据存储位置
    created_at: datetime
    expires_at: Optional[datetime] = None


class JoinService:
    """连接服务主类"""
    
    def __init__(self):
        """初始化连接服务"""
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 内存存储（生产环境应替换为Redis等持久化存储）
        self._tasks: Dict[str, TaskInfo] = {}
        self._results: Dict[str, ResultInfo] = {}
        self._user_tasks: Dict[str, List[str]] = {}  # user_id -> [task_ids]
        
        # 任务管理
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._task_locks: Dict[str, asyncio.Lock] = {}
        
        # 配置
        self._max_concurrent_tasks = getattr(settings, 'max_concurrent_tasks', 5)
        self._result_ttl_hours = getattr(settings, 'result_ttl_hours', 24)
        self._max_preview_rows = getattr(settings, 'max_preview_rows', 1000)
        
        self._logger.info("JoinService initialized")
    
    async def generate_preview(
        self,
        operations: List[JoinOperation],
        output_columns: Optional[List[str]] = None,
        sample_size: int = 1000,
        user_id: str = ""
    ) -> Dict[str, Any]:
        """
        生成连接预览
        
        Args:
            operations: 连接操作列表
            output_columns: 输出列列表
            sample_size: 样本大小
            user_id: 用户ID
            
        Returns:
            包含预览数据、资源估算、执行计划和警告的字典
            
        Raises:
            JoinPlanningError: 计划生成失败
            JoinExecutionError: 预览执行失败
        """
        start_time = time.time()
        self._logger.info(f"Generating join preview for user {user_id}, {len(operations)} operations")
        
        try:
            # 创建连接引擎
            engine = JoinEngineFactory.create_engine(
                optimization_level=1,  # 预览使用较低优化级别
                memory_limit_mb=512,
                enable_caching=True
            )
            
            # 转换操作为引擎格式
            sources, join_specs = self._convert_operations_to_engine_format(operations)
            
            # 创建执行计划
            execution_plan = await engine.plan_join(sources, join_specs)
            
            # 获取资源估算
            resource_estimate = execution_plan.resource_estimate
            
            # 生成预览数据（限制行数）
            limited_sample_size = min(sample_size, self._max_preview_rows)
            preview_data = await self._generate_preview_data(
                engine, execution_plan, limited_sample_size, output_columns
            )
            
            # 生成警告
            warnings = self._generate_warnings(resource_estimate, execution_plan)
            
            # 转换为API格式
            api_resource_estimate = self._convert_resource_estimate(resource_estimate)
            api_plan = self._convert_execution_plan(execution_plan)
            
            elapsed_time = time.time() - start_time
            self._logger.info(f"Join preview generated in {elapsed_time:.2f}s, {len(preview_data)} rows")
            
            return {
                "preview_data": preview_data,
                "resource_estimate": api_resource_estimate,
                "plan": api_plan,
                "warnings": warnings
            }
            
        except JoinEngineError as e:
            self._logger.error(f"Join engine error during preview: {e}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error during preview generation: {e}")
            raise JoinExecutionError(f"预览生成失败: {str(e)}")
    
    async def create_join_task(
        self,
        operations: List[JoinOperation],
        output_columns: Optional[List[str]] = None,
        result_name: Optional[str] = None,
        save_result: bool = True,
        chunk_size: int = 10000,
        user_id: str = ""
    ) -> str:
        """
        创建连接任务
        
        Args:
            operations: 连接操作列表
            output_columns: 输出列列表
            result_name: 结果名称
            save_result: 是否保存结果
            chunk_size: 分块大小
            user_id: 用户ID
            
        Returns:
            任务ID
            
        Raises:
            ValueError: 参数验证失败
            RuntimeError: 任务创建失败
        """
        self._logger.info(f"Creating join task for user {user_id}")
        
        # 检查并发任务数量限制
        user_running_tasks = self._get_user_running_tasks(user_id)
        if len(user_running_tasks) >= self._max_concurrent_tasks:
            raise RuntimeError(f"用户并发任务数量已达到上限 {self._max_concurrent_tasks}")
        
        # 生成任务ID
        task_id = f"task_{uuid.uuid4().hex}"
        
        try:
            # 创建执行计划
            engine = JoinEngineFactory.create_engine(
                optimization_level=2,
                memory_limit_mb=2048,
                enable_caching=True
            )
            
            sources, join_specs = self._convert_operations_to_engine_format(operations)
            execution_plan = await engine.plan_join(sources, join_specs)
            
            # 创建任务信息
            task_info = TaskInfo(
                task_id=task_id,
                user_id=user_id,
                status=TaskStatus.PENDING,
                progress=TaskProgress(
                    current_step="初始化任务",
                    step_index=1,
                    total_steps=len(execution_plan.steps) + 2,  # +2 for init and finalize
                    progress_percent=0.0,
                    processed_rows=0,
                    total_rows=execution_plan.resource_estimate.estimated_rows
                ),
                created_at=datetime.utcnow(),
                execution_plan=execution_plan.dict() if hasattr(execution_plan, 'dict') else {}
            )
            
            # 存储任务信息
            self._tasks[task_id] = task_info
            
            # 添加到用户任务列表
            if user_id not in self._user_tasks:
                self._user_tasks[user_id] = []
            self._user_tasks[user_id].append(task_id)
            
            # 创建任务锁
            self._task_locks[task_id] = asyncio.Lock()
            
            # 启动异步执行任务
            execution_task = asyncio.create_task(
                self._execute_join_task(
                    task_id, engine, execution_plan, 
                    output_columns, result_name, save_result, chunk_size
                )
            )
            self._running_tasks[task_id] = execution_task
            
            self._logger.info(f"Join task {task_id} created successfully")
            return task_id
            
        except Exception as e:
            # 清理部分创建的资源
            if task_id in self._tasks:
                del self._tasks[task_id]
            if user_id in self._user_tasks and task_id in self._user_tasks[user_id]:
                self._user_tasks[user_id].remove(task_id)
            if task_id in self._task_locks:
                del self._task_locks[task_id]
                
            self._logger.error(f"Failed to create join task: {e}")
            raise RuntimeError(f"任务创建失败: {str(e)}")
    
    async def get_task_status(self, task_id: str, user_id: str) -> Optional[TaskInfo]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            user_id: 用户ID
            
        Returns:
            任务信息，如果不存在返回None
        """
        if task_id not in self._tasks:
            return None
        
        task_info = self._tasks[task_id]
        
        # 验证用户权限
        if task_info.user_id != user_id:
            return None
        
        return task_info
    
    async def get_result(
        self,
        result_id: str,
        offset: int = 0,
        limit: int = 100,
        columns: Optional[List[str]] = None,
        user_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        """
        获取连接结果
        
        Args:
            result_id: 结果ID
            offset: 偏移量
            limit: 限制数量
            columns: 选择的列
            user_id: 用户ID
            
        Returns:
            结果数据字典，如果不存在返回None
        """
        if result_id not in self._results:
            return None
        
        result_info = self._results[result_id]
        
        # 验证用户权限
        if result_info.user_id != user_id:
            return None
        
        # 检查结果是否过期
        if result_info.expires_at and datetime.utcnow() > result_info.expires_at:
            await self._cleanup_result(result_id)
            return None
        
        try:
            # 从存储位置读取数据
            data = await self._read_result_data(
                result_info.data_location, offset, limit, columns
            )
            
            return {
                "metadata": result_info.metadata,
                "data": data,
                "columns": columns or await self._get_result_columns(result_info.data_location)
            }
            
        except Exception as e:
            self._logger.error(f"Failed to read result data {result_id}: {e}")
            return None
    
    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            user_id: 用户ID
            
        Returns:
            是否成功取消
        """
        if task_id not in self._tasks:
            return False
        
        task_info = self._tasks[task_id]
        
        # 验证用户权限
        if task_info.user_id != user_id:
            return False
        
        # 检查任务状态
        if task_info.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return False
        
        try:
            # 取消执行任务
            if task_id in self._running_tasks:
                execution_task = self._running_tasks[task_id]
                execution_task.cancel()
                
                try:
                    await execution_task
                except asyncio.CancelledError:
                    pass
                
                del self._running_tasks[task_id]
            
            # 更新任务状态
            async with self._task_locks.get(task_id, asyncio.Lock()):
                task_info.status = TaskStatus.CANCELLED
                task_info.completed_at = datetime.utcnow()
                task_info.error_message = "任务已被用户取消"
            
            self._logger.info(f"Task {task_id} cancelled successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to cancel task {task_id}: {e}")
            return False
    
    def _convert_operations_to_engine_format(
        self, 
        operations: List[JoinOperation]
    ) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
        """转换API操作格式为引擎格式"""
        sources = {}
        join_specs = []
        
        for i, operation in enumerate(operations):
            # 构建数据源映射
            left_alias = operation.left_dataset.alias or f"left_{i}"
            right_alias = operation.right_dataset.alias or f"right_{i}"
            
            sources[left_alias] = operation.left_dataset.dataset_id
            sources[right_alias] = operation.right_dataset.dataset_id
            
            # 构建连接规格
            join_spec = {
                "left_alias": left_alias,
                "right_alias": right_alias,
                "join_type": operation.join_type.value,
                "conditions": [
                    {
                        "left_column": cond.left_column,
                        "right_column": cond.right_column,
                        "operator": cond.operator
                    }
                    for cond in operation.conditions
                ],
                "left_columns": operation.left_dataset.columns,
                "right_columns": operation.right_dataset.columns,
                "left_filters": operation.left_dataset.filters,
                "right_filters": operation.right_dataset.filters
            }
            
            join_specs.append(join_spec)
        
        return sources, join_specs
    
    async def _generate_preview_data(
        self,
        engine: JoinEngine,
        execution_plan: ExecutionPlan,
        sample_size: int,
        output_columns: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """生成预览数据"""
        try:
            # 使用引擎执行预览
            async with engine.execute_preview(execution_plan, sample_size) as result_stream:
                preview_rows = []
                async for batch in result_stream:
                    for row in batch.iter_rows(named=True):
                        if len(preview_rows) >= sample_size:
                            break
                        preview_rows.append(row)
                    if len(preview_rows) >= sample_size:
                        break
                
                # 应用列过滤
                if output_columns:
                    filtered_rows = []
                    for row in preview_rows:
                        filtered_row = {col: row.get(col) for col in output_columns if col in row}
                        filtered_rows.append(filtered_row)
                    return filtered_rows
                
                return preview_rows
                
        except Exception as e:
            self._logger.warning(f"Failed to generate real preview data, using mock: {e}")
            # 返回模拟数据
            return self._generate_mock_preview_data(sample_size, output_columns)
    
    def _generate_mock_preview_data(
        self, 
        sample_size: int, 
        output_columns: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """生成模拟预览数据"""
        mock_data = []
        for i in range(min(sample_size, 10)):  # 限制模拟数据数量
            row = {
                "u.id": i + 1,
                "u.name": f"User{i + 1}",
                "u.email": f"user{i + 1}@example.com",
                "o.user_id": i + 1,
                "o.amount": (i + 1) * 10.5,
                "o.created_at": f"2025-09-10T{10 + (i % 12):02d}:00:00Z"
            }
            
            if output_columns:
                row = {col: row.get(col) for col in output_columns if col in row}
            
            mock_data.append(row)
        
        return mock_data
    
    def _generate_warnings(
        self, 
        resource_estimate: ResourceEstimate, 
        execution_plan: ExecutionPlan
    ) -> List[str]:
        """生成警告信息"""
        warnings = []
        
        if resource_estimate.memory_required_mb > 1024:
            warnings.append("预估内存使用量较高，建议分批处理")
        
        if resource_estimate.estimated_time_seconds > 300:
            warnings.append("预估执行时间较长，请耐心等待")
        
        if hasattr(resource_estimate, 'complexity_score') and resource_estimate.complexity_score > 8.0:
            warnings.append("连接操作复杂度较高，执行时间可能较长")
        
        if resource_estimate.estimated_rows > 1000000:
            warnings.append("结果行数较多，建议使用分页获取数据")
        
        return warnings
    
    def _convert_resource_estimate(self, estimate: ResourceEstimate) -> APIResourceEstimate:
        """转换资源估算为API格式"""
        return APIResourceEstimate(
            estimated_rows=estimate.estimated_rows,
            estimated_size_mb=estimate.estimated_size_mb,
            estimated_time_seconds=estimate.estimated_time_seconds,
            memory_required_mb=estimate.memory_required_mb,
            complexity_score=getattr(estimate, 'complexity_score', 5.0)
        )
    
    def _convert_execution_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """转换执行计划为API格式"""
        return {
            "steps": [step.description for step in plan.steps],
            "optimizations": plan.optimizations or [],
            "join_algorithm": getattr(plan, 'join_algorithm', 'hash_join'),
            "estimated_partitions": getattr(plan, 'estimated_partitions', 1)
        }
    
    def _get_user_running_tasks(self, user_id: str) -> List[str]:
        """获取用户正在运行的任务"""
        if user_id not in self._user_tasks:
            return []
        
        running_tasks = []
        for task_id in self._user_tasks[user_id]:
            if task_id in self._tasks:
                task_info = self._tasks[task_id]
                if task_info.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    running_tasks.append(task_id)
        
        return running_tasks
    
    async def _execute_join_task(
        self,
        task_id: str,
        engine: JoinEngine,
        execution_plan: ExecutionPlan,
        output_columns: Optional[List[str]],
        result_name: Optional[str],
        save_result: bool,
        chunk_size: int
    ):
        """执行连接任务的异步函数"""
        try:
            self._logger.info(f"Starting execution of task {task_id}")
            
            # 更新任务状态为运行中
            await self._update_task_status(
                task_id, TaskStatus.RUNNING, 
                TaskProgress(
                    current_step="开始执行连接",
                    step_index=2,
                    total_steps=len(execution_plan.steps) + 2,
                    progress_percent=5.0,
                    processed_rows=0,
                    total_rows=execution_plan.resource_estimate.estimated_rows
                ),
                started_at=datetime.utcnow()
            )
            
            # 模拟执行过程
            await self._simulate_task_execution(task_id, execution_plan)
            
            # 创建结果
            if save_result:
                result_id = await self._create_task_result(
                    task_id, result_name, execution_plan, output_columns
                )
            else:
                result_id = None
            
            # 更新任务为完成
            await self._update_task_status(
                task_id, TaskStatus.COMPLETED,
                TaskProgress(
                    current_step="任务完成",
                    step_index=len(execution_plan.steps) + 2,
                    total_steps=len(execution_plan.steps) + 2,
                    progress_percent=100.0,
                    processed_rows=execution_plan.resource_estimate.estimated_rows,
                    total_rows=execution_plan.resource_estimate.estimated_rows
                ),
                completed_at=datetime.utcnow(),
                result_id=result_id
            )
            
            self._logger.info(f"Task {task_id} completed successfully")
            
        except asyncio.CancelledError:
            self._logger.info(f"Task {task_id} was cancelled")
            raise
        except Exception as e:
            self._logger.error(f"Task {task_id} failed: {e}")
            await self._update_task_status(
                task_id, TaskStatus.FAILED,
                error_message=str(e),
                completed_at=datetime.utcnow()
            )
        finally:
            # 清理运行任务记录
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]
    
    async def _simulate_task_execution(self, task_id: str, execution_plan: ExecutionPlan):
        """模拟任务执行过程"""
        total_steps = len(execution_plan.steps) + 2
        total_rows = execution_plan.resource_estimate.estimated_rows
        
        for i, step in enumerate(execution_plan.steps):
            # 检查是否被取消
            if task_id not in self._running_tasks:
                raise asyncio.CancelledError()
            
            # 更新进度
            step_index = i + 2  # +1 for init step
            progress_percent = (step_index / total_steps) * 100
            processed_rows = int((step_index / total_steps) * total_rows)
            
            await self._update_task_status(
                task_id, TaskStatus.RUNNING,
                TaskProgress(
                    current_step=step.description,
                    step_index=step_index,
                    total_steps=total_steps,
                    progress_percent=progress_percent,
                    processed_rows=processed_rows,
                    total_rows=total_rows
                )
            )
            
            # 模拟处理时间
            await asyncio.sleep(1)
    
    async def _update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[TaskProgress] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        result_id: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """更新任务状态"""
        if task_id not in self._tasks:
            return
        
        async with self._task_locks.get(task_id, asyncio.Lock()):
            task_info = self._tasks[task_id]
            task_info.status = status
            
            if progress:
                task_info.progress = progress
            if started_at:
                task_info.started_at = started_at
            if completed_at:
                task_info.completed_at = completed_at
            if result_id:
                task_info.result_id = result_id
            if error_message:
                task_info.error_message = error_message
    
    async def _create_task_result(
        self,
        task_id: str,
        result_name: Optional[str],
        execution_plan: ExecutionPlan,
        output_columns: Optional[List[str]]
    ) -> str:
        """创建任务结果"""
        result_id = f"result_{uuid.uuid4().hex}"
        task_info = self._tasks[task_id]
        
        # 模拟数据存储位置
        data_location = f"/data/results/{result_id}.parquet"
        
        # 创建结果元数据
        metadata = ResultMetadata(
            result_id=result_id,
            task_id=task_id,
            rows=execution_plan.resource_estimate.estimated_rows,
            columns=len(output_columns) if output_columns else 10,  # 模拟列数
            size_bytes=int(execution_plan.resource_estimate.estimated_size_mb * 1024 * 1024),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=self._result_ttl_hours)
        )
        
        # 创建结果信息
        result_info = ResultInfo(
            result_id=result_id,
            task_id=task_id,
            user_id=task_info.user_id,
            metadata=metadata,
            data_location=data_location,
            created_at=datetime.utcnow(),
            expires_at=metadata.expires_at
        )
        
        # 存储结果信息
        self._results[result_id] = result_info
        
        self._logger.info(f"Result {result_id} created for task {task_id}")
        return result_id
    
    async def _read_result_data(
        self,
        data_location: str,
        offset: int,
        limit: int,
        columns: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """从存储位置读取结果数据"""
        # 模拟数据读取
        data = []
        for i in range(offset, min(offset + limit, offset + 100)):  # 模拟100行数据
            row = {
                "u.id": i + 1,
                "u.name": f"User{i + 1}",
                "u.email": f"user{i + 1}@example.com",
                "o.user_id": i + 1,
                "o.amount": (i + 1) * 10.5,
                "o.created_at": f"2025-09-10T{10 + (i % 12):02d}:00:00Z"
            }
            
            if columns:
                row = {col: row.get(col) for col in columns if col in row}
            
            data.append(row)
        
        return data
    
    async def _get_result_columns(self, data_location: str) -> List[str]:
        """获取结果数据的列名"""
        # 模拟列名
        return ["u.id", "u.name", "u.email", "o.user_id", "o.amount", "o.created_at"]
    
    async def _cleanup_result(self, result_id: str):
        """清理过期结果"""
        if result_id in self._results:
            result_info = self._results[result_id]
            # 删除数据文件
            # TODO: 实际删除存储的数据文件
            del self._results[result_id]
            self._logger.info(f"Result {result_id} cleaned up")