#!/usr/bin/env python3
"""
Debug why "banks in california" search returns 0 results
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def debug_banks_search():
    """Debug the banks search issue"""
    try:
        from search_api import db_manager, SearchFilters, SearchService, SortField, SortOrder
        await db_manager.connect()
        
        print("🔍 Debugging 'banks in california' search...")
        
        async with db_manager.pool.acquire() as conn:
            # First, check what tables exist
            print("\n0️⃣ Checking database structure:")
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            print(f"   Available tables: {[t['table_name'] for t in tables]}")
            
            # Test 1: Basic company count
            print("\n1️⃣ Testing basic company count:")
            total_count = await conn.fetchval("SELECT COUNT(*) FROM companies")
            print(f"   Total companies: {total_count}")
            
            # Test 2: Companies with "bank" in name
            print("\n2️⃣ Testing companies with 'bank' in name:")
            bank_count = await conn.fetchval("""
                SELECT COUNT(*) 
                FROM companies 
                WHERE company_name ILIKE '%bank%'
            """)
            print(f"   Companies with 'bank' in name: {bank_count}")
            
            if bank_count > 0:
                print("\n3️⃣ Sample bank companies:")
                samples = await conn.fetch("""
                    SELECT nmls_id, company_name
                    FROM companies 
                    WHERE company_name ILIKE '%bank%'
                    LIMIT 5
                """)
                for sample in samples:
                    print(f"   - {sample['company_name']} ({sample['nmls_id']})")
            
            # Test 3: Check if there's state information in licenses
            print("\n4️⃣ Checking state information in licenses:")
            state_info = await conn.fetch("""
                SELECT DISTINCT regulator, COUNT(*) as count
                FROM licenses 
                WHERE regulator IS NOT NULL
                GROUP BY regulator
                ORDER BY count DESC
                LIMIT 10
            """)
            print("   Regulators (likely states):")
            for state in state_info:
                print(f"     - {state['regulator']}: {state['count']} licenses")
            
            # Test 4: CA companies with "bank" in name using licenses table
            print("\n5️⃣ Testing CA companies with 'bank' using licenses:")
            ca_bank_query = """
                SELECT DISTINCT c.nmls_id, c.company_name
                FROM companies c
                JOIN licenses l ON c.nmls_id::text = l.nmls_id
                WHERE l.regulator ILIKE '%CA%' OR l.regulator ILIKE '%california%'
                AND c.company_name ILIKE '%bank%'
                LIMIT 5
            """
            ca_banks = await conn.fetch(ca_bank_query)
            print(f"   CA banks found: {len(ca_banks)}")
            for bank in ca_banks:
                print(f"     - {bank['company_name']} ({bank['nmls_id']})")
            
            # Test 5: Check what SearchFilters does with just "bank"
            print("\n6️⃣ Testing SearchFilters with just 'bank':")
            filters = SearchFilters(query="bank")
            count_query, count_params = SearchService.build_count_query(filters)
            print(f"   Generated query: {count_query}")
            print(f"   Parameters: {count_params}")
            
            search_count = await conn.fetchval(count_query, *count_params)
            print(f"   SearchFilters result for 'bank': {search_count}")
            
            # Test 6: Test with states filter
            print("\n7️⃣ Testing SearchFilters with CA state filter:")
            filters_ca = SearchFilters(states=["CA"])
            count_query_ca, count_params_ca = SearchService.build_count_query(filters_ca)
            ca_count = await conn.fetchval(count_query_ca, *count_params_ca)
            print(f"   CA companies: {ca_count}")
            
            # Test 7: Combined query + state
            print("\n8️⃣ Testing SearchFilters with 'bank' + CA:")
            filters_both = SearchFilters(query="bank", states=["CA"])
            count_query_both, count_params_both = SearchService.build_count_query(filters_both)
            both_count = await conn.fetchval(count_query_both, *count_params_both)
            print(f"   CA + bank: {both_count}")
            
        await db_manager.disconnect()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main debug function"""
    asyncio.run(debug_banks_search())

if __name__ == "__main__":
    main() 