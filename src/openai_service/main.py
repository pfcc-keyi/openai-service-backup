"""
Main FastAPI application for OpenAI service.
"""
import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram, Gauge
from fastapi.responses import Response

from .core.config import settings
from .api import endpoints
from .services.lock_manager import RedisLockManager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('openai_service_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('openai_service_request_duration_seconds', 'Request duration')
ACTIVE_LOCKS = Gauge('openai_service_active_locks', 'Number of active locks')
LOCK_ACQUISITION_DURATION = Histogram('openai_service_lock_acquisition_duration_seconds', 'Lock acquisition duration')

# Global variables
lock_manager: RedisLockManager = None
startup_time: datetime = None
cleanup_task: asyncio.Task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global lock_manager, startup_time, cleanup_task
    
    # Startup
    startup_time = datetime.utcnow()
    logger.info(
        "OpenAI Service starting up",
        version=settings.service_version,
        dev_mode=settings.dev_mode,
        redis_url=settings.redis_url.split('@')[-1] if '@' in settings.redis_url else settings.redis_url,
        api_keys_configured=len(settings.get_api_key_list())
    )
    
    try:
        # Initialize lock manager
        lock_manager = RedisLockManager()
        lock_manager.initialize()
        
        # Set global lock manager in endpoints module
        endpoints.lock_manager = lock_manager
        
        # Start background cleanup task
        cleanup_task = asyncio.create_task(periodic_cleanup())
        
        logger.info("OpenAI Service startup completed successfully")
        
    except Exception as e:
        logger.error("Failed to start OpenAI Service", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("OpenAI Service shutting down")
    
    try:
        # Cancel cleanup task
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close lock manager
        if lock_manager:
            lock_manager.close()
        
        logger.info("OpenAI Service shutdown completed")
        
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))

async def periodic_cleanup():
    """Periodic cleanup of expired locks."""
    while True:
        try:
            await asyncio.sleep(60)  # Run every minute
            if lock_manager:
                await lock_manager.cleanup_expired_locks()
                
                # Update metrics
                active_locks = lock_manager.get_active_locks()
                ACTIVE_LOCKS.set(len(active_locks))
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in periodic cleanup", error=str(e))

# Create FastAPI application
app = FastAPI(
    title="OpenAI Service",
    description="Distributed lock management and API key orchestration for OpenAI API access",
    version=settings.service_version,
    docs_url="/docs" if settings.dev_mode else None,
    redoc_url="/redoc" if settings.dev_mode else None,
    openapi_url="/openapi.json" if settings.dev_mode else None
    # lifespan=lifespan  # 移除这个参数
)

@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    global lock_manager, startup_time
    
    startup_time = datetime.utcnow()
    logger.info(
        "OpenAI Service starting up via startup event",
        version=settings.service_version,
        dev_mode=settings.dev_mode,
        redis_url=settings.redis_url.split('@')[-1] if '@' in settings.redis_url else settings.redis_url,
        api_keys_configured=len(settings.get_api_key_list())
    )
    
    try:
        # Initialize lock manager
        lock_manager = RedisLockManager()
        lock_manager.initialize()
        
        # Set global lock manager in endpoints module
        endpoints.lock_manager = lock_manager
        
        logger.info("OpenAI Service startup completed successfully via startup event")
        
    except Exception as e:
        logger.error("Failed to start OpenAI Service via startup event", error=str(e))
        raise

# Initialize lock manager immediately for testing
try:
    if endpoints.lock_manager is None:
        temp_lock_manager = RedisLockManager()
        temp_lock_manager.initialize()
        endpoints.lock_manager = temp_lock_manager
        logger.info("Lock manager initialized manually for immediate availability")
except Exception as e:
    logger.warning("Failed to initialize lock manager manually", error=str(e))

# Module-level initialization for immediate availability
def _initialize_lock_manager_immediately():
    """Initialize lock manager at module level."""
    try:
        temp_manager = RedisLockManager()
        temp_manager.initialize()
        endpoints.lock_manager = temp_manager
        logger.info("Lock manager initialized at module level")
        return True
    except Exception as e:
        logger.warning("Failed to initialize lock manager at module level", error=str(e))
        return False

# Try to initialize immediately when module is imported
if endpoints.lock_manager is None:
    _initialize_lock_manager_immediately()

# Configure CORS
if settings.dev_mode:
    # Development mode: more permissive for testing
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
else:
    # Production mode: restricted access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8001", "http://localhost:8002", "http://localhost:8003"],  # Known services
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Service-Token"],
    )

# Add request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests and track metrics."""
    start_time = time.time()
    method = request.method
    path = request.url.path
    
    # Process request
    try:
        response = await call_next(request)
        status_code = response.status_code
        
        # Record metrics
        REQUEST_COUNT.labels(method=method, endpoint=path, status=status_code).inc()
        REQUEST_DURATION.observe(time.time() - start_time)
        
        # Log request
        logger.info(
            "Request processed",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=(time.time() - start_time) * 1000,
            client_ip=request.client.host if request.client else "unknown"
        )
        
        return response
        
    except Exception as e:
        # Record error metrics
        REQUEST_COUNT.labels(method=method, endpoint=path, status=500).inc()
        REQUEST_DURATION.observe(time.time() - start_time)
        
        # Log error
        logger.error(
            "Request failed",
            method=method,
            path=path,
            error=str(e),
            duration_ms=(time.time() - start_time) * 1000
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Internal server error",
                "error_code": "INTERNAL_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

# Include API routes
app.include_router(endpoints.router, tags=["OpenAI Service"])

# Metrics endpoint
@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(
        "Unhandled exception",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "An unexpected error occurred",
            "error_code": "INTERNAL_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information."""
    global startup_time
    
    uptime_seconds = (datetime.utcnow() - startup_time).total_seconds() if startup_time else 0
    
    return {
        "service": "OpenAI Service",
        "version": settings.service_version,
        "status": "running",
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/health",
            "system_info": "/system/info",
            "acquire_lock": "POST /v1/lock/acquire",
            "release_lock": "POST /v1/lock/release",
            "active_locks": "/v1/locks/active",
            "metrics": "/metrics",
            "docs": "/docs" if settings.dev_mode else "disabled"
        }
    }

if __name__ == "__main__":
    # This is used for development only
    uvicorn.run(
        "openai_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.dev_mode,
        log_level=settings.log_level.lower(),
        workers=settings.workers if not settings.dev_mode else 1
    ) 