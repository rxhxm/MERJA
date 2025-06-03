#!/usr/bin/env python3
"""
NMLS Database Search & Intelligence Platform
Comprehensive Streamlit app for searching and analyzing NMLS database with AI-powered natural language processing.

Features:
- Natural language search with Claude AI
- Advanced filtering and sorting
- Business intelligence dashboard
- Lender classification and contact validation
- Export capabilities
- Real-time search suggestions
"""

import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime, timedelta
import json
import re
from typing import Dict, List, Any, Optional
import time
import logging
import nest_asyncio

# Configure Streamlit page
st.set_page_config(
    page_title="NMLS Search",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Import your modules
try:
    from natural_language_search import enhanced_search_api, LenderClassifier, ContactValidator, LenderType
except ImportError:
    st.error("natural_language_search module not found. Please ensure all required modules are available.")
    st.stop()

try:
    from search_api import SearchFilters, db_manager, SearchService, SortField, SortOrder
except ImportError:
    st.error("search_api module not found. Please ensure all required modules are available.")
    st.stop()

try:
    from enrichment_service import create_enrichment_service, EnrichmentService
except ImportError:
    st.warning("enrichment_service module not found. Enrichment features will be disabled.")
    
try:
    import asyncpg
except ImportError:
    st.error("asyncpg not installed. Please install with: pip install asyncpg")
    st.stop()
    
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .business-score-high {
        background-color: #d4edda;
        color: #155724;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .business-score-medium {
        background-color: #fff3cd;
        color: #856404;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .business-score-low {
        background-color: #f8d7da;
        color: #721c24;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .lender-type-target {
        background-color: #d1ecf1;
        color: #0c5460;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .lender-type-exclude {
        background-color: #f8d7da;
        color: #721c24;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
    .lender-type-mixed {
        background-color: #fff3cd;
        color: #856404;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'last_query' not in st.session_state:
    st.session_state.last_query = ""
if 'enriched_results' not in st.session_state:
    st.session_state.enriched_results = None
if 'selected_companies' not in st.session_state:
    st.session_state.selected_companies = []

# Helper functions
def run_async(coro):
    """Run async function in Streamlit with proper event loop handling"""
    try:
        # For Streamlit, we need to create a fresh event loop
        import asyncio
        import sys
        
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(coro)
            return result
        finally:
            loop.close()
            # It's good practice to reset the event loop for the current context
            # if it was explicitly set.
            try:
                if asyncio.get_event_loop_policy().get_event_loop() is loop:
                    asyncio.set_event_loop(None)
            except RuntimeError: # Handles case where no current event loop was set by this thread
                pass
            
    except Exception as e:
        logger.error(f"Async execution error. Original error: {e}")
        # Re-raise the original exception rather than attempting a problematic fallback
        raise e

# Database connection helper with better lifecycle management
@st.cache_resource
def get_database_pool():
    """Get a cached database connection pool"""
    # Don't use cached pools in Streamlit - create fresh connections
    return None

# Simplified search function that creates its own connection
async def run_natural_search(query: str, apply_filters: bool = True, page: int = 1, page_size: int = 20):
    """Run natural language search with proper error handling"""
    try:
        # Import search API
        from search_api import SearchService, SearchFilters, SortField, SortOrder
        from natural_language_search import LenderClassifier, ContactValidator, LenderType
        
        # Parse the query for business intelligence
        query_lower = query.lower()
        
        # Create search filters based on query analysis
        filters = SearchFilters()
        
        # Extract location information (fix typos in common state names)
        query_clean = query_lower.replace("califprnia", "california").replace("califronia", "california")
        
        if "california" in query_clean or " ca " in query_clean or query_clean.endswith(" ca"):
            filters.states = ["CA"]
        elif "texas" in query_clean or " tx " in query_clean or query_clean.endswith(" tx"):
            filters.states = ["TX"]
        elif "florida" in query_clean or " fl " in query_clean or query_clean.endswith(" fl"):
            filters.states = ["FL"]
        elif "new york" in query_clean or " ny " in query_clean or query_clean.endswith(" ny"):
            filters.states = ["NY"]
        
        # For basic company searches, just search by company name
        if any(term in query_clean for term in ["companies", "company", "companie"]):
            # Don't set specific license filters for basic company searches
            pass
        elif any(term in query_lower for term in ["personal loan", "consumer credit", "consumer loan", "installment loan", "finance company", "small loan"]):
            # Focus on unsecured personal lending license types (using actual DB license types)
            filters.license_types = [
                "Consumer Loan Company License",
                "Consumer Credit License", 
                "Consumer Lender License",
                "Consumer Loan License",
                "Consumer Finance License",
                "Sales Finance License",
                "Sales Finance Company License",
                "Small Loan Lender License",
                "Small Loan License",
                "Small Loan Company License",
                "Installment Lender License",
                "Installment Loan License",
                "Installment Loan Company License",
                "Consumer Installment Loan License",
                "Supervised Lender License",
                "Money Lender License",
                "Payday Lender License",
                "Short-Term Lender License",
                "Title Pledge Lender License",
                "Consumer Financial Services Class I License",
                "Consumer Financial Services Class II License"
            ]
        elif any(term in query_lower for term in ["mortgage", "home loan", "real estate"]):
            # User is asking for mortgage companies (should be flagged as not target for Fido)
            filters.license_types = [
                "Mortgage Loan Company License",
                "Mortgage Loan Originator License", 
                "Mortgage Broker License",
                "Mortgage Lender License",
                "Mortgage Company License",
                "Residential Mortgage Lender License"
            ]
        else:
            # Extract key search terms from the query instead of using the full phrase
            # Look for specific entity types
            if "bank" in query_lower:
                filters.query = "bank"
            elif "credit union" in query_lower:
                filters.query = "credit union"
            elif "finance" in query_lower:
                filters.query = "finance"
            elif "lending" in query_lower or "lender" in query_lower:
                filters.query = "lend"
            elif "loan" in query_lower:
                filters.query = "loan"
            # For broad searches like "companies in california", don't set a specific query filter
        
        # Create a fresh database connection for this search
        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            raise Exception("DATABASE_URL environment variable not set")
        
        # Use a simple connection instead of a pool for Streamlit
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
        
        try:
            # Get total count first
            count_query, count_params = SearchService.build_count_query(filters)
            
            logger.info(f"Count query: {count_query}")
            logger.info(f"Count params: {count_params}")
            
            total_count = await conn.fetchval(count_query, *count_params)
            logger.info(f"Total count found: {total_count}")
            
            # If no results with license type filter, fall back to broader search
            if total_count == 0 and filters.license_types:
                logger.info("No results with license filter, trying broader search...")
                # Try with just state filter
                fallback_filters = SearchFilters(states=filters.states) if filters.states else SearchFilters()
                count_query, count_params = SearchService.build_count_query(fallback_filters)
                total_count = await conn.fetchval(count_query, *count_params)
                filters = fallback_filters
                logger.info(f"Fallback search count: {total_count}")
            
            # If still no results, try even broader search
            if total_count == 0:
                logger.info("Still no results, trying very broad search...")
                broad_filters = SearchFilters()
                if filters.states:
                    broad_filters.states = filters.states
                count_query, count_params = SearchService.build_count_query(broad_filters)
                total_count = await conn.fetchval(count_query, *count_params)
                filters = broad_filters
                logger.info(f"Broad search count: {total_count}")
            
            # Get results
            search_query, search_params = SearchService.build_search_query(
                filters, page, page_size, 
                SortField.company_name, SortOrder.asc
            )
            
            logger.info(f"Search query: {search_query}")
            logger.info(f"Search params: {search_params}")
            
            rows = await conn.fetch(search_query, *search_params)
            logger.info(f"Rows fetched: {len(rows)}")
            
            # Enhance results with business intelligence
            enhanced_companies = []
            for row in rows:
                company_data = dict(row)
                
                # Classify lender type
                lender_classification = LenderClassifier.classify_company(
                    company_data.get('license_types', [])
                )
                
                # Validate contact info
                has_valid_contact, contact_issues = ContactValidator.has_valid_contact_info(company_data)
                
                # Calculate business score
                business_score = calculate_business_score(lender_classification, has_valid_contact, company_data)
                
                # Create enhanced company response
                enhanced_company = {
                    **company_data,
                    "lender_type": lender_classification.value,
                    "has_valid_contact": has_valid_contact,
                    "contact_issues": contact_issues,
                    "business_score": business_score
                }
                
                enhanced_companies.append(enhanced_company)
            
            # Sort by business score if applying business filters
            if apply_filters:
                enhanced_companies.sort(key=lambda x: x['business_score'], reverse=True)
            
            # Calculate statistics (simplified for performance)
            stats = calculate_result_stats(enhanced_companies, query)
            
            # Determine intent and explanation
            intent = "find_companies"
            explanation = f"Searching for companies matching: {query}"
            business_flags = ["claude_api_unavailable"]
            
            if "personal loan" in query_lower:
                intent = "find_personal_lenders"
                explanation = f"Searching for personal loan companies"
                if not any(c['lender_type'] == 'unsecured_personal' for c in enhanced_companies):
                    business_flags.append("no_target_lenders_found")
            elif "mortgage" in query_lower:
                intent = "find_mortgage_lenders"
                explanation = f"Searching for mortgage companies (flagged as non-target for Fido)"
                business_flags.append("mortgage_focus_detected")
            
            return {
                "query_analysis": {
                    "original_query": query,
                    "intent": intent,
                    "confidence": 0.8,
                    "explanation": explanation,
                    "business_critical_flags": business_flags
                },
                "filters_applied": filters.model_dump(exclude_unset=True),
                "companies": enhanced_companies,
                "pagination": {
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total_count + page_size - 1) // page_size
                },
                "business_intelligence": stats
            }
        
        finally:
            # Always close the connection
            await conn.close()
                
    except Exception as e:
        logger.error(f"Search error: {e}")
        import traceback
        traceback.print_exc()
        raise e

def calculate_business_score(lender_type: LenderType, has_valid_contact: bool, company_data: Dict) -> float:
    """Calculate business relevance score for Fido"""
    
    score = 0.0
    
    # Filter out trust/vehicle companies that aren't real lenders
    company_name = company_data.get('company_name', '').lower()
    if any(term in company_name for term in ['trust', 'receivables', 'securities', 'grantor']):
        # These are financial vehicles, not direct lenders - lower score
        if 'auto' in company_name or 'vehicle' in company_name:
            score = 20.0  # Auto financing trusts have some value but not primary target
        else:
            score = 10.0  # Other trusts are even less relevant
    else:
        # Lender type scoring (most important for real companies)
        if lender_type == LenderType.UNSECURED_PERSONAL:
            score += 50.0
        elif lender_type == LenderType.MIXED:
            score += 30.0  # Has some relevant licenses
        elif lender_type == LenderType.MORTGAGE:
            score += 0.0   # Not relevant for Fido
        else:
            score += 10.0  # Unknown, needs investigation
        
        # Contact information (critical for outreach)
        if has_valid_contact:
            score += 30.0
        
        # Additional factors
        if company_data.get('email'):
            score += 10.0
        if company_data.get('phone'):
            score += 10.0
        if company_data.get('website'):
            score += 5.0
        
        # License count (more licenses = more established)
        license_count = company_data.get('total_licenses', 0)
        score += min(license_count * 1, 15.0)  # Cap at 15 points, reduced multiplier
        
        # Business structure bonus (real companies have this filled)
        if company_data.get('business_structure') and company_data.get('business_structure') != 'None':
            score += 5.0
    
    return min(score, 100.0)  # Cap at 100

def calculate_result_stats(companies: List[Dict], query: str) -> Dict:
    """Calculate business intelligence statistics"""
    
    total = len(companies)
    
    # Initialize default values
    default_stats = {
        "total": total,
        "lender_type_distribution": {},
        "contact_statistics": {"valid_contact": 0, "email_only": 0, "phone_only": 0, "no_contact": 0},
        "high_value_targets": 0,
        "business_recommendations": generate_recommendations({}, {"valid_contact": 0, "email_only": 0, "phone_only": 0, "no_contact": 0}, query)
    }
    
    if total == 0:
        return default_stats
    
    # Lender type distribution
    lender_types = {}
    contact_stats = {"valid_contact": 0, "email_only": 0, "phone_only": 0, "no_contact": 0}
    high_value_targets = 0
    
    for company in companies:
        # Lender type counting
        lender_type = company.get('lender_type', 'unknown')
        lender_types[lender_type] = lender_types.get(lender_type, 0) + 1
        
        # Contact statistics
        has_email = ContactValidator.validate_email(company.get('email', ''))
        has_phone = ContactValidator.validate_phone(company.get('phone', ''))
        
        if has_email and has_phone:
            contact_stats["valid_contact"] += 1
        elif has_email:
            contact_stats["email_only"] += 1
        elif has_phone:
            contact_stats["phone_only"] += 1
        else:
            contact_stats["no_contact"] += 1
        
        # High-value targets (unsecured personal lenders with contact info)
        if (lender_type == "unsecured_personal" and 
            company.get('has_valid_contact', False) and
            company.get('business_score', 0) > 70):
            high_value_targets += 1
    
    return {
        "total": total,
        "lender_type_distribution": lender_types,
        "contact_statistics": contact_stats,
        "high_value_targets": high_value_targets,
        "business_recommendations": generate_recommendations(lender_types, contact_stats, query)
    }

def generate_recommendations(lender_types: Dict, contact_stats: Dict, query: str) -> List[str]:
    """Generate business recommendations based on search results"""
    
    recommendations = []
    
    # Lender type recommendations
    unsecured_count = lender_types.get('unsecured_personal', 0)
    mortgage_count = lender_types.get('mortgage', 0)
    
    if mortgage_count > unsecured_count:
        recommendations.append("Consider refining search to exclude mortgage lenders")
    
    if unsecured_count == 0:
        recommendations.append("No unsecured personal lenders found - try broader search terms")
    
    # Contact information recommendations
    no_contact = contact_stats.get('no_contact', 0)
    total = sum(contact_stats.values())
    
    if no_contact / total > 0.5 if total > 0 else 0:
        recommendations.append("High percentage of companies lack contact info - consider data enrichment")
    
    # Add Claude API note
    recommendations.append("Note: Advanced AI query analysis temporarily unavailable due to API limits")
    
    return recommendations

async def classify_lender(license_types: List[str]):
    """Classify lender type"""
    return LenderClassifier.classify_company(license_types)

async def validate_contact(phone: str = None, email: str = None):
    """Validate contact information"""
    phone_valid = ContactValidator.validate_phone(phone) if phone else False
    email_valid = ContactValidator.validate_email(email) if email else False
    return phone_valid, email_valid

# Helper functions
def format_business_score(score: float) -> str:
    """Format business score with color coding"""
    if score >= 70:
        return f'<span class="business-score-high">{score:.1f}</span>'
    elif score >= 40:
        return f'<span class="business-score-medium">{score:.1f}</span>'
    else:
        return f'<span class="business-score-low">{score:.1f}</span>'

def format_lender_type(lender_type: str) -> str:
    """Format lender type with color coding"""
    if lender_type == "unsecured_personal":
        return f'<span class="lender-type-target">✅ TARGET</span>'
    elif lender_type == "mortgage":
        return f'<span class="lender-type-exclude">❌ EXCLUDE</span>'
    elif lender_type == "mixed":
        return f'<span class="lender-type-mixed">⚠️ MIXED</span>'
    else:
        return f'<span>❓ UNKNOWN</span>'

async def fetch_company_licenses_with_states(nmls_id: str) -> Dict[str, List[str]]:
    """Fetch detailed license information for a company and group by license type and state"""
    try:
        # Use the same connection approach as the search function
        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            raise Exception("DATABASE_URL environment variable not set")
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
        
        try:
            rows = await conn.fetch("""
                SELECT l.license_type, l.regulator, l.active, l.status
                FROM licenses l
                JOIN companies c ON l.company_id = c.id
                WHERE c.nmls_id = $1 AND l.active = true
                ORDER BY l.license_type, l.regulator
            """, nmls_id)
            
            logger.info(f"Found {len(rows)} licenses for NMLS ID {nmls_id}")
            
            # Group licenses by type and extract states from regulator names
            license_states = {}
            for row in rows:
                license_type = row["license_type"]
                regulator = row["regulator"] or ""
                
                if license_type not in license_states:
                    license_states[license_type] = set()
                
                # Extract state from regulator name
                state = extract_state_from_regulator(regulator)
                if state:
                    license_states[license_type].add(state)
                    logger.info(f"Extracted state {state} from regulator '{regulator}' for license type '{license_type}'")
                else:
                    logger.warning(f"Could not extract state from regulator '{regulator}' for license type '{license_type}'")
            
            # Convert sets to sorted lists
            result = {license_type: sorted(list(states)) for license_type, states in license_states.items()}
            logger.info(f"Final license-state mapping: {result}")
            return result
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Error fetching company licenses for NMLS ID {nmls_id}: {e}")
        import traceback
        traceback.print_exc()
        return {}

def extract_state_from_regulator(regulator: str) -> str:
    """Extract state abbreviation from regulator name"""
    if not regulator:
        return ""
    
    # Mapping of state names to abbreviations
    state_mapping = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
        'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
        'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
        'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
        'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
        'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
        'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'Wyoming': 'WY'
    }
    
    regulator_lower = regulator.lower()
    
    # Check for state names in the regulator name
    for state_name, state_abbr in state_mapping.items():
        if state_name in regulator_lower:
            return state_abbr
    
    # If no full state name found, try to extract common patterns
    # Pattern like "CA Department of..." or "TX Finance Commission"
    import re
    state_pattern = r'\b([A-Z]{2})\b'
    match = re.search(state_pattern, regulator)
    if match and match.group(1) in state_mapping.values():
        return match.group(1)
    
    return ""

def format_license_summary_with_states(company: Dict) -> str:
    """Format license summary with state information for each license type"""
    try:
        nmls_id = company.get('nmls_id', '')
        if not nmls_id:
            return "License details unavailable"
        
        # First try to fetch detailed license information
        license_states = run_async(fetch_company_licenses_with_states(nmls_id))
        
        # If that fails or returns empty, use fallback approach with existing data
        if not license_states:
            st.write(f"Debug: Database fetch failed for {nmls_id}, using fallback approach")
            # Use existing data as fallback
            license_types = company.get('license_types', []) or []
            states_licensed = company.get('states_licensed', []) or []
            
            if not license_types:
                return "License details unavailable"
            
            # Since we don't have per-license state mapping, distribute states across license types
            # This is a simplified approach for demonstration
            from natural_language_search import LenderClassifier
            
            target_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
            exclude_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
            other_licenses = [lt for lt in license_types if lt not in LenderClassifier.UNSECURED_PERSONAL_LICENSES and lt not in LenderClassifier.MORTGAGE_LICENSES]
            
            summary_parts = []
            states_str = ", ".join(sorted(states_licensed)) if states_licensed else "Unknown"
            
            if target_licenses:
                summary_parts.append(f"🎯 {len(target_licenses)} personal ({states_str})")
            
            if exclude_licenses:
                summary_parts.append(f"❌ {len(exclude_licenses)} mortgage ({states_str})")
            
            if other_licenses:
                summary_parts.append(f"❓ {len(other_licenses)} other ({states_str})")
            
            result = " | ".join(summary_parts) if summary_parts else "License details unavailable"
            st.write(f"Debug: Fallback result for {company.get('company_name', 'Unknown')}: {result}")
            return result
        
        # Import classification for license categorization
        from natural_language_search import LenderClassifier
        
        # Categorize licenses
        target_licenses = {}
        exclude_licenses = {}
        other_licenses = {}
        
        for license_type, states in license_states.items():
            if license_type in LenderClassifier.UNSECURED_PERSONAL_LICENSES:
                target_licenses[license_type] = states
            elif license_type in LenderClassifier.MORTGAGE_LICENSES:
                exclude_licenses[license_type] = states
            else:
                other_licenses[license_type] = states
        
        # Build summary text
        summary_parts = []
        
        if target_licenses:
            target_count = len(target_licenses)
            target_states = set()
            for states in target_licenses.values():
                target_states.update(states)
            target_states_str = ", ".join(sorted(target_states))
            summary_parts.append(f"🎯 {target_count} personal ({target_states_str})")
        
        if exclude_licenses:
            exclude_count = len(exclude_licenses)
            exclude_states = set()
            for states in exclude_licenses.values():
                exclude_states.update(states)
            exclude_states_str = ", ".join(sorted(exclude_states))
            summary_parts.append(f"❌ {exclude_count} mortgage ({exclude_states_str})")
        
        if other_licenses:
            other_count = len(other_licenses)
            other_states = set()
            for states in other_licenses.values():
                other_states.update(states)
            other_states_str = ", ".join(sorted(other_states))
            summary_parts.append(f"❓ {other_count} other ({other_states_str})")
        
        result = " | ".join(summary_parts) if summary_parts else "License details unavailable"
        st.write(f"Debug: Database result for {company.get('company_name', 'Unknown')}: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error formatting license summary: {e}")
        import traceback
        traceback.print_exc()
        st.write(f"Debug: Exception in format_license_summary_with_states: {e}")
        return "License details unavailable"

# Main app
def main():
    # Header
    st.markdown('<h1 class="main-header">NMLS Search</h1>', unsafe_allow_html=True)
    
    # Show only natural language search page
    show_natural_search_page()

def show_natural_search_page():
    """Natural language search interface"""
    st.header("NMLS Lender Search")
    
    # Prominent filtering section
    st.subheader("🎯 Search & Filter")
    
    # Main search and filters in a clean layout
    col1, col2, col3 = st.columns(3)
    
    with col1:
        query = st.text_input(
            "Search for lenders:",
            value=st.session_state.last_query,
            placeholder="e.g., personal loan companies, banks in California, etc.",
            key="nl_search_input"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
    
    # Primary filters (the two most important things)
    st.markdown("### 🔧 Primary Filters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**📍 States Licensed In:**")
        selected_states = st.multiselect(
            "Filter by states",
            ["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI", "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI", "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT", "AR", "NV", "IA", "MS", "KS", "NM", "NE", "ID", "WV", "NH", "ME", "MT", "RI", "DE", "SD", "ND", "AK", "VT", "WY", "HI", "DC"],
            help="Select states to filter lenders"
        )
    
    with col2:
        st.markdown("**🏦 Lender Type:**")
        lender_type_filter = st.selectbox(
            "Filter by lender type",
            ["All Types", "Unsecured Personal (TARGET)", "Mortgage (EXCLUDE)", "Mixed", "Unknown"],
            help="Filter by the type of lending business"
        )
    
    with col3:
        st.markdown("**⚙️ Options:**")
        show_details = st.checkbox("Show detailed analysis", value=False, help="Show query processing details")
    
    # Perform search
    if search_clicked and query:
        st.session_state.last_query = query
        with st.spinner("🔍 Searching database..."):
            try:
                # Use high page_size to get all results
                result = run_async(run_natural_search(query, True, 1, 10000))
                if result:
                    st.session_state.search_results = result
                    st.session_state.selected_companies = []
                else:
                    st.error("❌ No results found. Try a different search.")
            except Exception as e:
                st.error(f"❌ Search failed: {str(e)}")
                logger.error(f"Search error: {e}")
    
    # Display results with focus on states and lender type
    if st.session_state.search_results:
        result = st.session_state.search_results
        
        # Apply post-search filters
        companies = result['companies']
        
        # Filter by states if selected
        if selected_states:
            companies = [c for c in companies if any(state in c.get('states_licensed', []) for state in selected_states)]
        
        # Filter by lender type if selected
        if lender_type_filter != "All Types":
            lender_map = {
                "Unsecured Personal (TARGET)": "unsecured_personal",
                "Mortgage (EXCLUDE)": "mortgage", 
                "Mixed": "mixed",
                "Unknown": "unknown"
            }
            target_type = lender_map.get(lender_type_filter)
            if target_type:
                companies = [c for c in companies if c.get('lender_type') == target_type]
        
        # Summary metrics
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Found", len(companies))
        with col2:
            target_count = sum(1 for c in companies if c.get('lender_type') == 'unsecured_personal')
            st.metric("🎯 Target Lenders", target_count)
        with col3:
            exclude_count = sum(1 for c in companies if c.get('lender_type') == 'mortgage')
            st.metric("❌ Mortgage Lenders", exclude_count)
        with col4:
            states_covered = len(set([state for c in companies for state in c.get('states_licensed', [])]))
            st.metric("States Covered", states_covered)
        
        # Detailed analysis (collapsible)
        if show_details:
            with st.expander("🔍 Query Processing Details", expanded=False):
                analysis = result['query_analysis']
                st.markdown(f"**Search Intent:** {analysis['intent'].replace('_', ' ').title()}")
                st.markdown(f"**Confidence:** {analysis['confidence']:.1%}")
                st.markdown(f"**Explanation:** {analysis['explanation']}")
                
                if analysis['business_critical_flags']:
                    st.warning(f"⚠️ Flags: {', '.join(analysis['business_critical_flags'])}")
        
        # Main results table - focused on the two key things
        st.subheader(f"📋 Lenders Found ({len(companies)} results)")
        
        if companies:
            # Create focused display data
            display_data = []
            for company in companies:
                # Get states as a readable string
                states_licensed = company.get('states_licensed', [])
                states_str = ', '.join(sorted(states_licensed)) if states_licensed else 'Unknown'
                if len(states_str) > 50:  # Truncate if too long
                    states_str = states_str[:47] + '...'
                
                # Format lender type with detailed explanation
                lender_type = company.get('lender_type', 'unknown')
                license_types = company.get('license_types', [])
                
                # Handle None license_types
                if license_types is None:
                    license_types = []
                
                # Import the license sets for analysis
                from natural_language_search import LenderClassifier
                
                # Categorize this company's licenses
                target_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                exclude_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
                other_licenses = [lt for lt in license_types if lt not in LenderClassifier.UNSECURED_PERSONAL_LICENSES and lt not in LenderClassifier.MORTGAGE_LICENSES]
                
                # Create detailed lender type description
                if lender_type == 'unsecured_personal':
                    lender_display = f'🎯 TARGET ({len(target_licenses)} personal loan licenses)'
                    license_detail = f"Personal loan licenses: {', '.join(target_licenses[:2])}{'...' if len(target_licenses) > 2 else ''}" if target_licenses else "Personal loan licenses: (details unavailable)"
                elif lender_type == 'mortgage':
                    lender_display = f'❌ EXCLUDE ({len(exclude_licenses)} mortgage licenses)'
                    license_detail = f"Mortgage licenses: {', '.join(exclude_licenses[:2])}{'...' if len(exclude_licenses) > 2 else ''}" if exclude_licenses else "Mortgage licenses: (details unavailable)"
                elif lender_type == 'mixed':
                    lender_display = f'⚠️ MIXED ({len(target_licenses)} personal + {len(exclude_licenses)} mortgage)'
                    personal_part = f"Personal: {', '.join(target_licenses[:1])}{'...' if len(target_licenses) > 1 else ''}" if target_licenses else "Personal: (none)"
                    mortgage_part = f"Mortgage: {', '.join(exclude_licenses[:1])}{'...' if len(exclude_licenses) > 1 else ''}" if exclude_licenses else "Mortgage: (none)"
                    license_detail = f"{personal_part} | {mortgage_part}"
                else:
                    lender_display = f'❓ UNKNOWN ({len(other_licenses)} other licenses)'
                    license_detail = f"Other licenses: {', '.join(other_licenses[:2])}{'...' if len(other_licenses) > 2 else ''}" if other_licenses else "Other licenses: (details unavailable)"
                
                display_data.append({
                    'NMLS ID': company['nmls_id'],
                    'Company Name': company['company_name'],
                    'Lender Type': lender_display,
                    'License Details': license_detail,
                    'States Licensed': states_str,
                    'Total States': len(states_licensed),
                    'Contact Info': '✅' if (company.get('phone') and company.get('email')) else '📧' if company.get('email') else '📞' if company.get('phone') else '❌'
                })
            
            # Display as a clean table
            df = pd.DataFrame(display_data)
            
            st.dataframe(df, use_container_width=True)
            
            # Enhanced license breakdown summary
            st.markdown("### 📊 License Type Breakdown")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**🎯 TARGET Companies:**")
                target_companies = [c for c in companies if c.get('lender_type') == 'unsecured_personal']
                for company in target_companies[:3]:  # Show first 3
                    license_types = company.get('license_types', [])
                    if license_types is None:
                        license_types = []
                    target_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                    st.write(f"**{company['company_name']}**")
                    if target_licenses:
                        for license_type in target_licenses[:2]:  # Show first 2 licenses
                            st.write(f"  • {license_type}")
                        if len(target_licenses) > 2:
                            st.write(f"  • ... and {len(target_licenses) - 2} more")
                    else:
                        st.write(f"  • (license details unavailable)")
                    st.write("")
                if len(target_companies) > 3:
                    st.write(f"... and {len(target_companies) - 3} more TARGET companies")
            
            with col2:
                st.markdown("**⚠️ MIXED Companies:**")
                mixed_companies = [c for c in companies if c.get('lender_type') == 'mixed']
                for company in mixed_companies[:3]:  # Show first 3
                    license_types = company.get('license_types', [])
                    if license_types is None:
                        license_types = []
                    target_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                    exclude_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
                    st.write(f"**{company['company_name']}**")
                    if target_licenses:
                        st.write(f"  🎯 Personal: {target_licenses[0]}")
                    else:
                        st.write(f"  🎯 Personal: (none)")
                    if exclude_licenses:
                        st.write(f"  ❌ Mortgage: {exclude_licenses[0]}")
                    else:
                        st.write(f"  ❌ Mortgage: (none)")
                    st.write("")
                if len(mixed_companies) > 3:
                    st.write(f"... and {len(mixed_companies) - 3} more MIXED companies")
                elif len(mixed_companies) == 0:
                    st.info("No mixed companies found")
            
            with col3:
                st.markdown("**❓ UNKNOWN Companies:**")
                unknown_companies = [c for c in companies if c.get('lender_type') == 'unknown']
                for company in unknown_companies[:3]:  # Show first 3
                    license_types = company.get('license_types', [])
                    if license_types is None:
                        license_types = []
                    other_licenses = [lt for lt in license_types if lt not in LenderClassifier.UNSECURED_PERSONAL_LICENSES and lt not in LenderClassifier.MORTGAGE_LICENSES]
                    st.write(f"**{company['company_name']}**")
                    if other_licenses:
                        for license_type in other_licenses[:2]:  # Show first 2 licenses
                            st.write(f"  • {license_type}")
                        if len(other_licenses) > 2:
                            st.write(f"  • ... and {len(other_licenses) - 2} more")
                    else:
                        st.write(f"  • (license details unavailable)")
                    st.write("")
                if len(unknown_companies) > 3:
                    st.write(f"... and {len(unknown_companies) - 3} more UNKNOWN companies")
                elif len(unknown_companies) == 0:
                    st.info("No unknown companies found")
            
            # Show license details for selected companies
            st.markdown("### 🔍 Detailed License Analysis")
            selected_company_id = st.selectbox(
                "Select a company to see its complete license breakdown:",
                options=["None"] + [f"{c['company_name']} ({c['nmls_id']})" for c in companies],
                help="See complete license details and classification reasoning"
            )
            
            if selected_company_id != "None":
                # Extract NMLS ID from selection
                nmls_id = selected_company_id.split("(")[-1].split(")")[0]
                selected_company = next((c for c in companies if str(c['nmls_id']) == nmls_id), None)
                
                if selected_company:
                    st.markdown(f"#### {selected_company['company_name']} - Complete License Analysis")
                    
                    # Get detailed license state breakdown
                    with st.spinner("Loading detailed license breakdown..."):
                        license_state_breakdown = run_async(get_license_state_breakdown(nmls_id))
                    
                    license_types = selected_company.get('license_types', [])
                    if license_types is None:
                        license_types = []
                    lender_type = selected_company.get('lender_type', 'unknown')
                    
                    # Import the license sets for comparison
                    from natural_language_search import LenderClassifier
                    
                    # Categorize this company's licenses
                    target_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                    exclude_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
                    other_licenses = [lt for lt in license_types if lt not in LenderClassifier.UNSECURED_PERSONAL_LICENSES and lt not in LenderClassifier.MORTGAGE_LICENSES]
                    
                    # Get state breakdown by category
                    category_states = get_license_category_state_breakdown(license_state_breakdown)
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown("**🎯 TARGET Licenses Found:**")
                        if target_licenses:
                            st.success(f"✅ {len(target_licenses)} Personal Loan Licenses")
                            if category_states['target']:
                                st.info(f"📍 States: {', '.join(category_states['target'])}")
                            for license_type in target_licenses:
                                states_for_license = license_state_breakdown.get(license_type, [])
                                if states_for_license:
                                    st.write(f"• **{license_type}** ({', '.join(states_for_license)})")
                                else:
                                    st.write(f"• **{license_type}** (states unknown)")
                        else:
                            st.info("None found")
                    
                    with col2:
                        st.markdown("**❌ EXCLUDE Licenses Found:**")
                        if exclude_licenses:
                            st.error(f"❌ {len(exclude_licenses)} Mortgage Licenses")
                            if category_states['exclude']:
                                st.info(f"📍 States: {', '.join(category_states['exclude'])}")
                            for license_type in exclude_licenses:
                                states_for_license = license_state_breakdown.get(license_type, [])
                                if states_for_license:
                                    st.write(f"• **{license_type}** ({', '.join(states_for_license)})")
                                else:
                                    st.write(f"• **{license_type}** (states unknown)")
                        else:
                            st.info("None found")
                    
                    with col3:
                        st.markdown("**❓ Other Licenses:**")
                        if other_licenses:
                            st.warning(f"❓ {len(other_licenses)} Other Licenses")
                            if category_states['other']:
                                st.info(f"📍 States: {', '.join(category_states['other'])}")
                            for license_type in other_licenses:
                                states_for_license = license_state_breakdown.get(license_type, [])
                                if states_for_license:
                                    st.write(f"• **{license_type}** ({', '.join(states_for_license)})")
                                else:
                                    st.write(f"• **{license_type}** (states unknown)")
                        else:
                            st.info("None found")
                    
                    # Enhanced classification reasoning with state information
                    st.markdown("**🧠 Classification Reasoning:**")
                    if lender_type == 'unsecured_personal':
                        if category_states['target']:
                            st.success(f"✅ **TARGET**: Has {len(target_licenses)} personal loan licenses across {len(category_states['target'])} states ({', '.join(category_states['target'])}) and only {len(exclude_licenses)} mortgage licenses. This company focuses on unsecured personal lending.")
                        else:
                            st.success(f"✅ **TARGET**: Has {len(target_licenses)} personal loan licenses and only {len(exclude_licenses)} mortgage licenses. This company focuses on unsecured personal lending.")
                    elif lender_type == 'mortgage':
                        if category_states['exclude']:
                            st.error(f"❌ **EXCLUDE**: Has {len(exclude_licenses)} mortgage licenses across {len(category_states['exclude'])} states ({', '.join(category_states['exclude'])}) and only {len(target_licenses)} personal loan licenses. This company focuses on mortgage lending.")
                        else:
                            st.error(f"❌ **EXCLUDE**: Has {len(exclude_licenses)} mortgage licenses and only {len(target_licenses)} personal loan licenses. This company focuses on mortgage lending.")
                    elif lender_type == 'mixed':
                        target_states_str = f" across {len(category_states['target'])} states ({', '.join(category_states['target'])})" if category_states['target'] else ""
                        exclude_states_str = f" across {len(category_states['exclude'])} states ({', '.join(category_states['exclude'])})" if category_states['exclude'] else ""
                        st.warning(f"⚠️ **MIXED**: Has both {len(target_licenses)} personal loan licenses{target_states_str} AND {len(exclude_licenses)} mortgage licenses{exclude_states_str}. This company does both types of lending.")
                    else:
                        if category_states['other']:
                            st.info(f"❓ **UNKNOWN**: Has {len(other_licenses)} licenses across {len(category_states['other'])} states ({', '.join(category_states['other'])}) that don't clearly indicate personal loan or mortgage focus. These may be bank charters, credit union licenses, or other financial services licenses.")
                        else:
                            st.info(f"❓ **UNKNOWN**: Has {len(other_licenses)} licenses that don't clearly indicate personal loan or mortgage focus. These may be bank charters, credit union licenses, or other financial services licenses.")
                    
                    # Show all licenses in one list for easy reference with state information
                    if license_types:
                        st.markdown("**📋 Complete License List with States:**")
                        for i, license_type in enumerate(license_types, 1):
                            states_for_license = license_state_breakdown.get(license_type, [])
                            state_info = f" ({', '.join(states_for_license)})" if states_for_license else " (states unknown)"
                            
                            if license_type in LenderClassifier.UNSECURED_PERSONAL_LICENSES:
                                st.write(f"{i}. 🎯 **{license_type}**{state_info} - Personal Loan")
                            elif license_type in LenderClassifier.MORTGAGE_LICENSES:
                                st.write(f"{i}. ❌ **{license_type}**{state_info} - Mortgage")
                            else:
                                st.write(f"{i}. ❓ **{license_type}**{state_info} - Other")
            
            # Quick actions
            st.markdown("### 🚀 Quick Actions")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📊 Export Results"):
                    csv = df.to_csv(index=False)
                    st.download_button(
                        "📥 Download CSV",
                        csv,
                        f"lenders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv"
                    )
            
            with col2:
                target_lenders = [c for c in companies if c.get('lender_type') == 'unsecured_personal']
                if st.button(f"🎯 Show Only Targets ({len(target_lenders)})"):
                    # Filter to show only target lenders
                    st.session_state.lender_type_filter = "unsecured_personal"
                    st.experimental_rerun()
            
            with col3:
                if st.button("🗺️ Show State Breakdown"):
                    # Show state breakdown
                    all_states = [state for c in companies for state in c.get('states_licensed', [])]
                    state_counts = pd.Series(all_states).value_counts()
                    
                    st.markdown("**📊 Companies by State:**")
                    for state, count in state_counts.head(10).items():
                        st.write(f"**{state}**: {count} companies")
                    
                    if len(state_counts) > 10:
                        st.write(f"... and {len(state_counts) - 10} more states")
            
            # Company Enrichment Section
            st.markdown("---")
            st.markdown("### 🧠 SixtyFour AI Enrichment")
            st.markdown("Use AI to enrich company data with business intelligence, contact information, and ICP matching.")
            
            # Enrichment controls
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**🎯 Select Companies to Enrich:**")
                enrichment_filter = st.selectbox(
                    "Which companies to enrich?",
                    ["Top 5 Target Lenders", "Top 10 by Business Score", "All TARGET Lenders", "All Results", "Custom Selection"],
                    help="Choose which companies to enrich with SixtyFour API"
                )
            
            with col2:
                st.markdown("**⚙️ Enrichment Options:**")
                include_contacts = st.checkbox("Find key contacts", value=True, help="Find decision makers and key contacts")
                icp_analysis = st.checkbox("ICP matching", value=True, help="Analyze fit with ideal customer profile")
            
            with col3:
                st.markdown("**🚀 Start Enrichment:**")
                if st.button("🧠 Enrich Companies", type="secondary"):
                    # Determine which companies to enrich
                    companies_to_enrich = []
                    
                    if enrichment_filter == "Top 5 Target Lenders":
                        target_companies = [c for c in companies if c.get('lender_type') == 'unsecured_personal']
                        companies_to_enrich = sorted(target_companies, key=lambda x: x.get('business_score', 0), reverse=True)[:5]
                    elif enrichment_filter == "Top 10 by Business Score":
                        companies_to_enrich = sorted(companies, key=lambda x: x.get('business_score', 0), reverse=True)[:10]
                    elif enrichment_filter == "All TARGET Lenders":
                        companies_to_enrich = [c for c in companies if c.get('lender_type') == 'unsecured_personal']
                    elif enrichment_filter == "All Results":
                        companies_to_enrich = companies
                    
                    if companies_to_enrich:
                        # Run enrichment
                        enrichment_service = create_enrichment_service()
                        if enrichment_service:
                            st.info(f"🧠 Starting enrichment for {len(companies_to_enrich)} companies...")
                            
                            # Progress tracking
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            def progress_callback(completed, total):
                                progress = completed / total
                                progress_bar.progress(progress)
                                status_text.text(f"Enriched {completed}/{total} companies ({progress:.1%})")
                            
                            try:
                                # Run enrichment
                                enriched_df, contacts_df = run_async(
                                    enrichment_service.enrich_companies_batch(
                                        companies_to_enrich, 
                                        progress_callback
                                    )
                                )
                                
                                # Store results in session state
                                st.session_state.enriched_results = {
                                    'companies': enriched_df,
                                    'contacts': contacts_df,
                                    'timestamp': datetime.now()
                                }
                                
                                progress_bar.progress(1.0)
                                status_text.text("✅ Enrichment completed!")
                                st.success(f"Successfully enriched {len(enriched_df)} companies and found {len(contacts_df)} contacts!")
                                
                            except Exception as e:
                                st.error(f"❌ Enrichment failed: {str(e)}")
                                logger.error(f"Enrichment error: {e}")
                        else:
                            st.error("❌ SixtyFour API key not configured. Please set SIXTYFOUR_API_KEY environment variable.")
                    else:
                        st.warning("⚠️ No companies selected for enrichment.")
            
            # Display enrichment results if available
            if st.session_state.enriched_results:
                enriched_data = st.session_state.enriched_results
                enriched_df = enriched_data['companies']
                contacts_df = enriched_data['contacts']
                timestamp = enriched_data['timestamp']
                
                st.markdown("---")
                st.markdown(f"### 📊 Enrichment Results")
                st.markdown(f"*Last updated: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}*")
                
                if not enriched_df.empty:
                    # Enrichment summary
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        successful_enrichments = len(enriched_df[enriched_df['enrichment_status'] == 'Success'])
                        st.metric("✅ Successfully Enriched", successful_enrichments)
                    
                    with col2:
                        qualified_leads = len(enriched_df[enriched_df.get('is_qualified_lead', False) == True])
                        st.metric("🎯 Qualified Leads", qualified_leads)
                    
                    with col3:
                        total_contacts = len(contacts_df) if not contacts_df.empty else 0
                        st.metric("👥 Contacts Found", total_contacts)
                    
                    with col4:
                        avg_quality = enriched_df['enrichment_quality_score'].mean() if 'enrichment_quality_score' in enriched_df.columns else 0
                        st.metric("📈 Avg Quality Score", f"{avg_quality:.1f}")
                    
                    # Detailed enriched company results
                    st.markdown("#### 🏢 Enriched Company Data")
                    
                    # Filter for successful enrichments
                    successful_companies = enriched_df[enriched_df['enrichment_status'] == 'Success'].copy()
                    
                    if not successful_companies.empty:
                        # Create display dataframe
                        display_columns = ['company_name', 'nmls_id', 'lender_type']
                        
                        # Add enriched fields if they exist
                        enriched_fields = {
                            'enriched_website': 'Website',
                            'enriched_num_employees': 'Employees',
                            'enriched_specializes_in_personal_loans': 'Personal Loans?',
                            'enriched_icp_match': 'ICP Match?',
                            'enrichment_quality_score': 'Quality Score',
                            'is_qualified_lead': 'Qualified?'
                        }
                        
                        for col, display_name in enriched_fields.items():
                            if col in successful_companies.columns:
                                display_columns.append(col)
                        
                        # Show the enriched data table
                        st.dataframe(
                            successful_companies[display_columns].rename(columns=enriched_fields),
                            use_container_width=True
                        )
                        
                        # Company deep dive
                        st.markdown("#### 🔍 Company Deep Dive")
                        selected_enriched_company = st.selectbox(
                            "Select a company for detailed enrichment data:",
                            options=["None"] + [f"{row['company_name']} ({row['nmls_id']})" for _, row in successful_companies.iterrows()],
                            key="enriched_company_selector"
                        )
                        
                        if selected_enriched_company != "None":
                            # Extract NMLS ID
                            nmls_id = selected_enriched_company.split("(")[-1].split(")")[0]
                            selected_row = successful_companies[successful_companies['nmls_id'].astype(str) == nmls_id].iloc[0]
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.markdown("**🏢 Company Intelligence:**")
                                if 'enriched_website' in selected_row and selected_row['enriched_website']:
                                    st.write(f"🌐 **Website:** {selected_row['enriched_website']}")
                                if 'enriched_company_linkedin' in selected_row and selected_row['enriched_company_linkedin']:
                                    st.write(f"💼 **LinkedIn:** {selected_row['enriched_company_linkedin']}")
                                if 'enriched_num_employees' in selected_row and selected_row['enriched_num_employees']:
                                    st.write(f"👥 **Employees:** {selected_row['enriched_num_employees']}")
                                if 'enriched_industry' in selected_row and selected_row['enriched_industry']:
                                    st.write(f"🏭 **Industry:** {selected_row['enriched_industry']}")
                                
                                st.markdown("**🎯 Business Assessment:**")
                                if 'enriched_specializes_in_personal_loans' in selected_row:
                                    st.write(f"💰 **Personal Loans:** {selected_row['enriched_specializes_in_personal_loans']}")
                                if 'enriched_target_customer_segment' in selected_row:
                                    st.write(f"🎯 **Target Segment:** {selected_row['enriched_target_customer_segment']}")
                                if 'enriched_technology_focus' in selected_row:
                                    st.write(f"💻 **Tech Focus:** {selected_row['enriched_technology_focus']}")
                            
                            with col2:
                                st.markdown("**🤝 Partnership Assessment:**")
                                if 'enriched_icp_match' in selected_row:
                                    icp_match = selected_row['enriched_icp_match']
                                    if 'yes' in str(icp_match).lower():
                                        st.success(f"✅ **ICP Match:** {icp_match}")
                                    else:
                                        st.warning(f"⚠️ **ICP Match:** {icp_match}")
                                
                                if 'qualification_reasons' in selected_row and selected_row['qualification_reasons']:
                                    st.write(f"📋 **Qualification:** {selected_row['qualification_reasons']}")
                                
                                if 'enriched_competitive_positioning' in selected_row:
                                    st.write(f"⚔️ **Positioning:** {selected_row['enriched_competitive_positioning']}")
                                
                                if 'enriched_notes' in selected_row and selected_row['enriched_notes']:
                                    st.markdown("**📝 Key Insights:**")
                                    st.write(selected_row['enriched_notes'])
                    
                    # Contact information
                    if not contacts_df.empty:
                        st.markdown("#### 👥 Key Contacts Found")
                        
                        # Filter for decision makers
                        decision_makers = contacts_df[contacts_df['is_decision_maker'].str.contains('yes', case=False, na=False)]
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**🎯 Decision Makers:**")
                            if not decision_makers.empty:
                                for _, contact in decision_makers.iterrows():
                                    st.write(f"**{contact['contact_name']}** - {contact['contact_title']}")
                                    st.write(f"🏢 {contact['company_name']}")
                                    if contact['contact_email']:
                                        st.write(f"📧 {contact['contact_email']}")
                                    if contact['contact_linkedin']:
                                        st.write(f"💼 [LinkedIn]({contact['contact_linkedin']})")
                                    st.write("---")
                            else:
                                st.info("No decision makers identified.")
                        
                        with col2:
                            st.markdown("**📊 All Contacts:**")
                            contact_display = contacts_df[['company_name', 'contact_name', 'contact_title', 'contact_email', 'is_decision_maker']].copy()
                            contact_display['is_decision_maker'] = contact_display['is_decision_maker'].apply(
                                lambda x: '🎯' if 'yes' in str(x).lower() else '👤'
                            )
                            st.dataframe(contact_display, use_container_width=True)
                    
                    # Export enriched data
                    st.markdown("#### 📤 Export Enriched Data")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("📊 Export Enriched Companies"):
                            csv = enriched_df.to_csv(index=False)
                            st.download_button(
                                "📥 Download Enriched Companies CSV",
                                csv,
                                f"enriched_companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                "text/csv"
                            )
                    
                    with col2:
                        if not contacts_df.empty and st.button("👥 Export Contacts"):
                            csv = contacts_df.to_csv(index=False)
                            st.download_button(
                                "📥 Download Contacts CSV",
                                csv,
                                f"contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                "text/csv"
                            )
                else:
                    st.info("No enriched data available yet. Use the enrichment feature above to get started.")
        
        else:
            st.info("🔍 No companies match your current filters. Try adjusting the state or lender type filters above.")

async def get_license_state_breakdown(nmls_id: str) -> Dict[str, List[str]]:
    """Get detailed breakdown of which states each license type is in for a company"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Ronin320320.@db.eissjxpcsxcktoanftjw.supabase.co:5432/postgres')
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
        
        try:
            # Get individual licenses with their state information
            rows = await conn.fetch("""
                SELECT 
                    l.license_type,
                    SUBSTRING(a.state FROM 1 FOR 2) as state
                FROM licenses l
                JOIN companies c ON l.company_id = c.id
                LEFT JOIN addresses a ON c.id = a.company_id
                WHERE c.nmls_id = $1 
                AND l.active = true 
                AND a.state IS NOT NULL
                ORDER BY l.license_type, a.state
            """, nmls_id)
            
            # Group licenses by type and collect states
            license_state_map = {}
            for row in rows:
                license_type = row['license_type']
                state = row['state']
                
                if license_type and state:
                    if license_type not in license_state_map:
                        license_state_map[license_type] = set()
                    license_state_map[license_type].add(state)
            
            # Convert sets to sorted lists
            return {lt: sorted(list(states)) for lt, states in license_state_map.items()}
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Error getting license state breakdown for {nmls_id}: {e}")
        return {}

def get_license_category_state_breakdown(license_types_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Categorize licenses by TARGET/EXCLUDE/OTHER and aggregate their states"""
    from natural_language_search import LenderClassifier
    
    target_states = set()
    exclude_states = set() 
    other_states = set()
    
    for license_type, states in license_types_dict.items():
        if license_type in LenderClassifier.UNSECURED_PERSONAL_LICENSES:
            target_states.update(states)
        elif license_type in LenderClassifier.MORTGAGE_LICENSES:
            exclude_states.update(states)
        else:
            other_states.update(states)
    
    return {
        'target': sorted(list(target_states)),
        'exclude': sorted(list(exclude_states)),
        'other': sorted(list(other_states))
    }

def format_license_with_states(lender_type: str, target_licenses: List[str], exclude_licenses: List[str], 
                              other_licenses: List[str], license_state_breakdown: Dict[str, List[str]]) -> str:
    """Format lender type with state information"""
    
    # Get state breakdown by category
    category_states = get_license_category_state_breakdown(license_state_breakdown)
    
    if lender_type == 'unsecured_personal':
        target_states_str = ', '.join(category_states['target'][:3])
        if len(category_states['target']) > 3:
            target_states_str += f", +{len(category_states['target'])-3} more"
        return f"🎯 TARGET ({len(target_licenses)} personal in {target_states_str})" if category_states['target'] else f"🎯 TARGET ({len(target_licenses)} personal licenses)"
    
    elif lender_type == 'mortgage':
        exclude_states_str = ', '.join(category_states['exclude'][:3])
        if len(category_states['exclude']) > 3:
            exclude_states_str += f", +{len(category_states['exclude'])-3} more"
        return f"❌ EXCLUDE ({len(exclude_licenses)} mortgage in {exclude_states_str})" if category_states['exclude'] else f"❌ EXCLUDE ({len(exclude_licenses)} mortgage licenses)"
    
    elif lender_type == 'mixed':
        personal_str = f"{len(target_licenses)} personal"
        mortgage_str = f"{len(exclude_licenses)} mortgage"
        
        if category_states['target']:
            target_states_str = ', '.join(category_states['target'][:2])
            if len(category_states['target']) > 2:
                target_states_str += f", +{len(category_states['target'])-2} more"
            personal_str += f" ({target_states_str})"
        
        if category_states['exclude']:
            exclude_states_str = ', '.join(category_states['exclude'][:2]) 
            if len(category_states['exclude']) > 2:
                exclude_states_str += f", +{len(category_states['exclude'])-2} more"
            mortgage_str += f" ({exclude_states_str})"
            
        return f"⚠️ MIXED ({personal_str} + {mortgage_str})"
    
    else:
        other_states_str = ', '.join(category_states['other'][:3])
        if len(category_states['other']) > 3:
            other_states_str += f", +{len(category_states['other'])-3} more"
        return f"❓ UNKNOWN ({len(other_licenses)} other in {other_states_str})" if category_states['other'] else f"❓ UNKNOWN ({len(other_licenses)} other licenses)"

if __name__ == "__main__":
    main() 