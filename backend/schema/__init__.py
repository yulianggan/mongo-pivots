"""
Schema - 数据结构和类型推断模块
提供智能的数据类型推断和结构分析功能
"""

from typing import Dict, Any, List, Optional, Union
import polars as pl

# 导出主要接口（等待后续Stream实现具体功能）
__all__ = [
    'SchemaInfo',
    'ColumnInfo', 
    'DataType',
]


class DataType:
    """数据类型常量"""
    STRING = "string"
    INTEGER = "integer" 
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    JSON = "json"
    NULL = "null"


class ColumnInfo:
    """列信息"""
    def __init__(
        self, 
        name: str,
        data_type: str,
        nullable: bool = True,
        unique_count: Optional[int] = None,
        null_count: Optional[int] = None,
        sample_values: Optional[List[Any]] = None
    ):
        self.name = name
        self.data_type = data_type
        self.nullable = nullable
        self.unique_count = unique_count
        self.null_count = null_count
        self.sample_values = sample_values or []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'data_type': self.data_type,
            'nullable': self.nullable,
            'unique_count': self.unique_count,
            'null_count': self.null_count,
            'sample_values': self.sample_values
        }


class SchemaInfo:
    """数据结构信息"""
    def __init__(self, columns: List[ColumnInfo]):
        self.columns = {col.name: col for col in columns}
        self.column_count = len(columns)
    
    def get_column(self, name: str) -> Optional[ColumnInfo]:
        """获取列信息"""
        return self.columns.get(name)
    
    def get_column_names(self) -> List[str]:
        """获取所有列名"""
        return list(self.columns.keys())
    
    def get_column_types(self) -> Dict[str, str]:
        """获取列类型映射"""
        return {name: col.data_type for name, col in self.columns.items()}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'columns': {name: col.to_dict() for name, col in self.columns.items()},
            'column_count': self.column_count
        }
    
    @classmethod
    def from_polars(cls, df: pl.DataFrame) -> 'SchemaInfo':
        """从Polars DataFrame创建结构信息"""
        columns = []
        
        for col_name in df.columns:
            # 获取列数据类型
            dtype = df[col_name].dtype
            if dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64]:
                data_type = DataType.INTEGER
            elif dtype in [pl.Float32, pl.Float64]:
                data_type = DataType.FLOAT
            elif dtype == pl.Boolean:
                data_type = DataType.BOOLEAN
            elif dtype == pl.Date:
                data_type = DataType.DATE
            elif dtype == pl.Datetime:
                data_type = DataType.DATETIME
            else:
                data_type = DataType.STRING
            
            # 获取基本统计信息
            col_series = df[col_name]
            null_count = col_series.null_count()
            unique_count = col_series.n_unique() if len(df) > 0 else 0
            
            # 获取样本值（最多5个非空值）
            sample_values = []
            try:
                non_null_values = col_series.drop_nulls().head(5).to_list()
                sample_values = [str(v) for v in non_null_values]
            except:
                pass
            
            column_info = ColumnInfo(
                name=col_name,
                data_type=data_type,
                nullable=null_count > 0,
                unique_count=unique_count,
                null_count=null_count,
                sample_values=sample_values
            )
            
            columns.append(column_info)
        
        return cls(columns)


def analyze_dataframe_schema(df: pl.DataFrame) -> SchemaInfo:
    """分析DataFrame的结构信息
    
    Args:
        df: Polars DataFrame
        
    Returns:
        SchemaInfo: 结构信息对象
    """
    return SchemaInfo.from_polars(df)