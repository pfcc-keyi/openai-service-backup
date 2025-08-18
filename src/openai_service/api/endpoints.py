"""
FastAPI endpoints for OpenAI service.
"""
import time
from datetime import datetime
from typing import Dict, Any

import structlog
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..core.config import settings
from ..models.api import (
    LockAcquireRequest, LockAcquireResponse, LockReleaseRequest, LockReleaseResponse,
    HealthCheck, SystemInfo, ApiKeyPoolStatus, UsageStatsResponse, ErrorResponse,
    HealthStatus, LockStatus
)
from ..services.lock_manager import RedisLockManager, LockAcquisitionError, LockReleaseError

logger = structlog.get_logger(__name__)

# Security
security = HTTPBearer(auto_error=False)

# Global lock manager instance (will be initialized in main.py)
lock_manager: RedisLockManager = None

# Try to initialize lock manager immediately in this module
def _initialize_lock_manager_in_endpoints():
    """Initialize lock manager directly in endpoints module."""
    global lock_manager
    try:
        from ..services.lock_manager import RedisLockManager
        if lock_manager is None:
            lock_manager = RedisLockManager()
            lock_manager.initialize()
            logger.info("Lock manager initialized directly in endpoints module")
    except Exception as e:
        logger.warning("Failed to initialize lock manager in endpoints", error=str(e))

# Initialize immediately when this module is imported
_initialize_lock_manager_in_endpoints()

def get_lock_manager() -> RedisLockManager:
    """Dependency to get the lock manager instance."""
    if lock_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lock manager not initialized"
        )
    return lock_manager

