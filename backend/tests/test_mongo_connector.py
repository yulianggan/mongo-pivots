"""
MongoDB 连接器测试套件
包含连接、查询、性能和错误处理的全面测试
"""
import pytest
import asyncio
import time
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import polars as pl
from bson import ObjectId, Decimal128
from datetime import datetime, timedelta
import pymongo
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure

from connectors.mongo_connector import (
    MongoConnector,
    MongoConnectionParams,
    AggregationOptimizer,
    BatchReader,
    SchemaDetector,
    AggregationStats
)
from connectors.base import (
    DataSourceType,
    ConnectionStatus,
    QueryOptions,
    ConnectionError,
    QueryError,
    SchemaError
)


class TestMongoConnectionParams:
    """测试 MongoDB 连接参数"""
    
    def test_default_params(self):
        """测试默认参数"""
        params = MongoConnectionParams(database="test_db", collection="test_coll")
        
        assert params.host == "localhost"
        assert params.port == 27017
        assert params.database == "test_db"
        assert params.collection == "test_coll"
        assert params.username is None
        assert params.password is None
        assert params.ssl is False
        assert params.connection_timeout_ms == 30000
    
    def test_custom_params(self):
        """测试自定义参数"""
        params = MongoConnectionParams(
            host="custom-host",
            port=27018,
            database="custom_db",
            collection="custom_coll",
            username="user",
            password="pass",
            ssl=True,
            connection_timeout_ms=60000
        )
        
        assert params.host == "custom-host"
        assert params.port == 27018
        assert params.username == "user"
        assert params.password == "pass"
        assert params.ssl is True
        assert params.connection_timeout_ms == 60000


class TestAggregationOptimizer:
    """测试聚合管道优化器"""
    
    def setup_method(self):
        """设置测试环境"""
        self.mock_collection = Mock()
        self.mock_collection.list_indexes.return_value = [
            {"key": {"field1": 1}},
            {"key": {"field2": -1, "field3": 1}}
        ]
        self.optimizer = AggregationOptimizer(self.mock_collection)
    
    def test_basic_pipeline_optimization(self):
        """测试基本管道优化"""
        base_pipeline = []
        options = QueryOptions(
            filters={"field1": "value1", "field2": {"$gt": 100}},
            projection={"field1": 1, "field2": 1, "_id": 0},
            sort={"field1": 1},
            skip=10,
            limit=100
        )
        
        optimized_pipeline, stats = self.optimizer.optimize_pipeline(base_pipeline, options)
        
        # 验证管道结构
        assert len(optimized_pipeline) > len(base_pipeline)
        
        # 验证 $match 阶段存在且在前面
        match_stages = [stage for stage in optimized_pipeline if "$match" in stage]
        assert len(match_stages) >= 1
        
        # 验证 $project 阶段
        project_stages = [stage for stage in optimized_pipeline if "$project" in stage]
        assert len(project_stages) == 1
        assert project_stages[0]["$project"]["field1"] == 1
        
        # 验证 $sort 阶段
        sort_stages = [stage for stage in optimized_pipeline if "$sort" in stage]
        assert len(sort_stages) == 1
        
        # 验证 $skip 和 $limit 阶段
        skip_stages = [stage for stage in optimized_pipeline if "$skip" in stage]
        limit_stages = [stage for stage in optimized_pipeline if "$limit" in stage]
        assert len(skip_stages) == 1
        assert len(limit_stages) == 1
        
        # 验证统计信息
        assert isinstance(stats, AggregationStats)
        assert stats.optimized_stages > 0
    
    def test_index_optimization(self):
        """测试索引优化"""
        base_pipeline = []
        options = QueryOptions(
            filters={
                "field1": "indexed_value",  # 有索引
                "field4": "non_indexed_value"  # 无索引
            }
        )
        
        optimized_pipeline, _ = self.optimizer.optimize_pipeline(base_pipeline, options)
        
        # 验证索引字段的 $match 在前
        match_stages = [stage for stage in optimized_pipeline if "$match" in stage]
        
        # 应该有两个 $match 阶段：有索引的字段在前
        assert len(match_stages) >= 1
        first_match = match_stages[0]["$match"]
        
        # 验证有索引的字段在第一个 $match 中
        if len(match_stages) > 1:
            assert "field1" in first_match
    
    def test_empty_options(self):
        """测试空选项"""
        base_pipeline = [{"$match": {"existing": "condition"}}]
        options = QueryOptions()
        
        optimized_pipeline, stats = self.optimizer.optimize_pipeline(base_pipeline, options)
        
        # 基本管道应该保持不变
        assert len(optimized_pipeline) >= len(base_pipeline)
        assert optimized_pipeline[0] == base_pipeline[0]
    
    def test_projection_with_id_handling(self):
        """测试投影中的 _id 字段处理"""
        base_pipeline = []
        
        # 不包含 _id 的投影
        options1 = QueryOptions(projection={"field1": 1, "field2": 1})
        optimized1, _ = self.optimizer.optimize_pipeline(base_pipeline, options1)
        
        project_stage1 = next(stage for stage in optimized1 if "$project" in stage)
        assert project_stage1["$project"]["_id"] == 0  # 应该排除 _id
        
        # 包含 _id 的投影
        options2 = QueryOptions(projection={"field1": 1, "_id": 1})
        optimized2, _ = self.optimizer.optimize_pipeline(base_pipeline, options2)
        
        project_stage2 = next(stage for stage in optimized2 if "$project" in stage)
        assert project_stage2["$project"]["_id"] == 1  # 应该包含 _id


