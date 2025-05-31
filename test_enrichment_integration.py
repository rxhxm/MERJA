#!/usr/bin/env python3
"""
Test script to verify enrichment service integration
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_enrichment_service():
    """Test the enrichment service integration"""
    print("🧪 Testing Enrichment Service Integration")
    print("=" * 50)
    
    try:
        from enrichment_service import create_enrichment_service
        
        # Create enrichment service
        enrichment_service = create_enrichment_service()
        
        if not enrichment_service:
            print("❌ Failed to create enrichment service")
            return False
        
        print(f"✅ Enrichment service created successfully")
        print(f"   API Base URL: {enrichment_service.base_url}")
        print(f"   Max Concurrent: {enrichment_service.max_concurrent}")
        print(f"   Timeout: {enrichment_service.timeout}s")
        
        # Test with a sample company
        test_company = {
            'company_name': 'LendingClub Corp',
            'nmls_id': '1066',
            'business_structure': 'Corporation',
            'license_types': ['Consumer Loan Company License'],
            'states_licensed': ['CA', 'TX', 'NY']
        }
        
        print(f"\n🔍 Testing enrichment with sample company: {test_company['company_name']}")
        
        # Test enrichment
        result = await enrichment_service.enrich_companies_batch([test_company])
        enriched_companies, contacts = result
        
        print(f"✅ Enrichment test completed")
        print(f"   Companies processed: {len(enriched_companies)}")
        print(f"   Contacts found: {len(contacts)}")
        
        if not enriched_companies.empty:
            print(f"   Sample company status: {enriched_companies.iloc[0]['enrichment_status']}")
            if enriched_companies.iloc[0]['enrichment_status'] == 'Success':
                print(f"   Enrichment confidence: {enriched_companies.iloc[0].get('enrichment_confidence', 'N/A')}")
                print(f"   Quality score: {enriched_companies.iloc[0].get('enrichment_quality_score', 'N/A')}")
                print(f"   Qualified lead: {enriched_companies.iloc[0].get('is_qualified_lead', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing enrichment service: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_with_search_integration():
    """Test enrichment with actual search results"""
    print("\n🔗 Testing Enrichment with Search Integration")
    print("=" * 50)
    
    try:
        from search_api import db_manager, SearchFilters, SearchService, SortField, SortOrder
        
        # Connect to database
        await db_manager.connect()
        
        # Run a simple search for CA companies
        filters = SearchFilters(states=["CA"], query="lending")
        
        async with db_manager.pool.acquire() as conn:
            # Get a few companies for testing
            search_query, search_params = SearchService.build_search_query(
                filters, 1, 3, SortField.company_name, SortOrder.asc
            )
            
            rows = await conn.fetch(search_query, *search_params)
            
            if not rows:
                print("❌ No companies found for testing")
                return False
            
            # Convert to company data format
            companies = []
            for row in rows:
                company_data = dict(row)
                companies.append(company_data)
            
            print(f"✅ Found {len(companies)} companies for enrichment test")
            
            # Test enrichment
            from enrichment_service import create_enrichment_service
            enrichment_service = create_enrichment_service()
            
            if enrichment_service:
                print("🚀 Starting enrichment test...")
                
                def progress_callback(completed, total):
                    print(f"   Progress: {completed}/{total} companies processed")
                
                enriched_df, contacts_df = await enrichment_service.enrich_companies_batch(
                    companies, progress_callback
                )
                
                print(f"✅ Search + Enrichment integration test completed")
                print(f"   Companies enriched: {len(enriched_df)}")
                print(f"   Contacts found: {len(contacts_df)}")
                
                # Show sample results
                if not enriched_df.empty:
                    successful = enriched_df[enriched_df['enrichment_status'] == 'Success']
                    qualified = enriched_df[enriched_df.get('is_qualified_lead', False) == True]
                    
                    print(f"   Successful enrichments: {len(successful)}")
                    print(f"   Qualified leads identified: {len(qualified)}")
                
                return True
            else:
                print("❌ Failed to create enrichment service")
                return False
        
        await db_manager.disconnect()
        
    except Exception as e:
        print(f"❌ Error testing search + enrichment integration: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    async def run_tests():
        # Test 1: Basic enrichment service
        test1_success = await test_enrichment_service()
        
        # Test 2: Integration with search
        test2_success = await test_with_search_integration()
        
        print(f"\n🎯 Test Results Summary")
        print("=" * 30)
        print(f"Enrichment Service: {'✅ PASS' if test1_success else '❌ FAIL'}")
        print(f"Search Integration: {'✅ PASS' if test2_success else '❌ FAIL'}")
        
        if test1_success and test2_success:
            print(f"\n🎉 All tests passed! Enrichment integration is ready for Streamlit.")
            print(f"   You can now use the enrichment feature in your app:")
            print(f"   1. Search for companies")
            print(f"   2. Select companies to enrich")
            print(f"   3. Click 'Enrich Selected Companies' or 'Enrich All Results'")
            print(f"   4. Download enriched data and contacts")
        else:
            print(f"\n⚠️  Some tests failed. Please check the errors above.")
    
    asyncio.run(run_tests())

if __name__ == "__main__":
    main() 