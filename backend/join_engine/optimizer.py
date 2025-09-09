"""
JoinOptimizer - 性能优化器
连接顺序优化、索引建议、查询重写和下推优化
"""
import polars as pl
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
import time
import logging
import math
from abc import ABC, abstractmethod

from connectors.base import DataSourceConnector
from core.memory_guard import memory_guard
from .planner import ExecutionPlan, JoinStep, JoinType, JoinCondition, OptimizationHint


@dataclass
class OptimizationRule:
    """优化规则"""
    rule_name: str
    description: str
    priority: int  # 0-10，数字越大优先级越高
    applicable_types: List[JoinType]
    
    def is_applicable(self, join_type: JoinType) -> bool:
        return join_type in self.applicable_types


@dataclass
class IndexRecommendation:
    """索引推荐"""
    source_id: str
    column_name: str
    index_type: str  # hash, btree, composite
    estimated_improvement: float  # 预估改善百分比
    priority: str  # high, medium, low
    reason: str


@dataclass
class QueryPushdown:
    """查询下推"""
    source_id: str
    filter_conditions: Dict[str, Any]
    projection_columns: List[str]
    estimated_reduction: float  # 数据量减少百分比


class JoinOptimizer:
    """连接优化器"""
    
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._optimization_rules = self._initialize_rules()
        self._cost_model = CostModel()
    
    def _initialize_rules(self) -> List[OptimizationRule]:
        """初始化优化规则"""
        return [
            OptimizationRule(
                rule_name="avoid_cross_join",
                description="避免笛卡尔积连接，转换为等值连接",
                priority=10,
                applicable_types=[JoinType.CROSS]
            ),
            OptimizationRule(
                rule_name="small_table_first",
                description="小表优先，减少中间结果大小",
                priority=8,
                applicable_types=list(JoinType)
            ),
            OptimizationRule(
                rule_name="selective_conditions_first",
                description="选择性高的条件优先执行",
                priority=7,
                applicable_types=list(JoinType)
            ),
            OptimizationRule(
                rule_name="index_based_join",
                description="优先使用索引列进行连接",
                priority=6,
                applicable_types=[JoinType.INNER, JoinType.LEFT, JoinType.RIGHT]
            ),
            OptimizationRule(
                rule_name="merge_consecutive_joins",
                description="合并连续的相同类型连接",
                priority=5,
                applicable_types=[JoinType.INNER, JoinType.LEFT]
            )
        ]
    
    async def optimize_execution_plan(
        self,
        plan: ExecutionPlan,
        source_stats: Dict[str, Dict[str, Any]],
        optimization_level: int = 2
    ) -> ExecutionPlan:
        """优化执行计划
        
        Args:
            plan: 原始执行计划
            source_stats: 数据源统计信息
            optimization_level: 优化级别 0-3
                0: 无优化
                1: 基础优化（连接顺序）
                2: 中级优化（连接顺序 + 索引建议）
                3: 高级优化（全部优化 + 查询下推）
        
        Returns:
            ExecutionPlan: 优化后的执行计划
        """
        
        if optimization_level == 0:
            return plan
        
        self._logger.info(f"Optimizing plan {plan.plan_id} at level {optimization_level}")
        
        with memory_guard.memory_guard("optimize_execution_plan"):
            
            optimized_steps = plan.steps.copy()
            optimization_hints = plan.optimization_hints.copy()
            
            # 级别1：基础优化
            if optimization_level >= 1:
                optimized_steps = await self._optimize_join_order(optimized_steps, source_stats)
                optimization_hints.extend(await self._generate_order_hints(optimized_steps, source_stats))
            
            # 级别2：中级优化
            if optimization_level >= 2:
                index_recommendations = await self._generate_index_recommendations(optimized_steps, source_stats)
                optimization_hints.extend(self._convert_index_recommendations_to_hints(index_recommendations))
                
                # 连接条件优化
                optimized_steps = await self._optimize_join_conditions(optimized_steps)
            
            # 级别3：高级优化
            if optimization_level >= 3:
                # 查询下推优化
                pushdown_opportunities = await self._identify_pushdown_opportunities(optimized_steps, source_stats)
                optimization_hints.extend(self._convert_pushdown_to_hints(pushdown_opportunities))
                
                # 连接类型优化
                optimized_steps = await self._optimize_join_types(optimized_steps, source_stats)
            
            # 重新计算资源预估
            from .planner import ResourceEstimator
            estimator = ResourceEstimator()
            
            total_memory = 0
            peak_memory = 0
            total_time = 0
            max_complexity = 0
            
            for step in optimized_steps:
                left_stats = source_stats.get(step.left_source, {})
                right_stats = source_stats.get(step.right_source, {})
                
                avg_mem, peak_mem = estimator.estimate_memory_usage(
                    left_stats.get('row_count', 1000),
                    right_stats.get('row_count', 1000),
                    left_stats.get('column_count', 10),
                    right_stats.get('column_count', 10),
                    step.join_type
                )
                
                exec_time = estimator.estimate_execution_time(
                    left_stats.get('row_count', 1000),
                    right_stats.get('row_count', 1000),
                    step.join_type,
                    left_stats.get('has_indexes', False)
                )
                
                complexity = estimator.estimate_cpu_complexity(
                    left_stats.get('row_count', 1000),
                    right_stats.get('row_count', 1000),
                    step.join_type
                )
                
                total_memory += avg_mem
                peak_memory = max(peak_memory, peak_mem)
                total_time += exec_time
                max_complexity = max(max_complexity, complexity)
            
            # 创建优化后的资源预估
            from .planner import ResourceEstimate
            optimized_estimate = ResourceEstimate(
                total_memory_mb=total_memory,
                peak_memory_mb=peak_memory * 0.9,  # 优化后减少10%
                execution_time_s=total_time * 0.85,  # 优化后减少15%
                temp_storage_mb=total_memory * 0.2,
                cpu_complexity_score=max_complexity
            )
            
            # 创建优化后的执行计划
            optimized_plan = ExecutionPlan(
                plan_id=f"{plan.plan_id}_opt{optimization_level}",
                steps=optimized_steps,
                resource_estimate=optimized_estimate,
                optimization_hints=optimization_hints,
                created_at=time.time()
            )
            
            self._logger.info(f"Plan optimization completed. Steps: {len(optimized_steps)}, Hints: {len(optimization_hints)}")
            
            return optimized_plan
    
    async def _optimize_join_order(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> List[JoinStep]:
        """优化连接顺序"""
        
        if len(steps) <= 1:
            return steps
        
        # 基于贪心算法的连接顺序优化
        optimized_steps = []
        remaining_steps = steps.copy()
        processed_sources = set()
        
        # 选择第一个步骤（选择涉及最小表的步骤）
        first_step = min(remaining_steps, key=lambda s: self._calculate_table_size(s, source_stats))
        optimized_steps.append(first_step)
        remaining_steps.remove(first_step)
        processed_sources.update([first_step.left_source, first_step.right_source])
        
        # 后续步骤优化
        while remaining_steps:
            # 找到与已处理表相关且代价最小的步骤
            candidate_steps = [
                step for step in remaining_steps
                if step.left_source in processed_sources or step.right_source in processed_sources
            ]
            
            if not candidate_steps:
                # 没有相关步骤，选择代价最小的
                candidate_steps = remaining_steps
            
            # 选择代价最小的步骤
            next_step = min(candidate_steps, key=lambda s: self._calculate_step_cost(s, source_stats))
            optimized_steps.append(next_step)
            remaining_steps.remove(next_step)
            processed_sources.update([next_step.left_source, next_step.right_source])
        
        return optimized_steps
    
    def _calculate_table_size(self, step: JoinStep, source_stats: Dict[str, Dict[str, Any]]) -> float:
        """计算表大小"""
        left_stats = source_stats.get(step.left_source, {})
        right_stats = source_stats.get(step.right_source, {})
        
        left_size = left_stats.get('row_count', 1000) * left_stats.get('column_count', 10)
        right_size = right_stats.get('row_count', 1000) * right_stats.get('column_count', 10)
        
        return left_size + right_size
    
    def _calculate_step_cost(self, step: JoinStep, source_stats: Dict[str, Dict[str, Any]]) -> float:
        """计算步骤代价"""
        return self._cost_model.calculate_join_cost(step, source_stats)
    
    async def _generate_order_hints(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> List[OptimizationHint]:
        """生成连接顺序优化建议"""
        
        hints = []
        
        # 检查大表连接
        for i, step in enumerate(steps):
            left_stats = source_stats.get(step.left_source, {})
            right_stats = source_stats.get(step.right_source, {})
            
            left_rows = left_stats.get('row_count', 1000)
            right_rows = right_stats.get('row_count', 1000)
            
            if left_rows > 1000000 and right_rows > 1000000:
                hints.append(OptimizationHint(
                    type="order",
                    message=f"步骤 {i+1} 涉及两个大表连接，建议检查连接条件的选择性",
                    impact_level="high",
                    estimated_improvement="减少50%执行时间"
                ))
        
        return hints
    
    async def _generate_index_recommendations(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> List[IndexRecommendation]:
        """生成索引推荐"""
        
        recommendations = []
        
        for step in steps:
            # 检查左表索引需求
            left_stats = source_stats.get(step.left_source, {})
            if not left_stats.get('has_indexes', False) and left_stats.get('row_count', 0) > 10000:
                for condition in step.conditions:
                    recommendations.append(IndexRecommendation(
                        source_id=step.left_source,
                        column_name=condition.left_column,
                        index_type="btree",
                        estimated_improvement=25.0,
                        priority="medium",
                        reason=f"连接列 {condition.left_column} 上的索引可以显著提高连接性能"
                    ))
            
            # 检查右表索引需求
            right_stats = source_stats.get(step.right_source, {})
            if not right_stats.get('has_indexes', False) and right_stats.get('row_count', 0) > 10000:
                for condition in step.conditions:
                    recommendations.append(IndexRecommendation(
                        source_id=step.right_source,
                        column_name=condition.right_column,
                        index_type="btree",
                        estimated_improvement=25.0,
                        priority="medium",
                        reason=f"连接列 {condition.right_column} 上的索引可以显著提高连接性能"
                    ))
        
        return recommendations
    
    def _convert_index_recommendations_to_hints(
        self, 
        recommendations: List[IndexRecommendation]
    ) -> List[OptimizationHint]:
        """将索引推荐转换为优化提示"""
        
        hints = []
        
        for rec in recommendations:
            hints.append(OptimizationHint(
                type="index",
                message=f"建议在数据源 {rec.source_id} 的列 {rec.column_name} 上创建 {rec.index_type} 索引",
                impact_level=rec.priority,
                estimated_improvement=f"减少 {rec.estimated_improvement:.0f}% 执行时间"
            ))
        
        return hints
    
    async def _optimize_join_conditions(self, steps: List[JoinStep]) -> List[JoinStep]:
        """优化连接条件"""
        
        optimized_steps = []
        
        for step in steps:
            # 对连接条件进行排序，选择性高的条件优先
            if len(step.conditions) > 1:
                # 简单的条件排序：等值条件优先，其他条件按字母顺序
                sorted_conditions = sorted(
                    step.conditions,
                    key=lambda c: (c.operator != "eq", c.left_column)
                )
                
                step.conditions = sorted_conditions
            
            optimized_steps.append(step)
        
        return optimized_steps
    
    async def _identify_pushdown_opportunities(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> List[QueryPushdown]:
        """识别查询下推机会"""
        
        pushdowns = []
        
        # 分析连接条件，识别可以下推的过滤条件
        for step in steps:
            for condition in step.conditions:
                # 如果连接条件是等值条件，可能可以下推
                if condition.operator == "eq":
                    # 检查是否是常量比较（实际实现中需要更复杂的分析）
                    # 这里简化处理
                    pass
        
        return pushdowns
    
    def _convert_pushdown_to_hints(self, pushdowns: List[QueryPushdown]) -> List[OptimizationHint]:
        """将查询下推转换为优化提示"""
        
        hints = []
        
        for pushdown in pushdowns:
            hints.append(OptimizationHint(
                type="pushdown",
                message=f"建议将过滤条件下推到数据源 {pushdown.source_id}",
                impact_level="medium",
                estimated_improvement=f"减少 {pushdown.estimated_reduction:.0f}% 数据传输"
            ))
        
        return hints
    
    async def _optimize_join_types(
        self, 
        steps: List[JoinStep], 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> List[JoinStep]:
        """优化连接类型"""
        
        optimized_steps = []
        
        for step in steps:
            optimized_step = step
            
            # 检查是否可以将外连接转换为内连接
            if step.join_type == JoinType.OUTER:
                # 简化处理：如果有非空约束，可以考虑转换
                # 实际实现需要更复杂的约束分析
                pass
            
            # 检查是否可以避免笛卡尔积
            elif step.join_type == JoinType.CROSS:
                if step.conditions:
                    # 有连接条件的交叉连接可以转换为内连接
                    optimized_step.join_type = JoinType.INNER
            
            optimized_steps.append(optimized_step)
        
        return optimized_steps
    
    def analyze_join_selectivity(
        self, 
        step: JoinStep, 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> float:
        """分析连接选择性"""
        
        left_stats = source_stats.get(step.left_source, {})
        right_stats = source_stats.get(step.right_source, {})
        
        left_rows = left_stats.get('row_count', 1000)
        right_rows = right_stats.get('row_count', 1000)
        
        # 简化的选择性估算
        if step.join_type == JoinType.CROSS:
            return 1.0  # 笛卡尔积选择性为100%
        
        # 基于表大小的选择性估算
        smaller_table = min(left_rows, right_rows)
        larger_table = max(left_rows, right_rows)
        
        # 假设较小表的每一行在较大表中平均匹配若干行
        estimated_selectivity = min(1.0, smaller_table / larger_table * 0.1)
        
        return estimated_selectivity
    
    def get_optimization_summary(self) -> Dict[str, Any]:
        """获取优化摘要"""
        
        return {
            "available_rules": [
                {
                    "name": rule.rule_name,
                    "description": rule.description,
                    "priority": rule.priority,
                    "applicable_types": [t.value for t in rule.applicable_types]
                }
                for rule in self._optimization_rules
            ],
            "cost_model": {
                "name": self._cost_model.__class__.__name__,
                "description": "基于行数和连接类型的代价模型"
            }
        }


class CostModel:
    """代价模型"""
    
    def __init__(self):
        # 连接类型的基础代价权重
        self.join_type_costs = {
            JoinType.INNER: 1.0,
            JoinType.LEFT: 1.2,
            JoinType.RIGHT: 1.2,
            JoinType.OUTER: 1.5,
            JoinType.CROSS: 3.0,
            JoinType.ANTI: 0.8
        }
    
    def calculate_join_cost(
        self, 
        step: JoinStep, 
        source_stats: Dict[str, Dict[str, Any]]
    ) -> float:
        """计算连接代价"""
        
        left_stats = source_stats.get(step.left_source, {})
        right_stats = source_stats.get(step.right_source, {})
        
        left_rows = left_stats.get('row_count', 1000)
        right_rows = right_stats.get('row_count', 1000)
        
        # 基础代价：基于行数
        base_cost = math.log10(left_rows + 1) * math.log10(right_rows + 1)
        
        # 连接类型权重
        type_weight = self.join_type_costs.get(step.join_type, 1.0)
        
        # 索引影响
        has_left_index = left_stats.get('has_indexes', False)
        has_right_index = right_stats.get('has_indexes', False)
        
        index_factor = 1.0
        if has_left_index and has_right_index:
            index_factor = 0.5  # 两边都有索引，代价减半
        elif has_left_index or has_right_index:
            index_factor = 0.7  # 一边有索引，代价减少30%
        
        # 连接条件复杂度
        condition_factor = 1.0 + 0.1 * (len(step.conditions) - 1)
        
        total_cost = base_cost * type_weight * index_factor * condition_factor
        
        return total_cost
    
    def estimate_result_size(
        self, 
        step: JoinStep, 
        source_stats: Dict[str, Dict[str, Any]],
        selectivity: float = 0.1
    ) -> int:
        """估算结果大小"""
        
        left_stats = source_stats.get(step.left_source, {})
        right_stats = source_stats.get(step.right_source, {})
        
        left_rows = left_stats.get('row_count', 1000)
        right_rows = right_stats.get('row_count', 1000)
        
        if step.join_type == JoinType.CROSS:
            return left_rows * right_rows
        elif step.join_type == JoinType.INNER:
            return int(min(left_rows, right_rows) * selectivity)
        elif step.join_type == JoinType.LEFT:
            return left_rows
        elif step.join_type == JoinType.RIGHT:
            return right_rows
        elif step.join_type == JoinType.OUTER:
            return left_rows + right_rows - int(min(left_rows, right_rows) * selectivity)
        elif step.join_type == JoinType.ANTI:
            return int(left_rows * (1 - selectivity))
        
        return max(left_rows, right_rows)


class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def analyze_execution_performance(
        self, 
        execution_stats: Dict[str, Any],
        plan: ExecutionPlan
    ) -> Dict[str, Any]:
        """分析执行性能"""
        
        analysis = {
            "performance_score": self._calculate_performance_score(execution_stats, plan),
            "bottlenecks": self._identify_bottlenecks(execution_stats, plan),
            "recommendations": self._generate_performance_recommendations(execution_stats, plan)
        }
        
        return analysis
    
    def _calculate_performance_score(
        self, 
        execution_stats: Dict[str, Any], 
        plan: ExecutionPlan
    ) -> float:
        """计算性能评分（0-100）"""
        
        # 时间性能评分
        actual_time = execution_stats.get("duration", 0)
        estimated_time = plan.resource_estimate.execution_time_s
        
        if estimated_time > 0:
            time_score = max(0, 100 - (actual_time - estimated_time) / estimated_time * 100)
        else:
            time_score = 50  # 默认评分
        
        # 内存性能评分
        actual_memory = execution_stats.get("peak_memory_used_mb", 0)
        estimated_memory = plan.resource_estimate.peak_memory_mb
        
        if estimated_memory > 0:
            memory_score = max(0, 100 - (actual_memory - estimated_memory) / estimated_memory * 100)
        else:
            memory_score = 50
        
        # 综合评分
        overall_score = (time_score + memory_score) / 2
        
        return overall_score
    
    def _identify_bottlenecks(
        self, 
        execution_stats: Dict[str, Any], 
        plan: ExecutionPlan
    ) -> List[str]:
        """识别性能瓶颈"""
        
        bottlenecks = []
        
        # 检查内存瓶颈
        if execution_stats.get("peak_memory_used_mb", 0) > 1024:
            bottlenecks.append("high_memory_usage")
        
        # 检查时间瓶颈
        if execution_stats.get("duration", 0) > 300:
            bottlenecks.append("long_execution_time")
        
        # 检查失败步骤
        if execution_stats.get("steps_failed", 0) > 0:
            bottlenecks.append("failed_steps")
        
        return bottlenecks
    
    def _generate_performance_recommendations(
        self, 
        execution_stats: Dict[str, Any], 
        plan: ExecutionPlan
    ) -> List[str]:
        """生成性能改进建议"""
        
        recommendations = []
        
        # 基于瓶颈生成建议
        bottlenecks = self._identify_bottlenecks(execution_stats, plan)
        
        if "high_memory_usage" in bottlenecks:
            recommendations.append("考虑启用数据分块处理以减少内存使用")
        
        if "long_execution_time" in bottlenecks:
            recommendations.append("检查连接条件和索引，考虑提高优化级别")
        
        if "failed_steps" in bottlenecks:
            recommendations.append("检查数据质量和连接条件的有效性")
        
        # 基于连接类型生成建议
        for step in plan.steps:
            if step.join_type == JoinType.CROSS:
                recommendations.append(f"步骤中的笛卡尔积连接可能导致性能问题，建议检查连接条件")
        
        return recommendations