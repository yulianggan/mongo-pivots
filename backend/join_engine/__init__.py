"""
JoinEngine - 连接引擎模块
提供统一的连接计划器、执行器和优化器API
"""
import polars as pl
from typing import Dict, List, Any, Optional, Callable, AsyncIterator
import asyncio
import logging
import time
from contextlib import asynccontextmanager

from connectors.base import DataSourceConnector
from connectors.registry import registry
from core.memory_guard import memory_guard

# 导入核心组件
from .planner import (
    JoinPlanner, 
    JoinType, 
    JoinCondition, 
    JoinStep, 
    ExecutionPlan, 
    ResourceEstimate,
    OptimizationHint
)
from .executor import (
    JoinExecutor, 
    ExecutionProgress, 
    ExecutionStats
)
from .optimizer import (
    JoinOptimizer, 
    IndexRecommendation, 
    QueryPushdown,
    PerformanceAnalyzer
)

# 导出主要类和函数
__all__ = [
    'JoinEngine',
    'JoinEngineFactory',
    'JoinType',
    'JoinCondition',
    'JoinStep',
    'ExecutionPlan',
    'ResourceEstimate',
    'OptimizationHint',
    'ExecutionProgress',
    'ExecutionStats',
    'IndexRecommendation',
    'QueryPushdown',
    'create_join_engine',
    'validate_join_request',
    'JoinEngineError',
    'JoinPlanningError',
    'JoinExecutionError'
]


# 异常类定义
class JoinEngineError(Exception):
    """连接引擎基础异常"""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        self.message = message
        self.context = context or {}
        super().__init__(message)


class JoinPlanningError(JoinEngineError):
    """连接计划错误"""
    pass


class JoinExecutionError(JoinEngineError):
    """连接执行错误"""
    pass


