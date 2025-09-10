"""
数据集管理API的单元测试

测试数据集上传、预览、列表、删除、下载等功能
包括断点续传功能的完整测试覆盖
"""
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from backend.api.routers.dataset import (
    router,
    _validate_upload_file,
    _validate_chunk_upload_params,
    _validate_file_processing_params
)
from backend.api.middleware.error_handler import ValidationAPIError, APIError, NotFoundAPIError
from backend.services.file_service import file_service
from backend.models.api.response_models import DatasetInfo, FieldInfo


# 测试数据
SAMPLE_CSV_CONTENT = b"""id,name,email,age
1,Alice,alice@example.com,25
2,Bob,bob@example.com,30
3,Charlie,charlie@example.com,35"""

SAMPLE_EXCEL_CONTENT = b'PK\x03\x04'  # Excel文件头部标识


class TestDatasetValidation:
    """数据集验证函数测试"""
    
    @pytest.mark.asyncio
    async def test_validate_upload_file_success(self):
        """测试文件验证成功"""
        # 创建模拟的UploadFile
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test.csv"
        mock_file.size = 1024
        mock_file.content_type = "text/csv"
        
        # 应该不抛出异常
        await _validate_upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_validate_upload_file_no_filename(self):
        """测试文件名为空的情况"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = None
        
        with pytest.raises(ValidationAPIError, match="文件名不能为空"):
            await _validate_upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_validate_upload_file_dangerous_filename(self):
        """测试文件名包含危险字符"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test<script>.csv"
        
        with pytest.raises(ValidationAPIError, match="文件名包含非法字符"):
            await _validate_upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_validate_upload_file_unsupported_format(self):
        """测试不支持的文件格式"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test.exe"
        
        with pytest.raises(ValidationAPIError, match="不支持的文件格式"):
            await _validate_upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_validate_upload_file_too_large(self):
        """测试文件过大"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test.csv"
        mock_file.size = 600 * 1024 * 1024  # 600MB
        
        with pytest.raises(ValidationAPIError, match="文件大小超过限制"):
            await _validate_upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_validate_upload_file_empty(self):
        """测试空文件"""
        mock_file = MagicMock(spec=UploadFile)
        mock_file.filename = "test.csv"
        mock_file.size = 0
        
        with pytest.raises(ValidationAPIError, match="文件内容为空"):
            await _validate_upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_validate_chunk_upload_params_success(self):
        """测试分块上传参数验证成功"""
        session_id = "upload_" + uuid.uuid4().hex
        chunk_index = 0
        chunk_data = b"test data"
        
        # 应该不抛出异常
        await _validate_chunk_upload_params(session_id, chunk_index, chunk_data)
    
    @pytest.mark.asyncio
    async def test_validate_chunk_upload_params_invalid_session(self):
        """测试无效的会话ID"""
        with pytest.raises(ValidationAPIError, match="无效的会话ID"):
            await _validate_chunk_upload_params("short", 0, b"data")
    
    @pytest.mark.asyncio
    async def test_validate_chunk_upload_params_negative_index(self):
        """测试负的块索引"""
        session_id = "upload_" + uuid.uuid4().hex
        
        with pytest.raises(ValidationAPIError, match="块索引不能为负数"):
            await _validate_chunk_upload_params(session_id, -1, b"data")
    
    @pytest.mark.asyncio
    async def test_validate_chunk_upload_params_empty_data(self):
        """测试空的块数据"""
        session_id = "upload_" + uuid.uuid4().hex
        
        with pytest.raises(ValidationAPIError, match="块数据不能为空"):
            await _validate_chunk_upload_params(session_id, 0, b"")
    
    @pytest.mark.asyncio
    async def test_validate_file_processing_params_success(self):
        """测试文件处理参数验证成功"""
        await _validate_file_processing_params(
            sheet="Sheet1",
            start_row=2,
            encoding="utf-8",
            separator=","
        )
    
    @pytest.mark.asyncio
    async def test_validate_file_processing_params_invalid_start_row(self):
        """测试无效的起始行"""
        with pytest.raises(ValidationAPIError, match="起始行号必须大于0"):
            await _validate_file_processing_params(start_row=0)
    
    @pytest.mark.asyncio
    async def test_validate_file_processing_params_invalid_encoding(self):
        """测试无效的编码"""
        with pytest.raises(ValidationAPIError, match="不支持的编码格式"):
            await _validate_file_processing_params(encoding="invalid-encoding")


