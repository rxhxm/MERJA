#!/usr/bin/env python3
"""
Test Texas personal loan search with improved statistics
"""
import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_texas_search():
    """Test the Texas search with improved statistics"""
    try:
        from streamlit_app import run_natural_search
        print("🔍 Testing personal loan search in Texas...")
        
        result = await run_natural_search("Find me personal loan companies in texas", True, 1, 20)
        
        if result:
            print("✅ Search successful!")
            total = result['pagination']['total_count']
            print(f"📊 Total results: {total}")
            
            # Check business intelligence
            bi = result['business_intelligence']
            print(f"\n📈 Business Intelligence:")
            print(f"  🎯 High-value targets: {bi['high_value_targets']}")
            
            # Lender type distribution
            lender_dist = bi['lender_type_distribution']
            print(f"\n📋 Lender Type Distribution:")
            for lender_type, count in lender_dist.items():
                percentage = (count / total) * 100 if total > 0 else 0
                if lender_type == 'unsecured_personal':
                    print(f"  ✅ Target: {count} ({percentage:.1f}%)")
                elif lender_type == 'mixed':
                    print(f"  ⚠️  Mixed: {count} ({percentage:.1f}%)")
                elif lender_type == 'mortgage':
                    print(f"  ❌ Exclude: {count} ({percentage:.1f}%)")
                else:
                    print(f"  ❓ Unknown: {count} ({percentage:.1f}%)")
            
            # Contact statistics
            contact_stats = bi['contact_statistics']
            contact_total = sum(contact_stats.values())
            print(f"\n📞 Contact Coverage (of {contact_total} companies):")
            for stat, count in contact_stats.items():
                percentage = (count / contact_total) * 100 if contact_total > 0 else 0
                print(f"  {stat}: {count} ({percentage:.1f}%)")
            
            # Sample companies with scores
            print(f"\n🏢 Sample companies (showing {len(result['companies'])}):")
            for i, company in enumerate(result['companies'][:5]):
                name = company['company_name']
                score = company.get('business_score', 0)
                lender_type = company.get('lender_type', 'unknown')
                
                if 'trust' in name.lower() or 'receivables' in name.lower():
                    note = " (Trust/Vehicle)"
                else:
                    note = " (Real Company)"
                    
                print(f"  {i+1}. {name[:50]}{note}")
                print(f"     Type: {lender_type}, Score: {score:.1f}")
                
        else:
            print("❌ Search returned None")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function"""
    print("🧪 Testing Texas search with improved statistics...")
    asyncio.run(test_texas_search())

if __name__ == "__main__":
    main() 