#!/usr/bin/env python3
import asyncio
from search_api import db_manager, SearchFilters, SearchService, SortField, SortOrder
from natural_language_search import LenderClassifier

async def debug_classification():
    await db_manager.connect()
    
    async with db_manager.pool.acquire() as conn:
        # Get a few specific companies to debug
        debug_companies = [
            "ABLE FINANCIAL CORP",
            "ACC Mortgage Lending", 
            "Advanced Financial Company"
        ]
        
        for company_name in debug_companies:
            print(f"\n🔍 Debugging: {company_name}")
            
            # Get all licenses for this company
            licenses_query = """
                SELECT c.nmls_id, c.company_name, 
                       ARRAY_AGG(DISTINCT l.license_type) as all_license_types
                FROM companies c
                LEFT JOIN licenses l ON c.nmls_id = l.nmls_id
                WHERE c.company_name ILIKE $1
                GROUP BY c.nmls_id, c.company_name
            """
            
            result = await conn.fetchrow(licenses_query, company_name)
            if result:
                all_licenses = result['all_license_types'] or []
                print(f"   NMLS ID: {result['nmls_id']}")
                print(f"   All Licenses ({len(all_licenses)}):")
                for lic in all_licenses:
                    if lic:  # Filter out None values
                        print(f"     - {lic}")
                
                # Check classification
                classification = LenderClassifier.classify_company(all_licenses)
                print(f"   Classification: {classification.value}")
                
                # Show which licenses matched each category
                personal_matches = [lic for lic in all_licenses if lic in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                mortgage_matches = [lic for lic in all_licenses if lic in LenderClassifier.MORTGAGE_LICENSES]
                
                print(f"   Personal Lending Matches ({len(personal_matches)}):")
                for lic in personal_matches:
                    print(f"     ✅ {lic}")
                
                print(f"   Mortgage Matches ({len(mortgage_matches)}):")
                for lic in mortgage_matches:
                    print(f"     ❌ {lic}")
                
                print(f"   Reason: ", end="")
                if personal_matches and mortgage_matches:
                    print("MIXED - Has both personal and mortgage licenses")
                elif personal_matches:
                    print("TARGET - Only personal lending licenses")
                elif mortgage_matches:
                    print("EXCLUDE - Only mortgage licenses")
                else:
                    print("UNKNOWN - No recognized license types")
            else:
                print(f"   ❌ Company not found")
    
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(debug_classification()) 