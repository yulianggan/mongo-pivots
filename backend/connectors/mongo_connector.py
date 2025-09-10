"""
MongoDB 连接器实现
支持聚合管道优化、分页读取、结构检测等高性能功能
"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Iterator, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import math
import polars as pl
import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import (
    ConnectionFailure, 
    ServerSelectionTimeoutError,
    OperationFailure,
    PyMongoError
)
from bson import ObjectId, Decimal128
import concurrent.futures

from .base import (
    DataSourceConnector,
    DataSourceType,
    ConnectionStatus,
    QueryOptions,
    DataSourceError,
    ConnectionError,
    QueryError,
    SchemaError
)
from core.data_engine import data_engine
from core.memory_guard import memory_guard
from core.config import config


@dataclass
class MongoConnectionParams:
    """MongoDB 连接参数"""
    database: str
    collection: str
    host: str = "localhost"
    port: int = 27017
    username: Optional[str] = None
    password: Optional[str] = None
    auth_database: Optional[str] = None
    ssl: bool = False
    ssl_cert_reqs: Optional[str] = None
    connection_timeout_ms: int = 30000
    server_selection_timeout_ms: int = 30000
    max_pool_size: int = 10
    min_pool_size: int = 1
    replica_set: Optional[str] = None
    read_preference: str = "primary"


@dataclass
class AggregationStats:
    """聚合统计信息"""
    pipeline_stages: int = 0
    optimized_stages: int = 0
    estimated_documents: int = 0
    execution_time_ms: float = 0
    data_transfer_bytes: int = 0
    memory_usage_mb: float = 0


class AggregationOptimizer:
    """MongoDB 聚合管道优化器"""
    
    def __init__(self, collection: Collection):
        self.collection = collection
        self._logger = logging.getLogger(f"{self.__class__.__name__}")
        
    def optimize_pipeline(
        self,
        base_pipeline: List[Dict[str, Any]],
        query_options: QueryOptions
    ) -> Tuple[List[Dict[str, Any]], AggregationStats]:
        """优化聚合管道"""
        
        optimized_pipeline = base_pipeline.copy()
        stats = AggregationStats()
        stats.pipeline_stages = len(optimized_pipeline)
        
        # 1. 添加过滤条件（$match）- 尽早过滤数据
        if query_options.filters:
            match_stage = self._build_match_stage(query_options.filters)
            if match_stage:
                optimized_pipeline.insert(0, match_stage)
        
        # 2. 添加投影（$project）- 减少数据传输
        if query_options.projection:
            project_stage = self._build_project_stage(query_options.projection)
            if project_stage:
                optimized_pipeline.append(project_stage)
        
        # 3. 添加排序（$sort）
        if query_options.sort:
            sort_stage = {"$sort": query_options.sort}
            optimized_pipeline.append(sort_stage)
        
        # 4. 添加分页（$skip 和 $limit）
        if query_options.skip > 0:
            optimized_pipeline.append({"$skip": query_options.skip})
        
        if query_options.limit:
            optimized_pipeline.append({"$limit": query_options.limit})
        
        # 5. 优化索引使用
        optimized_pipeline = self._optimize_index_usage(optimized_pipeline)
        
        # 6. 下推计算优化
        optimized_pipeline = self._optimize_pushdown_operations(optimized_pipeline)
        
        stats.optimized_stages = len(optimized_pipeline)
        stats.estimated_documents = self._estimate_result_size(optimized_pipeline)
        
        return optimized_pipeline, stats
    
    def _build_match_stage(self, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """构建 $match 阶段"""
        if not filters:
            return None
        
        match_conditions = {}
        
        for field, condition in filters.items():
            if isinstance(condition, dict):
                # MongoDB 查询操作符
                match_conditions[field] = condition
            else:
                # 简单相等匹配
                match_conditions[field] = condition
        
        return {"$match": match_conditions} if match_conditions else None
    
    def _build_project_stage(self, projection: Dict[str, int]) -> Optional[Dict[str, Any]]:
        """构建 $project 阶段"""
        if not projection:
            return None
        
        # 确保 _id 字段的处理
        project_fields = projection.copy()
        if "_id" not in project_fields:
            project_fields["_id"] = 0  # 默认排除 _id
        
        return {"$project": project_fields}
    
    def _optimize_index_usage(
        self, 
        pipeline: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """优化索引使用"""
        # 获取集合索引信息
        try:
            indexes = list(self.collection.list_indexes())
            index_fields = set()
            for index in indexes:
                for field in index.get("key", {}).keys():
                    index_fields.add(field)
            
            # 重新排序 $match 条件以利用索引
            optimized = []
            for stage in pipeline:
                if "$match" in stage:
                    match_conditions = stage["$match"]
                    indexed_conditions = {}
                    non_indexed_conditions = {}
                    
                    for field, condition in match_conditions.items():
                        if field in index_fields:
                            indexed_conditions[field] = condition
                        else:
                            non_indexed_conditions[field] = condition
                    
                    # 先添加索引字段的条件
                    if indexed_conditions:
                        optimized.append({"$match": indexed_conditions})
                    if non_indexed_conditions:
                        optimized.append({"$match": non_indexed_conditions})
                else:
                    optimized.append(stage)
            
            return optimized
            
        except Exception as e:
            self._logger.debug(f"Index optimization failed: {e}")
            return pipeline
    
    def _optimize_pushdown_operations(
        self, 
        pipeline: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """下推计算优化"""
        optimized = []
        
        for stage in pipeline:
            # 添加日期截断优化
            if "$project" in stage:
                project_stage = stage["$project"]
                optimized_project = {}
                
                for field, expression in project_stage.items():
                    if isinstance(expression, dict) and "$dateTrunc" in str(expression):
                        # 使用 MongoDB 原生 $dateTrunc 操作符
                        optimized_project[field] = expression
                    else:
                        optimized_project[field] = expression
                
                optimized.append({"$project": optimized_project})
            else:
                optimized.append(stage)
        
        return optimized
    
    def _estimate_result_size(self, pipeline: List[Dict[str, Any]]) -> int:
        """估算结果集大小"""
        try:
            # 使用 $collStats 获取集合统计信息
            stats_pipeline = pipeline.copy()
            stats_pipeline.append({"$count": "total"})
            
            result = list(self.collection.aggregate(
                stats_pipeline, 
                allowDiskUse=True,
                maxTimeMS=5000  # 5秒超时
            ))
            
            return result[0]["total"] if result else 0
            
        except Exception as e:
            self._logger.debug(f"Result size estimation failed: {e}")
            # 回退到集合文档数
            try:
                return self.collection.estimated_document_count()
            except Exception:
                return 0


class BatchReader:
    """MongoDB 分页读取器"""
    
    def __init__(self, collection: Collection, batch_size: int = 1000):
        self.collection = collection
        self.batch_size = batch_size
        self._logger = logging.getLogger(f"{self.__class__.__name__}")
        
    async def read_batches(
        self,
        pipeline: List[Dict[str, Any]],
        total_limit: Optional[int] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """分批读取数据"""
        
        processed_docs = 0
        batch_number = 0
        
        while total_limit is None or processed_docs < total_limit:
            # 计算当前批次的限制
            current_batch_size = self.batch_size
            if total_limit is not None:
                remaining = total_limit - processed_docs
                current_batch_size = min(self.batch_size, remaining)
            
            # 构建当前批次的管道
            batch_pipeline = pipeline.copy()
            batch_pipeline.extend([
                {"$skip": processed_docs},
                {"$limit": current_batch_size}
            ])
            
            try:
                # 使用线程池执行同步的聚合操作
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = loop.run_in_executor(
                        executor, 
                        self._execute_aggregation, 
                        batch_pipeline
                    )
                    
                    batch_data = await future
                
                if not batch_data:
                    # 没有更多数据
                    break
                
                actual_count = len(batch_data)
                processed_docs += actual_count
                batch_number += 1
                
                self._logger.debug(
                    f"Batch {batch_number}: {actual_count} documents, "
                    f"total processed: {processed_docs}"
                )
                
                yield batch_data
                
                # 如果返回的数据少于请求的数量，说明已到末尾
                if actual_count < current_batch_size:
                    break
                    
            except Exception as e:
                self._logger.error(f"Batch read error at batch {batch_number}: {e}")
                raise QueryError(f"Batch read failed: {e}", "", DataSourceType.MONGODB)
    
    def _execute_aggregation(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行聚合查询（同步方法，用于线程池）"""
        try:
            cursor = self.collection.aggregate(
                pipeline,
                allowDiskUse=True,
                maxTimeMS=30000,  # 30秒超时
                batchSize=self.batch_size
            )
            return list(cursor)
            
        except Exception as e:
            self._logger.error(f"Aggregation execution failed: {e}")
            raise


