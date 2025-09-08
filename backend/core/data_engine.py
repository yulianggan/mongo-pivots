"""
DataEngine - Polars引擎封装
提供统一的数据操作接口，替换pandas实现
"""
import polars as pl
import pandas as pd
from typing import Dict, Any, List, Optional, Union, Tuple
from io import BytesIO
import chardet
import time
import math

from .config import config
from .memory_guard import memory_guard
from .chunk_processor import chunk_processor


class DataEngine:
    """Polars数据引擎"""
    
    def __init__(self):
        # 应用Polars配置
        config.apply_polars_config()
        
        # 启动内存监控
        memory_guard.start_monitoring()
    
    def read_csv(
        self, 
        content: Union[str, bytes], 
        separator: str = ',',
        encoding: str = 'utf-8',
        start_row: int = 1,
        use_chunking: bool = True,
        **kwargs
    ) -> pl.DataFrame:
        """读取CSV数据"""
        
        with memory_guard.memory_guard("read_csv"):
            try:
                if isinstance(content, bytes):
                    # 估算内存需求
                    estimated_rows = len(content.split(b'\n'))
                    estimated_memory = memory_guard.estimate_dataframe_memory(estimated_rows, 20)
                    
                    # 如果数据较大且启用分块，使用分块处理
                    if use_chunking and estimated_memory > config.get_memory_limit_bytes() * 0.3:
                        return self._read_csv_chunked(content, separator, encoding, start_row, **kwargs)
                    else:
                        return self._read_csv_direct(content, separator, encoding, start_row, **kwargs)
                else:
                    # 文件路径，使用Polars直接读取
                    read_kwargs = {
                        'separator': separator,
                        'encoding': encoding,
                        'skip_rows': start_row - 1 if start_row > 1 else 0,
                        **kwargs
                    }
                    return pl.read_csv(content, **read_kwargs)
                    
            except Exception as e:
                # 如果Polars失败，回退到pandas兼容方式
                print(f"Polars read failed: {e}, falling back to pandas conversion")
                return self._read_csv_pandas_fallback(content, separator, encoding, start_row, **kwargs)
    
    def _read_csv_direct(
        self, 
        content: bytes, 
        separator: str, 
        encoding: str, 
        start_row: int,
        **kwargs
    ) -> pl.DataFrame:
        """直接读取CSV（适用于小文件）"""
        
        # 创建BytesIO对象
        buffer = BytesIO(content)
        
        read_kwargs = {
            'separator': separator,
            'encoding': encoding,
            'skip_rows': start_row - 1 if start_row > 1 else 0,
            'infer_schema_length': 1000,  # 限制推断长度以节省内存
            **kwargs
        }
        
        try:
            df = pl.read_csv(buffer, **read_kwargs)
        except Exception:
            # 尝试不同的编码
            for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']:
                try:
                    buffer = BytesIO(content)
                    read_kwargs['encoding'] = enc
                    df = pl.read_csv(buffer, **read_kwargs)
                    break
                except Exception:
                    continue
            else:
                raise ValueError("无法使用任何编码读取CSV文件")
        
        return df
    
    def _read_csv_chunked(
        self, 
        content: bytes, 
        separator: str, 
        encoding: str, 
        start_row: int,
        **kwargs
    ) -> pl.DataFrame:
        """分块读取大CSV文件"""
        
        read_kwargs = {
            'separator': separator,
            'encoding': encoding,
            'skip_rows': start_row - 1 if start_row > 1 else 0,
            'infer_schema_length': 1000,
            **kwargs
        }
        
        def identity_operation(chunk: pl.DataFrame) -> pl.DataFrame:
            return chunk
        
        return chunk_processor.process_and_aggregate(
            content, 
            identity_operation,
            **read_kwargs
        )
    
    def _read_csv_pandas_fallback(
        self, 
        content: Union[str, bytes], 
        separator: str, 
        encoding: str, 
        start_row: int,
        **kwargs
    ) -> pl.DataFrame:
        """pandas兼容模式回退"""
        
        if isinstance(content, bytes):
            buffer = BytesIO(content)
        else:
            buffer = content
        
        # 使用pandas读取
        pandas_df = pd.read_csv(
            buffer,
            sep=separator,
            encoding=encoding,
            header=start_row-1 if start_row > 1 else 0,
            dtype=str,
            na_values=['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na'],
            keep_default_na=True,
            **kwargs
        )
        
        # 转换为Polars DataFrame
        return pl.from_pandas(pandas_df)
    
    def read_excel(
        self, 
        content: bytes, 
        sheet: Optional[Union[str, int]] = None,
        start_row: int = 1,
        **kwargs
    ) -> pl.DataFrame:
        """读取Excel文件"""
        
        with memory_guard.memory_guard("read_excel"):
            # Excel处理仍然使用pandas，因为Polars的Excel支持有限
            buffer = BytesIO(content)
            
            try:
                pandas_df = pd.read_excel(
                    buffer,
                    sheet_name=sheet,
                    header=start_row-1 if start_row > 1 else 0,
                    engine=None,
                    na_values=['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na'],
                    keep_default_na=True,
                    **kwargs
                )
                
                if isinstance(pandas_df, dict):
                    first_key = list(pandas_df.keys())[0]
                    pandas_df = pandas_df[first_key]
                
                # 转换为Polars DataFrame
                return pl.from_pandas(pandas_df)
                
            except Exception as e:
                raise ValueError(f"Excel文件读取失败: {str(e)}")
    
    def clean_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """清理DataFrame数据"""
        
        with memory_guard.memory_guard("clean_dataframe"):
            # 清理列名
            clean_columns = []
            for i, col in enumerate(df.columns):
                if col is None or str(col).strip() == '':
                    clean_columns.append(f'Column_{i}')
                else:
                    clean_columns.append(str(col).strip())
            
            # 重命名列
            column_mapping = {old: new for old, new in zip(df.columns, clean_columns)}
            df = df.rename(column_mapping)
            
            # 删除完全空的行
            df = df.filter(~pl.all_horizontal(pl.all().is_null()))
            
            # 处理特殊数值
            for col in df.columns:
                col_type = df[col].dtype
                if col_type in [pl.Float32, pl.Float64]:
                    # 替换无穷大为null
                    df = df.with_columns(
                        pl.when(pl.col(col).is_infinite())
                        .then(None)
                        .otherwise(pl.col(col))
                        .alias(col)
                    )
            
            return df
    
    def convert_to_records(self, df: pl.DataFrame) -> List[Dict[str, Any]]:
        """转换为记录列表，确保JSON序列化安全"""
        
        with memory_guard.memory_guard("convert_to_records"):
            # 处理特殊值以确保JSON安全
            def safe_convert_value(v):
                if v is None:
                    return None
                if isinstance(v, (int, str, bool)):
                    return v
                if isinstance(v, float):
                    if math.isnan(v) or math.isinf(v):
                        return None
                    return v
                return str(v)
            
            # 转换为Python字典列表
            records = df.to_dicts()
            
            # 安全转换每个值
            safe_records = []
            for record in records:
                safe_record = {str(k): safe_convert_value(v) for k, v in record.items()}
                safe_records.append(safe_record)
            
            return safe_records
    
    def get_field_types(self, df: pl.DataFrame) -> Dict[str, str]:
        """获取字段类型信息"""
        
        fields = {}
        for col in df.columns:
            dtype = df[col].dtype
            
            if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                        pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                        pl.Float32, pl.Float64]:
                fields[col] = 'number'
            elif dtype == pl.Boolean:
                fields[col] = 'boolean'
            elif dtype == pl.Date or dtype == pl.Datetime:
                fields[col] = 'date'
            else:
                fields[col] = 'string'
        
        return fields
    
    def optimize_dataframe(self, df: pl.DataFrame) -> pl.DataFrame:
        """优化DataFrame内存使用"""
        
        with memory_guard.memory_guard("optimize_dataframe"):
            # 尝试推断更紧凑的数据类型
            optimized_exprs = []
            
            for col in df.columns:
                dtype = df[col].dtype
                
                if dtype == pl.Utf8:
                    # 检查是否可以转为数值类型
                    try:
                        # 尝试转换为数值
                        numeric_expr = pl.col(col).cast(pl.Float64, strict=False)
                        optimized_exprs.append(
                            pl.when(pl.col(col).str.strip_chars().str.len_chars() == 0)
                            .then(None)
                            .otherwise(numeric_expr)
                            .alias(col)
                        )
                    except:
                        # 保持字符串类型
                        optimized_exprs.append(pl.col(col))
                else:
                    optimized_exprs.append(pl.col(col))
            
            return df.with_columns(optimized_exprs)
    
    def filter_data(
        self, 
        df: pl.DataFrame, 
        filters: Dict[str, Any],
        use_lazy: bool = True
    ) -> pl.DataFrame:
        """过滤数据"""
        
        with memory_guard.memory_guard("filter_data"):
            if use_lazy and config.polars.lazy_by_default:
                # 使用懒计算
                lazy_df = df.lazy()
                
                for field, value in filters.items():
                    if field in df.columns:
                        if isinstance(value, dict):
                            # MongoDB风格的查询
                            for op, val in value.items():
                                if op == '$eq':
                                    lazy_df = lazy_df.filter(pl.col(field) == val)
                                elif op == '$ne':
                                    lazy_df = lazy_df.filter(pl.col(field) != val)
                                elif op == '$gt':
                                    lazy_df = lazy_df.filter(pl.col(field) > val)
                                elif op == '$gte':
                                    lazy_df = lazy_df.filter(pl.col(field) >= val)
                                elif op == '$lt':
                                    lazy_df = lazy_df.filter(pl.col(field) < val)
                                elif op == '$lte':
                                    lazy_df = lazy_df.filter(pl.col(field) <= val)
                                elif op == '$in':
                                    lazy_df = lazy_df.filter(pl.col(field).is_in(val))
                        else:
                            # 简单相等匹配
                            lazy_df = lazy_df.filter(pl.col(field) == value)
                
                return lazy_df.collect()
            else:
                # 直接过滤
                filtered_df = df
                
                for field, value in filters.items():
                    if field in df.columns:
                        if isinstance(value, dict):
                            for op, val in value.items():
                                if op == '$eq':
                                    filtered_df = filtered_df.filter(pl.col(field) == val)
                                elif op == '$ne':
                                    filtered_df = filtered_df.filter(pl.col(field) != val)
                                # ... 其他操作符实现
                        else:
                            filtered_df = filtered_df.filter(pl.col(field) == value)
                
                return filtered_df
    
    def select_columns(
        self, 
        df: pl.DataFrame, 
        projection: Optional[Dict[str, int]] = None
    ) -> pl.DataFrame:
        """选择列"""
        
        if projection is None:
            return df
        
        with memory_guard.memory_guard("select_columns"):
            # 获取需要的列
            selected_columns = []
            for field, include in projection.items():
                if include and field in df.columns:
                    selected_columns.append(field)
            
            if selected_columns:
                return df.select(selected_columns)
            else:
                return df
    
    def paginate(
        self, 
        df: pl.DataFrame, 
        skip: int = 0, 
        limit: Optional[int] = None
    ) -> pl.DataFrame:
        """分页"""
        
        with memory_guard.memory_guard("paginate"):
            if limit is None:
                return df.slice(skip)
            else:
                return df.slice(skip, limit)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            'config': config.to_dict(),
            'memory': memory_guard.to_dict(),
            'chunk_processor': {
                'chunk_size': chunk_processor.chunk_size
            }
        }


# 全局数据引擎实例
data_engine = DataEngine()