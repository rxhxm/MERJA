#!/usr/bin/env python3
"""
Enhanced Streamlit runner with comprehensive environment setup and monitoring.
For development use - loads environment variables and starts the Streamlit app.
"""

import os
import sys
import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_environment():
    """Load environment variables from .env file if it exists"""
    try:
        from dotenv import load_dotenv
        env_file = Path('.env')
        if env_file.exists():
            load_dotenv(env_file)
            logger.info("Loaded environment variables from .env file")
        else:
            logger.warning("No .env file found. Please create one with your configuration.")
            logger.info("Copy env.example to .env and fill in your actual values")
    except ImportError:
        logger.warning("python-dotenv not installed. Install with: pip install python-dotenv")

def validate_environment() -> bool:
    """Validate that required environment variables are set"""
    required_vars = ['DATABASE_URL']
    optional_vars = ['ANTHROPIC_API_KEY', 'SIXTYFOUR_API_KEY']
    
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
    
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
    
    if missing_required:
        logger.error(f"Missing required environment variables: {missing_required}")
        logger.error("Please set these in your .env file or environment")
        return False
    
    if missing_optional:
        logger.warning(f"Missing optional environment variables: {missing_optional}")
        logger.warning("Some features may not work without these")
    
    logger.info("Environment validation passed")
    return True

def check_database_connectivity():
    """Check if database is accessible"""
    try:
        import asyncpg
        import asyncio
        
        async def test_connection():
            try:
                conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
                await conn.close()
                return True
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                return False
        
        return asyncio.run(test_connection())
    except ImportError:
        logger.warning("asyncpg not installed. Cannot test database connectivity")
        return True
    except Exception as e:
        logger.error(f"Database connectivity check failed: {e}")
        return False

def main():
    """Main function to set up and run Streamlit"""
    logger.info("Starting NMLS Search & Intelligence Platform...")
    
    # Load environment
    load_environment()
    
    # Validate environment
    if not validate_environment():
        logger.error("Environment validation failed. Exiting.")
        sys.exit(1)
    
    # Check database connectivity
    if not check_database_connectivity():
        logger.error("Database connectivity check failed. Please verify your DATABASE_URL")
        sys.exit(1)
    
    # Run Streamlit
    try:
        logger.info("Starting Streamlit application...")
        cmd = [sys.executable, "-m", "streamlit", "run", "streamlit_app.py"]
        
        # Add custom port if specified
        port = os.getenv('STREAMLIT_SERVER_PORT', '8501')
        cmd.extend(["--server.port", port])
        
        # Add custom address if specified
        address = os.getenv('STREAMLIT_SERVER_ADDRESS', 'localhost')
        cmd.extend(["--server.address", address])
        
        logger.info(f"Running command: {' '.join(cmd)}")
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Failed to start Streamlit: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 