class SchemaDetector:
    """MongoDB 文档结构检测器"""
    
    def __init__(self, collection: Collection):
        self.collection = collection
        self._logger = logging.getLogger(f"{self.__class__.__name__}")
        
    async def detect_schema(
        self, 
        sample_size: int = 1000,
        max_depth: int = 3
    ) -> Dict[str, Any]:
        """检测集合的文档结构"""
        
        try:
            # 使用线程池执行同步操作
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = loop.run_in_executor(
                    executor, 
                    self._analyze_documents, 
                    sample_size, 
                    max_depth
                )
                
                schema_info = await future
            
            return schema_info
            
        except Exception as e:
            self._logger.error(f"Schema detection failed: {e}")
            raise SchemaError(f"Schema detection failed: {e}", "", DataSourceType.MONGODB)
    
    def _analyze_documents(self, sample_size: int, max_depth: int) -> Dict[str, Any]:
        """分析文档样本（同步方法）"""
        
        # 获取样本文档
        sample_docs = list(self.collection.aggregate([
            {"$sample": {"size": sample_size}},
            {"$limit": sample_size}
        ]))
        
        if not sample_docs:
            return {"columns": {}, "document_count": 0, "sample_size": 0}
        
        # 分析字段
        field_stats = {}
        
        for doc in sample_docs:
            self._analyze_document(doc, field_stats, max_depth=max_depth)
        
        # 构建结构信息
        columns = {}
        for field_path, stats in field_stats.items():
            columns[field_path] = self._infer_field_type(stats)
        
        # 获取集合统计信息
        try:
            collection_stats = self.collection.database.command("collStats", self.collection.name)
            document_count = collection_stats.get("count", 0)
        except Exception:
            document_count = self.collection.estimated_document_count()
        
        return {
            "columns": columns,
            "document_count": document_count,
            "sample_size": len(sample_docs),
            "collection_name": self.collection.name,
            "database_name": self.collection.database.name
        }
    
    def _analyze_document(
        self, 
        doc: Dict[str, Any], 
        field_stats: Dict[str, Dict], 
        prefix: str = "",
        depth: int = 0,
        max_depth: int = 3
    ) -> None:
        """递归分析文档字段"""
        
        if depth > max_depth:
            return
        
        for field, value in doc.items():
            if isinstance(value, dict) and not isinstance(value, ObjectId):
                # 嵌套文档
                field_path = f"{prefix}{field}." if prefix else f"{field}."
                self._analyze_document(value, field_stats, field_path, depth + 1, max_depth)
            else:
                # 叶子字段
                field_path = f"{prefix}{field}" if prefix else field
                
                if field_path not in field_stats:
                    field_stats[field_path] = {
                        "types": {},
                        "null_count": 0,
                        "total_count": 0,
                        "sample_values": []
                    }
                
                stats = field_stats[field_path]
                stats["total_count"] += 1
                
                if value is None:
                    stats["null_count"] += 1
                else:
                    value_type = type(value).__name__
                    if isinstance(value, ObjectId):
                        value_type = "ObjectId"
                    elif isinstance(value, Decimal128):
                        value_type = "Decimal128"
                    elif isinstance(value, datetime):
                        value_type = "datetime"
                    
                    stats["types"][value_type] = stats["types"].get(value_type, 0) + 1
                    
                    # 收集样本值（最多10个）
                    if len(stats["sample_values"]) < 10:
                        stats["sample_values"].append(str(value)[:100])  # 截断长值
    
    def _infer_field_type(self, stats: Dict) -> Dict[str, Any]:
        """推断字段类型"""
        
        types = stats["types"]
        total_count = stats["total_count"]
        null_count = stats["null_count"]
        
        # 找出主要类型
        if not types:
            primary_type = "null"
        else:
            primary_type = max(types.items(), key=lambda x: x[1])[0]
        
        # 映射到 Polars 兼容类型
        polars_type = self._map_to_polars_type(primary_type)
        
        return {
            "type": polars_type,
            "mongodb_type": primary_type,
            "nullable": null_count > 0,
            "null_count": null_count,
            "non_null_count": total_count - null_count,
            "type_distribution": types,
            "sample_values": stats["sample_values"]
        }
    
    def _map_to_polars_type(self, mongodb_type: str) -> str:
        """将 MongoDB 类型映射到 Polars 类型"""
        
        type_mapping = {
            "int": "Int64",
            "float": "Float64", 
            "str": "Utf8",
            "bool": "Boolean",
            "datetime": "Datetime",
            "ObjectId": "Utf8",
            "Decimal128": "Float64",
            "list": "List",
            "dict": "Struct",
            "NoneType": "Null"
        }
        
        return type_mapping.get(mongodb_type, "Utf8")


