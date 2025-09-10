"""
认证和授权中间件

提供API Key认证、JWT Token认证和权限控制
"""
import logging
from typing import Optional, List, Callable
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
import secrets

from fastapi import FastAPI, Request, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from .error_handler import AuthenticationAPIError, AuthorizationAPIError

logger = logging.getLogger(__name__)

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT设置
JWT_SECRET_KEY = secrets.token_urlsafe(32)  # 在生产环境中应该从环境变量获取
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_HOURS = 24

# HTTP Bearer认证方案
security = HTTPBearer(auto_error=False)


class AuthConfig:
    """认证配置"""
    
    def __init__(
        self,
        jwt_secret_key: str = JWT_SECRET_KEY,
        jwt_algorithm: str = JWT_ALGORITHM,
        jwt_expire_hours: int = JWT_ACCESS_TOKEN_EXPIRE_HOURS,
        api_keys: dict = None,
        public_paths: List[str] = None,
        require_auth: bool = False
    ):
        self.jwt_secret_key = jwt_secret_key
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expire_hours = jwt_expire_hours
        self.api_keys = api_keys or {}  # {api_key: {"user_id": str, "permissions": list}}
        self.public_paths = public_paths or [
            "/",
            "/api/health",
            "/api/docs",
            "/api/redoc",
            "/api/openapi.json"
        ]
        self.require_auth = require_auth


# 全局认证配置
auth_config = AuthConfig()


