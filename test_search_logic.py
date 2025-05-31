#!/usr/bin/env python3
"""
Test search logic with various phrases to validate the fixes
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_search_phrase(pool, query: str):
    """Test a single search phrase and analyze results"""
    print(f"\n🔍 Testing: '{query}'")
    print("-" * 50)
    
    try:
        from search_api import SearchFilters, SearchService, SortField, SortOrder
        from natural_language_search import LenderClassifier, ContactValidator, LenderType
        
        # Simulate the streamlit search logic
        query_lower = query.lower()
        filters = SearchFilters()
        
        # Extract location information
        state_detected = None
        if "california" in query_lower or "ca" in query_lower:
            filters.states = ["CA"]
            state_detected = "CA"
        elif "texas" in query_lower or "tx" in query_lower:
            filters.states = ["TX"]
            state_detected = "TX"
        elif "florida" in query_lower or "fl" in query_lower:
            filters.states = ["FL"]
            state_detected = "FL"
        elif "new york" in query_lower or "ny" in query_lower:
            filters.states = ["NY"]
            state_detected = "NY"
        
        # Map personal loan related terms to appropriate license types
        license_filter_applied = False
        if any(term in query_lower for term in ["personal loan", "consumer credit", "consumer loan", "installment loan", "finance company", "small loan"]):
            filters.license_types = [
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
            license_filter_applied = True
            print(f"   📋 Applied personal loan license filters")
        elif any(term in query_lower for term in ["mortgage", "home loan", "real estate"]):
            filters.license_types = [
                "Mortgage Loan Company License",
                "Mortgage Loan Originator License", 
                "Mortgage Broker License",
                "Mortgage Lender License",
                "Mortgage Company License",
                "Residential Mortgage Lender License"
            ]
            license_filter_applied = True
            print(f"   🏠 Applied mortgage license filters")
        else:
            # Extract key search terms from the query
            search_term_detected = None
            if "bank" in query_lower:
                filters.query = "bank"
                search_term_detected = "bank"
            elif "credit union" in query_lower:
                filters.query = "credit union"
                search_term_detected = "credit union"
            elif "finance" in query_lower:
                filters.query = "finance"
                search_term_detected = "finance"
            elif "lending" in query_lower or "lender" in query_lower:
                filters.query = "lend"
                search_term_detected = "lend"
            elif "loan" in query_lower:
                filters.query = "loan"
                search_term_detected = "loan"
            else:
                filters.query = query
                search_term_detected = f"full phrase: {query}"
            
            print(f"   🔍 Search term detected: {search_term_detected}")
        
        if state_detected:
            print(f"   📍 State filter: {state_detected}")
        
        # Execute the search
        async with pool.acquire() as conn:
            # Get count
            count_query, count_params = SearchService.build_count_query(filters)
            total_count = await conn.fetchval(count_query, *count_params)
            
            print(f"   📊 Total results: {total_count}")
            
            if total_count > 0:
                # Get sample results
                search_query, search_params = SearchService.build_search_query(
                    filters, 1, min(5, total_count), 
                    SortField.company_name, SortOrder.asc
                )
                
                rows = await conn.fetch(search_query, *search_params)
                
                print(f"   📋 Sample results:")
                for i, row in enumerate(rows, 1):
                    company_data = dict(row)
                    
                    # Classify lender type
                    lender_classification = LenderClassifier.classify_company(
                        company_data.get('license_types', [])
                    )
                    
                    # Get state info
                    states = company_data.get('states_licensed', [])
                    state_info = f"States: {', '.join(states[:3])}" if states else "No state info"
                    if len(states) > 3:
                        state_info += f" (+{len(states)-3} more)"
                    
                    print(f"     {i}. {company_data['company_name'][:50]}...")
                    print(f"        {state_info}")
                    print(f"        Type: {lender_classification.value}")
                    
                    # Show license types if license filter was applied
                    if license_filter_applied and company_data.get('license_types'):
                        relevant_licenses = [lt for lt in company_data['license_types'] if any(term in lt.lower() for term in ['consumer', 'loan', 'mortgage', 'finance'])]
                        if relevant_licenses:
                            print(f"        Licenses: {', '.join(relevant_licenses[:2])}")
                
                # Cross-check logic
                print(f"   ✅ Cross-check analysis:")
                
                # Check if state filter makes sense
                if state_detected:
                    matching_state_count = 0
                    for row in rows:
                        states = dict(row).get('states_licensed', [])
                        if state_detected in states:
                            matching_state_count += 1
                    
                    if matching_state_count > 0:
                        print(f"      ✅ {matching_state_count}/{len(rows)} samples have {state_detected} licenses")
                    else:
                        print(f"      ⚠️  None of the samples have {state_detected} licenses - check state mapping")
                
                # Check if search term makes sense
                if not license_filter_applied and search_term_detected:
                    matching_name_count = 0
                    for row in rows:
                        company_name = dict(row)['company_name'].lower()
                        if search_term_detected.replace("lend", "lend") in company_name:
                            matching_name_count += 1
                    
                    if matching_name_count > 0:
                        print(f"      ✅ {matching_name_count}/{len(rows)} samples contain '{search_term_detected}' in name")
                    else:
                        print(f"      ⚠️  No samples contain '{search_term_detected}' in name - check broader matching")
                
                # Check lender type distribution
                lender_types = {}
                for row in rows:
                    company_data = dict(row)
                    classification = LenderClassifier.classify_company(company_data.get('license_types', []))
                    lender_types[classification.value] = lender_types.get(classification.value, 0) + 1
                
                print(f"      📊 Lender types: {dict(lender_types)}")
                
                # Business relevance check
                if "personal loan" in query_lower:
                    target_count = lender_types.get('unsecured_personal', 0)
                    if target_count > 0:
                        print(f"      🎯 Found {target_count} target personal lenders - GOOD")
                    else:
                        print(f"      ⚠️  No target personal lenders found - consider broader search")
                
                elif "mortgage" in query_lower:
                    mortgage_count = lender_types.get('mortgage', 0)
                    if mortgage_count > 0:
                        print(f"      🏠 Found {mortgage_count} mortgage lenders - Expected for mortgage query")
                    else:
                        print(f"      ⚠️  No mortgage lenders found - check mortgage license mapping")
            
            else:
                print(f"   ❌ No results - check filters and data")
                
                # Debug why no results
                if filters.states:
                    state_only_count = await conn.fetchval(
                        *SearchService.build_count_query(SearchFilters(states=filters.states))
                    )
                    print(f"      🔍 {state_only_count} companies in {filters.states[0]} total")
                
                if filters.query:
                    query_only_count = await conn.fetchval(
                        *SearchService.build_count_query(SearchFilters(query=filters.query))
                    )
                    print(f"      🔍 {query_only_count} companies matching '{filters.query}' total")
        
    except Exception as e:
        print(f"   ❌ Error testing '{query}': {e}")
        import traceback
        traceback.print_exc()

async def run_comprehensive_tests():
    """Run comprehensive tests on various search phrases"""
    try:
        from search_api import db_manager
        await db_manager.connect()
        
        print("🧪 Comprehensive Search Logic Testing")
        print("=" * 60)
        
        # Test phrases covering different scenarios
        test_phrases = [
            # Basic entity + location
            "Find me banks in california",
            "banks in california", 
            "credit unions in texas",
            "finance companies in florida",
            
            # Personal lending queries
            "personal loan companies in california",
            "consumer credit companies",
            "installment loan lenders in texas",
            "small loan companies with email",
            
            # Mortgage queries  
            "mortgage lenders in california",
            "home loan companies in florida",
            "real estate lenders",
            
            # Broader searches
            "lending companies",
            "loan companies in new york",
            "finance companies with phone numbers",
            
            # Edge cases
            "find financial services",
            "companies in CA",
            "lenders with contact info"
        ]
        
        for phrase in test_phrases:
            await test_search_phrase(db_manager.pool, phrase)
        
        print("\n" + "=" * 60)
        print("🎯 Test Summary Complete")
        
        await db_manager.disconnect()
        
    except Exception as e:
        print(f"❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function"""
    asyncio.run(run_comprehensive_tests())

if __name__ == "__main__":
    main() 