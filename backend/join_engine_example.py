#!/usr/bin/env python3
"""
JoinEngine 使用示例
演示如何使用连接引擎进行多数据源连接
"""
import asyncio
import polars as pl
from join_engine import (
    create_join_engine,
    JoinType,
    execute_simple_join
)


async def example_basic_usage():
    """基础使用示例"""
    print("=== JoinEngine 基础使用示例 ===")
    
    # 创建连接引擎
    engine = create_join_engine(
        optimization_level=2,
        memory_limit_mb=1024
    )
    
    print(f"连接引擎已创建，优化级别: {engine.optimization_level}")
    
    # 定义连接规格
    sources = {
        "orders": "orders_source",      # 订单表
        "customers": "customers_source"  # 客户表
    }
    
    join_specs = [{
        "left_source": "orders",
        "right_source": "customers", 
        "join_type": "inner",
        "conditions": [
            {"left_column": "customer_id", "right_column": "id", "operator": "eq"}
        ]
    }]
    
    try:
        # 注意：这个例子需要真实的数据源连接器才能工作
        # 这里只是演示API使用方式
        
        # 1. 创建执行计划
        print("\n1. 创建执行计划...")
        # plan = await engine.plan_join(sources, join_specs)
        # print(f"计划ID: {plan.plan_id}")
        # print(f"预计执行时间: {plan.resource_estimate.execution_time_s:.2f}秒")
        # print(f"预计内存使用: {plan.resource_estimate.peak_memory_mb:.1f}MB")
        
        # 2. 获取优化建议
        print("\n2. 获取优化建议...")
        # recommendations = await engine.get_join_recommendations(sources, join_specs)
        # print(f"性能评分: {recommendations.get('performance_score', 'N/A')}")
        # for hint in recommendations.get('optimization_hints', []):
        #     print(f"  - {hint['type']}: {hint['message']}")
        
        # 3. 执行连接
        print("\n3. 执行连接...")
        # result = await engine.plan_and_execute_join(sources, join_specs)
        # print(f"连接结果: {len(result)}行 x {len(result.columns)}列")
        
        print("示例完成（需要真实数据源）")
        
    except Exception as e:
        print(f"示例执行失败（预期的，因为没有真实数据源）: {e}")


def example_join_types():
    """连接类型示例"""
    print("\n=== 连接类型示例 ===")
    
    # 创建测试数据
    left_data = pl.DataFrame({
        "id": [1, 2, 3, 4],
        "name": ["Alice", "Bob", "Charlie", "David"],
        "department": ["IT", "HR", "Finance", "IT"]
    })
    
    right_data = pl.DataFrame({
        "id": [2, 3, 4, 5],
        "city": ["New York", "London", "Tokyo", "Paris"],
        "country": ["USA", "UK", "Japan", "France"]
    })
    
    print("左表数据:")
    print(left_data)
    print("\n右表数据:")
    print(right_data)
    
    # 演示不同连接类型
    join_examples = [
        ("inner", "内连接 - 仅保留匹配记录"),
        ("left", "左连接 - 保留左表所有记录"),
        ("full", "全外连接 - 保留所有表记录"),
        ("cross", "笛卡尔积连接 - 所有组合"),
        ("anti", "反连接 - 左表中不匹配的记录")
    ]
    
    for join_type, description in join_examples:
        try:
            print(f"\n{description}:")
            result = left_data.join(
                right_data,
                left_on="id",
                right_on="id",
                how=join_type
            )
            print(f"结果: {len(result)}行")
            print(result.head())
        except Exception as e:
            print(f"连接失败: {e}")