class TestBatchReader:
    """测试批量读取器"""
    
    def setup_method(self):
        """设置测试环境"""
        self.mock_collection = Mock()
        self.batch_reader = BatchReader(self.mock_collection, batch_size=10)
    
    @pytest.mark.asyncio
    async def test_single_batch_read(self):
        """测试单批次读取"""
        mock_docs = [{"_id": i, "value": f"doc_{i}"} for i in range(5)]
        
        def mock_aggregate(pipeline, **kwargs):
            return mock_docs
        
        self.mock_collection.aggregate = Mock(side_effect=mock_aggregate)
        
        # 读取数据
        batches = []
        async for batch in self.batch_reader.read_batches([]):
            batches.append(batch)
        
        # 验证结果
        assert len(batches) == 1
        assert len(batches[0]) == 5
        assert batches[0] == mock_docs
    
    @pytest.mark.asyncio
    async def test_multiple_batch_read(self):
        """测试多批次读取"""
        # 模拟 25 个文档，批次大小为 10
        all_docs = [{"_id": i, "value": f"doc_{i}"} for i in range(25)]
        
        def mock_aggregate(pipeline, **kwargs):
            # 根据 $skip 和 $limit 返回相应数据
            skip = 0
            limit = 10
            
            for stage in pipeline:
                if "$skip" in stage:
                    skip = stage["$skip"]
                elif "$limit" in stage:
                    limit = stage["$limit"]
            
            return all_docs[skip:skip + limit]
        
        self.mock_collection.aggregate = Mock(side_effect=mock_aggregate)
        
        # 读取数据
        batches = []
        async for batch in self.batch_reader.read_batches([]):
            batches.append(batch)
        
        # 验证批次数量
        assert len(batches) == 3  # 10 + 10 + 5
        
        # 验证每批次大小
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5
        
        # 验证数据连续性
        all_returned = []
        for batch in batches:
            all_returned.extend(batch)
        
        assert len(all_returned) == 25
        assert all_returned == all_docs
    
    @pytest.mark.asyncio
    async def test_limited_batch_read(self):
        """测试带限制的批次读取"""
        mock_docs = [{"_id": i, "value": f"doc_{i}"} for i in range(100)]
        
        def mock_aggregate(pipeline, **kwargs):
            skip = 0
            limit = 10
            
            for stage in pipeline:
                if "$skip" in stage:
                    skip = stage["$skip"]
                elif "$limit" in stage:
                    limit = stage["$limit"]
            
            return mock_docs[skip:skip + limit]
        
        self.mock_collection.aggregate = Mock(side_effect=mock_aggregate)
        
        # 限制总数为 15
        batches = []
        async for batch in self.batch_reader.read_batches([], total_limit=15):
            batches.append(batch)
        
        # 验证总数限制
        total_docs = sum(len(batch) for batch in batches)
        assert total_docs == 15
        
        # 验证批次结构
        assert len(batches) == 2  # 10 + 5
        assert len(batches[0]) == 10
        assert len(batches[1]) == 5
    
    @pytest.mark.asyncio
    async def test_empty_result_handling(self):
        """测试空结果处理"""
        self.mock_collection.aggregate = Mock(return_value=[])
        
        batches = []
        async for batch in self.batch_reader.read_batches([]):
            batches.append(batch)
        
        # 应该没有批次返回
        assert len(batches) == 0
    
    @pytest.mark.asyncio
    async def test_aggregation_error_handling(self):
        """测试聚合错误处理"""
        self.mock_collection.aggregate = Mock(side_effect=OperationFailure("Test error"))
        
        with pytest.raises(QueryError):
            async for batch in self.batch_reader.read_batches([]):
                pass


