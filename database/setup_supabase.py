#!/usr/bin/env python3
"""
Simple Supabase Database Setup Script
Run this after creating your Supabase project to set up the database schema
"""

import os
import sys
from database.database_setup import DatabaseSetup

def main():
    print("🚀 NMLS Database Setup for Supabase")
    print("=" * 50)
    
    # Get connection string from user
    connection_string = input("""
Please paste your Supabase connection string here.

You can find it in your Supabase dashboard:
1. Go to Settings → Database
2. Copy the 'URI' connection string
3. Make sure to replace '[YOUR-PASSWORD]' with your actual password

Connection string: """).strip()
    
    if not connection_string:
        print("❌ No connection string provided. Exiting.")
        return 1
    
    if '[YOUR-PASSWORD]' in connection_string:
        print("❌ Please replace '[YOUR-PASSWORD]' with your actual database password.")
        return 1
    
    print("\n🔧 Setting up database...")
    
    try:
        # Initialize and run database setup
        db_setup = DatabaseSetup(connection_string)
        db_setup.connect()
        
        print("✅ Connected to Supabase successfully!")
        
        # Create all tables and indexes
        print("📋 Creating tables...")
        db_setup.create_tables()
        
        print("📊 Creating summary views...")
        db_setup.create_summary_views()
        
        print("🧪 Testing connection...")
        db_setup.test_connection()
        
        db_setup.disconnect()
        
        print("\n🎉 Database setup complete!")
        print("\nYour database is ready to receive NMLS company data.")
        print("\nNext steps:")
        print("1. Run the HTML extractor: python nmls_html_extractor.py")
        print("2. The data will be automatically stored in your Supabase database")
        
        # Save connection string for future use
        with open('.env', 'w') as f:
            f.write(f"DATABASE_URL={connection_string}\n")
        
        print("\n💾 Connection string saved to .env file for future use.")
        
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        print("\nTroubleshooting tips:")
        print("1. Make sure your connection string is correct")
        print("2. Check that you replaced [YOUR-PASSWORD] with your actual password")
        print("3. Verify your Supabase project is fully initialized (takes 2-3 minutes)")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 