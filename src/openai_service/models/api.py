"""
Pydantic models for OpenAI service API requests and responses.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from pydantic import BaseModel, Field


# Enums
class LockStatus(str, Enum):
    """Lock status enumeration."""
    ACQUIRED = "acquired"
    FAILED = "failed"
    EXPIRED = "expired"
    RELEASED = "released"


class ResourceType(str, Enum):
    """Resource type enumeration."""
    OPENAI_API = "openai_api"


class HealthStatus(str, Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


# Lock Request Models
class LockAcquireRequest(BaseModel):
    """Request model for acquiring a distributed lock."""
    service_name: str = Field(..., description="Name of the requesting service")
    resource_type: ResourceType = Field(default=ResourceType.OPENAI_API, description="Type of resource to lock")
    
    # Context information (from labeling-service)
    dimension: Optional[str] = Field(None, description="Labeling dimension (for labeling-service)")
    content_type: Optional[str] = Field(None, description="Content type being processed")
    
    # Context information (from json-service)  
    operation_type: Optional[str] = Field(None, description="Operation type (e.g., json_conversion)")
    template: Optional[str] = Field(None, description="Template being used")
    
    # Lock configuration
    estimated_duration: int = Field(default=300, description="Estimated lock duration in seconds")
    request_id: str = Field(..., description="Unique request identifier")
    
    # Optional metadata for future use
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context metadata")


class LockReleaseRequest(BaseModel):
    """Request model for releasing a distributed lock."""
    lock_id: str = Field(..., description="Lock identifier to release")
    service_name: str = Field(..., description="Name of the service releasing the lock")
    usage_stats: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Usage statistics")


# Lock Response Models
class LockInfo(BaseModel):
    """Lock information model."""
    lock_id: str = Field(..., description="Unique lock identifier")
    api_key: str = Field(..., description="Assigned OpenAI API key")
    acquired_at: datetime = Field(..., description="Lock acquisition timestamp")
    expires_at: datetime = Field(..., description="Lock expiration timestamp")
    request_id: str = Field(..., description="Original request identifier")
    status: LockStatus = Field(default=LockStatus.ACQUIRED, description="Current lock status")


class LockAcquireResponse(BaseModel):
    """Response model for lock acquisition."""
    success: bool = Field(..., description="Whether lock acquisition was successful")
    lock_info: Optional[LockInfo] = Field(None, description="Lock information if successful")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_code: Optional[str] = Field(None, description="Error code for programmatic handling")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retry")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


class LockReleaseResponse(BaseModel):
    """Response model for lock release."""
    success: bool = Field(..., description="Whether lock release was successful")
    lock_id: str = Field(..., description="Released lock identifier")
    usage_recorded: bool = Field(default=False, description="Whether usage statistics were recorded")
    error: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")


# Health and Status Models
class HealthCheck(BaseModel):
    """Health check response model."""
    status: HealthStatus = Field(..., description="Overall service health status")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    
    # Component health details
    redis_status: str = Field(..., description="Redis connection status")
    api_key_pool_status: str = Field(..., description="API key pool status")
    active_locks_count: int = Field(default=0, description="Number of active locks")
    
    # Resource availability
    available_api_keys: int = Field(default=0, description="Number of available API keys")
    total_api_keys: int = Field(default=0, description="Total number of configured API keys")
    
    # Performance metrics
    avg_lock_acquire_time_ms: Optional[float] = Field(None, description="Average lock acquisition time")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime in seconds")


class SystemInfo(BaseModel):
    """System information model."""
    service_name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    build_time: Optional[str] = Field(None, description="Build timestamp")
    git_commit: Optional[str] = Field(None, description="Git commit hash")
    
    # Configuration info
    redis_url: str = Field(..., description="Redis connection URL (masked)")
    max_lock_timeout: int = Field(..., description="Maximum allowed lock timeout")
    api_key_count: int = Field(..., description="Number of configured API keys")
    
    # Runtime info
    startup_time: datetime = Field(..., description="Service startup timestamp")
    timezone: str = Field(..., description="Server timezone")


# Usage Statistics Models
class UsageStats(BaseModel):
    """Usage statistics model."""
    service_name: str = Field(..., description="Service that used the resource")
    operation_type: Optional[str] = Field(None, description="Type of operation performed")
    success: bool = Field(..., description="Whether the operation was successful")
    duration_seconds: float = Field(..., description="Operation duration")
    tokens_used: Optional[int] = Field(None, description="OpenAI tokens consumed")
    api_key_id: str = Field(..., description="API key identifier used")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Usage timestamp")


class UsageStatsResponse(BaseModel):
    """Usage statistics response model."""
    total_requests: int = Field(..., description="Total number of requests")
    successful_requests: int = Field(..., description="Number of successful requests")
    failed_requests: int = Field(..., description="Number of failed requests")
    total_tokens_used: int = Field(default=0, description="Total tokens consumed")
    avg_duration_seconds: float = Field(..., description="Average operation duration")
    
    # Breakdown by service
    by_service: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Stats breakdown by service")
    
    # Time range
    start_time: datetime = Field(..., description="Statistics start time")
    end_time: datetime = Field(..., description="Statistics end time")


# API Key Management Models
class ApiKeyInfo(BaseModel):
    """API key information model."""
    key_id: str = Field(..., description="API key identifier")
    masked_key: str = Field(..., description="Masked API key for display")
    status: str = Field(..., description="API key status")
    last_used: Optional[datetime] = Field(None, description="Last usage timestamp")
    usage_count: int = Field(default=0, description="Total usage count")
    error_count: int = Field(default=0, description="Error count")
    is_primary: bool = Field(default=False, description="Whether this is the primary key")


class ApiKeyPoolStatus(BaseModel):
    """API key pool status model."""
    total_keys: int = Field(..., description="Total number of API keys")
    healthy_keys: int = Field(..., description="Number of healthy API keys")
    degraded_keys: int = Field(..., description="Number of degraded API keys")
    failed_keys: int = Field(..., description="Number of failed API keys")
    keys: List[ApiKeyInfo] = Field(default_factory=list, description="Individual key information")


# Error Response Models
class ErrorResponse(BaseModel):
    """Standard error response model."""
    success: bool = Field(default=False, description="Always false for errors")
    error: str = Field(..., description="Human-readable error message")
    error_code: str = Field(..., description="Machine-readable error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(None, description="Request ID for tracing") 