class TestDatasetUploadAPI:
    """数据集上传API测试"""
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = MagicMock()
        user.user_id = "test_user_123"
        return user
    
    @pytest.fixture
    def sample_csv_file(self):
        """创建示例CSV文件"""
        return UploadFile(
            filename="test.csv",
            file=BytesIO(SAMPLE_CSV_CONTENT),
            size=len(SAMPLE_CSV_CONTENT),
            headers={"content-type": "text/csv"}
        )
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_upload_dataset_success(self, mock_get_user, mock_file_service, mock_user, sample_csv_file):
        """测试数据集上传成功"""
        # 设置模拟
        mock_get_user.return_value = mock_user
        
        mock_dataset_info = {
            'dataset_id': 'ds_123',
            'name': 'test.csv',
            'description': None,
            'rows': 3,
            'columns': 4,
            'size_bytes': len(SAMPLE_CSV_CONTENT),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'file_type': 'csv',
            'encoding': 'utf-8'
        }
        
        mock_field_info = [
            {
                'name': 'id',
                'data_type': 'Int64',
                'nullable': False,
                'unique_count': 3,
                'null_count': 0,
                'sample_values': [1, 2, 3]
            },
            {
                'name': 'name',
                'data_type': 'String',
                'nullable': False,
                'unique_count': 3,
                'null_count': 0,
                'sample_values': ['Alice', 'Bob', 'Charlie']
            }
        ]
        
        mock_file_service.process_upload.return_value = {
            'dataset_info': mock_dataset_info,
            'field_info': mock_field_info,
            'preview_data': [
                {'id': 1, 'name': 'Alice', 'email': 'alice@example.com', 'age': 25}
            ]
        }
        
        # 导入API函数并测试
        from backend.api.routers.dataset import upload_dataset
        
        result = await upload_dataset(
            file=sample_csv_file,
            sheet=None,
            start_row=1,
            encoding=None,
            separator=None,
            current_user=mock_user
        )
        
        # 验证结果
        assert result.message.startswith("数据集 'test.csv' 上传成功")
        assert result.dataset.dataset_id == 'ds_123'
        assert result.dataset.name == 'test.csv'
        assert result.dataset.rows == 3
        assert len(result.fields) == 2
        assert result.fields[0].name == 'id'
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_upload_dataset_large_file_warning(self, mock_get_user, mock_file_service, mock_user):
        """测试大文件上传的警告信息"""
        # 创建大文件模拟
        large_content = b"x" * (60 * 1024 * 1024)  # 60MB
        mock_file = UploadFile(
            filename="large.csv",
            file=BytesIO(large_content),
            size=len(large_content),
            headers={"content-type": "text/csv"}
        )
        
        mock_get_user.return_value = mock_user
        
        mock_dataset_info = {
            'dataset_id': 'ds_large',
            'name': 'large.csv',
            'description': None,
            'rows': 1000000,
            'columns': 10,
            'size_bytes': len(large_content),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'file_type': 'csv',
            'encoding': 'utf-8'
        }
        
        mock_file_service.process_upload.return_value = {
            'dataset_info': mock_dataset_info,
            'field_info': [],
            'preview_data': []
        }
        
        from backend.api.routers.dataset import upload_dataset
        
        result = await upload_dataset(
            file=mock_file,
            sheet=None,
            start_row=1,
            encoding=None,
            separator=None,
            current_user=mock_user
        )
        
        # 验证包含大文件警告
        assert "建议使用分块上传" in result.message


