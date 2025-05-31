#!/usr/bin/env python3
"""
Database Loader for NMLS Data
Loads extracted company data from the HTML extractor into Supabase database
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import asdict
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

# Import the data structures from the extractor
from nmls_html_extractor import CompanyData, Address, ContactInfo, BusinessInfo, MLOInfo, FederalRegistration, LicenseDetails, ResidentAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseLoader:
    """Load extracted NMLS data into Supabase database"""
    
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or os.getenv('DATABASE_URL')
        if not self.connection_string:
            raise ValueError("Database connection string required. Set DATABASE_URL environment variable or provide connection_string")
        
        self.conn = None
        self.stats = {
            "companies_inserted": 0,
            "licenses_inserted": 0,
            "addresses_inserted": 0,
            "errors": 0,
            "skipped": 0
        }
    
    def connect(self):
        """Connect to the database"""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            self.conn.autocommit = False  # Use transactions
            logger.info("Connected to database successfully")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from the database"""
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from database")
    
    def _prepare_address_json(self, address: Address) -> Dict:
        """Convert Address object to JSON-compatible dict"""
        if not address:
            return {}
        
        return {
            "street_lines": address.street_lines,
            "city": address.city,
            "state": address.state,
            "zip_code": address.zip_code,
            "full_address": address.full_address
        }
    
    def _prepare_resident_agent_json(self, agent: ResidentAgent) -> Dict:
        """Convert ResidentAgent object to JSON-compatible dict"""
        if not agent:
            return {}
        
        return {
            "company": agent.company,
            "name": agent.name,
            "title": agent.title,
            "address": agent.address,
            "phone": agent.phone,
            "fax": agent.fax
        }
    
    def _insert_company(self, company: CompanyData) -> int:
        """Insert company data and return company ID"""
        cursor = self.conn.cursor()
        
        # Prepare address data
        street_address_json = self._prepare_address_json(company.street_address)
        mailing_address_json = self._prepare_address_json(company.mailing_address)
        
        # Prepare other data
        contact = company.contact_info
        business = company.business_info
        mlo = company.mlo_info
        federal = company.federal_registration
        
        # Parse date_formed if it exists
        date_formed = None
        if business and business.date_formed:
            try:
                # Try to parse common date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%Y']:
                    try:
                        date_formed = datetime.strptime(business.date_formed, fmt).date()
                        break
                    except ValueError:
                        continue
            except:
                pass  # Keep as None if parsing fails
        
        insert_query = """
        INSERT INTO companies (
            nmls_id, company_name, url, timestamp, zip_code,
            phone, toll_free, fax, email, website,
            street_address, mailing_address,
            business_structure, formed_in, date_formed, fiscal_year_end, stock_symbol,
            mlo_type, mlo_count,
            regulatory_actions,
            federal_regulator, federal_status, federal_regulator_url,
            trade_names, prior_trade_names, prior_legal_names,
            file_path, processing_errors, quality_flags
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        ) RETURNING id;
        """
        
        cursor.execute(insert_query, (
            company.nmls_id,
            company.company_name,
            company.url,
            company.timestamp,
            company.zip_code,
            
            # Contact info
            contact.phone if contact else None,
            contact.toll_free if contact else None,
            contact.fax if contact else None,
            contact.email if contact else None,
            contact.website if contact else None,
            
            # Addresses (as JSONB)
            json.dumps(street_address_json),
            json.dumps(mailing_address_json),
            
            # Business info
            business.structure if business else None,
            business.formed_in if business else None,
            date_formed,
            business.fiscal_year_end if business else None,
            business.stock_symbol if business else None,
            
            # MLO info
            mlo.type if mlo else None,
            mlo.count if mlo else None,
            
            # Regulatory
            company.regulatory_actions,
            
            # Federal registration
            federal.regulator if federal else None,
            federal.status if federal else None,
            federal.regulator_url if federal else None,
            
            # Trade names (as arrays)
            company.trade_names or [],
            company.prior_trade_names or [],
            company.prior_legal_names or [],
            
            # Processing metadata
            company.file_path,
            company.processing_errors or [],
            company.quality_flags or []
        ))
        
        company_id = cursor.fetchone()[0]
        self.stats["companies_inserted"] += 1
        
        return company_id
    
    def _insert_licenses(self, company_id: int, nmls_id: str, licenses: List[LicenseDetails]):
        """Insert license data for a company"""
        if not licenses:
            return
        
        cursor = self.conn.cursor()
        
        license_data = []
        for license_info in licenses:
            # Parse dates
            original_issue_date = None
            status_date = None
            renewed_through = None
            
            for date_field, date_value in [
                ('original_issue_date', license_info.original_issue_date),
                ('status_date', license_info.status_date),
                ('renewed_through', license_info.renewed_through)
            ]:
                if date_value:
                    try:
                        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y']:
                            try:
                                parsed_date = datetime.strptime(date_value, fmt).date()
                                if date_field == 'original_issue_date':
                                    original_issue_date = parsed_date
                                elif date_field == 'status_date':
                                    status_date = parsed_date
                                elif date_field == 'renewed_through':
                                    renewed_through = parsed_date
                                break
                            except ValueError:
                                continue
                    except:
                        pass  # Keep as None if parsing fails
            
            license_data.append((
                company_id,
                nmls_id,
                license_info.license_id,
                license_info.license_number,
                license_info.license_type,
                license_info.regulator,
                license_info.status,
                license_info.active,
                license_info.authorized_to_conduct_business,
                original_issue_date,
                status_date,
                renewed_through,
                license_info.state_trade_names,
                json.dumps(self._prepare_resident_agent_json(license_info.resident_agent))
            ))
        
        insert_query = """
        INSERT INTO licenses (
            company_id, nmls_id, license_id, license_number, license_type, 
            regulator, status, active, authorized_to_conduct_business,
            original_issue_date, status_date, renewed_through,
            state_trade_names, resident_agent
        ) VALUES %s
        """
        
        execute_values(cursor, insert_query, license_data)
        self.stats["licenses_inserted"] += len(license_data)
    
    def _insert_addresses(self, company_id: int, company: CompanyData):
        """Insert address data for a company"""
        cursor = self.conn.cursor()
        
        addresses_to_insert = []
        
        # Street address
        if company.street_address and company.street_address.full_address:
            addresses_to_insert.append((
                company_id,
                'street',
                company.street_address.street_lines or [],
                company.street_address.city,
                company.street_address.state,
                company.street_address.zip_code,
                company.street_address.full_address
            ))
        
        # Mailing address
        if company.mailing_address and company.mailing_address.full_address:
            addresses_to_insert.append((
                company_id,
                'mailing',
                company.mailing_address.street_lines or [],
                company.mailing_address.city,
                company.mailing_address.state,
                company.mailing_address.zip_code,
                company.mailing_address.full_address
            ))
        
        if addresses_to_insert:
            insert_query = """
            INSERT INTO addresses (
                company_id, address_type, street_lines, city, state, zip_code, full_address
            ) VALUES %s
            """
            
            execute_values(cursor, insert_query, addresses_to_insert)
            self.stats["addresses_inserted"] += len(addresses_to_insert)
    
    def load_company(self, company: CompanyData) -> bool:
        """Load a single company into the database"""
        try:
            cursor = self.conn.cursor()
            
            # Check if company already exists
            cursor.execute("SELECT id FROM companies WHERE nmls_id = %s", (company.nmls_id,))
            existing = cursor.fetchone()
            
            if existing:
                logger.debug(f"Company {company.nmls_id} already exists, skipping")
                self.stats["skipped"] += 1
                return True
            
            # Insert company
            company_id = self._insert_company(company)
            
            # Insert licenses
            self._insert_licenses(company_id, company.nmls_id, company.licenses)
            
            # Insert addresses
            self._insert_addresses(company_id, company)
            
            # Commit transaction
            self.conn.commit()
            
            logger.debug(f"Successfully loaded company {company.nmls_id}")
            return True
            
        except Exception as e:
            self.conn.rollback()
            self.stats["errors"] += 1
            logger.error(f"Error loading company {company.nmls_id}: {e}")
            return False
    
    def load_companies(self, companies: List[CompanyData]) -> Dict[str, int]:
        """Load multiple companies into the database"""
        logger.info(f"Loading {len(companies)} companies into database...")
        
        for i, company in enumerate(companies, 1):
            if not company.nmls_id:
                logger.warning(f"Skipping company without NMLS ID (index {i})")
                self.stats["skipped"] += 1
                continue
            
            self.load_company(company)
            
            # Log progress every 100 companies
            if i % 100 == 0:
                logger.info(f"Processed {i}/{len(companies)} companies")
        
        logger.info("=== Database Loading Complete ===")
        logger.info(f"Companies inserted: {self.stats['companies_inserted']}")
        logger.info(f"Licenses inserted: {self.stats['licenses_inserted']}")
        logger.info(f"Addresses inserted: {self.stats['addresses_inserted']}")
        logger.info(f"Skipped (already exist): {self.stats['skipped']}")
        logger.info(f"Errors: {self.stats['errors']}")
        
        return self.stats

