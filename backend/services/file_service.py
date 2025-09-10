"""
文件处理服务

提供数据集文件上传、处理、验证和管理功能
支持CSV、Excel等格式，包含断点续传、数据预览、质量检查等功能
"""
import os
import uuid
import hashlib
import aiofiles
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple, BinaryIO
from datetime import datetime, timezone
import logging
import json
from io import BytesIO

import polars as pl
import pandas as pd
from fastapi import UploadFile

from ..utils.file_utils import file_utils
from ..utils.encoding_detector import encoding_detector
from ..core.config import config
from ..api.middleware.error_handler import APIError, ValidationAPIError, NotFoundAPIError


class FileService:
    """文件处理服务类"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 数据存储目录
        self.storage_root = Path(os.getenv('FILE_STORAGE_ROOT', './data/datasets'))
        self.temp_root = Path(os.getenv('TEMP_STORAGE_ROOT', './data/temp'))
        
        # 创建必要目录
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        
        # 文件处理配置
        self.max_file_size = int(os.getenv('MAX_FILE_SIZE_BYTES', 500 * 1024 * 1024))  # 500MB
        self.chunk_size = int(os.getenv('UPLOAD_CHUNK_SIZE', 8192))  # 8KB
        self.preview_rows = int(os.getenv('PREVIEW_ROWS', 100))
        
        # 支持的格式
        self.supported_formats = {
            '.csv': self._process_csv,
            '.tsv': self._process_csv,
            '.txt': self._process_csv,
            '.xlsx': self._process_excel,
            '.xls': self._process_excel,
            '.xlsm': self._process_excel
        }
        
        # 数据集元数据存储（生产环境应使用数据库）
        self.metadata_store: Dict[str, Dict[str, Any]] = {}
        
        # 断点续传状态存储
        self.upload_sessions: Dict[str, Dict[str, Any]] = {}
    
    async def process_upload(
        self,
        file: UploadFile,
        content: bytes,
        sheet: Optional[str] = None,
        start_row: int = 1,
        encoding: Optional[str] = None,
        separator: Optional[str] = None,
        user_id: str = "anonymous"
    ) -> Dict[str, Any]:
        """
        处理文件上传
        
        Args:
            file: 上传的文件对象
            content: 文件内容
            sheet: Excel工作表名称
            start_row: 数据起始行
            encoding: 文件编码
            separator: CSV分隔符
            user_id: 用户ID
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        # 生成数据集ID
        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
        
        try:
            # 验证文件
            await self._validate_file_upload(file, content)
            
            # 保存临时文件
            temp_path = await self._save_temp_file(file, content)
            
            # 检测文件属性
            file_info = await self._analyze_file(temp_path, encoding, separator)
            
            # 处理文件内容
            processing_result = await self._process_file_content(
                temp_path, file_info, sheet, start_row
            )
            
            # 保存到永久存储
            storage_path = await self._save_to_storage(dataset_id, temp_path)
            
            # 创建数据集元数据
            dataset_metadata = {
                'dataset_id': dataset_id,
                'name': file.filename or 'unknown',
                'description': None,
                'user_id': user_id,
                'file_type': file_info['file_type'],
                'encoding': file_info['encoding'],
                'size_bytes': len(content),
                'rows': processing_result['row_count'],
                'columns': processing_result['column_count'],
                'column_info': processing_result['column_info'],
                'storage_path': str(storage_path),
                'file_hash': self._calculate_hash(content),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'processing_metadata': {
                    'sheet': sheet,
                    'start_row': start_row,
                    'separator': file_info.get('separator'),
                    'quality_score': processing_result.get('quality_score', 0.0)
                }
            }
            
            # 存储元数据
            self.metadata_store[dataset_id] = dataset_metadata
            
            # 清理临时文件
            await self._cleanup_temp_file(temp_path)
            
            return {
                'dataset_info': dataset_metadata,
                'field_info': processing_result['column_info'],
                'preview_data': processing_result['preview_data'],
                'quality_report': processing_result.get('quality_report', {})
            }
            
        except Exception as e:
            self.logger.error(f"文件处理失败: {str(e)}")
            # 清理资源
            if 'temp_path' in locals():
                await self._cleanup_temp_file(temp_path)
            raise APIError(
                message=f"文件处理失败: {str(e)}",
                error_code="PROCESSING_FAILED",
                status_code=500
            )
    
    async def get_dataset_preview(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 100,
        columns: Optional[List[str]] = None,
        user_id: str = "anonymous"
    ) -> Dict[str, Any]:
        """
        获取数据集预览
        
        Args:
            dataset_id: 数据集ID
            offset: 偏移量
            limit: 限制数量
            columns: 指定列
            user_id: 用户ID
            
        Returns:
            Dict[str, Any]: 预览数据
        """
        # 验证数据集存在
        dataset = await self._get_dataset_metadata(dataset_id, user_id)
        
        try:
            # 读取数据
            storage_path = Path(dataset['storage_path'])
            
            # 根据文件类型选择读取方法
            file_ext = storage_path.suffix.lower()
            if file_ext in ['.csv', '.tsv', '.txt']:
                df = await self._read_csv_chunk(
                    storage_path, 
                    offset, 
                    limit, 
                    columns,
                    dataset['encoding'],
                    dataset['processing_metadata'].get('separator', ',')
                )
            elif file_ext in ['.xlsx', '.xls', '.xlsm']:
                df = await self._read_excel_chunk(
                    storage_path,
                    offset,
                    limit,
                    columns,
                    dataset['processing_metadata'].get('sheet')
                )
            else:
                raise APIError(
                    message=f"不支持的文件格式: {file_ext}",
                    error_code="UNSUPPORTED_FORMAT",
                    status_code=400
                )
            
            # 转换为JSON格式
            data = df.to_dicts() if hasattr(df, 'to_dicts') else df.to_dict('records')
            
            return {
                'dataset_info': dataset,
                'data': data,
                'total_rows': dataset['rows'],
                'offset': offset,
                'limit': limit,
                'has_more': (offset + limit) < dataset['rows']
            }
            
        except Exception as e:
            self.logger.error(f"数据预览失败: {str(e)}")
            raise APIError(
                message=f"数据预览失败: {str(e)}",
                error_code="PREVIEW_FAILED",
                status_code=500
            )
    
    async def list_datasets(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        列出用户的数据集
        
        Args:
            user_id: 用户ID
            offset: 偏移量
            limit: 限制数量
            search: 搜索关键词
            
        Returns:
            List[Dict[str, Any]]: 数据集列表
        """
        # 过滤用户的数据集
        user_datasets = [
            dataset for dataset in self.metadata_store.values()
            if dataset['user_id'] == user_id
        ]
        
        # 应用搜索过滤
        if search:
            search_lower = search.lower()
            user_datasets = [
                dataset for dataset in user_datasets
                if search_lower in dataset['name'].lower()
                or (dataset['description'] and search_lower in dataset['description'].lower())
            ]
        
        # 按创建时间倒序排序
        user_datasets.sort(key=lambda x: x['created_at'], reverse=True)
        
        # 应用分页
        return user_datasets[offset:offset + limit]
    
    async def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        """
        删除数据集
        
        Args:
            dataset_id: 数据集ID
            user_id: 用户ID
            
        Returns:
            bool: 删除是否成功
        """
        # 验证数据集存在且用户有权限
        dataset = await self._get_dataset_metadata(dataset_id, user_id)
        
        try:
            # 删除文件
            storage_path = Path(dataset['storage_path'])
            if storage_path.exists():
                storage_path.unlink()
            
            # 删除元数据
            del self.metadata_store[dataset_id]
            
            self.logger.info(f"数据集删除成功: {dataset_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"数据集删除失败: {str(e)}")
            raise APIError(
                message=f"数据集删除失败: {str(e)}",
                error_code="DELETE_FAILED",
                status_code=500
            )
    
    async def export_dataset(
        self,
        dataset_id: str,
        format: str,
        user_id: str,
        columns: Optional[List[str]] = None
    ) -> bytes:
        """
        导出数据集
        
        Args:
            dataset_id: 数据集ID
            format: 导出格式
            user_id: 用户ID
            columns: 指定列
            
        Returns:
            bytes: 导出的文件内容
        """
        # 验证数据集存在
        dataset = await self._get_dataset_metadata(dataset_id, user_id)
        
        try:
            # 读取完整数据
            storage_path = Path(dataset['storage_path'])
            df = await self._read_full_dataset(storage_path, dataset, columns)
            
            # 根据格式导出
            if format == 'csv':
                return df.write_csv().encode('utf-8')
            elif format == 'json':
                return json.dumps(df.to_dicts(), ensure_ascii=False, indent=2).encode('utf-8')
            elif format == 'parquet':
                # 写入临时文件然后读取
                with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
                    df.write_parquet(tmp.name)
                    with open(tmp.name, 'rb') as f:
                        content = f.read()
                    os.unlink(tmp.name)
                    return content
            else:
                raise APIError(
                    message=f"不支持的导出格式: {format}",
                    error_code="UNSUPPORTED_FORMAT",
                    status_code=400
                )
                
        except Exception as e:
            self.logger.error(f"数据导出失败: {str(e)}")
            raise APIError(
                message=f"数据导出失败: {str(e)}",
                error_code="EXPORT_FAILED",
                status_code=500
            )
    
    # ========== 私有方法 ==========
    
    async def _validate_file_upload(self, file: UploadFile, content: bytes) -> None:
        """验证上传文件"""
        # 检查文件名
        if not file.filename:
            raise ValidationAPIError("文件名不能为空")
        
        # 检查文件大小
        if len(content) > self.max_file_size:
            raise ValidationAPIError(f"文件大小超过限制（最大 {self.max_file_size // 1024 // 1024}MB）")
        
        # 检查文件扩展名
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.supported_formats:
            raise ValidationAPIError(
                f"不支持的文件格式 '{file_ext}'，支持的格式: {', '.join(self.supported_formats.keys())}"
            )
        
        # 检查内容是否为空
        if len(content) == 0:
            raise ValidationAPIError("文件内容不能为空")
    
    async def _save_temp_file(self, file: UploadFile, content: bytes) -> Path:
        """保存临时文件"""
        # 生成临时文件名
        temp_filename = f"upload_{uuid.uuid4().hex}_{file.filename}"
        temp_path = self.temp_root / temp_filename
        
        # 异步写入文件
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(content)
        
        return temp_path
    
    async def _analyze_file(
        self, 
        file_path: Path, 
        encoding: Optional[str] = None,
        separator: Optional[str] = None
    ) -> Dict[str, Any]:
        """分析文件属性"""
        file_info = {
            'file_type': file_utils.get_file_type(str(file_path)),
            'size_bytes': file_path.stat().st_size
        }
        
        # 检测编码
        if not encoding and file_info['file_type'] in ['csv']:
            encoding_result = encoding_detector.detect_encoding(str(file_path))
            file_info['encoding'] = encoding_result['encoding']
            file_info['encoding_confidence'] = encoding_result['confidence']
        else:
            file_info['encoding'] = encoding or 'utf-8'
            file_info['encoding_confidence'] = 1.0
        
        # 检测CSV分隔符
        if not separator and file_info['file_type'] == 'csv':
            file_info['separator'] = file_utils.detect_csv_delimiter(
                str(file_path), encoding=file_info['encoding']
            )
        else:
            file_info['separator'] = separator
        
        return file_info
    
    async def _process_file_content(
        self,
        file_path: Path,
        file_info: Dict[str, Any],
        sheet: Optional[str] = None,
        start_row: int = 1
    ) -> Dict[str, Any]:
        """处理文件内容"""
        file_ext = file_path.suffix.lower()
        processor = self.supported_formats.get(file_ext)
        
        if not processor:
            raise APIError(
                message=f"不支持的文件格式: {file_ext}",
                error_code="UNSUPPORTED_FORMAT",
                status_code=400
            )
        
        return await processor(file_path, file_info, sheet, start_row)
    
    async def _process_csv(
        self,
        file_path: Path,
        file_info: Dict[str, Any],
        sheet: Optional[str] = None,
        start_row: int = 1
    ) -> Dict[str, Any]:
        """处理CSV文件"""
        try:
            # 使用Polars读取CSV
            df = pl.read_csv(
                str(file_path),
                separator=file_info.get('separator', ','),
                encoding=file_info.get('encoding', 'utf-8'),
                skip_rows=start_row - 1,
                infer_schema_length=10000,  # 增加推断行数
                null_values=['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na']
            )
            
            return await self._analyze_dataframe(df)
            
        except Exception as e:
            self.logger.error(f"CSV处理失败: {str(e)}")
            raise APIError(
                message=f"CSV文件处理失败: {str(e)}",
                error_code="CSV_PROCESSING_FAILED",
                status_code=500
            )
    
    async def _process_excel(
        self,
        file_path: Path,
        file_info: Dict[str, Any],
        sheet: Optional[str] = None,
        start_row: int = 1
    ) -> Dict[str, Any]:
        """处理Excel文件"""
        try:
            # 使用pandas读取Excel（Polars的Excel支持还不够完善）
            kwargs = {
                'skiprows': start_row - 1 if start_row > 1 else None,
                'na_values': ['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na']
            }
            
            if sheet:
                kwargs['sheet_name'] = sheet
            
            df_pandas = pd.read_excel(str(file_path), **kwargs)
            
            # 转换为Polars（更好的性能和类型推断）
            df = pl.from_pandas(df_pandas)
            
            return await self._analyze_dataframe(df)
            
        except Exception as e:
            self.logger.error(f"Excel处理失败: {str(e)}")
            raise APIError(
                message=f"Excel文件处理失败: {str(e)}",
                error_code="EXCEL_PROCESSING_FAILED",
                status_code=500
            )
    
    async def _analyze_dataframe(self, df: pl.DataFrame) -> Dict[str, Any]:
        """分析数据框"""
        # 基本信息
        row_count, column_count = df.shape
        
        # 列信息分析
        column_info = []
        for col_name in df.columns:
            col_data = df[col_name]
            
            # 数据类型
            data_type = str(col_data.dtype)
            
            # 统计信息
            null_count = col_data.null_count()
            unique_count = col_data.n_unique() if row_count > 0 else 0
            
            # 样本值（非空值）
            sample_values = []
            if row_count > 0:
                non_null_values = col_data.drop_nulls()
                if len(non_null_values) > 0:
                    sample_size = min(5, len(non_null_values))
                    sample_values = non_null_values.head(sample_size).to_list()
            
            column_info.append({
                'name': col_name,
                'data_type': data_type,
                'nullable': null_count > 0,
                'unique_count': unique_count,
                'null_count': null_count,
                'sample_values': sample_values
            })
        
        # 预览数据
        preview_data = []
        if row_count > 0:
            preview_df = df.head(self.preview_rows)
            preview_data = preview_df.to_dicts()
        
        # 数据质量评分
        quality_score = self._calculate_quality_score(df, column_info)
        
        # 质量报告
        quality_report = self._generate_quality_report(df, column_info)
        
        return {
            'row_count': row_count,
            'column_count': column_count,
            'column_info': column_info,
            'preview_data': preview_data,
            'quality_score': quality_score,
            'quality_report': quality_report
        }
    
    def _calculate_quality_score(self, df: pl.DataFrame, column_info: List[Dict]) -> float:
        """计算数据质量评分 (0-1)"""
        if df.shape[0] == 0:
            return 0.0
        
        total_score = 0.0
        factors = 0
        
        # 1. 空值比例 (权重: 0.3)
        total_cells = df.shape[0] * df.shape[1]
        null_cells = sum(col['null_count'] for col in column_info)
        null_ratio = null_cells / total_cells if total_cells > 0 else 1.0
        completeness_score = 1.0 - null_ratio
        total_score += completeness_score * 0.3
        factors += 0.3
        
        # 2. 数据类型一致性 (权重: 0.2)
        # 检查是否有混合类型（如数字列中有文本）
        consistency_score = 1.0  # 简化实现，假设Polars已经处理了类型推断
        total_score += consistency_score * 0.2
        factors += 0.2
        
        # 3. 唯一性 (权重: 0.2)
        # 检查是否有合理的唯一值分布
        uniqueness_scores = []
        for col in column_info:
            if col['null_count'] < df.shape[0]:  # 排除全空列
                unique_ratio = col['unique_count'] / (df.shape[0] - col['null_count'])
                # 理想的唯一性比例在0.1-0.9之间
                if 0.1 <= unique_ratio <= 0.9:
                    uniqueness_scores.append(1.0)
                else:
                    uniqueness_scores.append(0.5)
        
        if uniqueness_scores:
            uniqueness_score = sum(uniqueness_scores) / len(uniqueness_scores)
            total_score += uniqueness_score * 0.2
            factors += 0.2
        
        # 4. 列名质量 (权重: 0.15)
        # 检查列名是否有意义（非空、不重复）
        column_names = [col['name'] for col in column_info]
        valid_names = [name for name in column_names if name and name.strip()]
        name_quality = len(valid_names) / len(column_names) if column_names else 0.0
        total_score += name_quality * 0.15
        factors += 0.15
        
        # 5. 行数合理性 (权重: 0.15)
        # 数据量合理（不太少也不太多）
        row_count = df.shape[0]
        if row_count >= 10:
            size_score = 1.0
        elif row_count >= 5:
            size_score = 0.7
        else:
            size_score = 0.3
        total_score += size_score * 0.15
        factors += 0.15
        
        return total_score / factors if factors > 0 else 0.0
    
    def _generate_quality_report(self, df: pl.DataFrame, column_info: List[Dict]) -> Dict[str, Any]:
        """生成数据质量报告"""
        report = {
            'total_rows': df.shape[0],
            'total_columns': df.shape[1],
            'issues': [],
            'recommendations': []
        }
        
        # 检查空值问题
        high_null_columns = [
            col for col in column_info 
            if col['null_count'] / df.shape[0] > 0.5 and df.shape[0] > 0
        ]
        if high_null_columns:
            report['issues'].append({
                'type': 'high_null_ratio',
                'message': f"发现 {len(high_null_columns)} 列的空值比例超过50%",
                'columns': [col['name'] for col in high_null_columns]
            })
            report['recommendations'].append("考虑删除或填充高空值比例的列")
        
        # 检查重复列名
        column_names = [col['name'] for col in column_info]
        duplicate_names = [name for name in column_names if column_names.count(name) > 1]
        if duplicate_names:
            report['issues'].append({
                'type': 'duplicate_column_names',
                'message': f"发现重复的列名: {list(set(duplicate_names))}",
                'columns': list(set(duplicate_names))
            })
            report['recommendations'].append("重命名重复的列名")
        
        # 检查单一值列
        single_value_columns = [
            col for col in column_info 
            if col['unique_count'] <= 1 and col['null_count'] < df.shape[0]
        ]
        if single_value_columns:
            report['issues'].append({
                'type': 'single_value_columns',
                'message': f"发现 {len(single_value_columns)} 列只有单一值",
                'columns': [col['name'] for col in single_value_columns]
            })
            report['recommendations'].append("考虑删除只有单一值的列")
        
        return report
    
    async def _save_to_storage(self, dataset_id: str, temp_path: Path) -> Path:
        """保存到永久存储"""
        storage_filename = f"{dataset_id}{temp_path.suffix}"
        storage_path = self.storage_root / storage_filename
        
        # 移动文件到永久存储
        shutil.move(str(temp_path), str(storage_path))
        
        return storage_path
    
    async def _cleanup_temp_file(self, temp_path: Path) -> None:
        """清理临时文件"""
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception as e:
            self.logger.warning(f"临时文件清理失败: {e}")
    
    def _calculate_hash(self, content: bytes) -> str:
        """计算文件哈希"""
        return hashlib.md5(content).hexdigest()
    
    async def _get_dataset_metadata(self, dataset_id: str, user_id: str) -> Dict[str, Any]:
        """获取数据集元数据"""
        if dataset_id not in self.metadata_store:
            raise NotFoundAPIError("数据集", dataset_id)
        
        dataset = self.metadata_store[dataset_id]
        if dataset['user_id'] != user_id:
            raise APIError(
                message="无权访问该数据集",
                error_code="ACCESS_DENIED",
                status_code=403
            )
        
        return dataset
    
    async def _read_csv_chunk(
        self,
        file_path: Path,
        offset: int,
        limit: int,
        columns: Optional[List[str]],
        encoding: str,
        separator: str
    ) -> pl.DataFrame:
        """读取CSV数据块"""
        # 使用Polars的lazy API进行高效分页
        lazy_df = pl.scan_csv(
            str(file_path),
            separator=separator,
            encoding=encoding,
            infer_schema_length=1000
        )
        
        # 应用列筛选
        if columns:
            available_columns = lazy_df.columns
            valid_columns = [col for col in columns if col in available_columns]
            if valid_columns:
                lazy_df = lazy_df.select(valid_columns)
        
        # 应用分页
        lazy_df = lazy_df.slice(offset, limit)
        
        return lazy_df.collect()
    
    async def _read_excel_chunk(
        self,
        file_path: Path,
        offset: int,
        limit: int,
        columns: Optional[List[str]],
        sheet: Optional[str] = None
    ) -> pl.DataFrame:
        """读取Excel数据块"""
        # Excel分页读取比较复杂，这里先读取全部再切片
        # 生产环境中应该使用更高效的方法
        kwargs = {}
        if sheet:
            kwargs['sheet_name'] = sheet
        
        df_pandas = pd.read_excel(str(file_path), **kwargs)
        df = pl.from_pandas(df_pandas)
        
        # 应用列筛选
        if columns:
            available_columns = df.columns
            valid_columns = [col for col in columns if col in available_columns]
            if valid_columns:
                df = df.select(valid_columns)
        
        # 应用分页
        return df.slice(offset, limit)
    
    async def _read_full_dataset(
        self,
        file_path: Path,
        dataset: Dict[str, Any],
        columns: Optional[List[str]] = None
    ) -> pl.DataFrame:
        """读取完整数据集"""
        file_ext = file_path.suffix.lower()
        
        if file_ext in ['.csv', '.tsv', '.txt']:
            lazy_df = pl.scan_csv(
                str(file_path),
                separator=dataset['processing_metadata'].get('separator', ','),
                encoding=dataset.get('encoding', 'utf-8')
            )
        else:
            # Excel需要先转换
            kwargs = {}
            if dataset['processing_metadata'].get('sheet'):
                kwargs['sheet_name'] = dataset['processing_metadata']['sheet']
            
            df_pandas = pd.read_excel(str(file_path), **kwargs)
            lazy_df = pl.from_pandas(df_pandas).lazy()
        
        # 应用列筛选
        if columns:
            available_columns = lazy_df.columns
            valid_columns = [col for col in columns if col in available_columns]
            if valid_columns:
                lazy_df = lazy_df.select(valid_columns)
        
        return lazy_df.collect()
    
    # ========== 断点续传功能 ==========
    
    async def init_upload_session(
        self,
        filename: str,
        file_size: int,
        user_id: str,
        chunk_size: int = 1024 * 1024  # 1MB默认
    ) -> Dict[str, Any]:
        """
        初始化上传会话
        
        Args:
            filename: 文件名
            file_size: 文件总大小
            user_id: 用户ID
            chunk_size: 分块大小
            
        Returns:
            Dict[str, Any]: 上传会话信息
        """
        # 验证文件大小
        if file_size > self.max_file_size:
            raise ValidationAPIError(f"文件大小超过限制（最大 {self.max_file_size // 1024 // 1024}MB）")
        
        # 生成会话ID
        session_id = f"upload_{uuid.uuid4().hex}"
        
        # 创建临时文件
        temp_filename = f"{session_id}_{file_utils.safe_filename(filename)}"
        temp_path = self.temp_root / temp_filename
        
        # 初始化会话状态
        session = {
            'session_id': session_id,
            'filename': filename,
            'file_size': file_size,
            'user_id': user_id,
            'chunk_size': chunk_size,
            'temp_path': str(temp_path),
            'uploaded_chunks': set(),
            'total_chunks': (file_size + chunk_size - 1) // chunk_size,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_activity': datetime.now(timezone.utc).isoformat(),
            'status': 'initialized'
        }
        
        # 存储会话
        self.upload_sessions[session_id] = session
        
        # 创建空的临时文件
        temp_path.touch()
        
        self.logger.info(f"上传会话初始化成功: {session_id}, 文件: {filename}")
        
        return {
            'session_id': session_id,
            'chunk_size': chunk_size,
            'total_chunks': session['total_chunks'],
            'uploaded_chunks': []
        }
    
    async def upload_chunk(
        self,
        session_id: str,
        chunk_index: int,
        chunk_data: bytes,
        user_id: str
    ) -> Dict[str, Any]:
        """
        上传文件块
        
        Args:
            session_id: 会话ID
            chunk_index: 块索引
            chunk_data: 块数据
            user_id: 用户ID
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        # 验证会话
        if session_id not in self.upload_sessions:
            raise NotFoundAPIError("上传会话", session_id)
        
        session = self.upload_sessions[session_id]
        
        # 验证用户权限
        if session['user_id'] != user_id:
            raise APIError(
                message="无权访问该上传会话",
                error_code="ACCESS_DENIED",
                status_code=403
            )
        
        # 验证块索引
        if chunk_index < 0 or chunk_index >= session['total_chunks']:
            raise ValidationAPIError(f"无效的块索引: {chunk_index}")
        
        # 验证块大小
        expected_size = session['chunk_size']
        if chunk_index == session['total_chunks'] - 1:
            # 最后一块可能较小
            expected_size = session['file_size'] % session['chunk_size']
            if expected_size == 0:
                expected_size = session['chunk_size']
        
        if len(chunk_data) != expected_size:
            raise ValidationAPIError(f"块大小不匹配，期望: {expected_size}, 实际: {len(chunk_data)}")
        
        try:
            # 写入块数据
            temp_path = Path(session['temp_path'])
            offset = chunk_index * session['chunk_size']
            
            # 使用随机访问写入
            with open(temp_path, 'r+b') as f:
                f.seek(offset)
                f.write(chunk_data)
            
            # 更新会话状态
            session['uploaded_chunks'].add(chunk_index)
            session['last_activity'] = datetime.now(timezone.utc).isoformat()
            
            # 检查是否上传完成
            is_complete = len(session['uploaded_chunks']) == session['total_chunks']
            if is_complete:
                session['status'] = 'completed'
            
            uploaded_count = len(session['uploaded_chunks'])
            progress = (uploaded_count / session['total_chunks']) * 100
            
            self.logger.info(f"块上传成功: {session_id}, 块: {chunk_index}, 进度: {progress:.1f}%")
            
            return {
                'chunk_index': chunk_index,
                'uploaded_chunks': uploaded_count,
                'total_chunks': session['total_chunks'],
                'progress_percent': progress,
                'is_complete': is_complete
            }
            
        except Exception as e:
            self.logger.error(f"块上传失败: {str(e)}")
            raise APIError(
                message=f"块上传失败: {str(e)}",
                error_code="CHUNK_UPLOAD_FAILED",
                status_code=500
            )
    
    async def complete_upload_session(
        self,
        session_id: str,
        user_id: str,
        sheet: Optional[str] = None,
        start_row: int = 1,
        encoding: Optional[str] = None,
        separator: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        完成上传会话，处理完整文件
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            sheet: Excel工作表
            start_row: 起始行
            encoding: 编码
            separator: 分隔符
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        # 验证会话
        if session_id not in self.upload_sessions:
            raise NotFoundAPIError("上传会话", session_id)
        
        session = self.upload_sessions[session_id]
        
        # 验证用户权限
        if session['user_id'] != user_id:
            raise APIError(
                message="无权访问该上传会话",
                error_code="ACCESS_DENIED",
                status_code=403
            )
        
        # 验证上传完成
        if session['status'] != 'completed':
            missing_chunks = set(range(session['total_chunks'])) - session['uploaded_chunks']
            raise APIError(
                message=f"上传未完成，缺失块: {sorted(missing_chunks)}",
                error_code="UPLOAD_INCOMPLETE",
                status_code=400
            )
        
        try:
            # 验证文件完整性
            temp_path = Path(session['temp_path'])
            actual_size = temp_path.stat().st_size
            if actual_size != session['file_size']:
                raise APIError(
                    message=f"文件大小不匹配，期望: {session['file_size']}, 实际: {actual_size}",
                    error_code="FILE_SIZE_MISMATCH",
                    status_code=400
                )
            
            # 读取完整文件内容
            with open(temp_path, 'rb') as f:
                file_content = f.read()
            
            # 创建模拟的UploadFile对象
            class MockUploadFile:
                def __init__(self, filename: str, content: bytes):
                    self.filename = filename
                    self.content = content
                    self.file = BytesIO(content)
                
                async def read(self) -> bytes:
                    return self.content
            
            mock_file = MockUploadFile(session['filename'], file_content)
            
            # 调用标准处理流程
            result = await self.process_upload(
                file=mock_file,
                content=file_content,
                sheet=sheet,
                start_row=start_row,
                encoding=encoding,
                separator=separator,
                user_id=user_id
            )
            
            # 清理会话
            await self._cleanup_upload_session(session_id)
            
            self.logger.info(f"断点续传完成: {session_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"断点续传完成失败: {str(e)}")
            # 保留会话以便重试
            raise
    
    async def get_upload_session_status(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        获取上传会话状态
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            
        Returns:
            Dict[str, Any]: 会话状态
        """
        # 验证会话
        if session_id not in self.upload_sessions:
            raise NotFoundAPIError("上传会话", session_id)
        
        session = self.upload_sessions[session_id]
        
        # 验证用户权限
        if session['user_id'] != user_id:
            raise APIError(
                message="无权访问该上传会话",
                error_code="ACCESS_DENIED",
                status_code=403
            )
        
        uploaded_count = len(session['uploaded_chunks'])
        progress = (uploaded_count / session['total_chunks']) * 100
        
        return {
            'session_id': session_id,
            'filename': session['filename'],
            'file_size': session['file_size'],
            'chunk_size': session['chunk_size'],
            'total_chunks': session['total_chunks'],
            'uploaded_chunks': uploaded_count,
            'missing_chunks': sorted(set(range(session['total_chunks'])) - session['uploaded_chunks']),
            'progress_percent': progress,
            'status': session['status'],
            'created_at': session['created_at'],
            'last_activity': session['last_activity']
        }
    
    async def cancel_upload_session(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """
        取消上传会话
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            
        Returns:
            bool: 取消是否成功
        """
        # 验证会话
        if session_id not in self.upload_sessions:
            return True  # 会话不存在视为已取消
        
        session = self.upload_sessions[session_id]
        
        # 验证用户权限
        if session['user_id'] != user_id:
            raise APIError(
                message="无权访问该上传会话",
                error_code="ACCESS_DENIED",
                status_code=403
            )
        
        # 清理会话
        await self._cleanup_upload_session(session_id)
        
        self.logger.info(f"上传会话已取消: {session_id}")
        return True
    
    async def _cleanup_upload_session(self, session_id: str) -> None:
        """清理上传会话"""
        if session_id not in self.upload_sessions:
            return
        
        session = self.upload_sessions[session_id]
        
        # 删除临时文件
        temp_path = Path(session['temp_path'])
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as e:
                self.logger.warning(f"临时文件清理失败: {e}")
        
        # 删除会话记录
        del self.upload_sessions[session_id]


# 全局文件服务实例
file_service = FileService()