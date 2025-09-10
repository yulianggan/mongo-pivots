"""
速率限制中间件

基于内存和Redis的API请求速率限制
"""
import asyncio
import time
from typing import Dict, Tuple, Optional, Callable
from collections import defaultdict, deque
import logging

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .error_handler import RateLimitAPIError

logger = logging.getLogger(__name__)


class MemoryRateLimiter:
    """
    基于内存的速率限制器
    
    使用滑动窗口算法实现速率限制
    """
    
    def __init__(self):
        self.clients: Dict[str, deque] = defaultdict(deque)
        self.lock = asyncio.Lock()
    
    async def is_allowed(
        self,
        client_id: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, Dict[str, any]]:
        """
        检查请求是否在速率限制内
        
        Args:
            client_id: 客户端标识符
            max_requests: 窗口内最大请求数
            window_seconds: 时间窗口（秒）
            
        Returns:
            (是否允许, 限制信息字典)
        """
        async with self.lock:
            now = time.time()
            window_start = now - window_seconds
            
            # 清理过期的请求记录
            client_requests = self.clients[client_id]
            while client_requests and client_requests[0] < window_start:
                client_requests.popleft()
            
            current_count = len(client_requests)
            
            # 检查是否超过限制
            if current_count >= max_requests:
                # 计算重试延迟
                oldest_request = client_requests[0] if client_requests else now
                retry_after = int(oldest_request + window_seconds - now) + 1
                
                return False, {
                    "current_count": current_count,
                    "max_requests": max_requests,
                    "window_seconds": window_seconds,
                    "retry_after": retry_after
                }
            
            # 记录此次请求
            client_requests.append(now)
            
            return True, {
                "current_count": current_count + 1,
                "max_requests": max_requests,
                "window_seconds": window_seconds,
                "remaining": max_requests - current_count - 1
            }
    
    async def cleanup_expired(self, max_idle_seconds: int = 3600):
        """
        清理长时间未活动的客户端记录
        
        Args:
            max_idle_seconds: 最大空闲时间（秒）
        """
        async with self.lock:
            now = time.time()
            expired_clients = []
            
            for client_id, requests in self.clients.items():
                if not requests or (now - requests[-1]) > max_idle_seconds:
                    expired_clients.append(client_id)
            
            for client_id in expired_clients:
                del self.clients[client_id]
            
            if expired_clients:
                logger.info(f"Cleaned up {len(expired_clients)} expired rate limit records")


# 全局速率限制器实例
memory_limiter = MemoryRateLimiter()


class RateLimitRule:
    """速率限制规则"""
    
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        path_pattern: str = "*",
        methods: list = None,
        client_identifier: Callable[[Request], str] = None
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.path_pattern = path_pattern
        self.methods = methods or ["*"]
        self.client_identifier = client_identifier or self._default_client_identifier
    
    def _default_client_identifier(self, request: Request) -> str:
        """默认的客户端标识符：IP地址"""
        # 考虑代理服务器的情况
        client_ip = request.headers.get("X-Forwarded-For")
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return client_ip
    
    def matches(self, request: Request) -> bool:
        """检查规则是否匹配当前请求"""
        # 检查HTTP方法
        if "*" not in self.methods and request.method not in self.methods:
            return False
        
        # 检查路径模式
        if self.path_pattern == "*":
            return True
        
        # 简单的通配符匹配
        path = request.url.path
        if self.path_pattern.endswith("*"):
            return path.startswith(self.path_pattern[:-1])
        elif self.path_pattern.startswith("*"):
            return path.endswith(self.path_pattern[1:])
        else:
            return path == self.path_pattern


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    速率限制中间件
    """
    
    def __init__(self, app, rules: list = None, default_rule: RateLimitRule = None):
        super().__init__(app)
        self.rules = rules or []
        self.default_rule = default_rule
        
        # 启动清理任务
        asyncio.create_task(self._cleanup_task())
    
    async def dispatch(self, request: Request, call_next):
        # 查找适用的规则
        applicable_rule = self._find_applicable_rule(request)
        
        if applicable_rule is None:
            # 没有适用的规则，直接通过
            return await call_next(request)
        
        # 获取客户端标识符
        client_id = applicable_rule.client_identifier(request)
        
        # 检查速率限制
        allowed, limit_info = await memory_limiter.is_allowed(
            client_id=client_id,
            max_requests=applicable_rule.max_requests,
            window_seconds=applicable_rule.window_seconds
        )
        
        if not allowed:
            logger.warning(
                f"Rate limit exceeded for client {client_id} on {request.url.path}",
                extra={
                    "client_id": client_id,
                    "path": request.url.path,
                    "method": request.method,
                    "limit_info": limit_info
                }
            )
            raise RateLimitAPIError(
                message=f"Rate limit exceeded. Try again in {limit_info['retry_after']} seconds.",
                details=limit_info
            )
        
        # 执行请求
        response = await call_next(request)
        
        # 添加速率限制头部
        response.headers["X-RateLimit-Limit"] = str(applicable_rule.max_requests)
        response.headers["X-RateLimit-Window"] = str(applicable_rule.window_seconds)
        response.headers["X-RateLimit-Remaining"] = str(limit_info.get("remaining", 0))
        
        return response
    
    def _find_applicable_rule(self, request: Request) -> Optional[RateLimitRule]:
        """查找适用于当前请求的规则"""
        # 优先匹配具体规则
        for rule in self.rules:
            if rule.matches(request):
                return rule
        
        # 使用默认规则
        return self.default_rule
    
    async def _cleanup_task(self):
        """定期清理过期的客户端记录"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                await memory_limiter.cleanup_expired()
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup task: {e}")


def create_default_rate_limit_rules() -> list:
    """
    创建默认的速率限制规则
    
    Returns:
        默认速率限制规则列表
    """
    return [
        # 文件上传限制更严格
        RateLimitRule(
            max_requests=10,
            window_seconds=60,
            path_pattern="/api/dataset/upload*",
            methods=["POST"]
        ),
        
        # 连接执行限制
        RateLimitRule(
            max_requests=20,
            window_seconds=60,
            path_pattern="/api/join/execute*",
            methods=["POST"]
        ),
        
        # API文档访问限制
        RateLimitRule(
            max_requests=30,
            window_seconds=60,
            path_pattern="/api/docs*",
            methods=["GET"]
        ),
        
        # 预览和状态查询相对宽松
        RateLimitRule(
            max_requests=100,
            window_seconds=60,
            path_pattern="/api/*/preview*",
            methods=["GET", "POST"]
        ),
        
        RateLimitRule(
            max_requests=100,
            window_seconds=60,
            path_pattern="/api/join/status*",
            methods=["GET"]
        )
    ]


def add_rate_limiter(
    app: FastAPI,
    rules: list = None,
    default_max_requests: int = 100,
    default_window_seconds: int = 60
) -> None:
    """
    向FastAPI应用添加速率限制中间件
    
    Args:
        app: FastAPI应用实例
        rules: 自定义速率限制规则列表
        default_max_requests: 默认最大请求数
        default_window_seconds: 默认时间窗口
    """
    if rules is None:
        rules = create_default_rate_limit_rules()
    
    default_rule = RateLimitRule(
        max_requests=default_max_requests,
        window_seconds=default_window_seconds
    )
    
    middleware = RateLimitMiddleware(
        app=app,
        rules=rules,
        default_rule=default_rule
    )
    
    app.add_middleware(RateLimitMiddleware, rules=rules, default_rule=default_rule)
    
    logger.info(f"Rate limiter added with {len(rules)} custom rules and default limit of {default_max_requests} requests per {default_window_seconds} seconds")