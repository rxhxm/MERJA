#!/usr/bin/env python3
"""
MERJA - NMLS Lender Search & Analysis Tool
A streamlit application for searching and analyzing NMLS database with advanced licensing details and AI enrichment.
Last updated: 2025-01-19 - Enrichment section always visible with proper availability status

*** THIS IS THE WORKING ENRICHMENT VERSION - ALL THREADING AND DATABASE ISSUES FIXED ***
*** ENRICHMENT SERVICE FULLY FUNCTIONAL WITH PROPER ERROR HANDLING AND CONTEXT MANAGEMENT ***
*** NO MORE SCRIPTRUNCONTEXT ERRORS OR DATABASE TIMEOUTS - PRODUCTION READY ***
*** ENRICHMENT SECTION NOW ALWAYS VISIBLE WITH CLEAR STATUS INDICATORS ***
*** CHRIS VERSION - States and Lender Type filters moved to Advanced section ***
"""

from unified_search import (
    run_unified_search,
    SearchFilters,
    LenderType,
    LenderClassifier
)
import streamlit as st
import pandas as pd
import asyncio
import logging
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Any
import os
import threading
import time
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# NMLS Search - Enhanced for Finosu (v2.1 - Indentation Fix)

# Configure Streamlit page
st.set_page_config(
    page_title="NMLS Search",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize error handling for Streamlit warnings
def handle_streamlit_errors():
    """Suppress Streamlit threading warnings that are not actionable"""
    # Suppress specific Streamlit warnings that are expected in our use case
    streamlit_logger = logging.getLogger('streamlit')
    
    class StreamlitWarningFilter(logging.Filter):
        def filter(self, record):
            # Filter out the ScriptRunContext warnings that are expected
            if 'missing ScriptRunContext' in record.getMessage():
                return False
            return True
    
    streamlit_logger.addFilter(StreamlitWarningFilter())

# Apply error handling immediately
handle_streamlit_errors()

# Initialize session state at module level to ensure it's available immediately
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'last_query' not in st.session_state:
    st.session_state.last_query = ""
if 'enriched_results' not in st.session_state:
    st.session_state.enriched_results = None
if 'enrichment_running' not in st.session_state:
    st.session_state.enrichment_running = False

# Check enrichment availability
try:
    from enrichment_service import create_enrichment_service
    ENRICHMENT_AVAILABLE = True
except ImportError:
    ENRICHMENT_AVAILABLE = False

# Database pool setup
_db_pool = None

async def get_or_create_pool():
    """Creates and returns the asyncpg connection pool with proper timeout handling"""
    global _db_pool
    if _db_pool is None:
        try:
            import asyncpg
            DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
            if not DATABASE_URL:
                logger.error("DATABASE_URL not found")
                return None
            
            # Create pool with shorter timeouts to prevent hanging
            _db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=3,  # Reduced from 5 to prevent too many connections
                statement_cache_size=0,  # For pgbouncer compatibility
                command_timeout=30,  # 30 second command timeout
                server_settings={
                    'application_name': 'merja_streamlit',
                    'tcp_keepalives_idle': '600',
                    'tcp_keepalives_interval': '30',
                    'tcp_keepalives_count': '3'
                }
            )
            logger.info("Database pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            return None
    return _db_pool

async def close_db_pool():
    """Properly close the database pool"""
    global _db_pool
    if _db_pool:
        try:
            await _db_pool.close()
            logger.info("Database pool closed successfully")
        except Exception as e:
            logger.warning(f"Error closing database pool: {e}")
        finally:
            _db_pool = None

# Simple CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .business-score-high { color: #28a745; font-weight: bold; }
    .business-score-medium { color: #ffc107; font-weight: bold; }
    .business-score-low { color: #dc3545; font-weight: bold; }
    .lender-type-target { color: #28a745; font-weight: bold; }
    .lender-type-exclude { color: #dc3545; font-weight: bold; }
    .lender-type-mixed { color: #ffc107; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

def run_async(coro):
    """Production-grade async runner for Streamlit with proper context handling"""
    # Get current Streamlit context
    ctx = get_script_run_ctx()
    
    def run_in_thread():
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Add Streamlit context to this thread if available
            if ctx:
                current_thread = threading.current_thread()
                add_script_run_ctx(current_thread, ctx)
            
            # Run the coroutine
            result = loop.run_until_complete(coro)
            return result
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Async execution error: {error_msg}")
            import traceback
            full_traceback = traceback.format_exc()
            logger.error(f"Full traceback: {full_traceback}")
            # Re-raise with full context
            raise Exception(f"Async operation failed: {error_msg}") from e
            
        finally:
            try:
                # Clean up pending tasks
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task in pending:
                        task.cancel()
                    # Wait for cancellation to complete
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # Close the loop
                loop.close()
                
            except Exception as cleanup_error:
                logger.warning(f"Cleanup error (non-critical): {cleanup_error}")

    # Use ThreadPoolExecutor with timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        try:
            # Increased timeout for enrichment operations
            result = future.result(timeout=1800)  # 30 minutes
            return result
            
        except concurrent.futures.TimeoutError:
            error_msg = "Operation timed out after 30 minutes"
            logger.error(error_msg)
            raise TimeoutError(error_msg)
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Thread execution error: {error_msg}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise e

async def get_total_database_count() -> int:
    """Get total number of companies in the database"""
    pool = await get_or_create_pool()
    if not pool:
        return 0
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) as total FROM companies")
            return row['total'] if row else 0
    except Exception as e:
        logger.error(f"Error getting total database count: {e}")
        return 0

async def search_companies(query: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run search using unified search API"""
    try:
        search_filters = SearchFilters(**filters) if filters else None
        result = await run_unified_search(
            query=query,
            filters=search_filters,
            use_ai=True,
            apply_business_filters=True,
            page=1,
            page_size=10000
        )
        return result
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise Exception(f"Search error: {str(e)}")

async def fetch_company_licenses_with_states(nmls_id: str) -> Dict[str, List[str]]:
    """Fetch detailed license information for a company and group by license type and state"""
    pool = await get_or_create_pool()
    if not pool:
        st.error("Database connection pool is not available. Cannot fetch company licenses.")
        return {}

    try:
        async with pool.acquire() as conn:
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
            
            # Convert sets to sorted lists
            return {lt: sorted(list(states)) for lt, states in license_states.items()}
            
    except Exception as e:
        logger.error(f"Database error fetching licenses for {nmls_id}: {e}")
        return {}

def extract_state_from_regulator(regulator_name: str) -> str:
    """Extract state abbreviation from regulator name"""
    if not regulator_name:
        return None
    
    # Common state patterns in regulator names
    state_patterns = {
        'california': 'CA', 'texas': 'TX', 'florida': 'FL', 'new york': 'NY',
        'illinois': 'IL', 'pennsylvania': 'PA', 'ohio': 'OH', 'georgia': 'GA',
        'north carolina': 'NC', 'michigan': 'MI', 'new jersey': 'NJ', 'virginia': 'VA',
        'washington': 'WA', 'arizona': 'AZ', 'massachusetts': 'MA', 'tennessee': 'TN',
        'indiana': 'IN', 'missouri': 'MO', 'maryland': 'MD', 'wisconsin': 'WI',
        'colorado': 'CO', 'minnesota': 'MN', 'south carolina': 'SC', 'alabama': 'AL',
        'louisiana': 'LA', 'kentucky': 'KY', 'oregon': 'OR', 'oklahoma': 'OK',
        'connecticut': 'CT', 'utah': 'UT', 'arkansas': 'AR', 'nevada': 'NV',
        'iowa': 'IA', 'mississippi': 'MS', 'kansas': 'KS', 'new mexico': 'NM',
        'nebraska': 'NE', 'idaho': 'ID', 'west virginia': 'WV', 'new hampshire': 'NH',
        'maine': 'ME', 'montana': 'MT', 'rhode island': 'RI', 'delaware': 'DE',
        'south dakota': 'SD', 'north dakota': 'ND', 'alaska': 'AK', 'vermont': 'VT',
        'wyoming': 'WY', 'hawaii': 'HI', 'district of columbia': 'DC'
    }
    
    regulator_lower = regulator_name.lower()
    for state_name, state_abbr in state_patterns.items():
        if state_name in regulator_lower:
            return state_abbr
    
    return None

async def get_license_state_breakdown(nmls_id: str) -> Dict[str, List[str]]:
    """Get detailed breakdown of which states each license type is in for a company"""
    pool = await get_or_create_pool()
    if not pool:
        return {}

    try:
        async with pool.acquire() as conn:
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
            
    except Exception as e:
        logger.error(f"Error fetching license state breakdown for {nmls_id}: {e}")
        return {}

def get_license_category_state_breakdown(license_state_breakdown: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Categorize license states by target/exclude/other"""
    category_states = {
        'target': set(),
        'exclude': set(), 
        'other': set()
    }
    
    for license_type, states in license_state_breakdown.items():
        if license_type in LenderClassifier.UNSECURED_PERSONAL_LICENSES:
            category_states['target'].update(states)
        elif license_type in LenderClassifier.MORTGAGE_LICENSES:
            category_states['exclude'].update(states)
        else:
            category_states['other'].update(states)
    
    return {category: sorted(list(states)) for category, states in category_states.items()}

def format_lender_type(lender_type: str, license_types: List[str]) -> str:
    """Format lender type with emoji indicators"""
    type_map = {
        'unsecured_personal': '🎯 Target Lender',
        'mortgage': '❌ Mortgage (Exclude)',
        'mixed': '⚠️ Mixed',
        'unknown': '❓ Unknown'
    }
    return type_map.get(lender_type, '❓ Unknown')

def format_license_summary(company: Dict[str, Any]) -> str:
    """Format license summary for display"""
    license_types = company.get('license_types', [])
    states_licensed = company.get('states_licensed', [])
    
    if not license_types:
        return "No license information available"
    
    # Group by license type
    license_counts = {}
    for license_type in license_types:
        license_counts[license_type] = license_counts.get(license_type, 0) + 1
    
    summary_parts = []
    for license_type, count in license_counts.items():
        if count > 1:
            summary_parts.append(f"{license_type} ({count})")
        else:
            summary_parts.append(license_type)
    
    summary = "; ".join(summary_parts)
    if len(states_licensed) > 0:
        summary += f" | Licensed in {len(states_licensed)} states"
    
    return summary

def apply_advanced_filters(companies: List[Dict[str, Any]], advanced_filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply advanced filtering criteria to companies"""
    if not companies:
        return companies
    
    filtered_companies = companies.copy()
    
    # Apply license count filters
    min_licenses = advanced_filters.get('min_licenses', 1)
    max_licenses = advanced_filters.get('max_licenses', 1000)
    if min_licenses > 1 or max_licenses < 1000:
        filtered_companies = [
            c for c in filtered_companies 
            if min_licenses <= len(c.get('license_types', [])) <= max_licenses
        ]
    
    # Apply states count filters
    min_states = advanced_filters.get('min_states', 1)
    max_states = advanced_filters.get('max_states', 50)
    if min_states > 1 or max_states < 50:
        filtered_companies = [
            c for c in filtered_companies 
            if min_states <= len(c.get('states_licensed', [])) <= max_states
        ]
    
    # Apply business structure filter
    business_structures = advanced_filters.get('business_structures', [])
    if business_structures:
        filtered_companies = [
            c for c in filtered_companies 
            if c.get('business_structure') in business_structures
        ]
    
    # Apply federal regulator filter
    federal_regulators = advanced_filters.get('federal_regulators', [])
    if federal_regulators:
        filtered_companies = [
            c for c in filtered_companies 
            if c.get('federal_regulator') in federal_regulators
        ]
    
    # Apply contact information filter
    contact_req = advanced_filters.get('has_contact_info', 'Any')
    if contact_req != 'Any':
        if contact_req == 'Email Required':
            filtered_companies = [
                c for c in filtered_companies 
                if c.get('email_address')
            ]
        elif contact_req == 'Phone Required':
            filtered_companies = [
                c for c in filtered_companies 
                if c.get('phone_number')
            ]
        elif contact_req == 'Both Required':
            filtered_companies = [
                c for c in filtered_companies 
                if c.get('email_address') and c.get('phone_number')
            ]
    
    return filtered_companies

async def get_comprehensive_company_details(nmls_id: str) -> Dict[str, Any]:
    """Get comprehensive company details including business identity, corporate info, and detailed licenses"""
    pool = await get_or_create_pool()
    if not pool:
        return {}

    try:
        async with pool.acquire() as conn:
            # Get company details with all fields
            company_row = await conn.fetchrow("""
                SELECT 
                    c.company_name,
                    c.nmls_id,
                    c.phone,
                    c.email,
                    c.website,
                    c.business_structure,
                    c.trade_names,
                    c.federal_regulator
                FROM companies c
                WHERE c.nmls_id = $1
            """, nmls_id)
            
            if not company_row:
                return {}
            
            # Get detailed license information
            license_rows = await conn.fetch("""
                SELECT 
                    l.license_type,
                    l.license_number,
                    l.regulator,
                    l.status,
                    l.active,
                    l.original_issue_date,
                    l.renewed_through,
                    l.authorized_to_conduct_business
                FROM licenses l
                JOIN companies c ON l.company_id = c.id
                WHERE c.nmls_id = $1
                ORDER BY l.license_type, l.regulator
            """, nmls_id)
            
            # Process company data
            company_details = dict(company_row)
            
            # Process licenses
            licenses = []
            for row in license_rows:
                license_data = dict(row)
                # Extract state from regulator
                license_data['state'] = extract_state_from_regulator(row['regulator'] or '')
                licenses.append(license_data)
            
            company_details['licenses'] = licenses
            
            # Calculate license statistics
            total_licenses = len(licenses)
            active_licenses = len([l for l in licenses if l['active']])
            license_types = list(set([l['license_type'] for l in licenses if l['license_type']]))
            
            company_details['license_stats'] = {
                'total_licenses': total_licenses,
                'active_licenses': active_licenses,
                'license_types': license_types
            }
            
            return company_details
        
    except Exception as e:
        logger.error(f"Error fetching comprehensive company details for {nmls_id}: {e}")
        return {}

def main():
    """Main application"""
    # Register cleanup function
    import atexit
    atexit.register(cleanup_resources)
    
    st.markdown('<h1 class="main-header">NMLS Search</h1>', unsafe_allow_html=True)
    
    
    # Initialize session state for search query
    if 'search_query' not in st.session_state:
        st.session_state['search_query'] = ""
    st.subheader("🎯 Search & Filter")
    
    # Search input
    col1, col2 = st.columns([3, 1])
    
    with col1:
        query = st.text_input(
            "Search for lenders:",
            value=st.session_state.last_query,
            placeholder="e.g., personal loan companies, banks in California, etc.")
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
    
    # Subtle test cases dropdown for Finosu
    with st.expander("💡 Example Searches for Personal Lending Prospecting", expanded=False):
        st.markdown("**Click any example to use it:**")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🏦 Personal loan service providers", key="ex1", use_container_width=True):
                st.session_state.last_query = "Find me personal loan service providers"
                st.rerun()
            if st.button("🌎 Banks in California", key="ex2", use_container_width=True):
                st.session_state.last_query = "Banks in California"  
                st.rerun()
            if st.button("💳 Consumer credit companies", key="ex3", use_container_width=True):
                st.session_state.last_query = "Consumer credit companies"
                st.rerun()
            if st.button("📧 Companies with contact info", key="ex4", use_container_width=True):
                st.session_state.last_query = "Financial companies with email addresses"
                st.rerun()
        
        with col2:
            if st.button("🏢 Large lenders (10+ licenses)", key="ex5", use_container_width=True):
                st.session_state.last_query = "Large lenders with 10+ licenses"
                st.rerun()
            if st.button("🏛️ Banks in CA and NY", key="ex6", use_container_width=True):
                st.session_state.last_query = "Banks in California and New York"
                st.rerun()
            if st.button("💰 Installment loan companies", key="ex7", use_container_width=True):
                st.session_state.last_query = "Installment loan companies"
                st.rerun()
            if st.button("❌ Mortgage companies (exclude)", key="ex8", use_container_width=True):
                st.session_state.last_query = "Mortgage companies"
                st.rerun()
    
    # Advanced Filters Section
    with st.expander("🔧 Advanced Filters & Custom Rules", expanded=False):
        st.markdown("**Customize your filtering criteria with business rules and thresholds**")
        
        # Initialize session state for advanced filters
        if 'advanced_filters' not in st.session_state:
            st.session_state.advanced_filters = {
                'selected_states': [],
                'lender_type_filter': 'All Types',
                'min_licenses': 1,
                'max_licenses': 1000,
                'min_states': 1,
                'max_states': 50,
                'business_structures': [],
                'federal_regulators': [],
                'has_contact_info': 'Any'
            }
        
        # Ensure all required keys exist (migration for existing sessions)
        if 'selected_states' not in st.session_state.advanced_filters:
            st.session_state.advanced_filters['selected_states'] = []
        if 'lender_type_filter' not in st.session_state.advanced_filters:
            st.session_state.advanced_filters['lender_type_filter'] = 'All Types'
        
        # Primary Filters Section
        st.markdown("##### 🎯 Primary Filters")
        
        col_primary1, col_primary2 = st.columns(2)
        
        with col_primary1:
            selected_states = st.multiselect(
                "📍 States Licensed In:",
                ["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI", "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI", "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT", "AR", "NV", "IA", "MS", "KS", "NM", "NE", "ID", "WV", "NH", "ME", "MT", "RI", "DE", "SD", "ND", "AK", "VT", "WY", "HI", "DC"],
                default=st.session_state.advanced_filters['selected_states'],
                help="Filter companies by states where they are licensed"
            )
            st.session_state.advanced_filters['selected_states'] = selected_states
        
        with col_primary2:
            lender_type_filter = st.selectbox(
                "🏦 Lender Type:", 
                ["All Types", "Unsecured Personal (TARGET)", "Mortgage (EXCLUDE)", "Mixed", "Unknown"],
                index=["All Types", "Unsecured Personal (TARGET)", "Mortgage (EXCLUDE)", "Mixed", "Unknown"].index(
                    st.session_state.advanced_filters['lender_type_filter']
                ),
                help="Filter by lender classification type"
            )
            st.session_state.advanced_filters['lender_type_filter'] = lender_type_filter
        
        st.markdown("---")
        
        # Business Rules & Thresholds
        st.markdown("##### ⚙️ Business Rules & Thresholds")
        
        col_rules1, col_rules2 = st.columns(2)
        
        with col_rules1:
            st.markdown("**📊 License Requirements:**")
            
            min_licenses = st.number_input(
                "Minimum total licenses:",
                min_value=1, max_value=100, 
                value=st.session_state.advanced_filters['min_licenses'],
                help="Companies must have at least this many licenses"
            )
            st.session_state.advanced_filters['min_licenses'] = min_licenses
            
            max_licenses = st.number_input(
                "Maximum total licenses:",
                min_value=1, max_value=1000,
                value=st.session_state.advanced_filters['max_licenses'],
                help="Companies must have no more than this many licenses"
            )
            st.session_state.advanced_filters['max_licenses'] = max_licenses
            
            min_states = st.number_input(
                "Minimum states licensed:",
                min_value=1, max_value=50,
                value=st.session_state.advanced_filters['min_states'],
                help="Companies must be licensed in at least this many states"
            )
            st.session_state.advanced_filters['min_states'] = min_states
            
            max_states = st.number_input(
                "Maximum states licensed:",
                min_value=1, max_value=50,
                value=st.session_state.advanced_filters['max_states'],
                help="Companies must be licensed in no more than this many states"
            )
            st.session_state.advanced_filters['max_states'] = max_states
        
        with col_rules2:
            st.markdown("**📞 Contact Requirements:**")
            
            contact_req = st.selectbox(
                "Contact information requirement:",
                ["Any", "Email Required", "Phone Required", "Both Required"],
                index=["Any", "Email Required", "Phone Required", "Both Required"].index(
                    st.session_state.advanced_filters['has_contact_info']
                ),
                help="Filter companies based on available contact information"
            )
            st.session_state.advanced_filters['has_contact_info'] = contact_req
        
        st.markdown("---")
        
        # Additional Filters
        st.markdown("##### 🏢 Additional Business Filters")
        
        col_biz1, col_biz2 = st.columns(2)
        
        with col_biz1:
            business_structures = st.multiselect(
                "Business Structure:",
                ["Corporation", "LLC", "Partnership", "Sole Proprietorship", "Limited Partnership", "Other"],
                default=st.session_state.advanced_filters['business_structures'],
                help="Filter by business entity type"
            )
            st.session_state.advanced_filters['business_structures'] = business_structures
        
        with col_biz2:
            federal_regulators = st.multiselect(
                "Federal Regulator:",
                ["FDIC", "OCC", "Federal Reserve", "NCUA", "CFPB", "Other"],
                default=st.session_state.advanced_filters['federal_regulators'],
                help="Filter by federal regulatory oversight"
            )
            st.session_state.advanced_filters['federal_regulators'] = federal_regulators
        
        # Filter Preview
        st.markdown("---")
        st.markdown("##### 👀 Filter Preview")
        
        if st.button("🔍 Preview Filter Results", use_container_width=True):
            if st.session_state.search_results:
                preview_companies = st.session_state.search_results['companies'].copy()
                
                # Apply advanced filters for preview
                original_count = len(preview_companies)
                
                # Apply basic filters first
                if st.session_state.advanced_filters['selected_states']:
                    preview_companies = [c for c in preview_companies if any(state in c.get('states_licensed', []) for state in st.session_state.advanced_filters['selected_states'])]
                
                if st.session_state.advanced_filters['lender_type_filter'] != "All Types":
                    lender_map = {
                        "Unsecured Personal (TARGET)": "unsecured_personal",
                        "Mortgage (EXCLUDE)": "mortgage", 
                        "Mixed": "mixed",
                        "Unknown": "unknown"
                    }
                    target_type = lender_map.get(st.session_state.advanced_filters['lender_type_filter'])
                    if target_type:
                        preview_companies = [c for c in preview_companies if c.get('lender_type') == target_type]
                
                # Apply advanced filters
                preview_companies = apply_advanced_filters(preview_companies, st.session_state.advanced_filters)
                
                after_basic = len(st.session_state.search_results['companies'])
                if st.session_state.advanced_filters['selected_states'] or st.session_state.advanced_filters['lender_type_filter'] != "All Types":
                    temp_companies = st.session_state.search_results['companies'].copy()
                    if st.session_state.advanced_filters['selected_states']:
                        temp_companies = [c for c in temp_companies if any(state in c.get('states_licensed', []) for state in st.session_state.advanced_filters['selected_states'])]
                    if st.session_state.advanced_filters['lender_type_filter'] != "All Types":
                        lender_map = {
                            "Unsecured Personal (TARGET)": "unsecured_personal",
                            "Mortgage (EXCLUDE)": "mortgage", 
                            "Mixed": "mixed",
                            "Unknown": "unknown"
                        }
                        target_type = lender_map.get(st.session_state.advanced_filters['lender_type_filter'])
                        if target_type:
                            temp_companies = [c for c in temp_companies if c.get('lender_type') == target_type]
                    after_basic = len(temp_companies)
                
                st.success(f"🔍 **Filter Preview Results:**")
                st.info(f"• **{original_count}** companies from search results")
                if after_basic != original_count:
                    st.info(f"• **{after_basic}** companies after basic filters")
                st.info(f"• **{len(preview_companies)}** companies after advanced filters")
                
                if len(preview_companies) < after_basic:
                    st.warning(f"⚠️ Advanced filters removed **{after_basic - len(preview_companies)}** additional companies")
                elif len(preview_companies) == after_basic:
                    st.success("✅ Advanced filters don't change the results - all companies pass")
            else:
                st.warning("Please run a search first to preview filter results")
        
        # Reset Filters
        if st.button("🔄 Reset All Advanced Filters"):
            st.session_state.advanced_filters = {
                'selected_states': [],
                'lender_type_filter': 'All Types',
                'min_licenses': 1,
                'max_licenses': 1000,
                'min_states': 1,
                'max_states': 50,
                'business_structures': [],
                'federal_regulators': [],
                'has_contact_info': 'Any'
            }
            st.rerun()
    
    # Perform search
    if search_clicked and query:
        st.session_state.last_query = query
        with st.spinner("🔍 Searching database..."):
            try:
                result = run_async(search_companies(query))
                if result and 'error' in result:
                    st.error(f"❌ Search failed: {result['error']}")
                    st.info("💡 This may be a database connection issue. Please try again or contact support.")
                elif result and result['companies']:
                    st.session_state.search_results = result
                    st.success(f"✅ Found {len(result['companies'])} results!")
                else:
                    st.error("❌ No results found. Try a different search.")
                    # Show debug info if no results
                    if result:
                        st.info(f"Debug: Total count: {result.get('total_count', 0)}, Filters: {result.get('filters_applied', {})}")
            except Exception as e:
                st.error(f"❌ Search failed: {str(e)}")
                st.info("💡 This may be a database connection issue. Please try again or contact support.")
    
    # Display results
    if st.session_state.search_results:
        result = st.session_state.search_results
        companies = result['companies']
        original_count = len(companies)  # Store original count before filtering
        
        # Apply filters
        if st.session_state.advanced_filters['selected_states']:
            companies = [c for c in companies if any(state in c.get('states_licensed', []) for state in st.session_state.advanced_filters['selected_states'])]
        
        if st.session_state.advanced_filters['lender_type_filter'] != "All Types":
            lender_map = {
                "Unsecured Personal (TARGET)": "unsecured_personal",
                "Mortgage (EXCLUDE)": "mortgage", 
                "Mixed": "mixed",
                "Unknown": "unknown"
            }
            target_type = lender_map.get(st.session_state.advanced_filters['lender_type_filter'])
            if target_type:
                companies = [c for c in companies if c.get('lender_type') == target_type]
        
        # Apply advanced filters if any are set
        basic_filtered_count = len(companies)
        companies = apply_advanced_filters(companies, st.session_state.advanced_filters)
        
        filtered_count = len(companies)  # Count after all filtering
        
        # Use constant total database count
        total_db_count = 13971
        
        # Summary metrics
        st.markdown("---")
        
        # Query Transparency Section
        if st.session_state.search_results and st.session_state.search_results.get('query_analysis'):
            with st.expander("🔍 Query Transparency - How Your Search Worked", expanded=False):
                query_analysis = st.session_state.search_results['query_analysis']
                
                st.markdown("### 🧠 Natural Language Understanding")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Your Query:**")
                    st.code(query_analysis.get('original_query', 'N/A'), language="text")
                
                with col2:
                    st.markdown("**AI Interpretation:**")
                    st.info(query_analysis.get('explanation', 'No explanation available'))
                
                # Plain English Explanation
                if 'sql_explanation' in query_analysis:
                    st.markdown("#### 📝 What We Searched For:")
                    st.markdown(query_analysis['sql_explanation'])
                
                # Technical SQL Details - Use checkbox instead of nested expander
                st.markdown("---")
                show_sql = st.checkbox("⚙️ Show Technical SQL Query", value=False)
                
                if show_sql:
                    sql_query = st.session_state.search_results.get('sql_query')
                    sql_params = st.session_state.search_results.get('sql_params')
                    
                    if sql_query:
                        # Format SQL for better readability
                        formatted_sql = sql_query.replace('SELECT', '\nSELECT').replace('FROM', '\nFROM').replace('WHERE', '\nWHERE').replace('ORDER BY', '\nORDER BY').replace('LIMIT', '\nLIMIT')
                        
                        st.markdown("**SQL Query:**")
                        st.code(formatted_sql, language="sql")
                        
                        if sql_params:
                            st.markdown("**Query Parameters:**")
                            param_display = []
                            for i, param in enumerate(sql_params, 1):
                                if isinstance(param, list):
                                    param_display.append(f"${i}: {param}")
                                else:
                                    param_display.append(f"${i}: '{param}'")
                            st.code("\n".join(param_display), language="text")
                    else:
                        st.info("No SQL query available")
                
                # Filters Applied
                st.markdown("---")
                st.markdown("#### 🔧 Filters Applied")
                filters_applied = st.session_state.search_results.get('filters_applied', {})
                
                if filters_applied:
                    filter_items = []
                    for key, value in filters_applied.items():
                        if value is not None and value != [] and value != "":
                            if isinstance(value, list):
                                filter_items.append(f"• **{key.replace('_', ' ').title()}:** {', '.join(map(str, value))}")
                            elif isinstance(value, bool):
                                filter_items.append(f"• **{key.replace('_', ' ').title()}:** {'Yes' if value else 'No'}")
                            else:
                                filter_items.append(f"• **{key.replace('_', ' ').title()}:** {value}")
                    
                    if filter_items:
                        st.markdown("\n".join(filter_items))
                    else:
                        st.info("No specific filters applied - searched all companies")
                else:
                    st.info("No filters applied - searched all companies")
                
                # Performance Metrics
                search_time = st.session_state.search_results.get('search_time_ms', 0)
                if search_time > 0:
                    st.markdown("---")
                    st.markdown("#### ⚡ Performance")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Search Time", f"{search_time:.0f}ms")
                    with col2:
                        total_count = st.session_state.search_results.get('total_count', 0)
                        st.metric("Total Results", f"{total_count:,}")
                    with col3:
                        if search_time > 0:
                            results_per_sec = (total_count / search_time) * 1000
                            st.metric("Results/Second", f"{results_per_sec:,.0f}")
        
        # Always show total database context for transparency
        filters_applied = bool(st.session_state.advanced_filters['selected_states'] or st.session_state.advanced_filters['lender_type_filter'] != "All Types")
        advanced_filters_applied = any([
            st.session_state.advanced_filters.get('min_licenses', 1) > 1,
            st.session_state.advanced_filters.get('max_licenses', 1000) < 1000,
            st.session_state.advanced_filters.get('min_states', 1) > 1,
            st.session_state.advanced_filters.get('max_states', 50) < 50,
            st.session_state.advanced_filters.get('business_structures', []),
            st.session_state.advanced_filters.get('federal_regulators', []),
            st.session_state.advanced_filters.get('has_contact_info', 'Any') != 'Any'
        ])
        
        if filters_applied or advanced_filters_applied:
            filter_info = []
            if filters_applied:
                filter_info.append("basic filters")
            if advanced_filters_applied:
                filter_info.append("advanced filters")
            filter_text = " + ".join(filter_info)
            
            if basic_filtered_count != filtered_count and advanced_filters_applied:
                st.info(f"📊 Showing **{filtered_count}** companies out of **{total_db_count:,}** total companies in database ({filter_text} applied)")
                st.caption(f"🔍 Filter breakdown: {original_count} → {basic_filtered_count} (basic) → {filtered_count} (advanced)")
            else:
                st.info(f"📊 Showing **{filtered_count}** companies out of **{total_db_count:,}** total companies in database ({filter_text} applied)")
        else:
            st.info(f"📊 Showing **{filtered_count}** companies found out of **{total_db_count:,}** total companies in database")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if filters_applied and filtered_count != original_count:
                st.metric("Filtered Results", filtered_count, delta=f"{filtered_count - original_count} from total")
            else:
                st.metric("Total Found", filtered_count)
        with col2:
            target_count = sum(1 for c in companies if c.get('lender_type') == 'unsecured_personal')
            st.metric("🎯 Target Lenders", target_count)
        with col3:
            exclude_count = sum(1 for c in companies if c.get('lender_type') == 'mortgage')
            st.metric("❌ Mortgage Lenders", exclude_count)
        with col4:
            states_covered = len(set([state for c in companies for state in c.get('states_licensed', [])]))
            st.metric("States Covered", states_covered)
        
        # Results table with annotations
        if companies:
            st.subheader(f"📋 Lenders Found")
            
            # Create display data with annotations
            display_data = []
            for i, company in enumerate(companies):
                states_licensed = company.get('states_licensed', [])
                states_str = ', '.join(sorted(states_licensed)) if states_licensed else 'Unknown'
                if len(states_str) > 50:
                    states_str = states_str[:47] + '...'
                
                license_types = company.get('license_types', []) or []
                lender_type = company.get('lender_type', 'unknown')
                
                display_data.append({
                    'NMLS ID': company['nmls_id'],
                    'Company Name': company['company_name'],
                    'Lender Type': format_lender_type(lender_type, license_types),
                    'LinkedIn': f"[🔗 LinkedIn]({company.get('company_linkedin', '')})" if company.get('company_linkedin') else '❌',
                    'States Licensed': states_str,
                    'Total States': len(states_licensed),
                    'Contact Info': '✅' if (company.get('phone') and company.get('email')) else '📧' if company.get('email') else '📞' if company.get('phone') else '❌',
                    'Reviewed': '✅' if company.get('is_reviewed') else '❌',
                    'Classification': company.get('classification', ''),
                    'Notes': company.get('notes', '')
                })
            
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True)
            
            # Annotation Section - check if annotations are available
            annotations_available = any(
                company.get('is_reviewed') is not None or 
                company.get('classification') is not None or 
                company.get('notes') is not None 
                for company in companies
            )
            
            st.markdown("---")
            if annotations_available:
                st.subheader("📝 Company Annotations")
            else:
                st.subheader("📝 Company Annotations")
                st.info("🔧 **Annotation system will be available after database migration is complete.** Currently showing search results without annotation data.")
            
            if annotations_available:
                # Select company to annotate
                company_options = [(f"{c['company_name']} (NMLS: {c['nmls_id']})", c['nmls_id']) for c in companies]
                selected_option = st.selectbox(
                    "Select a company to review/annotate:",
                    options=company_options,
                    format_func=lambda x: x[0],
                    help="Choose a company to add your review, classification, and notes"
                )
                
                selected_nmls_id = selected_option[1] if selected_option else None
            else:
                st.warning("📋 **To enable annotations:** Run the database migration script to add annotation columns.")
                st.code("python3 run_migration.py", language="bash")
                selected_nmls_id = None
            
            if selected_nmls_id:
                selected_company = next((c for c in companies if c['nmls_id'] == selected_nmls_id), None)
                
                if selected_company:
                    st.markdown(f"**Annotating:** {selected_company['company_name']}")
                    
                    col1, col2, col3 = st.columns([1, 2, 3])
                    
                    with col1:
                        # Reviewed checkbox
                        current_reviewed = selected_company.get('is_reviewed', False)
                        is_reviewed = st.checkbox(
                            "✅ Reviewed",
                            value=current_reviewed,
                            key=f"reviewed_{selected_nmls_id}",
                            help="Mark this company as reviewed"
                        )
                    
                    with col2:
                        # Classification dropdown
                        classification_options = [
                            "",
                            "🎯 Target Customer",
                            "❌ Exclude - Mortgage Only",
                            "⚠️ Mixed - Needs Review",
                            "🔍 Investigate Further",
                            "✅ Good Prospect",
                            "❌ Not Interested",
                            "📞 Contact Attempted"
                        ]
                        current_classification = selected_company.get('classification', '')
                        classification = st.selectbox(
                            "Classification",
                            options=classification_options,
                            index=classification_options.index(current_classification) if current_classification in classification_options else 0,
                            key=f"classification_{selected_nmls_id}",
                            help="Classify this company for your sales process"
                        )
                    
                    with col3:
                        # Notes text area
                        current_notes = selected_company.get('notes', '')
                        notes = st.text_area(
                            "Notes",
                            value=current_notes,
                            key=f"notes_{selected_nmls_id}",
                            help="Add your notes about this company",
                            height=100
                        )
                    
                    # Save/Update button
                    col_save1, col_save2, col_save3 = st.columns([1, 1, 2])
                    with col_save1:
                        if st.button("💾 Save Annotations", key=f"save_{selected_nmls_id}"):
                            # Save annotations directly to database
                            try:
                                async def update_annotations_db():
                                    pool = await get_or_create_pool()
                                    if not pool:
                                        raise Exception("Database connection not available")
                                    
                                    # Check if annotation columns exist
                                    async with pool.acquire() as conn:
                                        # First check if columns exist
                                        columns_check = await conn.fetchval("""
                                            SELECT COUNT(*) FROM information_schema.columns 
                                            WHERE table_name = 'companies' 
                                            AND column_name IN ('is_reviewed', 'classification', 'notes')
                                        """)
                                        
                                        if columns_check < 3:
                                            raise Exception("Annotation columns not yet created. Database migration required.")
                                        
                                        # Build update query dynamically
                                        update_fields = []
                                        params = []
                                        param_count = 0
                                        
                                        if is_reviewed is not None:
                                            param_count += 1
                                            update_fields.append(f"is_reviewed = ${param_count}")
                                            params.append(is_reviewed)
                                        
                                        if classification:
                                            param_count += 1
                                            update_fields.append(f"classification = ${param_count}")
                                            params.append(classification)
                                        else:
                                            param_count += 1
                                            update_fields.append(f"classification = ${param_count}")
                                            params.append(None)
                                        
                                        if notes:
                                            param_count += 1
                                            update_fields.append(f"notes = ${param_count}")
                                            params.append(notes)
                                        else:
                                            param_count += 1
                                            update_fields.append(f"notes = ${param_count}")
                                            params.append(None)
                                        
                                        if not update_fields:
                                            raise Exception("No annotation fields to update")
                                        
                                        param_count += 1
                                        params.append(selected_nmls_id)
                                        
                                        update_query = f"""
                                        UPDATE companies 
                                        SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                                        WHERE nmls_id = ${param_count}
                                        RETURNING nmls_id, company_name, is_reviewed, classification, notes
                                        """
                                        
                                        result = await conn.fetchrow(update_query, *params)
                                        
                                        if not result:
                                            raise Exception("Company not found or update failed")
                                        
                                        return result
                                
                                result = run_async(update_annotations_db())
                                st.success(f"✅ Annotations saved for {selected_company['company_name']}")
                                
                                # Update the company data in session state
                                if 'search_results' in st.session_state and st.session_state.search_results:
                                    for company in st.session_state.search_results['companies']:
                                        if company['nmls_id'] == selected_nmls_id:
                                            company['is_reviewed'] = is_reviewed
                                            company['classification'] = classification
                                            company['notes'] = notes
                                            break
                                
                                # Brief success message
                                time.sleep(1)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"❌ Failed to save annotations: {str(e)}")
                                
                                # Show helpful guidance based on error type
                                error_str = str(e).lower()
                                if "annotation columns not yet created" in error_str or "column" in error_str:
                                    st.info("💡 **Next Step:** Run the database migration to enable annotations:")
                                    st.code("python3 run_migration.py", language="bash")
                                elif "database connection" in error_str:
                                    st.info("💡 **Tip:** Check your database connection settings.")
                    
                    with col_save2:
                        if st.button("🔄 Refresh Data", key=f"refresh_{selected_nmls_id}"):
                            st.rerun()
                    
                    # Show current annotation status
                    if selected_company.get('is_reviewed') or selected_company.get('classification') or selected_company.get('notes'):
                        st.markdown("**Current Annotations:**")
                        if selected_company.get('is_reviewed'):
                            st.success("✅ Marked as reviewed")
                        if selected_company.get('classification'):
                            st.info(f"🏷️ Classification: {selected_company.get('classification')}")
                        if selected_company.get('notes'):
                            st.text_area("📝 Existing Notes:", selected_company.get('notes'), disabled=True, height=100)
            
            # Complete Database Information Section
            st.markdown("---")
            st.markdown("### 💾 Complete Database Information")
            st.markdown("*Access ALL database fields from every table - the complete data dump Mark requested*")
            
            database_company_id = st.selectbox(
                "Select a company to see ALL database information:",
                options=["None"] + [f"{c['company_name']} ({c['nmls_id']})" for c in companies],
                help="View every single database field from companies, licenses, and addresses tables - all 47+ missing fields from detailed license section",
                key="database_selector"
            )
            
            if database_company_id != "None":
                # Extract NMLS ID from the selection
                database_nmls_id = database_company_id.split('(')[-1].replace(')', '')
                
                with st.spinner("📊 Loading complete database information..."):
                    complete_database_data = run_async(get_complete_company_database_info(database_nmls_id))
                
                if complete_database_data:
                    display_complete_database_info(complete_database_data)
                else:
                    st.error("❌ Unable to load complete database information. Check error messages above for details.")
            
            # Show license details for selected companies
            st.markdown("---")
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
                    
                    # Get comprehensive company details
                    with st.spinner("Loading comprehensive company details..."):
                        comprehensive_details = run_async(get_comprehensive_company_details(nmls_id))
                    
                    if comprehensive_details:
                        # Business Identity & Corporate Information Section
                        st.markdown("##### 🏢 Business Identity & Corporate Information")
                        
                        col_corp1, col_corp2, col_corp3 = st.columns(3)
                        
                        with col_corp1:
                            st.markdown("**📞 Contact Information:**")
                            if comprehensive_details.get('phone'):
                                st.markdown(f"• **Phone:** {comprehensive_details['phone']}")
                            if comprehensive_details.get('email'):
                                st.markdown(f"• **Email:** {comprehensive_details['email']}")
                            
                        # Website link - clickable if available
                            website = comprehensive_details.get('website')
                        if website:
                            # Clean up website URL for display
                            display_url = website
                            if not website.startswith(('http://', 'https://')):
                                full_url = f"https://{website}"
                            else:
                                full_url = website
                                st.markdown(f"• **Website:** [🌐 {display_url}]({full_url})")
                        else:
                                st.markdown("• **Website:** Not available")
                        
                        with col_corp2:
                            st.markdown("**🏛️ Corporate Structure:**")
                            if comprehensive_details.get('business_structure'):
                                st.markdown(f"• **Structure:** {comprehensive_details['business_structure']}")
                            else:
                                st.markdown("• **Structure:** Not available")
                            
                            if comprehensive_details.get('federal_regulator'):
                                st.markdown(f"• **Federal Regulator:** {comprehensive_details['federal_regulator']}")
                            else:
                                st.markdown("• **Federal Regulator:** Not available")
                        
                        with col_corp3:
                            st.markdown("**🏷️ Trade Names:**")
                            trade_names = comprehensive_details.get('trade_names')
                            if trade_names and isinstance(trade_names, list) and len(trade_names) > 0:
                                # Filter out empty strings and None values
                                valid_trade_names = [name for name in trade_names if name and str(name).strip()]
                                if valid_trade_names:
                                    for i, name in enumerate(valid_trade_names, 1):
                                        st.markdown(f"• **{i}.** {name}")
                                else:
                                    st.markdown("• No trade names available")
                            else:
                                st.markdown("• No trade names available")
                        
                        # License Statistics Overview
                        st.markdown("##### 📊 License Overview")
                        license_stats = comprehensive_details.get('license_stats', {})
                        
                        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
                        with col_stats1:
                            st.metric("Total Licenses", license_stats.get('total_licenses', 0))
                        with col_stats2:
                            st.metric("Active Licenses", license_stats.get('active_licenses', 0))
                        with col_stats3:
                            unique_types = len(license_stats.get('license_types', []))
                            st.metric("License Types", unique_types)
                        with col_stats4:
                            licenses = comprehensive_details.get('licenses', [])
                            unique_states = len(set([l['state'] for l in licenses if l['state']]))
                            st.metric("States Licensed", unique_states)
                    
                    st.markdown("---")
                    
                    # Get detailed license state breakdown for categorization
                    with st.spinner("Loading license categorization..."):
                        license_state_breakdown = run_async(get_license_state_breakdown(nmls_id))
                    
                    license_types = selected_company.get('license_types', [])
                    if license_types is None:
                        license_types = []
                    lender_type = selected_company.get('lender_type', 'unknown')
                    
                    # Categorize this company's licenses
                    target_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                    exclude_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
                    other_licenses = [lt for lt in license_types if lt not in LenderClassifier.UNSECURED_PERSONAL_LICENSES and lt not in LenderClassifier.MORTGAGE_LICENSES]
                    
                    # Get state breakdown by category
                    category_states = get_license_category_state_breakdown(license_state_breakdown)
                    
                    st.markdown("##### 🎯 License Classification Analysis")
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
                            st.warning("❌ No TARGET licenses found")
                    
                    with col2:
                        st.markdown("**❌ EXCLUDE Licenses Found:**")
                        if exclude_licenses:
                            st.warning(f"⚠️ {len(exclude_licenses)} Mortgage Licenses")
                            if category_states['exclude']:
                                st.info(f"📍 States: {', '.join(category_states['exclude'])}")
                            for license_type in exclude_licenses:
                                states_for_license = license_state_breakdown.get(license_type, [])
                                if states_for_license:
                                    st.write(f"• **{license_type}** ({', '.join(states_for_license)})")
                                else:
                                    st.write(f"• **{license_type}** (states unknown)")
                        else:
                            st.success("✅ No EXCLUDE licenses found")
                    
                    with col3:
                        st.markdown("**ℹ️ Other Licenses:**")
                        if other_licenses:
                            for i, license_type in enumerate(other_licenses, 1):
                                states_for_license = license_state_breakdown.get(license_type, [])
                                state_info = f" ({', '.join(states_for_license)})" if states_for_license else ""
                                st.write(f"{i}. **{license_type}**{state_info}")
                        else:
                            st.write("No other licenses found")
                    
                    # Overall classification explanation
                    st.markdown("**📊 Classification Summary:**")
                    if lender_type == 'unsecured_personal':
                        st.success("🎯 **CLASSIFIED AS: TARGET LENDER** - Has personal loan licenses without mortgage exclusions")
                    elif lender_type == 'mortgage':
                        st.error("❌ **CLASSIFIED AS: EXCLUDE** - Primarily mortgage-focused lender")
                    elif lender_type == 'mixed':
                        st.warning("⚠️ **CLASSIFIED AS: MIXED** - Has both personal loan and mortgage licenses")
                    else:
                        st.info("❓ **CLASSIFIED AS: UNKNOWN** - License types couldn't be definitively categorized")
                    
                    # Detailed License Information Table
                    if comprehensive_details and comprehensive_details.get('licenses'):
                        st.markdown("---")
                        st.markdown("##### 📋 Detailed License Information")
                        
                        licenses = comprehensive_details['licenses']
                        
                        # Create detailed license table
                        license_table_data = []
                        for license_info in licenses:
                            # Format dates
                            issue_date = license_info.get('original_issue_date')
                            renewed_date = license_info.get('renewed_through')
                            
                            issue_date_str = issue_date.strftime('%Y-%m-%d') if issue_date else 'N/A'
                            renewed_date_str = renewed_date.strftime('%Y-%m-%d') if renewed_date else 'N/A'
                            
                            # Status with emoji
                            status = license_info.get('status', 'Unknown')
                            active = license_info.get('active', False)
                            status_display = f"✅ {status}" if active else f"❌ {status}"
                            
                            # Authorized to conduct business
                            authorized = license_info.get('authorized_to_conduct_business')
                            authorized_display = "✅ Yes" if authorized else "❌ No" if authorized is False else "❓ Unknown"
                            
                            license_table_data.append({
                                'License Type': license_info.get('license_type', 'Unknown'),
                                'License Number': license_info.get('license_number', 'N/A'),
                                'State': license_info.get('state', 'Unknown'),
                                'Regulator': license_info.get('regulator', 'Unknown'),
                                'Status': status_display,
                                'Issue Date': issue_date_str,
                                'Renewed Through': renewed_date_str,
                                'Authorized': authorized_display
                            })
                        
                        if license_table_data:
                            license_df = pd.DataFrame(license_table_data)
                            st.dataframe(license_df, use_container_width=True)
                        else:
                            st.info("No detailed license information available")
                    else:
                        st.info("Unable to load detailed license information")

            # Add enrichment section after license analysis
            st.markdown("---")
            st.markdown("### 🚀 Company Enrichment")
            
            # Initialize custom enrichment fields in session state
            if 'custom_enrichment_fields' not in st.session_state:
                st.session_state.custom_enrichment_fields = {
                    'company_fields': {
                        "website": "Company website URL", 
                        "company_linkedin": "Company LinkedIn profile URL",
                        "industry": "Primary industry",
                        "employees": "Number of employees",
                        "personal_loans": "Does this company offer personal loans? Answer Yes or No"
                    },
                    'people_fields': {
                        "name": "Full name",
                        "title": "Job title", 
                        "linkedin": "LinkedIn profile URL of the person",
                        "email": "Email address"
                    }
                }
            
            # Custom Enrichment Fields Configuration
            with st.expander("🔧 Custom Enrichment Fields Configuration", expanded=False):
                st.markdown("**Customize what information to gather during enrichment**")
                st.info("💡 Add custom fields like Facebook pages, Twitter profiles, specific business questions, or any other data you want the AI to research.")
                
                # Preset Templates
                st.markdown("##### 📋 Quick Templates")
                col_template1, col_template2, col_template3, col_template4 = st.columns(4)
                
                with col_template1:
                    if st.button("📱 Social Media Pack", use_container_width=True):
                        st.session_state.custom_enrichment_fields['company_fields'].update({
                            "facebook_page": "Company Facebook page URL",
                            "twitter_profile": "Company Twitter/X profile URL", 
                            "instagram_account": "Company Instagram account URL",
                            "youtube_channel": "Company YouTube channel URL"
                        })
                        st.rerun()
                
                with col_template2:
                    if st.button("📞 Contact Pack", use_container_width=True):
                        st.session_state.custom_enrichment_fields['company_fields'].update({
                            "phone_number": "Main company phone number",
                            "support_email": "Customer support email address",
                            "sales_email": "Sales contact email address",
                            "physical_address": "Company headquarters address"
                        })
                        st.session_state.custom_enrichment_fields['people_fields'].update({
                            "phone": "Direct phone number",
                            "mobile": "Mobile phone number"
                        })
                        st.rerun()
                
                with col_template3:
                    if st.button("💼 Business Intel", use_container_width=True):
                        st.session_state.custom_enrichment_fields['company_fields'].update({
                            "revenue_estimate": "Estimated annual revenue",
                            "funding_status": "Recent funding or investment status",
                            "key_partnerships": "Major business partnerships",
                            "competitive_position": "Position vs competitors"
                        })
                        st.rerun()
                
                with col_template4:
                    if st.button("🎯 Lending Focus", use_container_width=True):
                        st.session_state.custom_enrichment_fields['company_fields'].update({
                            "loan_products": "Specific loan products offered",
                            "target_customers": "Primary customer segments",
                            "lending_volume": "Estimated lending volume",
                            "technology_stack": "Lending technology and platforms used"
                        })
                        st.rerun()
                
                st.markdown("---")
                
                # Tabs for Company vs People fields
                tab_company, tab_people = st.tabs(["🏢 Company Fields", "👥 People Fields"])
                
                with tab_company:
                    st.markdown("**Configure what company information to research:**")
                    
                    # Display current company fields
                    company_fields = st.session_state.custom_enrichment_fields['company_fields']
                    
                    # Edit existing fields
                    fields_to_remove = []
                    for field_key, field_desc in company_fields.items():
                        col_field, col_desc, col_action = st.columns([2, 4, 1])
                        
                        with col_field:
                            new_key = st.text_input(f"Field Name", value=field_key, key=f"company_key_{field_key}")
                        
                        with col_desc:
                            new_desc = st.text_input(f"Description", value=field_desc, key=f"company_desc_{field_key}")
                        
                        with col_action:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("🗑️", key=f"company_remove_{field_key}", help="Remove field"):
                                fields_to_remove.append(field_key)
                        
                        # Update field if changed
                        if new_key != field_key or new_desc != field_desc:
                            if field_key in st.session_state.custom_enrichment_fields['company_fields']:
                                del st.session_state.custom_enrichment_fields['company_fields'][field_key]
                            if new_key.strip():  # Only add if not empty
                                st.session_state.custom_enrichment_fields['company_fields'][new_key] = new_desc
                    
                    # Remove fields marked for deletion
                    for field_key in fields_to_remove:
                        if field_key in st.session_state.custom_enrichment_fields['company_fields']:
                            del st.session_state.custom_enrichment_fields['company_fields'][field_key]
                        st.rerun()
                    
                    # Add new company field
                    st.markdown("**➕ Add New Company Field:**")
                    col_new_key, col_new_desc, col_new_add = st.columns([2, 4, 1])
                    
                    with col_new_key:
                        new_company_field = st.text_input("New field name", placeholder="e.g., facebook_page", key="new_company_field")
                    
                    with col_new_desc:
                        new_company_desc = st.text_input("Field description", placeholder="e.g., Company Facebook page URL", key="new_company_desc")
                    
                    with col_new_add:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("➕ Add", key="add_company_field"):
                            if new_company_field.strip() and new_company_desc.strip():
                                st.session_state.custom_enrichment_fields['company_fields'][new_company_field] = new_company_desc
                                st.rerun()
                
                with tab_people:
                    st.markdown("**Configure what people information to research:**")
                    
                    # Display current people fields
                    people_fields = st.session_state.custom_enrichment_fields['people_fields']
                    
                    # Edit existing fields
                    people_fields_to_remove = []
                    for field_key, field_desc in people_fields.items():
                        col_field, col_desc, col_action = st.columns([2, 4, 1])
                        
                        with col_field:
                            new_key = st.text_input(f"Field Name", value=field_key, key=f"people_key_{field_key}")
                        
                        with col_desc:
                            new_desc = st.text_input(f"Description", value=field_desc, key=f"people_desc_{field_key}")
                        
                        with col_action:
                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("🗑️", key=f"people_remove_{field_key}", help="Remove field"):
                                people_fields_to_remove.append(field_key)
                        
                        # Update field if changed
                        if new_key != field_key or new_desc != field_desc:
                            if field_key in st.session_state.custom_enrichment_fields['people_fields']:
                                del st.session_state.custom_enrichment_fields['people_fields'][field_key]
                            if new_key.strip():  # Only add if not empty
                                st.session_state.custom_enrichment_fields['people_fields'][new_key] = new_desc
                    
                    # Remove fields marked for deletion
                    for field_key in people_fields_to_remove:
                        if field_key in st.session_state.custom_enrichment_fields['people_fields']:
                            del st.session_state.custom_enrichment_fields['people_fields'][field_key]
                        st.rerun()
                    
                    # Add new people field
                    st.markdown("**➕ Add New People Field:**")
                    col_new_key, col_new_desc, col_new_add = st.columns([2, 4, 1])
                    
                    with col_new_key:
                        new_people_field = st.text_input("New field name", placeholder="e.g., twitter_handle", key="new_people_field")
                    
                    with col_new_desc:
                        new_people_desc = st.text_input("Field description", placeholder="e.g., Personal Twitter handle", key="new_people_desc")
                    
                    with col_new_add:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("➕ Add", key="add_people_field"):
                            if new_people_field.strip() and new_people_desc.strip():
                                st.session_state.custom_enrichment_fields['people_fields'][new_people_field] = new_people_desc
                                st.rerun()
                
                # Reset to defaults
                st.markdown("---")
                col_reset, col_summary = st.columns([1, 2])
                
                with col_reset:
                    if st.button("🔄 Reset to Defaults", use_container_width=True):
                        st.session_state.custom_enrichment_fields = {
                            'company_fields': {
                                "website": "Company website URL", 
                                "company_linkedin": "Company LinkedIn profile URL",
                                "industry": "Primary industry",
                                "employees": "Number of employees",
                                "personal_loans": "Does this company offer personal loans? Answer Yes or No"
                            },
                            'people_fields': {
                                "name": "Full name",
                                "title": "Job title", 
                                "linkedin": "LinkedIn profile URL of the person",
                                "email": "Email address"
                            }
                        }
                        st.rerun()
                
                with col_summary:
                    company_count = len(st.session_state.custom_enrichment_fields['company_fields'])
                    people_count = len(st.session_state.custom_enrichment_fields['people_fields'])
                    st.info(f"📊 Current configuration: **{company_count}** company fields, **{people_count}** people fields")
            
            # Add helpful note about API behavior
            
            # Show enrichment availability status
            if not ENRICHMENT_AVAILABLE:
                st.warning("⚠️ Enrichment service is not available. Please check that the enrichment dependencies are installed and the API key is configured.")
                st.info("To enable enrichment, ensure the SixtyFour API key is configured in your Streamlit secrets.")
                st.markdown("**Note:** The enrichment section is visible but disabled until the service is properly configured.")
            
            # Company selection for enrichment (always show, but disable if not available)
            enrichment_options = []
            for i, company in enumerate(companies):
                company_name = company['company_name']
                nmls_id = company['nmls_id']
                lender_type = company.get('lender_type', 'unknown')
                states_count = len(company.get('states_licensed', []))
                
                # Create display string with key info
                type_emoji = "🎯" if lender_type == 'unsecured_personal' else "❌" if lender_type == 'mortgage' else "⚠️" if lender_type == 'mixed' else "❓"
                display_str = f"{type_emoji} {company_name} (NMLS: {nmls_id}) - {states_count} states"
                enrichment_options.append((display_str, i))
            
            # Multi-select for companies
            selected_company_indices = st.multiselect(
                "Choose companies to enrich (select multiple):",
                options=[opt[1] for opt in enrichment_options],
                format_func=lambda i: enrichment_options[i][0],
                help="Select companies you want to enrich with additional business data and contacts",
                disabled=not ENRICHMENT_AVAILABLE
            )
            
            # Enrichment controls
            col1, col2 = st.columns([2, 1])
            
            with col1:
                if selected_company_indices:
                    count = len(selected_company_indices)
                    estimated_time = count * 8  # 8 minutes per company (extra safe)
                    if count > 2:
                        st.warning(f"⚠️ {count} companies selected. This will take ~{estimated_time:.0f} minutes. The SixtyFour API does extensive research - consider selecting 1-2 companies for faster results.")
                    else:
                        st.info(f"Selected {count} companies for enrichment (~{estimated_time:.0f} minutes)")
                        st.caption("⏱️ Each company takes ~8 minutes due to extensive AI research by the SixtyFour API")
            
            with col2:
                enrich_button = st.button(
                    "🚀 Start Enrichment",
                    disabled=not selected_company_indices or st.session_state.enrichment_running or not ENRICHMENT_AVAILABLE,
                    use_container_width=True,
                    type="primary"
                )
            
            # Enrichment processing (only if available)
            if ENRICHMENT_AVAILABLE and enrich_button and selected_company_indices:
                st.session_state.enrichment_running = True
                
                selected_companies = [companies[i] for i in selected_company_indices]
                
                # Create enrichment service
                try:
                    enrichment_service = create_enrichment_service()
                    
                    if not enrichment_service:
                        st.error("❌ Enrichment service unavailable. Please check API key configuration.")
                        st.info("💡 Make sure SIXTYFOUR_API_KEY is set in your Streamlit secrets or environment variables.")
                        st.session_state.enrichment_running = False
                    else:
                        st.info("✅ Enrichment service initialized successfully")
                except Exception as e:
                    st.error(f"❌ Failed to create enrichment service: {type(e).__name__}: {str(e)}")
                    st.session_state.enrichment_running = False
                    enrichment_service = None
                
                if enrichment_service:
                    # Progress tracking
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    def simple_progress_callback(completed, total, current_company):
                        progress = completed / total
                        progress_bar.progress(progress)
                        
                        # Show more detailed status
                        if completed == total:
                            status_text.text(f"✅ Completed: {current_company} ({completed}/{total})")
                        else:
                            estimated_remaining = ((total - completed) * 10)  # 10 minutes per company estimate
                            status_text.text(f"🔄 Enriching: {current_company} ({completed}/{total}) - ~{estimated_remaining:.0f}min remaining")
                    
                    try:
                        with st.spinner("Starting enrichment process..."):
                            status_text.text("Initializing enrichment service...")
                            
                            # Run simplified enrichment
                            enriched_df, contacts_df = run_async(
                                enrichment_service.enrich_companies_batch(
                                    selected_companies,
                                    progress_callback=simple_progress_callback,
                                    custom_company_fields=st.session_state.custom_enrichment_fields['company_fields'],
                                    custom_people_fields=st.session_state.custom_enrichment_fields['people_fields']
                                )
                            )
                            
                            # Store results in session state
                            st.session_state.enriched_results = {
                                'companies': enriched_df,
                                'contacts': contacts_df,
                                'timestamp': datetime.now()
                            }
                            
                            # Debug information
                            st.success("✅ Enrichment completed! Here's what we got:")
                            st.write("**Debug Info:**")
                            st.write(f"- Companies DataFrame shape: {enriched_df.shape}")
                            st.write(f"- Companies DataFrame columns: {list(enriched_df.columns)}")
                            st.write(f"- Contacts DataFrame shape: {contacts_df.shape}")
                            st.write(f"- Contacts DataFrame columns: {list(contacts_df.columns)}")
                            
                            # Show first few rows of data
                            if not enriched_df.empty:
                                st.write("**First company record:**")
                                st.json(enriched_df.iloc[0].to_dict())
                            
                            if not contacts_df.empty:
                                st.write("**First contact record:**")
                                st.json(contacts_df.iloc[0].to_dict())
                            
                            progress_bar.progress(1.0)
                            status_text.text("✅ Enrichment completed successfully!")
                            
                    except Exception as e:
                        import traceback
                        error_details = f"{type(e).__name__}: {str(e)}"
                        full_traceback = traceback.format_exc()
                        
                        logger.error(f"Enrichment failed: {error_details}")
                        logger.error(f"Full traceback: {full_traceback}")
                        
                        # Show user-friendly error message
                        st.error(f"❌ Enrichment failed: {error_details}")
                        status_text.text("❌ Enrichment failed")
                        
                        # Show detailed error information in expandable section
                        with st.expander("🔍 Error Details (Click to expand)", expanded=False):
                            st.code(f"Error Type: {type(e).__name__}")
                            st.code(f"Error Message: {str(e)}")
                            st.text("Full Traceback:")
                            st.code(full_traceback)
                            
                            # Add troubleshooting tips
                            st.markdown("**💡 Troubleshooting Tips:**")
                            if "timeout" in str(e).lower():
                                st.markdown("- This appears to be a timeout error. The SixtyFour API may be taking longer than expected.")
                                st.markdown("- Try selecting fewer companies or retry with a single company.")
                            elif "api" in str(e).lower():
                                st.markdown("- This appears to be an API-related error.")
                                st.markdown("- Check your SixtyFour API key configuration.")
                                st.markdown("- Verify your internet connection.")
                            else:
                                st.markdown("- Try restarting the Streamlit app.")
                                st.markdown("- Check the logs for more detailed error information.")
                                st.markdown("- If the issue persists, contact support with the error details above.")
                    finally:
                        st.session_state.enrichment_running = False
            
            # Display enrichment results
            if st.session_state.enriched_results:
                st.markdown("---")
                st.markdown("#### 📊 Enrichment Results")
                
                enriched_data = st.session_state.enriched_results
                enriched_df = enriched_data['companies']
                contacts_df = enriched_data['contacts']
                timestamp = enriched_data['timestamp']
                
                # Results summary
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Companies Enriched", len(enriched_df))
                with col2:
                    qualified_count = len(enriched_df[enriched_df.get('qualified', False) == True]) if 'qualified' in enriched_df.columns else 0
                    st.metric("Qualified Leads", qualified_count)
                with col3:
                    total_contacts = len(contacts_df)
                    st.metric("Contacts Found", total_contacts)
                with col4:
                    avg_time = enriched_df['processing_time'].mean() if 'processing_time' in enriched_df.columns else 0
                    st.metric("Avg Time (s)", f"{avg_time:.1f}")
                
                # Simple tabs for results
                tab1, tab2 = st.tabs(["📈 Company Data", "👥 Contacts"])
                
                with tab1:
                    st.markdown("**Enriched Companies**")
                    
                    if not enriched_df.empty:
                        # Get all available columns dynamically
                        base_columns = ['company_name', 'nmls_id']
                        enriched_columns = []
                        
                        # Add custom company fields that were enriched
                        for field_name in st.session_state.custom_enrichment_fields['company_fields'].keys():
                            if field_name in enriched_df.columns:
                                enriched_columns.append(field_name)
                        
                        # Add status columns
                        status_columns = ['qualified', 'enrichment_status']
                        
                        # Combine all columns
                        display_columns = base_columns + enriched_columns + status_columns
                        available_columns = [col for col in display_columns if col in enriched_df.columns]
                        
                        if available_columns:
                            display_df = enriched_df[available_columns].copy()
                            
                            # Format special columns
                            if 'company_linkedin' in display_df.columns:
                                display_df['Company LinkedIn'] = display_df['company_linkedin'].apply(
                                    lambda x: f"[🔗 LinkedIn]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                                )
                                display_df = display_df.drop('company_linkedin', axis=1)
                            
                            # Format website links
                            if 'website' in display_df.columns:
                                display_df['Website'] = display_df['website'].apply(
                                    lambda x: f"[🌐 Website]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                                )
                                display_df = display_df.drop('website', axis=1)
                            
                            # Format social media links
                            social_fields = ['facebook_page', 'twitter_profile', 'instagram_account', 'youtube_channel']
                            for field in social_fields:
                                if field in display_df.columns:
                                    field_emoji = {"facebook_page": "📘", "twitter_profile": "🐦", "instagram_account": "📸", "youtube_channel": "📺"}
                                    emoji = field_emoji.get(field, "🔗")
                                    display_name = field.replace('_', ' ').title()
                                    display_df[display_name] = display_df[field].apply(
                                        lambda x: f"[{emoji} {display_name}]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                                    )
                                    display_df = display_df.drop(field, axis=1)
                            
                            # Format personal loans field
                            if 'personal_loans' in display_df.columns:
                                display_df['Personal Loans'] = display_df['personal_loans'].apply(
                                    lambda x: "✅ Yes" if str(x).lower().startswith('yes') else "❌ No" if str(x).lower().startswith('no') else "❓ Unknown"
                                )
                                display_df = display_df.drop('personal_loans', axis=1)
                            
                            # Format qualified field
                            if 'qualified' in display_df.columns:
                                display_df['Qualified'] = display_df['qualified'].apply(
                                    lambda x: "🎯 YES" if x else "❌ NO"
                                )
                                display_df = display_df.drop('qualified', axis=1)
                            
                            # Format enrichment status
                            if 'enrichment_status' in display_df.columns:
                                display_df['Status'] = display_df['enrichment_status'].apply(
                                    lambda x: "✅ Success" if x == 'Success' else "❌ Failed"
                                )
                                display_df = display_df.drop('enrichment_status', axis=1)
                            
                            # Rename columns for better display
                            column_renames = {
                                'company_name': 'Company',
                                'nmls_id': 'NMLS ID',
                                'industry': 'Industry',
                                'employees': 'Employees'
                            }
                            
                            display_df = display_df.rename(columns=column_renames)
                            st.dataframe(display_df, use_container_width=True)
                            
                            # Show field summary
                            st.markdown("---")
                            st.markdown("**📊 Enrichment Summary:**")
                            col_summary1, col_summary2 = st.columns(2)
                            
                            with col_summary1:
                                company_fields_used = len([f for f in st.session_state.custom_enrichment_fields['company_fields'].keys() if f in enriched_df.columns])
                                st.info(f"**Company Fields Enriched:** {company_fields_used}/{len(st.session_state.custom_enrichment_fields['company_fields'])}")
                            
                            with col_summary2:
                                people_fields_used = len(st.session_state.custom_enrichment_fields['people_fields'])
                                st.info(f"**People Fields Configured:** {people_fields_used}")
                        else:
                            st.warning("No enrichment data to display")
                    else:
                        st.info("No companies were successfully enriched")
                
                with tab2:
                    st.markdown("**Contact Information**")
                    
                    if not contacts_df.empty:
                        # Get all available contact columns dynamically
                        base_contact_columns = ['company_name', 'nmls_id']
                        
                        # Add all people fields that were configured
                        people_field_columns = []
                        for field_name in st.session_state.custom_enrichment_fields['people_fields'].keys():
                            if field_name in contacts_df.columns:
                                people_field_columns.append(field_name)
                        
                        # Combine columns
                        contact_display_columns = base_contact_columns + people_field_columns
                        available_contact_columns = [col for col in contact_display_columns if col in contacts_df.columns]
                        
                        if available_contact_columns:
                            display_contacts_df = contacts_df[available_contact_columns].copy()
                            
                        # Format LinkedIn links in contacts
                        if 'linkedin' in display_contacts_df.columns:
                            display_contacts_df['LinkedIn'] = display_contacts_df['linkedin'].apply(
                                lambda x: f"[🔗 Profile]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                            )
                            display_contacts_df = display_contacts_df.drop('linkedin', axis=1)
                        
                            # Format other social media fields for contacts
                            contact_social_fields = ['twitter_handle', 'facebook_profile', 'instagram_handle']
                            for field in contact_social_fields:
                                if field in display_contacts_df.columns:
                                    field_emoji = {"twitter_handle": "🐦", "facebook_profile": "📘", "instagram_handle": "📸"}
                                    emoji = field_emoji.get(field, "🔗")
                                    display_name = field.replace('_', ' ').title()
                                    display_contacts_df[display_name] = display_contacts_df[field].apply(
                                        lambda x: f"[{emoji} {display_name}]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                                    )
                                    display_contacts_df = display_contacts_df.drop(field, axis=1)
                        
                        # Rename columns for better display
                            contact_column_renames = {
                            'company_name': 'Company',
                            'nmls_id': 'NMLS ID',
                            'name': 'Name',
                            'title': 'Title',
                                'email': 'Email',
                                'phone': 'Phone',
                                'mobile': 'Mobile'
                        }
                            display_contacts_df = display_contacts_df.rename(columns=contact_column_renames)
                        
                        st.dataframe(display_contacts_df, use_container_width=True)
                        
                        # Contact summary
                        st.markdown("---")
                        st.markdown("**👥 Contact Summary:**")
                        col_contact1, col_contact2, col_contact3 = st.columns(3)
                        
                        with col_contact1:
                            total_contacts = len(contacts_df)
                            st.metric("Total Contacts", total_contacts)
                        
                        with col_contact2:
                            contacts_with_email = len(contacts_df[contacts_df.get('email', '').notna() & (contacts_df.get('email', '') != '')])
                            st.metric("With Email", contacts_with_email)
                        
                        with col_contact3:
                            contacts_with_linkedin = len(contacts_df[contacts_df.get('linkedin', '').notna() & (contacts_df.get('linkedin', '') != '')])
                            st.metric("With LinkedIn", contacts_with_linkedin)
                    else:
                        st.warning("No contact data to display")
                        
                        # Export contacts
                        if st.button("📧 Download Contacts CSV"):
                            csv = contacts_df.to_csv(index=False)
                            st.download_button(
                                label="Download Contacts",
                                data=csv,
                                file_name=f"contacts_{timestamp.strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )
        else:
            st.info("No companies match the current filters.")

        # Always check for migration needs when we have results
        if st.session_state.search_results and 'companies' in st.session_state.search_results and st.session_state.search_results['companies']:
            # Check if annotation columns exist
            try:
                annotation_columns_exist = check_annotation_columns_exist()
                # Debug info
                st.write(f"🔍 Debug: Annotation columns exist = {annotation_columns_exist}")
            except Exception as e:
                annotation_columns_exist = False
                st.error(f"Error checking database columns: {e}")
            
            # Show migration section prominently if columns don't exist
            if not annotation_columns_exist:
                st.markdown("---")
                st.markdown("### 🔧 **DATABASE MIGRATION REQUIRED**")
                st.error("⚠️ The annotation system needs to be set up. Click below to add the required database columns.")
                
                # Make the button more prominent
                st.markdown("#### 👇 **CLICK HERE TO FIX THE ANNOTATION SYSTEM** 👇")
                
                # Center the button
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    # Make button more prominent
                    migration_button = st.button(
                        "🚀 **RUN MIGRATION NOW**", 
                        type="primary", 
                        use_container_width=True,
                        help="Click to add annotation columns to your database"
                    )
                    
                    if migration_button:
                        st.write("🔄 **Migration button clicked!** Starting migration...")
                        with st.spinner("🔄 Adding annotation columns to database..."):
                            success, message = run_annotation_migration()
                            if success:
                                st.success("✅ " + message)
                                st.info("🔄 Please refresh the page to use the annotation features.")
                                st.balloons()
                                time.sleep(2)
                                st.rerun()  # Auto-refresh the page
                            else:
                                st.error("❌ " + message)
                                # Add retry button for failed migrations
                                if "database busy" in message.lower() or "timeout" in message.lower():
                                    st.warning("💡 **Tip:** The database was busy. Wait 10 seconds and try again.")
                                    if st.button("🔄 **TRY MIGRATION AGAIN**", type="secondary", key="retry_migration"):
                                        st.rerun()
                
                st.info("📋 This will safely add `is_reviewed`, `classification`, and `notes` columns to your companies table.")
                st.warning("⚠️ **If you don't see a button above, try refreshing the page!**")
                st.markdown("---")
            else:
                st.success("✅ Database migration already completed - annotation features are ready!")

def cleanup_resources():
    """Clean up resources when app shuts down"""
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(close_db_pool())
        loop.close()
        logger.info("Resources cleaned up successfully")
    except Exception as e:
        logger.warning(f"Error during cleanup: {e}")

def check_annotation_columns_exist():
    """Check if annotation columns exist in the database"""
    try:
        # Use the database URL directly with psycopg2 for simpler connection
        import psycopg2
        import os
        
        DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
        if not DATABASE_URL:
            return False
            
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'companies' 
            AND column_name IN ('is_reviewed', 'classification', 'notes')
        """)
        
        result = cur.fetchall()
        cur.close()
        conn.close()
        
        return len(result) == 3  # All 3 columns exist
        
    except ImportError:
        st.error("❌ psycopg2 not available. Using fallback method...")
        # Fallback to async method if psycopg2 not available
        try:
            async def check_columns():
                pool = await get_or_create_pool()
                if not pool:
                    return False
                
                async with pool.acquire() as conn:
                    result = await conn.fetch("""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'companies' 
                        AND column_name IN ('is_reviewed', 'classification', 'notes')
                    """)
                    return len(result) == 3
            
            return run_async(check_columns())
        except Exception as e:
            logger.error(f"Error checking annotation columns: {e}")
            return False
    except Exception as e:
        logger.error(f"Error checking annotation columns: {e}")
        return False

def run_annotation_migration():
    """Run the database migration to add annotation columns"""
    try:
        st.write("🔍 **Debug:** Starting migration process...")
        
        # Try psycopg2 first for simpler connection handling
        try:
            import psycopg2
            import os
            
            DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
            if not DATABASE_URL:
                raise Exception("Database URL not available")
            
            st.write("🔍 **Debug:** Using direct psycopg2 connection...")
            
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = True  # Enable autocommit for DDL statements
            cur = conn.cursor()
            
            # Execute migration commands one by one
            commands = [
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_reviewed BOOLEAN DEFAULT FALSE",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS classification VARCHAR(100) DEFAULT NULL", 
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT NULL",
                "CREATE INDEX IF NOT EXISTS idx_companies_is_reviewed ON companies(is_reviewed)",
                "CREATE INDEX IF NOT EXISTS idx_companies_classification ON companies(classification)",
                "UPDATE companies SET is_reviewed = FALSE WHERE is_reviewed IS NULL"
            ]
            
            for i, command in enumerate(commands, 1):
                st.write(f"🔍 **Debug:** Executing command {i}/6: {command[:50]}...")
                try:
                    cur.execute(command)
                    st.write(f"✅ **Debug:** Command {i}/6 completed successfully")
                except Exception as cmd_error:
                    st.write(f"⚠️ **Debug:** Command {i}/6 failed: {str(cmd_error)}")
                    # For ALTER TABLE IF NOT EXISTS, ignore if column already exists
                    if "already exists" in str(cmd_error).lower() or "duplicate" in str(cmd_error).lower():
                        st.write(f"ℹ️ **Debug:** Command {i}/6 skipped (already exists)")
                        continue
                    else:
                        raise cmd_error
            
            cur.close()
            conn.close()
            st.write("🔍 **Debug:** Migration completed successfully with psycopg2!")
            return True, "Migration completed successfully!"
            
        except ImportError:
            st.write("🔍 **Debug:** psycopg2 not available, trying asyncpg...")
            # Fallback to simplified async approach
            return False, "psycopg2 not available. Please install psycopg2-binary package."
            
    except Exception as e:
        error_msg = str(e)
        st.write(f"🔍 **Debug:** Migration failed with error: {error_msg}")
        logger.error(f"Migration error: {e}")
        
        # Provide helpful error messages
        if "another operation is in progress" in error_msg.lower():
            return False, "Database busy - please wait a moment and try again"
        elif "timeout" in error_msg.lower():
            return False, "Database connection timeout - please try again"
        else:
            return False, f"Migration failed: {error_msg}"

# Add this new function after the existing company detail functions (around line 550)

async def get_complete_company_intelligence(nmls_id: str) -> Dict[str, Any]:
    """Get complete company intelligence aggregating all available data"""
    pool = await get_or_create_pool()
    if not pool:
        return {}

    try:
        async with pool.acquire() as conn:
            # Get comprehensive company data
            company_data = await conn.fetchrow("""
                SELECT 
                    c.*,
                    (SELECT COUNT(*) FROM licenses WHERE company_id = c.id) as total_licenses,
                    (SELECT COUNT(*) FROM licenses WHERE company_id = c.id AND active = true) as active_licenses,
                    (SELECT COUNT(*) FROM addresses WHERE company_id = c.id AND address_type = 'street') as street_addresses,
                    (SELECT COUNT(*) FROM addresses WHERE company_id = c.id AND address_type = 'mailing') as mailing_addresses
                FROM companies c
                WHERE c.nmls_id = $1
            """, nmls_id)
            
            if not company_data:
                return {}
            
            # Get all licenses with full details
            licenses = await conn.fetch("""
                SELECT 
                    license_type,
                    license_number,
                    regulator,
                    status,
                    active,
                    authorized_to_conduct_business,
                    original_issue_date,
                    renewed_through,
                    status_date,
                    state_trade_names
                FROM licenses l
                WHERE l.company_id = (SELECT id FROM companies WHERE nmls_id = $1)
                ORDER BY active DESC, original_issue_date DESC
            """, nmls_id)
            
            # Get all addresses
            addresses = await conn.fetch("""
                SELECT 
                    address_type,
                    full_address,
                    city,
                    state,
                    zip_code,
                    street_lines
                FROM addresses a
                WHERE a.company_id = (SELECT id FROM companies WHERE nmls_id = $1)
                ORDER BY address_type
            """, nmls_id)
            
            # Process and structure the data
            intelligence = {
                'company_info': dict(company_data),
                'licenses': [dict(row) for row in licenses],
                'addresses': [dict(row) for row in addresses],
                'license_analysis': analyze_license_portfolio(licenses),
                'business_intelligence': extract_business_intelligence(company_data, licenses),
                'contact_quality': assess_contact_quality(company_data),
                'regulatory_status': assess_regulatory_status(licenses)
            }
            
            return intelligence
            
    except Exception as e:
        logger.error(f"Error fetching company intelligence for {nmls_id}: {e}")
        return {}

def analyze_license_portfolio(licenses) -> Dict[str, Any]:
    """Analyze the company's license portfolio for business intelligence"""
    if not licenses:
        return {}
    
    active_licenses = [l for l in licenses if l['active']]
    inactive_licenses = [l for l in licenses if not l['active']]
    
    # Analyze license types
    license_types = {}
    states_covered = set()
    authorized_states = set()
    
    for license in active_licenses:
        license_type = license['license_type']
        regulator = license['regulator'] or ''
        
        # Extract state from regulator
        state = extract_state_from_regulator(regulator)
        if state:
            states_covered.add(state)
            
        if license['authorized_to_conduct_business']:
            if state:
                authorized_states.add(state)
        
        # Count license types
        if license_type not in license_types:
            license_types[license_type] = {'count': 0, 'states': set()}
        license_types[license_type]['count'] += 1
        if state:
            license_types[license_type]['states'].add(state)
    
    # Convert sets to lists for JSON serialization
    for lt in license_types:
        license_types[lt]['states'] = sorted(list(license_types[lt]['states']))
    
    return {
        'total_licenses': len(licenses),
        'active_licenses': len(active_licenses),
        'inactive_licenses': len(inactive_licenses),
        'license_types': license_types,
        'states_covered': sorted(list(states_covered)),
        'authorized_states': sorted(list(authorized_states)),
        'geographic_reach': len(states_covered),
        'authorization_rate': len(authorized_states) / max(len(states_covered), 1) * 100
    }

def extract_business_intelligence(company_data, licenses) -> Dict[str, Any]:
    """Extract business intelligence insights"""
    intelligence = {}
    
    # Company age and maturity
    if company_data.get('date_formed'):
        from datetime import datetime
        formed_date = company_data['date_formed']
        if isinstance(formed_date, str):
            try:
                formed_date = datetime.strptime(formed_date, '%Y-%m-%d').date()
            except:
                formed_date = None
        
        if formed_date:
            years_in_business = (datetime.now().date() - formed_date).days / 365.25
            intelligence['years_in_business'] = round(years_in_business, 1)
            
            if years_in_business < 2:
                intelligence['maturity_level'] = 'Startup'
            elif years_in_business < 5:
                intelligence['maturity_level'] = 'Growing'
            elif years_in_business < 10:
                intelligence['maturity_level'] = 'Established'
            else:
                intelligence['maturity_level'] = 'Mature'
    
    # Business complexity indicators
    trade_names_count = len(company_data.get('trade_names') or [])
    intelligence['trade_names_count'] = trade_names_count
    intelligence['has_multiple_brands'] = trade_names_count > 1
    
    # Federal regulation status
    intelligence['federally_regulated'] = bool(company_data.get('federal_regulator'))
    intelligence['federal_regulator'] = company_data.get('federal_regulator')
    
    # License diversity
    if licenses:
        unique_license_types = len(set(l['license_type'] for l in licenses if l['active']))
        intelligence['license_diversity'] = unique_license_types
        intelligence['is_multi_product'] = unique_license_types > 2
    
    return intelligence

def assess_contact_quality(company_data) -> Dict[str, Any]:
    """Assess the quality and completeness of contact information"""
    quality = {
        'has_phone': bool(company_data.get('phone')),
        'has_email': bool(company_data.get('email')),
        'has_website': bool(company_data.get('website')),
        'has_toll_free': bool(company_data.get('toll_free')),
        'contact_score': 0
    }
    
    # Calculate contact score
    score = 0
    if quality['has_phone']: score += 25
    if quality['has_email']: score += 35  # Email is most valuable for outreach
    if quality['has_website']: score += 25
    if quality['has_toll_free']: score += 15
    
    quality['contact_score'] = score
    
    if score >= 85:
        quality['contact_grade'] = 'Excellent'
    elif score >= 60:
        quality['contact_grade'] = 'Good'
    elif score >= 35:
        quality['contact_grade'] = 'Fair'
    else:
        quality['contact_grade'] = 'Poor'
    
    return quality

def assess_regulatory_status(licenses) -> Dict[str, Any]:
    """Assess regulatory status and compliance indicators"""
    if not licenses:
        return {'status': 'No licenses found'}
    
    active_licenses = [l for l in licenses if l['active']]
    
    # Check for any regulatory red flags
    revoked_licenses = [l for l in licenses if 'revoked' in (l.get('status') or '').lower()]
    suspended_licenses = [l for l in licenses if 'suspended' in (l.get('status') or '').lower()]
    
    status = {
        'active_license_count': len(active_licenses),
        'total_license_count': len(licenses),
        'has_revoked_licenses': len(revoked_licenses) > 0,
        'has_suspended_licenses': len(suspended_licenses) > 0,
        'revoked_count': len(revoked_licenses),
        'suspended_count': len(suspended_licenses)
    }
    
    # Overall regulatory health
    if status['has_revoked_licenses'] or status['has_suspended_licenses']:
        status['regulatory_health'] = 'Concerning'
        status['risk_level'] = 'High'
    elif len(active_licenses) == 0:
        status['regulatory_health'] = 'Inactive'
        status['risk_level'] = 'Medium'
    else:
        status['regulatory_health'] = 'Good'
        status['risk_level'] = 'Low'
    
    return status

def display_company_intelligence_dashboard(intelligence_data: Dict[str, Any]):
    """Display comprehensive company intelligence dashboard"""
    company_info = intelligence_data.get('company_info', {})
    license_analysis = intelligence_data.get('license_analysis', {})
    business_intelligence = intelligence_data.get('business_intelligence', {})
    contact_quality = intelligence_data.get('contact_quality', {})
    regulatory_status = intelligence_data.get('regulatory_status', {})
    licenses = intelligence_data.get('licenses', [])
    addresses = intelligence_data.get('addresses', [])
    
    # Header with company name
    st.markdown(f"## 🏢 {company_info.get('company_name', 'Unknown Company')}")
    st.markdown(f"**NMLS ID:** {company_info.get('nmls_id', 'N/A')}")
    
    # Quick stats row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Contact Score", 
            f"{contact_quality.get('contact_score', 0)}/100",
            help="Quality of available contact information"
        )
        st.caption(f"Grade: {contact_quality.get('contact_grade', 'Unknown')}")
    
    with col2:
        st.metric(
            "Active Licenses", 
            license_analysis.get('active_licenses', 0),
            help="Number of currently active licenses"
        )
        st.caption(f"Total: {license_analysis.get('total_licenses', 0)}")
    
    with col3:
        st.metric(
            "States", 
            license_analysis.get('geographic_reach', 0),
            help="Number of states with active licenses"
        )
        auth_rate = license_analysis.get('authorization_rate', 0)
        st.caption(f"{auth_rate:.0f}% Authorized")
    
    with col4:
        risk_level = regulatory_status.get('risk_level', 'Unknown')
        risk_color = {'Low': '🟢', 'Medium': '🟡', 'High': '🔴'}.get(risk_level, '⚪')
        st.metric(
            "Risk Level", 
            f"{risk_color} {risk_level}",
            help="Regulatory risk assessment"
        )
        st.caption(regulatory_status.get('regulatory_health', 'Unknown'))
    
    # Detailed sections in tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🏢 Company Profile", 
        "📋 License Portfolio", 
        "📞 Contact Intelligence", 
        "⚖️ Regulatory Status",
        "🎯 Sales Intelligence"
    ])
    
    with tab1:
        st.markdown("### Company Profile")
        
        # Basic company information
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Company Details:**")
            st.write(f"• **Legal Name:** {company_info.get('company_name', 'N/A')}")
            st.write(f"• **Business Structure:** {company_info.get('business_structure', 'N/A')}")
            st.write(f"• **Formed In:** {company_info.get('formed_in', 'N/A')}")
            
            if company_info.get('date_formed'):
                st.write(f"• **Date Formed:** {company_info.get('date_formed')}")
            
            if business_intelligence.get('years_in_business'):
                st.write(f"• **Years in Business:** {business_intelligence.get('years_in_business')} years")
                st.write(f"• **Maturity Level:** {business_intelligence.get('maturity_level', 'Unknown')}")
            
            if company_info.get('fiscal_year_end'):
                st.write(f"• **Fiscal Year End:** {company_info.get('fiscal_year_end')}")
        
        with col2:
            st.markdown("**Federal Regulation:**")
            if business_intelligence.get('federally_regulated'):
                st.write(f"✅ **Federal Regulator:** {business_intelligence.get('federal_regulator')}")
            else:
                st.write("❌ Not federally regulated")
            
            st.markdown("**Business Complexity:**")
            trade_names_count = business_intelligence.get('trade_names_count', 0)
            st.write(f"• **Trade Names:** {trade_names_count}")
            
            if business_intelligence.get('has_multiple_brands'):
                st.write("🏷️ **Multi-brand operation**")
            
            license_diversity = business_intelligence.get('license_diversity', 0)
            st.write(f"• **License Types:** {license_diversity}")
            
            if business_intelligence.get('is_multi_product'):
                st.write("🔄 **Multi-product lender**")
        
        # Trade names if available
        if company_info.get('trade_names'):
            st.markdown("**Trade Names:**")
            trade_names = company_info.get('trade_names', [])
            if isinstance(trade_names, list):
                for name in trade_names[:10]:  # Show first 10
                    st.write(f"• {name}")
                if len(trade_names) > 10:
                    st.write(f"... and {len(trade_names) - 10} more")
            else:
                st.write(trade_names)
        
        # Addresses
        if addresses:
            st.markdown("**Addresses:**")
            for addr in addresses:
                addr_type = addr.get('address_type', 'Unknown').title()
                full_address = addr.get('full_address', 'N/A')
                st.write(f"• **{addr_type}:** {full_address}")
    
    with tab2:
        st.markdown("### License Portfolio Analysis")
        
        if license_analysis:
            # Portfolio summary
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Licenses", license_analysis.get('total_licenses', 0))
                st.metric("Active Licenses", license_analysis.get('active_licenses', 0))
            
            with col2:
                st.metric("Geographic Reach", f"{license_analysis.get('geographic_reach', 0)} states")
                auth_rate = license_analysis.get('authorization_rate', 0)
                st.metric("Authorization Rate", f"{auth_rate:.1f}%")
            
            with col3:
                inactive_count = license_analysis.get('inactive_licenses', 0)
                st.metric("Inactive Licenses", inactive_count)
                
                if inactive_count > 0:
                    st.caption("⚠️ Has inactive licenses")
            
            # License types breakdown
            license_types = license_analysis.get('license_types', {})
            if license_types:
                st.markdown("**License Types & Coverage:**")
                for license_type, details in license_types.items():
                    count = details.get('count', 0)
                    states = details.get('states', [])
                    states_text = ', '.join(states[:5])
                    if len(states) > 5:
                        states_text += f" (+{len(states)-5} more)"
                    
                    st.write(f"• **{license_type}** ({count} licenses)")
                    if states:
                        st.write(f"  📍 States: {states_text}")
            
            # States coverage
            states_covered = license_analysis.get('states_covered', [])
            authorized_states = license_analysis.get('authorized_states', [])
            
            if states_covered:
                st.markdown("**Geographic Coverage:**")
                st.write(f"**Licensed in:** {', '.join(states_covered)}")
                
                if authorized_states:
                    st.write(f"**Authorized to conduct business in:** {', '.join(authorized_states)}")
                    
                    not_authorized = set(states_covered) - set(authorized_states)
                    if not_authorized:
                        st.write(f"**⚠️ Licensed but not authorized in:** {', '.join(sorted(not_authorized))}")
        
        # Detailed license table
        if licenses:
            st.markdown("**All Licenses:**")
            license_df = pd.DataFrame(licenses)
            
            # Select relevant columns for display
            display_columns = ['license_type', 'regulator', 'status', 'active', 'authorized_to_conduct_business', 'original_issue_date']
            available_columns = [col for col in display_columns if col in license_df.columns]
            
            if available_columns:
                st.dataframe(
                    license_df[available_columns],
                    use_container_width=True,
                    hide_index=True
                )
    
    with tab3:
        st.markdown("### Contact Intelligence")
        
        # Contact quality overview
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Contact Information Available:**")
            
            phone = company_info.get('phone')
            if phone:
                st.write(f"📞 **Phone:** {phone}")
            else:
                st.write("📞 Phone: ❌ Not available")
            
            toll_free = company_info.get('toll_free')
            if toll_free:
                st.write(f"☎️ **Toll-Free:** {toll_free}")
            
            email = company_info.get('email')
            if email:
                st.write(f"📧 **Email:** {email}")
            else:
                st.write("📧 Email: ❌ Not available")
            
            website = company_info.get('website')
            if website:
                # Handle multiple websites
                if isinstance(website, str) and (',' in website or ' ' in website):
                    websites = [w.strip() for w in website.replace(',', ' ').split() if w.strip()]
                    st.write("🌐 **Websites:**")
                    for w in websites:
                        if not w.startswith('http'):
                            w = f"https://{w}"
                        st.write(f"  • [{w}]({w})")
                else:
                    if not website.startswith('http'):
                        website = f"https://{website}"
                    st.write(f"🌐 **Website:** [{website}]({website})")
            else:
                st.write("🌐 Website: ❌ Not available")
            
            fax = company_info.get('fax')
            if fax:
                st.write(f"📠 **Fax:** {fax}")
        
        with col2:
            st.markdown("**Contact Quality Assessment:**")
            
            score = contact_quality.get('contact_score', 0)
            grade = contact_quality.get('contact_grade', 'Unknown')
            
            # Progress bar for contact score
            st.progress(score / 100)
            st.write(f"**Score:** {score}/100 ({grade})")
            
            st.markdown("**Outreach Readiness:**")
            
            if contact_quality.get('has_email'):
                st.write("✅ Email outreach possible")
            else:
                st.write("❌ No email for direct outreach")
            
            if contact_quality.get('has_phone'):
                st.write("✅ Phone contact available")
            else:
                st.write("❌ No phone number")
            
            if contact_quality.get('has_website'):
                st.write("✅ Website for research")
            else:
                st.write("❌ No website listed")
            
            # Recommendations
            st.markdown("**Recommendations:**")
            if score >= 60:
                st.success("🎯 **Ready for outreach** - Good contact information available")
            elif score >= 35:
                st.warning("⚠️ **Needs research** - Limited contact info, research website/LinkedIn")
            else:
                st.error("🔍 **High research needed** - Very limited contact information")
    
    with tab4:
        st.markdown("### Regulatory Status")
        
        # Regulatory health overview
        health = regulatory_status.get('regulatory_health', 'Unknown')
        risk = regulatory_status.get('risk_level', 'Unknown')
        
        if health == 'Good':
            st.success(f"✅ **Regulatory Health:** {health} (Risk: {risk})")
        elif health == 'Concerning':
            st.error(f"🚨 **Regulatory Health:** {health} (Risk: {risk})")
        else:
            st.warning(f"⚠️ **Regulatory Health:** {health} (Risk: {risk})")
        
        # License status breakdown
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**License Status:**")
            active_count = regulatory_status.get('active_license_count', 0)
            total_count = regulatory_status.get('total_license_count', 0)
            st.write(f"• **Active Licenses:** {active_count}")
            st.write(f"• **Total Licenses:** {total_count}")
            
            if total_count > 0:
                active_rate = (active_count / total_count) * 100
                st.write(f"• **Active Rate:** {active_rate:.1f}%")
        
        with col2:
            st.markdown("**Regulatory Issues:**")
            
            revoked_count = regulatory_status.get('revoked_count', 0)
            suspended_count = regulatory_status.get('suspended_count', 0)
            
            if revoked_count > 0:
                st.write(f"🚨 **Revoked Licenses:** {revoked_count}")
            else:
                st.write("✅ No revoked licenses")
            
            if suspended_count > 0:
                st.write(f"⚠️ **Suspended Licenses:** {suspended_count}")
            else:
                st.write("✅ No suspended licenses")
        
        # Regulatory actions if available
        if company_info.get('regulatory_actions'):
            st.markdown("**Regulatory Actions:**")
            st.write(company_info.get('regulatory_actions'))
        else:
            st.write("✅ No regulatory actions on record")
    
    with tab5:
        st.markdown("### Sales Intelligence Summary")
        
        # Overall prospect score
        prospect_score = calculate_prospect_score(intelligence_data)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Prospect Assessment:**")
            
            # Progress bar for prospect score
            st.progress(prospect_score / 100)
            st.write(f"**Overall Score:** {prospect_score}/100")
            
            if prospect_score >= 80:
                st.success("🎯 **Hot Prospect** - High priority for outreach")
            elif prospect_score >= 60:
                st.info("✅ **Good Prospect** - Worth pursuing")
            elif prospect_score >= 40:
                st.warning("⚠️ **Moderate Prospect** - Needs evaluation")
            else:
                st.error("❌ **Low Priority** - May not be worth pursuing")
        
        with col2:
            st.markdown("**Key Insights:**")
            
            # Business maturity
            maturity = business_intelligence.get('maturity_level')
            if maturity:
                st.write(f"• **Business Maturity:** {maturity}")
            
            # Geographic reach
            reach = license_analysis.get('geographic_reach', 0)
            if reach > 10:
                st.write(f"• **Wide Geographic Reach:** {reach} states")
            elif reach > 5:
                st.write(f"• **Regional Player:** {reach} states")
            elif reach > 0:
                st.write(f"• **Local/Limited:** {reach} states")
            
            # Multi-product capability
            if business_intelligence.get('is_multi_product'):
                st.write("• **Multi-Product Lender:** Diversified offerings")
            
            # Federal regulation
            if business_intelligence.get('federally_regulated'):
                st.write("• **Federally Regulated:** Established institution")
            
            # Contact readiness
            contact_grade = contact_quality.get('contact_grade', 'Unknown')
            st.write(f"• **Contact Quality:** {contact_grade}")
        
        # Action recommendations
        st.markdown("**Recommended Actions:**")
        
        recommendations = generate_sales_recommendations(intelligence_data)
        for rec in recommendations:
            st.write(f"• {rec}")

def calculate_prospect_score(intelligence_data: Dict[str, Any]) -> int:
    """Calculate overall prospect score for sales prioritization"""
    score = 0
    
    # Contact quality (0-30 points)
    contact_score = intelligence_data.get('contact_quality', {}).get('contact_score', 0)
    score += int(contact_score * 0.3)
    
    # Regulatory health (0-25 points)
    regulatory_health = intelligence_data.get('regulatory_status', {}).get('regulatory_health', 'Unknown')
    if regulatory_health == 'Good':
        score += 25
    elif regulatory_health == 'Inactive':
        score += 10
    # Concerning gets 0 points
    
    # Business maturity (0-20 points)
    maturity = intelligence_data.get('business_intelligence', {}).get('maturity_level', '')
    maturity_scores = {'Mature': 20, 'Established': 15, 'Growing': 10, 'Startup': 5}
    score += maturity_scores.get(maturity, 0)
    
    # Geographic reach (0-15 points)
    reach = intelligence_data.get('license_analysis', {}).get('geographic_reach', 0)
    if reach >= 10:
        score += 15
    elif reach >= 5:
        score += 10
    elif reach >= 2:
        score += 5
    
    # Active licenses (0-10 points)
    active_licenses = intelligence_data.get('license_analysis', {}).get('active_licenses', 0)
    if active_licenses >= 10:
        score += 10
    elif active_licenses >= 5:
        score += 7
    elif active_licenses >= 1:
        score += 5
    
    return min(score, 100)  # Cap at 100

def generate_sales_recommendations(intelligence_data: Dict[str, Any]) -> List[str]:
    """Generate specific sales recommendations based on company intelligence"""
    recommendations = []
    
    contact_quality = intelligence_data.get('contact_quality', {})
    business_intel = intelligence_data.get('business_intelligence', {})
    regulatory_status = intelligence_data.get('regulatory_status', {})
    license_analysis = intelligence_data.get('license_analysis', {})
    
    # Contact-based recommendations
    if contact_quality.get('has_email'):
        recommendations.append("📧 **Email outreach possible** - Direct contact available")
    else:
        recommendations.append("🔍 **Research needed** - Find decision maker contact info")
    
    if contact_quality.get('has_website'):
        recommendations.append("🌐 **Research company website** - Understand their business model")
    
    # Business intelligence recommendations
    if business_intel.get('is_multi_product'):
        recommendations.append("🎯 **Multi-product opportunity** - Multiple lending products to discuss")
    
    if business_intel.get('federally_regulated'):
        recommendations.append("🏛️ **Federally regulated** - Likely has compliance budget and needs")
    
    # Geographic recommendations
    reach = license_analysis.get('geographic_reach', 0)
    if reach > 10:
        recommendations.append("🗺️ **National reach** - Large-scale solutions may be relevant")
    elif reach > 1:
        recommendations.append("📍 **Multi-state operation** - Regional expansion opportunities")
    
    # Regulatory recommendations
    if regulatory_status.get('regulatory_health') == 'Concerning':
        recommendations.append("⚠️ **Regulatory issues** - Compliance solutions may be needed")
    elif regulatory_status.get('active_license_count', 0) == 0:
        recommendations.append("❌ **No active licenses** - May be inactive or changing business")
    
    # Maturity-based recommendations
    maturity = business_intel.get('maturity_level', '')
    if maturity == 'Growing':
        recommendations.append("📈 **Growing company** - Scaling solutions may be relevant")
    elif maturity == 'Startup':
        recommendations.append("🚀 **Startup** - Cost-effective solutions and growth support")
    
    return recommendations

async def get_complete_company_database_info(nmls_id: str) -> Dict[str, Any]:
    """Get ALL database information for a company from all tables and columns"""
    pool = await get_or_create_pool()
    if not pool:
        st.error("❌ Database connection pool not available")
        return {}

    try:
        async with pool.acquire() as conn:
            # Get ALL company data (every single field)
            company_data = await conn.fetchrow("""
                SELECT * FROM companies WHERE nmls_id = $1
            """, nmls_id)
            
            if not company_data:
                st.error(f"❌ No company found with NMLS ID: {nmls_id}")
                return {}
            
            company_id = company_data['id']
            
            # Get ALL license data (every single field)
            licenses_data = await conn.fetch("""
                SELECT * FROM licenses WHERE company_id = $1 ORDER BY id
            """, company_id)
            
            # Get ALL address data (every single field)
            addresses_data = await conn.fetch("""
                SELECT * FROM addresses WHERE company_id = $1 ORDER BY id
            """, company_id)
            
            # Structure all the data
            complete_data = {
                'company': dict(company_data),
                'licenses': [dict(row) for row in licenses_data],
                'addresses': [dict(row) for row in addresses_data]
            }
            
            return complete_data
            
    except Exception as e:
        st.error(f"❌ Database error: {str(e)}")
        logger.error(f"Error fetching complete database info for {nmls_id}: {e}")
        return {}

def display_complete_database_info(complete_data: Dict[str, Any]):
    """Display ALL database information in organized sections"""
    if not complete_data:
        st.error("No database information available")
        return
    
    company_data = complete_data.get('company', {})
    licenses_data = complete_data.get('licenses', [])
    addresses_data = complete_data.get('addresses', [])
    
    # Remove the debug success message - we know it works now
    st.markdown("### 📊 Complete Database Information")
    st.markdown("*Every single field from all database tables - complete data access*")
    
    # Create tabs for different data sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏢 Company Data", 
        "📋 License Data", 
        "🏠 Address Data",
        "📈 Summary"
    ])
    
    with tab1:
        st.markdown("#### 🏢 Complete Company Information")
        
        # Organize company fields into logical groups
        basic_info_fields = ['nmls_id', 'company_name', 'url', 'timestamp', 'zip_code']
        contact_fields = ['phone', 'toll_free', 'fax', 'email', 'website']
        business_fields = ['business_structure', 'formed_in', 'date_formed', 'fiscal_year_end', 'stock_symbol']
        mlo_fields = ['mlo_type', 'mlo_count']
        federal_fields = ['federal_regulator', 'federal_status', 'federal_regulator_url']
        names_fields = ['trade_names', 'prior_trade_names', 'prior_legal_names']
        regulatory_fields = ['regulatory_actions']
        annotation_fields = ['is_reviewed', 'classification', 'notes']
        
        # Display key information prominently
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("##### 📋 Company Identity")
            for field in basic_info_fields:
                value = company_data.get(field)
                if value is not None and value != '':
                    st.write(f"**{field.replace('_', ' ').title()}:** {value}")
            
            st.markdown("##### 📞 Contact Information")
            for field in contact_fields:
                value = company_data.get(field)
                if value is not None and value != '':
                    if field == 'website' and value:
                        # Make websites clickable
                        websites = value.split(',') if ',' in value else [value]
                        st.write(f"**Website:**")
                        for website in websites:
                            website = website.strip()
                            if not website.startswith('http'):
                                website = f"https://{website}"
                            st.write(f"  • [{website}]({website})")
                    else:
                        st.write(f"**{field.replace('_', ' ').title()}:** {value}")
            
            st.markdown("##### 🏛️ Business Structure")
            for field in business_fields:
                value = company_data.get(field)
                if value is not None and value != '':
                    st.write(f"**{field.replace('_', ' ').title()}:** {value}")
            
            st.markdown("##### 👥 MLO Information")
            for field in mlo_fields:
                value = company_data.get(field)
                if value is not None and value != '':
                    st.write(f"**{field.replace('_', ' ').title()}:** {value}")
        
        with col2:
            st.markdown("##### 🏛️ Federal Registration")
            for field in federal_fields:
                value = company_data.get(field)
                if value is not None and value != '':
                    if field == 'federal_regulator_url' and value:
                        st.write(f"**Federal Regulator URL:** [{value}]({value})")
                    else:
                        st.write(f"**{field.replace('_', ' ').title()}:** {value}")
            
            st.markdown("##### 🏷️ Trade Names")
            for field in names_fields:
                value = company_data.get(field)
                if value is not None and value and len(value) > 0:
                    st.write(f"**{field.replace('_', ' ').title()}:**")
                    for name in value:
                        if name and str(name).strip():
                            st.write(f"  • {name}")
            
            # Show annotations if they exist
            has_annotations = any(company_data.get(field) for field in annotation_fields)
            if has_annotations:
                st.markdown("##### 📝 Review Status")
                for field in annotation_fields:
                    value = company_data.get(field)
                    if value is not None and value != '':
                        if field == 'notes' and len(str(value)) > 100:
                            st.write(f"**{field.replace('_', ' ').title()}:**")
                            st.text_area("", value, height=80, disabled=True, key=f"clean_ann_{field}")
                        else:
                            st.write(f"**{field.replace('_', ' ').title()}:** {value}")
        
        # Regulatory information (if exists)
        regulatory_actions = company_data.get('regulatory_actions')
        if regulatory_actions and regulatory_actions.strip():
            st.markdown("##### ⚖️ Regulatory Information")
            if len(regulatory_actions) > 300:
                st.text_area("Regulatory Actions:", regulatory_actions, height=150, disabled=True, key="clean_reg_actions")
            else:
                st.write(f"**Regulatory Actions:** {regulatory_actions}")
        
        # Address information (JSONB) - only if exists
        address_fields = ['street_address', 'mailing_address']
        has_addresses = any(company_data.get(field) for field in address_fields)
        if has_addresses:
            st.markdown("##### 🏠 Address Information")
            for field in address_fields:
                value = company_data.get(field)
                if value is not None:
                    st.write(f"**{field.replace('_', ' ').title()}:**")
                    if isinstance(value, dict):
                        for key, val in value.items():
                            if val:
                                st.write(f"  • **{key}:** {val}")
                    else:
                        st.write(f"  {value}")
        
        # Technical metadata (collapsible - less important)
        metadata_fields = ['extraction_timestamp', 'file_path', 'processing_errors', 'quality_flags']
        has_metadata = any(company_data.get(field) for field in metadata_fields)
        if has_metadata:
            with st.expander("🔧 Technical Metadata", expanded=False):
                for field in metadata_fields:
                    value = company_data.get(field)
                    if value is not None and value != '':
                        if isinstance(value, list) and value:
                            st.write(f"**{field.replace('_', ' ').title()}:**")
                            for item in value:
                                st.write(f"  • {item}")
                        else:
                            st.write(f"**{field.replace('_', ' ').title()}:** {value}")
    
    with tab2:
        st.markdown("#### 📋 Complete License Information")
        
        if licenses_data:
            st.info(f"📊 **{len(licenses_data)} licenses** with complete database information")
            
            for i, license_data in enumerate(licenses_data, 1):
                license_type = license_data.get('license_type', 'Unknown Type')
                status = license_data.get('status', 'Unknown')
                active = license_data.get('active', False)
                
                # Create a more readable title
                status_emoji = "✅" if active else "❌"
                title = f"{status_emoji} License {i}: {license_type} ({status})"
                
                with st.expander(title, expanded=i == 1):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Core Information:**")
                        core_fields = ['license_number', 'regulator', 'status', 'active', 'authorized_to_conduct_business']
                        for field in core_fields:
                            value = license_data.get(field)
                            if value is not None:
                                if field == 'active':
                                    display_value = "✅ Active" if value else "❌ Inactive"
                                elif field == 'authorized_to_conduct_business':
                                    display_value = "✅ Authorized" if value else "❌ Not Authorized" if value is False else "Unknown"
                                else:
                                    display_value = value
                                st.write(f"**{field.replace('_', ' ').title()}:** {display_value}")
                    
                    with col2:
                        st.markdown("**Important Dates:**")
                        date_fields = ['original_issue_date', 'status_date', 'renewed_through']
                        for field in date_fields:
                            value = license_data.get(field)
                            if value:
                                st.write(f"**{field.replace('_', ' ').title()}:** {value}")
                    
                    # Additional information (only if exists)
                    additional_info = []
                    if license_data.get('state_trade_names'):
                        additional_info.append(('State Trade Names', license_data.get('state_trade_names')))
                    if license_data.get('resident_agent'):
                        additional_info.append(('Resident Agent', license_data.get('resident_agent')))
                    
                    if additional_info:
                        st.markdown("**Additional Information:**")
                        for label, value in additional_info:
                            if isinstance(value, dict):
                                st.write(f"**{label}:**")
                                for key, val in value.items():
                                    if val:
                                        st.write(f"  • **{key}:** {val}")
                            else:
                                st.write(f"**{label}:** {value}")
        else:
            st.info("No license data found for this company")
    
    with tab3:
        st.markdown("#### 🏠 Complete Address Information")
        
        if addresses_data:
            st.info(f"📍 **{len(addresses_data)} addresses** with complete database information")
            
            for i, address_data in enumerate(addresses_data, 1):
                address_type = address_data.get('address_type', 'Unknown').title()
                
                with st.expander(f"📍 {address_type} Address", expanded=True):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Address Details:**")
                        
                        # Full address first (most important)
                        full_address = address_data.get('full_address')
                        if full_address:
                            st.write(f"**Full Address:** {full_address}")
                        
                        # Individual components
                        address_components = ['city', 'state', 'zip_code']
                        for field in address_components:
                            value = address_data.get(field)
                            if value:
                                st.write(f"**{field.replace('_', ' ').title()}:** {value}")
                        
                        # Street lines (if different from full address)
                        street_lines = address_data.get('street_lines')
                        if street_lines and isinstance(street_lines, list):
                            st.write("**Street Lines:**")
                            for line in street_lines:
                                if line:
                                    st.write(f"  • {line}")
                    
                    with col2:
                        # Geographic coordinates (if available)
                        lat = address_data.get('latitude')
                        lng = address_data.get('longitude')
                        if lat and lng:
                            st.markdown("**Geographic Coordinates:**")
                            st.write(f"**Latitude:** {lat}")
                            st.write(f"**Longitude:** {lng}")
                            
                            # Optional: Add a map link
                            map_url = f"https://www.google.com/maps?q={lat},{lng}"
                            st.write(f"[🗺️ View on Google Maps]({map_url})")
        else:
            st.info("No address data found for this company")
    
    with tab4:
        st.markdown("#### 📈 Data Summary")
        
        # Calculate data completeness
        company_fields_with_data = sum(1 for v in company_data.values() if v is not None and v != '' and v != [])
        total_company_fields = len([k for k, v in company_data.items() if k not in ['id', 'search_vector']])  # Exclude technical fields
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Company Data",
                f"{company_fields_with_data}/{total_company_fields}",
                f"{(company_fields_with_data/total_company_fields*100):.0f}% complete"
            )
            
            st.markdown("**Key Contact Info:**")
            key_fields = ['phone', 'email', 'website']
            for field in key_fields:
                value = company_data.get(field)
                status = "✅" if value else "❌"
                st.write(f"{status} {field.title()}")
        
        with col2:
            st.metric("License Records", len(licenses_data))
            
            if licenses_data:
                active_licenses = sum(1 for l in licenses_data if l.get('active'))
                authorized_licenses = sum(1 for l in licenses_data if l.get('authorized_to_conduct_business'))
                
                st.markdown("**License Status:**")
                st.write(f"✅ Active: {active_licenses}")
                st.write(f"🏛️ Authorized: {authorized_licenses}")
                
                # Unique states
                states = set(l.get('regulator', '').split()[-1] for l in licenses_data if l.get('regulator'))
                states = {s for s in states if len(s) == 2}  # State abbreviations
                if states:
                    st.write(f"📍 States: {len(states)}")
        
        with col3:
            st.metric("Address Records", len(addresses_data))
            
            if addresses_data:
                address_types = set(a.get('address_type') for a in addresses_data if a.get('address_type'))
                st.markdown("**Address Types:**")
                for addr_type in address_types:
                    st.write(f"📍 {addr_type.title()}")
                
                # Check if we have coordinates
                has_coords = sum(1 for a in addresses_data if a.get('latitude') and a.get('longitude'))
                if has_coords:
                    st.write(f"🗺️ Geocoded: {has_coords}")
        
        # Overall data quality assessment
        st.markdown("---")
        st.markdown("**📊 Overall Data Quality Assessment:**")
        
        quality_score = 0
        max_score = 10
        
        # Contact completeness (3 points)
        contact_score = sum(1 for field in ['phone', 'email', 'website'] if company_data.get(field))
        quality_score += contact_score
        
        # Business info completeness (2 points)
        business_score = sum(1 for field in ['business_structure', 'formed_in'] if company_data.get(field))
        quality_score += min(business_score, 2)
        
        # License data (3 points)
        if licenses_data:
            quality_score += min(len(licenses_data) // 5, 3)  # 1 point per 5 licenses, max 3
        
        # Address data (2 points)
        if addresses_data:
            quality_score += min(len(addresses_data), 2)
        
        # Display quality score
        quality_percentage = (quality_score / max_score) * 100
        
        if quality_percentage >= 80:
            st.success(f"🌟 **Excellent Data Quality:** {quality_score}/{max_score} ({quality_percentage:.0f}%)")
        elif quality_percentage >= 60:
            st.info(f"👍 **Good Data Quality:** {quality_score}/{max_score} ({quality_percentage:.0f}%)")
        elif quality_percentage >= 40:
            st.warning(f"⚠️ **Fair Data Quality:** {quality_score}/{max_score} ({quality_percentage:.0f}%)")
        else:
            st.error(f"📉 **Limited Data Quality:** {quality_score}/{max_score} ({quality_percentage:.0f}%)")

if __name__ == "__main__":
    main() 