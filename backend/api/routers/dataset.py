"""
数据集管理路由器

提供数据集上传、预览和管理功能的API端点
"""
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, UploadFile, File, Form, Depends, Path, Query
from fastapi.responses import StreamingResponse

from ..middleware.auth import get_current_user, User
from ..middleware.error_handler import APIError, ValidationAPIError, NotFoundAPIError
from ...models.api.request_models import DatasetUploadRequest, DatasetPreviewRequest
from ...models.api.response_models import (
    DatasetUploadResponse, DatasetPreviewResponse, APIResponse,
    DatasetInfo, FieldInfo
)
from ...services.file_service import file_service

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter()


@router.post(
    "/upload",
    response_model=DatasetUploadResponse,
    summary="上传数据集",
    description="上传CSV、Excel等格式的数据文件，自动进行格式检测和数据解析。大文件（>50MB）建议使用分块上传",
    response_description="返回数据集信息、字段信息和数据预览"
)
async def upload_dataset(
    file: UploadFile = File(..., description="要上传的数据文件"),
    sheet: Optional[str] = Form(None, description="Excel工作表名称或索引"),
    start_row: int = Form(1, description="数据起始行号（从1开始）", ge=1),
    encoding: Optional[str] = Form(None, description="文件编码，留空自动检测"),
    separator: Optional[str] = Form(None, description="CSV分隔符，留空自动检测"),
    current_user: User = Depends(get_current_user)
):
    """
    上传数据集文件（适用于中小文件，<50MB）
    
    支持的文件格式：
    - CSV (.csv, .tsv, .txt)
    - Excel (.xlsx, .xls)
    
    自动功能：
    - 文件编码检测
    - CSV分隔符检测
    - 数据类型推断
    - 数据质量检查
    
    注意：对于大文件（>50MB），建议使用分块上传API：
    1. POST /upload/init - 初始化上传会话
    2. POST /upload/chunk - 逐块上传文件
    3. POST /upload/complete - 完成上传并处理
    """
    logger.info(f"用户 {current_user.user_id} 上传数据集: {file.filename}")
    
    try:
        # 验证文件
        await _validate_upload_file(file)
        
        # 验证处理参数
        await _validate_file_processing_params(sheet, start_row, encoding, separator)
        
        # 读取文件内容
        file_content = await file.read()
        file.file.seek(0)  # 重置文件指针以供后续处理
        
        # 检查文件大小，如果超过50MB建议使用分块上传
        size_mb = len(file_content) / (1024 * 1024)
        if size_mb > 50:
            logger.warning(f"文件大小 {size_mb:.1f}MB 较大，建议使用分块上传API")
            # 仍然允许上传，但给出警告
        
        # 调用文件服务处理上传
        result = await file_service.process_upload(
            file=file,
            content=file_content,
            sheet=sheet,
            start_row=start_row,
            encoding=encoding,
            separator=separator,
            user_id=current_user.user_id
        )
        
        # 转换为API响应格式
        dataset_metadata = result['dataset_info']
        
        dataset_info = DatasetInfo(
            dataset_id=dataset_metadata['dataset_id'],
            name=dataset_metadata['name'],
            description=dataset_metadata['description'],
            rows=dataset_metadata['rows'],
            columns=dataset_metadata['columns'],
            size_bytes=dataset_metadata['size_bytes'],
            created_at=dataset_metadata['created_at'],
            updated_at=dataset_metadata['updated_at'],
            file_type=dataset_metadata['file_type'],
            encoding=dataset_metadata['encoding']
        )
        
        # 转换字段信息
        fields = [
            FieldInfo(
                name=field['name'],
                data_type=field['data_type'],
                nullable=field['nullable'],
                unique_count=field['unique_count'],
                null_count=field['null_count'],
                sample_values=field['sample_values']
            )
            for field in result['field_info']
        ]
        
        message = f"数据集 '{file.filename}' 上传成功"
        if size_mb > 50:
            message += f"（文件大小 {size_mb:.1f}MB，下次建议使用分块上传以获得更好的体验）"
        
        logger.info(f"数据集上传成功: {dataset_info.dataset_id}")
        
        return DatasetUploadResponse(
            message=message,
            dataset=dataset_info,
            fields=fields,
            preview=result['preview_data']
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"数据集上传失败: {str(e)}")
        raise APIError(
            message=f"数据集上传失败: {str(e)}",
            error_code="UPLOAD_FAILED",
            status_code=500
        )


