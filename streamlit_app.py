#!/usr/bin/env python3
"""
MERJA - NMLS Lender Search & Analysis Tool
A streamlit application for searching and analyzing NMLS database with advanced licensing details and AI enrichment.
Last updated: 2025-01-19 - Force deployment refresh with session state fix
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
import threading
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Any
import os

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

# Initialize session state at module level to ensure it's available immediately
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'last_query' not in st.session_state:
    st.session_state.last_query = ""
if 'enriched_results' not in st.session_state:
    st.session_state.enriched_results = None
if 'enrichment_running' not in st.session_state:
    st.session_state.enrichment_running = False

# Global cancellation state (thread-safe, no session state dependency)
_global_enrichment_state = {'running': False, 'lock': threading.Lock()}

# Check enrichment availability
try:
    from enrichment_service import create_enrichment_service
    ENRICHMENT_AVAILABLE = True
except ImportError:
    ENRICHMENT_AVAILABLE = False
    st.warning("⚠️ Enrichment service unavailable. Search functionality will work normally.")

# Database pool setup
_db_pool = None

async def get_or_create_pool():
    """Creates and returns the asyncpg connection pool"""
    global _db_pool
    if _db_pool is None:
        try:
            import asyncpg
            DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
            if not DATABASE_URL:
                logger.error("DATABASE_URL not found")
                return None
            _db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=5,
                statement_cache_size=0  # For pgbouncer compatibility
            )
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            return None
    return _db_pool

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
    """Production-grade async runner for Streamlit"""
    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro)
            return result
        except Exception as e:
            logger.error(f"Async execution error: {e}")
            raise e
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()
            except Exception as cleanup_error:
                logger.warning(f"Cleanup error (non-critical): {cleanup_error}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        try:
            result = future.result(timeout=300)
            return result
        except concurrent.futures.TimeoutError:
            logger.error("Async operation timed out")
            raise TimeoutError("Search operation timed out after 5 minutes")
        except Exception as e:
            logger.error(f"Thread execution error: {e}")
            raise e

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
    """Format license summary for a company"""
    try:
        nmls_id = company.get('nmls_id', '')
        if not nmls_id:
            return "License details unavailable"
        
        # Use existing data as fallback
        license_types = company.get('license_types', []) or []
        states_licensed = company.get('states_licensed', []) or []
        
        if not license_types:
            return "License details unavailable"
        
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
            summary_parts.append(f"ℹ️ {len(other_licenses)} other ({states_str})")
        
        return " | ".join(summary_parts) if summary_parts else "License details unavailable"
        
    except Exception as e:
        logger.error(f"Error formatting license summary: {e}")
        return "License details unavailable"

def main():
    """Main application"""
    st.markdown('<h1 class="main-header">NMLS Search</h1>', unsafe_allow_html=True)

    # Main search interface
    st.header("🔍 Enhanced AI Search")
    
    # Initialize session state for search query
    if 'search_query' not in st.session_state:
        st.session_state['search_query'] = ""
    
    st.header("NMLS Lender Search")
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
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        selected_states = st.multiselect(
            "📍 States Licensed In:",
            ["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI", "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI", "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT", "AR", "NV", "IA", "MS", "KS", "NM", "NE", "ID", "WV", "NH", "ME", "MT", "RI", "DE", "SD", "ND", "AK", "VT", "WY", "HI", "DC"])
    
    with col2:
        lender_type_filter = st.selectbox(
            "🏦 Lender Type:", 
            ["All Types", "Unsecured Personal (TARGET)", "Mortgage (EXCLUDE)", "Mixed", "Unknown"])
    
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
        
        # Apply filters
        if selected_states:
            companies = [c for c in companies if any(state in c.get('states_licensed', []) for state in selected_states)]
        
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
        
        # Results table
        if companies:
            st.subheader(f"📋 Lenders Found ({len(companies)} results)")
            
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
                    
                    # Get detailed license state breakdown
                    with st.spinner("Loading detailed license breakdown..."):
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

            # Add enrichment section after license analysis
            st.markdown("---")
            st.markdown("### 🚀 Company Enrichment")
            st.markdown("Enrich selected companies with additional business intelligence using AI-powered data gathering.")
            
            if ENRICHMENT_AVAILABLE:
                # Company selection for enrichment
                st.markdown("#### Select Companies to Enrich")
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
                    help="Select companies you want to enrich with additional business data and contacts"
                )
                
                # Enrichment controls
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    if selected_company_indices:
                        st.info(f"Selected {len(selected_company_indices)} companies for enrichment")
                
                with col2:
                    enrich_button = st.button(
                        "🚀 Start Enrichment",
                        disabled=not selected_company_indices or st.session_state.enrichment_running,
                        use_container_width=True,
                        type="primary"
                    )
                
                with col3:
                    if st.session_state.enrichment_running:
                        if st.button("🛑 Cancel", use_container_width=True):
                            # Update both session state and global state for cancellation
                            st.session_state.enrichment_running = False
                            with _global_enrichment_state['lock']:
                                _global_enrichment_state['running'] = False
                            st.rerun()
                
                # Enrichment processing
                if enrich_button and selected_company_indices:
                    st.session_state.enrichment_running = True
                    
                    # Initialize global cancellation state
                    with _global_enrichment_state['lock']:
                        _global_enrichment_state['running'] = True
                    
                    selected_companies = [companies[i] for i in selected_company_indices]
                    
                    # Create enrichment service
                    enrichment_service = create_enrichment_service()
                    
                    if not enrichment_service:
                        st.error("❌ Enrichment service unavailable. Please check API key configuration.")
                        st.session_state.enrichment_running = False
                        with _global_enrichment_state['lock']:
                            _global_enrichment_state['running'] = False
                    else:
                        # Progress tracking
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        results_container = st.empty()
                        
                        def progress_callback(completed, total, current_company):
                            progress = completed / total
                            progress_bar.progress(progress)
                            status_text.text(f"Enriching {current_company}... ({completed}/{total} completed)")
                        
                        def cancellation_check():
                            # Use global thread-safe state
                            with _global_enrichment_state['lock']:
                                return not _global_enrichment_state['running']
                        
                        try:
                            with st.spinner("Starting enrichment process..."):
                                status_text.text("Initializing enrichment service...")
                                
                                # Create custom progress callback for Streamlit - NO session state access
                                def streamlit_progress_callback(completed, total, current_company):
                                    # Check global thread-safe state
                                    with _global_enrichment_state['lock']:
                                        if not _global_enrichment_state['running']:
                                            return
                                    
                                    progress = completed / total
                                    progress_bar.progress(progress)
                                    status_text.text(f"🔄 Enriching: {current_company} ({completed}/{total})")
                                
                                # Run enrichment with global state - no session state access
                                enriched_df, contacts_df = run_async(
                                    enrichment_service.enrich_companies_batch(
                                        selected_companies,
                                        progress_callback=streamlit_progress_callback,
                                        cancellation_check=cancellation_check
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
                            st.error(f"❌ Enrichment failed: {str(e)}")
                            status_text.text("❌ Enrichment failed")
                        finally:
                            # Clear both session state and global state
                            st.session_state.enrichment_running = False
                            with _global_enrichment_state['lock']:
                                _global_enrichment_state['running'] = False
                
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
                        qualified_count = len(enriched_df[enriched_df.get('is_qualified', False) == True]) if 'is_qualified' in enriched_df.columns else 0
                        st.metric("Qualified Leads", qualified_count)
                    with col3:
                        total_contacts = len(contacts_df)
                        st.metric("Contacts Found", total_contacts)
                    with col4:
                        decision_makers = len(contacts_df[contacts_df.get('is_decision_maker', False) == True]) if 'is_decision_maker' in contacts_df.columns else 0
                        st.metric("Decision Makers", decision_makers)
                    
                    # Tabs for different views
                    tab1, tab2, tab3 = st.tabs(["📈 Company Insights", "👥 Contacts & Leads", "📋 Raw Data"])
                    
                    with tab1:
                        st.markdown("**Enriched Company Analysis**")
                        
                        if not enriched_df.empty:
                            # Filter for display
                            display_columns = [
                                'company_name', 'nmls_id', 'api_specializes_in_personal_loans',
                                'api_icp_match', 'is_qualified', 'api_num_employees',
                                'api_website', 'api_industry', 'enrichment_quality_score'
                            ]
                            
                            # Only show columns that exist
                            available_columns = [col for col in display_columns if col in enriched_df.columns]
                            
                            if available_columns:
                                display_df = enriched_df[available_columns].copy()
                                
                                # Format columns for better display
                                if 'api_specializes_in_personal_loans' in display_df.columns:
                                    display_df['Personal Loans'] = display_df['api_specializes_in_personal_loans'].apply(
                                        lambda x: "✅ Yes" if str(x).lower().startswith('yes') else "❌ No" if str(x).lower().startswith('no') else "❓ Unknown"
                                    )
                                    display_df = display_df.drop('api_specializes_in_personal_loans', axis=1)
                                
                                if 'is_qualified' in display_df.columns:
                                    display_df['Qualified'] = display_df['is_qualified'].apply(
                                        lambda x: "🎯 YES" if x else "❌ NO"
                                    )
                                    display_df = display_df.drop('is_qualified', axis=1)
                                
                                # Rename columns for display
                                column_renames = {
                                    'company_name': 'Company',
                                    'nmls_id': 'NMLS ID',
                                    'api_icp_match': 'ICP Match',
                                    'api_num_employees': 'Employees',
                                    'api_website': 'Website',
                                    'api_industry': 'Industry',
                                    'enrichment_quality_score': 'Quality Score'
                                }
                                
                                display_df = display_df.rename(columns=column_renames)
                                st.dataframe(display_df, use_container_width=True)
                            else:
                                st.warning("No enrichment data available to display")
                                
                        # Detailed company view
                        if not enriched_df.empty:
                            st.markdown("**Detailed Company Analysis**")
                            company_names = enriched_df['company_name'].tolist()
                            selected_enriched_company = st.selectbox(
                                "Select company for detailed analysis:",
                                options=["None"] + company_names
                            )
                            
                            if selected_enriched_company != "None":
                                company_row = enriched_df[enriched_df['company_name'] == selected_enriched_company].iloc[0]
                                
                                st.markdown(f"##### {selected_enriched_company}")
                                
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.markdown("**Business Intelligence:**")
                                    
                                    if 'api_website' in company_row and pd.notna(company_row['api_website']):
                                        st.write(f"🌐 **Website:** {company_row['api_website']}")
                                    
                                    if 'api_industry' in company_row and pd.notna(company_row['api_industry']):
                                        st.write(f"🏢 **Industry:** {company_row['api_industry']}")
                                    
                                    if 'api_num_employees' in company_row and pd.notna(company_row['api_num_employees']):
                                        st.write(f"👥 **Employees:** {company_row['api_num_employees']}")
                                    
                                    if 'api_specializes_in_personal_loans' in company_row:
                                        personal_loans = company_row['api_specializes_in_personal_loans']
                                        emoji = "✅" if str(personal_loans).lower().startswith('yes') else "❌"
                                        st.write(f"{emoji} **Personal Loans:** {personal_loans}")
                                
                                with col2:
                                    st.markdown("**Assessment:**")
                                    
                                    if 'is_qualified' in company_row:
                                        qualified = company_row['is_qualified']
                                        emoji = "🎯" if qualified else "❌"
                                        st.write(f"{emoji} **Qualified Lead:** {'Yes' if qualified else 'No'}")
                                    
                                    if 'api_icp_match' in company_row and pd.notna(company_row['api_icp_match']):
                                        st.write(f"🎯 **ICP Match:** {company_row['api_icp_match']}")
                                    
                                    if 'enrichment_quality_score' in company_row:
                                        quality = company_row['enrichment_quality_score']
                                        st.write(f"⭐ **Quality Score:** {quality:.1f}/100")
                                    
                                    if 'qualification_reasons' in company_row and pd.notna(company_row['qualification_reasons']):
                                        st.write(f"📋 **Reasons:** {company_row['qualification_reasons']}")
                    
                    with tab2:
                        st.markdown("**Contact Information & Decision Makers**")
                        
                        if not contacts_df.empty:
                            # Filter and display contacts
                            contact_display_columns = [
                                'company_name', 'name', 'title', 'email', 'linkedin',
                                'is_decision_maker', 'decision_maker_score', 'relevance_score'
                            ]
                            
                            available_contact_columns = [col for col in contact_display_columns if col in contacts_df.columns]
                            
                            if available_contact_columns:
                                contact_display_df = contacts_df[available_contact_columns].copy()
                                
                                # Format decision maker column
                                if 'is_decision_maker' in contact_display_df.columns:
                                    contact_display_df['Decision Maker'] = contact_display_df['is_decision_maker'].apply(
                                        lambda x: "🎯 YES" if x else "👤 No"
                                    )
                                    contact_display_df = contact_display_df.drop('is_decision_maker', axis=1)
                                
                                # Rename columns
                                contact_renames = {
                                    'company_name': 'Company',
                                    'name': 'Name',
                                    'title': 'Title',
                                    'email': 'Email',
                                    'linkedin': 'LinkedIn',
                                    'decision_maker_score': 'DM Score',
                                    'relevance_score': 'Relevance'
                                }
                                
                                contact_display_df = contact_display_df.rename(columns=contact_renames)
                                
                                # Sort by decision makers first, then relevance
                                if 'Decision Maker' in contact_display_df.columns:
                                    contact_display_df = contact_display_df.sort_values(['Decision Maker', 'Relevance'], ascending=[False, False])
                                
                                st.dataframe(contact_display_df, use_container_width=True)
                                
                                # Export options
                                st.markdown("**Export Options:**")
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    if st.button("📧 Download Contacts CSV"):
                                        csv = contacts_df.to_csv(index=False)
                                        st.download_button(
                                            label="Download Contacts",
                                            data=csv,
                                            file_name=f"enriched_contacts_{timestamp.strftime('%Y%m%d_%H%M%S')}.csv",
                                            mime="text/csv"
                                        )
                                
                                with col2:
                                    if st.button("🏢 Download Companies CSV"):
                                        csv = enriched_df.to_csv(index=False)
                                        st.download_button(
                                            label="Download Companies",
                                            data=csv,
                                            file_name=f"enriched_companies_{timestamp.strftime('%Y%m%d_%H%M%S')}.csv",
                                            mime="text/csv"
                                        )
                            else:
                                st.warning("No contact data available")
                        else:
                            st.info("No contacts found in enrichment results")
                    
                    with tab3:
                        st.markdown("**Raw Enrichment Data**")
                        
                        if not enriched_df.empty:
                            st.markdown("**Companies Data:**")
                            st.dataframe(enriched_df, use_container_width=True)
                        
                        if not contacts_df.empty:
                            st.markdown("**Contacts Data:**")
                            st.dataframe(contacts_df, use_container_width=True)
                    
                    # Additional actions
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("🔄 Clear Results"):
                            st.session_state.enriched_results = None
                            st.rerun()
                    
                    with col2:
                        if st.button("📊 Run New Enrichment"):
                            # Keep results but allow new enrichment
                            pass
                    
                    with col3:
                        st.info(f"Enriched on: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            else:
                st.warning("⚠️ Enrichment service is not available. Please check that the enrichment dependencies are installed and the API key is configured.")
                st.info("To enable enrichment, ensure the SixtyFour API key is configured in your Streamlit secrets.")
        else:
            st.info("No companies match the current filters.")

if __name__ == "__main__":
    main() 