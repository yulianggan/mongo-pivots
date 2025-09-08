"""
测试数据源连接器基础架构
验证抽象基类和注册系统的接口设计
"""
import pytest
import asyncio
import polars as pl
from typing import Dict, Any, Iterator, Optional
from unittest.mock import Mock, patch

from connectors.base import (
    DataSourceConnector, 
    DataSourceType, 
    ConnectionStatus, 
    QueryOptions,
    DataSourceInfo,
    DataSourceError,
    ConnectionError,
    QueryError
)
from connectors.registry import DataSourceRegistry, RegistryStats
from connectors import registry, create_source, get_source, list_sources


class MockConnector(DataSourceConnector):
    """模拟连接器用于测试"""
    
    def __init__(self, source_id: str, source_type: DataSourceType, **connection_params):
        super().__init__(source_id, source_type, **connection_params)
        self._test_data = None
        self._should_fail_connect = connection_params.get('should_fail_connect', False)
        
    async def connect(self) -> bool:
        """模拟连接"""
        if self._should_fail_connect:
            self.connection_status = ConnectionStatus.ERROR
            raise ConnectionError("Mock connection failed", self.source_id, self.source_type)
        
        self.connection_status = ConnectionStatus.CONNECTED
        self._connection = Mock()
        
        # 设置测试数据
        self._test_data = pl.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eva'],
            'age': [25, 30, 35, 40, 45],
            'city': ['New York', 'London', 'Tokyo', 'Paris', 'Sydney']
        })
        
        return True
    
    async def close(self) -> None:
        """关闭连接"""
        self.connection_status = ConnectionStatus.CLOSED
        self._connection = None
    
    async def test_connection(self) -> bool:
        """测试连接"""
        return self.connection_status == ConnectionStatus.CONNECTED
    
    async def get_schema(self, refresh: bool = False) -> Dict[str, Any]:
        """获取结构"""
        if self._test_data is None:
            raise QueryError("No test data available", self.source_id, self.source_type)
        
        return {
            'columns': {
                'id': {'type': 'integer', 'nullable': False},
                'name': {'type': 'string', 'nullable': False},
                'age': {'type': 'integer', 'nullable': False},
                'city': {'type': 'string', 'nullable': False}
            },
            'row_count': len(self._test_data),
            'column_count': len(self._test_data.columns)
        }
    
    async def query(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> pl.DataFrame:
        """执行查询"""
        self._validate_connection()
        self._update_access_time()
        
        if self._test_data is None:
            raise QueryError("No test data available", self.source_id, self.source_type)
        
        df = self._test_data
        
        # 应用查询选项
        if options:
            if options.filters:
                # 简单过滤实现
                for field, value in options.filters.items():
                    if field in df.columns:
                        df = df.filter(pl.col(field) == value)
            
            if options.projection:
                selected_cols = [col for col, include in options.projection.items() if include and col in df.columns]
                if selected_cols:
                    df = df.select(selected_cols)
            
            if options.limit:
                df = df.head(options.limit)
        
        return df
    
    async def query_stream(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> Iterator[pl.DataFrame]:
        """流式查询"""
        self._validate_connection()
        self._update_access_time()
        
        batch_size = options.batch_size if options else 1000
        df = await self.query(query, options)
        
        # 分批返回
        for i in range(0, len(df), batch_size):
            yield df.slice(i, batch_size)


class TestDataSourceConnector:
    """测试数据源连接器基类"""
    
    @pytest.fixture
    def mock_connector(self):
        """创建模拟连接器"""
        return MockConnector("test_source", DataSourceType.CSV, host="localhost")
    
    def test_connector_initialization(self, mock_connector):
        """测试连接器初始化"""
        assert mock_connector.source_id == "test_source"
        assert mock_connector.source_type == DataSourceType.CSV
        assert mock_connector.connection_status == ConnectionStatus.DISCONNECTED
        assert mock_connector.connection_params == {"host": "localhost"}
        assert isinstance(mock_connector.info, DataSourceInfo)
    
    @pytest.mark.asyncio
    async def test_successful_connection(self, mock_connector):
        """测试成功连接"""
        success = await mock_connector.connect()
        assert success is True
        assert mock_connector.connection_status == ConnectionStatus.CONNECTED
        assert await mock_connector.test_connection() is True
    
    @pytest.mark.asyncio
    async def test_failed_connection(self):
        """测试连接失败"""
        connector = MockConnector("fail_source", DataSourceType.CSV, should_fail_connect=True)
        
        with pytest.raises(ConnectionError):
            await connector.connect()
        
        assert connector.connection_status == ConnectionStatus.ERROR
    
    @pytest.mark.asyncio
    async def test_query_operations(self, mock_connector):
        """测试查询操作"""
        # 先连接
        await mock_connector.connect()
        
        # 基本查询
        df = await mock_connector.query()
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 5
        assert list(df.columns) == ['id', 'name', 'age', 'city']
        
        # 带过滤的查询
        options = QueryOptions(filters={'age': 30})
        filtered_df = await mock_connector.query(options=options)
        assert len(filtered_df) == 1
        assert filtered_df['name'][0] == 'Bob'
        
        # 带投影的查询
        options = QueryOptions(projection={'id': 1, 'name': 1})
        projected_df = await mock_connector.query(options=options)
        assert list(projected_df.columns) == ['id', 'name']
        
        # 带限制的查询
        options = QueryOptions(limit=3)
        limited_df = await mock_connector.query(options=options)
        assert len(limited_df) == 3
    
    @pytest.mark.asyncio
    async def test_stream_query(self, mock_connector):
        """测试流式查询"""
        await mock_connector.connect()
        
        options = QueryOptions(batch_size=2)
        chunks = []
        
        async for chunk in mock_connector.query_stream(options=options):
            chunks.append(chunk)
        
        assert len(chunks) == 3  # 5 rows with batch_size=2: 2+2+1
        assert len(chunks[0]) == 2
        assert len(chunks[1]) == 2
        assert len(chunks[2]) == 1
    
    @pytest.mark.asyncio
    async def test_schema_operations(self, mock_connector):
        """测试结构操作"""
        await mock_connector.connect()
        
        schema = await mock_connector.get_schema()
        assert 'columns' in schema
        assert 'row_count' in schema
        assert 'column_count' in schema
        assert len(schema['columns']) == 4
        
        # 测试行数和列数
        row_count = await mock_connector.get_row_count()
        assert row_count == 5
        
        col_count = await mock_connector.get_column_count()
        assert col_count == 4
    
    @pytest.mark.asyncio
    async def test_preview_data(self, mock_connector):
        """测试数据预览"""
        await mock_connector.connect()
        
        preview_df = await mock_connector.preview_data(limit=3)
        assert len(preview_df) == 3
        assert list(preview_df.columns) == ['id', 'name', 'age', 'city']
    
    @pytest.mark.asyncio
    async def test_connection_validation(self, mock_connector):
        """测试连接验证"""
        # 未连接状态下执行查询应该失败
        with pytest.raises(ConnectionError):
            await mock_connector.query()
    
    @pytest.mark.asyncio
    async def test_info_retrieval(self, mock_connector):
        """测试信息获取"""
        info = await mock_connector.get_info()
        assert info.source_id == "test_source"
        assert info.source_type == DataSourceType.CSV
        assert info.connection_params == {"host": "localhost"}
        
        # 连接后信息应该更完整
        await mock_connector.connect()
        updated_info = await mock_connector.get_info()
        assert updated_info.schema is not None
        assert updated_info.row_count == 5
        assert updated_info.column_count == 4


class TestDataSourceRegistry:
    """测试数据源注册表"""
    
    @pytest.fixture
    def test_registry(self):
        """创建测试注册表"""
        test_reg = DataSourceRegistry()
        test_reg.register_connector_type(DataSourceType.CSV, MockConnector)
        return test_reg
    
    @pytest.mark.asyncio
    async def test_register_connector_type(self, test_registry):
        """测试连接器类型注册"""
        test_registry.register_connector_type(DataSourceType.JSON, MockConnector)
        assert DataSourceType.JSON in test_registry._connector_types
    
    @pytest.mark.asyncio
    async def test_register_source(self, test_registry):
        """测试数据源注册"""
        connector = await test_registry.register_source(
            "test_source", 
            DataSourceType.CSV,
            host="localhost"
        )
        
        assert isinstance(connector, MockConnector)
        assert connector.source_id == "test_source"
        assert len(test_registry) == 1
        assert "test_source" in test_registry
    
    @pytest.mark.asyncio
    async def test_duplicate_registration(self, test_registry):
        """测试重复注册"""
        await test_registry.register_source("test_source", DataSourceType.CSV)
        
        with pytest.raises(ValueError, match="already registered"):
            await test_registry.register_source("test_source", DataSourceType.CSV)
    
    @pytest.mark.asyncio
    async def test_connection_limit(self, test_registry):
        """测试连接数限制"""
        # 注册最大数量的连接
        for i in range(DataSourceRegistry.MAX_CONNECTIONS):
            await test_registry.register_source(f"source_{i}", DataSourceType.CSV)
        
        # 超过限制应该失败
        with pytest.raises(ConnectionError, match="Maximum connections"):
            await test_registry.register_source("over_limit", DataSourceType.CSV)
    
    @pytest.mark.asyncio
    async def test_connect_source(self, test_registry):
        """测试数据源连接"""
        connector = await test_registry.register_source("test_source", DataSourceType.CSV)
        
        success = await test_registry.connect_source("test_source")
        assert success is True
        assert connector.connection_status == ConnectionStatus.CONNECTED
    
    @pytest.mark.asyncio
    async def test_source_operations(self, test_registry):
        """测试数据源操作"""
        # 注册并连接多个数据源
        await test_registry.register_source("csv_source", DataSourceType.CSV)
        await test_registry.register_source("json_source", DataSourceType.CSV)  # 使用CSV类型作为测试
        
        await test_registry.connect_source("csv_source")
        
        # 获取数据源
        source = test_registry.get_source("csv_source")
        assert source is not None
        assert source.source_id == "csv_source"
        
        # 列出数据源
        all_sources = test_registry.list_sources()
        assert len(all_sources) == 2
        
        connected_sources = test_registry.list_sources(status=ConnectionStatus.CONNECTED)
        assert len(connected_sources) == 1
        
        # 获取源ID
        source_ids = test_registry.get_source_ids()
        assert "csv_source" in source_ids
        assert "json_source" in source_ids
    
    @pytest.mark.asyncio
    async def test_acquire_source_context(self, test_registry):
        """测试数据源独占使用"""
        connector = await test_registry.register_source("test_source", DataSourceType.CSV)
        await test_registry.connect_source("test_source")
        
        async with test_registry.acquire_source("test_source") as source:
            assert source is connector
            assert test_registry._active_operations["test_source"] == 1
        
        # 退出上下文后操作计数应该清零
        assert test_registry._active_operations.get("test_source", 0) == 0
    
    @pytest.mark.asyncio
    async def test_registry_info(self, test_registry):
        """测试注册表信息"""
        await test_registry.register_source("test_source", DataSourceType.CSV)
        await test_registry.connect_source("test_source")
        
        info = await test_registry.get_registry_info()
        
        assert 'stats' in info
        assert 'sources' in info
        assert 'registered_types' in info
        assert 'limits' in info
        
        assert info['stats']['total_sources'] == 1
        assert info['stats']['connected_sources'] == 1
        assert info['limits']['max_connections'] == DataSourceRegistry.MAX_CONNECTIONS
    
    @pytest.mark.asyncio
    async def test_cleanup_operations(self, test_registry):
        """测试清理操作"""
        connector = await test_registry.register_source("test_source", DataSourceType.CSV)
        await test_registry.connect_source("test_source")
        
        # 断开连接
        await test_registry.disconnect_source("test_source")
        assert connector.connection_status == ConnectionStatus.CLOSED
        
        # 注销数据源
        await test_registry.unregister_source("test_source")
        assert len(test_registry) == 0
        assert "test_source" not in test_registry


class TestConnectorsModule:
    """测试连接器模块接口"""
    
    @pytest.fixture(autouse=True)
    async def setup_registry(self):
        """设置测试注册表"""
        # 注册模拟连接器类型
        registry.register_connector_type(DataSourceType.CSV, MockConnector)
        yield
        # 清理
        await registry.shutdown()
    
    @pytest.mark.asyncio
    async def test_create_source(self):
        """测试创建数据源"""
        connector = await create_source(
            source_id="test_csv",
            source_type=DataSourceType.CSV,
            auto_connect=True,
            host="localhost"
        )
        
        assert connector.source_id == "test_csv"
        assert connector.connection_status == ConnectionStatus.CONNECTED
    
    @pytest.mark.asyncio
    async def test_get_source(self):
        """测试获取数据源"""
        # 先创建
        await create_source("test_csv", DataSourceType.CSV, auto_connect=False)
        
        # 再获取
        connector = await get_source("test_csv")
        assert connector.source_id == "test_csv"
        
        # 获取不存在的源应该失败
        with pytest.raises(ValueError, match="not found"):
            await get_source("nonexistent")
    
    @pytest.mark.asyncio 
    async def test_list_sources(self):
        """测试列出数据源"""
        await create_source("csv1", DataSourceType.CSV, auto_connect=True)
        await create_source("csv2", DataSourceType.CSV, auto_connect=False)
        
        all_sources = list_sources()
        assert len(all_sources) == 2
        
        connected_sources = list_sources(status=ConnectionStatus.CONNECTED)
        assert len(connected_sources) == 1
        
        csv_sources = list_sources(source_type=DataSourceType.CSV)
        assert len(csv_sources) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])