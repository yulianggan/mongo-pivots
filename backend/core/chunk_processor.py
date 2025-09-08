"""
分块处理器
支持200K行/块的大数据集处理，实现内存可控的数据操作
"""
import polars as pl
from typing import Iterator, List, Dict, Any, Optional, Callable, Union
import math

from .config import config
from .memory_guard import memory_guard


class ChunkProcessor:
    """分块处理器"""
    
    def __init__(self, chunk_size: Optional[int] = None):
        self.chunk_size = chunk_size or config.memory.chunk_size_rows
    
    def process_csv_in_chunks(
        self, 
        file_path_or_buffer: Union[str, bytes], 
        operation: Callable[[pl.DataFrame], pl.DataFrame],
        **read_csv_kwargs
    ) -> Iterator[pl.DataFrame]:
        """分块处理CSV文件"""
        
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
                yield from self._process_file_in_chunks(temp_path, operation, **read_csv_kwargs)
            finally:
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            # 处理文件路径
            yield from self._process_file_in_chunks(file_path_or_buffer, operation, **read_csv_kwargs)
    
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
            total_rows = lazy_df.select(pl.count()).collect().item()
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
                    chunk_kwargs.update({
                        'skip_rows': skip_rows if skip_rows > 0 else None,
                        'n_rows': self.chunk_size
                    })
                    
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
        operation: Callable[[pl.DataFrame], pl.DataFrame]
    ) -> Iterator[pl.DataFrame]:
        """分块处理DataFrame"""
        
        total_rows = len(df)
        num_chunks = math.ceil(total_rows / self.chunk_size)
        
        print(f"Processing DataFrame with {total_rows} rows in {num_chunks} chunks")
        
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
                
                # 生成处理后的块
                yield processed_chunk
                
                # 进度报告
                if chunk_idx % max(1, num_chunks // 10) == 0:
                    progress = (chunk_idx + 1) / num_chunks * 100
                    print(f"Progress: {progress:.1f}%")
    
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
        **read_kwargs
    ) -> pl.DataFrame:
        """处理并聚合数据的便捷方法"""
        
        if isinstance(data_source, pl.DataFrame):
            chunks = self.process_dataframe_in_chunks(data_source, operation)
        else:
            chunks = self.process_csv_in_chunks(data_source, operation, **read_kwargs)
        
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


# 全局分块处理器实例
chunk_processor = ChunkProcessor()