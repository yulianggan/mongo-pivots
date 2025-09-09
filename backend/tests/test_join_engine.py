"""
测试连接引擎核心功能
"""
import pytest
import polars as pl
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# 导入被测试的模块
from join_engine import (
    JoinEngine, 
    JoinType, 
    JoinCondition, 
    create_join_engine,
    validate_join_request,
    JoinPlanningError,
    JoinExecutionError
)
from join_engine.planner import JoinPlanner, ExecutionPlan, ResourceEstimate, OptimizationHint
from join_engine.executor import JoinExecutor
from join_engine.optimizer import JoinOptimizer
from connectors.base import DataSourceConnector, DataSourceInfo, DataSourceType


class TestJoinEngine:
    """测试JoinEngine主类"""
    
    def setup_method(self):
        """测试前置设置"""
        self.engine = create_join_engine(optimization_level=1, memory_limit_mb=1024)
    
    def test_join_engine_initialization(self):
        """测试连接引擎初始化"""
        assert self.engine.optimization_level == 1
        assert self.engine.memory_limit_mb == 1024
        assert self.engine.enable_caching == True
        assert isinstance(self.engine.planner, JoinPlanner)
        assert isinstance(self.engine.executor, JoinExecutor)
        assert isinstance(self.engine.optimizer, JoinOptimizer)
    
    def test_validate_join_request_valid(self):
        """测试有效连接请求验证"""
        sources = {"left": "source1", "right": "source2"}
        join_specs = [{
            "left_source": "left",
            "right_source": "right", 
            "join_type": "inner",
            "conditions": [{"left_column": "id", "right_column": "id"}]
        }]
        
        errors = validate_join_request(sources, join_specs)
        assert len(errors) == 0
    
    def test_validate_join_request_invalid(self):
        """测试无效连接请求验证"""
        # 缺少数据源
        errors = validate_join_request({}, [])
        assert "No sources specified" in errors
        
        # 只有一个数据源
        errors = validate_join_request({"left": "source1"}, [])
        assert "At least 2 sources required for join" in errors
        
        # 缺少连接规格
        errors = validate_join_request({"left": "source1", "right": "source2"}, [])
        assert "No join specifications provided" in errors
    
    @pytest.mark.asyncio
    async def test_plan_join_invalid_sources(self):
        """测试计划连接时数据源无效"""
        sources = {"left": "invalid_source", "right": "another_invalid"}
        join_specs = [{
            "left_source": "left",
            "right_source": "right",
            "join_type": "inner", 
            "conditions": [{"left_column": "id", "right_column": "id"}]
        }]
        
        with pytest.raises(JoinPlanningError):
            await self.engine.plan_join(sources, join_specs)
    
    def test_get_performance_metrics(self):
        """测试获取性能指标"""
        metrics = self.engine.get_performance_metrics()
        
        assert "total_executions" in metrics
        assert "average_execution_time_s" in metrics
        assert "engine_config" in metrics
        assert metrics["engine_config"]["optimization_level"] == 1
    
    def test_clear_caches(self):
        """测试清空缓存"""
        # 添加一些执行历史
        self.engine._execution_history.append({"test": "data"})
        
        self.engine.clear_caches()
        
        assert len(self.engine._execution_history) == 0