def example_resource_estimation():
    """资源预估示例"""
    print("\n=== 资源预估示例 ===")
    
    from join_engine.planner import ResourceEstimator, JoinType
    
    estimator = ResourceEstimator()
    
    # 不同场景的资源预估
    scenarios = [
        ("小表连接", 1000, 2000, JoinType.INNER),
        ("大表内连接", 100000, 200000, JoinType.INNER),
        ("笛卡尔积连接", 1000, 1000, JoinType.CROSS),
        ("左连接", 50000, 30000, JoinType.LEFT)
    ]
    
    for name, left_rows, right_rows, join_type in scenarios:
        print(f"\n{name}:")
        print(f"  左表: {left_rows:,} 行, 右表: {right_rows:,} 行")
        
        # 行数预估
        estimated_rows = estimator.estimate_join_rows(left_rows, right_rows, join_type)
        print(f"  预估结果行数: {estimated_rows:,}")
        
        # 内存使用预估
        avg_mem, peak_mem = estimator.estimate_memory_usage(
            left_rows, right_rows, 10, 8, join_type
        )
        print(f"  预估内存使用: 平均 {avg_mem:.1f}MB, 峰值 {peak_mem:.1f}MB")
        
        # 执行时间预估
        exec_time = estimator.estimate_execution_time(
            left_rows, right_rows, join_type, has_index=False
        )
        print(f"  预估执行时间: {exec_time:.2f}秒")
        
        # CPU复杂度
        complexity = estimator.estimate_cpu_complexity(left_rows, right_rows, join_type)
        print(f"  CPU复杂度评分: {complexity}/10")


def example_optimization_hints():
    """优化建议示例"""
    print("\n=== 优化建议示例 ===")
    
    from join_engine.planner import OptimizationHint
    from join_engine.optimizer import IndexRecommendation
    
    # 创建示例优化建议
    hints = [
        OptimizationHint(
            type="memory",
            message="连接操作需要大量内存，建议启用分块处理",
            impact_level="high",
            estimated_improvement="减少50%内存使用"
        ),
        OptimizationHint(
            type="index", 
            message="建议在连接列上创建索引",
            impact_level="medium",
            estimated_improvement="减少20%执行时间"
        ),
        OptimizationHint(
            type="order",
            message="建议调整连接顺序，小表优先",
            impact_level="low",
            estimated_improvement="减少10%执行时间"
        )
    ]
    
    print("优化建议:")
    for hint in hints:
        impact_icon = {"high": "🔥", "medium": "⚠️", "low": "💡"}.get(hint.impact_level, "ℹ️")
        print(f"  {impact_icon} [{hint.type.upper()}] {hint.message}")
        if hint.estimated_improvement:
            print(f"     预计改善: {hint.estimated_improvement}")
    
    # 索引推荐示例
    print("\n索引推荐:")
    index_recs = [
        IndexRecommendation(
            source_id="orders_table",
            column_name="customer_id", 
            index_type="btree",
            estimated_improvement=25.0,
            priority="high",
            reason="连接列上的索引可以显著提高性能"
        ),
        IndexRecommendation(
            source_id="products_table",
            column_name="category_id",
            index_type="hash", 
            estimated_improvement=15.0,
            priority="medium",
            reason="频繁查询的列建议创建哈希索引"
        )
    ]
    
    for rec in index_recs:
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec.priority, "⚪")
        print(f"  {priority_icon} {rec.source_id}.{rec.column_name}")
        print(f"     类型: {rec.index_type}, 预计改善: {rec.estimated_improvement}%")
        print(f"     原因: {rec.reason}")


def example_performance_monitoring():
    """性能监控示例"""
    print("\n=== 性能监控示例 ===")
    
    # 创建连接引擎
    engine = create_join_engine()
    
    # 获取性能指标
    metrics = engine.get_performance_metrics()
    
    print("引擎性能指标:")
    print(f"  总执行次数: {metrics['total_executions']}")
    print(f"  平均执行时间: {metrics['average_execution_time_s']:.2f}秒")
    print(f"  平均结果行数: {metrics['average_result_rows']:,}")
    print(f"  平均内存使用: {metrics['average_memory_usage_mb']:.1f}MB")
    print(f"  成功率: {metrics['success_rate']*100:.1f}%")
    
    # 引擎配置
    config = metrics['engine_config']
    print(f"\n引擎配置:")
    print(f"  优化级别: {config['optimization_level']}")
    print(f"  内存限制: {config['memory_limit_mb']}MB")
    print(f"  缓存启用: {config['caching_enabled']}")
    
    # 执行器统计
    executor_stats = engine.get_executor_stats()
    print(f"\n执行器统计:")
    for key, value in executor_stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")


def main():
    """主函数"""
    print("🔗 JoinEngine 连接引擎使用示例")
    print("=" * 50)
    
    # 运行异步示例
    asyncio.run(example_basic_usage())
    
    # 运行同步示例
    example_join_types()
    example_resource_estimation()
    example_optimization_hints()
    example_performance_monitoring()
    
    print("\n" + "=" * 50)
    print("✅ 所有示例运行完成")


if __name__ == "__main__":
    main()