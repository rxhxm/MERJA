#!/usr/bin/env python3
import asyncio
from search_api import db_manager, SearchFilters, SearchService, SortField, SortOrder
from natural_language_search import LenderClassifier

async def test_personal_loan_search():
    await db_manager.connect()
    
    # Define the actual personal loan license types from the database
    personal_loan_licenses = [
        "Consumer Loan Company License",
        "Consumer Credit License", 
        "Consumer Lender License",
        "Consumer Loan License",
        "Consumer Finance License",
        "Sales Finance License",
        "Sales Finance Company License",
        "Small Loan Lender License",
        "Small Loan License",
        "Small Loan Company License",
        "Installment Lender License",
        "Installment Loan License",
        "Installment Loan Company License",
        "Consumer Installment Loan License",
        "Supervised Lender License",
        "Money Lender License",
        "Payday Lender License",
        "Short-Term Lender License",
        "Title Pledge Lender License",
        "Consumer Financial Services Class I License",
        "Consumer Financial Services Class II License"
    ]
    
    # Test search with these license types in California
    filters = SearchFilters(license_types=personal_loan_licenses, states=["CA"])
    
    async with db_manager.pool.acquire() as conn:
        # Get count
        count_query, count_params = SearchService.build_count_query(filters)
        total_count = await conn.fetchval(count_query, *count_params)
        print(f"🔍 CA companies with personal loan licenses: {total_count}")
        
        # Get sample results
        search_query, search_params = SearchService.build_search_query(
            filters, 1, 10, 
            SortField.company_name, SortOrder.asc
        )
        
        rows = await conn.fetch(search_query, *search_params)
        print(f"\n📋 Sample companies ({len(rows)}):")
        
        target_count = 0
        mixed_count = 0
        unknown_count = 0
        
        for row in rows:
            company_data = dict(row)
            
            # Classify lender type
            lender_classification = LenderClassifier.classify_company(
                company_data.get('license_types', [])
            )
            
            lender_type = lender_classification.value
            if lender_type == "unsecured_personal":
                target_count += 1
                status = "✅ TARGET"
            elif lender_type == "mixed":
                mixed_count += 1
                status = "⚠️ MIXED"
            elif lender_type == "mortgage":
                status = "❌ EXCLUDE"
            else:
                unknown_count += 1
                status = "❓ UNKNOWN"
            
            print(f"  - {company_data['company_name']} ({company_data['nmls_id']}) - {status}")
            print(f"    Licenses: {company_data.get('license_types', [])[0] if company_data.get('license_types') else 'None'}")
        
        print(f"\n📊 Classification Results:")
        print(f"  ✅ TARGET (unsecured_personal): {target_count}")
        print(f"  ⚠️ MIXED: {mixed_count}")
        print(f"  ❓ UNKNOWN: {unknown_count}")
        print(f"  📈 Expected: This should show more TARGET companies now!")
    
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(test_personal_loan_search()) 