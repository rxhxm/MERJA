#!/usr/bin/env python3
"""
Test script to verify async fixes work properly
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_search():
    """Test the search function directly"""
    try:
        from streamlit_app import run_natural_search
        print("🔍 Testing personal loan search in California...")
        
        result = await run_natural_search("find me personal loan companies in california", True, 1, 10)
        
        if result:
            print("✅ Search successful!")
            print(f"📊 Total results: {result['pagination']['total_count']}")
            print(f"🎯 High-value targets: {result['business_intelligence']['high_value_targets']}")
            print(f"📋 Companies returned: {len(result['companies'])}")
            
            # Show first few companies
            print("\n🏢 Sample companies:")
            for i, company in enumerate(result['companies'][:3]):
                print(f"  {i+1}. {company['company_name']} ({company['nmls_id']})")
                print(f"     Type: {company.get('lender_type', 'unknown')}")
                print(f"     Score: {company.get('business_score', 0):.1f}")
        else:
            print("❌ Search returned None")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function"""
    print("🧪 Testing async search functionality...")
    
    try:
        # Test with asyncio.run (simulates how Streamlit should work)
        asyncio.run(test_search())
        print("✅ Async test completed successfully!")
    except Exception as e:
        print(f"❌ Async test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 