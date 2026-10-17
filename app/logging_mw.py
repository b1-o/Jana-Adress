"""Middleware: логирует все API-запросы с таймингом."""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("jana.address")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        
        # Читаем body только для POST (для логирования)
        body_log = ""
        if request.method == "POST":
            body = await request.body()
            body_log = f" body={body[:200]}..."
            # Восстанавливаем тело для следующего обработчика
            async def receive():
                return {"type": "http.request", "body": body}
            request._receive = receive
        
        response = await call_next(request)
        
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %s (%.0fms)%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            body_log
        )
        return response
