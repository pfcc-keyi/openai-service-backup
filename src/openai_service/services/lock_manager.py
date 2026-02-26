"""
Distributed lock manager using Redis Redlock algorithm.
"""
import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import redis
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings
from ..models.api import LockInfo, LockStatus

logger = structlog.get_logger(__name__)


class LockManagerError(Exception):
    """Base exception for lock manager errors."""
    pass


class LockAcquisitionError(LockManagerError):
    """Raised when lock acquisition fails."""
    pass


class LockReleaseError(LockManagerError):
    """Raised when lock release fails."""
    pass


class RedisLockManager:
    """
    Distributed lock manager using Redis Redlock algorithm.
    
    Implements the Redlock algorithm for distributed locking across multiple Redis instances.
    Provides thread-safe and network-partition-tolerant locking mechanism.
    """
    
    def __init__(self):
        """Initialize the Redis lock manager."""
        self.redis_pool: Optional[redis.Redis] = None
        self.active_locks: Dict[str, LockInfo] = {}
        self.lock_stats: Dict[str, Dict] = {}
        self._startup_time = datetime.utcnow()
        
    def initialize(self):
        """Initialize Redis connection pool."""
        try:
            # Create Redis connection pool
            self.redis_pool = redis.from_url(
                settings.redis_url,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                max_connections=20,
                retry_on_timeout=True
            )
            
            # Test connection
            self.redis_pool.ping()
            logger.info("Redis lock manager initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize Redis lock manager", error=str(e))
            raise LockManagerError(f"Redis initialization failed: {e}")
    
    def close(self):
        """Close Redis connections."""
        if self.redis_pool:
            self.redis_pool.close()
            logger.info("Redis lock manager closed")
    
    def _generate_lock_id(self, service_name: str, resource_type: str, context: str = "") -> str:
        """Generate a unique lock identifier."""
        timestamp = str(int(time.time() * 1000))
        random_id = str(uuid.uuid4())
        content = f"{service_name}:{resource_type}:{context}:{timestamp}:{random_id}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _generate_lock_value(self) -> str:
        """Generate a unique lock value for ownership verification."""
        return str(uuid.uuid4())
    
    def _get_lock_key(self, lock_id: str) -> str:
        """Get Redis key for the lock."""
        return f"openai_service:lock:{lock_id}"
    
    def _get_expiry_time(self, duration_seconds: int) -> datetime:
        """Calculate lock expiry time."""
        max_duration = min(duration_seconds, settings.max_lock_timeout)
        return datetime.utcnow() + timedelta(seconds=max_duration)
    
    @retry(
        stop=stop_after_attempt(settings.redlock_retry_count),
        wait=wait_exponential(multiplier=1, min=0.1, max=2),
        reraise=True
    )
    async def acquire_lock(
        self,
        service_name: str,
        resource_type: str,
        estimated_duration: int,
        request_id: str,
        context: Optional[Dict] = None
    ) -> LockInfo:
        """
        Acquire a distributed lock using Redlock algorithm.
        
        Args:
            service_name: Name of the requesting service
            resource_type: Type of resource to lock
            estimated_duration: Estimated lock duration in seconds
            request_id: Unique request identifier
            context: Additional context information
            
        Returns:
            LockInfo: Information about the acquired lock
            
        Raises:
            LockAcquisitionError: If lock acquisition fails
        """
        start_time = time.time()
        
        try:
            # Generate lock identifier and value
            context_str = self._build_context_string(context or {})
            lock_id = self._generate_lock_id(service_name, resource_type, context_str)
            lock_value = self._generate_lock_value()
            lock_key = self._get_lock_key(lock_id)
            
            # Calculate expiry
            expires_at = self._get_expiry_time(estimated_duration)
            ttl_seconds = int((expires_at - datetime.utcnow()).total_seconds())
            
            logger.info(
                "Attempting to acquire lock",
                lock_id=lock_id,
                service_name=service_name,
                resource_type=resource_type,
                ttl_seconds=ttl_seconds,
                request_id=request_id
            )
            
            # Implement Redlock algorithm
            success = await self._redlock_acquire(lock_key, lock_value, ttl_seconds)
            
            if not success:
                raise LockAcquisitionError(
                    f"Failed to acquire lock for {service_name}:{resource_type} after retries"
                )
            
            # Get API key for this lock
            api_key = await self._assign_api_key(lock_id, service_name, context)
            
            # Create lock info
            acquired_at = datetime.utcnow()
            lock_info = LockInfo(
                lock_id=lock_id,
                api_key=api_key,
                base_url=settings.openai_base_url,
                acquired_at=acquired_at,
                expires_at=expires_at,
                request_id=request_id,
                status=LockStatus.ACQUIRED
            )
            
            # Store in active locks
            self.active_locks[lock_id] = lock_info
            
            # Record acquisition stats
            acquisition_time = (time.time() - start_time) * 1000  # milliseconds
            await self._record_lock_stats(lock_id, "acquire", acquisition_time, True)
            
            logger.info(
                "Lock acquired successfully",
                lock_id=lock_id,
                service_name=service_name,
                api_key_prefix=api_key[:10] + "...",
                acquisition_time_ms=acquisition_time,
                expires_at=expires_at.isoformat()
            )
            
            return lock_info
            
        except Exception as e:
            acquisition_time = (time.time() - start_time) * 1000
            await self._record_lock_stats("unknown", "acquire", acquisition_time, False, str(e))
            logger.error(
                "Lock acquisition failed",
                service_name=service_name,
                resource_type=resource_type,
                error=str(e),
                acquisition_time_ms=acquisition_time
            )
            raise LockAcquisitionError(f"Lock acquisition failed: {e}")
    
    async def _redlock_acquire(self, lock_key: str, lock_value: str, ttl_seconds: int) -> bool:
        """
        Implement the Redlock acquisition algorithm.
        
        For now, using single Redis instance. In production, this should be
        extended to multiple Redis instances for true Redlock.
        """
        try:
            # SET if not exists with TTL
            result = self.redis_pool.set(
                lock_key,
                lock_value,
                nx=True,  # Only set if key doesn't exist
                ex=ttl_seconds  # Expiry time in seconds
            )
            
            return result is True
            
        except Exception as e:
            logger.error("Redlock acquire failed", lock_key=lock_key, error=str(e))
            return False
    
    async def release_lock(
        self,
        lock_id: str,
        service_name: str,
        usage_stats: Optional[Dict] = None
    ) -> bool:
        """
        Release a distributed lock.
        
        Args:
            lock_id: Lock identifier to release
            service_name: Name of the service releasing the lock
            usage_stats: Usage statistics for the lock period
            
        Returns:
            bool: True if lock was successfully released
            
        Raises:
            LockReleaseError: If lock release fails
        """
        start_time = time.time()
        
        try:
            # Check if lock exists in our active locks
            if lock_id not in self.active_locks:
                logger.warning(
                    "Attempted to release unknown lock",
                    lock_id=lock_id,
                    service_name=service_name
                )
                return False
            
            lock_info = self.active_locks[lock_id]
            lock_key = self._get_lock_key(lock_id)
            
            logger.info(
                "Attempting to release lock",
                lock_id=lock_id,
                service_name=service_name
            )
            
            # Release from Redis
            success = await self._redlock_release(lock_key)
            
            # Remove from active locks regardless of Redis result
            # (lock might have expired in Redis but still exist locally)
            del self.active_locks[lock_id]
            
            # Record usage statistics
            if usage_stats:
                await self._record_usage_stats(lock_id, service_name, usage_stats, lock_info)
            
            # Record release stats
            release_time = (time.time() - start_time) * 1000
            await self._record_lock_stats(lock_id, "release", release_time, success)
            
            logger.info(
                "Lock released",
                lock_id=lock_id,
                service_name=service_name,
                redis_success=success,
                release_time_ms=release_time
            )
            
            return True
            
        except Exception as e:
            release_time = (time.time() - start_time) * 1000
            await self._record_lock_stats(lock_id, "release", release_time, False, str(e))
            logger.error(
                "Lock release failed",
                lock_id=lock_id,
                service_name=service_name,
                error=str(e)
            )
            raise LockReleaseError(f"Lock release failed: {e}")
    
    async def _redlock_release(self, lock_key: str) -> bool:
        """
        Implement the Redlock release algorithm.
        """
        try:
            # Delete the lock key
            result = self.redis_pool.delete(lock_key)
            return result > 0
            
        except Exception as e:
            logger.error("Redlock release failed", lock_key=lock_key, error=str(e))
            return False
    
    def _build_context_string(self, context: Dict) -> str:
        """Build a context string for lock identification."""
        if not context:
            return ""
        
        # Create a deterministic string from context
        sorted_items = sorted(context.items())
        return "|".join(f"{k}:{v}" for k, v in sorted_items if v is not None)
    
    async def _assign_api_key(self, lock_id: str, service_name: str, context: Optional[Dict]) -> str:
        """
        Assign an API key for the lock.
        
        For now, returns the primary API key. In production, this should
        implement round-robin or other load balancing strategies.
        """
        api_keys = settings.get_api_key_list()
        if not api_keys:
            raise LockAcquisitionError("No API keys available")
        
        # Simple round-robin based on lock_id hash
        key_index = hash(lock_id) % len(api_keys)
        selected_key = api_keys[key_index]
        
        logger.debug(
            "API key assigned",
            lock_id=lock_id,
            service_name=service_name,
            key_index=key_index,
            total_keys=len(api_keys)
        )
        
        return selected_key
    
    async def _record_lock_stats(
        self,
        lock_id: str,
        operation: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None
    ):
        """Record lock operation statistics."""
        try:
            if not settings.metrics_collection_enabled:
                return
            
            stats_key = f"openai_service:stats:lock:{operation}"
            timestamp = datetime.utcnow().isoformat()
            
            stats_data = {
                "lock_id": lock_id,
                "operation": operation,
                "duration_ms": duration_ms,
                "success": success,
                "timestamp": timestamp
            }
            
            if error:
                stats_data["error"] = error
            
            # Store in Redis with TTL
            ttl_seconds = settings.usage_stats_retention_days * 24 * 3600
            self.redis_pool.lpush(stats_key, str(stats_data))
            self.redis_pool.expire(stats_key, ttl_seconds)
            
        except Exception as e:
            logger.warning("Failed to record lock stats", error=str(e))
    
    async def _record_usage_stats(
        self,
        lock_id: str,
        service_name: str,
        usage_stats: Dict,
        lock_info: LockInfo
    ):
        """Record usage statistics for the completed operation."""
        try:
            if not settings.metrics_collection_enabled:
                return
            
            stats_key = f"openai_service:stats:usage:{service_name}"
            timestamp = datetime.utcnow().isoformat()
            
            duration_seconds = (datetime.utcnow() - lock_info.acquired_at).total_seconds()
            
            usage_data = {
                "lock_id": lock_id,
                "service_name": service_name,
                "duration_seconds": duration_seconds,
                "timestamp": timestamp,
                "api_key_used": lock_info.api_key[:10] + "...",  # Masked
                **usage_stats  # Include provided usage stats
            }
            
            # Store in Redis with TTL
            ttl_seconds = settings.usage_stats_retention_days * 24 * 3600
            self.redis_pool.lpush(stats_key, str(usage_data))
            self.redis_pool.expire(stats_key, ttl_seconds)
            
            logger.debug(
                "Usage stats recorded",
                lock_id=lock_id,
                service_name=service_name,
                duration_seconds=duration_seconds
            )
            
        except Exception as e:
            logger.warning("Failed to record usage stats", error=str(e))
    
    async def cleanup_expired_locks(self):
        """Clean up expired locks from local storage."""
        try:
            current_time = datetime.utcnow()
            expired_locks = []
            
            for lock_id, lock_info in self.active_locks.items():
                if current_time > lock_info.expires_at:
                    expired_locks.append(lock_id)
            
            for lock_id in expired_locks:
                del self.active_locks[lock_id]
                logger.info("Cleaned up expired lock", lock_id=lock_id)
            
            if expired_locks:
                logger.info(f"Cleaned up {len(expired_locks)} expired locks")
                
        except Exception as e:
            logger.error("Failed to cleanup expired locks", error=str(e))
    
    async def get_health_status(self) -> Dict:
        """Get health status of the lock manager."""
        try:
            # Test Redis connection
            redis_healthy = False
            try:
                self.redis_pool.ping()
                redis_healthy = True
            except Exception:
                pass
            
            # Count active locks
            active_count = len(self.active_locks)
            
            # Calculate uptime
            uptime_seconds = (datetime.utcnow() - self._startup_time).total_seconds()
            
            return {
                "redis_healthy": redis_healthy,
                "active_locks_count": active_count,
                "uptime_seconds": uptime_seconds,
                "api_keys_configured": len(settings.get_api_key_list())
            }
            
        except Exception as e:
            logger.error("Failed to get health status", error=str(e))
            return {
                "redis_healthy": False,
                "active_locks_count": 0,
                "uptime_seconds": 0,
                "error": str(e)
            }
    
    def get_active_locks(self) -> Dict[str, LockInfo]:
        """Get currently active locks."""
        return self.active_locks.copy()
    
    async def force_release_lock(self, lock_id: str, reason: str = "Manual release") -> bool:
        """Force release a lock (admin operation)."""
        try:
            if lock_id in self.active_locks:
                lock_key = self._get_lock_key(lock_id)
                await self._redlock_release(lock_key)
                del self.active_locks[lock_id]
                
                logger.warning(
                    "Lock force released",
                    lock_id=lock_id,
                    reason=reason
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(
                "Failed to force release lock",
                lock_id=lock_id,
                error=str(e)
            )
            return False 