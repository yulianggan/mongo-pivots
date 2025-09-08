"""
DataSourceRegistry - 数据源注册和管理系统
支持最多6个数据源同时连接，提供连接池管理和资源清理
"""
import asyncio
import threading
import time
from typing import Dict, List, Optional, Set, Any, Type
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import logging
from collections import defaultdict

from .base import (
    DataSourceConnector, 
    DataSourceType, 
    ConnectionStatus, 
    DataSourceInfo,
    DataSourceError,
    ConnectionError
)
from core.memory_guard import memory_guard
from core.config import config


@dataclass
class RegistryStats:
    """注册表统计信息"""
    total_sources: int = 0
    connected_sources: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    memory_usage_mb: float = 0.0
    last_cleanup_time: float = field(default_factory=time.time)


class DataSourceRegistry:
    """数据源注册表管理器"""
    
    MAX_CONNECTIONS = 6  # 最大同时连接数
    CLEANUP_INTERVAL = 300  # 清理间隔（秒）
    CONNECTION_TIMEOUT = 30  # 连接超时（秒）
    
    def __init__(self):
        self._sources: Dict[str, DataSourceConnector] = {}
        self._connector_types: Dict[DataSourceType, Type[DataSourceConnector]] = {}
        self._stats = RegistryStats()
        self._lock = threading.RLock()
        self._async_lock = asyncio.Lock()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._cleanup_task: Optional[asyncio.Task] = None
        self._active_operations: Dict[str, int] = defaultdict(int)
        
        # 启动定期清理任务
        self._start_cleanup_task()
    
    def register_connector_type(
        self, 
        source_type: DataSourceType, 
        connector_class: Type[DataSourceConnector]
    ) -> None:
        """注册连接器类型
        
        Args:
            source_type: 数据源类型
            connector_class: 连接器类
        """
        with self._lock:
            self._connector_types[source_type] = connector_class
            self._logger.info(f"Registered connector type: {source_type.value} -> {connector_class.__name__}")
    
    async def register_source(
        self, 
        source_id: str,
        source_type: DataSourceType,
        **connection_params
    ) -> DataSourceConnector:
        """注册新的数据源
        
        Args:
            source_id: 数据源ID
            source_type: 数据源类型
            **connection_params: 连接参数
            
        Returns:
            DataSourceConnector: 创建的连接器实例
            
        Raises:
            ValueError: 参数错误
            ConnectionError: 连接失败
        """
        async with self._async_lock:
            # 检查源ID是否已存在
            if source_id in self._sources:
                raise ValueError(f"Data source {source_id} already registered")
            
            # 检查连接数限制
            if len(self._sources) >= self.MAX_CONNECTIONS:
                raise ConnectionError(
                    f"Maximum connections ({self.MAX_CONNECTIONS}) reached",
                    source_id,
                    source_type
                )
            
            # 检查连接器类型是否已注册
            if source_type not in self._connector_types:
                raise ValueError(f"Connector type {source_type.value} not registered")
            
            try:
                # 创建连接器实例
                connector_class = self._connector_types[source_type]
                connector = connector_class(source_id, source_type, **connection_params)
                
                # 添加到注册表
                self._sources[source_id] = connector
                self._stats.total_sources += 1
                
                self._logger.info(f"Registered data source: {source_id} ({source_type.value})")
                return connector
                
            except Exception as e:
                self._logger.error(f"Failed to register source {source_id}: {e}")
                raise ConnectionError(str(e), source_id, source_type)
    
    async def connect_source(self, source_id: str) -> bool:
        """连接数据源
        
        Args:
            source_id: 数据源ID
            
        Returns:
            bool: 连接是否成功
            
        Raises:
            ValueError: 数据源不存在
            ConnectionError: 连接失败
        """
        connector = self.get_source(source_id)
        if not connector:
            raise ValueError(f"Data source {source_id} not found")
        
        try:
            # 使用超时保护
            success = await asyncio.wait_for(
                connector.connect(), 
                timeout=self.CONNECTION_TIMEOUT
            )
            
            if success:
                self._stats.connected_sources += 1
                self._stats.active_connections += 1
                self._logger.info(f"Connected to data source: {source_id}")
            else:
                self._stats.failed_connections += 1
                self._logger.warning(f"Failed to connect to data source: {source_id}")
            
            return success
            
        except asyncio.TimeoutError:
            self._logger.error(f"Connection timeout for data source: {source_id}")
            self._stats.failed_connections += 1
            raise ConnectionError(f"Connection timeout", source_id, connector.source_type)
        except Exception as e:
            self._logger.error(f"Connection error for {source_id}: {e}")
            self._stats.failed_connections += 1
            raise ConnectionError(str(e), source_id, connector.source_type)
    
    async def disconnect_source(self, source_id: str) -> None:
        """断开数据源连接
        
        Args:
            source_id: 数据源ID
        """
        connector = self.get_source(source_id)
        if not connector:
            return
        
        try:
            if connector.connection_status == ConnectionStatus.CONNECTED:
                await connector.close()
                self._stats.active_connections -= 1
                self._logger.info(f"Disconnected data source: {source_id}")
        except Exception as e:
            self._logger.error(f"Error disconnecting {source_id}: {e}")
    
    async def unregister_source(self, source_id: str) -> None:
        """注销数据源
        
        Args:
            source_id: 数据源ID
        """
        async with self._async_lock:
            if source_id not in self._sources:
                return
            
            # 先断开连接
            await self.disconnect_source(source_id)
            
            # 从注册表移除
            del self._sources[source_id]
            self._stats.total_sources -= 1
            
            self._logger.info(f"Unregistered data source: {source_id}")
    
    def get_source(self, source_id: str) -> Optional[DataSourceConnector]:
        """获取数据源连接器
        
        Args:
            source_id: 数据源ID
            
        Returns:
            Optional[DataSourceConnector]: 连接器实例，不存在时返回None
        """
        with self._lock:
            return self._sources.get(source_id)
    
    def list_sources(
        self, 
        source_type: Optional[DataSourceType] = None,
        status: Optional[ConnectionStatus] = None
    ) -> List[DataSourceConnector]:
        """列出数据源
        
        Args:
            source_type: 过滤数据源类型，None表示所有类型
            status: 过滤连接状态，None表示所有状态
            
        Returns:
            List[DataSourceConnector]: 数据源连接器列表
        """
        with self._lock:
            sources = list(self._sources.values())
            
            if source_type is not None:
                sources = [s for s in sources if s.source_type == source_type]
            
            if status is not None:
                sources = [s for s in sources if s.connection_status == status]
            
            return sources
    
    def get_source_ids(self) -> Set[str]:
        """获取所有数据源ID
        
        Returns:
            Set[str]: 数据源ID集合
        """
        with self._lock:
            return set(self._sources.keys())
    
    async def test_all_connections(self) -> Dict[str, bool]:
        """测试所有连接
        
        Returns:
            Dict[str, bool]: 各数据源的连接测试结果
        """
        results = {}
        
        async def test_source(source_id: str, connector: DataSourceConnector):
            try:
                results[source_id] = await connector.test_connection()
            except Exception as e:
                self._logger.error(f"Connection test failed for {source_id}: {e}")
                results[source_id] = False
        
        # 并发测试所有连接
        tasks = [
            test_source(source_id, connector)
            for source_id, connector in self._sources.items()
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return results
    
    async def cleanup_stale_connections(self) -> int:
        """清理失效连接
        
        Returns:
            int: 清理的连接数
        """
        cleaned = 0
        
        # 测试所有连接
        test_results = await self.test_all_connections()
        
        # 清理失效连接
        stale_sources = [
            source_id for source_id, is_valid in test_results.items()
            if not is_valid
        ]
        
        for source_id in stale_sources:
            try:
                await self.disconnect_source(source_id)
                cleaned += 1
                self._logger.info(f"Cleaned stale connection: {source_id}")
            except Exception as e:
                self._logger.error(f"Error cleaning {source_id}: {e}")
        
        # 强制垃圾回收
        if cleaned > 0:
            memory_guard.force_gc()
        
        self._stats.last_cleanup_time = time.time()
        return cleaned
    
    @asynccontextmanager
    async def acquire_source(self, source_id: str):
        """获取数据源的独占使用权
        
        Args:
            source_id: 数据源ID
            
        Yields:
            DataSourceConnector: 数据源连接器
            
        Raises:
            ValueError: 数据源不存在
            ConnectionError: 连接无效
        """
        connector = self.get_source(source_id)
        if not connector:
            raise ValueError(f"Data source {source_id} not found")
        
        if connector.connection_status != ConnectionStatus.CONNECTED:
            raise ConnectionError("Data source not connected", source_id, connector.source_type)
        
        # 增加活动操作计数
        self._active_operations[source_id] += 1
        
        try:
            yield connector
        finally:
            # 减少活动操作计数
            self._active_operations[source_id] -= 1
            if self._active_operations[source_id] <= 0:
                del self._active_operations[source_id]
    
    async def get_registry_info(self) -> Dict[str, Any]:
        """获取注册表信息
        
        Returns:
            Dict[str, Any]: 注册表状态信息
        """
        # 更新统计信息
        self._update_stats()
        
        source_info = {}
        for source_id, connector in self._sources.items():
            info = await connector.get_info()
            source_info[source_id] = {
                'type': connector.source_type.value,
                'status': connector.connection_status.value,
                'info': info,
                'active_operations': self._active_operations.get(source_id, 0)
            }
        
        return {
            'stats': {
                'total_sources': self._stats.total_sources,
                'connected_sources': self._stats.connected_sources,
                'active_connections': self._stats.active_connections,
                'failed_connections': self._stats.failed_connections,
                'memory_usage_mb': self._stats.memory_usage_mb,
                'last_cleanup_time': self._stats.last_cleanup_time
            },
            'sources': source_info,
            'registered_types': [t.value for t in self._connector_types.keys()],
            'limits': {
                'max_connections': self.MAX_CONNECTIONS,
                'current_connections': len(self._sources)
            }
        }
    
    def _update_stats(self) -> None:
        """更新统计信息"""
        connected_count = sum(
            1 for connector in self._sources.values()
            if connector.connection_status == ConnectionStatus.CONNECTED
        )
        self._stats.connected_sources = connected_count
        self._stats.active_connections = connected_count
        
        # 获取内存使用信息
        memory_stats = memory_guard.get_memory_stats()
        self._stats.memory_usage_mb = memory_stats.rss_bytes / 1024 / 1024
    
    def _start_cleanup_task(self) -> None:
        """启动定期清理任务"""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(self.CLEANUP_INTERVAL)
                    cleaned = await self.cleanup_stale_connections()
                    if cleaned > 0:
                        self._logger.info(f"Cleanup completed, removed {cleaned} stale connections")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self._logger.error(f"Cleanup task error: {e}")
        
        # 创建后台任务
        loop = asyncio.get_event_loop()
        self._cleanup_task = loop.create_task(cleanup_loop())
    
    async def shutdown(self) -> None:
        """关闭注册表"""
        self._logger.info("Shutting down registry...")
        
        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 断开所有连接
        disconnect_tasks = [
            self.disconnect_source(source_id)
            for source_id in list(self._sources.keys())
        ]
        
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
        
        # 清空注册表
        self._sources.clear()
        self._stats = RegistryStats()
        
        self._logger.info("Registry shutdown completed")
    
    def __len__(self) -> int:
        """返回注册的数据源数量"""
        return len(self._sources)
    
    def __contains__(self, source_id: str) -> bool:
        """检查数据源是否已注册"""
        return source_id in self._sources
    
    def __repr__(self) -> str:
        return f"DataSourceRegistry(sources={len(self._sources)}, connected={self._stats.connected_sources})"


# 全局注册表实例
registry = DataSourceRegistry()