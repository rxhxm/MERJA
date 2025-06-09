#!/usr/bin/env python3
"""
Simplified Company Enrichment Service for NMLS Search Application
Gets basic company information using SixtyFour API.
"""

import asyncio
import httpx
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class EnrichmentService:
    """Simple service for enriching company data using SixtyFour API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sixtyfour.ai"
        self.enrich_endpoint = "/enrich-company"
        self.timeout = 180.0  # 3 minutes per company
        
    async def enrich_single_company(
        self, 
        client: httpx.AsyncClient, 
        semaphore: asyncio.Semaphore,
        company_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enrich a single company with basic information"""
        async with semaphore:
            company_name = company_data.get('company_name', '')
            nmls_id = company_data.get('nmls_id', '')
            
            # Simple description
            description = f"Financial services company: {company_name}"
            
            # Basic enrichment structure
            company_struct = {
                "website": "Company website URL", 
                "industry": "Primary industry",
                "employees": "Number of employees",
                "personal_loans": "Does this company offer personal loans? Answer Yes or No"
            }
            
            people_struct = {
                "name": "Full name",
                "title": "Job title", 
                "email": "Email address"
            }
            
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "target_company": {
                    "company_name": company_name,
                    "description": description
                },
                "struct": company_struct,
                "find_people": True,
                "people_struct": people_struct,
                "max_people": 2
            }
            
            start_time = time.time()
            try:
                logger.info(f"Enriching: {company_name}")
                response = await client.post(
                    f"{self.base_url}{self.enrich_endpoint}",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                elapsed = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"✅ {company_name} enriched in {elapsed:.1f}s")
                return {
                    "success": True,
                    "company_name": company_name,
                    "nmls_id": nmls_id,
                    "data": data,
                    "processing_time": elapsed
                }
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"❌ {company_name} failed: {str(e)}")
                return {
                    "success": False,
                    "company_name": company_name,
                    "nmls_id": nmls_id,
                    "error": str(e),
                    "processing_time": elapsed
                }
    
    async def enrich_companies_batch(
        self, 
        companies: List[Dict[str, Any]], 
        progress_callback: Optional[callable] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Enrich multiple companies"""
        if not companies:
            return pd.DataFrame(), pd.DataFrame()
        
        logger.info(f"Starting enrichment of {len(companies)} companies")
        
        # Limit concurrent requests
        semaphore = asyncio.Semaphore(2)  # Only 2 at a time
        
        results = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Create tasks
            tasks = []
            for company in companies:
                task = self.enrich_single_company(client, semaphore, company)
                tasks.append(task)
            
            # Process with progress
            for i, task in enumerate(asyncio.as_completed(tasks)):
                result = await task
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(companies), result.get('company_name', 'Unknown'))
        
        # Process results
        return self._process_results(results, companies)
    
    def _process_results(
        self, 
        results: List[Dict[str, Any]], 
        original_companies: List[Dict[str, Any]]
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Process enrichment results into simple dataframes"""
        enriched_companies = []
        all_contacts = []
        
        for idx, result in enumerate(results):
            # Get original company data
            original_company = original_companies[idx] if idx < len(original_companies) else {}
            
            # Base company record
            company_record = original_company.copy()
            company_record.update({
                'enrichment_status': 'Success' if result['success'] else 'Failed',
                'processing_time': result.get('processing_time', 0)
            })

            if not result['success']:
                company_record['error'] = result.get('error', 'Unknown error')
                enriched_companies.append(company_record)
                continue

            # Extract data
            api_data = result.get('data', {})
            structured_data = api_data.get('structured_data', {})

            # Add enriched fields
            company_record.update({
                'website': structured_data.get('website', ''),
                'industry': structured_data.get('industry', ''),
                'personal_loans': structured_data.get('personal_loans', ''),
                'employees': self._parse_employees(structured_data.get('employees', ''))
            })

            # Simple qualification
            personal_loans = structured_data.get('personal_loans', '').lower()
            company_record['qualified'] = 'yes' in personal_loans

            # Process contacts
            contacts = structured_data.get('leads', [])
            for contact in contacts:
                if isinstance(contact, dict):
                    contact_record = {
                        'company': result['company_name'],
                        'nmls_id': result.get('nmls_id', ''),
                        'name': contact.get('name', ''),
                        'title': contact.get('title', ''),
                        'email': contact.get('email', '')
                    }
                    all_contacts.append(contact_record)

            company_record['contacts_found'] = len(contacts)
            enriched_companies.append(company_record)

        # Create DataFrames
        companies_df = pd.DataFrame(enriched_companies)
        contacts_df = pd.DataFrame(all_contacts)

        return companies_df, contacts_df

    def _parse_employees(self, employee_str: str) -> str:
        """Simple employee parsing - return as string"""
        if not employee_str:
            return "Unknown"
        
        import re
        # Extract first number and return with text
        numbers = re.findall(r'\d+', str(employee_str))
        if numbers:
            return f"{numbers[0]} employees"
        return str(employee_str)


def create_enrichment_service() -> Optional[EnrichmentService]:
    """Create enrichment service with API key"""
    import os
    
    try:
        import streamlit as st
        api_key = st.secrets.get('SIXTYFOUR_API_KEY', os.getenv('SIXTYFOUR_API_KEY'))
    except:
        api_key = os.getenv('SIXTYFOUR_API_KEY')
    
    if not api_key:
        return None
    
    return EnrichmentService(api_key) 