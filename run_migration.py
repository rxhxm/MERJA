#!/usr/bin/env python3
"""
Run database migration to add annotation columns
"""

import os
import asyncio
import asyncpg
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Ronin320320.@db.eissjxpcsxcktoanftjw.supabase.co:5432/postgres')

async def run_migration():
    """Run the annotation columns migration"""
    try:
        # Connect to database
        conn = await asyncpg.connect(DATABASE_URL)
        logger.info("Connected to database")
        
        # Read migration SQL
        with open('database/add_annotations.sql', 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        logger.info("Running migration...")
        await conn.execute(migration_sql)
        logger.info("✅ Migration completed successfully")
        
        # Verify columns were added
        result = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'companies' 
            AND column_name IN ('is_reviewed', 'classification', 'notes')
            ORDER BY column_name
        """)
        
        if result:
            logger.info("✅ Annotation columns added:")
            for row in result:
                logger.info(f"  - {row['column_name']}: {row['data_type']} (nullable: {row['is_nullable']}, default: {row['column_default']})")
        else:
            logger.warning(f"⚠️ Could not verify annotation columns were added")
        
        await conn.close()
        logger.info("Database connection closed")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(run_migration()) 