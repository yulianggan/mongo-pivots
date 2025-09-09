"""
JoinPlanner - 连接计划器
生成优化的连接执行计划，支持6种连接类型和资源预估
"""
import polars as pl
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import time
import logging
import hashlib
from abc import ABC, abstractmethod

from connectors.base import DataSourceConnector
from core.data_engine import data_engine
from core.memory_guard import memory_guard


class JoinType(Enum):
    """连接类型"""
    INNER = "inner"          # 内连接，仅保留匹配记录
    LEFT = "left"            # 左连接，保留左表所有记录
    RIGHT = "right"          # 右连接，保留右表所有记录
    OUTER = "outer"          # 全外连接，保留所有表记录
    CROSS = "cross"          # 笛卡尔积连接
    ANTI = "anti"            # 反连接，保留不匹配记录


@dataclass
class JoinCondition:
    """连接条件"""
    left_column: str
    right_column: str
    operator: str = "eq"     # 默认等值连接
    
    def __str__(self) -> str:
        op_symbol = {"eq": "=", "ne": "!=", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
        return f"{self.left_column} {op_symbol.get(self.operator, '=')} {self.right_column}"


@dataclass
class JoinStep:
    """连接步骤"""
    step_id: str
    left_source: str         # 左表数据源ID
    right_source: str        # 右表数据源ID
    join_type: JoinType
    conditions: List[JoinCondition]
    estimated_rows: Optional[int] = None
    estimated_memory_mb: Optional[float] = None
    execution_time_estimate_s: Optional[float] = None


@dataclass
class ResourceEstimate:
    """资源消耗预估"""
    total_memory_mb: float
    peak_memory_mb: float
    execution_time_s: float
    temp_storage_mb: float
    cpu_complexity_score: int    # 1-10，越高越复杂
    
    @property
    def is_memory_intensive(self) -> bool:
        """是否内存密集型操作"""
        return self.peak_memory_mb > 1024  # 1GB
    
    @property
    def is_time_intensive(self) -> bool:
        """是否时间密集型操作"""
        return self.execution_time_s > 300  # 5分钟


@dataclass
class OptimizationHint:
    """优化建议"""
    type: str                # index, memory, order等
    message: str
    impact_level: str        # low, medium, high
    estimated_improvement: Optional[str] = None


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    steps: List[JoinStep]
    resource_estimate: ResourceEstimate
    optimization_hints: List[OptimizationHint]
    created_at: float = field(default_factory=time.time)
    
    @property
    def total_steps(self) -> int:
        return len(self.steps)
    
    @property
    def involves_sources(self) -> Set[str]:
        """涉及的数据源ID集合"""
        sources = set()
        for step in self.steps:
            sources.add(step.left_source)
            sources.add(step.right_source)
        return sources


class ResourceEstimator:
    """资源预估器"""
    
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # 基于行数的内存估算系数
        self.row_memory_factor = 100  # bytes per row
        self.join_memory_multiplier = {
            JoinType.INNER: 1.2,
            JoinType.LEFT: 1.4,
            JoinType.RIGHT: 1.4,
            JoinType.OUTER: 1.8,
            JoinType.CROSS: 3.0,
            JoinType.ANTI: 1.1
        }
    
    def estimate_join_rows(
        self, 
        left_rows: int, 
        right_rows: int, 
        join_type: JoinType,
        selectivity: float = 0.1
    ) -> int:
        """估算连接结果行数"""
        
        if join_type == JoinType.CROSS:
            return left_rows * right_rows
        elif join_type == JoinType.LEFT:
            return left_rows
        elif join_type == JoinType.RIGHT:
            return right_rows
        elif join_type == JoinType.OUTER:
            # 估算为两表行数之和减去重复部分
            return left_rows + right_rows - int(min(left_rows, right_rows) * selectivity)
        elif join_type == JoinType.INNER:
            return int(min(left_rows, right_rows) * selectivity)
        elif join_type == JoinType.ANTI:
            return int(left_rows * (1 - selectivity))
        
        return max(left_rows, right_rows)
    
    def estimate_memory_usage(
        self, 
        left_rows: int, 
        right_rows: int,
        left_cols: int,
        right_cols: int,
        join_type: JoinType
    ) -> Tuple[float, float]:  # (avg_memory_mb, peak_memory_mb)
        """估算内存使用量"""
        
        # 基础内存计算
        left_memory = left_rows * left_cols * self.row_memory_factor
        right_memory = right_rows * right_cols * self.row_memory_factor
        
        # 连接类型影响
        multiplier = self.join_memory_multiplier.get(join_type, 1.5)
        
        # 结果集内存
        result_rows = self.estimate_join_rows(left_rows, right_rows, join_type)
        result_memory = result_rows * (left_cols + right_cols) * self.row_memory_factor
        
        # 平均内存：输入数据 + 结果数据的一部分
        avg_memory_mb = (left_memory + right_memory + result_memory * 0.5) / (1024 * 1024)
        
        # 峰值内存：所有数据同时存在时
        peak_memory_mb = (left_memory + right_memory + result_memory) * multiplier / (1024 * 1024)
        
        return avg_memory_mb, peak_memory_mb
    
    def estimate_execution_time(
        self, 
        left_rows: int, 
        right_rows: int, 
        join_type: JoinType,
        has_index: bool = False
    ) -> float:
        """估算执行时间（秒）"""
        
        # 基础复杂度计算
        if join_type == JoinType.CROSS:
            complexity = left_rows * right_rows
        else:
            # 其他连接类型通常是O(n+m)或O(n*log(m))
            if has_index:
                complexity = left_rows + right_rows * 2  # 有索引时更快
            else:
                complexity = left_rows * right_rows / 100  # 近似hash join复杂度
        
        # 基于复杂度和系统性能估算时间
        # 假设每秒处理100万条记录的复杂度
        base_throughput = 1000000
        estimated_seconds = complexity / base_throughput
        
        # 连接类型修正
        type_multiplier = {
            JoinType.INNER: 1.0,
            JoinType.LEFT: 1.2,
            JoinType.RIGHT: 1.2,
            JoinType.OUTER: 1.5,
            JoinType.CROSS: 2.0,
            JoinType.ANTI: 0.8
        }
        
        return estimated_seconds * type_multiplier.get(join_type, 1.0)
    
    def estimate_cpu_complexity(
        self, 
        left_rows: int, 
        right_rows: int, 
        join_type: JoinType
    ) -> int:
        """估算CPU复杂度评分（1-10）"""
        
        total_rows = left_rows + right_rows
        
        # 基于数据量的基础复杂度
        if total_rows < 10000:
            base_score = 1
        elif total_rows < 100000:
            base_score = 3
        elif total_rows < 1000000:
            base_score = 5
        elif total_rows < 10000000:
            base_score = 7
        else:
            base_score = 9
        
        # 连接类型修正
        type_modifier = {
            JoinType.INNER: 0,
            JoinType.LEFT: 1,
            JoinType.RIGHT: 1,
            JoinType.OUTER: 2,
            JoinType.CROSS: 3,
            JoinType.ANTI: 0
        }
        
        final_score = min(10, base_score + type_modifier.get(join_type, 1))
        return final_score


class JoinPlanner:
    """连接计划器"""
    
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.resource_estimator = ResourceEstimator()
        self._plan_cache: Dict[str, ExecutionPlan] = {}
    
    async def create_execution_plan(
        self,
        sources: Dict[str, DataSourceConnector],
        join_specs: List[Dict[str, Any]],
        optimization_level: int = 1
    ) -> ExecutionPlan:
        """创建执行计划
        
        Args:
            sources: 数据源连接器字典 {source_id: connector}
            join_specs: 连接规格列表，每个元素包含:
                - left_source: 左表数据源ID
                - right_source: 右表数据源ID
                - join_type: 连接类型
                - conditions: 连接条件列表
            optimization_level: 优化级别 0-3
        
        Returns:
            ExecutionPlan: 执行计划
        """
        
        # 生成计划ID
        plan_hash = self._generate_plan_hash(sources, join_specs)
        
        # 检查缓存
        if plan_hash in self._plan_cache:
            self._logger.info(f"Using cached execution plan: {plan_hash}")
            return self._plan_cache[plan_hash]
        
        with memory_guard.memory_guard("create_execution_plan"):
            
            # 收集数据源信息
            source_stats = await self._collect_source_statistics(sources)
            
            # 生成初始连接步骤
            steps = await self._generate_join_steps(join_specs, source_stats)
            
            # 根据优化级别进行优化
            if optimization_level > 0:
                steps = await self._optimize_join_order(steps, source_stats, optimization_level)
            
            # 计算资源预估
            resource_estimate = await self._calculate_resource_estimate(steps, source_stats)
            
            # 生成优化建议
            optimization_hints = await self._generate_optimization_hints(steps, source_stats, resource_estimate)
            
            # 创建执行计划
            execution_plan = ExecutionPlan(
                plan_id=plan_hash,
                steps=steps,
                resource_estimate=resource_estimate,
                optimization_hints=optimization_hints
            )
            
            # 缓存计划
            self._plan_cache[plan_hash] = execution_plan
            
            self._logger.info(f"Created execution plan {plan_hash} with {len(steps)} steps")
            
            return execution_plan
    
    async def _collect_source_statistics(
        self, 
        sources: Dict[str, DataSourceConnector]
    ) -> Dict[str, Dict[str, Any]]:
        """收集数据源统计信息"""
        
        stats = {}
        
        for source_id, connector in sources.items():
            try:
                # 获取基本信息
                info = await connector.get_info()
                
                # 获取schema信息
                schema = await connector.get_schema_with_inference(sample_size=100)
                
                stats[source_id] = {
                    'row_count': info.row_count or 1000,  # 默认估值
                    'column_count': info.column_count or len(schema.get('columns', {})),
                    'schema': schema,
                    'has_indexes': self._detect_indexes(schema),
                    'estimated_size_mb': (info.row_count or 1000) * (info.column_count or 10) * 100 / (1024 * 1024)
                }
                
            except Exception as e:
                self._logger.warning(f"Failed to collect stats for {source_id}: {e}")
                # 使用默认统计信息
                stats[source_id] = {
                    'row_count': 1000,
                    'column_count': 10,
                    'schema': {},
                    'has_indexes': False,
                    'estimated_size_mb': 1.0
                }
        
        return stats
    
    def _detect_indexes(self, schema: Dict[str, Any]) -> bool:
        """检测是否有可用索引"""
        # 简单的索引检测逻辑
        columns = schema.get('columns', {})
        
        # 检查是否有_id字段（MongoDB通常有索引）
        if '_id' in columns:
            return True
        
        # 检查是否有标记为索引的字段
        for col_info in columns.values():
            if isinstance(col_info, dict) and col_info.get('indexed', False):
                return True
        
        return False
    
    async def _generate_join_steps(
        self, 
        join_specs: List[Dict[str, Any]], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> List[JoinStep]:
        """生成连接步骤"""
        
        steps = []
        
        for i, spec in enumerate(join_specs):
            # 解析连接规格
            left_source = spec['left_source']
            right_source = spec['right_source']
            join_type = JoinType(spec['join_type'])
            
            # 解析连接条件
            conditions = []
            for condition_spec in spec.get('conditions', []):
                condition = JoinCondition(
                    left_column=condition_spec['left_column'],
                    right_column=condition_spec['right_column'],
                    operator=condition_spec.get('operator', 'eq')
                )
                conditions.append(condition)
            
            # 获取数据源统计信息
            left_stats = source_stats.get(left_source, {})
            right_stats = source_stats.get(right_source, {})
            
            # 预估结果
            estimated_rows = self.resource_estimator.estimate_join_rows(
                left_stats.get('row_count', 1000),
                right_stats.get('row_count', 1000),
                join_type
            )
            
            avg_mem, peak_mem = self.resource_estimator.estimate_memory_usage(
                left_stats.get('row_count', 1000),
                right_stats.get('row_count', 1000),
                left_stats.get('column_count', 10),
                right_stats.get('column_count', 10),
                join_type
            )
            
            execution_time = self.resource_estimator.estimate_execution_time(
                left_stats.get('row_count', 1000),
                right_stats.get('row_count', 1000),
                join_type,
                left_stats.get('has_indexes', False) or right_stats.get('has_indexes', False)
            )
            
            # 创建连接步骤
            step = JoinStep(
                step_id=f"step_{i+1}",
                left_source=left_source,
                right_source=right_source,
                join_type=join_type,
                conditions=conditions,
                estimated_rows=estimated_rows,
                estimated_memory_mb=avg_mem,
                execution_time_estimate_s=execution_time
            )
            
            steps.append(step)
        
        return steps
    
    async def _optimize_join_order(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]],
        optimization_level: int
    ) -> List[JoinStep]:
        """优化连接顺序"""
        
        if optimization_level < 2 or len(steps) <= 1:
            return steps
        
        # 基于代价的连接顺序优化
        optimized_steps = []
        remaining_steps = steps.copy()
        
        while remaining_steps:
            # 找到当前代价最小的步骤
            best_step = min(remaining_steps, key=lambda s: self._calculate_step_cost(s, source_stats))
            optimized_steps.append(best_step)
            remaining_steps.remove(best_step)
        
        return optimized_steps
    
    def _calculate_step_cost(self, step: JoinStep, source_stats: Dict[str, Dict[str, Any]]) -> float:
        """计算步骤代价"""
        
        left_stats = source_stats.get(step.left_source, {})
        right_stats = source_stats.get(step.right_source, {})
        
        # 基于行数、内存使用和执行时间的综合代价
        row_cost = (left_stats.get('row_count', 1000) + right_stats.get('row_count', 1000)) / 1000
        memory_cost = (step.estimated_memory_mb or 100) / 100
        time_cost = (step.execution_time_estimate_s or 10) / 10
        
        # 连接类型权重
        type_weight = {
            JoinType.INNER: 1.0,
            JoinType.LEFT: 1.2,
            JoinType.RIGHT: 1.2,
            JoinType.OUTER: 1.5,
            JoinType.CROSS: 3.0,
            JoinType.ANTI: 0.8
        }
        
        total_cost = (row_cost + memory_cost + time_cost) * type_weight.get(step.join_type, 1.0)
        
        return total_cost
    
    async def _calculate_resource_estimate(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> ResourceEstimate:
        """计算总资源预估"""
        
        total_memory = sum(step.estimated_memory_mb or 0 for step in steps)
        peak_memory = max(step.estimated_memory_mb or 0 for step in steps) * 1.5  # 峰值内存估算
        total_time = sum(step.execution_time_estimate_s or 0 for step in steps)
        
        # 临时存储估算（中间结果）
        temp_storage = total_memory * 0.3
        
        # CPU复杂度评分
        max_complexity = 0
        for step in steps:
            left_stats = source_stats.get(step.left_source, {})
            right_stats = source_stats.get(step.right_source, {})
            
            complexity = self.resource_estimator.estimate_cpu_complexity(
                left_stats.get('row_count', 1000),
                right_stats.get('row_count', 1000),
                step.join_type
            )
            max_complexity = max(max_complexity, complexity)
        
        return ResourceEstimate(
            total_memory_mb=total_memory,
            peak_memory_mb=peak_memory,
            execution_time_s=total_time,
            temp_storage_mb=temp_storage,
            cpu_complexity_score=max_complexity
        )
    
    async def _generate_optimization_hints(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]],
        resource_estimate: ResourceEstimate
    ) -> List[OptimizationHint]:
        """生成优化建议"""
        
        hints = []
        
        # 内存优化建议
        if resource_estimate.is_memory_intensive:
            hints.append(OptimizationHint(
                type="memory",
                message="连接操作需要大量内存，建议启用分块处理或增加可用内存",
                impact_level="high",
                estimated_improvement="减少50%内存使用"
            ))
        
        # 时间优化建议
        if resource_estimate.is_time_intensive:
            hints.append(OptimizationHint(
                type="time",
                message="连接操作预计耗时较长，建议检查连接条件和索引",
                impact_level="high",
                estimated_improvement="减少30%执行时间"
            ))
        
        # 索引建议
        for step in steps:
            left_stats = source_stats.get(step.left_source, {})
            right_stats = source_stats.get(step.right_source, {})
            
            if not left_stats.get('has_indexes') and left_stats.get('row_count', 0) > 10000:
                hints.append(OptimizationHint(
                    type="index",
                    message=f"数据源 {step.left_source} 缺少索引，建议在连接列上创建索引",
                    impact_level="medium",
                    estimated_improvement="减少20%执行时间"
                ))
            
            if not right_stats.get('has_indexes') and right_stats.get('row_count', 0) > 10000:
                hints.append(OptimizationHint(
                    type="index",
                    message=f"数据源 {step.right_source} 缺少索引，建议在连接列上创建索引",
                    impact_level="medium",
                    estimated_improvement="减少20%执行时间"
                ))
        
        # 连接顺序建议
        cross_joins = [s for s in steps if s.join_type == JoinType.CROSS]
        if cross_joins:
            hints.append(OptimizationHint(
                type="order",
                message="检测到笛卡尔积连接，建议检查连接条件或调整连接顺序",
                impact_level="high",
                estimated_improvement="减少90%执行时间"
            ))
        
        return hints
    
    def _generate_plan_hash(
        self, 
        sources: Dict[str, DataSourceConnector], 
        join_specs: List[Dict[str, Any]]
    ) -> str:
        """生成计划哈希值"""
        
        # 创建计划的唯一标识
        plan_data = {
            'sources': sorted(sources.keys()),
            'join_specs': join_specs
        }
        
        plan_str = str(plan_data)
        return hashlib.md5(plan_str.encode()).hexdigest()[:16]
    
    def get_plan_cache_stats(self) -> Dict[str, Any]:
        """获取计划缓存统计"""
        return {
            'cached_plans': len(self._plan_cache),
            'cache_keys': list(self._plan_cache.keys())
        }
    
    def clear_plan_cache(self) -> None:
        """清空计划缓存"""
        self._plan_cache.clear()
        self._logger.info("Execution plan cache cleared")
    
    def validate_join_spec(self, join_spec: Dict[str, Any]) -> List[str]:
        """验证连接规格"""
        errors = []
        
        # 必需字段检查
        required_fields = ['left_source', 'right_source', 'join_type', 'conditions']
        for field in required_fields:
            if field not in join_spec:
                errors.append(f"Missing required field: {field}")
        
        # 连接类型检查
        if 'join_type' in join_spec:
            try:
                JoinType(join_spec['join_type'])
            except ValueError:
                valid_types = [t.value for t in JoinType]
                errors.append(f"Invalid join_type. Must be one of: {valid_types}")
        
        # 连接条件检查
        if 'conditions' in join_spec:
            conditions = join_spec['conditions']
            if not isinstance(conditions, list) or len(conditions) == 0:
                errors.append("conditions must be a non-empty list")
            else:
                for i, condition in enumerate(conditions):
                    if not isinstance(condition, dict):
                        errors.append(f"conditions[{i}] must be a dict")
                    else:
                        req_fields = ['left_column', 'right_column']
                        for field in req_fields:
                            if field not in condition:
                                errors.append(f"conditions[{i}] missing field: {field}")
        
        return errors