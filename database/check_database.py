#!/usr/bin/env python3
"""
Check Database Status
Simple script to view what's been loaded into the Supabase database
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

def main():
    # Get connection string
    connection_string = os.getenv('DATABASE_URL')
    if not connection_string:
        print("❌ DATABASE_URL environment variable not set")
        print("Run: export DATABASE_URL='your_connection_string'")
        return 1
    
    try:
        # Connect to database
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("🔍 Database Status Check")
        print("=" * 50)
        
        # Basic counts
        cursor.execute("SELECT COUNT(*) as count FROM companies;")
        company_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM licenses;")
        license_count = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM addresses;")
        address_count = cursor.fetchone()['count']
        
        print(f"📊 Total Records:")
        print(f"   Companies: {company_count:,}")
        print(f"   Licenses: {license_count:,}")
        print(f"   Addresses: {address_count:,}")
        
        if company_count > 0:
            print(f"\n📈 Average licenses per company: {license_count/company_count:.1f}")
            
            # Top business structures
            cursor.execute("""
                SELECT business_structure, COUNT(*) as count 
                FROM companies 
                WHERE business_structure IS NOT NULL
                GROUP BY business_structure 
                ORDER BY count DESC 
                LIMIT 5;
            """)
            
            print(f"\n🏢 Top Business Structures:")
            for row in cursor.fetchall():
                print(f"   {row['business_structure']}: {row['count']}")
            
            # Top license types
            cursor.execute("""
                SELECT license_type, COUNT(*) as count 
                FROM licenses 
                WHERE license_type IS NOT NULL
                GROUP BY license_type 
                ORDER BY count DESC 
                LIMIT 10;
            """)
            
            print(f"\n📋 Top License Types:")
            for row in cursor.fetchall():
                print(f"   {row['license_type']}: {row['count']}")
            
            # States
            cursor.execute("""
                SELECT street_address->>'state' as state, COUNT(*) as count 
                FROM companies 
                WHERE street_address->>'state' IS NOT NULL
                GROUP BY street_address->>'state' 
                ORDER BY count DESC;
            """)
            
            print(f"\n🗺️  Companies by State:")
            for row in cursor.fetchall():
                if row['state']:
                    print(f"   {row['state']}: {row['count']}")
        
        print(f"\n✅ Database check complete!")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 