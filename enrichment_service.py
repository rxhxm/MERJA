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
        self.timeout = 600.0  # 10 minutes per company
        self.max_retries = 1  # Allow one retry on timeout
        
    async def enrich_single_company(
        self, 
        client: httpx.AsyncClient, 
        semaphore: asyncio.Semaphore,
        company_data: Dict[str, Any],
        custom_company_fields: Optional[Dict[str, str]] = None,
        custom_people_fields: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Enrich a single company with basic information"""
        async with semaphore:
            company_name = company_data.get('company_name', '')
            nmls_id = company_data.get('nmls_id', '')
            
            # Simple description
            description = f"Financial services company: {company_name}"
            
            # Use custom fields if provided, otherwise use defaults
            company_struct = custom_company_fields or {
                "website": "Company website URL", 
                "company_linkedin": "Company LinkedIn profile URL",
                "industry": "Primary industry",
                "employees": "Number of employees",
                "personal_loans": "Does this company offer personal loans? Answer Yes or No"
            }
            
            people_struct = custom_people_fields or {
                "name": "Full name",
                "title": "Job title", 
                "linkedin": "LinkedIn profile URL of the person",
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
            
            # Retry logic for timeouts
            for attempt in range(self.max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"Retry {attempt} for {company_name}")
                    
                    logger.info(f"Enriching: {company_name} (attempt {attempt + 1})")
                    logger.info(f"Payload: {payload}")
                    
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
                    logger.info(f"Response data structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    
                    # Log the full response for debugging
                    logger.info(f"Full API response for {company_name}: {data}")
                    
                    return {
                        "success": True,
                        "company_name": company_name,
                        "nmls_id": nmls_id,
                        "data": data,
                        "processing_time": elapsed
                    }
                    
                except httpx.TimeoutException:
                    elapsed = time.time() - start_time
                    if attempt < self.max_retries:
                        logger.warning(f"⏰ {company_name} timeout on attempt {attempt + 1}, retrying...")
                        continue
                    else:
                        error_msg = f"API timeout after {elapsed:.1f}s (tried {self.max_retries + 1} times)"
                        logger.error(f"❌ {company_name} failed: {error_msg}")
                        return {
                            "success": False,
                            "company_name": company_name,
                            "nmls_id": nmls_id,
                            "error": error_msg,
                            "processing_time": elapsed
                        }
                except httpx.HTTPStatusError as e:
                    elapsed = time.time() - start_time
                    error_msg = f"API error {e.response.status_code}: {e.response.text}"
                    logger.error(f"❌ {company_name} failed: {error_msg}")
                    return {
                        "success": False,
                        "company_name": company_name,
                        "nmls_id": nmls_id,
                        "error": error_msg,
                        "processing_time": elapsed
                    }
                except Exception as e:
                    elapsed = time.time() - start_time
                    error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
                    logger.error(f"❌ {company_name} failed: {error_msg}")
                    return {
                        "success": False,
                        "company_name": company_name,
                        "nmls_id": nmls_id,
                        "error": error_msg,
                        "processing_time": elapsed
                    }
    
    async def enrich_companies_batch(
        self, 
        companies: List[Dict[str, Any]], 
        progress_callback: Optional[callable] = None,
        custom_company_fields: Optional[Dict[str, str]] = None,
        custom_people_fields: Optional[Dict[str, str]] = None
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
                task = self.enrich_single_company(
                    client, 
                    semaphore, 
                    company,
                    custom_company_fields,
                    custom_people_fields
                )
                tasks.append(task)
            
            # Process with progress
            for i, task in enumerate(asyncio.as_completed(tasks)):
                result = await task
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(companies), result.get('company_name', 'Unknown'))
        
        # Process results
        return self._process_results(results, companies, custom_company_fields)
    
    def _process_results(
        self, 
        results: List[Dict[str, Any]], 
        original_companies: List[Dict[str, Any]],
        custom_company_fields: Optional[Dict[str, str]] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Process enrichment results into simple dataframes"""
        enriched_companies = []
        all_contacts = []
        
        # Get field names for dynamic processing
        default_company_fields = {
            "website": "Company website URL", 
            "company_linkedin": "Company LinkedIn profile URL",
            "industry": "Primary industry",
            "employees": "Number of employees",
            "personal_loans": "Does this company offer personal loans? Answer Yes or No"
        }
        
        company_fields_to_process = custom_company_fields or default_company_fields
        
        logger.info(f"Processing {len(results)} enrichment results")
        logger.info(f"Company fields to process: {list(company_fields_to_process.keys())}")
        
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
                logger.warning(f"Company {result.get('company_name', 'Unknown')} failed: {result.get('error', 'Unknown error')}")
                enriched_companies.append(company_record)
                continue

            # Extract data
            api_data = result.get('data', {})
            structured_data = api_data.get('structured_data', {})
            
            logger.info(f"Company {result.get('company_name', 'Unknown')} - API data keys: {list(api_data.keys())}")
            logger.info(f"Company {result.get('company_name', 'Unknown')} - Structured data keys: {list(structured_data.keys())}")
            logger.info(f"Company {result.get('company_name', 'Unknown')} - Structured data: {structured_data}")
            
            # If structured_data is empty, try to extract from other parts of the response
            if not structured_data and isinstance(api_data, dict):
                logger.warning(f"No structured_data found for {result.get('company_name', 'Unknown')}, trying alternative extraction")
                
                # Try to find data in other common response structures
                for key in ['data', 'result', 'company_data', 'enrichment_data']:
                    if key in api_data and isinstance(api_data[key], dict):
                        structured_data = api_data[key]
                        logger.info(f"Found data in '{key}' field: {list(structured_data.keys())}")
                        break
                
                # If still no structured data, use the entire api_data as fallback
                if not structured_data:
                    structured_data = api_data
                    logger.info(f"Using entire API response as structured data: {list(structured_data.keys())}")

            # Add enriched fields dynamically based on custom fields
            fields_found = 0
            for field_name in company_fields_to_process.keys():
                field_value = structured_data.get(field_name, '')
                
                # Try alternative field names if the exact field name isn't found
                if not field_value and field_name == 'company_linkedin':
                    field_value = structured_data.get('linkedin', '') or structured_data.get('linkedin_url', '')
                elif not field_value and field_name == 'website':
                    field_value = structured_data.get('website_url', '') or structured_data.get('url', '')
                elif not field_value and field_name == 'employees':
                    field_value = structured_data.get('employee_count', '') or structured_data.get('num_employees', '')
                
                # Special handling for employees field
                if field_name == 'employees':
                    field_value = self._parse_employees(field_value)
                
                company_record[field_name] = field_value
                if field_value and str(field_value).strip():
                    fields_found += 1
                    logger.info(f"Found {field_name}: {field_value}")
                else:
                    logger.warning(f"Missing or empty {field_name}")

            logger.info(f"Company {result.get('company_name', 'Unknown')} - Found {fields_found}/{len(company_fields_to_process)} fields")

            # Simple qualification (check if personal_loans field exists and contains 'yes')
            personal_loans_value = structured_data.get('personal_loans', '').lower()
            company_record['qualified'] = 'yes' in personal_loans_value
            logger.info(f"Company {result.get('company_name', 'Unknown')} - Personal loans: '{personal_loans_value}', Qualified: {company_record['qualified']}")

            enriched_companies.append(company_record)

            # Extract contacts with all available fields - try multiple possible locations
            leads = structured_data.get('leads', [])
            
            # Try alternative contact field names
            if not leads:
                for contact_field in ['contacts', 'people', 'employees', 'team_members', 'personnel']:
                    if contact_field in structured_data:
                        leads = structured_data[contact_field]
                        logger.info(f"Found contacts in '{contact_field}' field")
                        break
            
            # Also check if contacts are in the main API data
            if not leads and 'contacts' in api_data:
                leads = api_data['contacts']
                logger.info(f"Found contacts in main API data")
            
            logger.info(f"Company {result.get('company_name', 'Unknown')} - Found {len(leads) if isinstance(leads, list) else 0} leads")
            
            if isinstance(leads, list):
                for lead_idx, lead in enumerate(leads):
                    if isinstance(lead, dict):
                        contact_record = {
                            'company_name': result['company_name'],
                            'nmls_id': result['nmls_id']
                        }
                        
                        # Add all lead fields dynamically
                        for field_name, field_value in lead.items():
                            contact_record[field_name] = field_value
                        
                        logger.info(f"Contact {lead_idx} for {result.get('company_name', 'Unknown')}: {list(lead.keys())}")
                        all_contacts.append(contact_record)

        # Create DataFrames
        companies_df = pd.DataFrame(enriched_companies)
        contacts_df = pd.DataFrame(all_contacts)
        
        logger.info(f"Final results: {len(companies_df)} companies, {len(contacts_df)} contacts")
        logger.info(f"Companies DataFrame columns: {list(companies_df.columns)}")
        logger.info(f"Contacts DataFrame columns: {list(contacts_df.columns)}")

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