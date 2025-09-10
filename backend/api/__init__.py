"""
API模块 - REST API核心框架

提供FastAPI应用的路由组织、中间件管理和API基础设施
"""

from .main import create_app

__all__ = ['create_app']