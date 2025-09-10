"""
全局错误处理中间件

提供统一的错误响应格式和异常处理机制
"""
import logging
import traceback
from typing import Any, Dict
from datetime import datetime

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from pydantic import ValidationError
import uvicorn

logger = logging.getLogger(__name__)


class APIError(Exception):
    """
    自定义API错误基类
    """
    def __init__(
        self,
        message: str,
        error_code: str = "GENERIC_ERROR",
        status_code: int = 500,
        details: Dict[str, Any] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationAPIError(APIError):
    """参数验证错误"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=422,
            details=details
        )


class NotFoundAPIError(APIError):
    """资源未找到错误"""
    def __init__(self, resource: str, identifier: str = None):
        message = f"{resource} not found"
        if identifier:
            message = f"{resource} '{identifier}' not found"
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "identifier": identifier}
        )


class ConflictAPIError(APIError):
    """资源冲突错误"""
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=409,
            details=details
        )


class RateLimitAPIError(APIError):
    """速率限制错误"""
    def __init__(self, message: str = "Rate limit exceeded", details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details
        )


class AuthenticationAPIError(APIError):
    """认证错误"""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_REQUIRED",
            status_code=401
        )


class AuthorizationAPIError(APIError):
    """授权错误"""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            error_code="INSUFFICIENT_PERMISSIONS",
            status_code=403
        )


def create_error_response(
    error_code: str,
    message: str,
    status_code: int = 500,
    details: Dict[str, Any] = None,
    request: Request = None
) -> JSONResponse:
    """
    创建标准化的错误响应
    
    Args:
        error_code: 错误代码
        message: 错误消息
        status_code: HTTP状态码
        details: 错误详情
        request: 请求对象
        
    Returns:
        标准格式的JSON错误响应
    """
    error_data = {
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": status_code
        }
    }
    
    if details:
        error_data["error"]["details"] = details
    
    if request:
        error_data["error"]["path"] = str(request.url.path)
        error_data["error"]["method"] = request.method
    
    return JSONResponse(
        status_code=status_code,
        content=error_data
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """
    处理自定义API错误
    """
    logger.error(
        f"API Error: {exc.error_code} - {exc.message}",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details
        }
    )
    
    return create_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request=request
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    处理HTTP异常
    """
    error_code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE"
    }
    
    error_code = error_code_map.get(exc.status_code, "HTTP_ERROR")
    
    logger.error(
        f"HTTP Error: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return create_error_response(
        error_code=error_code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request=request
    )


async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """
    处理Pydantic验证错误
    """
    # 解析验证错误详情
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(x) for x in error["loc"])
        errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"],
            "input": error.get("input")
        })
    
    logger.warning(
        f"Validation Error on {request.url.path}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": errors
        }
    )
    
    return create_error_response(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=422,
        details={"validation_errors": errors},
        request=request
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    处理未预期的异常
    """
    # 记录完整的异常信息
    error_id = f"err_{datetime.utcnow().timestamp()}"
    logger.error(
        f"Unhandled exception [{error_id}]: {str(exc)}",
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc()
        }
    )
    
    # 在开发环境返回详细错误，生产环境返回通用错误
    is_debug = logger.level <= logging.DEBUG
    
    if is_debug:
        details = {
            "error_id": error_id,
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc().split("\n")
        }
        message = str(exc)
    else:
        details = {"error_id": error_id}
        message = "An internal server error occurred"
    
    return create_error_response(
        error_code="INTERNAL_SERVER_ERROR",
        message=message,
        status_code=500,
        details=details,
        request=request
    )


def add_error_handlers(app: FastAPI) -> None:
    """
    向FastAPI应用添加错误处理器
    
    Args:
        app: FastAPI应用实例
    """
    # 自定义API错误
    app.add_exception_handler(APIError, api_error_handler)
    
    # HTTP异常
    app.add_exception_handler(HTTPException, http_error_handler)
    
    # 验证错误
    app.add_exception_handler(ValidationError, validation_error_handler)
    
    # 通用异常处理器（最后的保护措施）
    app.add_exception_handler(Exception, generic_error_handler)