def create_access_token(data: dict) -> str:
    """
    创建JWT访问令牌
    
    Args:
        data: 要编码到令牌中的数据
        
    Returns:
        JWT访问令牌字符串
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=auth_config.jwt_expire_hours)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode,
        auth_config.jwt_secret_key,
        algorithm=auth_config.jwt_algorithm
    )
    return encoded_jwt


def verify_token(token: str) -> dict:
    """
    验证JWT令牌
    
    Args:
        token: JWT令牌字符串
        
    Returns:
        解码后的令牌数据
        
    Raises:
        AuthenticationAPIError: 令牌无效或过期
    """
    try:
        payload = jwt.decode(
            token,
            auth_config.jwt_secret_key,
            algorithms=[auth_config.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationAPIError("Token has expired")
    except jwt.JWTError:
        raise AuthenticationAPIError("Invalid token")


def verify_api_key(api_key: str) -> dict:
    """
    验证API Key
    
    Args:
        api_key: API密钥
        
    Returns:
        API Key信息字典
        
    Raises:
        AuthenticationAPIError: API Key无效
    """
    if api_key not in auth_config.api_keys:
        raise AuthenticationAPIError("Invalid API key")
    
    return auth_config.api_keys[api_key]


class User:
    """用户信息类"""
    
    def __init__(
        self,
        user_id: str,
        permissions: List[str] = None,
        auth_type: str = "unknown"
    ):
        self.user_id = user_id
        self.permissions = permissions or []
        self.auth_type = auth_type  # "jwt", "api_key", "anonymous"
    
    def has_permission(self, permission: str) -> bool:
        """检查用户是否具有指定权限"""
        return permission in self.permissions or "admin" in self.permissions


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: Optional[str] = Header(None)
) -> User:
    """
    获取当前用户信息
    
    Args:
        request: 请求对象
        credentials: HTTP Bearer认证凭据
        x_api_key: API Key头部
        
    Returns:
        用户信息对象
        
    Raises:
        AuthenticationAPIError: 认证失败
    """
    # 检查是否为公共路径
    if not auth_config.require_auth or request.url.path in auth_config.public_paths:
        return User(user_id="anonymous", auth_type="anonymous")
    
    # 尝试API Key认证
    if x_api_key:
        try:
            api_key_info = verify_api_key(x_api_key)
            return User(
                user_id=api_key_info["user_id"],
                permissions=api_key_info.get("permissions", []),
                auth_type="api_key"
            )
        except AuthenticationAPIError:
            pass  # 继续尝试其他认证方式
    
    # 尝试JWT Token认证
    if credentials:
        try:
            token_data = verify_token(credentials.credentials)
            return User(
                user_id=token_data.get("user_id", "unknown"),
                permissions=token_data.get("permissions", []),
                auth_type="jwt"
            )
        except AuthenticationAPIError:
            pass  # 继续尝试其他认证方式
    
    # 如果要求认证但没有有效凭据
    if auth_config.require_auth:
        raise AuthenticationAPIError("Valid authentication credentials required")
    
    # 返回匿名用户
    return User(user_id="anonymous", auth_type="anonymous")


def require_permission(permission: str):
    """
    权限要求装饰器
    
    Args:
        permission: 所需权限
        
    Returns:
        依赖函数
    """
    def permission_dependency(user: User = Depends(get_current_user)) -> User:
        if not user.has_permission(permission):
            raise AuthorizationAPIError(f"Permission '{permission}' required")
        return user
    
    return permission_dependency


def require_admin(user: User = Depends(get_current_user)) -> User:
    """要求管理员权限"""
    if not user.has_permission("admin"):
        raise AuthorizationAPIError("Administrator privileges required")
    return user


class AuthMiddleware(BaseHTTPMiddleware):
    """
    认证中间件
    
    在请求处理前进行认证检查并将用户信息添加到请求状态
    """
    
    async def dispatch(self, request: Request, call_next):
        try:
            # 尝试获取用户信息（不抛出异常，在依赖中处理）
            user = None
            
            # 检查API Key
            api_key = request.headers.get("X-API-Key")
            if api_key:
                try:
                    api_key_info = verify_api_key(api_key)
                    user = User(
                        user_id=api_key_info["user_id"],
                        permissions=api_key_info.get("permissions", []),
                        auth_type="api_key"
                    )
                except AuthenticationAPIError:
                    pass
            
            # 检查JWT Token
            if not user:
                auth_header = request.headers.get("Authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ", 1)[1]
                    try:
                        token_data = verify_token(token)
                        user = User(
                            user_id=token_data.get("user_id", "unknown"),
                            permissions=token_data.get("permissions", []),
                            auth_type="jwt"
                        )
                    except AuthenticationAPIError:
                        pass
            
            # 默认匿名用户
            if not user:
                user = User(user_id="anonymous", auth_type="anonymous")
            
            # 将用户信息添加到请求状态
            request.state.user = user
            
            # 记录认证信息（调试级别）
            logger.debug(
                f"Request authenticated: {user.auth_type} user {user.user_id}",
                extra={
                    "user_id": user.user_id,
                    "auth_type": user.auth_type,
                    "permissions": user.permissions,
                    "path": request.url.path,
                    "method": request.method
                }
            )
            
        except Exception as e:
            logger.error(f"Error in auth middleware: {e}")
            request.state.user = User(user_id="anonymous", auth_type="anonymous")
        
        response = await call_next(request)
        return response


def setup_auth_config(
    jwt_secret_key: str = None,
    api_keys: dict = None,
    require_auth: bool = False,
    public_paths: List[str] = None
) -> None:
    """
    配置认证设置
    
    Args:
        jwt_secret_key: JWT密钥
        api_keys: API密钥字典
        require_auth: 是否要求认证
        public_paths: 公共路径列表
    """
    global auth_config
    
    if jwt_secret_key:
        auth_config.jwt_secret_key = jwt_secret_key
    
    if api_keys:
        auth_config.api_keys = api_keys
    
    if require_auth is not None:
        auth_config.require_auth = require_auth
    
    if public_paths:
        auth_config.public_paths = public_paths
    
    logger.info(f"Authentication configured: require_auth={auth_config.require_auth}, api_keys={len(auth_config.api_keys)}")


def add_auth_middleware(app: FastAPI) -> None:
    """
    向FastAPI应用添加认证中间件
    
    Args:
        app: FastAPI应用实例
    """
    app.add_middleware(AuthMiddleware)
    logger.info("Authentication middleware added")


# 生成API密钥的工具函数
def generate_api_key() -> str:
    """生成新的API密钥"""
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)