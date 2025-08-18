#!/usr/bin/env python3
"""
Development startup script for OpenAI service.

🔑 IMPORTANT: OpenAI Service is the CENTRAL API KEY MANAGER
Other services should NOT have OpenAI API keys configured!
"""
import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import uvicorn
from dotenv import load_dotenv

def main():
    """Start the OpenAI service in development mode."""
    print("🚀 Starting OpenAI Service in Development Mode")
    print("=" * 50)
    print("🔑 CENTRAL API KEY MANAGER for the entire system")
    print()
    
    # Load environment variables
    load_dotenv()
    
    # Set development mode if not already set
    if not os.getenv("DEV_MODE"):
        os.environ["DEV_MODE"] = "true"
    
    # Set default Redis URL for development
    if not os.getenv("REDIS_URL"):
        os.environ["REDIS_URL"] = "redis://localhost:6379"
    
    # Check critical environment variables
    if not os.getenv("PRIMARY_OPENAI_API_KEY"):
        print("❌ Error: PRIMARY_OPENAI_API_KEY environment variable is required")
        print()
        print("🔑 OpenAI Service manages ALL OpenAI API keys for the system.")
        print("📝 Please set your OpenAI API key:")
        print("   export PRIMARY_OPENAI_API_KEY=sk-your-openai-api-key-here")
        print()
        print("💡 Other services should NOT have OpenAI keys:")
        print("   labeling-service → DEV_MODE=false, OPENAI_SERVICE_URL=http://localhost:8004")
        print("   json-service     → DEV_MODE=false, OPENAI_SERVICE_URL=http://localhost:8004")
        print()
        sys.exit(1)
    
    # Display configuration
    print(f"✅ Development environment configured")
    print(f"   - DEV_MODE: {os.getenv('DEV_MODE', 'true')}")
    print(f"   - LOG_LEVEL: {os.getenv('LOG_LEVEL', 'DEBUG')}")
    print(f"   - REDIS_URL: {os.getenv('REDIS_URL', 'redis://localhost:6379')}")
    print(f"   - PRIMARY_OPENAI_API_KEY: {os.getenv('PRIMARY_OPENAI_API_KEY', '')[:20]}...")
    
    # Show additional keys if configured
    additional_keys = os.getenv('OPENAI_API_KEYS', '')
    if additional_keys:
        key_count = len([k for k in additional_keys.split(',') if k.strip()])
        print(f"   - ADDITIONAL_KEYS: {key_count} extra key(s) configured")
    
    print()
    print(f"📍 Service will be available at: http://localhost:{os.getenv('PORT', '8004')}")
    print(f"📖 API Documentation: http://localhost:{os.getenv('PORT', '8004')}/docs")
    print("🔑 Use 'dev-token' as Authorization Bearer token for testing")
    print()
    print("🎯 Next steps:")
    print("   1. Start this service (OpenAI Service)")
    print("   2. Configure other services to use DEV_MODE=false")
    print("   3. Test the distributed lock mechanism")
    print()
    
    # Start the service
    uvicorn.run(
        "openai_service.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8004")),
        reload=False,  # Disable reload to avoid env var inheritance issues
        log_level=os.getenv("LOG_LEVEL", "debug").lower()
    )

if __name__ == "__main__":
    main() 