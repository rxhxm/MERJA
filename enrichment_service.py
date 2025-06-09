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
                description_parts.append(
                    f"Business structure: {company_data['business_structure']}")
            if company_data.get('license_types'):
                # First 3 license types
                license_types = company_data['license_types'][:3]
                description_parts.append(
                    f"Licensed for: {', '.join(license_types)}")
            if company_data.get('states_licensed'):
                states = company_data['states_licensed'][:5]  # First 5 states
                description_parts.append(f"Licensed in: {', '.join(states)}")
            
            description = "; ".join(
                description_parts) if description_parts else f"Financial services company with NMLS ID {nmls_id}"
            
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
                "notes": "Key insights about this company's business model and relevance for personal lending partnerships."}
            
            people_struct = {
                "name": "Full name of the person",
                "title": "Job title at the company", 
                "linkedin": "LinkedIn profile URL",
                "email": "Email address if available",
                "phone": "Phone number if available",
                "is_decision_maker": "Is this person a key decision maker for lending partnerships? Answer 'Yes' ONLY for C-suite executives, presidents, VPs, directors, or heads of lending/credit/business development.",
                "relevance_score": "How relevant is this person for Fido's business (1-10 scale)?"}
            
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"}
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
                
                logger.info(
                    f"Successfully enriched {company_name} in {elapsed:.2f}s")
                return {
                    "success": True,
                    "company_name": company_name,
                    "nmls_id": nmls_id,
                    "data": data,
                    "processing_time": elapsed
                }
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Error enriching {company_name} after {elapsed:.2f}s: {str(e)}")
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
        progress_callback: Optional[callable] = None,
        cancellation_check: Optional[callable] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Enrich a batch of companies and return structured results
        
        Args:
            companies: List of company data from NMLS search
            progress_callback: Optional callback function for progress updates
            cancellation_check: Optional function that returns True if processing should be cancelled
            
        Returns:
            Tuple of (enriched_companies_df, contacts_df)
        """
        if not companies:
            return pd.DataFrame(), pd.DataFrame()
        
        # Check for cancellation before starting
        if cancellation_check and cancellation_check():
            raise Exception("Enrichment cancelled before starting")

        # Get reference companies for ICP matching (first 3 high-value targets)
        reference_companies = []
        for company in companies[:3]:
            if company.get('business_score', 0) > 70:
                reference_companies.append(company['company_name'])
        
        if not reference_companies:
            reference_companies = [companies[0]['company_name']]
        
        logger.info(f"Starting enrichment of {len(companies)} companies")
        logger.info(f"Using reference companies: {reference_companies}")
        
        # Set up concurrency control with smaller batches for better
        # responsiveness
        # Limit to 3 concurrent for better control
        semaphore = asyncio.Semaphore(min(self.max_concurrent, 3))
        limits = httpx.Limits(
            max_keepalive_connections=self.max_concurrent,
            max_connections=self.max_concurrent + 5
        )
        
        # Process companies in smaller chunks for better cancellation
        # responsiveness
        results = []
        chunk_size = 5  # Process 5 companies at a time

        async with httpx.AsyncClient(limits=limits, timeout=self.timeout) as client:
            for chunk_start in range(0, len(companies), chunk_size):
                # Check for cancellation before each chunk
                if cancellation_check and cancellation_check():
                    raise Exception("Enrichment cancelled during processing")

                chunk_end = min(chunk_start + chunk_size, len(companies))
                chunk_companies = companies[chunk_start:chunk_end]

                # Create tasks for this chunk
                tasks = []
                for company in chunk_companies:
                    task = self.enrich_single_company(
                        client, semaphore, company, reference_companies
                    )
                    tasks.append(task)
                
                # Process chunk with progress tracking
                chunk_results = []
                for task in asyncio.as_completed(tasks):
                    # Check for cancellation before processing each result
                    if cancellation_check and cancellation_check():
                        # Cancel remaining tasks
                        for remaining_task in tasks:
                            if not remaining_task.done():
                                remaining_task.cancel()
                        raise Exception(
                            "Enrichment cancelled during chunk processing")

                    result = await task
                    chunk_results.append(result)
                    
                    # Update progress
                    completed = len(results) + len(chunk_results)
                if progress_callback:
                    progress_callback(completed, len(companies))
                
                results.extend(chunk_results)

                # Small delay between chunks to allow for cancellation checks
                await asyncio.sleep(0.1)

        # Final cancellation check before processing results
        if cancellation_check and cancellation_check():
            raise Exception("Enrichment cancelled before result processing")

        # Process results into structured DataFrames
        return self._process_enrichment_results(results, companies)
    
    def _process_enrichment_results(
        self, 
        results: List[Dict[str, Any]], 
        original_companies: List[Dict[str, Any]]
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Process enrichment results into structured dataframes with enhanced qualification logic
        """
        enriched_companies = []
        all_contacts = []
        
        for idx, result in enumerate(results):
            # Get original company data
            original_company = original_companies[idx] if idx < len(
                original_companies) else {}

            # Base company record
            company_record = original_company.copy()
            company_record.update({
                'enrichment_timestamp': datetime.now().isoformat(),
                'enrichment_status': 'Success' if result['success'] else 'Failed',
                'enrichment_processing_time': result.get('processing_time', 0)
            })

            if not result['success']:
                company_record['enrichment_error'] = result.get('error', 'Unknown error')
                company_record['enrichment_quality_score'] = 0
                company_record['is_qualified_lead'] = False
                enriched_companies.append(company_record)
                continue

            # Extract structured data
            api_data = result.get('data', {})
            structured_data = api_data.get('structured_data', {})
            confidence_score = api_data.get('confidence_score', 0)

            # Add enriched fields with enhanced processing
            company_record.update({
                'enrichment_confidence': confidence_score,
                'enriched_website': structured_data.get('website', ''),
                'enriched_company_linkedin': structured_data.get('company_linkedin', ''),
                'enriched_industry': structured_data.get('industry', ''),
                'enriched_specializes_in_personal_loans': structured_data.get('specializes_in_personal_loans', ''),
                'enriched_target_customer_segment': structured_data.get('target_customer_segment', ''),
                'enriched_lending_volume': structured_data.get('lending_volume', ''),
                'enriched_technology_focus': structured_data.get('technology_focus', ''),
                'enriched_icp_match': structured_data.get('icp_match', ''),
                'enriched_competitive_positioning': structured_data.get('competitive_positioning', ''),
                'enriched_notes': structured_data.get('notes', '')
            })

            # Enhanced employee count parsing
            employee_str = structured_data.get('num_employees', '0')
            employee_count = self._parse_employee_count(employee_str)
            company_record['enriched_num_employees'] = employee_count
            company_record['enriched_num_employees_raw'] = employee_str

            # Process contacts/leads
            contacts = structured_data.get('leads', [])
            decision_makers = []
            qualified_contacts = []

            for contact in contacts:
                if isinstance(contact, dict):
                    contact_record = {
                        'company_name': result['company_name'],
                        'nmls_id': result.get('nmls_id', ''),
                        'contact_name': contact.get('name', ''),
                        'contact_title': contact.get('title', ''),
                        'contact_linkedin': contact.get('linkedin', ''),
                        'contact_email': contact.get('email', ''),
                        'contact_phone': contact.get('phone', ''),
                        'is_decision_maker': contact.get('is_decision_maker', '').lower(),
                        'relevance_score': contact.get('relevance_score', 0),
                        'enrichment_timestamp': datetime.now().isoformat()
                    }
                    
                    # Enhanced decision maker detection
                    is_dm = self._is_enhanced_decision_maker(contact)
                    contact_record['is_enhanced_decision_maker'] = is_dm
                    contact_record['decision_maker_score'] = self._calculate_decision_maker_score(contact)
                    
                    all_contacts.append(contact_record)
                    
                    if is_dm:
                        decision_makers.append(contact)
                    
                    # Qualify contacts for relevance
                    if self._is_relevant_contact(contact):
                        qualified_contacts.append(contact)

            # Enhanced qualification assessment
            is_qualified, qualification_reasons = self._assess_enhanced_qualification(
                structured_data, contacts, confidence_score, employee_count
            )

            company_record.update({
                'enrichment_quality_score': self._calculate_enrichment_quality(structured_data),
                'is_qualified_lead': is_qualified,
                'qualification_reasons': '; '.join(qualification_reasons),
                'decision_maker_count': len(decision_makers),
                'qualified_contact_count': len(qualified_contacts),
                'total_contact_count': len(contacts)
            })

            enriched_companies.append(company_record)

        # Create DataFrames
        companies_df = pd.DataFrame(enriched_companies)
        contacts_df = pd.DataFrame(all_contacts)

        return companies_df, contacts_df

    def _parse_employee_count(self, employee_str: str) -> int:
        """
        Enhanced employee count parsing similar to bild enrich functionality
        """
        if not employee_str or not isinstance(employee_str, str):
            return 0

        import re
        
        # General cleanup
        cleaned_str = employee_str.lower()
        phrases_to_remove = ["employees", "staff members", "approximately", "about", "around", "listed on linkedin"]
        for phrase in phrases_to_remove:
            cleaned_str = cleaned_str.replace(phrase, "")

        # Remove content in parentheses
        cleaned_str = re.sub(r'\(.*?\)', '', cleaned_str).strip()

        # Extract numbers
        numbers = re.findall(r'\d+', cleaned_str)

        if not numbers:
            return 0

        # Take the first number (usually the lower bound of a range)
        return int(numbers[0])

    def _is_enhanced_decision_maker(self, contact: Dict[str, Any]) -> bool:
        """
        Enhanced decision maker detection with title analysis
        """
        title = contact.get('title', '').lower()
        name = contact.get('name', '').lower()
        
        # C-suite and executive titles
        executive_keywords = ['ceo', 'cfo', 'coo', 'cto', 'chief', 'president', 'founder', 'owner']
        vp_keywords = ['vp', 'vice president', 'v.p.']
        director_keywords = ['director', 'head of', 'head ', 'managing director']
        
        # Lending-specific titles
        lending_keywords = ['lending', 'credit', 'loans', 'underwriting', 'risk']
        
        # Check API response first
        api_decision_maker = contact.get('is_decision_maker', '').lower()
        if 'yes' in api_decision_maker:
            return True
            
        # Check title keywords
        for keyword in executive_keywords:
            if keyword in title:
                return True
                
        for keyword in vp_keywords:
            if keyword in title:
                return True
                
        for keyword in director_keywords:
            if keyword in title and any(lk in title for lk in lending_keywords):
                return True
                
        return False

    def _calculate_decision_maker_score(self, contact: Dict[str, Any]) -> int:
        """
        Calculate decision maker score (1-10) based on title and role
        """
        title = contact.get('title', '').lower()
        
        # C-suite gets highest scores
        if any(keyword in title for keyword in ['ceo', 'chief executive', 'founder', 'owner']):
            return 10
        if any(keyword in title for keyword in ['cfo', 'coo', 'cto', 'chief']):
            return 9
        if any(keyword in title for keyword in ['president', 'managing director']):
            return 9
            
        # VPs get high scores
        if any(keyword in title for keyword in ['vp', 'vice president', 'v.p.']):
            return 8
            
        # Directors get medium-high scores
        if 'director' in title:
            return 7
            
        # Managers get medium scores
        if 'manager' in title:
            return 5
            
        # Team leads get lower scores
        if any(keyword in title for keyword in ['lead', 'supervisor']):
            return 4
            
        # Default for other roles
        return 2

    def _is_relevant_contact(self, contact: Dict[str, Any]) -> bool:
        """
        Determine if contact is relevant for lending partnerships
        """
        title = contact.get('title', '').lower()
        relevant_keywords = [
            'lending', 'credit', 'loans', 'business development', 'partnerships',
            'sales', 'operations', 'underwriting', 'risk', 'finance', 'strategy'
        ]
        
        return any(keyword in title for keyword in relevant_keywords) or self._is_enhanced_decision_maker(contact)

    def _assess_enhanced_qualification(
        self, 
        structured_data: Dict[str, Any], 
        contacts: List[Dict[str, Any]], 
        confidence_score: float,
        employee_count: int
    ) -> Tuple[bool, List[str]]:
        """
        Enhanced qualification assessment similar to bild enrich logic
        """
        reasons = []
        is_qualified = False
        
        # Confidence score check
        if confidence_score >= 7.0:
            reasons.append(f"Good confidence score ({confidence_score})")
            confidence_qualified = True
        else:
            reasons.append(f"Low confidence score ({confidence_score})")
            confidence_qualified = False
            
        # ICP match check
        icp_match = structured_data.get('icp_match', '').lower()
        if any(keyword in icp_match for keyword in ['yes', 'good target', 'suitable', 'match']):
            reasons.append("Matches ICP profile")
            icp_qualified = True
        else:
            reasons.append("Does not match ICP profile")
            icp_qualified = False
            
        # Personal loans specialization check
        personal_loans = structured_data.get('specializes_in_personal_loans', '').lower()
        if 'yes' in personal_loans:
            reasons.append("Specializes in personal loans")
            loans_qualified = True
        else:
            reasons.append("Does not specialize in personal loans")
            loans_qualified = False
            
        # Decision maker count
        decision_maker_count = sum(1 for contact in contacts 
                                 if isinstance(contact, dict) and 
                                 self._is_enhanced_decision_maker(contact))
        
        if decision_maker_count > 0:
            reasons.append(f"Found {decision_maker_count} decision makers")
            dm_qualified = True
        else:
            reasons.append("No decision makers found")
            dm_qualified = False
            
        # Employee count check
        if employee_count >= 10:
            reasons.append(f"Sufficient size ({employee_count} employees)")
            size_qualified = True
        else:
            reasons.append(f"Small company ({employee_count} employees)")
            size_qualified = False
            
        # Technology focus check
        tech_focus = structured_data.get('technology_focus', '').lower()
        if 'yes' in tech_focus:
            reasons.append("Technology-focused")
            tech_qualified = True
        else:
            tech_qualified = False
            
        # Overall qualification logic
        # Must have ICP match AND (personal loans OR decision makers) AND reasonable confidence
        if icp_qualified and confidence_qualified and (loans_qualified or dm_qualified):
            is_qualified = True
            reasons.append("✅ QUALIFIED: Meets core criteria")
        else:
            reasons.append("❌ NOT QUALIFIED: Missing key criteria")
            
        return is_qualified, reasons

    def _calculate_enrichment_quality(
            self, structured_data: Dict[str, Any]) -> float:
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
        personal_loan_focus = structured_data.get(
            "specializes_in_personal_loans", "").lower()
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
    
    def _assess_company_qualification(
            self, structured_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Assess if a company is a qualified lead for Fido"""
        reasons = []
        is_qualified = False
        
        # Check personal loan specialization
        personal_loan_focus = structured_data.get(
            "specializes_in_personal_loans", "").lower()
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
        decision_makers = sum(
            1 for lead in leads if isinstance(
                lead, dict) and "yes" in lead.get(
                "is_decision_maker", "").lower())
        
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
    
    # Try Streamlit secrets first, then environment variables
    try:
        import streamlit as st
        api_key = st.secrets.get(
            'SIXTYFOUR_API_KEY',
            os.getenv(
                'SIXTYFOUR_API_KEY',
                '42342922-b737-43bf-8e67-68be5108be7b'))
    except ImportError:
        # Streamlit not available, fall back to environment variable
        api_key = os.getenv(
            'SIXTYFOUR_API_KEY',
            '42342922-b737-43bf-8e67-68be5108be7b')
    except Exception:
        # Any other error, fall back to environment variable
        api_key = os.getenv(
            'SIXTYFOUR_API_KEY',
            '42342922-b737-43bf-8e67-68be5108be7b')
    
    if not api_key:
        return None
    
    return EnrichmentService(api_key) 
