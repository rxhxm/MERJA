#!/usr/bin/env python3
import asyncio
from search_api import db_manager

async def check_licenses():
    await db_manager.connect()
    async with db_manager.pool.acquire() as conn:
        # Get all license types with consumer/credit/finance keywords
        licenses = await conn.fetch("""
            SELECT DISTINCT license_type, COUNT(*) as count
            FROM licenses 
            WHERE license_type ILIKE '%consumer%' 
               OR license_type ILIKE '%credit%'
               OR license_type ILIKE '%finance%'
               OR license_type ILIKE '%loan%'
               OR license_type ILIKE '%lend%'
            GROUP BY license_type
            ORDER BY count DESC
        """)
        
        print('📜 License types with consumer/credit/finance/loan keywords:')
        personal_licenses = []
        for lic in licenses:
            license_type = lic['license_type']
            count = lic['count']
            print(f'  - {license_type} ({count} licenses)')
            
            # Filter out mortgage-related
            if not any(term in license_type.lower() for term in ['mortgage', 'real estate', 'home']):
                personal_licenses.append(license_type)
        
        print(f'\n🎯 Non-mortgage licenses for personal lending ({len(personal_licenses)}):')
        for lic in personal_licenses:
            print(f'  - {lic}')
        
        # Test search with these licenses in CA
        if personal_licenses:
            from search_api import SearchFilters, SearchService
            filters = SearchFilters(license_types=personal_licenses, states=["CA"])
            count_query, count_params = SearchService.build_count_query(filters)
            count = await conn.fetchval(count_query, *count_params)
            print(f'\n🔍 CA companies with personal lending licenses: {count}')
    
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(check_licenses()) 