@router.get(
    "/preview/{dataset_id}",
    response_model=DatasetPreviewResponse,
    summary="预览数据集",
    description="分页获取数据集内容预览，支持列筛选和数据过滤",
    response_description="返回数据集信息和分页数据"
)
async def preview_dataset(
    dataset_id: str = Path(..., description="数据集ID"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
    limit: int = Query(100, ge=1, le=1000, description="每页记录数（最大1000）"),
    columns: Optional[List[str]] = Query(None, description="指定要预览的列名"),
    current_user: User = Depends(get_current_user)
):
    """
    预览数据集内容
    
    支持功能：
    - 分页查询
    - 列筛选
    - 数据类型显示
    - 统计信息
    """
    logger.info(f"用户 {current_user.user_id} 预览数据集: {dataset_id}")
    
    try:
        # 调用文件服务获取数据预览
        result = await file_service.get_dataset_preview(
            dataset_id=dataset_id,
            offset=offset,
            limit=limit,
            columns=columns,
            user_id=current_user.user_id
        )
        
        # 转换为API响应格式
        dataset_metadata = result['dataset_info']
        
        dataset_info = DatasetInfo(
            dataset_id=dataset_metadata['dataset_id'],
            name=dataset_metadata['name'],
            description=dataset_metadata['description'],
            rows=dataset_metadata['rows'],
            columns=dataset_metadata['columns'],
            size_bytes=dataset_metadata['size_bytes'],
            created_at=dataset_metadata['created_at'],
            updated_at=dataset_metadata['updated_at'],
            file_type=dataset_metadata['file_type'],
            encoding=dataset_metadata['encoding']
        )
        
        return DatasetPreviewResponse(
            total=result['total_rows'],
            offset=result['offset'],
            limit=result['limit'],
            has_more=result['has_more'],
            dataset=dataset_info,
            data=result['data']
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"数据集预览失败: {str(e)}")
        raise APIError(
            message=f"数据集预览失败: {str(e)}",
            error_code="PREVIEW_FAILED",
            status_code=500
        )


@router.get(
    "/list",
    response_model=List[DatasetInfo],
    summary="列出数据集",
    description="获取用户的数据集列表",
    response_description="返回数据集信息列表"
)
async def list_datasets(
    offset: int = Query(0, ge=0, description="分页偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页记录数（最大100）"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: User = Depends(get_current_user)
):
    """
    获取用户的数据集列表
    
    支持功能：
    - 分页查询
    - 关键词搜索
    - 按创建时间排序
    """
    logger.info(f"用户 {current_user.user_id} 获取数据集列表")
    
    try:
        # 调用文件服务获取数据集列表
        datasets_data = await file_service.list_datasets(
            user_id=current_user.user_id,
            offset=offset,
            limit=limit,
            search=search
        )
        
        # 转换为API响应格式
        datasets = [
            DatasetInfo(
                dataset_id=dataset['dataset_id'],
                name=dataset['name'],
                description=dataset['description'],
                rows=dataset['rows'],
                columns=dataset['columns'],
                size_bytes=dataset['size_bytes'],
                created_at=dataset['created_at'],
                updated_at=dataset['updated_at'],
                file_type=dataset['file_type'],
                encoding=dataset['encoding']
            )
            for dataset in datasets_data
        ]
        
        return datasets
        
    except Exception as e:
        logger.error(f"获取数据集列表失败: {str(e)}")
        raise APIError(
            message=f"获取数据集列表失败: {str(e)}",
            error_code="LIST_FAILED",
            status_code=500
        )


@router.delete(
    "/{dataset_id}",
    response_model=APIResponse,
    summary="删除数据集",
    description="删除指定的数据集及其相关文件",
    response_description="返回删除操作结果"
)
async def delete_dataset(
    dataset_id: str = Path(..., description="数据集ID"),
    current_user: User = Depends(get_current_user)
):
    """
    删除数据集
    
    会同时删除：
    - 数据集元数据
    - 存储的数据文件
    - 相关的缓存
    """
    logger.info(f"用户 {current_user.user_id} 删除数据集: {dataset_id}")
    
    try:
        # 调用文件服务删除数据集
        success = await file_service.delete_dataset(dataset_id, current_user.user_id)
        
        if success:
            logger.info(f"数据集删除成功: {dataset_id}")
            return APIResponse(
                message=f"数据集 {dataset_id} 删除成功"
            )
        else:
            raise APIError(
                message="数据集删除失败",
                error_code="DELETE_FAILED",
                status_code=500
            )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"数据集删除失败: {str(e)}")
        raise APIError(
            message=f"数据集删除失败: {str(e)}",
            error_code="DELETE_FAILED",
            status_code=500
        )


@router.get(
    "/{dataset_id}/download",
    summary="下载数据集",
    description="下载数据集为指定格式的文件",
    response_description="返回文件流"
)
async def download_dataset(
    dataset_id: str = Path(..., description="数据集ID"),
    format: str = Query("csv", description="下载格式 (csv, json, parquet)"),
    current_user: User = Depends(get_current_user)
):
    """
    下载数据集
    
    支持格式：
    - CSV
    - JSON
    - Parquet
    """
    logger.info(f"用户 {current_user.user_id} 下载数据集: {dataset_id}, 格式: {format}")
    
    try:
        # 验证格式
        if format not in ["csv", "json", "parquet"]:
            raise ValidationAPIError("不支持的下载格式")
        
        # 调用文件服务导出数据集
        file_content = await file_service.export_dataset(
            dataset_id=dataset_id,
            format=format,
            user_id=current_user.user_id
        )
        
        filename = f"{dataset_id}.{format}"
        content_type = {
            "csv": "text/csv",
            "json": "application/json",
            "parquet": "application/octet-stream"
        }[format]
        
        def generate():
            yield file_content
        
        return StreamingResponse(
            generate(),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"数据集下载失败: {str(e)}")
        raise APIError(
            message=f"数据集下载失败: {str(e)}",
            error_code="DOWNLOAD_FAILED",
            status_code=500
        )


# ========== 断点续传 API 端点 ==========

@router.post(
    "/upload/init",
    response_model=Dict[str, Any],
    summary="初始化大文件上传",
    description="初始化大文件上传会话，支持断点续传",
    response_description="返回上传会话信息和分块配置"
)
async def init_upload_session(
    filename: str = Form(..., description="文件名"),
    file_size: int = Form(..., description="文件总大小（字节）"),
    chunk_size: int = Form(1024 * 1024, description="分块大小（字节）"),
    current_user: User = Depends(get_current_user)
):
    """
    初始化大文件上传会话
    
    用于上传大于50MB的文件，支持断点续传功能
    """
    logger.info(f"用户 {current_user.user_id} 初始化文件上传: {filename}, 大小: {file_size}")
    
    try:
        # 调用文件服务初始化上传会话
        session_info = await file_service.init_upload_session(
            filename=filename,
            file_size=file_size,
            user_id=current_user.user_id,
            chunk_size=chunk_size
        )
        
        logger.info(f"上传会话初始化成功: {session_info['session_id']}")
        
        return {
            "message": f"上传会话初始化成功",
            "session_id": session_info["session_id"],
            "chunk_size": session_info["chunk_size"],
            "total_chunks": session_info["total_chunks"],
            "uploaded_chunks": session_info["uploaded_chunks"]
        }
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"上传会话初始化失败: {str(e)}")
        raise APIError(
            message=f"上传会话初始化失败: {str(e)}",
            error_code="SESSION_INIT_FAILED",
            status_code=500
        )


