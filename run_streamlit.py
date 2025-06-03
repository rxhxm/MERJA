#!/usr/bin/env python3
"""
Startup script for NMLS Search Intelligence Platform
Handles proper initialization and dependency checking before launching Streamlit.
"""

import os
import sys
import subprocess
import asyncio
from pathlib import Path

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_modules = [
        'streamlit',
        'pandas', 
        'plotly',
        'anthropic',
        'asyncpg',
        'pydantic',
        'fastapi'
    ]
    
    missing = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    
    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("📦 Installing missing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("✅ Dependencies installed")
    else:
        print("✅ All dependencies satisfied")

def check_environment():
    """Check environment variables and configuration"""
    required_env = ['DATABASE_URL']
    missing_env = []
    
    for env_var in required_env:
        if not os.getenv(env_var):
            missing_env.append(env_var)
    
    if missing_env:
        print(f"⚠️  Missing environment variables: {', '.join(missing_env)}")
        print("🔧 Setting default values...")
        
        # Set default DATABASE_URL if not provided
        if 'DATABASE_URL' in missing_env:
            os.environ['DATABASE_URL'] = 'postgresql://postgres:Ronin320320.@db.eissjxpcsxcktoanftjw.supabase.co:5432/postgres'
            print("✅ DATABASE_URL set to default")
    else:
        print("✅ Environment variables configured")

async def test_database_connection():
    """Test database connectivity"""
    try:
        import asyncpg
        DATABASE_URL = os.getenv('DATABASE_URL')
        
        print("🔌 Testing database connection...")
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Simple test query
        count = await conn.fetchval("SELECT COUNT(*) FROM companies LIMIT 1")
        await conn.close()
        
        print(f"✅ Database connected successfully (found {count:,} companies)")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("⚠️  The app will still launch but database features may not work")
        return False

def check_anthropic_api():
    """Check Claude API configuration"""
    api_key = os.getenv('ANTHROPIC_API_KEY', 'your-api-key-here')
    
    if api_key and api_key.startswith('sk-ant-'):
        print("✅ Claude API key configured")
        return True
    else:
        print("⚠️  Claude API key not found - natural language search may not work")
        return False

def main():
    """Main startup routine"""
    print("🚀 Starting NMLS Search Intelligence Platform")
    print("=" * 60)
    
    # Check dependencies
    check_dependencies()
    
    # Check environment
    check_environment()
    
    # Check Claude API
    check_anthropic_api()
    
    # Test database (async)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        db_ok = loop.run_until_complete(test_database_connection())
    except Exception as e:
        print(f"⚠️  Database test failed: {e}")
        db_ok = False
    finally:
        loop.close()
    
    print("\n" + "=" * 60)
    print("🎯 System Status Summary:")
    print("✅ Dependencies: Ready")
    print("✅ Environment: Configured")
    print(f"{'✅' if db_ok else '⚠️ '} Database: {'Connected' if db_ok else 'Warning'}")
    print("=" * 60)
    
    # Launch Streamlit
    print("\n🌟 Launching Streamlit app...")
    print("📱 App will open in your browser at: http://localhost:8501")
    print("🛑 Press Ctrl+C to stop the application")
    
    try:
        # Run Streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port=8501",
            "--server.headless=false",
            "--browser.gatherUsageStats=false"
        ])
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"❌ Failed to start Streamlit: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 