class TestJoinPlanner:
    """测试JoinPlanner连接计划器"""
    
    def setup_method(self):
        """测试前置设置"""
        self.planner = JoinPlanner()
    
    def test_join_planner_initialization(self):
        """测试计划器初始化"""
        assert isinstance(self.planner.resource_estimator, type(self.planner.resource_estimator))
        assert len(self.planner._plan_cache) == 0
    
    def test_validate_join_spec_valid(self):
        """测试有效连接规格验证"""
        join_spec = {
            "left_source": "left",
            "right_source": "right",
            "join_type": "inner",
            "conditions": [{"left_column": "id", "right_column": "id"}]
        }
        
        errors = self.planner.validate_join_spec(join_spec)
        assert len(errors) == 0
    
    def test_validate_join_spec_invalid(self):
        """测试无效连接规格验证"""
        # 缺少必需字段
        join_spec = {"join_type": "inner"}
        errors = self.planner.validate_join_spec(join_spec)
        
        assert any("Missing required field" in error for error in errors)
        
        # 无效连接类型
        join_spec = {
            "left_source": "left",
            "right_source": "right", 
            "join_type": "invalid_type",
            "conditions": []
        }
        errors = self.planner.validate_join_spec(join_spec)
        
        assert any("Invalid join_type" in error for error in errors)
    
    def test_generate_plan_hash(self):
        """测试计划哈希生成"""
        sources = {"left": Mock(), "right": Mock()}
        join_specs = [{"test": "spec"}]
        
        hash1 = self.planner._generate_plan_hash(sources, join_specs)
        hash2 = self.planner._generate_plan_hash(sources, join_specs)
        
        assert hash1 == hash2
        assert len(hash1) == 16
    
    @pytest.mark.asyncio 
    async def test_collect_source_statistics_mock(self):
        """测试收集数据源统计信息（使用mock）"""
        # 创建mock连接器
        mock_connector = AsyncMock(spec=DataSourceConnector)
        mock_connector.get_info.return_value = DataSourceInfo(
            source_id="test_source",
            source_type=DataSourceType.CSV,
            connection_params={},
            row_count=1000,
            column_count=5
        )
        mock_connector.get_schema_with_inference.return_value = {
            "columns": {"id": {}, "name": {}, "value": {}, "date": {}, "flag": {}}
        }
        
        sources = {"test": mock_connector}
        
        stats = await self.planner._collect_source_statistics(sources)
        
        assert "test" in stats
        assert stats["test"]["row_count"] == 1000
        assert stats["test"]["column_count"] == 5
    
    def test_get_plan_cache_stats(self):
        """测试获取计划缓存统计"""
        stats = self.planner.get_plan_cache_stats()
        
        assert "cached_plans" in stats
        assert "cache_keys" in stats
        assert stats["cached_plans"] == 0
    
    def test_clear_plan_cache(self):
        """测试清空计划缓存"""
        # 添加缓存项
        self.planner._plan_cache["test"] = Mock()
        
        self.planner.clear_plan_cache()
        
        assert len(self.planner._plan_cache) == 0


class TestJoinCondition:
    """测试JoinCondition类"""
    
    def test_join_condition_creation(self):
        """测试连接条件创建"""
        condition = JoinCondition("left_col", "right_col", "eq")
        
        assert condition.left_column == "left_col"
        assert condition.right_column == "right_col"
        assert condition.operator == "eq"
    
    def test_join_condition_default_operator(self):
        """测试连接条件默认操作符"""
        condition = JoinCondition("left_col", "right_col")
        
        assert condition.operator == "eq"
    
    def test_join_condition_string_representation(self):
        """测试连接条件字符串表示"""
        condition = JoinCondition("left_col", "right_col", "eq")
        
        assert str(condition) == "left_col = right_col"
        
        condition = JoinCondition("left_col", "right_col", "gt")
        assert str(condition) == "left_col > right_col"


class TestJoinType:
    """测试JoinType枚举"""
    
    def test_join_type_values(self):
        """测试连接类型值"""
        assert JoinType.INNER.value == "inner"
        assert JoinType.LEFT.value == "left"
        assert JoinType.RIGHT.value == "right"
        assert JoinType.OUTER.value == "outer"
        assert JoinType.CROSS.value == "cross"
        assert JoinType.ANTI.value == "anti"
    
    def test_join_type_count(self):
        """测试连接类型数量"""
        assert len(JoinType) == 6


class TestResourceEstimator:
    """测试ResourceEstimator资源预估器"""
    
    def setup_method(self):
        """测试前置设置"""
        from join_engine.planner import ResourceEstimator
        self.estimator = ResourceEstimator()
    
    def test_estimate_join_rows(self):
        """测试行数估算"""
        # 内连接
        result = self.estimator.estimate_join_rows(1000, 2000, JoinType.INNER, 0.1)
        assert result == 100  # min(1000, 2000) * 0.1
        
        # 左连接
        result = self.estimator.estimate_join_rows(1000, 2000, JoinType.LEFT, 0.1)
        assert result == 1000
        
        # 笛卡尔积连接
        result = self.estimator.estimate_join_rows(100, 200, JoinType.CROSS, 0.1)
        assert result == 20000  # 100 * 200
    
    def test_estimate_memory_usage(self):
        """测试内存使用估算"""
        avg_mem, peak_mem = self.estimator.estimate_memory_usage(
            1000, 2000, 5, 8, JoinType.INNER
        )
        
        assert avg_mem > 0
        assert peak_mem > avg_mem
    
    def test_estimate_execution_time(self):
        """测试执行时间估算"""
        # 无索引
        time_no_index = self.estimator.estimate_execution_time(
            1000, 2000, JoinType.INNER, has_index=False
        )
        
        # 有索引 
        time_with_index = self.estimator.estimate_execution_time(
            1000, 2000, JoinType.INNER, has_index=True
        )
        
        assert time_no_index > time_with_index
    
    def test_estimate_cpu_complexity(self):
        """测试CPU复杂度估算"""
        complexity = self.estimator.estimate_cpu_complexity(
            1000, 2000, JoinType.INNER
        )
        
        assert 1 <= complexity <= 10
        
        # 笛卡尔积应该有更高的复杂度
        cross_complexity = self.estimator.estimate_cpu_complexity(
            1000, 2000, JoinType.CROSS
        )
        
        assert cross_complexity >= complexity


class TestResourceEstimate:
    """测试ResourceEstimate资源预估结果"""
    
    def test_resource_estimate_creation(self):
        """测试资源预估创建"""
        estimate = ResourceEstimate(
            total_memory_mb=100.0,
            peak_memory_mb=150.0,
            execution_time_s=30.0,
            temp_storage_mb=20.0,
            cpu_complexity_score=5
        )
        
        assert estimate.total_memory_mb == 100.0
        assert estimate.peak_memory_mb == 150.0
        assert estimate.execution_time_s == 30.0
        assert estimate.temp_storage_mb == 20.0
        assert estimate.cpu_complexity_score == 5
    
    def test_is_memory_intensive(self):
        """测试内存密集型判断"""
        # 不是内存密集型
        estimate = ResourceEstimate(100.0, 500.0, 30.0, 20.0, 5)
        assert not estimate.is_memory_intensive
        
        # 是内存密集型
        estimate = ResourceEstimate(100.0, 2000.0, 30.0, 20.0, 5)
        assert estimate.is_memory_intensive
    
    def test_is_time_intensive(self):
        """测试时间密集型判断"""
        # 不是时间密集型
        estimate = ResourceEstimate(100.0, 150.0, 60.0, 20.0, 5)
        assert not estimate.is_time_intensive
        
        # 是时间密集型
        estimate = ResourceEstimate(100.0, 150.0, 600.0, 20.0, 5)
        assert estimate.is_time_intensive


class TestExecutionPlan:
    """测试ExecutionPlan执行计划"""
    
    def test_execution_plan_creation(self):
        """测试执行计划创建"""
        from join_engine.planner import JoinStep
        
        steps = [
            JoinStep(
                step_id="step_1",
                left_source="left",
                right_source="right",
                join_type=JoinType.INNER,
                conditions=[JoinCondition("id", "id")]
            )
        ]
        
        estimate = ResourceEstimate(100.0, 150.0, 30.0, 20.0, 5)
        hints = [OptimizationHint("index", "Create index", "medium")]
        
        plan = ExecutionPlan(
            plan_id="test_plan",
            steps=steps,
            resource_estimate=estimate,
            optimization_hints=hints
        )
        
        assert plan.plan_id == "test_plan"
        assert plan.total_steps == 1
        assert len(plan.involves_sources) == 2
        assert "left" in plan.involves_sources
        assert "right" in plan.involves_sources


class TestJoinExecutor:
    """测试JoinExecutor连接执行器"""
    
    def setup_method(self):
        """测试前置设置"""
        self.executor = JoinExecutor(memory_limit_mb=1024)
    
    def test_join_executor_initialization(self):
        """测试执行器初始化"""
        assert self.executor.memory_limit_mb == 1024
        assert len(self.executor._active_executions) == 0
        assert len(self.executor._execution_stats) == 0
    
    def test_get_active_executions(self):
        """测试获取活动执行"""
        executions = self.executor.get_active_executions()
        assert isinstance(executions, dict)
        assert len(executions) == 0
    
    def test_get_execution_stats(self):
        """测试获取执行统计"""
        stats = self.executor.get_execution_stats()
        assert isinstance(stats, dict)
        assert len(stats) == 0
    
    def test_get_performance_summary(self):
        """测试获取性能摘要"""
        summary = self.executor.get_performance_summary()
        
        assert "total_executions" in summary
        assert summary["total_executions"] == 0
    
    def test_clear_execution_history(self):
        """测试清理执行历史"""
        # 添加一些统计数据
        self.executor._execution_stats["test"] = Mock()
        
        self.executor.clear_execution_history()
        
        assert len(self.executor._execution_stats) == 0