class TestChunkedUploadAPI:
    """分块上传API测试"""
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = MagicMock()
        user.user_id = "test_user_123"
        return user
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_init_upload_session_success(self, mock_get_user, mock_file_service, mock_user):
        """测试初始化上传会话成功"""
        mock_get_user.return_value = mock_user
        
        session_info = {
            'session_id': 'upload_abc123',
            'chunk_size': 1024 * 1024,
            'total_chunks': 10,
            'uploaded_chunks': []
        }
        
        mock_file_service.init_upload_session.return_value = session_info
        
        from backend.api.routers.dataset import init_upload_session
        
        result = await init_upload_session(
            filename="large_file.csv",
            file_size=10 * 1024 * 1024,  # 10MB
            chunk_size=1024 * 1024,      # 1MB
            current_user=mock_user
        )
        
        assert "上传会话初始化成功" in result["message"]
        assert result["session_id"] == 'upload_abc123'
        assert result["total_chunks"] == 10
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_upload_chunk_success(self, mock_get_user, mock_file_service, mock_user):
        """测试上传文件块成功"""
        mock_get_user.return_value = mock_user
        
        chunk_data = b"x" * 1024  # 1KB数据
        mock_chunk = UploadFile(
            filename="chunk_0",
            file=BytesIO(chunk_data),
            size=len(chunk_data)
        )
        
        upload_result = {
            'chunk_index': 0,
            'uploaded_chunks': 1,
            'total_chunks': 10,
            'progress_percent': 10.0,
            'is_complete': False
        }
        
        mock_file_service.upload_chunk.return_value = upload_result
        
        from backend.api.routers.dataset import upload_chunk
        
        result = await upload_chunk(
            session_id="upload_abc123",
            chunk_index=0,
            chunk=mock_chunk,
            current_user=mock_user
        )
        
        assert "块 0 上传成功" in result["message"]
        assert result["progress_percent"] == 10.0
        assert not result["is_complete"]
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_complete_upload_success(self, mock_get_user, mock_file_service, mock_user):
        """测试完成上传成功"""
        mock_get_user.return_value = mock_user
        
        mock_dataset_info = {
            'dataset_id': 'ds_chunked',
            'name': 'large_file.csv',
            'description': None,
            'rows': 10000,
            'columns': 5,
            'size_bytes': 10 * 1024 * 1024,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'file_type': 'csv',
            'encoding': 'utf-8'
        }
        
        completion_result = {
            'dataset_info': mock_dataset_info,
            'field_info': [],
            'preview_data': []
        }
        
        mock_file_service.complete_upload_session.return_value = completion_result
        
        from backend.api.routers.dataset import complete_upload
        
        result = await complete_upload(
            session_id="upload_abc123",
            sheet=None,
            start_row=1,
            encoding=None,
            separator=None,
            current_user=mock_user
        )
        
        assert result.message == "大文件上传完成"
        assert result.dataset.dataset_id == 'ds_chunked'
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_get_upload_status_success(self, mock_get_user, mock_file_service, mock_user):
        """测试查询上传状态成功"""
        mock_get_user.return_value = mock_user
        
        status_info = {
            'session_id': 'upload_abc123',
            'filename': 'large_file.csv',
            'file_size': 10 * 1024 * 1024,
            'total_chunks': 10,
            'uploaded_chunks': 5,
            'missing_chunks': [5, 6, 7, 8, 9],
            'progress_percent': 50.0,
            'status': 'uploading',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_activity': datetime.now(timezone.utc).isoformat()
        }
        
        mock_file_service.get_upload_session_status.return_value = status_info
        
        from backend.api.routers.dataset import get_upload_status
        
        result = await get_upload_status(
            session_id="upload_abc123",
            current_user=mock_user
        )
        
        assert "上传状态查询成功" in result["message"]
        assert result["progress_percent"] == 50.0
        assert len(result["missing_chunks"]) == 5
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_cancel_upload_success(self, mock_get_user, mock_file_service, mock_user):
        """测试取消上传成功"""
        mock_get_user.return_value = mock_user
        mock_file_service.cancel_upload_session.return_value = True
        
        from backend.api.routers.dataset import cancel_upload
        
        result = await cancel_upload(
            session_id="upload_abc123",
            current_user=mock_user
        )
        
        assert result.success
        assert "已取消" in result.message