@router.post(
    "/upload/chunk",
    response_model=Dict[str, Any],
    summary="上传文件块",
    description="上传指定的文件块",
    response_description="返回上传进度信息"
)
async def upload_chunk(
    session_id: str = Form(..., description="上传会话ID"),
    chunk_index: int = Form(..., description="块索引"),
    chunk: UploadFile = File(..., description="文件块数据"),
    current_user: User = Depends(get_current_user)
):
    """
    上传文件块
    
    按块上传文件内容，支持断点续传
    """
    logger.info(f"用户 {current_user.user_id} 上传文件块: {session_id}, 块: {chunk_index}")
    
    try:
        # 读取块数据
        chunk_data = await chunk.read()
        
        # 验证分块上传参数
        await _validate_chunk_upload_params(session_id, chunk_index, chunk_data)
        
        # 调用文件服务上传块
        result = await file_service.upload_chunk(
            session_id=session_id,
            chunk_index=chunk_index,
            chunk_data=chunk_data,
            user_id=current_user.user_id
        )
        
        logger.info(f"文件块上传成功: {session_id}, 块: {chunk_index}, 进度: {result['progress_percent']:.1f}%")
        
        return {
            "message": f"块 {chunk_index} 上传成功",
            "chunk_index": result["chunk_index"],
            "uploaded_chunks": result["uploaded_chunks"],
            "total_chunks": result["total_chunks"],
            "progress_percent": result["progress_percent"],
            "is_complete": result["is_complete"]
        }
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"文件块上传失败: {str(e)}")
        raise APIError(
            message=f"文件块上传失败: {str(e)}",
            error_code="CHUNK_UPLOAD_FAILED",
            status_code=500
        )


