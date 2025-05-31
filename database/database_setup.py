#!/usr/bin/env python3
"""
Database Setup for NMLS Data Processing
Sets up PostgreSQL tables in Supabase for storing extracted NMLS data
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import argparse
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseSetup:
    """Database setup and management for NMLS data"""
    
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.conn = None
        
    def connect(self):
        """Connect to the database"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.conn.autocommit = True
            logger.info("Connected to database successfully")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from the database"""
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from database")
    
    def create_tables(self):
        """Create all necessary tables for NMLS data"""
        
        # Companies table
        companies_table = """
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            nmls_id VARCHAR(20) UNIQUE NOT NULL,
            company_name TEXT NOT NULL,
            url TEXT,
            timestamp TIMESTAMP,
            zip_code VARCHAR(10),
            
            -- Contact Information
            phone VARCHAR(20),
            toll_free VARCHAR(20),
            fax VARCHAR(20),
            email VARCHAR(100),
            website TEXT,
            
            -- Addresses (stored as JSONB for flexibility)
            street_address JSONB,
            mailing_address JSONB,
            
            -- Business Information
            business_structure VARCHAR(100),
            formed_in VARCHAR(100),
            date_formed DATE,
            fiscal_year_end VARCHAR(10),
            stock_symbol VARCHAR(20),
            
            -- MLO Information
            mlo_type VARCHAR(20), -- 'sponsored' or 'registered'
            mlo_count INTEGER,
            
            -- Regulatory
            regulatory_actions TEXT,
            
            -- Federal Registration (for banks/credit unions)
            federal_regulator VARCHAR(100),
            federal_status VARCHAR(50),
            federal_regulator_url TEXT,
            
            -- Trade Names (stored as arrays)
            trade_names TEXT[],
            prior_trade_names TEXT[],
            prior_legal_names TEXT[],
            
            -- Processing Metadata
            extraction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            processing_errors TEXT[],
            quality_flags TEXT[],
            
            -- Search and indexing
            search_vector TSVECTOR,
            
            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        # Licenses table (normalized)
        licenses_table = """
        CREATE TABLE IF NOT EXISTS licenses (
            id SERIAL PRIMARY KEY,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            nmls_id VARCHAR(20) REFERENCES companies(nmls_id),
            
            -- License Identity
            license_id VARCHAR(50),
            license_number VARCHAR(100),
            license_type VARCHAR(200) NOT NULL,
            
            -- Regulator Information
            regulator VARCHAR(200),
            
            -- Status Information
            status VARCHAR(100),
            active BOOLEAN DEFAULT TRUE,
            authorized_to_conduct_business BOOLEAN,
            
            -- Important Dates
            original_issue_date DATE,
            status_date DATE,
            renewed_through DATE,
            
            -- Additional Information
            state_trade_names TEXT,
            
            -- Resident Agent (stored as JSONB)
            resident_agent JSONB,
            
            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        # Addresses table (for better geographic queries)
        addresses_table = """
        CREATE TABLE IF NOT EXISTS addresses (
            id SERIAL PRIMARY KEY,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            address_type VARCHAR(20) NOT NULL, -- 'street' or 'mailing'
            
            -- Address Components
            street_lines TEXT[],
            city VARCHAR(100),
            state VARCHAR(2),
            zip_code VARCHAR(10),
            full_address TEXT,
            
            -- Geographic data (for future enhancement)
            latitude DECIMAL(10, 8),
            longitude DECIMAL(11, 8),
            
            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_companies_nmls_id ON companies(nmls_id);",
            "CREATE INDEX IF NOT EXISTS idx_companies_name ON companies USING GIN(to_tsvector('english', company_name));",
            "CREATE INDEX IF NOT EXISTS idx_companies_search_vector ON companies USING GIN(search_vector);",
            "CREATE INDEX IF NOT EXISTS idx_companies_zip ON companies(zip_code);",
            "CREATE INDEX IF NOT EXISTS idx_companies_state ON companies((street_address->>'state'));",
            "CREATE INDEX IF NOT EXISTS idx_companies_business_structure ON companies(business_structure);",
            "CREATE INDEX IF NOT EXISTS idx_companies_mlo_type ON companies(mlo_type);",
            
            "CREATE INDEX IF NOT EXISTS idx_licenses_company_id ON licenses(company_id);",
            "CREATE INDEX IF NOT EXISTS idx_licenses_nmls_id ON licenses(nmls_id);",
            "CREATE INDEX IF NOT EXISTS idx_licenses_type ON licenses(license_type);",
            "CREATE INDEX IF NOT EXISTS idx_licenses_regulator ON licenses(regulator);",
            "CREATE INDEX IF NOT EXISTS idx_licenses_status ON licenses(status);",
            "CREATE INDEX IF NOT EXISTS idx_licenses_active ON licenses(active);",
            
            "CREATE INDEX IF NOT EXISTS idx_addresses_company_id ON addresses(company_id);",
            "CREATE INDEX IF NOT EXISTS idx_addresses_state ON addresses(state);",
            "CREATE INDEX IF NOT EXISTS idx_addresses_city ON addresses(city);",
            "CREATE INDEX IF NOT EXISTS idx_addresses_zip ON addresses(zip_code);"
        ]
        
        # Enable pgvector extension for future vector search
        enable_vector = """
        CREATE EXTENSION IF NOT EXISTS vector;
        """
        
        # Create search vector update function
        search_function = """
        CREATE OR REPLACE FUNCTION update_company_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.search_vector = 
                setweight(to_tsvector('english', COALESCE(NEW.company_name, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(array_to_string(NEW.trade_names, ' '), '')), 'B') ||
                setweight(to_tsvector('english', COALESCE(NEW.business_structure, '')), 'C') ||
                setweight(to_tsvector('english', COALESCE(NEW.federal_regulator, '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
        
        # Create trigger for search vector updates
        search_trigger = """
        DROP TRIGGER IF EXISTS trigger_update_search_vector ON companies;
        CREATE TRIGGER trigger_update_search_vector
            BEFORE INSERT OR UPDATE ON companies
            FOR EACH ROW EXECUTE FUNCTION update_company_search_vector();
        """
        
        try:
            cursor = self.conn.cursor()
            
            # Create tables
            logger.info("Creating companies table...")
            cursor.execute(companies_table)
            
            logger.info("Creating licenses table...")
            cursor.execute(licenses_table)
            
            logger.info("Creating addresses table...")
            cursor.execute(addresses_table)
            
            # Enable extensions
            logger.info("Enabling vector extension...")
            cursor.execute(enable_vector)
            
            # Create indexes
            logger.info("Creating indexes...")
            for index in indexes:
                cursor.execute(index)
            
            # Create search functions and triggers
            logger.info("Creating search functions...")
            cursor.execute(search_function)
            cursor.execute(search_trigger)
            
            logger.info("Database setup completed successfully!")
            
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def create_summary_views(self):
        """Create useful summary views for data analysis"""
        
        views = [
            # Company summary view
            """
            CREATE OR REPLACE VIEW company_summary AS
            SELECT 
                c.nmls_id,
                c.company_name,
                c.business_structure,
                c.mlo_type,
                c.mlo_count,
                c.federal_regulator,
                c.street_address->>'state' as state,
                c.zip_code,
                COUNT(l.id) as total_licenses,
                COUNT(CASE WHEN l.active THEN 1 END) as active_licenses,
                array_agg(DISTINCT l.license_type) FILTER (WHERE l.license_type IS NOT NULL) as license_types,
                array_agg(DISTINCT l.regulator) FILTER (WHERE l.regulator IS NOT NULL) as regulators
            FROM companies c
            LEFT JOIN licenses l ON c.id = l.company_id
            GROUP BY c.id, c.nmls_id, c.company_name, c.business_structure, 
                     c.mlo_type, c.mlo_count, c.federal_regulator, 
                     c.street_address->>'state', c.zip_code;
            """,
            
            # License statistics view
            """
            CREATE OR REPLACE VIEW license_stats AS
            SELECT 
                license_type,
                COUNT(*) as total_count,
                COUNT(CASE WHEN active THEN 1 END) as active_count,
                COUNT(DISTINCT regulator) as regulator_count,
                array_agg(DISTINCT regulator) as regulators
            FROM licenses
            GROUP BY license_type
            ORDER BY total_count DESC;
            """,
            
            # State summary view
            """
            CREATE OR REPLACE VIEW state_summary AS
            SELECT 
                c.street_address->>'state' as state,
                COUNT(*) as company_count,
                COUNT(DISTINCT c.business_structure) as business_structures,
                COUNT(CASE WHEN c.federal_regulator IS NOT NULL THEN 1 END) as federal_companies,
                SUM(l.license_count) as total_licenses
            FROM companies c
            LEFT JOIN (
                SELECT nmls_id, COUNT(*) as license_count
                FROM licenses
                GROUP BY nmls_id
            ) l ON c.nmls_id = l.nmls_id
            WHERE c.street_address->>'state' IS NOT NULL
            GROUP BY c.street_address->>'state'
            ORDER BY company_count DESC;
            """
        ]
        
        try:
            cursor = self.conn.cursor()
            
            for view in views:
                cursor.execute(view)
            
            logger.info("Summary views created successfully!")
            
        except Exception as e:
            logger.error(f"Error creating views: {e}")
            raise
    
    def test_connection(self):
        """Test database connection and basic functionality"""
        try:
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            logger.info(f"Database version: {version['version']}")
            
            # Test table existence
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('companies', 'licenses', 'addresses');
            """)
            tables = cursor.fetchall()
            logger.info(f"Found tables: {[t['table_name'] for t in tables]}")
            
        except Exception as e:
            logger.error(f"Database test failed: {e}")
            raise

