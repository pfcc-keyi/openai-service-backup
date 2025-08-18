"""
Configuration management for OpenAI service.
"""
from typing import List, Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Service configuration
    service_name: str = Field(default="openai-service", env="SERVICE_NAME")
    service_version: str = Field(default="1.0.0", env="SERVICE_VERSION")
    
    # Server configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8004, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    
    # Development mode
    dev_mode: bool = Field(default=False, env="DEV_MODE")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Authentication
    service_token: str = Field(default="openai-service-token", env="SERVICE_TOKEN")
    
    # Redis configuration for distributed locks
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # OpenAI API Key pool configuration
    # 🔑 IMPORTANT: OpenAI Service manages the API key pool
    # Other services (labeling-service, json-service) should NOT have OpenAI keys
    # They get keys dynamically through the distributed lock mechanism
    openai_api_keys: List[str] = Field(default_factory=list, env="OPENAI_API_KEYS")
    primary_api_key: str = Field(default="", env="PRIMARY_OPENAI_API_KEY")
    
    # Lock configuration
    default_lock_timeout: int = Field(default=300, env="DEFAULT_LOCK_TIMEOUT")  # 5 minutes
    max_lock_timeout: int = Field(default=1800, env="MAX_LOCK_TIMEOUT")  # 30 minutes
    lock_acquire_timeout: int = Field(default=30, env="LOCK_ACQUIRE_TIMEOUT")  # 30 seconds
    
    # Redis Redlock configuration
    redlock_retry_count: int = Field(default=3, env="REDLOCK_RETRY_COUNT")
    redlock_retry_delay: float = Field(default=0.2, env="REDLOCK_RETRY_DELAY")
    redlock_validity_time: int = Field(default=10000, env="REDLOCK_VALIDITY_TIME")  # 10 seconds in ms
    
    # API Key rotation and health
    api_key_health_check_interval: int = Field(default=300, env="API_KEY_HEALTH_CHECK_INTERVAL")  # 5 minutes
    api_key_rotation_enabled: bool = Field(default=True, env="API_KEY_ROTATION_ENABLED")
    
    # Statistics and monitoring
    usage_stats_retention_days: int = Field(default=30, env="USAGE_STATS_RETENTION_DAYS")
    metrics_collection_enabled: bool = Field(default=True, env="METRICS_COLLECTION_ENABLED")
    
    # Request timeout configuration
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    
    # Health check
    health_check_timeout: int = Field(default=10, env="HEALTH_CHECK_TIMEOUT")

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_api_key_list(self) -> List[str]:
        """
        Get the complete list of API keys managed by this service.
        
        ⚠️  IMPORTANT: Only OpenAI Service should manage OpenAI API keys.
        Other services should request keys through the distributed lock mechanism.
        """
        keys = []
        if self.primary_api_key:
            keys.append(self.primary_api_key)
        if self.openai_api_keys:
            # Handle both comma-separated string and list
            if isinstance(self.openai_api_keys, str):
                additional_keys = [k.strip() for k in self.openai_api_keys.split(",") if k.strip()]
                keys.extend(additional_keys)
            else:
                keys.extend(self.openai_api_keys)
        return list(set(keys))  # Remove duplicates

    def validate_configuration(self) -> 'Settings':
        """
        Validate critical configuration.
        
        OpenAI Service MUST have API keys configured as it's the central key manager.
        """
        api_keys = self.get_api_key_list()
        if not api_keys:
            raise ValueError(
                "❌ OpenAI Service requires at least one API key to function.\n"
                "🔑 OpenAI Service is the CENTRAL API KEY MANAGER for the entire system.\n"
                "📝 Please configure:\n"
                "   - PRIMARY_OPENAI_API_KEY=sk-your-primary-key\n"
                "   - OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3 (optional additional keys)\n"
                "\n"
                "💡 Other services (labeling-service, json-service) should NOT have OpenAI keys.\n"
                "   They get keys dynamically through OpenAI Service's distributed lock mechanism."
            )
        
        # Validate key format
        for i, key in enumerate(api_keys):
            if not key.startswith('sk-'):
                raise ValueError(
                    f"❌ Invalid OpenAI API key format at position {i+1}: {key[:10]}...\n"
                    "🔑 OpenAI API keys must start with 'sk-'"
                )
                
        return self


# Global settings instance
settings = Settings().validate_configuration()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings 