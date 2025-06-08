#!/usr/bin/env python3
import asyncio
import asyncpg
import os

DATABASE_URL = "postgresql://postgres.eissjxpcsxcktoanftjw:Ronin320320.@aws-0-us-east-2.pooler.supabase.com:6543/postgres"

async def check_ny_financials():
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    
    # Check various financial terms
    terms = ['loan', 'credit', 'mortgage', 'financial', 'capital', 'funding', 'lending', 'finance']
    
    print('🏦 NY FINANCIAL COMPANIES BY KEYWORD:')
    print('=' * 40)
    
    for term in terms:
        count = await conn.fetchval(f'''
            SELECT COUNT(DISTINCT c.id)
            FROM companies c
            JOIN addresses a ON c.id = a.company_id
            WHERE UPPER(a.state) LIKE '%NY%'
            AND UPPER(c.company_name) LIKE '%{term.upper()}%'
        ''')
        print(f'{term.upper()}: {count:,}')
    
    # Show total NY companies
    total_ny = await conn.fetchval('''
        SELECT COUNT(DISTINCT c.id)
        FROM companies c
        JOIN addresses a ON c.id = a.company_id
        WHERE UPPER(a.state) LIKE '%NY%'
    ''')
    print(f'\nTOTAL NY COMPANIES: {total_ny:,}')
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_ny_financials()) 