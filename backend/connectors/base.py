"""
DataSourceConnector - 数据源连接器抽象基类
定义统一的数据源接口，支持流式读取和分块处理
"""
import polars as pl
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Iterator, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager
import time
import logging
from enum import Enum

from core.data_engine import data_engine
from core.memory_guard import memory_guard
from core.config import config


class DataSourceType(Enum):
    """数据源类型"""
    MONGODB = "mongodb"
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class ConnectionStatus(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting" 
    CONNECTED = "connected"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class DataSourceInfo:
    """数据源信息"""
    source_id: str
    source_type: DataSourceType
    connection_params: Dict[str, Any]
    schema: Optional[Dict[str, Any]] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    last_accessed: Optional[float] = None


@dataclass
class QueryOptions:
    """查询选项"""
    filters: Optional[Dict[str, Any]] = None
    projection: Optional[Dict[str, int]] = None
    sort: Optional[Dict[str, int]] = None
    skip: int = 0
    limit: Optional[int] = None
    batch_size: int = 1000
    streaming: bool = False
    memory_optimized: bool = True


class DataSourceConnector(ABC):
    """数据源连接器抽象基类"""
    
    def __init__(self, source_id: str, source_type: DataSourceType, **connection_params):
        self.source_id = source_id
        self.source_type = source_type
        self.connection_params = connection_params
        self.connection_status = ConnectionStatus.DISCONNECTED
        self._connection = None
        self._schema_cache = None
        self._logger = logging.getLogger(f"{self.__class__.__name__}.{source_id}")
        self.info = DataSourceInfo(
            source_id=source_id,
            source_type=source_type,
            connection_params=connection_params
        )
    
    @abstractmethod
    async def connect(self) -> bool:
        """建立连接到数据源
        
        Returns:
            bool: 连接是否成功
            
        Raises:
            ConnectionError: 连接失败时抛出
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """测试连接是否有效
        
        Returns:
            bool: 连接是否有效
        """
        pass
    
    @abstractmethod
    async def get_schema(self, refresh: bool = False) -> Dict[str, Any]:
        """获取数据源结构信息
        
        Args:
            refresh: 是否刷新缓存
            
        Returns:
            Dict[str, Any]: 结构信息
        """
        pass
    
    @abstractmethod
    async def query(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> pl.DataFrame:
        """执行查询并返回DataFrame
        
        Args:
            query: 查询条件，格式依数据源而定
            options: 查询选项
            
        Returns:
            pl.DataFrame: 查询结果
            
        Raises:
            QueryError: 查询执行失败
        """
        pass
    
    @abstractmethod
    async def query_stream(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> Iterator[pl.DataFrame]:
        """流式查询，返回DataFrame迭代器
        
        Args:
            query: 查询条件
            options: 查询选项
            
        Yields:
            pl.DataFrame: 数据块
            
        Raises:
            QueryError: 查询执行失败
        """
        pass
    
    async def get_row_count(self, query: Optional[Dict[str, Any]] = None) -> int:
        """获取行数
        
        Args:
            query: 查询条件，为None时返回总行数
            
        Returns:
            int: 行数
        """
        # 默认实现，子类可重写以优化性能
        try:
            df = await self.query(query, QueryOptions(limit=0))
            return len(df)
        except Exception as e:
            self._logger.error(f"Failed to get row count: {e}")
            return 0
    
    async def get_column_count(self) -> int:
        """获取列数
        
        Returns:
            int: 列数
        """
        try:
            schema = await self.get_schema()
            return len(schema.get('columns', {}))
        except Exception as e:
            self._logger.error(f"Failed to get column count: {e}")
            return 0
    
    async def preview_data(self, limit: int = 100) -> pl.DataFrame:
        """预览数据
        
        Args:
            limit: 预览行数
            
        Returns:
            pl.DataFrame: 预览数据
        """
        options = QueryOptions(limit=limit, memory_optimized=True)
        return await self.query(options=options)
    
    @contextmanager
    def memory_protected_operation(self, operation_name: str, estimated_bytes: Optional[int] = None):
        """内存保护操作上下文管理器"""
        with memory_guard.memory_guard(
            operation_name=f"{self.source_id}_{operation_name}",
            estimated_bytes=estimated_bytes
        ) as stats:
            yield stats
    
    def _validate_connection(self) -> None:
        """验证连接状态"""
        if self.connection_status != ConnectionStatus.CONNECTED:
            raise ConnectionError(f"Data source {self.source_id} is not connected")
    
    def _update_access_time(self) -> None:
        """更新最后访问时间"""
        self.info.last_accessed = time.time()
    
    def _log_operation(self, operation: str, duration: float, rows: int = 0) -> None:
        """记录操作日志"""
        if config.performance.log_slow_operations and duration > 1.0:
            self._logger.info(
                f"Operation {operation} took {duration:.2f}s, processed {rows} rows"
            )
    
    async def get_info(self) -> DataSourceInfo:
        """获取数据源信息"""
        # 更新统计信息
        if self.connection_status == ConnectionStatus.CONNECTED:
            try:
                schema = await self.get_schema()
                self.info.schema = schema
                self.info.column_count = len(schema.get('columns', {}))
                
                # 尝试获取行数（可能比较慢，所以设置较短超时）
                if self.info.row_count is None:
                    self.info.row_count = await self.get_row_count()
            except Exception as e:
                self._logger.debug(f"Failed to update info: {e}")
        
        return self.info
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.source_id}, type={self.source_type.value}, status={self.connection_status.value})"


class DataSourceError(Exception):
    """数据源错误基类"""
    def __init__(self, message: str, source_id: str, source_type: DataSourceType):
        self.message = message
        self.source_id = source_id
        self.source_type = source_type
        super().__init__(f"{source_type.value}://{source_id}: {message}")


class ConnectionError(DataSourceError):
    """连接错误"""
    pass


class QueryError(DataSourceError):
    """查询错误"""
    pass


class SchemaError(DataSourceError):
    """结构错误"""
    pass