def verify_service_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify service token for authentication."""
    if settings.dev_mode:
        # In development mode, accept dev-token or configured token
        if credentials and credentials.credentials in ["dev-token", settings.service_token]:
            return credentials.credentials
        # Also allow requests without token in dev mode
        return "dev-mode"
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if credentials.credentials != settings.service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return credentials.credentials

# Create router
router = APIRouter()

@router.post("/v1/lock/acquire")
async def acquire_lock(
    request: LockAcquireRequest,
    manager: RedisLockManager = Depends(get_lock_manager),
    token: str = Depends(verify_service_token)
) -> Dict[str, Any]:
    """
    Acquire a distributed lock for OpenAI API access.
    
    This endpoint implements the lock acquisition logic as shown in the sequence diagram:
    1. Receive lock request from labeling-service or json-service
    2. Use Redis Redlock to acquire distributed lock
    3. Assign API Key from pool
    4. Return lock information including API key
    """
    start_time = time.time()
    
    try:
        logger.info(
            "Lock acquisition requested",
            service_name=request.service_name,
            resource_type=request.resource_type,
            estimated_duration=request.estimated_duration,
            request_id=request.request_id,
            dimension=request.dimension,
            content_type=request.content_type,
            operation_type=request.operation_type,
            template=request.template
        )
        
        # Build context from request
        context = {}
        if request.dimension:
            context["dimension"] = request.dimension
        if request.content_type:
            context["content_type"] = request.content_type
        if request.operation_type:
            context["operation_type"] = request.operation_type
        if request.template:
            context["template"] = request.template
        if request.metadata:
            context.update(request.metadata)
        
        # Acquire lock using lock manager
        lock_info = await manager.acquire_lock(
            service_name=request.service_name,
            resource_type=request.resource_type.value,
            estimated_duration=request.estimated_duration,
            request_id=request.request_id,
            context=context
        )
        
        processing_time = time.time() - start_time
        
        logger.info(
            "Lock acquired successfully",
            lock_id=lock_info.lock_id,
            service_name=request.service_name,
            processing_time_ms=processing_time * 1000,
            expires_at=lock_info.expires_at.isoformat()
        )
        
        # Return response matching the expected format from existing services
        # NOTE: Existing services expect lock fields directly in response, not nested in lock_info
        return {
            "lock_id": lock_info.lock_id,
            "api_key": lock_info.api_key,
            "acquired_at": lock_info.acquired_at.isoformat(),
            "expires_at": lock_info.expires_at.isoformat(),
            "request_id": lock_info.request_id,
            "status": lock_info.status.value
        }
        
    except LockAcquisitionError as e:
        processing_time = time.time() - start_time
        logger.error(
            "Lock acquisition failed",
            service_name=request.service_name,
            error=str(e),
            processing_time_ms=processing_time * 1000
        )
        
        # Return error in a format that existing services can handle
        return {
            "error": str(e),
            "error_code": "LOCK_ACQUISITION_FAILED",
            "retry_after": 5,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            "Unexpected error during lock acquisition",
            service_name=request.service_name,
            error=str(e),
            processing_time_ms=processing_time * 1000
        )
        
        # Return error in a format that existing services can handle
        return {
            "error": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "retry_after": 10,
            "timestamp": datetime.utcnow().isoformat()
        }

@router.post("/v1/lock/release", response_model=LockReleaseResponse)
async def release_lock(
    request: LockReleaseRequest,
    manager: RedisLockManager = Depends(get_lock_manager),
    token: str = Depends(verify_service_token)
) -> LockReleaseResponse:
    """
    Release a distributed lock and record usage statistics.
    
    This endpoint implements the lock release logic as shown in the sequence diagram:
    1. Receive lock release request with usage stats
    2. Release the distributed lock from Redis
    3. Record usage statistics
    4. Return success confirmation
    """
    start_time = time.time()
    
    try:
        logger.info(
            "Lock release requested",
            lock_id=request.lock_id,
            service_name=request.service_name,
            has_usage_stats=bool(request.usage_stats)
        )
        
        # Release lock using lock manager
        success = await manager.release_lock(
            lock_id=request.lock_id,
            service_name=request.service_name,
            usage_stats=request.usage_stats
        )
        
        processing_time = time.time() - start_time
        
        if success:
            logger.info(
                "Lock released successfully",
                lock_id=request.lock_id,
                service_name=request.service_name,
                processing_time_ms=processing_time * 1000
            )
        else:
            logger.warning(
                "Lock release returned false (possibly already expired)",
                lock_id=request.lock_id,
                service_name=request.service_name
            )
        
        return LockReleaseResponse(
            success=success,
            lock_id=request.lock_id,
            usage_recorded=bool(request.usage_stats),
            timestamp=datetime.utcnow()
        )
        
    except LockReleaseError as e:
        processing_time = time.time() - start_time
        logger.error(
            "Lock release failed",
            lock_id=request.lock_id,
            service_name=request.service_name,
            error=str(e),
            processing_time_ms=processing_time * 1000
        )
        
        return LockReleaseResponse(
            success=False,
            lock_id=request.lock_id,
            error=str(e),
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            "Unexpected error during lock release",
            lock_id=request.lock_id,
            service_name=request.service_name,
            error=str(e),
            processing_time_ms=processing_time * 1000
        )
        
        return LockReleaseResponse(
            success=False,
            lock_id=request.lock_id,
            error="Internal server error",
            timestamp=datetime.utcnow()
        )

@router.get("/health", response_model=HealthCheck)
async def health_check(
    manager: RedisLockManager = Depends(get_lock_manager)
) -> HealthCheck:
    """
    Health check endpoint for service monitoring.
    """
    try:
        # Get health status from lock manager
        health_data = await manager.get_health_status()
        
        # Determine overall health status
        redis_healthy = health_data.get("redis_healthy", False)
        api_keys_count = health_data.get("api_keys_configured", 0)
        
        if redis_healthy and api_keys_count > 0:
            overall_status = HealthStatus.HEALTHY
        elif redis_healthy or api_keys_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.UNHEALTHY
        
        return HealthCheck(
            status=overall_status,
            version=settings.service_version,
            redis_status="healthy" if redis_healthy else "unhealthy",
            api_key_pool_status="healthy" if api_keys_count > 0 else "no_keys_configured",
            active_locks_count=health_data.get("active_locks_count", 0),
            available_api_keys=api_keys_count,
            total_api_keys=api_keys_count,
            uptime_seconds=health_data.get("uptime_seconds", 0),
            timestamp=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        
        return HealthCheck(
            status=HealthStatus.UNHEALTHY,
            version=settings.service_version,
            redis_status="error",
            api_key_pool_status="error",
            active_locks_count=0,
            available_api_keys=0,
            total_api_keys=0,
            timestamp=datetime.utcnow()
        )

@router.get("/system/info", response_model=SystemInfo)
async def get_system_info(
    token: str = Depends(verify_service_token)
) -> SystemInfo:
    """
    Get system information and configuration details.
    """
    try:
        # Mask sensitive information
        masked_redis_url = settings.redis_url
        if "@" in masked_redis_url:
            # Hide password in Redis URL
            parts = masked_redis_url.split("@")
            if len(parts) == 2:
                host_part = parts[1]
                protocol_part = parts[0].split("//")[0] + "//"
                masked_redis_url = f"{protocol_part}***@{host_part}"
        
        return SystemInfo(
            service_name=settings.service_name,
            version=settings.service_version,
            redis_url=masked_redis_url,
            max_lock_timeout=settings.max_lock_timeout,
            api_key_count=len(settings.get_api_key_list()),
            startup_time=datetime.utcnow(),  # This should be tracked globally
            timezone="UTC"
        )
        
    except Exception as e:
        logger.error("Failed to get system info", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system information"
        )

@router.get("/v1/locks/active")
async def get_active_locks(
    manager: RedisLockManager = Depends(get_lock_manager),
    token: str = Depends(verify_service_token)
) -> Dict[str, Any]:
    """
    Get currently active locks (admin endpoint).
    """
    try:
        active_locks = manager.get_active_locks()
        
        # Convert to serializable format
        locks_data = {}
        for lock_id, lock_info in active_locks.items():
            locks_data[lock_id] = {
                "lock_id": lock_info.lock_id,
                "service_name": "unknown",  # We don't store this in LockInfo
                "acquired_at": lock_info.acquired_at.isoformat(),
                "expires_at": lock_info.expires_at.isoformat(),
                "request_id": lock_info.request_id,
                "status": lock_info.status.value,
                "api_key_prefix": lock_info.api_key[:10] + "..." if lock_info.api_key else "N/A"
            }
        
        return {
            "success": True,
            "active_locks_count": len(locks_data),
            "locks": locks_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to get active locks", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active locks"
        )

@router.delete("/v1/locks/{lock_id}/force-release")
async def force_release_lock(
    lock_id: str,
    manager: RedisLockManager = Depends(get_lock_manager),
    token: str = Depends(verify_service_token)
) -> Dict[str, Any]:
    """
    Force release a specific lock (admin endpoint).
    """
    try:
        success = await manager.force_release_lock(lock_id, "Admin force release")
        
        if success:
            logger.warning("Lock force released by admin", lock_id=lock_id)
            return {
                "success": True,
                "message": f"Lock {lock_id} force released successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "success": False,
                "message": f"Lock {lock_id} not found or already released",
                "timestamp": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        logger.error("Failed to force release lock", lock_id=lock_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to force release lock {lock_id}"
        )

@router.post("/v1/maintenance/cleanup-expired")
async def cleanup_expired_locks(
    manager: RedisLockManager = Depends(get_lock_manager),
    token: str = Depends(verify_service_token)
) -> Dict[str, Any]:
    """
    Trigger cleanup of expired locks (admin endpoint).
    """
    try:
        await manager.cleanup_expired_locks()
        
        return {
            "success": True,
            "message": "Expired locks cleanup completed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to cleanup expired locks", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup expired locks"
        ) 

@router.get("/debug/lock-manager-status")
async def debug_lock_manager_status():
    """Debug endpoint to check lock manager status."""
    return {
        "lock_manager_is_none": lock_manager is None,
        "lock_manager_type": str(type(lock_manager)) if lock_manager else "None",
        "has_redis_pool": hasattr(lock_manager, 'redis_pool') and lock_manager.redis_pool is not None if lock_manager else False
    } 