@router.post(
    "/upload/complete",
    response_model=DatasetUploadResponse,
    summary="完成文件上传",
    description="完成大文件上传并处理数据集",
    response_description="返回数据集信息和预览数据"
)
async def complete_upload(
    session_id: str = Form(..., description="上传会话ID"),
    sheet: Optional[str] = Form(None, description="Excel工作表名称"),
    start_row: int = Form(1, description="数据起始行号"),
    encoding: Optional[str] = Form(None, description="文件编码"),
    separator: Optional[str] = Form(None, description="CSV分隔符"),
    current_user: User = Depends(get_current_user)
):
    """
    完成大文件上传
    
    验证文件完整性并处理为数据集
    """
    logger.info(f"用户 {current_user.user_id} 完成文件上传: {session_id}")
    
    try:
        # 验证处理参数
        await _validate_file_processing_params(sheet, start_row, encoding, separator)
        
        # 调用文件服务完成上传
        result = await file_service.complete_upload_session(
            session_id=session_id,
            user_id=current_user.user_id,
            sheet=sheet,
            start_row=start_row,
            encoding=encoding,
            separator=separator
        )
        
        # 转换为API响应格式
        dataset_metadata = result['dataset_info']
        
        dataset_info = DatasetInfo(
            dataset_id=dataset_metadata['dataset_id'],
            name=dataset_metadata['name'],
            description=dataset_metadata['description'],
            rows=dataset_metadata['rows'],
            columns=dataset_metadata['columns'],
            size_bytes=dataset_metadata['size_bytes'],
            created_at=dataset_metadata['created_at'],
            updated_at=dataset_metadata['updated_at'],
            file_type=dataset_metadata['file_type'],
            encoding=dataset_metadata['encoding']
        )
        
        # 转换字段信息
        fields = [
            FieldInfo(
                name=field['name'],
                data_type=field['data_type'],
                nullable=field['nullable'],
                unique_count=field['unique_count'],
                null_count=field['null_count'],
                sample_values=field['sample_values']
            )
            for field in result['field_info']
        ]
        
        logger.info(f"大文件上传完成: {dataset_info.dataset_id}")
        
        return DatasetUploadResponse(
            message=f"大文件上传完成",
            dataset=dataset_info,
            fields=fields,
            preview=result['preview_data']
        )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"完成上传失败: {str(e)}")
        raise APIError(
            message=f"完成上传失败: {str(e)}",
            error_code="COMPLETE_UPLOAD_FAILED",
            status_code=500
        )


