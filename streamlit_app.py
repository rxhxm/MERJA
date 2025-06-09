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

def format_lender_type(lender_type: str, license_types: List[str]) -> str:
    """Format lender type with emoji indicators"""
    type_map = {
        'unsecured_personal': '🎯 Target Lender',
        'mortgage': '❌ Mortgage (Exclude)',
        'mixed': '⚠️ Mixed',
        'unknown': '❓ Unknown'
    }
    return type_map.get(lender_type, '❓ Unknown')

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
        else:
            st.info("No companies match the current filters.")

if __name__ == "__main__":
    main() 