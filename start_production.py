#!/usr/bin/env python3
"""
Production startup script for OpenAI service.

🔑 IMPORTANT: This is the CENTRAL API KEY MANAGER for the entire system.
Configure your OpenAI API keys here, not in other services!
"""
import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn

def setup_production_environment():
    """Configure production environment variables."""
    
    print("🚀 Starting OpenAI Service in Production Mode")
    print("=" * 50)
    print("🔑 CENTRAL API KEY MANAGER for the entire system")
    print()
    
    # Load .env file first if it exists
    try:
        from dotenv import load_dotenv
        if Path(".env").exists():
            load_dotenv()
            print("✅ Loaded configuration from .env file")
        else:
            print("ℹ️  No .env file found, using environment variables")
    except ImportError:
        print("ℹ️  dotenv not available, using environment variables only")
    
    # Check if API key is provided via environment variable (after loading .env)
    api_key = os.getenv("PRIMARY_OPENAI_API_KEY")
    
    if not api_key:
        print("❌ Error: PRIMARY_OPENAI_API_KEY environment variable is required")
        print()
        print("🔑 Please set your OpenAI API key using ONE of these methods:")
        print()
        print("📝 Method 1: Export environment variable")
        print("   export PRIMARY_OPENAI_API_KEY=sk-your-openai-api-key-here")
        print("   python3 start_production.py")
        print()
        print("📝 Method 2: Create .env file")
        print("   cp env.example .env")
        print("   # Edit .env file and set PRIMARY_OPENAI_API_KEY=sk-your-key")
        print("   python3 start_production.py")
        print()
        print("📝 Method 3: Inline setting")
        print("   PRIMARY_OPENAI_API_KEY=sk-your-key python3 start_production.py")
        print()
        print("💡 Security tip: Use .env file for persistent configuration")
        print("   echo '.env' >> .gitignore  # Don't commit API keys!")
        return False
    
    # Set production configuration
    production_config = {
        "SERVICE_NAME": "openai-service",
        "SERVICE_VERSION": "1.0.0", 
        "DEV_MODE": "false",  # Production mode
        "LOG_LEVEL": "INFO",
        "HOST": "0.0.0.0",
        "PORT": "8004",
        "WORKERS": "1",
        "SERVICE_TOKEN": "openai-service-production-token",
        
        # Redis configuration
        "REDIS_URL": "redis://localhost:6379",
        "REDIS_DB": "0",
        
        # Lock configuration
        "DEFAULT_LOCK_TIMEOUT": "300",
        "MAX_LOCK_TIMEOUT": "1800", 
        "LOCK_ACQUIRE_TIMEOUT": "30",
        
        # Redlock settings
        "REDLOCK_RETRY_COUNT": "3",
        "REDLOCK_RETRY_DELAY": "0.2",
        "REDLOCK_VALIDITY_TIME": "10000",
        
        # Monitoring
        "USAGE_STATS_RETENTION_DAYS": "30",
        "METRICS_COLLECTION_ENABLED": "true",
        
        # Timeouts
        "REQUEST_TIMEOUT": "30",
        "HEALTH_CHECK_TIMEOUT": "10"
    }
    
    # Apply configuration
    for key, value in production_config.items():
        if not os.getenv(key):
            os.environ[key] = value
    
    # Display configuration summary
    print()
    print("🎯 Production Configuration:")
    print(f"   - Service: {os.getenv('SERVICE_NAME', 'openai-service')}")
    print(f"   - Version: {os.getenv('SERVICE_VERSION', '1.0.0')}")
    print(f"   - Mode: Production (DEV_MODE=false)")
    print(f"   - Port: {os.getenv('PORT', '8004')}")
    print(f"   - Redis: {os.getenv('REDIS_URL', 'redis://localhost:6379')}")
    
    # Show API key status (masked)
    current_key = os.getenv("PRIMARY_OPENAI_API_KEY", "")
    if current_key:
        print(f"   - Primary API Key: {current_key[:10]}...{current_key[-4:]} ✅")
    
    # Show additional keys if configured
    additional_keys = os.getenv("OPENAI_API_KEYS", "")
    if additional_keys:
        key_count = len([k for k in additional_keys.split(',') if k.strip()])
        print(f"   - Additional Keys: {key_count} extra key(s) configured")
    
    print()
    print("🌐 Service Endpoints:")
    print(f"   - Main API: http://localhost:{os.getenv('PORT', '8004')}")
    print(f"   - Health Check: http://localhost:{os.getenv('PORT', '8004')}/health")
    print(f"   - System Info: http://localhost:{os.getenv('PORT', '8004')}/system/info")
    print(f"   - Metrics: http://localhost:{os.getenv('PORT', '8004')}/metrics")
    print()
    print("🔒 Authentication:")
    print(f"   - Service Token: {os.getenv('SERVICE_TOKEN', 'openai-service-production-token')}")
    print("   - Use as Authorization: Bearer <token>")
    print()
    print("🎯 Integration with Other Services:")
    print("   Configure labeling-service and json-service with:")
    print("     DEV_MODE=false")
    print(f"     OPENAI_SERVICE_URL=http://localhost:{os.getenv('PORT', '8004')}")
    print("     # Remove any OPENAI_API_KEY from those services!")
    print()
    
    return True

def check_redis_connection():
    """Check if Redis is available."""
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        r = redis.from_url(redis_url)
        r.ping()
        print("✅ Redis connection verified")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print()
        print("🔧 To start Redis:")
        print("   # On macOS with Homebrew:")
        print("   brew install redis")
        print("   brew services start redis")
        print()
        print("   # Or using Docker:")
        print("   docker run -d -p 6379:6379 redis:alpine")
        print()
        return False

def main():
    """Start OpenAI service in production mode."""
    
    # Setup environment
    if not setup_production_environment():
        sys.exit(1)
    
    # Check Redis
    if not check_redis_connection():
        print("⚠️  Warning: Redis not available. Service will fail to start.")
        print("   Please start Redis first, then restart this service.")
        sys.exit(1)
    
    print("🚀 Starting OpenAI Service...")
    print("   Press Ctrl+C to stop")
    print()
    
    # Start the service
    try:
        uvicorn.run(
            "openai_service.main:app",
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8004")),
            reload=False,  # No reload in production
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
            workers=int(os.getenv("WORKERS", "1"))
        )
    except KeyboardInterrupt:
        print("\n🛑 OpenAI Service stopped by user")
    except Exception as e:
        print(f"\n❌ Failed to start OpenAI Service: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 