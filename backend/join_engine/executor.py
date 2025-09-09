"""
JoinExecutor - 连接执行器
执行连接计划的核心引擎，与Polars数据引擎深度集成
"""
import polars as pl
from typing import Dict, List, Any, Optional, Iterator, Tuple, Callable
from dataclasses import dataclass
import asyncio
import time
import logging
from contextlib import asynccontextmanager

from connectors.base import DataSourceConnector, QueryOptions
from connectors.registry import registry
from core.data_engine import data_engine
from core.memory_guard import memory_guard
from .planner import ExecutionPlan, JoinStep, JoinType, JoinCondition


@dataclass
class ExecutionProgress:
    """执行进度"""
    step_index: int
    total_steps: int
    current_step: Optional[JoinStep]
    rows_processed: int
    estimated_remaining_time: Optional[float]
    status: str  # running, completed, failed, paused
    error_message: Optional[str] = None
    
    @property
    def progress_percent(self) -> float:
        if self.total_steps == 0:
            return 100.0
        return (self.step_index / self.total_steps) * 100


@dataclass
class ExecutionStats:
    """执行统计"""
    execution_id: str
    start_time: float
    end_time: Optional[float]
    total_rows_processed: int
    total_memory_used_mb: float
    peak_memory_used_mb: float
    steps_completed: int
    steps_failed: int
    
    @property
    def duration(self) -> Optional[float]:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time


class JoinExecutor:
    """连接执行器"""
    
    def __init__(self, memory_limit_mb: Optional[float] = None):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.memory_limit_mb = memory_limit_mb or 2048  # 默认2GB限制
        
        # 执行状态管理
        self._active_executions: Dict[str, ExecutionProgress] = {}
        self._execution_stats: Dict[str, ExecutionStats] = {}
        
        # 支持的连接操作映射
        self._join_operations = {
            JoinType.INNER: self._execute_inner_join,
            JoinType.LEFT: self._execute_left_join,
            JoinType.RIGHT: self._execute_right_join,
            JoinType.OUTER: self._execute_outer_join,
            JoinType.CROSS: self._execute_cross_join,
            JoinType.ANTI: self._execute_anti_join
        }
    
    async def execute_plan(
        self,
        execution_plan: ExecutionPlan,
        progress_callback: Optional[Callable[[ExecutionProgress], None]] = None,
        chunk_size: Optional[int] = None
    ) -> pl.DataFrame:
        """执行连接计划
        
        Args:
            execution_plan: 执行计划
            progress_callback: 进度回调函数
            chunk_size: 分块大小，None表示不分块
            
        Returns:
            pl.DataFrame: 连接结果
        """
        
        execution_id = execution_plan.plan_id
        self._logger.info(f"Starting execution of plan {execution_id}")
        
        # 初始化执行状态
        progress = ExecutionProgress(
            step_index=0,
            total_steps=execution_plan.total_steps,
            current_step=None,
            rows_processed=0,
            estimated_remaining_time=execution_plan.resource_estimate.execution_time_s,
            status="running"
        )
        
        stats = ExecutionStats(
            execution_id=execution_id,
            start_time=time.time(),
            end_time=None,
            total_rows_processed=0,
            total_memory_used_mb=0,
            peak_memory_used_mb=0,
            steps_completed=0,
            steps_failed=0
        )
        
        self._active_executions[execution_id] = progress
        self._execution_stats[execution_id] = stats
        
        try:
            with memory_guard.memory_guard(
                f"execute_plan_{execution_id}", 
                int(execution_plan.resource_estimate.peak_memory_mb * 1024 * 1024)
            ):
                
                # 检查内存限制
                if execution_plan.resource_estimate.peak_memory_mb > self.memory_limit_mb:
                    if chunk_size is None:
                        self._logger.warning(f"Plan requires {execution_plan.resource_estimate.peak_memory_mb:.1f}MB, enabling chunking")
                        chunk_size = max(1000, int(self.memory_limit_mb * 1024 * 50))  # 估算合适的块大小
                
                # 执行连接步骤
                result_data = None
                
                for step_index, step in enumerate(execution_plan.steps):
                    # 更新进度
                    progress.step_index = step_index
                    progress.current_step = step
                    if progress_callback:
                        progress_callback(progress)
                    
                    self._logger.info(f"Executing step {step_index + 1}/{execution_plan.total_steps}: {step.join_type.value} join")
                    
                    step_start_time = time.time()
                    
                    try:
                        # 执行单个步骤
                        if step_index == 0:
                            # 第一个步骤：连接两个数据源
                            result_data = await self._execute_step(step, chunk_size)
                        else:
                            # 后续步骤：将结果与新数据源连接
                            result_data = await self._execute_step_with_result(step, result_data, chunk_size)
                        
                        # 更新统计信息
                        step_duration = time.time() - step_start_time
                        stats.steps_completed += 1
                        stats.total_rows_processed += len(result_data) if result_data is not None else 0
                        
                        # 更新内存统计
                        memory_stats = memory_guard.get_memory_stats()
                        stats.peak_memory_used_mb = max(
                            stats.peak_memory_used_mb,
                            memory_stats.rss_bytes / (1024 * 1024)
                        )
                        
                        self._logger.info(f"Step {step_index + 1} completed in {step_duration:.2f}s, result rows: {len(result_data) if result_data is not None else 0}")
                        
                    except Exception as e:
                        stats.steps_failed += 1
                        progress.status = "failed"
                        progress.error_message = str(e)
                        self._logger.error(f"Step {step_index + 1} failed: {e}")
                        raise
                
                # 执行完成
                progress.step_index = execution_plan.total_steps
                progress.status = "completed"
                stats.end_time = time.time()
                
                if progress_callback:
                    progress_callback(progress)
                
                self._logger.info(f"Plan {execution_id} completed successfully in {stats.duration:.2f}s")
                
                return result_data or pl.DataFrame()
        
        except Exception as e:
            progress.status = "failed"
            progress.error_message = str(e)
            stats.end_time = time.time()
            
            if progress_callback:
                progress_callback(progress)
            
            raise
        
        finally:
            # 清理活动执行记录
            if execution_id in self._active_executions:
                del self._active_executions[execution_id]
    
    async def _execute_step(
        self, 
        step: JoinStep, 
        chunk_size: Optional[int] = None
    ) -> pl.DataFrame:
        """执行单个连接步骤"""
        
        # 获取数据源连接器
        async with registry.acquire_source(step.left_source) as left_connector:
            async with registry.acquire_source(step.right_source) as right_connector:
                
                # 加载数据
                if chunk_size:
                    # 分块处理
                    return await self._execute_step_chunked(step, left_connector, right_connector, chunk_size)
                else:
                    # 直接处理
                    left_data = await left_connector.query()
                    right_data = await right_connector.query()
                    
                    # 执行连接操作
                    join_op = self._join_operations.get(step.join_type)
                    if not join_op:
                        raise ValueError(f"Unsupported join type: {step.join_type}")
                    
                    return await join_op(left_data, right_data, step.conditions)
    
    async def _execute_step_with_result(
        self, 
        step: JoinStep, 
        previous_result: pl.DataFrame, 
        chunk_size: Optional[int] = None
    ) -> pl.DataFrame:
        """执行步骤，将前一步结果作为左表"""
        
        # 获取右表数据源
        async with registry.acquire_source(step.right_source) as right_connector:
            if chunk_size:
                # 分块处理
                return await self._execute_step_with_result_chunked(
                    step, previous_result, right_connector, chunk_size
                )
            else:
                # 直接处理
                right_data = await right_connector.query()
                
                # 执行连接操作
                join_op = self._join_operations.get(step.join_type)
                if not join_op:
                    raise ValueError(f"Unsupported join type: {step.join_type}")
                
                return await join_op(previous_result, right_data, step.conditions)
    
    async def _execute_step_chunked(
        self,
        step: JoinStep,
        left_connector: DataSourceConnector,
        right_connector: DataSourceConnector,
        chunk_size: int
    ) -> pl.DataFrame:
        """分块执行连接步骤"""
        
        self._logger.info(f"Executing chunked join with chunk_size={chunk_size}")
        
        result_chunks = []
        
        # 获取右表数据（通常作为较小的表全部加载）
        right_data = await right_connector.query()
        
        # 分块处理左表
        async for left_chunk in left_connector.query_stream(
            options=QueryOptions(batch_size=chunk_size, streaming=True)
        ):
            if left_chunk.is_empty():
                continue
            
            # 执行连接操作
            join_op = self._join_operations.get(step.join_type)
            if not join_op:
                raise ValueError(f"Unsupported join type: {step.join_type}")
            
            chunk_result = await join_op(left_chunk, right_data, step.conditions)
            
            if not chunk_result.is_empty():
                result_chunks.append(chunk_result)
        
        # 合并所有块的结果
        if result_chunks:
            return pl.concat(result_chunks)
        else:
            return pl.DataFrame()
    
    async def _execute_step_with_result_chunked(
        self,
        step: JoinStep,
        previous_result: pl.DataFrame,
        right_connector: DataSourceConnector,
        chunk_size: int
    ) -> pl.DataFrame:
        """分块执行步骤，使用前一步结果"""
        
        result_chunks = []
        
        # 获取右表数据
        right_data = await right_connector.query()
        
        # 分块处理前一步结果
        total_rows = len(previous_result)
        
        for start_idx in range(0, total_rows, chunk_size):
            end_idx = min(start_idx + chunk_size, total_rows)
            left_chunk = previous_result.slice(start_idx, end_idx - start_idx)
            
            if left_chunk.is_empty():
                continue
            
            # 执行连接操作
            join_op = self._join_operations.get(step.join_type)
            if not join_op:
                raise ValueError(f"Unsupported join type: {step.join_type}")
            
            chunk_result = await join_op(left_chunk, right_data, step.conditions)
            
            if not chunk_result.is_empty():
                result_chunks.append(chunk_result)
        
        # 合并所有块的结果
        if result_chunks:
            return pl.concat(result_chunks)
        else:
            return pl.DataFrame()
    
    # 连接操作实现
    
    async def _execute_inner_join(
        self, 
        left_data: pl.DataFrame, 
        right_data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """执行内连接"""
        
        if len(conditions) == 0:
            raise ValueError("Inner join requires at least one condition")
        
        # 使用第一个条件作为主要连接条件
        primary_condition = conditions[0]
        
        try:
            # Polars内连接
            result = left_data.join(
                right_data,
                left_on=primary_condition.left_column,
                right_on=primary_condition.right_column,
                how="inner"
            )
            
            # 处理额外的连接条件（作为过滤器）
            if len(conditions) > 1:
                result = self._apply_additional_conditions(result, conditions[1:])
            
            return result
            
        except Exception as e:
            self._logger.error(f"Inner join failed: {e}")
            raise
    
    async def _execute_left_join(
        self, 
        left_data: pl.DataFrame, 
        right_data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """执行左连接"""
        
        if len(conditions) == 0:
            raise ValueError("Left join requires at least one condition")
        
        primary_condition = conditions[0]
        
        try:
            result = left_data.join(
                right_data,
                left_on=primary_condition.left_column,
                right_on=primary_condition.right_column,
                how="left"
            )
            
            if len(conditions) > 1:
                result = self._apply_additional_conditions(result, conditions[1:])
            
            return result
            
        except Exception as e:
            self._logger.error(f"Left join failed: {e}")
            raise
    
    async def _execute_right_join(
        self, 
        left_data: pl.DataFrame, 
        right_data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """执行右连接"""
        
        if len(conditions) == 0:
            raise ValueError("Right join requires at least one condition")
        
        # Polars没有直接的右连接，使用左连接交换表
        primary_condition = conditions[0]
        
        try:
            result = right_data.join(
                left_data,
                left_on=primary_condition.right_column,
                right_on=primary_condition.left_column,
                how="left"
            )
            
            # 调整列顺序以匹配预期（左表列在前，右表列在后）
            left_cols = left_data.columns
            right_cols = right_data.columns
            
            # 重新排列列顺序
            new_order = []
            for col in left_cols:
                if col in result.columns:
                    new_order.append(col)
            for col in right_cols:
                if col in result.columns and col not in new_order:
                    new_order.append(col)
            
            result = result.select(new_order)
            
            if len(conditions) > 1:
                result = self._apply_additional_conditions(result, conditions[1:])
            
            return result
            
        except Exception as e:
            self._logger.error(f"Right join failed: {e}")
            raise
    
    async def _execute_outer_join(
        self, 
        left_data: pl.DataFrame, 
        right_data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """执行全外连接"""
        
        if len(conditions) == 0:
            raise ValueError("Outer join requires at least one condition")
        
        primary_condition = conditions[0]
        
        try:
            result = left_data.join(
                right_data,
                left_on=primary_condition.left_column,
                right_on=primary_condition.right_column,
                how="full"
            )
            
            if len(conditions) > 1:
                result = self._apply_additional_conditions(result, conditions[1:])
            
            return result
            
        except Exception as e:
            self._logger.error(f"Outer join failed: {e}")
            raise
    
    async def _execute_cross_join(
        self, 
        left_data: pl.DataFrame, 
        right_data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """执行笛卡尔积连接"""
        
        try:
            # Polars笛卡尔积连接
            result = left_data.join(right_data, how="cross")
            
            # 应用连接条件作为过滤器
            if conditions:
                result = self._apply_additional_conditions(result, conditions)
            
            return result
            
        except Exception as e:
            self._logger.error(f"Cross join failed: {e}")
            raise
    
    async def _execute_anti_join(
        self, 
        left_data: pl.DataFrame, 
        right_data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """执行反连接"""
        
        if len(conditions) == 0:
            raise ValueError("Anti join requires at least one condition")
        
        primary_condition = conditions[0]
        
        try:
            result = left_data.join(
                right_data,
                left_on=primary_condition.left_column,
                right_on=primary_condition.right_column,
                how="anti"
            )
            
            if len(conditions) > 1:
                result = self._apply_additional_conditions(result, conditions[1:])
            
            return result
            
        except Exception as e:
            self._logger.error(f"Anti join failed: {e}")
            raise
    
    def _apply_additional_conditions(
        self, 
        data: pl.DataFrame, 
        conditions: List[JoinCondition]
    ) -> pl.DataFrame:
        """应用额外的连接条件作为过滤器"""
        
        result = data
        
        for condition in conditions:
            # 检查列是否存在
            if condition.left_column not in result.columns or condition.right_column not in result.columns:
                continue
            
            # 根据操作符创建过滤条件
            if condition.operator == "eq":
                filter_expr = pl.col(condition.left_column) == pl.col(condition.right_column)
            elif condition.operator == "ne":
                filter_expr = pl.col(condition.left_column) != pl.col(condition.right_column)
            elif condition.operator == "gt":
                filter_expr = pl.col(condition.left_column) > pl.col(condition.right_column)
            elif condition.operator == "ge":
                filter_expr = pl.col(condition.left_column) >= pl.col(condition.right_column)
            elif condition.operator == "lt":
                filter_expr = pl.col(condition.left_column) < pl.col(condition.right_column)
            elif condition.operator == "le":
                filter_expr = pl.col(condition.left_column) <= pl.col(condition.right_column)
            else:
                self._logger.warning(f"Unsupported operator: {condition.operator}")
                continue
            
            result = result.filter(filter_expr)
        
        return result
    
    # 监控和管理方法
    
    def get_active_executions(self) -> Dict[str, ExecutionProgress]:
        """获取活动执行状态"""
        return self._active_executions.copy()
    
    def get_execution_stats(self, execution_id: Optional[str] = None) -> Dict[str, ExecutionStats]:
        """获取执行统计"""
        if execution_id:
            return {execution_id: self._execution_stats.get(execution_id)}
        return self._execution_stats.copy()
    
    def cancel_execution(self, execution_id: str) -> bool:
        """取消执行（暂不实现，预留接口）"""
        if execution_id in self._active_executions:
            self._active_executions[execution_id].status = "cancelled"
            return True
        return False
    
    def clear_execution_history(self) -> None:
        """清理执行历史"""
        self._execution_stats.clear()
        self._logger.info("Execution history cleared")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self._execution_stats:
            return {"total_executions": 0}
        
        stats_list = list(self._execution_stats.values())
        
        total_executions = len(stats_list)
        successful_executions = len([s for s in stats_list if s.steps_failed == 0])
        total_rows = sum(s.total_rows_processed for s in stats_list)
        
        durations = [s.duration for s in stats_list if s.duration is not None]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        peak_memories = [s.peak_memory_used_mb for s in stats_list]
        avg_peak_memory = sum(peak_memories) / len(peak_memories) if peak_memories else 0
        
        return {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "success_rate": successful_executions / total_executions if total_executions > 0 else 0,
            "total_rows_processed": total_rows,
            "average_duration_s": avg_duration,
            "average_peak_memory_mb": avg_peak_memory
        }