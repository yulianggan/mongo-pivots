"""
FileConnector - 统一的CSV/Excel文件连接器
支持大文件流式处理，自动编码检测，分块读取
"""
import os
import asyncio
import time
from typing import Dict, Any, Optional, Iterator, List, Union
import polars as pl
from io import BytesIO
import tempfile
import logging

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
from .registry import registry
from core.data_engine import data_engine
from core.memory_guard import memory_guard
from core.chunk_processor import chunk_processor
from utils.encoding_detector import encoding_detector
from utils.file_utils import file_utils


class CSVProcessor:
    """CSV处理器 - 支持流式读取和分块处理"""
    
    def __init__(self, file_path: str, encoding: str = 'utf-8', delimiter: str = ','):
        self.file_path = file_path
        self.encoding = encoding
        self.delimiter = delimiter
        self._logger = logging.getLogger(f"{self.__class__.__name__}.{os.path.basename(file_path)}")
    
    async def read_full(
        self, 
        start_row: int = 1,
        use_chunking: bool = True,
        **kwargs
    ) -> pl.DataFrame:
        """完整读取CSV文件"""
        try:
            with memory_guard.memory_guard(
                "csv_read_full",
                estimated_bytes=self._estimate_memory_usage()
            ):
                # 使用数据引擎读取
                return data_engine.read_csv(
                    self.file_path,
                    separator=self.delimiter,
                    encoding=self.encoding,
                    start_row=start_row,
                    use_chunking=use_chunking,
                    **kwargs
                )
        except Exception as e:
            raise QueryError(f"Failed to read CSV: {str(e)}", self.file_path, DataSourceType.CSV)
    
    async def read_stream(
        self, 
        chunk_size: Optional[int] = None,
        start_row: int = 1,
        **kwargs
    ) -> Iterator[pl.DataFrame]:
        """流式读取CSV文件"""
        chunk_size = chunk_size or chunk_processor.chunk_size
        
        def identity_operation(chunk: pl.DataFrame) -> pl.DataFrame:
            return chunk
        
        try:
            # 使用分块处理器
            for chunk in chunk_processor.process_csv_in_chunks(
                self.file_path,
                identity_operation,
                separator=self.delimiter,
                encoding=self.encoding,
                skip_rows=start_row - 1 if start_row > 1 else 0,
                **kwargs
            ):
                yield chunk
                
        except Exception as e:
            raise QueryError(f"Failed to stream CSV: {str(e)}", self.file_path, DataSourceType.CSV)
    
    async def get_sample(self, sample_rows: int = 100) -> pl.DataFrame:
        """获取数据样本"""
        try:
            return data_engine.read_csv(
                self.file_path,
                separator=self.delimiter,
                encoding=self.encoding,
                start_row=1,
                use_chunking=False,
                n_rows=sample_rows
            )
        except Exception as e:
            raise QueryError(f"Failed to get CSV sample: {str(e)}", self.file_path, DataSourceType.CSV)
    
    def _estimate_memory_usage(self) -> int:
        """估算内存使用量"""
        try:
            file_info = file_utils.estimate_file_info(self.file_path)
            estimated_rows = file_info.get('estimated_rows', 1000)
            estimated_cols = 20  # 默认估算20列
            return memory_guard.estimate_dataframe_memory(estimated_rows, estimated_cols)
        except Exception:
            return 100 * 1024 * 1024  # 默认100MB