class TestSchemaDetector:
    """测试结构检测器"""
    
    def setup_method(self):
        """设置测试环境"""
        self.mock_collection = Mock()
        self.mock_collection.name = "test_collection"
        
        self.mock_database = Mock()
        self.mock_database.name = "test_database"
        self.mock_collection.database = self.mock_database
        
        self.schema_detector = SchemaDetector(self.mock_collection)
    
    @pytest.mark.asyncio
    async def test_basic_schema_detection(self):
        """测试基本结构检测"""
        sample_docs = [
            {
                "_id": ObjectId(),
                "name": "John",
                "age": 30,
                "score": 95.5,
                "active": True,
                "created_at": datetime.now()
            },
            {
                "_id": ObjectId(),
                "name": "Jane",
                "age": 25,
                "score": 87.2,
                "active": False,
                "created_at": datetime.now()
            }
        ]
        
        # 模拟聚合结果
        self.mock_collection.aggregate = Mock(return_value=sample_docs)
        self.mock_collection.estimated_document_count = Mock(return_value=1000)
        
        # 模拟 collStats 命令
        self.mock_database.command = Mock(return_value={"count": 1000})
        
        # 检测结构
        schema = await self.schema_detector.detect_schema(sample_size=100)
        
        # 验证基本信息
        assert schema["document_count"] == 1000
        assert schema["sample_size"] == 2
        assert schema["collection_name"] == "test_collection"
        assert schema["database_name"] == "test_database"
        
        # 验证字段信息
        columns = schema["columns"]
        assert "_id" in columns
        assert "name" in columns
        assert "age" in columns
        assert "score" in columns
        assert "active" in columns
        assert "created_at" in columns
        
        # 验证类型推断
        assert columns["_id"]["type"] == "Utf8"  # ObjectId -> Utf8
        assert columns["name"]["type"] == "Utf8"
        assert columns["age"]["type"] == "Int64"
        assert columns["score"]["type"] == "Float64"
        assert columns["active"]["type"] == "Boolean"
        assert columns["created_at"]["type"] == "Datetime"
    
    @pytest.mark.asyncio
    async def test_nested_document_detection(self):
        """测试嵌套文档检测"""
        sample_docs = [
            {
                "_id": ObjectId(),
                "user": {
                    "name": "John",
                    "email": "john@example.com"
                },
                "settings": {
                    "theme": "dark",
                    "notifications": True
                }
            }
        ]
        
        self.mock_collection.aggregate = Mock(return_value=sample_docs)
        self.mock_collection.estimated_document_count = Mock(return_value=100)
        self.mock_database.command = Mock(return_value={"count": 100})
        
        schema = await self.schema_detector.detect_schema(max_depth=2)
        
        # 验证嵌套字段
        columns = schema["columns"]
        assert "user.name" in columns
        assert "user.email" in columns
        assert "settings.theme" in columns
        assert "settings.notifications" in columns
    
    @pytest.mark.asyncio 
    async def test_mixed_types_detection(self):
        """测试混合类型检测"""
        sample_docs = [
            {"field1": "string_value", "field2": 42},
            {"field1": 123, "field2": None},
            {"field1": "another_string", "field2": 3.14}
        ]
        
        self.mock_collection.aggregate = Mock(return_value=sample_docs)
        self.mock_collection.estimated_document_count = Mock(return_value=100)
        self.mock_database.command = Mock(return_value={"count": 100})
        
        schema = await self.schema_detector.detect_schema()
        
        columns = schema["columns"]
        
        # field1 有 str 和 int 类型，应该选择出现频率高的
        assert "field1" in columns
        field1_info = columns["field1"]
        assert "type_distribution" in field1_info
        
        # field2 有 int, None, float 类型
        assert "field2" in columns
        field2_info = columns["field2"]
        assert field2_info["nullable"] is True
        assert field2_info["null_count"] == 1
    
    @pytest.mark.asyncio
    async def test_special_types_detection(self):
        """测试特殊类型检测"""
        sample_docs = [
            {
                "_id": ObjectId(),
                "decimal_field": Decimal128("123.45"),
                "date_field": datetime.now(),
                "array_field": [1, 2, 3],
                "object_field": {"key": "value"}
            }
        ]
        
        self.mock_collection.aggregate = Mock(return_value=sample_docs)
        self.mock_collection.estimated_document_count = Mock(return_value=100)
        self.mock_database.command = Mock(return_value={"count": 100})
        
        schema = await self.schema_detector.detect_schema()
        
        columns = schema["columns"]
        
        # 验证特殊类型映射
        assert columns["decimal_field"]["mongodb_type"] == "Decimal128"
        assert columns["decimal_field"]["type"] == "Float64"
        
        assert columns["date_field"]["mongodb_type"] == "datetime"
        assert columns["date_field"]["type"] == "Datetime"
        
        assert columns["array_field"]["mongodb_type"] == "list"
        assert columns["object_field"]["mongodb_type"] == "dict"
    
    @pytest.mark.asyncio
    async def test_empty_collection_handling(self):
        """测试空集合处理"""
        self.mock_collection.aggregate = Mock(return_value=[])
        
        schema = await self.schema_detector.detect_schema()
        
        assert schema["columns"] == {}
        assert schema["sample_size"] == 0
    
    @pytest.mark.asyncio
    async def test_detection_error_handling(self):
        """测试检测错误处理"""
        self.mock_collection.aggregate = Mock(side_effect=OperationFailure("Test error"))
        
        with pytest.raises(SchemaError):
            await self.schema_detector.detect_schema()


