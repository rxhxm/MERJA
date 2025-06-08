#!/usr/bin/env python3
"""
MERJA - NMLS Lender Search & Analysis Tool
A streamlit application for searching and analyzing NMLS database with advanced licensing details and AI enrichment.
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

# Configure Streamlit page
st.set_page_config(
    page_title="NMLS Search",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Check enrichment availability
try:
    from enrichment_service import create_enrichment_service
    ENRICHMENT_AVAILABLE = True
except ImportError:
    ENRICHMENT_AVAILABLE = False
    st.warning(
        "⚠️ Enrichment service unavailable. Search functionality will work normally.")

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

# Initialize session state
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'last_query' not in st.session_state:
    st.session_state.last_query = ""
if 'enriched_results' not in st.session_state:
    st.session_state.enriched_results = None
if 'enrichment_running' not in st.session_state:
    st.session_state.enrichment_running = False


def run_async(coro):
    """
    Production-grade async runner for Streamlit that completely isolates event loops.
    
    This approach:
    1. Runs async code in a separate thread with its own event loop
    2. Ensures complete cleanup of all async resources
    3. Prevents any event loop conflicts with Streamlit
    4. Handles database connections and HTTP clients properly
    """
    def run_in_thread():
        """Run coroutine in a completely separate thread with fresh event loop"""
        # Create a completely new event loop in this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run the coroutine in the fresh loop
            result = loop.run_until_complete(coro)
            return result
        except Exception as e:
            logger.error(f"Async execution error: {e}")
            raise e
        finally:
            # Ensure complete cleanup
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # Wait for all tasks to complete cancellation
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # Close the loop
                loop.close()
            except Exception as cleanup_error:
                logger.warning(f"Cleanup error (non-critical): {cleanup_error}")

    # Use ThreadPoolExecutor to run async code in isolation
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_thread)
        try:
            # Wait for result with timeout to prevent hanging
            result = future.result(timeout=300)  # 5 minute timeout
            return result
        except concurrent.futures.TimeoutError:
            logger.error("Async operation timed out")
            raise TimeoutError("Search operation timed out after 5 minutes")
        except Exception as e:
            logger.error(f"Thread execution error: {e}")
            raise e


async def search_companies(
        query: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
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
    """Format lender type with simple classification"""
    if not license_types:
        license_types = []

    target_licenses = [
        lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
    exclude_licenses = [
        lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]

    if lender_type == 'unsecured_personal':
        return f'🎯 TARGET ({len(target_licenses)} personal)'
    elif lender_type == 'mortgage':
        return f'❌ EXCLUDE ({len(exclude_licenses)} mortgage)'
    elif lender_type == 'mixed':
        return f'⚠️ MIXED ({len(target_licenses)} personal + {len(exclude_licenses)} mortgage)'
    else:
        return f'❓ UNKNOWN'


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
    st.markdown(
        '<h1 class="main-header">NMLS Search</h1>',
        unsafe_allow_html=True)

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
        search_clicked = st.button(
            "🔍 Search",
            type="primary",
            use_container_width=True)
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        selected_states = st.multiselect(
            "📍 States Licensed In:",
            [
                "CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI",
                "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
                "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT",
                "AR", "NV", "IA", "MS", "KS", "NM", "NE", "ID", "WV", "NH",
                "ME", "MT", "RI", "DE", "SD", "ND", "AK", "VT", "WY", "HI", "DC"])
    
    with col2:
        lender_type_filter = st.selectbox(
            "🏦 Lender Type:", [
                "All Types", "Unsecured Personal (TARGET)", "Mortgage (EXCLUDE)", "Mixed", "Unknown"])
    
    # Perform search
    if search_clicked and query:
        st.session_state.last_query = query
        with st.spinner("🔍 Searching database..."):
            try:
                result = run_async(search_companies(query))
                if result and result['companies']:
                    st.session_state.search_results = result
                    st.success(f"✅ Found {len(result['companies'])} results!")
                else:
                    st.error("❌ No results found. Try a different search.")
            except Exception as e:
                st.error(f"❌ Search failed: {str(e)}")
    
    # Display results
    if st.session_state.search_results:
        result = st.session_state.search_results
        companies = result['companies']
        
        # Apply filters
        if selected_states:
            companies = [
                c for c in companies if any(
                    state in c.get('states_licensed', []) for state in selected_states)]
        
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
            
            # Company Enrichment Section
            if ENRICHMENT_AVAILABLE:
                st.markdown("---")
                st.markdown("### 🧠 SixtyFour AI Enrichment")
                st.markdown("Use AI to enrich company data with business intelligence, contact information, and ICP matching.")
                
                # Debug info - show what companies we have
                target_companies_available = [c for c in companies if c.get('lender_type') == 'unsecured_personal']
                st.info(f"🔍 Debug: Found {len(target_companies_available)} TARGET companies in current results")
                
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
                            if target_companies:
                                # Sort by business_score if available, otherwise by company name
                                companies_to_enrich = sorted(target_companies, 
                                                           key=lambda x: x.get('business_score', 50), 
                                                           reverse=True)[:5]
                            st.info(f"🔍 Debug: Found {len(target_companies)} target companies, selected {len(companies_to_enrich)}")
                        elif enrichment_filter == "Top 10 by Business Score":
                            # Sort by business_score if available, otherwise by company name
                            companies_to_enrich = sorted(companies, 
                                                       key=lambda x: x.get('business_score', 50), 
                                                       reverse=True)[:10]
                        elif enrichment_filter == "All TARGET Lenders":
                            companies_to_enrich = [c for c in companies if c.get('lender_type') == 'unsecured_personal']
                        elif enrichment_filter == "All Results":
                            companies_to_enrich = companies
                        
                        # Debug: Show what we found
                        st.info(f"🔍 Debug: Selected {len(companies_to_enrich)} companies for enrichment")
                        if companies_to_enrich:
                            st.info(f"🔍 Debug: First company example: {companies_to_enrich[0].get('company_name', 'Unknown')} (Type: {companies_to_enrich[0].get('lender_type', 'Unknown')})")
                        
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
                            # Show debug info about what companies we have
                            lender_types = [c.get('lender_type', 'unknown') for c in companies]
                            lender_type_counts = {lt: lender_types.count(lt) for lt in set(lender_types)}
                            st.info(f"🔍 Debug: Lender types in results: {lender_type_counts}")
                
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
                                    st.markdown("**📊 ICP Analysis:**")
                                    if 'enriched_icp_match' in selected_row:
                                        st.write(f"🎯 **ICP Match:** {selected_row['enriched_icp_match']}")
                                    if 'enrichment_quality_score' in selected_row:
                                        st.write(f"📈 **Quality Score:** {selected_row['enrichment_quality_score']}")
                                    if 'is_qualified_lead' in selected_row:
                                        st.write(f"✅ **Qualified Lead:** {selected_row['is_qualified_lead']}")
                        
                        # Contacts section
                        if not contacts_df.empty:
                            st.markdown("#### 👥 Key Contacts Found")
                            st.dataframe(contacts_df, use_container_width=True)
                            
                            # Export contacts
                            csv = contacts_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "📥 Export Contacts CSV",
                                csv,
                                f"contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                "text/csv"
                            )
                    else:
                        st.info("No enriched data available yet. Use the enrichment feature above to get started.")
            
            # Export functionality
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export CSV",
                data=csv,
                file_name=f"lenders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv")
        else:
            st.info("🔍 No companies match your filters. Try adjusting the filters above.")


if __name__ == "__main__":
    main() 