class ExcelProcessor:
    """Excel处理器 - 支持多工作表和流式转换"""
    
    def __init__(self, file_path: str, sheet_name: Optional[Union[str, int]] = None):
        self.file_path = file_path
        self.sheet_name = sheet_name
        self._logger = logging.getLogger(f"{self.__class__.__name__}.{os.path.basename(file_path)}")
        self._sheet_info = None
    
    async def read_full(
        self, 
        start_row: int = 1,
        **kwargs
    ) -> pl.DataFrame:
        """完整读取Excel文件"""
        try:
            with memory_guard.memory_guard(
                "excel_read_full", 
                estimated_bytes=self._estimate_memory_usage()
            ):
                # 读取文件内容
                with open(self.file_path, 'rb') as f:
                    content = f.read()
                
                # 使用数据引擎读取
                return data_engine.read_excel(
                    content,
                    sheet=self.sheet_name,
                    start_row=start_row,
                    **kwargs
                )
        except Exception as e:
            raise QueryError(f"Failed to read Excel: {str(e)}", self.file_path, DataSourceType.EXCEL)
    
    async def read_stream(
        self, 
        chunk_size: Optional[int] = None,
        start_row: int = 1,
        **kwargs
    ) -> Iterator[pl.DataFrame]:
        """流式读取Excel文件（通过转换为CSV实现）"""
        temp_csv_path = None
        
        try:
            # 先转换为临时CSV文件
            temp_csv_path = await self._convert_to_temp_csv(start_row=start_row, **kwargs)
            
            # 检测CSV属性
            delimiter = file_utils.detect_csv_delimiter(temp_csv_path)
            
            # 创建CSV处理器并流式读取
            csv_processor = CSVProcessor(temp_csv_path, encoding='utf-8', delimiter=delimiter)
            
            chunk_size = chunk_size or chunk_processor.chunk_size
            async for chunk in csv_processor.read_stream(chunk_size=chunk_size, start_row=1):
                yield chunk
                
        except Exception as e:
            raise QueryError(f"Failed to stream Excel: {str(e)}", self.file_path, DataSourceType.EXCEL)
        finally:
            # 清理临时文件
            if temp_csv_path and os.path.exists(temp_csv_path):
                file_utils.cleanup_temp_file(temp_csv_path)
    
    async def get_sample(self, sample_rows: int = 100) -> pl.DataFrame:
        """获取数据样本"""
        try:
            with open(self.file_path, 'rb') as f:
                content = f.read()
            
            # 读取有限行数
            return data_engine.read_excel(
                content,
                sheet=self.sheet_name,
                start_row=1,
                nrows=sample_rows
            )
        except Exception as e:
            raise QueryError(f"Failed to get Excel sample: {str(e)}", self.file_path, DataSourceType.EXCEL)
    
    async def get_sheet_info(self) -> Dict[str, Any]:
        """获取工作表信息"""
        if self._sheet_info is None:
            try:
                file_info = file_utils.estimate_file_info(self.file_path)
                self._sheet_info = {
                    'sheet_names': file_info.get('sheet_names', []),
                    'sheet_count': file_info.get('sheet_count', 0),
                    'current_sheet': self.sheet_name or 0
                }
            except Exception as e:
                self._logger.warning(f"Failed to get sheet info: {e}")
                self._sheet_info = {
                    'sheet_names': [],
                    'sheet_count': 0,
                    'current_sheet': self.sheet_name or 0
                }
        
        return self._sheet_info
    
    async def _convert_to_temp_csv(
        self, 
        start_row: int = 1,
        **kwargs
    ) -> str:
        """将Excel转换为临时CSV文件"""
        try:
            # 读取Excel数据
            df = await self.read_full(start_row=start_row, **kwargs)
            
            # 创建临时CSV文件
            temp_csv = tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.csv', 
                prefix='excel_convert_',
                delete=False,
                encoding='utf-8'
            )
            
            # 写入CSV数据
            df.write_csv(temp_csv.name)
            temp_csv.close()
            
            return temp_csv.name
            
        except Exception as e:
            raise QueryError(f"Excel to CSV conversion failed: {str(e)}", self.file_path, DataSourceType.EXCEL)
    
    def _estimate_memory_usage(self) -> int:
        """估算内存使用量"""
        try:
            file_info = file_utils.estimate_file_info(self.file_path)
            estimated_rows = file_info.get('estimated_rows', 1000)
            estimated_cols = file_info.get('estimated_columns', 20)
            return memory_guard.estimate_dataframe_memory(estimated_rows, estimated_cols)
        except Exception:
            return 200 * 1024 * 1024  # 默认200MB（Excel通常更大）


