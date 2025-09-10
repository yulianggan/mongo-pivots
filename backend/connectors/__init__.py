"""
Connectors - 数据源连接器模块
提供统一的数据源抽象接口和注册管理
"""

from .base import (
    DataSourceConnector,
    DataSourceType,
    ConnectionStatus,
    DataSourceInfo,
    QueryOptions,
    DataSourceError,
    ConnectionError as ConnectorConnectionError,  # 避免与内置异常冲突
    QueryError,
    SchemaError
)

from .registry import (
    DataSourceRegistry,
    RegistryStats,
    registry
)

# 导入具体连接器实现（触发装饰器注册）
from . import mongo_connector

# 导出主要接口
__all__ = [
    # 基类和类型
    'DataSourceConnector',
    'DataSourceType', 
    'ConnectionStatus',
    'DataSourceInfo',
    'QueryOptions',
    
    # 异常类
    'DataSourceError',
    'ConnectorConnectionError',
    'QueryError', 
    'SchemaError',
    
    # 注册表
    'DataSourceRegistry',
    'RegistryStats',
    'registry',  # 全局注册表实例
    
    # 装饰器
    'connector_type',
]


def get_registry() -> DataSourceRegistry:
    """获取全局数据源注册表实例
    
    Returns:
        DataSourceRegistry: 全局注册表实例
    """
    return registry


def register_connector_type(source_type: DataSourceType, connector_class):
    """注册连接器类型到全局注册表
    
    Args:
        source_type: 数据源类型
        connector_class: 连接器类
    """
    registry.register_connector_type(source_type, connector_class)


async def create_source(
    source_id: str,
    source_type: DataSourceType,
    auto_connect: bool = True,
    **connection_params
) -> DataSourceConnector:
    """创建并注册数据源
    
    Args:
        source_id: 数据源唯一ID
        source_type: 数据源类型
        auto_connect: 是否自动连接
        **connection_params: 连接参数
        
    Returns:
        DataSourceConnector: 创建的连接器实例
        
    Raises:
        ValueError: 参数错误
        ConnectorConnectionError: 连接失败
    """
    # 注册数据源
    connector = await registry.register_source(
        source_id=source_id,
        source_type=source_type,
        **connection_params
    )
    
    # 自动连接
    if auto_connect:
        await registry.connect_source(source_id)
    
    return connector


async def get_source(source_id: str) -> DataSourceConnector:
    """获取已注册的数据源
    
    Args:
        source_id: 数据源ID
        
    Returns:
        DataSourceConnector: 连接器实例
        
    Raises:
        ValueError: 数据源不存在
    """
    connector = registry.get_source(source_id)
    if not connector:
        raise ValueError(f"Data source '{source_id}' not found")
    
    return connector


async def remove_source(source_id: str) -> None:
    """移除数据源
    
    Args:
        source_id: 数据源ID
    """
    await registry.unregister_source(source_id)


def list_sources(
    source_type: DataSourceType = None,
    status: ConnectionStatus = None
) -> list:
    """列出数据源
    
    Args:
        source_type: 过滤数据源类型
        status: 过滤连接状态
        
    Returns:
        list: 数据源连接器列表
    """
    return registry.list_sources(source_type=source_type, status=status)


async def get_registry_info() -> dict:
    """获取注册表状态信息
    
    Returns:
        dict: 注册表状态信息
    """
    return await registry.get_registry_info()


async def shutdown_all() -> None:
    """关闭所有连接和注册表
    
    用于应用程序关闭时的清理工作
    """
    await registry.shutdown()


# 连接器类型注册装饰器
def connector_type(source_type: DataSourceType):
    """连接器类型注册装饰器
    
    Usage:
        @connector_type(DataSourceType.CSV)
        class CSVConnector(DataSourceConnector):
            pass
    """
    def decorator(cls):
        register_connector_type(source_type, cls)
        return cls
    
    return decorator