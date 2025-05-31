#!/usr/bin/env python3
"""
Test Script for Natural Language Search
Tests the Claude-powered natural language search functionality.
"""

import asyncio
import sys
import json
from typing import Dict, Any

from natural_language_search import enhanced_search_api, claude_client

async def test_claude_connection():
    """Test basic Claude API connectivity"""
    print("🧪 Testing Claude API connection...")
    
    try:
        response = await claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": "Hello, respond with 'Claude is working!' in JSON format: {\"status\": \"Claude is working!\"}"
                }
            ]
        )
        
        print(f"✅ Claude API Response: {response.content[0].text}")
        return True
        
    except Exception as e:
        print(f"❌ Claude API Error: {e}")
        return False

async def test_query_analysis():
    """Test natural language query analysis"""
    print("\n🧪 Testing query analysis...")
    
    test_queries = [
        "Find personal loan companies in California",
        "Show me mortgage lenders in Texas",
        "List companies with email addresses",
        "Find large lenders with more than 5 licenses"
    ]
    
    try:
        await enhanced_search_api.initialize()
        
        for query in test_queries:
            print(f"\n📝 Testing query: '{query}'")
            
            analysis = await enhanced_search_api.nlp.analyze_query(query)
            
            print(f"   Intent: {analysis.intent.value}")
            print(f"   Confidence: {analysis.confidence}")
            print(f"   Lender Type: {analysis.lender_type_preference.value if analysis.lender_type_preference else 'None'}")
            print(f"   Explanation: {analysis.explanation}")
            
            if analysis.business_critical_flags:
                print(f"   🚨 Flags: {', '.join(analysis.business_critical_flags)}")
            
            print("   ✅ Query analysis successful")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Query analysis error: {e}")
        return False

async def test_lender_classification():
    """Test lender classification logic"""
    print("\n🧪 Testing lender classification...")
    
    test_cases = [
        {
            "name": "Unsecured Personal Lender",
            "licenses": ["Consumer Credit License", "Personal Loan License"],
            "expected": "unsecured_personal"
        },
        {
            "name": "Mortgage Lender",
            "licenses": ["Mortgage Loan Company License", "Mortgage Broker License"],
            "expected": "mortgage"
        },
        {
            "name": "Mixed Lender",
            "licenses": ["Consumer Credit License", "Mortgage Loan Company License"],
            "expected": "mixed"
        },
        {
            "name": "Unknown Lender",
            "licenses": ["Some Unknown License Type"],
            "expected": "unknown"
        }
    ]
    
    try:
        from natural_language_search import LenderClassifier
        
        for case in test_cases:
            result = LenderClassifier.classify_company(case["licenses"])
            
            if result.value == case["expected"]:
                print(f"   ✅ {case['name']}: {result.value}")
            else:
                print(f"   ❌ {case['name']}: Expected {case['expected']}, got {result.value}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Classification error: {e}")
        return False

async def test_contact_validation():
    """Test contact validation logic"""
    print("\n🧪 Testing contact validation...")
    
    test_cases = [
        {"phone": "555-123-4567", "email": "test@example.com", "expected": (True, True)},
        {"phone": "5551234567", "email": "test@example.com", "expected": (True, True)},
        {"phone": "invalid", "email": "test@example.com", "expected": (False, True)},
        {"phone": "555-123-4567", "email": "invalid-email", "expected": (True, False)},
        {"phone": "", "email": "", "expected": (False, False)},
    ]
    
    try:
        from natural_language_search import ContactValidator
        
        for i, case in enumerate(test_cases):
            phone_valid = ContactValidator.validate_phone(case["phone"])
            email_valid = ContactValidator.validate_email(case["email"])
            
            expected_phone, expected_email = case["expected"]
            
            if phone_valid == expected_phone and email_valid == expected_email:
                print(f"   ✅ Test case {i+1}: Phone={phone_valid}, Email={email_valid}")
            else:
                print(f"   ❌ Test case {i+1}: Expected ({expected_phone}, {expected_email}), got ({phone_valid}, {email_valid})")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Contact validation error: {e}")
        return False

async def test_full_search():
    """Test full natural language search pipeline"""
    print("\n🧪 Testing full search pipeline...")
    
    try:
        # Test a simple query
        query = "Find consumer credit companies with email addresses"
        print(f"   Query: '{query}'")
        
        result = await enhanced_search_api.natural_language_search(
            query=query,
            apply_business_filters=True,
            page=1,
            page_size=5
        )
        
        print(f"   ✅ Search completed")
        print(f"   Intent: {result['query_analysis']['intent']}")
        print(f"   Confidence: {result['query_analysis']['confidence']}")
        print(f"   Total results: {result['pagination']['total_count']}")
        print(f"   High-value targets: {result['business_intelligence']['high_value_targets']}")
        
        if result['business_intelligence']['business_recommendations']:
            print(f"   Recommendations: {len(result['business_intelligence']['business_recommendations'])}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Full search error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run comprehensive test suite"""
    print("🚀 Starting Natural Language Search Test Suite")
    print("=" * 60)
    
    tests = [
        ("Claude API Connection", test_claude_connection),
        ("Query Analysis", test_query_analysis),
        ("Lender Classification", test_lender_classification),
        ("Contact Validation", test_contact_validation),
        ("Full Search Pipeline", test_full_search),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running: {test_name}")
        try:
            success = await test_func()
            results[test_name] = success
        except Exception as e:
            print(f"❌ Test {test_name} failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for success in results.values() if success)
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Natural language search is ready to use.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        return False
    
    return True

async def interactive_test():
    """Interactive test mode for manual query testing"""
    print("\n🔧 Interactive Test Mode")
    print("Enter natural language queries to test the system.")
    print("Type 'quit' to exit.\n")
    
    await enhanced_search_api.initialize()
    
    while True:
        query = input("Query: ").strip()
        
        if query.lower() in ['quit', 'exit', 'q']:
            break
        
        if not query:
            continue
        
        try:
            print(f"\n🔍 Analyzing: '{query}'")
            
            # First analyze the query
            analysis = await enhanced_search_api.nlp.analyze_query(query)
            print(f"Intent: {analysis.intent.value}")
            print(f"Confidence: {analysis.confidence}")
            print(f"Lender Type: {analysis.lender_type_preference.value if analysis.lender_type_preference else 'None'}")
            print(f"Explanation: {analysis.explanation}")
            
            if analysis.business_critical_flags:
                print(f"Flags: {', '.join(analysis.business_critical_flags)}")
            
            # Ask if they want to run the full search
            run_search = input("\nRun full search? (y/n): ").strip().lower()
            
            if run_search == 'y':
                result = await enhanced_search_api.natural_language_search(
                    query=query,
                    apply_business_filters=True,
                    page=1,
                    page_size=3
                )
                
                print(f"\nResults: {result['pagination']['total_count']} companies found")
                print(f"High-value targets: {result['business_intelligence']['high_value_targets']}")
                
                if result['companies']:
                    print("\nTop results:")
                    for i, company in enumerate(result['companies'][:3], 1):
                        print(f"{i}. {company['company_name']} ({company['lender_type']}) - Score: {company['business_score']:.1f}")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "-" * 40)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        asyncio.run(interactive_test())
    else:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1) 