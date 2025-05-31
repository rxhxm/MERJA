#!/usr/bin/env python3
"""
Demo Script for NMLS Search Intelligence Platform
Quick test of core functionality before launching Streamlit app.
"""

import asyncio
import sys
from datetime import datetime

async def test_core_functionality():
    """Test core app functionality"""
    print("🧪 Testing NMLS Search Intelligence Platform")
    print("=" * 50)
    
    # Test 1: Import all modules
    print("\n1. Testing module imports...")
    try:
        from natural_language_search import enhanced_search_api, LenderClassifier, ContactValidator
        from search_api import SearchFilters
        print("   ✅ All modules imported successfully")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return False
    
    # Test 2: Database connection
    print("\n2. Testing database connection...")
    try:
        await enhanced_search_api.initialize()
        print("   ✅ Database connection successful")
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False
    
    # Test 3: Natural language search
    print("\n3. Testing natural language search...")
    try:
        result = await enhanced_search_api.natural_language_search(
            query="Find personal loan companies with phone numbers",
            page_size=5
        )
        
        if result and result.get('companies'):
            print(f"   ✅ Search successful - found {len(result['companies'])} companies")
            print(f"   📊 Query intent: {result['query_analysis']['intent']}")
            print(f"   🎯 Confidence: {result['query_analysis']['confidence']:.1%}")
        else:
            print("   ⚠️  Search returned no results")
            
    except Exception as e:
        print(f"   ❌ Search error: {e}")
        return False
    
    # Test 4: Lender classification
    print("\n4. Testing lender classification...")
    try:
        test_licenses = ["Consumer Credit License", "Personal Loan License"]
        classification = LenderClassifier.classify_company(test_licenses)
        print(f"   ✅ Classification successful: {classification.value}")
    except Exception as e:
        print(f"   ❌ Classification error: {e}")
        return False
    
    # Test 5: Contact validation
    print("\n5. Testing contact validation...")
    try:
        phone_valid = ContactValidator.validate_phone("555-123-4567")
        email_valid = ContactValidator.validate_email("test@example.com")
        print(f"   ✅ Validation successful - Phone: {phone_valid}, Email: {email_valid}")
    except Exception as e:
        print(f"   ❌ Validation error: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 All tests passed! The app is ready to launch.")
    return True

async def demo_search_examples():
    """Demo various search examples"""
    print("\n🔍 Demo: Natural Language Search Examples")
    print("=" * 50)
    
    test_queries = [
        "Find consumer credit companies in California",
        "Show me lenders with email addresses",
        "List companies with more than 5 licenses"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{i}. Query: '{query}'")
        try:
            result = await enhanced_search_api.natural_language_search(
                query=query,
                page_size=3
            )
            
            analysis = result['query_analysis']
            print(f"   Intent: {analysis['intent']}")
            print(f"   Confidence: {analysis['confidence']:.1%}")
            print(f"   Results: {result['pagination']['total_count']} companies")
            print(f"   High-value targets: {result['business_intelligence']['high_value_targets']}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")

def print_usage_instructions():
    """Print instructions for using the app"""
    print("\n" + "=" * 50)
    print("🚀 Ready to Launch Streamlit App!")
    print("=" * 50)
    
    print("\n📋 Quick Start Instructions:")
    print("1. Run: python run_streamlit.py")
    print("2. Open browser to: http://localhost:8501")
    print("3. Try natural language searches like:")
    print("   • 'Find personal loan companies in Texas'")
    print("   • 'Show consumer credit lenders with emails'")
    print("   • 'List companies with federal registration'")
    
    print("\n🎯 Key Features to Explore:")
    print("• Natural Language Search - AI-powered query understanding")
    print("• Business Intelligence - Market analysis dashboard")
    print("• Advanced Filters - Precise database control")
    print("• Tools & Utilities - Lender classification and validation")
    
    print("\n💡 Pro Tips:")
    print("• Use specific terms: 'personal loans' not 'lending'")
    print("• Include location: 'companies in California'")
    print("• Specify contact needs: 'with phone numbers'")
    print("• Check business scores for target relevance")

async def main():
    """Main demo routine"""
    print("🏦 NMLS Search Intelligence Platform - Demo")
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run core functionality tests
    success = await test_core_functionality()
    
    if success:
        # Run demo searches
        await demo_search_examples()
        
        # Print usage instructions
        print_usage_instructions()
        
        # Offer to launch Streamlit
        launch = input("\n🚀 Launch Streamlit app now? (y/n): ").strip().lower()
        if launch == 'y':
            import subprocess
            print("\n🌟 Launching Streamlit app...")
            subprocess.run([sys.executable, "run_streamlit.py"])
    else:
        print("\n❌ Demo failed. Please check your setup before launching the app.")
        print("\n🔧 Troubleshooting steps:")
        print("1. Verify DATABASE_URL environment variable")
        print("2. Check network connectivity to database")
        print("3. Ensure Claude API key is configured")
        print("4. Install missing dependencies: pip install -r requirements_streamlit.txt")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        sys.exit(1) 