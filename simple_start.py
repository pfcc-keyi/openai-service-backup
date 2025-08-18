#!/usr/bin/env python3
"""
简化版 OpenAI Service 启动脚本 - 绕过复杂依赖问题
"""
import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    """使用 dev_start.py 的逻辑但加载 .env 文件"""
    print("🚀 启动 OpenAI Service (简化版)")
    print("=" * 50)
    
    # Load .env file
    try:
        from dotenv import load_dotenv
        if Path(".env").exists():
            load_dotenv()
            print("✅ 已加载 .env 配置文件")
        else:
            print("❌ 找不到 .env 文件")
            return False
    except ImportError:
        print("❌ 缺少 python-dotenv，请运行: pip install python-dotenv")
        return False
    
    # Check API key
    api_key = os.getenv("PRIMARY_OPENAI_API_KEY")
    if not api_key:
        print("❌ 请在 .env 文件中设置 PRIMARY_OPENAI_API_KEY")
        return False
    
    print(f"✅ API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Set DEV_MODE=true to bypass Redis dependency
    os.environ["DEV_MODE"] = "true"
    os.environ["PORT"] = "8004"
    
    print("✅ 使用开发模式启动（绕过 Redis）")
    print(f"✅ 服务将运行在: http://localhost:8004")
    print()
    
    # Import and run
    try:
        import uvicorn
        uvicorn.run(
            "openai_service.main:app",
            host="0.0.0.0",
            port=8004,
            reload=False,
            log_level="info"
        )
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False

if __name__ == "__main__":
    main() 