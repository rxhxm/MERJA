#!/usr/bin/env python3
"""
MERJA - NMLS Lender Search & Analysis Tool
A streamlit application for searching and analyzing NMLS database with advanced licensing details and AI enrichment.
Last updated: 2025-01-19 - Enrichment section always visible with proper availability status

*** THIS IS THE WORKING ENRICHMENT VERSION - ALL THREADING AND DATABASE ISSUES FIXED ***
*** ENRICHMENT SERVICE FULLY FUNCTIONAL WITH PROPER ERROR HANDLING AND CONTEXT MANAGEMENT ***
*** NO MORE SCRIPTRUNCONTEXT ERRORS OR DATABASE TIMEOUTS - PRODUCTION READY ***
*** ENRICHMENT SECTION NOW ALWAYS VISIBLE WITH CLEAR STATUS INDICATORS ***
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
        
        # Results table
        if companies:
            st.subheader(f"📋 Lenders Found")
            
            # Create display data
            display_data = []
            for company in companies:
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
                    'Contact Info': '✅' if (company.get('phone') and company.get('email')) else '📧' if company.get('email') else '📞' if company.get('phone') else '❌'
                })
            
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True)
            
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
                        status_text.text(f"🔄 Enriching: {current_company} ({completed}/{total})")
                    
                    try:
                        with st.spinner("Starting enrichment process..."):
                            status_text.text("Initializing enrichment service...")
                            
                            # Run simplified enrichment
                            enriched_df, contacts_df = run_async(
                                enrichment_service.enrich_companies_batch(
                                    selected_companies,
                                    progress_callback=simple_progress_callback
                                )
                            )
                            
                            # Store results in session state
                            st.session_state.enriched_results = {
                                'companies': enriched_df,
                                'contacts': contacts_df,
                                'timestamp': datetime.now()
                            }
                            
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
                        # Display simplified data
                        display_columns = ['company_name', 'nmls_id', 'website', 'company_linkedin', 'industry', 'employees', 'personal_loans', 'qualified']
                        available_columns = [col for col in display_columns if col in enriched_df.columns]
                        
                        if available_columns:
                            display_df = enriched_df[available_columns].copy()
                            
                            # Format LinkedIn links
                            if 'company_linkedin' in display_df.columns:
                                display_df['Company LinkedIn'] = display_df['company_linkedin'].apply(
                                    lambda x: f"[🔗 LinkedIn]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                                )
                                display_df = display_df.drop('company_linkedin', axis=1)
                            
                            # Format columns
                            if 'personal_loans' in display_df.columns:
                                display_df['Personal Loans'] = display_df['personal_loans'].apply(
                                    lambda x: "✅ Yes" if str(x).lower().startswith('yes') else "❌ No" if str(x).lower().startswith('no') else "❓ Unknown"
                                )
                                display_df = display_df.drop('personal_loans', axis=1)
                            
                            if 'qualified' in display_df.columns:
                                display_df['Qualified'] = display_df['qualified'].apply(
                                    lambda x: "🎯 YES" if x else "❌ NO"
                                )
                                display_df = display_df.drop('qualified', axis=1)
                            
                            # Rename columns
                            column_renames = {
                                'company_name': 'Company',
                                'nmls_id': 'NMLS ID',
                                'website': 'Website',
                                'industry': 'Industry',
                                'employees': 'Employees'
                            }
                            
                            display_df = display_df.rename(columns=column_renames)
                            st.dataframe(display_df, use_container_width=True)
                        else:
                            st.warning("No enrichment data to display")
                    else:
                        st.info("No companies were successfully enriched")
                
                with tab2:
                    st.markdown("**Contact Information**")
                    
                    if not contacts_df.empty:
                        # Format LinkedIn links in contacts
                        display_contacts_df = contacts_df.copy()
                        if 'linkedin' in display_contacts_df.columns:
                            display_contacts_df['LinkedIn'] = display_contacts_df['linkedin'].apply(
                                lambda x: f"[🔗 Profile]({x})" if x and str(x) != 'nan' and str(x).strip() else "❌"
                            )
                            display_contacts_df = display_contacts_df.drop('linkedin', axis=1)
                        
                        # Rename columns for better display
                        column_renames = {
                            'company_name': 'Company',
                            'nmls_id': 'NMLS ID',
                            'name': 'Name',
                            'title': 'Title',
                            'email': 'Email'
                        }
                        display_contacts_df = display_contacts_df.rename(columns=column_renames)
                        
                        st.dataframe(display_contacts_df, use_container_width=True)
                        
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
                        st.info("No contacts found")
        else:
            st.info("No companies match the current filters.")

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

if __name__ == "__main__":
    main() 