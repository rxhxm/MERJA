#!/usr/bin/env python3
"""
Company Enrichment Service for NMLS Search Application
Integrates with SixtyFour API to enrich company data with additional business intelligence.
"""

import asyncio
import httpx
import json
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class EnrichmentService:
    """Service for enriching company data using SixtyFour API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sixtyfour.ai"
        self.enrich_endpoint = "/enrich-company"
        self.max_concurrent = 10  # Conservative for Streamlit
        self.timeout = 300.0  # 5 minutes per API call for web app
        
    async def enrich_single_company(
        self, 
        client: httpx.AsyncClient, 
        semaphore: asyncio.Semaphore,
        company_data: Dict[str, Any],
        reference_companies: List[str] = None
    ) -> Dict[str, Any]:
        """
        Enrich a single company using the SixtyFour API
        
        Args:
            client: HTTP client
            semaphore: Concurrency control
            company_data: Company data from NMLS database
            reference_companies: Reference companies for ICP matching
            
        Returns:
            Enrichment result with success status and data
        """
        async with semaphore:
            company_name = company_data.get('company_name', '')
            nmls_id = company_data.get('nmls_id', '')
            
            # Create description from available NMLS data
            description_parts = []
            if company_data.get('business_structure'):
                description_parts.append(f"Business structure: {company_data['business_structure']}")
            if company_data.get('license_types'):
                license_types = company_data['license_types'][:3]  # First 3 license types
                description_parts.append(f"Licensed for: {', '.join(license_types)}")
            if company_data.get('states_licensed'):
                states = company_data['states_licensed'][:5]  # First 5 states
                description_parts.append(f"Licensed in: {', '.join(states)}")
            
            description = "; ".join(description_parts) if description_parts else f"Financial services company with NMLS ID {nmls_id}"
            
            # Define enrichment structure for personal lending focus
            company_struct = {
                "company_linkedin": "LinkedIn profile URL of the company",
                "website": "Official website of the company", 
                "num_employees": "Estimated number of employees",
                "industry": "Primary industry of the company",
                "specializes_in_personal_loans": "Does this company specialize in unsecured personal loans or consumer credit? Yes/No",
                "target_customer_segment": "What customer segment does this company primarily serve (e.g., prime, near-prime, subprime)?",
                "lending_volume": "Estimated annual lending volume or loan portfolio size",
                "technology_focus": "Does this company have a strong technology or fintech focus? Yes/No",
                "icp_match": f"Is this company a good target for Fido's personal lending services? Consider: unsecured personal lending focus, technology adoption, growth potential. Yes/No and explain why.",
                "competitive_positioning": "How does this company position itself in the personal lending market?",
                "notes": "Key insights about this company's business model and relevance for personal lending partnerships."
            }
            
            people_struct = {
                "name": "Full name of the person",
                "title": "Job title at the company", 
                "linkedin": "LinkedIn profile URL",
                "email": "Email address if available",
                "phone": "Phone number if available",
                "is_decision_maker": "Is this person a key decision maker for lending partnerships? Answer 'Yes' ONLY for C-suite executives, presidents, VPs, directors, or heads of lending/credit/business development.",
                "relevance_score": "How relevant is this person for Fido's business (1-10 scale)?"
            }
            
            headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
            payload = {
                "target_company": {
                    "company_name": company_name,
                    "description": description
                },
                "struct": company_struct,
                "find_people": True,
                "people_focus_prompt": "Find key decision-makers for lending partnerships: C-suite executives, VPs of lending/credit/business development, directors of partnerships, heads of operations.",
                "people_struct": people_struct,
                "max_people": 8
            }
            
            start_time = time.time()
            try:
                logger.info(f"Starting enrichment for: {company_name}")
                response = await client.post(
                    f"{self.base_url}{self.enrich_endpoint}",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                elapsed = time.time() - start_time
                
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"Successfully enriched {company_name} in {elapsed:.2f}s")
                return {
                    "success": True,
                    "company_name": company_name,
                    "nmls_id": nmls_id,
                    "data": data,
                    "processing_time": elapsed
                }
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"Error enriching {company_name} after {elapsed:.2f}s: {str(e)}")
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
        """
        Enrich a batch of companies and return structured results
        
        Args:
            companies: List of company data from NMLS search
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Tuple of (enriched_companies_df, contacts_df)
        """
        if not companies:
            return pd.DataFrame(), pd.DataFrame()
        
        # Get reference companies for ICP matching (first 3 high-value targets)
        reference_companies = []
        for company in companies[:3]:
            if company.get('business_score', 0) > 70:
                reference_companies.append(company['company_name'])
        
        if not reference_companies:
            reference_companies = [companies[0]['company_name']]
        
        logger.info(f"Starting enrichment of {len(companies)} companies")
        logger.info(f"Using reference companies: {reference_companies}")
        
        # Set up concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)
        limits = httpx.Limits(
            max_keepalive_connections=self.max_concurrent,
            max_connections=self.max_concurrent + 5
        )
        
        # Process companies
        results = []
        async with httpx.AsyncClient(limits=limits, timeout=self.timeout) as client:
            tasks = []
            for i, company in enumerate(companies):
                task = self.enrich_single_company(
                    client, semaphore, company, reference_companies
                )
                tasks.append(task)
            
            # Process with progress tracking
            completed = 0
            for task in asyncio.as_completed(tasks):
                result = await task
                results.append(result)
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, len(companies))
        
        # Process results into structured DataFrames
        return self._process_enrichment_results(results, companies)
    
    def _process_enrichment_results(
        self, 
        results: List[Dict[str, Any]], 
        original_companies: List[Dict[str, Any]]
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Process enrichment results into structured DataFrames"""
        
        enriched_companies = []
        contacts = []
        
        for i, result in enumerate(results):
            # Get original company data
            try:
                original_company = original_companies[i]
            except IndexError:
                original_company = {"company_name": result.get("company_name", "Unknown")}
            
            # Create enriched company record
            company_record = original_company.copy()
            company_record["enrichment_timestamp"] = datetime.now().isoformat()
            company_record["enrichment_processing_time"] = result.get("processing_time", 0)
            
            if not result.get("success"):
                company_record["enrichment_status"] = "Failed"
                company_record["enrichment_error"] = result.get("error", "Unknown error")
                enriched_companies.append(company_record)
                continue
            
            # Process successful enrichment
            api_data = result.get("data", {})
            structured_data = api_data.get("structured_data", {})
            
            company_record["enrichment_status"] = "Success"
            company_record["enrichment_confidence"] = api_data.get("confidence_score", 0)
            
            # Add enriched company fields
            for key, value in structured_data.items():
                if key != "leads":  # Leads are processed separately
                    company_record[f"enriched_{key}"] = value
            
            # Calculate enrichment quality score
            quality_score = self._calculate_enrichment_quality(structured_data)
            company_record["enrichment_quality_score"] = quality_score
            
            # Determine if this is a qualified lead
            is_qualified, qualification_reasons = self._assess_company_qualification(structured_data)
            company_record["is_qualified_lead"] = is_qualified
            company_record["qualification_reasons"] = "; ".join(qualification_reasons)
            
            enriched_companies.append(company_record)
            
            # Process contacts/leads
            leads = structured_data.get("leads", [])
            for lead in leads:
                if isinstance(lead, dict):
                    contact_record = {
                        "company_name": original_company.get("company_name"),
                        "nmls_id": original_company.get("nmls_id"),
                        "contact_name": lead.get("name", ""),
                        "contact_title": lead.get("title", ""),
                        "contact_linkedin": lead.get("linkedin", ""),
                        "contact_email": lead.get("email", ""),
                        "contact_phone": lead.get("phone", ""),
                        "is_decision_maker": lead.get("is_decision_maker", "").lower(),
                        "relevance_score": lead.get("relevance_score", ""),
                        "enrichment_timestamp": datetime.now().isoformat()
                    }
                    contacts.append(contact_record)
        
        return pd.DataFrame(enriched_companies), pd.DataFrame(contacts)
    
    def _calculate_enrichment_quality(self, structured_data: Dict[str, Any]) -> float:
        """Calculate a quality score for the enrichment data"""
        score = 0.0
        max_score = 100.0
        
        # Website found
        if structured_data.get("website"):
            score += 20
        
        # LinkedIn found  
        if structured_data.get("company_linkedin"):
            score += 15
        
        # Employee count provided
        if structured_data.get("num_employees"):
            score += 10
        
        # Personal loan specialization identified
        personal_loan_focus = structured_data.get("specializes_in_personal_loans", "").lower()
        if "yes" in personal_loan_focus:
            score += 25
        elif "no" in personal_loan_focus:
            score += 10  # At least we know
        
        # ICP match assessment
        icp_match = structured_data.get("icp_match", "").lower()
        if "yes" in icp_match:
            score += 20
        elif "no" in icp_match:
            score += 5
        
        # Has decision makers/leads
        leads_count = len(structured_data.get("leads", []))
        if leads_count > 0:
            score += min(leads_count * 2, 10)  # Up to 10 points for leads
        
        return min(score, max_score)
    
    def _assess_company_qualification(self, structured_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Assess if a company is a qualified lead for Fido"""
        reasons = []
        is_qualified = False
        
        # Check personal loan specialization
        personal_loan_focus = structured_data.get("specializes_in_personal_loans", "").lower()
        if "yes" in personal_loan_focus:
            reasons.append("Specializes in personal loans")
            is_qualified = True
        else:
            reasons.append("Does not specialize in personal loans")
        
        # Check ICP match
        icp_match = structured_data.get("icp_match", "").lower()
        if "yes" in icp_match:
            reasons.append("Matches ideal customer profile")
            is_qualified = is_qualified and True
        else:
            reasons.append("Does not match ideal customer profile")
            is_qualified = False
        
        # Check for decision makers
        leads = structured_data.get("leads", [])
        decision_makers = sum(1 for lead in leads if isinstance(lead, dict) and "yes" in lead.get("is_decision_maker", "").lower())
        
        if decision_makers > 0:
            reasons.append(f"Found {decision_makers} decision maker(s)")
        else:
            reasons.append("No decision makers identified")
            is_qualified = False
        
        # Check technology focus (bonus)
        tech_focus = structured_data.get("technology_focus", "").lower()
        if "yes" in tech_focus:
            reasons.append("Technology-focused company")
        
        return is_qualified, reasons

# Streamlit integration helper
def create_enrichment_service() -> Optional[EnrichmentService]:
    """Create enrichment service with API key from environment or user input"""
    import os
    
    api_key = os.getenv('SIXTYFOUR_API_KEY', '42342922-b737-43bf-8e67-68be5108be7b')
    
    if not api_key:
        return None
    
    return EnrichmentService(api_key) 