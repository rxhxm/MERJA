#!/usr/bin/env python3
"""
Database Inspection Tool
Analyzes the NMLS database to understand record counts and search limitations
"""

import os
import asyncio
import asyncpg
from typing import Dict, Any

# Get database URL
try:
    import streamlit as st
    DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
except (ImportError, Exception):
    DATABASE_URL = os.getenv('DATABASE_URL')

async def inspect_database():
    """Comprehensive database inspection"""
    
    if not DATABASE_URL:
        print("❌ No DATABASE_URL found. Please set it in environment or Streamlit secrets.")
        return
    
    print("🔍 NMLS Database Inspection")
    print("=" * 50)
    
    try:
        # Connect to database
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to database")
        
        # 1. Total record counts
        print("\n📊 TOTAL RECORD COUNTS:")
        print("-" * 30)
        
        companies_count = await conn.fetchval("SELECT COUNT(*) FROM companies")
        print(f"Companies: {companies_count:,}")
        
        licenses_count = await conn.fetchval("SELECT COUNT(*) FROM licenses")
        print(f"Licenses: {licenses_count:,}")
        
        addresses_count = await conn.fetchval("SELECT COUNT(*) FROM addresses")
        print(f"Addresses: {addresses_count:,}")
        
        # 2. New York specific analysis
        print("\n🗽 NEW YORK ANALYSIS:")
        print("-" * 30)
        
        # Companies with NY addresses
        ny_companies_by_address = await conn.fetchval("""
            SELECT COUNT(DISTINCT c.id)
            FROM companies c
            JOIN addresses a ON c.id = a.company_id
            WHERE UPPER(a.state) LIKE '%NY%' OR UPPER(a.state) LIKE '%NEW YORK%'
        """)
        print(f"Companies with NY addresses: {ny_companies_by_address:,}")
        
        # Companies with NY licenses
        ny_companies_by_license = await conn.fetchval("""
            SELECT COUNT(DISTINCT c.id)
            FROM companies c
            JOIN licenses l ON c.id = l.company_id
            WHERE UPPER(l.state) LIKE '%NY%' OR UPPER(l.state) LIKE '%NEW YORK%'
        """)
        print(f"Companies with NY licenses: {ny_companies_by_license:,}")
        
        # Companies that match "bank" keyword
        bank_companies = await conn.fetchval("""
            SELECT COUNT(DISTINCT c.id)
            FROM companies c
            WHERE UPPER(c.company_name) LIKE '%BANK%'
        """)
        print(f"Companies with 'BANK' in name: {bank_companies:,}")
        
        # NY companies with "bank" in name
        ny_bank_companies = await conn.fetchval("""
            SELECT COUNT(DISTINCT c.id)
            FROM companies c
            JOIN addresses a ON c.id = a.company_id
            WHERE (UPPER(a.state) LIKE '%NY%' OR UPPER(a.state) LIKE '%NEW YORK%')
            AND UPPER(c.company_name) LIKE '%BANK%'
        """)
        print(f"NY companies with 'BANK' in name: {ny_bank_companies:,}")
        
        # 3. Search query simulation (what your app does)
        print("\n🔍 SEARCH QUERY SIMULATION:")
        print("-" * 30)
        
        # This simulates your unified search query
        search_results = await conn.fetch("""
            WITH company_stats AS (
                SELECT
                    c.id as company_id,
                    c.nmls_id,
                    COUNT(l.license_id) as total_licenses,
                    COUNT(CASE WHEN l.active = true THEN 1 END) as active_licenses,
                    ARRAY_AGG(DISTINCT l.license_type) FILTER (WHERE l.license_type IS NOT NULL) as license_types,
                    ARRAY_AGG(DISTINCT SUBSTRING(a.state FROM 1 FOR 2)) FILTER (WHERE a.state IS NOT NULL) as states_licensed
                FROM companies c
                LEFT JOIN licenses l ON c.id = l.company_id
                LEFT JOIN addresses a ON c.id = a.company_id
                GROUP BY c.id, c.nmls_id
            )
            SELECT
                c.nmls_id,
                c.company_name,
                cs.states_licensed
            FROM companies c
            LEFT JOIN company_stats cs ON c.id = cs.company_id
            LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
            LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
            WHERE (c.company_name ILIKE '%bank%'
                   OR a.full_address ILIKE '%bank%'
                   OR am.full_address ILIKE '%bank%')
               OR (c.company_name ILIKE '%new york%'
                   OR a.full_address ILIKE '%new york%'
                   OR am.full_address ILIKE '%new york%')
            LIMIT 100
        """)
        
        print(f"Raw search results: {len(search_results)}")
        
        # Analyze states in results
        ny_in_results = []
        for row in search_results:
            states = row['states_licensed'] or []
            if 'NY' in states:
                ny_in_results.append(row)
        
        print(f"Results with NY in states_licensed: {len(ny_in_results)}")
        
        # 4. Address type analysis
        print("\n📍 ADDRESS TYPE ANALYSIS:")
        print("-" * 30)
        
        address_types = await conn.fetch("""
            SELECT address_type, COUNT(*) as count
            FROM addresses
            GROUP BY address_type
            ORDER BY count DESC
        """)
        
        for row in address_types:
            print(f"{row['address_type'] or 'NULL'}: {row['count']:,}")
        
        # 5. State format analysis
        print("\n🗺️ STATE FORMAT ANALYSIS:")
        print("-" * 30)
        
        state_samples = await conn.fetch("""
            SELECT DISTINCT state, COUNT(*) as count
            FROM addresses
            WHERE state IS NOT NULL
            GROUP BY state
            ORDER BY count DESC
            LIMIT 20
        """)
        
        for row in state_samples:
            print(f"'{row['state']}': {row['count']:,}")
        
        # 6. AI Query analysis simulation
        print("\n🤖 AI QUERY ANALYSIS SIMULATION:")
        print("-" * 30)
        
        # Check how AI might interpret "banks in new york"
        ai_style_search = await conn.fetch("""
            WITH company_stats AS (
                SELECT
                    c.id as company_id,
                    c.nmls_id,
                    COUNT(l.license_id) as total_licenses,
                    COUNT(CASE WHEN l.active = true THEN 1 END) as active_licenses,
                    ARRAY_AGG(DISTINCT l.license_type) FILTER (WHERE l.license_type IS NOT NULL) as license_types,
                    ARRAY_AGG(DISTINCT SUBSTRING(a.state FROM 1 FOR 2)) FILTER (WHERE a.state IS NOT NULL) as states_licensed
                FROM companies c
                LEFT JOIN licenses l ON c.id = l.company_id
                LEFT JOIN addresses a ON c.id = a.company_id
                GROUP BY c.id, c.nmls_id
            )
            SELECT
                c.nmls_id,
                c.company_name,
                c.business_structure,
                cs.total_licenses,
                cs.license_types,
                cs.states_licensed
            FROM companies c
            LEFT JOIN company_stats cs ON c.id = cs.company_id
            LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
            LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
            WHERE (c.company_name ILIKE '%bank%'
                   OR a.full_address ILIKE '%bank%'
                   OR am.full_address ILIKE '%bank%')
            ORDER BY c.company_name
        """)
        
        print(f"Companies with 'bank' keyword: {len(ai_style_search)}")
        
        # Filter for those with NY
        ny_filtered = [r for r in ai_style_search if r['states_licensed'] and 'NY' in r['states_licensed']]
        print(f"Of those, with NY in states: {len(ny_filtered)}")
        
        # Show sample results
        print("\n📋 SAMPLE RESULTS:")
        print("-" * 30)
        for i, result in enumerate(ny_filtered[:10]):
            print(f"{i+1}. {result['company_name']} (NMLS: {result['nmls_id']})")
            print(f"   States: {result['states_licensed']}")
            print(f"   Licenses: {result['total_licenses']}")
            if result['license_types']:
                print(f"   Types: {result['license_types'][:3]}")  # First 3 types
            print()
        
        await conn.close()
        print("✅ Database inspection complete")
        
    except Exception as e:
        print(f"❌ Error during inspection: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(inspect_database()) 