class TestPolarsJoinOperations:
    """测试Polars连接操作"""
    
    def setup_method(self):
        """创建测试数据"""
        self.left_data = pl.DataFrame({
            "id": [1, 2, 3, 4],
            "name": ["Alice", "Bob", "Charlie", "David"],
            "age": [25, 30, 35, 40]
        })
        
        self.right_data = pl.DataFrame({
            "id": [2, 3, 4, 5],
            "city": ["New York", "London", "Tokyo", "Paris"],
            "country": ["USA", "UK", "Japan", "France"]
        })
    
    def test_inner_join(self):
        """测试内连接"""
        result = self.left_data.join(
            self.right_data,
            left_on="id",
            right_on="id", 
            how="inner"
        )
        
        assert len(result) == 3  # ids 2, 3, 4 匹配
        assert "name" in result.columns
        assert "city" in result.columns
    
    def test_left_join(self):
        """测试左连接"""
        result = self.left_data.join(
            self.right_data,
            left_on="id",
            right_on="id",
            how="left"
        )
        
        assert len(result) == 4  # 保持左表所有行
        assert result.filter(pl.col("id") == 1).select("city").item(0, 0) is None
    
    def test_outer_join(self):
        """测试全外连接"""
        result = self.left_data.join(
            self.right_data,
            left_on="id",
            right_on="id",
            how="full"
        )
        
        assert len(result) >= 4  # 至少包含所有不同的id
    
    def test_cross_join(self):
        """测试笛卡尔积连接"""
        result = self.left_data.join(self.right_data, how="cross")
        
        assert len(result) == 16  # 4 * 4
    
    def test_anti_join(self):
        """测试反连接"""
        result = self.left_data.join(
            self.right_data,
            left_on="id",
            right_on="id",
            how="anti"
        )
        
        assert len(result) == 1  # 只有id=1不在右表中
        assert result.select("id").item(0, 0) == 1


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_simple_join_scenario(self):
        """测试简单连接场景（使用mock数据源）"""
        # 创建mock数据源连接器
        left_connector = AsyncMock(spec=DataSourceConnector)
        left_connector.source_id = "left_source"
        left_connector.source_type = DataSourceType.CSV
        left_connector.get_info.return_value = DataSourceInfo(
            source_id="left_source",
            source_type=DataSourceType.CSV,
            connection_params={},
            row_count=100,
            column_count=3
        )
        left_connector.get_schema_with_inference.return_value = {
            "columns": {"id": {}, "name": {}, "value": {}}
        }
        left_connector.query.return_value = pl.DataFrame({
            "id": [1, 2, 3],
            "name": ["A", "B", "C"],
            "value": [10, 20, 30]
        })
        
        right_connector = AsyncMock(spec=DataSourceConnector)
        right_connector.source_id = "right_source"  
        right_connector.source_type = DataSourceType.CSV
        right_connector.get_info.return_value = DataSourceInfo(
            source_id="right_source",
            source_type=DataSourceType.CSV,
            connection_params={},
            row_count=80,
            column_count=2
        )
        right_connector.get_schema_with_inference.return_value = {
            "columns": {"id": {}, "category": {}}
        }
        right_connector.query.return_value = pl.DataFrame({
            "id": [2, 3, 4],
            "category": ["X", "Y", "Z"]
        })
        
        # Mock registry，需要patch两个地方的import
        with patch('join_engine.registry') as mock_registry_main, \
             patch('join_engine.executor.registry') as mock_registry_executor:
            
            # 配置registry mock
            async def mock_acquire_source(source_id):
                from contextlib import asynccontextmanager
                
                @asynccontextmanager
                async def context():
                    if source_id == "left":
                        yield left_connector
                    elif source_id == "right":
                        yield right_connector
                    else:
                        raise ValueError(f"Unknown source: {source_id}")
                
                return context()
            
            # 配置两个registry mock
            for mock_registry in [mock_registry_main, mock_registry_executor]:
                mock_registry.get_source.side_effect = lambda sid: left_connector if sid == "left" else right_connector
                mock_registry.acquire_source = mock_acquire_source
            
            # 创建连接引擎
            engine = create_join_engine(optimization_level=0)  # 关闭优化简化测试
            
            # 定义连接规格
            sources = {"left": "left", "right": "right"}
            join_specs = [{
                "left_source": "left",
                "right_source": "right",
                "join_type": "inner",
                "conditions": [{"left_column": "id", "right_column": "id"}]
            }]
            
            # 创建计划
            plan = await engine.plan_join(sources, join_specs)
            
            # 验证计划
            assert plan.total_steps == 1
            assert plan.steps[0].join_type == JoinType.INNER
            assert len(plan.steps[0].conditions) == 1
    
    def test_end_to_end_validation(self):
        """测试端到端验证"""
        # 验证所有组件都能正确实例化
        engine = create_join_engine()
        
        assert isinstance(engine, JoinEngine)
        assert isinstance(engine.planner, JoinPlanner) 
        assert isinstance(engine.executor, JoinExecutor)
        assert isinstance(engine.optimizer, JoinOptimizer)
        
        # 验证配置参数正确传递
        engine = create_join_engine(optimization_level=3, memory_limit_mb=4096)
        
        assert engine.optimization_level == 3
        assert engine.memory_limit_mb == 4096