"""
FastAPI主应用 - 模块化架构

提供应用创建、路由注册和中间件配置的核心功能
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

from .middleware.error_handler import add_error_handlers
from .middleware.rate_limiter import add_rate_limiter
from .middleware.auth import add_auth_middleware
from .routers import dataset, join, preset, progress, pivot
from ..services.sse_service import sse_service


def create_app(
    title: str = "Multi-Source Data Join API",
    description: str = "REST API for multi-source data joining with real-time progress tracking",
    version: str = "1.0.0",
    cors_origins: Optional[List[str]] = None,
    enable_docs: bool = True
) -> FastAPI:
    """
    创建配置完整的FastAPI应用实例
    
    Args:
        title: API标题
        description: API描述
        version: API版本
        cors_origins: 允许的CORS源列表，默认为["*"]
        enable_docs: 是否启用API文档，默认为True
        
    Returns:
        配置完整的FastAPI应用实例
    """
    # 创建FastAPI应用
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url="/api/docs" if enable_docs else None,
        redoc_url="/api/redoc" if enable_docs else None,
        openapi_url="/api/openapi.json" if enable_docs else None
    )
    
    # 配置CORS中间件
    if cors_origins is None:
        cors_origins = ["*"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 添加自定义中间件
    add_error_handlers(app)
    add_rate_limiter(app)
    add_auth_middleware(app)
    
    # 注册路由器
    register_routers(app)
    
    # 添加健康检查端点
    @app.get("/")
    async def root():
        """根路径健康检查"""
        return {"message": "Multi-Source Data Join API", "status": "ok"}
    
    @app.get("/api/health")
    async def health():
        """API健康检查"""
        return {"status": "ok", "version": version}
    
    # 添加启动和关闭事件处理器
    @app.on_event("startup")
    async def startup_event():
        """应用启动事件处理器"""
        try:
            await sse_service.initialize()
        except Exception as e:
            # 记录错误但不阻止应用启动
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to initialize SSE service: {e}")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """应用关闭事件处理器"""
        try:
            await sse_service.shutdown()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error during SSE service shutdown: {e}")
    
    return app


def register_routers(app: FastAPI) -> None:
    """
    注册所有API路由器
    
    Args:
        app: FastAPI应用实例
    """
    # 数据集管理路由
    app.include_router(
        dataset.router,
        prefix="/api/dataset",
        tags=["dataset"]
    )
    
    # 连接操作路由
    app.include_router(
        join.router,
        prefix="/api/join", 
        tags=["join"]
    )
    
    # 配置预设路由
    app.include_router(
        preset.router,
        prefix="/api/preset",
        tags=["preset"]
    )
    
    # 进度推送路由
    app.include_router(
        progress.router,
        prefix="/api/join",  # 与join路由共享前缀
        tags=["progress"]
    )
    
    # 透视分析路由
    app.include_router(
        pivot.router,
        prefix="/api/pivot",
        tags=["pivot"]
    )