class TestDatasetManagementAPI:
    """数据集管理API测试"""
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = MagicMock()
        user.user_id = "test_user_123"
        return user
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_preview_dataset_success(self, mock_get_user, mock_file_service, mock_user):
        """测试数据集预览成功"""
        mock_get_user.return_value = mock_user
        
        mock_dataset_info = {
            'dataset_id': 'ds_123',
            'name': 'test.csv',
            'description': None,
            'rows': 1000,
            'columns': 4,
            'size_bytes': 50000,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'file_type': 'csv',
            'encoding': 'utf-8'
        }
        
        preview_result = {
            'dataset_info': mock_dataset_info,
            'data': [
                {'id': 1, 'name': 'Alice', 'email': 'alice@example.com', 'age': 25},
                {'id': 2, 'name': 'Bob', 'email': 'bob@example.com', 'age': 30}
            ],
            'total_rows': 1000,
            'offset': 0,
            'limit': 100,
            'has_more': True
        }
        
        mock_file_service.get_dataset_preview.return_value = preview_result
        
        from backend.api.routers.dataset import preview_dataset
        
        result = await preview_dataset(
            dataset_id="ds_123",
            offset=0,
            limit=100,
            columns=None,
            current_user=mock_user
        )
        
        assert result.dataset.dataset_id == 'ds_123'
        assert result.total == 1000
        assert len(result.data) == 2
        assert result.has_more is True
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_list_datasets_success(self, mock_get_user, mock_file_service, mock_user):
        """测试列出数据集成功"""
        mock_get_user.return_value = mock_user
        
        mock_datasets = [
            {
                'dataset_id': 'ds_123',
                'name': 'test1.csv',
                'description': 'Test dataset 1',
                'rows': 1000,
                'columns': 4,
                'size_bytes': 50000,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'file_type': 'csv',
                'encoding': 'utf-8'
            },
            {
                'dataset_id': 'ds_456',
                'name': 'test2.xlsx',
                'description': 'Test dataset 2',
                'rows': 2000,
                'columns': 6,
                'size_bytes': 100000,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'file_type': 'excel',
                'encoding': 'utf-8'
            }
        ]
        
        mock_file_service.list_datasets.return_value = mock_datasets
        
        from backend.api.routers.dataset import list_datasets
        
        result = await list_datasets(
            offset=0,
            limit=20,
            search=None,
            current_user=mock_user
        )
        
        assert len(result) == 2
        assert result[0].dataset_id == 'ds_123'
        assert result[1].dataset_id == 'ds_456'
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_delete_dataset_success(self, mock_get_user, mock_file_service, mock_user):
        """测试删除数据集成功"""
        mock_get_user.return_value = mock_user
        mock_file_service.delete_dataset.return_value = True
        
        from backend.api.routers.dataset import delete_dataset
        
        result = await delete_dataset(
            dataset_id="ds_123",
            current_user=mock_user
        )
        
        assert result.success
        assert "删除成功" in result.message
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_download_dataset_csv(self, mock_get_user, mock_file_service, mock_user):
        """测试下载数据集为CSV格式"""
        mock_get_user.return_value = mock_user
        mock_file_service.export_dataset.return_value = SAMPLE_CSV_CONTENT
        
        from backend.api.routers.dataset import download_dataset
        
        result = await download_dataset(
            dataset_id="ds_123",
            format="csv",
            current_user=mock_user
        )
        
        assert result.media_type == "text/csv"
        assert result.headers["Content-Disposition"] == "attachment; filename=ds_123.csv"


class TestErrorHandling:
    """错误处理测试"""
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = MagicMock()
        user.user_id = "test_user_123"
        return user
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_upload_dataset_not_found_error(self, mock_get_user, mock_file_service, mock_user):
        """测试数据集不存在错误"""
        mock_get_user.return_value = mock_user
        mock_file_service.process_upload.side_effect = NotFoundAPIError("数据集", "ds_123")
        
        sample_file = UploadFile(
            filename="test.csv",
            file=BytesIO(SAMPLE_CSV_CONTENT),
            size=len(SAMPLE_CSV_CONTENT)
        )
        
        from backend.api.routers.dataset import upload_dataset
        
        with pytest.raises(NotFoundAPIError):
            await upload_dataset(
                file=sample_file,
                sheet=None,
                start_row=1,
                encoding=None,
                separator=None,
                current_user=mock_user
            )
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_upload_dataset_processing_error(self, mock_get_user, mock_file_service, mock_user):
        """测试数据处理错误"""
        mock_get_user.return_value = mock_user
        mock_file_service.process_upload.side_effect = Exception("Processing failed")
        
        sample_file = UploadFile(
            filename="test.csv",
            file=BytesIO(SAMPLE_CSV_CONTENT),
            size=len(SAMPLE_CSV_CONTENT)
        )
        
        from backend.api.routers.dataset import upload_dataset
        
        with pytest.raises(APIError) as exc_info:
            await upload_dataset(
                file=sample_file,
                sheet=None,
                start_row=1,
                encoding=None,
                separator=None,
                current_user=mock_user
            )
        
        assert "数据集上传失败" in str(exc_info.value)
    
    @pytest.mark.asyncio
    @patch('backend.api.routers.dataset.file_service')
    @patch('backend.api.routers.dataset.get_current_user')
    async def test_chunk_upload_session_not_found(self, mock_get_user, mock_file_service, mock_user):
        """测试上传会话不存在错误"""
        mock_get_user.return_value = mock_user
        mock_file_service.upload_chunk.side_effect = NotFoundAPIError("上传会话", "upload_123")
        
        chunk_data = b"test data"
        mock_chunk = UploadFile(
            filename="chunk_0",
            file=BytesIO(chunk_data),
            size=len(chunk_data)
        )
        
        from backend.api.routers.dataset import upload_chunk
        
        with pytest.raises(NotFoundAPIError):
            await upload_chunk(
                session_id="upload_123",
                chunk_index=0,
                chunk=mock_chunk,
                current_user=mock_user
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])