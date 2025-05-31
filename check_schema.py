#!/usr/bin/env python3
import asyncio
from search_api import db_manager

async def check_schema():
    await db_manager.connect()
    async with db_manager.pool.acquire() as conn:
        # Check companies table schema
        companies_info = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'companies'
            ORDER BY ordinal_position
        """)
        print('🏢 Companies table schema:')
        for col in companies_info:
            print(f'  {col["column_name"]}: {col["data_type"]}')
        
        # Check licenses table schema
        licenses_info = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'licenses'
            ORDER BY ordinal_position
        """)
        print('\n📜 Licenses table schema:')
        for col in licenses_info:
            print(f'  {col["column_name"]}: {col["data_type"]}')
        
        # Sample data from each table
        print('\n📊 Sample companies data:')
        companies_sample = await conn.fetch("SELECT nmls_id, company_name FROM companies LIMIT 3")
        for row in companies_sample:
            print(f'  NMLS ID: {row["nmls_id"]} ({type(row["nmls_id"])}) - {row["company_name"]}')
        
        print('\n📊 Sample licenses data:')
        licenses_sample = await conn.fetch("SELECT company_id, license_type FROM licenses WHERE license_type IS NOT NULL LIMIT 3")
        for row in licenses_sample:
            print(f'  Company ID: {row["company_id"]} ({type(row["company_id"])}) - {row["license_type"]}')
    
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(check_schema()) 