class TestMongoConnector:
    """测试 MongoDB 连接器"""
    
    def setup_method(self):
        """设置测试环境"""
        self.connection_params = {
            "database": "test_db",
            "collection": "test_collection",
            "host": "localhost",
            "port": 27017
        }
        
        self.connector = MongoConnector(
            "test_source",
            DataSourceType.MONGODB,
            **self.connection_params
        )
    
    def test_initialization(self):
        """测试初始化"""
        assert self.connector.source_id == "test_source"
        assert self.connector.source_type == DataSourceType.MONGODB
        assert self.connector.params.database == "test_db"
        assert self.connector.params.collection == "test_collection"
        assert self.connector.connection_status == ConnectionStatus.DISCONNECTED
    
    def test_connection_uri_building(self):
        """测试连接 URI 构建"""
        # 无认证
        uri1 = self.connector._build_connection_uri()
        expected1 = "mongodb://localhost:27017/test_db"
        assert uri1 == expected1
        
        # 有认证
        connector2 = MongoConnector(
            "test_source2", 
            DataSourceType.MONGODB,
            database="test_db",
            collection="test_coll",
            username="user",
            password="pass",
            host="remote-host",
            port=27018,
            ssl=True
        )
        
        uri2 = connector2._build_connection_uri()
        assert "user:pass@" in uri2
        assert "remote-host:27018" in uri2
        assert "ssl=true" in uri2
    
    @pytest.mark.asyncio
    @patch('pymongo.MongoClient')
    async def test_successful_connection(self, mock_client_class):
        """测试成功连接"""
        # 模拟 MongoDB 客户端
        mock_client = Mock()
        mock_database = Mock()
        mock_collection = Mock()
        
        mock_client.admin.command.return_value = {"ismaster": True}
        mock_client.__getitem__.return_value = mock_database
        mock_database.__getitem__.return_value = mock_collection
        mock_database.list_collection_names.return_value = ["test_collection"]
        
        mock_client_class.return_value = mock_client
        
        # 连接
        success = await self.connector.connect()
        
        # 验证结果
        assert success is True
        assert self.connector.connection_status == ConnectionStatus.CONNECTED
        assert self.connector._client == mock_client
        assert self.connector._collection == mock_collection
        
        # 验证组件初始化
        assert self.connector._optimizer is not None
        assert self.connector._batch_reader is not None
        assert self.connector._schema_detector is not None
    
    @pytest.mark.asyncio
    @patch('pymongo.MongoClient')
    async def test_connection_failure(self, mock_client_class):
        """测试连接失败"""
        mock_client_class.side_effect = ConnectionFailure("Connection failed")
        
        # 连接应该抛出异常
        with pytest.raises(ConnectionError):
            await self.connector.connect()
        
        assert self.connector.connection_status == ConnectionStatus.ERROR
    
    @pytest.mark.asyncio
    @patch('pymongo.MongoClient')
    async def test_connection_timeout(self, mock_client_class):
        """测试连接超时"""
        mock_client_class.side_effect = ServerSelectionTimeoutError("Timeout")
        
        with pytest.raises(ConnectionError):
            await self.connector.connect()
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """测试关闭连接"""
        # 模拟已连接状态
        self.connector._client = Mock()
        self.connector.connection_status = ConnectionStatus.CONNECTED
        
        await self.connector.close()
        
        # 验证清理
        assert self.connector.connection_status == ConnectionStatus.CLOSED
        assert self.connector._client is None
        assert self.connector._optimizer is None
    
    @pytest.mark.asyncio
    async def test_connection_test(self):
        """测试连接测试"""
        # 模拟连接状态
        mock_client = Mock()
        mock_collection = Mock()
        
        mock_client.admin.command.return_value = {"ok": 1}
        mock_collection.find_one.return_value = {"_id": ObjectId()}
        
        self.connector._client = mock_client
        self.connector._collection = mock_collection
        
        # 测试连接
        result = await self.connector.test_connection()
        assert result is True
    
    def test_document_type_conversion(self):
        """测试文档类型转换"""
        doc = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "decimal_field": Decimal128("123.45"),
            "date_field": datetime(2023, 1, 1),
            "nested": {"key": "value"},
            "array": [1, 2, 3],
            "normal_field": "string_value"
        }
        
        converted = self.connector._convert_document_types(doc)
        
        # 验证转换结果
        assert isinstance(converted["_id"], str)
        assert converted["_id"] == "507f1f77bcf86cd799439011"
        
        assert isinstance(converted["decimal_field"], float)
        assert converted["decimal_field"] == 123.45
        
        assert isinstance(converted["date_field"], datetime)
        
        assert isinstance(converted["nested"], str)  # 嵌套对象转为字符串
        assert isinstance(converted["array"], str)   # 数组转为字符串
        
        assert converted["normal_field"] == "string_value"
    
    @pytest.mark.asyncio
    async def test_query_execution(self):
        """测试查询执行"""
        # 准备模拟数据
        mock_docs = [
            {"_id": ObjectId(), "name": "John", "age": 30},
            {"_id": ObjectId(), "name": "Jane", "age": 25}
        ]
        
        # 设置连接状态
        self.connector.connection_status = ConnectionStatus.CONNECTED
        self.connector._optimizer = Mock()
        
        # 模拟优化器返回
        optimized_pipeline = [{"$match": {"age": {"$gt": 20}}}]
        stats = AggregationStats()
        self.connector._optimizer.optimize_pipeline.return_value = (optimized_pipeline, stats)
        
        # 模拟聚合执行
        with patch.object(self.connector, '_execute_aggregation_sync', return_value=mock_docs):
            
            # 执行查询
            query = {"age": {"$gt": 20}}
            options = QueryOptions(limit=100)
            
            df = await self.connector.query(query, options)
            
            # 验证结果
            assert isinstance(df, pl.DataFrame)
            assert len(df) == 2
    
    @pytest.mark.asyncio
    async def test_stream_query(self):
        """测试流式查询"""
        # 设置连接状态
        self.connector.connection_status = ConnectionStatus.CONNECTED
        self.connector._optimizer = Mock()
        self.connector._batch_reader = Mock()
        
        # 模拟优化器和批量读取器
        optimized_pipeline = [{"$match": {}}]
        stats = AggregationStats()
        self.connector._optimizer.optimize_pipeline.return_value = (optimized_pipeline, stats)
        
        # 模拟批次数据
        batch1 = [{"_id": ObjectId(), "name": "John"}]
        batch2 = [{"_id": ObjectId(), "name": "Jane"}] 
        
        async def mock_read_batches(*args, **kwargs):
            yield batch1
            yield batch2
        
        self.connector._batch_reader.read_batches = mock_read_batches
        
        # 执行流式查询
        batches = []
        async for df in self.connector.query_stream():
            assert isinstance(df, pl.DataFrame)
            batches.append(df)
        
        assert len(batches) == 2
    
    @pytest.mark.asyncio
    async def test_row_count(self):
        """测试行数统计"""
        self.connector.connection_status = ConnectionStatus.CONNECTED
        
        mock_collection = Mock()
        mock_collection.estimated_document_count.return_value = 1000
        mock_collection.count_documents.return_value = 500
        
        self.connector._collection = mock_collection
        
        # 测试总行数
        total_count = await self.connector.get_row_count()
        assert total_count == 1000
        
        # 测试带查询条件的行数
        query_count = await self.connector.get_row_count({"status": "active"})
        assert query_count == 500
    
    @pytest.mark.asyncio
    async def test_schema_retrieval(self):
        """测试结构信息获取"""
        self.connector.connection_status = ConnectionStatus.CONNECTED
        
        # 模拟结构检测器
        mock_schema = {
            "columns": {
                "field1": {"type": "Utf8"},
                "field2": {"type": "Int64"}
            },
            "document_count": 1000
        }
        
        mock_detector = AsyncMock()
        mock_detector.detect_schema.return_value = mock_schema
        
        self.connector._schema_detector = mock_detector
        
        # 获取结构信息
        schema = await self.connector.get_schema()
        
        assert schema == mock_schema
        assert self.connector._schema_cache == mock_schema
        
        # 测试缓存使用
        schema2 = await self.connector.get_schema(refresh=False)
        assert schema2 == mock_schema
        
        # 检测器应该只调用一次（使用缓存）
        mock_detector.detect_schema.assert_called_once()
    
    def test_connection_validation(self):
        """测试连接验证"""
        # 未连接状态
        self.connector.connection_status = ConnectionStatus.DISCONNECTED
        
        with pytest.raises(ConnectionError):
            self.connector._validate_connection()
        
        # 已连接状态
        self.connector.connection_status = ConnectionStatus.CONNECTED
        
        # 应该不抛出异常
        self.connector._validate_connection()
    
    def test_memory_estimation(self):
        """测试内存估算"""
        options1 = QueryOptions(limit=1000)
        estimated1 = self.connector._estimate_query_memory(options1)
        assert estimated1 > 0
        
        options2 = QueryOptions(limit=10000)
        estimated2 = self.connector._estimate_query_memory(options2)
        
        # 更大的限制应该需要更多内存
        assert estimated2 > estimated1
    
    def test_query_statistics_update(self):
        """测试查询统计更新"""
        initial_stats = self.connector._connection_stats.copy()
        
        # 更新统计信息
        self.connector._update_query_stats(100, 1500.0)
        
        stats = self.connector._connection_stats
        
        assert stats["queries_executed"] == initial_stats["queries_executed"] + 1
        assert stats["total_documents_processed"] == initial_stats["total_documents_processed"] + 100
        assert stats["total_execution_time_ms"] == initial_stats["total_execution_time_ms"] + 1500.0
        assert stats["average_query_time_ms"] > 0
    
    def test_connection_info(self):
        """测试连接信息获取"""
        info = self.connector.get_connection_info()
        
        assert "connection_params" in info
        assert "connection_status" in info
        assert "statistics" in info
        assert "components" in info
        
        # 验证连接参数
        params = info["connection_params"]
        assert params["host"] == "localhost"
        assert params["database"] == "test_db"
        assert params["collection"] == "test_collection"


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    @patch('pymongo.MongoClient')
    async def test_full_workflow(self, mock_client_class):
        """测试完整工作流程"""
        # 设置模拟
        mock_client = Mock()
        mock_database = Mock()
        mock_collection = Mock()
        
        mock_client.admin.command.return_value = {"ismaster": True}
        mock_client.__getitem__.return_value = mock_database
        mock_database.__getitem__.return_value = mock_collection
        mock_database.list_collection_names.return_value = ["test_collection"]
        mock_database.command.return_value = {"count": 1000}
        mock_database.name = "test_db"
        mock_collection.name = "test_collection"
        
        # 模拟样本数据
        sample_docs = [
            {"_id": ObjectId(), "name": "John", "age": 30, "score": 95.5},
            {"_id": ObjectId(), "name": "Jane", "age": 25, "score": 87.2}
        ]
        
        def mock_aggregate(pipeline, **kwargs):
            # 根据管道返回不同结果
            if any("$sample" in str(stage) for stage in pipeline):
                return sample_docs  # 用于结构检测
            else:
                return sample_docs  # 用于查询
        
        mock_collection.aggregate = Mock(side_effect=mock_aggregate)
        mock_collection.estimated_document_count = Mock(return_value=1000)
        mock_collection.list_indexes.return_value = [{"key": {"name": 1}}]
        
        mock_client_class.return_value = mock_client
        
        # 创建连接器
        connector = MongoConnector(
            "integration_test",
            DataSourceType.MONGODB,
            database="test_db",
            collection="test_collection"
        )
        
        try:
            # 1. 连接
            success = await connector.connect()
            assert success is True
            
            # 2. 测试连接
            test_result = await connector.test_connection()
            assert test_result is True
            
            # 3. 获取结构信息
            schema = await connector.get_schema()
            assert "columns" in schema
            assert len(schema["columns"]) > 0
            
            # 4. 执行查询
            df = await connector.query(
                query={"age": {"$gt": 20}},
                options=QueryOptions(limit=10)
            )
            assert isinstance(df, pl.DataFrame)
            assert len(df) <= 10
            
            # 5. 流式查询
            batch_count = 0
            async for batch_df in connector.query_stream(
                options=QueryOptions(batch_size=1)
            ):
                assert isinstance(batch_df, pl.DataFrame)
                batch_count += 1
                if batch_count >= 2:  # 限制测试批次
                    break
            
            assert batch_count >= 1
            
            # 6. 获取行数
            row_count = await connector.get_row_count()
            assert row_count >= 0
            
            # 7. 获取连接信息
            info = connector.get_connection_info()
            assert info["connection_status"] == "connected"
            
        finally:
            # 清理
            await connector.close()
            assert connector.connection_status == ConnectionStatus.CLOSED