@router.get(
    "/upload/status/{session_id}",
    response_model=Dict[str, Any],
    summary="查询上传状态",
    description="查询大文件上传会话的状态和进度",
    response_description="返回上传会话状态信息"
)
async def get_upload_status(
    session_id: str = Path(..., description="上传会话ID"),
    current_user: User = Depends(get_current_user)
):
    """
    查询大文件上传状态
    
    获取上传会话的当前状态和进度信息
    """
    logger.info(f"用户 {current_user.user_id} 查询上传状态: {session_id}")
    
    try:
        # 调用文件服务获取状态
        status = await file_service.get_upload_session_status(
            session_id=session_id,
            user_id=current_user.user_id
        )
        
        return {
            "message": "上传状态查询成功",
            "session_id": status["session_id"],
            "filename": status["filename"],
            "file_size": status["file_size"],
            "total_chunks": status["total_chunks"],
            "uploaded_chunks": status["uploaded_chunks"],
            "missing_chunks": status["missing_chunks"],
            "progress_percent": status["progress_percent"],
            "status": status["status"],
            "created_at": status["created_at"],
            "last_activity": status["last_activity"]
        }
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"查询上传状态失败: {str(e)}")
        raise APIError(
            message=f"查询上传状态失败: {str(e)}",
            error_code="STATUS_QUERY_FAILED",
            status_code=500
        )


@router.delete(
    "/upload/cancel/{session_id}",
    response_model=APIResponse,
    summary="取消文件上传",
    description="取消大文件上传会话",
    response_description="返回取消操作结果"
)
async def cancel_upload(
    session_id: str = Path(..., description="上传会话ID"),
    current_user: User = Depends(get_current_user)
):
    """
    取消大文件上传
    
    取消上传会话并清理临时文件
    """
    logger.info(f"用户 {current_user.user_id} 取消文件上传: {session_id}")
    
    try:
        # 调用文件服务取消上传
        success = await file_service.cancel_upload_session(
            session_id=session_id,
            user_id=current_user.user_id
        )
        
        if success:
            logger.info(f"上传会话取消成功: {session_id}")
            return APIResponse(
                message=f"上传会话 {session_id} 已取消"
            )
        else:
            raise APIError(
                message="上传会话取消失败",
                error_code="CANCEL_FAILED",
                status_code=500
            )
        
    except APIError:
        raise
    except Exception as e:
        logger.error(f"取消上传失败: {str(e)}")
        raise APIError(
            message=f"取消上传失败: {str(e)}",
            error_code="CANCEL_FAILED",
            status_code=500
        )