class JoinEngine:
    """连接引擎主类 - 提供统一的连接功能接口"""
    
    def __init__(
        self,
        optimization_level: int = 2,
        memory_limit_mb: Optional[float] = None,
        enable_caching: bool = True
    ):
        """初始化连接引擎
        
        Args:
            optimization_level: 优化级别 0-3
            memory_limit_mb: 内存限制（MB）
            enable_caching: 是否启用缓存
        """
        
        self._logger = logging.getLogger(self.__class__.__name__)
        self.optimization_level = optimization_level
        self.memory_limit_mb = memory_limit_mb or 2048
        self.enable_caching = enable_caching
        
        # 初始化核心组件
        self.planner = JoinPlanner()
        self.executor = JoinExecutor(memory_limit_mb)
        self.optimizer = JoinOptimizer()
        self.performance_analyzer = PerformanceAnalyzer()
        
        # 执行历史和缓存
        self._execution_history: List[Dict[str, Any]] = []
        self._performance_metrics: Dict[str, float] = {}
        
        self._logger.info(f"JoinEngine initialized with optimization_level={optimization_level}, memory_limit={memory_limit_mb}MB")
    
    async def plan_join(
        self,
        sources: Dict[str, str],  # {alias: source_id}
        join_specs: List[Dict[str, Any]]
    ) -> ExecutionPlan:
        """创建连接执行计划
        
        Args:
            sources: 数据源映射 {别名: 数据源ID}
            join_specs: 连接规格列表
        
        Returns:
            ExecutionPlan: 执行计划
        
        Raises:
            JoinPlanningError: 计划创建失败
        """
        
        try:
            self._logger.info(f"Planning join for {len(sources)} sources with {len(join_specs)} join specs")
            
            # 验证输入
            validation_errors = self._validate_join_request(sources, join_specs)
            if validation_errors:
                raise JoinPlanningError(f"Validation errors: {validation_errors}")
            
            # 获取数据源连接器
            source_connectors = {}
            for alias, source_id in sources.items():
                connector = registry.get_source(source_id)
                if not connector:
                    raise JoinPlanningError(f"Data source not found: {source_id}")
                source_connectors[alias] = connector
            
            # 创建执行计划
            plan = await self.planner.create_execution_plan(
                source_connectors, 
                join_specs, 
                self.optimization_level
            )
            
            # 如果优化级别 > 0，进行计划优化
            if self.optimization_level > 0:
                source_stats = await self.planner._collect_source_statistics(source_connectors)
                plan = await self.optimizer.optimize_execution_plan(
                    plan, 
                    source_stats, 
                    self.optimization_level
                )
            
            self._logger.info(f"Join plan created: {plan.plan_id}, steps: {plan.total_steps}")
            
            return plan
            
        except Exception as e:
            self._logger.error(f"Join planning failed: {e}")
            raise JoinPlanningError(str(e), {"sources": sources, "join_specs": join_specs})
    
    async def execute_join(
        self,
        plan: ExecutionPlan,
        progress_callback: Optional[Callable[[ExecutionProgress], None]] = None,
        chunk_size: Optional[int] = None
    ) -> pl.DataFrame:
        """执行连接计划
        
        Args:
            plan: 执行计划
            progress_callback: 进度回调函数
            chunk_size: 分块大小
        
        Returns:
            pl.DataFrame: 连接结果
        
        Raises:
            JoinExecutionError: 执行失败
        """
        
        try:
            self._logger.info(f"Executing join plan: {plan.plan_id}")
            
            start_time = time.time()
            
            # 执行连接
            result = await self.executor.execute_plan(plan, progress_callback, chunk_size)
            
            end_time = time.time()
            execution_duration = end_time - start_time
            
            # 记录执行历史
            execution_record = {
                "plan_id": plan.plan_id,
                "start_time": start_time,
                "end_time": end_time,
                "duration": execution_duration,
                "result_rows": len(result),
                "result_columns": len(result.columns),
                "memory_peak_mb": memory_guard.get_memory_stats().rss_bytes / (1024 * 1024),
                "optimization_level": self.optimization_level
            }
            
            self._execution_history.append(execution_record)
            
            # 更新性能指标
            self._update_performance_metrics(execution_record, plan)
            
            self._logger.info(f"Join execution completed: {len(result)} rows, {len(result.columns)} columns in {execution_duration:.2f}s")
            
            return result
            
        except Exception as e:
            self._logger.error(f"Join execution failed: {e}")
            raise JoinExecutionError(str(e), {"plan_id": plan.plan_id})
    
    async def plan_and_execute_join(
        self,
        sources: Dict[str, str],
        join_specs: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[ExecutionProgress], None]] = None,
        chunk_size: Optional[int] = None
    ) -> pl.DataFrame:
        """一步完成连接计划和执行
        
        Args:
            sources: 数据源映射
            join_specs: 连接规格列表
            progress_callback: 进度回调函数
            chunk_size: 分块大小
        
        Returns:
            pl.DataFrame: 连接结果
        """
        
        # 创建计划
        plan = await self.plan_join(sources, join_specs)
        
        # 执行计划
        return await self.execute_join(plan, progress_callback, chunk_size)
    
    async def get_join_recommendations(
        self,
        sources: Dict[str, str],
        join_specs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """获取连接优化建议
        
        Args:
            sources: 数据源映射
            join_specs: 连接规格列表
        
        Returns:
            Dict[str, Any]: 优化建议
        """
        
        try:
            # 创建基础计划
            plan = await self.plan_join(sources, join_specs)
            
            # 获取数据源统计信息
            source_connectors = {}
            for alias, source_id in sources.items():
                connector = registry.get_source(source_id)
                if connector:
                    source_connectors[alias] = connector
            
            source_stats = await self.planner._collect_source_statistics(source_connectors)
            
            # 生成索引建议
            index_recommendations = await self.optimizer._generate_index_recommendations(
                plan.steps, source_stats
            )
            
            # 生成查询下推建议
            pushdown_opportunities = await self.optimizer._identify_pushdown_opportunities(
                plan.steps, source_stats
            )
            
            recommendations = {
                "execution_plan": {
                    "plan_id": plan.plan_id,
                    "total_steps": plan.total_steps,
                    "estimated_time_s": plan.resource_estimate.execution_time_s,
                    "estimated_memory_mb": plan.resource_estimate.peak_memory_mb
                },
                "optimization_hints": [
                    {
                        "type": hint.type,
                        "message": hint.message,
                        "impact_level": hint.impact_level,
                        "estimated_improvement": hint.estimated_improvement
                    }
                    for hint in plan.optimization_hints
                ],
                "index_recommendations": [
                    {
                        "source_id": rec.source_id,
                        "column_name": rec.column_name,
                        "index_type": rec.index_type,
                        "priority": rec.priority,
                        "reason": rec.reason
                    }
                    for rec in index_recommendations
                ],
                "pushdown_opportunities": len(pushdown_opportunities),
                "performance_score": self._estimate_performance_score(plan)
            }
            
            return recommendations
            
        except Exception as e:
            self._logger.error(f"Failed to generate recommendations: {e}")
            return {"error": str(e)}
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        
        return {
            "total_executions": len(self._execution_history),
            "average_execution_time_s": self._performance_metrics.get("avg_execution_time", 0),
            "average_result_rows": self._performance_metrics.get("avg_result_rows", 0),
            "average_memory_usage_mb": self._performance_metrics.get("avg_memory_usage", 0),
            "success_rate": self._performance_metrics.get("success_rate", 1.0),
            "recent_executions": self._execution_history[-10:],  # 最近10次执行
            "engine_config": {
                "optimization_level": self.optimization_level,
                "memory_limit_mb": self.memory_limit_mb,
                "caching_enabled": self.enable_caching
            }
        }
    
    def get_executor_stats(self) -> Dict[str, Any]:
        """获取执行器统计信息"""
        return self.executor.get_performance_summary()
    
    def get_planner_cache_stats(self) -> Dict[str, Any]:
        """获取计划器缓存统计"""
        return self.planner.get_plan_cache_stats()
    
    def clear_caches(self) -> None:
        """清空所有缓存"""
        if self.enable_caching:
            self.planner.clear_plan_cache()
            self.executor.clear_execution_history()
            self._execution_history.clear()
            self._performance_metrics.clear()
            self._logger.info("All caches cleared")
    
    # 私有方法
    
    def _validate_join_request(
        self,
        sources: Dict[str, str],
        join_specs: List[Dict[str, Any]]
    ) -> List[str]:
        """验证连接请求"""
        
        errors = []
        
        # 验证数据源
        if not sources:
            errors.append("No sources specified")
        
        if len(sources) < 2:
            errors.append("At least 2 sources required for join")
        
        # 验证连接规格
        if not join_specs:
            errors.append("No join specifications provided")
        
        for i, spec in enumerate(join_specs):
            spec_errors = self.planner.validate_join_spec(spec)
            for error in spec_errors:
                errors.append(f"join_specs[{i}]: {error}")
            
            # 检查引用的数据源是否存在
            left_source = spec.get('left_source')
            right_source = spec.get('right_source')
            
            if left_source and left_source not in sources:
                errors.append(f"join_specs[{i}]: left_source '{left_source}' not in sources")
            
            if right_source and right_source not in sources:
                errors.append(f"join_specs[{i}]: right_source '{right_source}' not in sources")
        
        return errors
    
    def _update_performance_metrics(self, execution_record: Dict[str, Any], plan: ExecutionPlan) -> None:
        """更新性能指标"""
        
        # 计算平均执行时间
        durations = [record["duration"] for record in self._execution_history]
        self._performance_metrics["avg_execution_time"] = sum(durations) / len(durations)
        
        # 计算平均结果行数
        result_rows = [record["result_rows"] for record in self._execution_history]
        self._performance_metrics["avg_result_rows"] = sum(result_rows) / len(result_rows)
        
        # 计算平均内存使用
        memory_usage = [record["memory_peak_mb"] for record in self._execution_history]
        self._performance_metrics["avg_memory_usage"] = sum(memory_usage) / len(memory_usage)
        
        # 计算成功率（这里简化处理，实际需要记录失败次数）
        self._performance_metrics["success_rate"] = 1.0  # 简化处理
    
    def _estimate_performance_score(self, plan: ExecutionPlan) -> float:
        """估算性能评分"""
        
        score = 100.0
        
        # 基于资源预估调整评分
        if plan.resource_estimate.is_memory_intensive:
            score -= 20
        
        if plan.resource_estimate.is_time_intensive:
            score -= 30
        
        # 基于优化提示调整评分
        high_impact_hints = len([h for h in plan.optimization_hints if h.impact_level == "high"])
        score -= high_impact_hints * 15
        
        return max(0, score)


class JoinEngineFactory:
    """连接引擎工厂类"""
    
    @staticmethod
    def create_engine(
        optimization_level: int = 2,
        memory_limit_mb: Optional[float] = None,
        enable_caching: bool = True
    ) -> JoinEngine:
        """创建连接引擎实例"""
        
        return JoinEngine(
            optimization_level=optimization_level,
            memory_limit_mb=memory_limit_mb,
            enable_caching=enable_caching
        )
    
    @staticmethod
    def create_memory_optimized_engine(memory_limit_mb: float) -> JoinEngine:
        """创建内存优化的连接引擎"""
        
        return JoinEngine(
            optimization_level=3,  # 最高优化级别
            memory_limit_mb=memory_limit_mb,
            enable_caching=True
        )
    
    @staticmethod
    def create_performance_optimized_engine() -> JoinEngine:
        """创建性能优化的连接引擎"""
        
        return JoinEngine(
            optimization_level=3,
            memory_limit_mb=4096,  # 4GB内存限制
            enable_caching=True
        )


# 便捷函数
def create_join_engine(
    optimization_level: int = 2,
    memory_limit_mb: Optional[float] = None,
    enable_caching: bool = True
) -> JoinEngine:
    """创建连接引擎实例的便捷函数"""
    
    return JoinEngineFactory.create_engine(
        optimization_level=optimization_level,
        memory_limit_mb=memory_limit_mb,
        enable_caching=enable_caching
    )


def validate_join_request(
    sources: Dict[str, str],
    join_specs: List[Dict[str, Any]]
) -> List[str]:
    """验证连接请求的便捷函数"""
    
    # 创建临时连接引擎进行验证
    temp_engine = JoinEngine()
    return temp_engine._validate_join_request(sources, join_specs)


# 全局默认连接引擎实例
_default_engine: Optional[JoinEngine] = None


def get_default_engine() -> JoinEngine:
    """获取全局默认连接引擎"""
    
    global _default_engine
    
    if _default_engine is None:
        _default_engine = create_join_engine()
    
    return _default_engine


def set_default_engine(engine: JoinEngine) -> None:
    """设置全局默认连接引擎"""
    
    global _default_engine
    _default_engine = engine


# 异步上下文管理器
@asynccontextmanager
async def join_engine_context(
    optimization_level: int = 2,
    memory_limit_mb: Optional[float] = None
) -> AsyncIterator[JoinEngine]:
    """连接引擎异步上下文管理器"""
    
    engine = create_join_engine(
        optimization_level=optimization_level,
        memory_limit_mb=memory_limit_mb
    )
    
    try:
        yield engine
    finally:
        # 清理资源
        engine.clear_caches()


# 模块级别的便捷函数
async def execute_simple_join(
    left_source_id: str,
    right_source_id: str,
    left_column: str,
    right_column: str,
    join_type: str = "inner"
) -> pl.DataFrame:
    """执行简单连接的便捷函数"""
    
    engine = get_default_engine()
    
    sources = {
        "left": left_source_id,
        "right": right_source_id
    }
    
    join_specs = [{
        "left_source": "left",
        "right_source": "right",
        "join_type": join_type,
        "conditions": [{
            "left_column": left_column,
            "right_column": right_column,
            "operator": "eq"
        }]
    }]
    
    return await engine.plan_and_execute_join(sources, join_specs)


# 版本信息
__version__ = "1.0.0"