@pytest.mark.performance
class TestPerformance:
    """性能测试"""
    
    @pytest.mark.asyncio
    async def test_large_result_set_handling(self):
        """测试大结果集处理"""
        # 模拟大数据集
        large_docs = [{"_id": ObjectId(), "index": i} for i in range(10000)]
        
        mock_collection = Mock()
        
        def batch_aggregate(pipeline, **kwargs):
            # 模拟分批返回
            skip = 0
            limit = 1000
            
            for stage in pipeline:
                if "$skip" in stage:
                    skip = stage["$skip"]
                elif "$limit" in stage:
                    limit = stage["$limit"]
            
            return large_docs[skip:skip + limit]
        
        mock_collection.aggregate = Mock(side_effect=batch_aggregate)
        
        batch_reader = BatchReader(mock_collection, batch_size=1000)
        
        # 测试批量读取性能
        start_time = time.time()
        
        total_docs = 0
        async for batch in batch_reader.read_batches([], total_limit=5000):
            total_docs += len(batch)
        
        duration = time.time() - start_time
        
        assert total_docs == 5000
        assert duration < 5.0  # 应在 5 秒内完成
    
    def test_aggregation_optimization_performance(self):
        """测试聚合优化性能"""
        mock_collection = Mock()
        mock_collection.list_indexes.return_value = [{"key": {"field1": 1}}]
        
        optimizer = AggregationOptimizer(mock_collection)
        
        # 复杂查询选项
        complex_options = QueryOptions(
            filters={
                "field1": {"$in": [1, 2, 3, 4, 5]},
                "field2": {"$gt": 100, "$lt": 1000},
                "field3": {"$regex": "pattern"},
                "field4": {"$exists": True}
            },
            projection={f"field_{i}": 1 for i in range(20)},
            sort={"field1": 1, "field2": -1},
            skip=1000,
            limit=100
        )
        
        # 测试优化性能
        start_time = time.time()
        
        optimized_pipeline, stats = optimizer.optimize_pipeline([], complex_options)
        
        duration = time.time() - start_time
        
        assert duration < 0.1  # 优化应在 100ms 内完成
        assert len(optimized_pipeline) > 0
        assert stats.optimized_stages > 0
    
    @pytest.mark.asyncio
    async def test_memory_usage_monitoring(self):
        """测试内存使用监控"""
        # 创建大量文档进行转换
        large_docs = []
        for i in range(1000):
            doc = {
                "_id": ObjectId(),
                "data": f"large_data_string_{i}" * 100,  # 较大的字符串
                "nested": {"key": f"value_{i}"},
                "array": list(range(100))
            }
            large_docs.append(doc)
        
        connector = MongoConnector(
            "memory_test",
            DataSourceType.MONGODB,
            database="test_db",
            collection="test_collection"
        )
        
        # 测试文档转换内存使用
        start_memory = memory_guard.get_memory_stats().rss_bytes
        
        df = connector._documents_to_dataframe(large_docs)
        
        end_memory = memory_guard.get_memory_stats().rss_bytes
        memory_used = end_memory - start_memory
        
        # 验证 DataFrame 创建成功
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 1000
        
        # 内存使用应该是合理的（小于 100MB）
        assert memory_used < 100 * 1024 * 1024


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])