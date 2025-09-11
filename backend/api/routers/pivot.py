"""
透视分析路由
提供连接结果到透视分析的API端点
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any, List
import logging

from backend.adapters.pivot_bridge import PivotBridge
from backend.models.api.request_models import PivotConfigRequest
from backend.models.api.response_models import (
    PivotPreviewResponse, 
    PivotDataResponse, 
    ValidationResponse
)
from backend.services.join_service import join_service
from backend.api.validators import validate_result_id

logger = logging.getLogger(__name__)
router = APIRouter()

# 全局PivotBridge实例
pivot_bridge = PivotBridge()


@router.get("/result/{result_id}/pivot-preview", response_model=PivotPreviewResponse)
async def get_pivot_preview(
    result_id: str,
    limit: int = Query(100, description="预览行数限制", ge=10, le=1000),
    _: dict = Depends(validate_result_id)
):
    """
    获取连接结果的透视预览数据
    
    用于在用户配置透视表之前预览数据结构和内容
    """
    try:
        logger.info(f"Getting pivot preview for result {result_id}, limit: {limit}")
        
        # 获取连接结果
        join_result = await join_service.get_result(result_id)
        if not join_result:
            raise HTTPException(status_code=404, detail=f"Join result {result_id} not found")
        
        # 转换为AR Table
        ar_table = pivot_bridge.convert_join_result_to_ar_table(join_result)
        
        # 获取预览
        preview = pivot_bridge.get_pivot_preview(ar_table, preview_rows=limit)
        
        return PivotPreviewResponse(
            result_id=result_id,
            preview_data=preview["preview"],
            fields=preview["fields"],
            sample_size=preview["sample_size"],
            total_size=preview["total_size"],
            recommended_dimensions=preview["recommendations"],
            recommended_measures=preview["measures"],
            performance_hints=preview["performance_hints"]
        )
        
    except Exception as e:
        logger.error(f"Failed to get pivot preview for {result_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate pivot preview: {str(e)}")


@router.post("/result/{result_id}/create-pivot", response_model=PivotDataResponse)
async def create_pivot_from_join(
    result_id: str,
    config: PivotConfigRequest,
    limit: Optional[int] = Query(None, description="数据行数限制", ge=1, le=100000),
    _: dict = Depends(validate_result_id)
):
    """
    基于连接结果创建透视分析
    
    接受透视配置并返回计算后的透视数据
    """
    try:
        logger.info(f"Creating pivot from result {result_id} with config: {config.dict()}")
        
        # 获取连接结果
        join_result = await join_service.get_result(result_id)
        if not join_result:
            raise HTTPException(status_code=404, detail=f"Join result {result_id} not found")
        
        # 转换为AR Table
        ar_table = pivot_bridge.convert_join_result_to_ar_table(
            join_result, 
            performance_mode=config.performance_mode
        )
        
        # 验证AR Table
        validation = pivot_bridge.validate_ar_table(ar_table)
        if not validation["valid"]:
            logger.warning(f"AR Table validation issues: {validation['warnings']}")
        
        # 转换为透视格式
        pivot_data = pivot_bridge.convert_to_pivot_format(ar_table, limit=limit)
        
        # 应用透视配置（这里需要调用现有的透视计算逻辑）
        processed_data = await _apply_pivot_configuration(pivot_data, config)
        
        return PivotDataResponse(
            result_id=result_id,
            pivot_data=processed_data["pivot_table"],
            row_fields=config.row_fields,
            col_fields=config.col_fields,
            value_fields=config.value_fields,
            aggregation_type=config.aggregation_type,
            total_records=pivot_data["total_count"],
            processing_time_ms=processed_data.get("processing_time_ms", 0),
            warnings=validation.get("warnings", []),
            metadata=pivot_data["metadata"]
        )
        
    except Exception as e:
        logger.error(f"Failed to create pivot from {result_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create pivot: {str(e)}")


@router.get("/result/{result_id}/validate", response_model=ValidationResponse)
async def validate_for_pivot(
    result_id: str,
    _: dict = Depends(validate_result_id)
):
    """
    验证连接结果是否适合进行透视分析
    
    返回数据质量评估和性能建议
    """
    try:
        logger.info(f"Validating result {result_id} for pivot analysis")
        
        # 获取连接结果
        join_result = await join_service.get_result(result_id)
        if not join_result:
            raise HTTPException(status_code=404, detail=f"Join result {result_id} not found")
        
        # 转换为AR Table
        ar_table = pivot_bridge.convert_join_result_to_ar_table(join_result)
        
        # 验证
        validation = pivot_bridge.validate_ar_table(ar_table)
        
        return ValidationResponse(
            result_id=result_id,
            valid=validation["valid"],
            warnings=validation["warnings"],
            recommendations=validation["recommendations"],
            performance_score=validation["performance_score"],
            data_summary={
                "total_rows": len(ar_table.data),
                "total_columns": len(ar_table.data.columns),
                "numeric_columns": len([c for c in ar_table.data.columns 
                                      if ar_table.data[c].dtype in [ar_table.data.dtypes[0].__class__._variants['Int64'], 
                                                                    ar_table.data.dtypes[0].__class__._variants['Float64']]]),
                "estimated_memory_mb": (len(ar_table.data) * len(ar_table.data.columns) * 8) / (1024 * 1024)
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to validate result {result_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/result/{result_id}/metadata")
async def get_result_metadata(
    result_id: str,
    _: dict = Depends(validate_result_id)
):
    """
    获取连接结果的元数据信息
    
    用于透视配置界面显示数据源信息和质量指标
    """
    try:
        logger.info(f"Getting metadata for result {result_id}")
        
        # 获取连接结果
        join_result = await join_service.get_result(result_id)
        if not join_result:
            raise HTTPException(status_code=404, detail=f"Join result {result_id} not found")
        
        # 转换为AR Table以获取完整元数据
        ar_table = pivot_bridge.convert_join_result_to_ar_table(join_result)
        
        return {
            "result_id": result_id,
            "source_info": ar_table.metadata.source_info,
            "join_statistics": {
                "total_records": ar_table.metadata.join_statistics.total_records,
                "matched_records": ar_table.metadata.join_statistics.matched_records,
                "unmatched_records": ar_table.metadata.join_statistics.unmatched_records,
                "execution_time_ms": ar_table.metadata.join_statistics.execution_time_ms,
                "memory_peak_mb": ar_table.metadata.join_statistics.memory_peak_mb
            },
            "quality_metrics": {
                "completeness": ar_table.metadata.quality_metrics.completeness,
                "accuracy": ar_table.metadata.quality_metrics.accuracy,
                "consistency": ar_table.metadata.quality_metrics.consistency,
                "uniqueness": ar_table.metadata.quality_metrics.uniqueness
            },
            "created_at": ar_table.metadata.created_at.isoformat(),
            "schema": {
                "columns": ar_table.data.columns,
                "column_types": {col: str(dtype) for col, dtype in zip(ar_table.data.columns, ar_table.data.dtypes)},
                "row_count": len(ar_table.data)
            },
            "pivot_recommendations": ar_table.pivot_config
        }
        
    except Exception as e:
        logger.error(f"Failed to get metadata for {result_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metadata: {str(e)}")


async def _apply_pivot_configuration(
    pivot_data: Dict[str, Any], 
    config: PivotConfigRequest
) -> Dict[str, Any]:
    """
    应用透视配置到数据
    
    这个函数将集成现有的透视计算逻辑
    """
    import time
    start_time = time.time()
    
    try:
        # 这里应该调用现有的透视计算逻辑
        # 现在作为示例，返回模拟的透视结果
        
        rows = pivot_data["rows"]
        
        # 基础透视计算示例（实际实现需要调用现有的透视引擎）
        if not config.row_fields and not config.col_fields:
            # 没有分组字段，返回聚合结果
            pivot_table = _calculate_simple_aggregation(rows, config.value_fields, config.aggregation_type)
        else:
            # 有分组字段，执行透视计算
            pivot_table = _calculate_pivot_table(rows, config)
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            "pivot_table": pivot_table,
            "processing_time_ms": processing_time,
            "config_applied": config.dict()
        }
        
    except Exception as e:
        logger.error(f"Failed to apply pivot configuration: {e}")
        raise


def _calculate_simple_aggregation(rows: List[Dict], value_fields: List[str], agg_type: str) -> Dict[str, Any]:
    """计算简单聚合（无分组）"""
    result = {}
    
    for field in value_fields:
        values = [row.get(field, 0) for row in rows if row.get(field) is not None]
        numeric_values = [float(v) for v in values if isinstance(v, (int, float))]
        
        if numeric_values:
            if agg_type == "sum":
                result[field] = sum(numeric_values)
            elif agg_type == "mean":
                result[field] = sum(numeric_values) / len(numeric_values)
            elif agg_type == "count":
                result[field] = len(numeric_values)
            elif agg_type == "min":
                result[field] = min(numeric_values)
            elif agg_type == "max":
                result[field] = max(numeric_values)
            else:
                result[field] = sum(numeric_values)  # 默认求和
        else:
            result[field] = 0
    
    return {"summary": result, "total_records": len(rows)}


def _calculate_pivot_table(rows: List[Dict], config: PivotConfigRequest) -> Dict[str, Any]:
    """计算透视表（有分组）- 简化版实现"""
    from collections import defaultdict
    
    # 按行字段分组
    grouped = defaultdict(list)
    
    for row in rows:
        # 生成分组键
        group_key = tuple(str(row.get(field, '')) for field in config.row_fields)
        grouped[group_key].append(row)
    
    # 计算每组的聚合值
    pivot_result = []
    
    for group_key, group_rows in grouped.items():
        row_data = {}
        
        # 添加分组字段
        for i, field in enumerate(config.row_fields):
            row_data[field] = group_key[i]
        
        # 计算聚合值
        for value_field in config.value_fields:
            values = [row.get(value_field, 0) for row in group_rows if row.get(value_field) is not None]
            numeric_values = [float(v) for v in values if isinstance(v, (int, float))]
            
            if numeric_values:
                if config.aggregation_type == "sum":
                    row_data[f"{value_field}_sum"] = sum(numeric_values)
                elif config.aggregation_type == "mean":
                    row_data[f"{value_field}_avg"] = sum(numeric_values) / len(numeric_values)
                elif config.aggregation_type == "count":
                    row_data[f"{value_field}_count"] = len(numeric_values)
                elif config.aggregation_type == "min":
                    row_data[f"{value_field}_min"] = min(numeric_values)
                elif config.aggregation_type == "max":
                    row_data[f"{value_field}_max"] = max(numeric_values)
                else:
                    row_data[f"{value_field}_sum"] = sum(numeric_values)
            else:
                row_data[f"{value_field}_{config.aggregation_type}"] = 0
        
        pivot_result.append(row_data)
    
    return {
        "pivot_table": pivot_result,
        "group_count": len(pivot_result),
        "total_records": len(rows)
    }