def main():
    """Load data from extractor output into database"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Load extracted NMLS data into database")
    parser.add_argument("input_file", help="JSON file from nmls_html_extractor.py")
    parser.add_argument("--connection-string", help="Database connection string", 
                       default=os.getenv('DATABASE_URL'))
    
    args = parser.parse_args()
    
    if not args.connection_string:
        logger.error("Database connection string required. Set DATABASE_URL environment variable or use --connection-string")
        return 1
    
    # Load data from JSON file
    logger.info(f"Loading data from {args.input_file}")
    with open(args.input_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    # Convert back to CompanyData objects (simplified, assumes JSON structure matches)
    companies = []
    for item in json_data:
        try:
            # Create CompanyData object from JSON
            company = CompanyData()
            
            # Basic fields
            company.nmls_id = item.get('nmls_id')
            company.company_name = item.get('company_name')
            company.url = item.get('url')
            company.timestamp = item.get('timestamp')
            company.zip_code = item.get('zip_code')
            company.file_path = item.get('file_path')
            company.processing_errors = item.get('processing_errors', [])
            company.quality_flags = item.get('quality_flags', [])
            
            # Contact info
            if item.get('contact_info'):
                contact = ContactInfo()
                contact.phone = item['contact_info'].get('phone')
                contact.toll_free = item['contact_info'].get('toll_free')
                contact.fax = item['contact_info'].get('fax')
                contact.email = item['contact_info'].get('email')
                contact.website = item['contact_info'].get('website')
                company.contact_info = contact
            
            # Continue with other nested objects as needed...
            # This is a simplified version - full implementation would reconstruct all nested objects
            
            companies.append(company)
            
        except Exception as e:
            logger.error(f"Error processing company data: {e}")
            continue
    
    # Load into database
    loader = DatabaseLoader(args.connection_string)
    
    try:
        loader.connect()
        stats = loader.load_companies(companies)
        logger.info(f"Successfully loaded data. Stats: {stats}")
    finally:
        loader.disconnect()
    
    return 0

if __name__ == "__main__":
    exit(main()) 