class FileConnector(DataSourceConnector):
    """文件连接器 - 统一处理CSV和Excel文件"""
    
    def __init__(self, source_id: str, source_type: DataSourceType, **connection_params):
        super().__init__(source_id, source_type, **connection_params)
        
        # 连接参数
        self.file_path = connection_params.get('file_path')
        self.encoding = connection_params.get('encoding', 'auto')  # 'auto' 表示自动检测
        self.delimiter = connection_params.get('delimiter', 'auto')  # CSV分隔符
        self.sheet_name = connection_params.get('sheet_name')  # Excel工作表
        self.start_row = connection_params.get('start_row', 1)  # 数据起始行
        
        # 处理器
        self._processor = None
        self._file_info = None
        self._detected_encoding = None
        self._detected_delimiter = None
    
    async def connect(self) -> bool:
        """建立文件连接"""
        try:
            self.connection_status = ConnectionStatus.CONNECTING
            start_time = time.time()
            
            # 验证文件
            if not self.file_path:
                raise ConnectionError("file_path is required", self.source_id, self.source_type)
            
            validation = file_utils.validate_file_access(self.file_path)
            if not validation['readable']:
                error_msg = "; ".join(validation['errors'])
                raise ConnectionError(error_msg, self.source_id, self.source_type)
            
            # 获取文件信息
            self._file_info = file_utils.estimate_file_info(self.file_path)
            detected_type = self._file_info['file_type']
            
            # 验证文件类型匹配
            if ((self.source_type == DataSourceType.CSV and detected_type != 'csv') or
                (self.source_type == DataSourceType.EXCEL and detected_type != 'excel')):
                raise ConnectionError(
                    f"File type mismatch: expected {self.source_type.value}, got {detected_type}",
                    self.source_id, 
                    self.source_type
                )
            
            # 初始化处理器
            if self.source_type == DataSourceType.CSV:
                await self._init_csv_processor()
            elif self.source_type == DataSourceType.EXCEL:
                await self._init_excel_processor()
            else:
                raise ConnectionError(
                    f"Unsupported file type: {self.source_type}", 
                    self.source_id, 
                    self.source_type
                )
            
            self.connection_status = ConnectionStatus.CONNECTED
            duration = time.time() - start_time
            self._log_operation("connect", duration)
            
            return True
            
        except Exception as e:
            self.connection_status = ConnectionStatus.ERROR
            self._logger.error(f"Connection failed: {e}")
            if isinstance(e, (ConnectionError, DataSourceError)):
                raise
            else:
                raise ConnectionError(str(e), self.source_id, self.source_type)
    
    async def _init_csv_processor(self) -> None:
        """初始化CSV处理器"""
        # 自动检测编码
        if self.encoding == 'auto':
            encoding_info = encoding_detector.detect_encoding(self.file_path)
            self._detected_encoding = encoding_info['encoding']
            
            if not encoding_info['validation_passed']:
                self._logger.warning(f"Encoding validation failed, using fallback")
        else:
            self._detected_encoding = self.encoding
        
        # 自动检测分隔符
        if self.delimiter == 'auto':
            self._detected_delimiter = file_utils.detect_csv_delimiter(
                self.file_path, 
                encoding=self._detected_encoding
            )
        else:
            self._detected_delimiter = self.delimiter
        
        # 创建CSV处理器
        self._processor = CSVProcessor(
            self.file_path,
            encoding=self._detected_encoding,
            delimiter=self._detected_delimiter
        )
    
    async def _init_excel_processor(self) -> None:
        """初始化Excel处理器"""
        self._processor = ExcelProcessor(self.file_path, sheet_name=self.sheet_name)
    
    async def close(self) -> None:
        """关闭连接"""
        try:
            if self.connection_status == ConnectionStatus.CONNECTED:
                self._processor = None
                self._file_info = None
                self.connection_status = ConnectionStatus.CLOSED
                self._logger.info(f"Connection closed: {self.source_id}")
        except Exception as e:
            self._logger.error(f"Error closing connection: {e}")
    
    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            if self.connection_status != ConnectionStatus.CONNECTED:
                return False
            
            if not self._processor:
                return False
            
            # 尝试读取少量样本数据
            sample = await self._processor.get_sample(sample_rows=5)
            return not sample.is_empty()
            
        except Exception as e:
            self._logger.warning(f"Connection test failed: {e}")
            return False
    
    async def get_schema(self, refresh: bool = False) -> Dict[str, Any]:
        """获取数据结构"""
        if self._schema_cache is None or refresh:
            try:
                self._validate_connection()
                
                # 获取数据样本以推断schema
                sample = await self._processor.get_sample(sample_rows=1000)
                
                # 构建schema信息
                field_types = data_engine.get_field_types(sample)
                
                schema = {
                    'columns': field_types,
                    'row_count': self._file_info.get('estimated_rows', len(sample)),
                    'column_count': len(field_types),
                    'file_info': {
                        'file_path': self.file_path,
                        'file_size': self._file_info.get('size_bytes', 0),
                        'file_type': self._file_info.get('file_type', 'unknown'),
                        'encoding': getattr(self, '_detected_encoding', self.encoding),
                        'delimiter': getattr(self, '_detected_delimiter', self.delimiter)
                    }
                }
                
                # Excel特定信息
                if self.source_type == DataSourceType.EXCEL:
                    sheet_info = await self._processor.get_sheet_info()
                    schema['file_info']['sheet_info'] = sheet_info
                
                self._schema_cache = schema
                
            except Exception as e:
                raise SchemaError(f"Failed to get schema: {str(e)}", self.source_id, self.source_type)
        
        return self._schema_cache
    
    async def query(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> pl.DataFrame:
        """执行查询"""
        self._validate_connection()
        self._update_access_time()
        
        start_time = time.time()
        
        try:
            # 设置默认选项
            if options is None:
                options = QueryOptions()
            
            # 读取数据
            if options.streaming or (options.memory_optimized and self._is_large_file()):
                # 流式处理大文件
                df = await self._query_with_streaming(query, options)
            else:
                # 直接读取
                df = await self._processor.read_full(
                    start_row=self.start_row,
                    use_chunking=options.memory_optimized
                )
            
            # 应用过滤器
            if query:
                df = data_engine.filter_data(df, query)
            
            # 应用投影
            df = data_engine.select_columns(df, options.projection)
            
            # 应用分页
            df = data_engine.paginate(df, options.skip, options.limit)
            
            # 清理数据
            df = data_engine.clean_dataframe(df)
            
            duration = time.time() - start_time
            self._log_operation("query", duration, len(df))
            
            return df
            
        except Exception as e:
            self._logger.error(f"Query failed: {e}")
            if isinstance(e, DataSourceError):
                raise
            else:
                raise QueryError(str(e), self.source_id, self.source_type)
    
    async def query_stream(
        self, 
        query: Optional[Dict[str, Any]] = None,
        options: Optional[QueryOptions] = None
    ) -> Iterator[pl.DataFrame]:
        """流式查询"""
        self._validate_connection()
        self._update_access_time()
        
        try:
            if options is None:
                options = QueryOptions()
            
            # 获取流式数据
            chunk_count = 0
            async for chunk in self._processor.read_stream(
                chunk_size=options.batch_size,
                start_row=self.start_row
            ):
                # 应用过滤器
                if query:
                    chunk = data_engine.filter_data(chunk, query)
                
                # 应用投影
                chunk = data_engine.select_columns(chunk, options.projection)
                
                # 清理数据
                chunk = data_engine.clean_dataframe(chunk)
                
                if not chunk.is_empty():
                    yield chunk
                    chunk_count += 1
            
            self._logger.info(f"Stream query completed: {chunk_count} chunks processed")
            
        except Exception as e:
            self._logger.error(f"Stream query failed: {e}")
            if isinstance(e, DataSourceError):
                raise
            else:
                raise QueryError(str(e), self.source_id, self.source_type)
    
    async def _query_with_streaming(
        self, 
        query: Optional[Dict[str, Any]], 
        options: QueryOptions
    ) -> pl.DataFrame:
        """使用流式处理执行查询"""
        chunks = []
        
        async for chunk in self.query_stream(query, options):
            chunks.append(chunk)
        
        if not chunks:
            return pl.DataFrame()
        
        # 合并所有块
        with memory_guard.memory_guard("merge_chunks"):
            result = pl.concat(chunks, rechunk=True)
        
        return result
    
    def _is_large_file(self) -> bool:
        """判断是否为大文件"""
        if not self._file_info:
            return False
        
        # 大于50MB或超过100万行认为是大文件
        size_mb = self._file_info.get('size_mb', 0)
        estimated_rows = self._file_info.get('estimated_rows', 0)
        
        return size_mb > 50 or estimated_rows > 1000000
    
    async def get_row_count(self, query: Optional[Dict[str, Any]] = None) -> int:
        """获取行数"""
        try:
            # 总是通过实际查询获取准确行数，避免估算误差
            df = await self.query(query, QueryOptions(limit=None))
            return len(df)
            
        except Exception as e:
            self._logger.error(f"Failed to get row count: {e}")
            return 0


# 注册连接器类型
def register_file_connectors():
    """注册文件连接器类型"""
    registry.register_connector_type(DataSourceType.CSV, FileConnector)
    registry.register_connector_type(DataSourceType.EXCEL, FileConnector)


# 自动注册
register_file_connectors()