class MongoConnector(DataSourceConnector):
    """MongoDB 数据源连接器"""
    
    def __init__(self, source_id: str, source_type: DataSourceType, **connection_params):
        super().__init__(source_id, source_type, **connection_params)
        
        # 解析连接参数
        self.params = MongoConnectionParams(**connection_params)
        
        # MongoDB 客户端和集合
        self._client: Optional[MongoClient] = None
        self._database: Optional[Database] = None
        self._collection: Optional[Collection] = None
        
        # 工具组件
        self._optimizer: Optional[AggregationOptimizer] = None
        self._batch_reader: Optional[BatchReader] = None  
        self._schema_detector: Optional[SchemaDetector] = None
        
        # 统计信息
        self._connection_stats = {
            "queries_executed": 0,
            "total_documents_processed": 0,
            "total_execution_time_ms": 0,
            "average_query_time_ms": 0
        }
    
    async def connect(self) -> bool:
        """建立 MongoDB 连接"""
        
        try:
            self.connection_status = ConnectionStatus.CONNECTING
            
            # 构建连接 URI
            uri = self._build_connection_uri()
            
            # 创建客户端配置
            client_options = {
                "connectTimeoutMS": self.params.connection_timeout_ms,
                "serverSelectionTimeoutMS": self.params.server_selection_timeout_ms,
                "maxPoolSize": self.params.max_pool_size,
                "minPoolSize": self.params.min_pool_size,
                "readPreference": self.params.read_preference
            }
            
            if self.params.replica_set:
                client_options["replicaSet"] = self.params.replica_set
            
            # 使用线程池创建连接
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = loop.run_in_executor(
                    executor, 
                    self._create_connection, 
                    uri, 
                    client_options
                )
                
                success = await future
            
            if success:
                self.connection_status = ConnectionStatus.CONNECTED
                
                # 初始化工具组件
                self._optimizer = AggregationOptimizer(self._collection)
                self._batch_reader = BatchReader(self._collection, 
                                               config.get("mongodb", {}).get("batch_size", 1000))
                self._schema_detector = SchemaDetector(self._collection)
                
                self._logger.info(f"Connected to MongoDB: {self.params.database}.{self.params.collection}")
                return True
            else:
                self.connection_status = ConnectionStatus.ERROR
                return False
                
        except Exception as e:
            self.connection_status = ConnectionStatus.ERROR
            self._logger.error(f"MongoDB connection failed: {e}")
            raise ConnectionError(f"MongoDB connection failed: {e}", self.source_id, self.source_type)
    
    def _build_connection_uri(self) -> str:
        """构建 MongoDB 连接 URI"""
        
        if self.params.username and self.params.password:
            auth_part = f"{self.params.username}:{self.params.password}@"
            if self.params.auth_database:
                auth_part += f"?authSource={self.params.auth_database}&"
        else:
            auth_part = ""
        
        ssl_part = "&ssl=true" if self.params.ssl else ""
        
        uri = f"mongodb://{auth_part}{self.params.host}:{self.params.port}/{self.params.database}{ssl_part}"
        
        return uri
    
    def _create_connection(self, uri: str, client_options: Dict[str, Any]) -> bool:
        """创建 MongoDB 连接（同步方法）"""
        
        try:
            # 创建客户端
            self._client = MongoClient(uri, **client_options)
            
            # 测试连接
            self._client.admin.command('ismaster')
            
            # 获取数据库和集合
            self._database = self._client[self.params.database]
            self._collection = self._database[self.params.collection]
            
            # 验证集合存在
            if self.params.collection not in self._database.list_collection_names():
                self._logger.warning(f"Collection {self.params.collection} does not exist")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Connection creation failed: {e}")
            return False
    
    async def close(self) -> None:
        """关闭连接"""
        
        try:
            if self._client:
                self._client.close()
                self._client = None
                self._database = None
                self._collection = None
                
                self._optimizer = None
                self._batch_reader = None
                self._schema_detector = None
                
                self.connection_status = ConnectionStatus.CLOSED
                self._logger.info(f"MongoDB connection closed: {self.source_id}")
                
        except Exception as e:
            self._logger.error(f"Error closing MongoDB connection: {e}")
    
    async def test_connection(self) -> bool:
        """测试连接状态"""
        
        try:
            if not self._client or not self._collection:
                return False
            
            # 使用线程池执行同步操作
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = loop.run_in_executor(
                    executor, 
                    self._test_connection_sync
                )
                
                return await future
                
        except Exception as e:
            self._logger.error(f"Connection test failed: {e}")
            return False
    
    def _test_connection_sync(self) -> bool:
        """同步测试连接"""
        try:
            # 执行简单的 ping
            self._client.admin.command('ping')
            
            # 测试集合访问
            self._collection.find_one({}, {"_id": 1})
            
            return True
            
        except Exception:
            return False
    
    async def get_schema(self, refresh: bool = False) -> Dict[str, Any]:
        """获取数据源结构信息"""
        
        self._validate_connection()
        
        if not refresh and self._schema_cache:
            return self._schema_cache
        
        try:
            with self.memory_protected_operation("get_schema"):
                schema_info = await self._schema_detector.detect_schema()
                
                # 缓存结果
                self._schema_cache = schema_info
                self._update_access_time()
                
                return schema_info
                
        except Exception as e:
            self._logger.error(f"Schema detection failed: {e}")
            raise SchemaError(f"Schema detection failed: {e}", self.source_id, self.source_type)
    
    async def query(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> pl.DataFrame:
        """执行查询并返回 DataFrame"""
        
        self._validate_connection()
        
        if options is None:
            options = QueryOptions()
        
        start_time = time.time()
        
        try:
            with self.memory_protected_operation("query", self._estimate_query_memory(options)):
                
                # 构建基础聚合管道
                base_pipeline = []
                if query:
                    base_pipeline.append({"$match": query})
                
                # 优化管道
                optimized_pipeline, agg_stats = self._optimizer.optimize_pipeline(
                    base_pipeline, options
                )
                
                # 执行查询
                if options.streaming or agg_stats.estimated_documents > 10000:
                    # 使用流式读取
                    documents = []
                    async for batch in self._batch_reader.read_batches(
                        optimized_pipeline, options.limit
                    ):
                        documents.extend(batch)
                        
                        # 内存保护检查
                        if not memory_guard.check_memory_limit():
                            self._logger.warning("Memory limit reached, stopping query")
                            break
                else:
                    # 直接查询
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = loop.run_in_executor(
                            executor, 
                            self._execute_aggregation_sync, 
                            optimized_pipeline
                        )
                        
                        documents = await future
                
                # 转换为 DataFrame
                df = self._documents_to_dataframe(documents)
                
                # 更新统计信息
                execution_time = (time.time() - start_time) * 1000
                self._update_query_stats(len(documents), execution_time)
                
                # 记录性能
                self._log_operation("query", execution_time / 1000, len(documents))
                
                return df
                
        except Exception as e:
            self._logger.error(f"Query execution failed: {e}")
            raise QueryError(f"Query execution failed: {e}", self.source_id, self.source_type)
    
    async def query_stream(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> Iterator[pl.DataFrame]:
        """流式查询"""
        
        self._validate_connection()
        
        if options is None:
            options = QueryOptions(streaming=True)
        else:
            options.streaming = True
        
        try:
            # 构建管道
            base_pipeline = []
            if query:
                base_pipeline.append({"$match": query})
            
            # 优化管道
            optimized_pipeline, _ = self._optimizer.optimize_pipeline(base_pipeline, options)
            
            # 流式读取并返回 DataFrame
            async for batch in self._batch_reader.read_batches(
                optimized_pipeline, options.limit
            ):
                if batch:
                    df = self._documents_to_dataframe(batch)
                    yield df
                    
        except Exception as e:
            self._logger.error(f"Stream query failed: {e}")
            raise QueryError(f"Stream query failed: {e}", self.source_id, self.source_type)
    
    def _execute_aggregation_sync(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """同步执行聚合查询"""
        try:
            cursor = self._collection.aggregate(
                pipeline,
                allowDiskUse=True,
                maxTimeMS=30000
            )
            return list(cursor)
            
        except Exception as e:
            self._logger.error(f"Aggregation execution failed: {e}")
            raise
    
    def _documents_to_dataframe(self, documents: List[Dict[str, Any]]) -> pl.DataFrame:
        """将 MongoDB 文档转换为 Polars DataFrame"""
        
        if not documents:
            return pl.DataFrame()
        
        # 转换特殊类型
        converted_docs = []
        for doc in documents:
            converted_doc = self._convert_document_types(doc)
            converted_docs.append(converted_doc)
        
        # 创建 DataFrame
        try:
            df = pl.DataFrame(converted_docs)
            return data_engine.clean_dataframe(df)
            
        except Exception as e:
            self._logger.error(f"DataFrame conversion failed: {e}")
            # 回退到逐个字段转换
            return self._safe_documents_to_dataframe(converted_docs)
    
    def _convert_document_types(self, doc: Dict[str, Any], max_depth: int = 2) -> Dict[str, Any]:
        """转换文档中的特殊类型"""
        
        converted = {}
        
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                converted[key] = str(value)
            elif isinstance(value, Decimal128):
                converted[key] = float(value.to_decimal())
            elif isinstance(value, datetime):
                converted[key] = value
            elif isinstance(value, dict) and max_depth > 0:
                # 递归转换嵌套文档（有深度限制）
                converted[key] = str(value)  # 简化为字符串
            elif isinstance(value, list):
                # 列表转换为字符串表示
                converted[key] = str(value)
            else:
                converted[key] = value
        
        return converted
    
    def _safe_documents_to_dataframe(self, documents: List[Dict[str, Any]]) -> pl.DataFrame:
        """安全的文档到 DataFrame 转换（回退方法）"""
        
        # 分析所有字段
        all_fields = set()
        for doc in documents:
            all_fields.update(doc.keys())
        
        # 创建统一结构
        normalized_docs = []
        for doc in documents:
            normalized_doc = {}
            for field in all_fields:
                value = doc.get(field)
                if value is None:
                    normalized_doc[field] = None
                else:
                    # 强制转换为字符串以避免类型冲突
                    normalized_doc[field] = str(value)
            
            normalized_docs.append(normalized_doc)
        
        return pl.DataFrame(normalized_docs)
    
    def _estimate_query_memory(self, options: QueryOptions) -> int:
        """估算查询内存需求"""
        
        # 基础估算：每行文档约 1KB，每个字段额外 100B
        estimated_rows = options.limit or 10000  # 默认估算
        estimated_columns = 20  # 默认字段数
        
        bytes_per_row = 1024 + (estimated_columns * 100)
        total_bytes = estimated_rows * bytes_per_row
        
        # DataFrame 额外开销（约 1.5 倍）
        return int(total_bytes * 1.5)
    
    def _update_query_stats(self, document_count: int, execution_time_ms: float) -> None:
        """更新查询统计信息"""
        
        self._connection_stats["queries_executed"] += 1
        self._connection_stats["total_documents_processed"] += document_count
        self._connection_stats["total_execution_time_ms"] += execution_time_ms
        
        # 计算平均查询时间
        if self._connection_stats["queries_executed"] > 0:
            self._connection_stats["average_query_time_ms"] = (
                self._connection_stats["total_execution_time_ms"] / 
                self._connection_stats["queries_executed"]
            )
    
    async def get_row_count(self, query: Optional[Dict[str, Any]] = None) -> int:
        """获取行数"""
        
        self._validate_connection()
        
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                if query:
                    future = loop.run_in_executor(
                        executor, 
                        self._collection.count_documents, 
                        query
                    )
                else:
                    future = loop.run_in_executor(
                        executor, 
                        self._collection.estimated_document_count
                    )
                
                return await future
                
        except Exception as e:
            self._logger.error(f"Row count failed: {e}")
            return 0
    
    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        
        return {
            "connection_params": {
                "host": self.params.host,
                "port": self.params.port,
                "database": self.params.database,
                "collection": self.params.collection,
                "ssl": self.params.ssl
            },
            "connection_status": self.connection_status.value,
            "statistics": self._connection_stats,
            "components": {
                "optimizer": self._optimizer is not None,
                "batch_reader": self._batch_reader is not None,
                "schema_detector": self._schema_detector is not None
            }
        }


# 注册 MongoDB 连接器类型
def _register_mongo_connector():
    """注册 MongoDB 连接器到全局注册表"""
    try:
        from .registry import registry
        registry.register_connector_type(DataSourceType.MONGODB, MongoConnector)
    except ImportError:
        # 如果在测试环境中，忽略注册错误
        pass


# 自动注册
_register_mongo_connector()