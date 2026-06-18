"""
性能监控中间件
记录每个请求的处理时间和性能指标
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)


class PerformanceMonitorMiddleware(BaseHTTPMiddleware):
    """性能监控中间件"""
    
    # 需要监控的路径前缀
    MONITOR_PREFIXES = ("/api/", "/v1/")
    
    # 慢请求阈值（秒）
    SLOW_REQUEST_THRESHOLD = 2.0
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
        except Exception as exc:
            # 计算处理时间
            process_time = time.perf_counter() - start_time
            
            # 记录异常
            logger.error(
                f"请求异常 - 路径: {request.url.path}, "
                f"方法: {request.method}, "
                f"耗时: {process_time:.3f}s, "
                f"异常: {str(exc)[:200]}"
            )
            raise
        
        # 计算处理时间
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # 检查是否为慢请求
        if (process_time > self.SLOW_REQUEST_THRESHOLD and 
            any(request.url.path.startswith(prefix) for prefix in self.MONITOR_PREFIXES)):
            logger.warning(
                f"⚠️ 慢请求 - 路径: {request.url.path}, "
                f"方法: {request.method}, "
                f"耗时: {process_time:.3f}s, "
                f"状态码: {response.status_code}"
            )
        
        return response
