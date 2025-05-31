#!/usr/bin/env python3
import asyncio
from search_api import db_manager, SearchFilters, SearchService

async def test_database():
    try:
        print("🔌 Connecting to database...")
        await db_manager.connect()
        print("✅ Connected!")
        
        async with db_manager.pool.acquire() as conn:
            # Test basic company count
            count = await conn.fetchval('SELECT COUNT(*) FROM companies')
            print(f"📊 Total companies in database: {count}")
            
            # Test a few sample companies
            companies = await conn.fetch('SELECT company_name, nmls_id FROM companies LIMIT 5')
            print("📋 Sample companies:")
            for company in companies:
                print(f"  - {company['company_name']} ({company['nmls_id']})")
            
            # Check what license types exist
            licenses = await conn.fetch('SELECT DISTINCT license_type FROM licenses WHERE license_type IS NOT NULL ORDER BY license_type LIMIT 50')
            print("📜 Available license types:")
            personal_loan_licenses = []
            mortgage_licenses = []
            for lic in licenses:
                license_type = lic['license_type']
                print(f"  - {license_type}")
                if any(term in license_type.lower() for term in ['consumer', 'personal', 'credit', 'finance', 'loan', 'installment', 'small']):
                    if not any(term in license_type.lower() for term in ['mortgage', 'real estate', 'home']):
                        personal_loan_licenses.append(license_type)
                if any(term in license_type.lower() for term in ['mortgage', 'home']):
                    mortgage_licenses.append(license_type)
            
            print(f"\n🎯 Potential Personal Loan Licenses ({len(personal_loan_licenses)}):")
            for lic in personal_loan_licenses:
                print(f"  - {lic}")
            
            print(f"\n🏠 Mortgage Licenses ({len(mortgage_licenses)}):")
            for lic in mortgage_licenses[:10]:  # Show first 10
                print(f"  - {lic}")
            
            # Test search with actual license types
            if personal_loan_licenses:
                pl_filters = SearchFilters(license_types=personal_loan_licenses[:5], states=["CA"])
                pl_count_query, pl_count_params = SearchService.build_count_query(pl_filters)
                pl_count = await conn.fetchval(pl_count_query, *pl_count_params)
                print(f"\n🔍 CA companies with personal loan licenses: {pl_count}")
            
            # Search for companies with finance-related names
            finance_companies = await conn.fetch("""
                SELECT company_name, nmls_id FROM companies 
                WHERE company_name ILIKE '%finance%' 
                OR company_name ILIKE '%loan%'
                OR company_name ILIKE '%credit%'
                LIMIT 10
            """)
            print("🏦 Finance-related companies:")
            for company in finance_companies:
                print(f"  - {company['company_name']} ({company['nmls_id']})")
            
            # Test search query
            filters = SearchFilters(query="finance")
            count_query, count_params = SearchService.build_count_query(filters)
            search_count = await conn.fetchval(count_query, *count_params)
            print(f"🔍 Companies matching 'finance': {search_count}")
            
            # Test California filter
            ca_filters = SearchFilters(states=["CA"])
            ca_count_query, ca_count_params = SearchService.build_count_query(ca_filters)
            ca_count = await conn.fetchval(ca_count_query, *ca_count_params)
            print(f"🏖️ Companies in California: {ca_count}")
            
        await db_manager.disconnect()
        print("🔌 Disconnected")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_database()) 