def main():
    """Main setup function"""
    parser = argparse.ArgumentParser(description="Set up NMLS database schema")
    parser.add_argument("--connection-string", 
                       help="PostgreSQL connection string",
                       default=os.getenv('DATABASE_URL'))
    parser.add_argument("--create-tables", action="store_true",
                       help="Create database tables")
    parser.add_argument("--create-views", action="store_true", 
                       help="Create summary views")
    parser.add_argument("--test", action="store_true",
                       help="Test database connection")
    
    args = parser.parse_args()
    
    if not args.connection_string:
        logger.error("Connection string required. Set DATABASE_URL environment variable or use --connection-string")
        return 1
    
    # Initialize database setup
    db_setup = DatabaseSetup(args.connection_string)
    
    try:
        db_setup.connect()
        
        if args.create_tables:
            db_setup.create_tables()
        
        if args.create_views:
            db_setup.create_summary_views()
        
        if args.test:
            db_setup.test_connection()
        
        if not any([args.create_tables, args.create_views, args.test]):
            # Default: create everything
            db_setup.create_tables()
            db_setup.create_summary_views()
            db_setup.test_connection()
        
    finally:
        db_setup.disconnect()
    
    logger.info("Database setup complete!")
    return 0

if __name__ == "__main__":
    exit(main()) 