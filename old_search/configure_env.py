#!/usr/bin/env python3
"""
Configuration Helper for Supabase Connection
This script helps set up your environment variables for the NMLS processing system.
"""

import os
from dotenv import load_dotenv

def check_env_setup():
    """Check if environment variables are properly set"""
    
    # Try to load from .env file
    load_dotenv()
    
    print("🔍 Checking Environment Configuration...")
    print("=" * 50)
    
    # Check DATABASE_URL
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        # Hide password for security
        safe_url = db_url.replace(db_url.split(':')[2].split('@')[0], '[HIDDEN]') if ':' in db_url else db_url
        print(f"✅ DATABASE_URL: {safe_url}")
    else:
        print("❌ DATABASE_URL: Not set")
        print("\n📝 To fix this, add to your .env file:")
        print("DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-PROJECT-ID].supabase.co:5432/postgres")
        return False
    
    # Check optional vars
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    print(f"📋 SUPABASE_URL: {'✅ Set' if supabase_url else '❌ Not set (optional)'}")
    print(f"📋 SUPABASE_KEY: {'✅ Set' if supabase_key else '❌ Not set (optional)'}")
    print(f"📋 OPENAI_API_KEY: {'✅ Set' if openai_key else '❌ Not set (optional)'}")
    
    return True

def provide_instructions():
    """Provide setup instructions"""
    print("\n" + "=" * 50)
    print("📚 SETUP INSTRUCTIONS")
    print("=" * 50)
    print("1. Go to your Supabase project dashboard")
    print("2. Navigate to Settings > Database") 
    print("3. Find 'Connection string' section")
    print("4. Copy the 'URI' format connection string")
    print("5. Replace [YOUR-PASSWORD] with your actual database password")
    print("6. Add it to your .env file as:")
    print("   DATABASE_URL=postgresql://postgres:your_password@your_project.supabase.co:5432/postgres")
    print("\n🚀 Then run: python configure_env.py")

if __name__ == "__main__":
    if not check_env_setup():
        provide_instructions()
    else:
        print("\n🎉 Environment configuration looks good!")
        print("🚀 Ready to proceed with database setup and processing!") 