async def _validate_upload_file(file: UploadFile) -> None:
    """
    验证上传的文件
    
    Args:
        file: 上传的文件
        
    Raises:
        ValidationAPIError: 文件验证失败
    """
    # 检查文件名
    if not file.filename:
        raise ValidationAPIError("文件名不能为空")
    
    # 检查文件名安全性
    filename = file.filename.strip()
    if len(filename) == 0:
        raise ValidationAPIError("文件名不能只包含空格")
    
    if len(filename) > 255:
        raise ValidationAPIError("文件名过长（最大255个字符）")
    
    # 检查是否包含危险字符
    dangerous_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    if any(char in filename for char in dangerous_chars):
        raise ValidationAPIError(f"文件名包含非法字符: {', '.join(dangerous_chars)}")
    
    # 检查文件扩展名
    allowed_extensions = ["csv", "xlsx", "xls", "tsv", "txt", "xlsm"]
    file_ext = filename.split(".")[-1].lower()
    if file_ext not in allowed_extensions:
        raise ValidationAPIError(
            f"不支持的文件格式 '.{file_ext}'，支持的格式: {', '.join(allowed_extensions)}"
        )
    
    # 检查文件大小（通过内容长度头部或读取内容）
    max_size_mb = 500  # 500MB限制
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if hasattr(file, 'size') and file.size:
        if file.size > max_size_bytes:
            raise ValidationAPIError(f"文件大小超过限制（最大 {max_size_mb}MB）")
        
        if file.size == 0:
            raise ValidationAPIError("文件内容为空")
    
    # 检查内容类型（如果可用）
    if file.content_type:
        allowed_types = [
            "text/csv",
            "text/plain",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream",
            "text/tab-separated-values"
        ]
        if file.content_type not in allowed_types:
            logger.warning(f"未知的内容类型: {file.content_type}，将继续处理")


async def _validate_chunk_upload_params(
    session_id: str,
    chunk_index: int,
    chunk_data: bytes
) -> None:
    """
    验证分块上传参数
    
    Args:
        session_id: 会话ID
        chunk_index: 块索引
        chunk_data: 块数据
        
    Raises:
        ValidationAPIError: 参数验证失败
    """
    # 验证会话ID格式
    if not session_id or len(session_id) < 10:
        raise ValidationAPIError("无效的会话ID")
    
    # 验证块索引
    if chunk_index < 0:
        raise ValidationAPIError("块索引不能为负数")
    
    if chunk_index > 100000:  # 防止极大的索引值
        raise ValidationAPIError("块索引过大")
    
    # 验证块数据
    if not chunk_data:
        raise ValidationAPIError("块数据不能为空")
    
    # 检查块大小限制（单块最大100MB）
    max_chunk_size = 100 * 1024 * 1024
    if len(chunk_data) > max_chunk_size:
        raise ValidationAPIError(f"块大小超过限制（最大 {max_chunk_size // 1024 // 1024}MB）")


async def _validate_file_processing_params(
    sheet: Optional[str] = None,
    start_row: int = 1,
    encoding: Optional[str] = None,
    separator: Optional[str] = None
) -> None:
    """
    验证文件处理参数
    
    Args:
        sheet: Excel工作表名
        start_row: 起始行
        encoding: 编码
        separator: 分隔符
        
    Raises:
        ValidationAPIError: 参数验证失败
    """
    # 验证起始行
    if start_row < 1:
        raise ValidationAPIError("起始行号必须大于0")
    
    if start_row > 1000000:
        raise ValidationAPIError("起始行号过大")
    
    # 验证工作表名
    if sheet is not None:
        sheet = sheet.strip()
        if len(sheet) == 0:
            raise ValidationAPIError("工作表名不能为空")
        
        if len(sheet) > 255:
            raise ValidationAPIError("工作表名过长")
    
    # 验证编码
    if encoding is not None:
        encoding = encoding.strip().lower()
        common_encodings = [
            'utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'gb18030', 
            'big5', 'iso-8859-1', 'latin-1', 'cp1252', 'ascii'
        ]
        if encoding and encoding not in common_encodings:
            raise ValidationAPIError(f"不支持的编码格式: {encoding}")
    
    # 验证分隔符
    if separator is not None:
        if len(separator) > 5:
            raise ValidationAPIError("分隔符过长")
        
        # 检查是否为可见字符或常用分隔符
        valid_separators = [',', '\t', ';', '|', ':', ' ']
        if separator and separator not in valid_separators and not separator.isprintable():
            raise ValidationAPIError("无效的分隔符")