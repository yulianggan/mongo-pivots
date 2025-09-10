"""
分块处理器
支持200K行/块的大数据集处理，实现内存可控的数据操作
"""
import polars as pl
from typing import Iterator, List, Dict, Any, Optional, Callable, Union
import math

from .config import config
from .memory_guard import memory_guard
from .redis_cache import cache_manager
from .task_queue import task_manager
import hashlib
import json
import time
from datetime import datetime


class ChunkProcessor:
    """分块处理器 - 支持缓存和队列管理的增强版本"""
    
    def __init__(self, chunk_size: Optional[int] = None):
        self.chunk_size = chunk_size or config.memory.chunk_size_rows
        self._enable_cache = True
        self._cache_ttl = 3600  # 1小时
        self._performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'processing_time': 0,
            'chunks_processed': 0
        }
    
    def process_csv_in_chunks(
        self, 
        file_path_or_buffer: Union[str, bytes], 
        operation: Callable[[pl.DataFrame], pl.DataFrame],
        enable_cache: bool = True,
        user_id: Optional[str] = None,
        **read_csv_kwargs
    ) -> Iterator[pl.DataFrame]:
        """分块处理CSV文件 - 支持缓存和任务队列"""
        
        # 生成缓存键
        cache_key = None
        if enable_cache and self._enable_cache:
            cache_key = self._generate_cache_key(
                file_path_or_buffer, operation, read_csv_kwargs
            )
            
            # 尝试从缓存中获取结果
            cached_result = cache_manager.get_bulk(cache_key)
            if cached_result:
                self._performance_metrics['cache_hits'] += 1
                print(f"Cache hit for key: {cache_key[:16]}...")
                yield from cached_result
                return
            else:
                self._performance_metrics['cache_misses'] += 1
        
        # 检查任务队列限制
        if user_id:
            session = task_manager.get_or_create_session(user_id)
            if not session.can_accept_task:
                raise RuntimeError(f"User {user_id} has reached maximum concurrent tasks")
        
        start_time = time.time()
        results = []
        
        try:
            # 如果是字节数据，需要先写入临时文件或使用BytesIO
            if isinstance(file_path_or_buffer, bytes):
                import tempfile
                import os
                
                # 创建临时文件
                temp_fd, temp_path = tempfile.mkstemp(suffix='.csv')
                try:
                    with os.fdopen(temp_fd, 'wb') as temp_file:
                        temp_file.write(file_path_or_buffer)
                    
                    # 处理临时文件
                    for chunk in self._process_file_in_chunks(temp_path, operation, **read_csv_kwargs):
                        results.append(chunk)
                        yield chunk
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            else:
                # 处理文件路径
                for chunk in self._process_file_in_chunks(file_path_or_buffer, operation, **read_csv_kwargs):
                    results.append(chunk)
                    yield chunk
            
            # 缓存结果
            if cache_key and results:
                cache_manager.set_bulk(cache_key, results, ttl=self._cache_ttl)
        
        finally:
            # 更新性能指标
            processing_time = time.time() - start_time
            self._performance_metrics['processing_time'] += processing_time
            self._performance_metrics['chunks_processed'] += len(results)
    
    def _process_file_in_chunks(
        self, 
        file_path: str, 
        operation: Callable[[pl.DataFrame], pl.DataFrame],
        **read_csv_kwargs
    ) -> Iterator[pl.DataFrame]:
        """分块处理文件"""
        
        # 首先获取总行数（如果可能）
        try:
            # 使用Polars快速扫描获取行数
            lazy_df = pl.scan_csv(file_path, **read_csv_kwargs)
            total_rows = lazy_df.select(pl.len()).collect().item()
            num_chunks = math.ceil(total_rows / self.chunk_size)
            
            print(f"Processing {total_rows} rows in {num_chunks} chunks")
            
        except Exception as e:
            print(f"Could not determine file size: {e}, processing in chunks anyway")
            total_rows = None
            num_chunks = None
        
        # 分块读取和处理
        chunk_idx = 0
        skip_rows = 0
        
        while True:
            try:
                with memory_guard.memory_guard(
                    operation_name=f"chunk_{chunk_idx}",
                    estimated_bytes=memory_guard.estimate_dataframe_memory(self.chunk_size, 20)
                ):
                    # 读取当前块
                    chunk_kwargs = read_csv_kwargs.copy()
                    if skip_rows > 0:
                        chunk_kwargs['skip_rows'] = skip_rows
                    chunk_kwargs['n_rows'] = self.chunk_size
                    
                    chunk = pl.read_csv(file_path, **chunk_kwargs)
                    
                    # 如果块为空，处理完成
                    if chunk.is_empty():
                        break
                    
                    # 应用操作
                    processed_chunk = operation(chunk)
                    
                    # 生成处理后的块
                    yield processed_chunk
                    
                    # 如果读取的行数少于chunk_size，说明文件结束
                    if len(chunk) < self.chunk_size:
                        break
                    
                    chunk_idx += 1
                    skip_rows += self.chunk_size
                    
                    # 进度报告
                    if num_chunks and chunk_idx % max(1, num_chunks // 10) == 0:
                        progress = (chunk_idx + 1) / num_chunks * 100
                        print(f"Progress: {progress:.1f}%")
                        
            except Exception as e:
                print(f"Error processing chunk {chunk_idx}: {e}")
                break
    
    def process_dataframe_in_chunks(
        self, 
        df: pl.DataFrame, 
        operation: Callable[[pl.DataFrame], pl.DataFrame],
        enable_cache: bool = True,
        user_id: Optional[str] = None
    ) -> Iterator[pl.DataFrame]:
        """分块处理DataFrame - 支持缓存和任务队列"""
        
        # 生成缓存键
        cache_key = None
        if enable_cache and self._enable_cache:
            cache_key = self._generate_dataframe_cache_key(df, operation)
            
            # 尝试从缓存中获取结果
            cached_result = cache_manager.get_bulk(cache_key)
            if cached_result:
                self._performance_metrics['cache_hits'] += 1
                print(f"Cache hit for DataFrame key: {cache_key[:16]}...")
                yield from cached_result
                return
            else:
                self._performance_metrics['cache_misses'] += 1
        
        # 检查任务队列限制
        if user_id:
            session = task_manager.get_or_create_session(user_id)
            if not session.can_accept_task:
                raise RuntimeError(f"User {user_id} has reached maximum concurrent tasks")
        
        total_rows = len(df)
        num_chunks = math.ceil(total_rows / self.chunk_size)
        
        print(f"Processing DataFrame with {total_rows} rows in {num_chunks} chunks")
        
        start_time = time.time()
        results = []
        
        try:
            for chunk_idx in range(num_chunks):
                start_row = chunk_idx * self.chunk_size
                end_row = min((chunk_idx + 1) * self.chunk_size, total_rows)
                
                with memory_guard.memory_guard(
                    operation_name=f"dataframe_chunk_{chunk_idx}",
                    estimated_bytes=memory_guard.estimate_dataframe_memory(end_row - start_row, len(df.columns))
                ):
                    # 获取当前块
                    chunk = df.slice(start_row, end_row - start_row)
                    
                    # 应用操作
                    processed_chunk = operation(chunk)
                    
                    results.append(processed_chunk)
                    
                    # 生成处理后的块
                    yield processed_chunk
                    
                    # 进度报告
                    if chunk_idx % max(1, num_chunks // 10) == 0:
                        progress = (chunk_idx + 1) / num_chunks * 100
                        print(f"Progress: {progress:.1f}%")
            
            # 缓存结果
            if cache_key and results:
                cache_manager.set_bulk(cache_key, results, ttl=self._cache_ttl)
        
        finally:
            # 更新性能指标
            processing_time = time.time() - start_time
            self._performance_metrics['processing_time'] += processing_time
            self._performance_metrics['chunks_processed'] += len(results)
    
    def aggregate_chunks(
        self, 
        chunks: Iterator[pl.DataFrame], 
        method: str = "concat"
    ) -> pl.DataFrame:
        """聚合块处理结果"""
        
        chunk_list = []
        
        for chunk in chunks:
            chunk_list.append(chunk)
            
            # 定期检查内存并合并中间结果
            if len(chunk_list) >= 10:  # 每10个块合并一次
                with memory_guard.memory_guard("intermediate_concat"):
                    if method == "concat":
                        intermediate = pl.concat(chunk_list, rechunk=True)
                    elif method == "sum":
                        intermediate = chunk_list[0]
                        for c in chunk_list[1:]:
                            intermediate = intermediate + c
                    else:
                        raise ValueError(f"Unsupported aggregation method: {method}")
                    
                    chunk_list = [intermediate]
        
        # 最终合并
        if not chunk_list:
            return pl.DataFrame()
        elif len(chunk_list) == 1:
            return chunk_list[0]
        else:
            with memory_guard.memory_guard("final_concat"):
                if method == "concat":
                    return pl.concat(chunk_list, rechunk=True)
                elif method == "sum":
                    result = chunk_list[0]
                    for c in chunk_list[1:]:
                        result = result + c
                    return result
                else:
                    raise ValueError(f"Unsupported aggregation method: {method}")
    
    def process_and_aggregate(
        self, 
        data_source: Union[str, bytes, pl.DataFrame], 
        operation: Callable[[pl.DataFrame], pl.DataFrame],
        aggregation_method: str = "concat",
        enable_cache: bool = True,
        user_id: Optional[str] = None,
        **read_kwargs
    ) -> pl.DataFrame:
        """处理并聚合数据的便捷方法 - 支持缓存"""
        
        if isinstance(data_source, pl.DataFrame):
            chunks = self.process_dataframe_in_chunks(
                data_source, operation, enable_cache=enable_cache, user_id=user_id
            )
        else:
            chunks = self.process_csv_in_chunks(
                data_source, operation, enable_cache=enable_cache, user_id=user_id, **read_kwargs
            )
        
        return self.aggregate_chunks(chunks, method=aggregation_method)
    
    def estimate_optimal_chunk_size(
        self, 
        sample_df: pl.DataFrame, 
        target_memory_mb: int = 500
    ) -> int:
        """根据样本数据估算最优块大小"""
        
        if sample_df.is_empty():
            return self.chunk_size
        
        # 计算单行的平均内存使用
        sample_rows = min(1000, len(sample_df))
        sample_memory = memory_guard.estimate_dataframe_memory(
            sample_rows, 
            len(sample_df.columns)
        )
        
        bytes_per_row = sample_memory / sample_rows
        target_memory_bytes = target_memory_mb * 1024 * 1024
        
        optimal_chunk_size = int(target_memory_bytes / bytes_per_row)
        
        # 确保在合理范围内
        min_chunk_size = 1000
        max_chunk_size = 1_000_000
        
        optimal_chunk_size = max(min_chunk_size, min(max_chunk_size, optimal_chunk_size))
        
        print(f"Estimated optimal chunk size: {optimal_chunk_size} rows "
              f"({optimal_chunk_size * bytes_per_row / 1024 / 1024:.1f}MB per chunk)")
        
        return optimal_chunk_size
    
    def adaptive_chunk_size(self, data_source: Union[str, pl.DataFrame], **read_kwargs) -> int:
        """自适应确定块大小"""
        
        if isinstance(data_source, pl.DataFrame):
            sample_df = data_source.head(1000) if len(data_source) > 1000 else data_source
        else:
            # 读取样本数据
            try:
                if isinstance(data_source, str):
                    sample_df = pl.read_csv(data_source, n_rows=1000, **read_kwargs)
                else:  # bytes
                    import tempfile
                    import os
                    
                    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv')
                    try:
                        with os.fdopen(temp_fd, 'wb') as temp_file:
                            temp_file.write(data_source)
                        sample_df = pl.read_csv(temp_path, n_rows=1000, **read_kwargs)
                    finally:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                            
            except Exception as e:
                print(f"Could not read sample for adaptive sizing: {e}")
                return self.chunk_size
        
        return self.estimate_optimal_chunk_size(sample_df)
    
    def _generate_cache_key(
        self, 
        data_source: Union[str, bytes], 
        operation: Callable, 
        kwargs: Dict[str, Any]
    ) -> str:
        """生成缓存键"""
        
        # 创建唯一标识符
        if isinstance(data_source, str):
            # 文件路径 + 修改时间
            import os
            if os.path.exists(data_source):
                mod_time = os.path.getmtime(data_source)
                source_id = f"{data_source}:{mod_time}"
            else:
                source_id = data_source
        else:
            # 字节数据的哈希值
            source_id = hashlib.md5(data_source).hexdigest()
        
        # 操作函数名称
        operation_name = getattr(operation, '__name__', str(operation))
        
        # 参数哈希
        kwargs_str = json.dumps(kwargs, sort_keys=True, default=str)
        kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()
        
        # 组合生成最终键
        cache_key = f"chunk_csv:{source_id}:{operation_name}:{kwargs_hash}"
        return hashlib.md5(cache_key.encode()).hexdigest()
    
    def _generate_dataframe_cache_key(
        self, 
        df: pl.DataFrame, 
        operation: Callable
    ) -> str:
        """生成DataFrame缓存键"""
        
        # 数据特征
        df_info = {
            'shape': df.shape,
            'columns': list(df.columns),
            'dtypes': [str(dtype) for dtype in df.dtypes]
        }
        
        # 如果数据较小，包含部分数据的哈希
        if len(df) <= 1000:
            # 使用前100行的哈希值
            sample_data = df.head(100).to_pandas().to_string()
            df_info['sample_hash'] = hashlib.md5(sample_data.encode()).hexdigest()
        
        # 操作函数名称
        operation_name = getattr(operation, '__name__', str(operation))
        
        # 组合生成最终键
        df_str = json.dumps(df_info, sort_keys=True)
        cache_key = f"chunk_df:{df_str}:{operation_name}"
        return hashlib.md5(cache_key.encode()).hexdigest()
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        
        metrics = self._performance_metrics.copy()
        
        # 计算缓存命中率
        total_requests = metrics['cache_hits'] + metrics['cache_misses']
        if total_requests > 0:
            metrics['cache_hit_rate'] = metrics['cache_hits'] / total_requests
        else:
            metrics['cache_hit_rate'] = 0.0
        
        # 平均处理时间
        if metrics['chunks_processed'] > 0:
            metrics['avg_processing_time'] = metrics['processing_time'] / metrics['chunks_processed']
        else:
            metrics['avg_processing_time'] = 0.0
        
        # 添加时间戳
        metrics['timestamp'] = datetime.now().isoformat()
        
        return metrics
    
    def reset_performance_metrics(self):
        """重置性能指标"""
        
        self._performance_metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'processing_time': 0,
            'chunks_processed': 0
        }
    
    def set_cache_enabled(self, enabled: bool):
        """设置缓存是否启用"""
        self._enable_cache = enabled
    
    def set_cache_ttl(self, ttl: int):
        """设置缓存TTL（秒）"""
        self._cache_ttl = ttl
    
    def clear_cache(self, pattern: Optional[str] = None):
        """清理缓存"""
        
        if pattern:
            # 清理匹配模式的缓存
            cache_manager.delete_pattern(f"chunk_*{pattern}*")
        else:
            # 清理所有分块处理缓存
            cache_manager.delete_pattern("chunk_*")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        
        # 获取分块处理相关的缓存键
        chunk_keys = cache_manager.get_keys_by_pattern("chunk_*")
        
        return {
            'total_chunk_cache_keys': len(chunk_keys),
            'cache_enabled': self._enable_cache,
            'cache_ttl': self._cache_ttl,
            'performance_metrics': self.get_performance_metrics()
        }


# 全局分块处理器实例
chunk_processor = ChunkProcessor()