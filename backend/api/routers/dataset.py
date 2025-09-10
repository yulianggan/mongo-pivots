"""
数据集管理路由器

提供数据集上传、预览和管理功能的API端点
"""
import logging
from typing import List, Optional

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
    description="上传CSV、Excel等格式的数据文件，自动进行格式检测和数据解析",
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
    上传数据集文件
    
    支持的文件格式：
    - CSV (.csv, .tsv, .txt)
    - Excel (.xlsx, .xls)
    
    自动功能：
    - 文件编码检测
    - CSV分隔符检测
    - 数据类型推断
    - 数据质量检查
    """
    logger.info(f"用户 {current_user.user_id} 上传数据集: {file.filename}")
    
    try:
        # 验证文件
        await _validate_upload_file(file)
        
        # 读取文件内容
        file_content = await file.read()
        file.file.seek(0)  # 重置文件指针以供后续处理
        
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
        
        logger.info(f"数据集上传成功: {dataset_info.dataset_id}")
        
        return DatasetUploadResponse(
            message=f"数据集 '{file.filename}' 上传成功",
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
    
    # 检查文件扩展名
    allowed_extensions = ["csv", "xlsx", "xls", "tsv", "txt"]
    file_ext = file.filename.split(".")[-1].lower()
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
    
    # 检查内容类型（如果可用）
    if file.content_type:
        allowed_types = [
            "text/csv",
            "text/plain",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/octet-stream"
        ]
        if file.content_type not in allowed_types:
            logger.warning(f"未知的内容类型: {file.content_type}，将继续处理")