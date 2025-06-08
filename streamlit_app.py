#!/usr/bin/env python3
"""
MERJA - NMLS Lender Search & Analysis Tool
A streamlined Streamlit application for searching and analyzing NMLS database.
"""

import streamlit as st
import pandas as pd
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any

# Import unified search system
from unified_search import (
    run_unified_search,
    SearchFilters,
    LenderType,
    LenderClassifier
)

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
    """Simple async runner for Streamlit"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Async execution error: {e}")
        raise


async def search_companies(
        query: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
    """Run search using unified search API"""
    try:
        search_filters = SearchFilters(**filters) if filters else None

        result = await run_unified_search(
            query=query,
            filters=search_filters,
            use_ai=True,
            page=1,
            page_size=10000
        )

        return result

    except Exception as e:
        st.error(f"Search error: {str(e)}")
        return {
            "companies": [],
            "total_count": 0,
            "query_analysis": None
        }


def format_lender_type(lender_type: str, license_types: List[str]) -> str:
    """Format lender type with simple classification"""
    if not license_types:
        license_types = []

    target_licenses = [
        lt for lt in license_types if lt in LenderClassifier.UNSECURED_LICENSES]
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
                "CA",
                "TX",
                "FL",
                "NY",
                "IL",
                "PA",
                "OH",
                "GA",
                "NC",
                "MI",
                "NJ",
                "VA",
                "WA",
                "AZ",
                "MA",
                "TN",
                "IN",
                "MO",
                "MD",
                "WI",
                "CO",
                "MN",
                "SC",
                "AL",
                "LA",
                "KY",
                "OR",
                "OK",
                "CT",
                "UT",
                "AR",
                "NV",
                "IA",
                "MS",
                "KS",
                "NM",
                "NE",
                "ID",
                "WV",
                "NH",
                "ME",
                "MT",
                "RI",
                "DE",
                "SD",
                "ND",
                "AK",
                "VT",
                "WY",
                "HI",
                "DC"])

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
                    state in c.get(
                        'states_licensed',
                        []) for state in selected_states)]

        if lender_type_filter != "All Types":
            lender_map = {
                "Unsecured Personal (TARGET)": "unsecured_personal",
                "Mortgage (EXCLUDE)": "mortgage",
                "Mixed": "mixed",
                "Unknown": "unknown"
            }
            target_type = lender_map.get(lender_type_filter)
            if target_type:
                companies = [c for c in companies if c.get(
                    'lender_type') == target_type]

        # Summary metrics
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Found", len(companies))
        with col2:
            target_count = sum(1 for c in companies if c.get(
                'lender_type') == 'unsecured_personal')
            st.metric("🎯 Target Lenders", target_count)
        with col3:
            exclude_count = sum(
                1 for c in companies if c.get('lender_type') == 'mortgage')
            st.metric("❌ Mortgage Lenders", exclude_count)
        with col4:
            states_covered = len(
                set([state for c in companies for state in c.get('states_licensed', [])]))
            st.metric("States Covered", states_covered)

        # Results table
        if companies:
            st.subheader(f"📋 Lenders Found ({len(companies)} results)")

            # Create display data
            display_data = []
            for company in companies:
                states_licensed = company.get('states_licensed', [])
                states_str = ', '.join(
                    sorted(states_licensed)) if states_licensed else 'Unknown'
                if len(states_str) > 50:
                    states_str = states_str[:47] + '...'

                license_types = company.get('license_types', []) or []
                lender_type = company.get('lender_type', 'unknown')

                display_data.append(
                    {
                        'NMLS ID': company['nmls_id'],
                        'Company Name': company['company_name'],
                        'Lender Type': format_lender_type(
                            lender_type,
                            license_types),
                        'States Licensed': states_str,
                        'Total States': len(states_licensed),
                        'Contact Info': '✅' if (
                            company.get('phone') and company.get('email')) else '📧' if company.get('email') else '📞' if company.get('phone') else '❌'})

            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True)

            # Export functionality
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export CSV",
                data=csv,
                file_name=f"lenders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv")

            # Simple enrichment section
            if ENRICHMENT_AVAILABLE:
                st.markdown("---")
                st.markdown("### 🧠 Company Enrichment")

                if not st.session_state.enrichment_running:
                    col1, col2 = st.columns(2)

                    with col1:
                        enrichment_filter = st.selectbox(
                            "Companies to enrich:", [
                                "Top 5 Target Lenders", "Top 10 Results", "All TARGET Lenders"])

                    with col2:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🧠 Start Enrichment", type="secondary"):
                            st.session_state.enrichment_running = True

                            # Select companies
                            if enrichment_filter == "Top 5 Target Lenders":
                                target_companies = [
                                    c for c in companies if c.get('lender_type') == 'unsecured_personal']
                                companies_to_enrich = sorted(
                                    target_companies, key=lambda x: x.get(
                                        'business_score', 0), reverse=True)[
                                    :5]
                            elif enrichment_filter == "Top 10 Results":
                                companies_to_enrich = companies[:10]
                            else:
                                companies_to_enrich = [
                                    c for c in companies if c.get('lender_type') == 'unsecured_personal']

                            if companies_to_enrich:
                                try:
                                    enrichment_service = create_enrichment_service()
                                    if enrichment_service:
                                        with st.spinner(f"Enriching {len(companies_to_enrich)} companies..."):
                                            enriched_df, contacts_df = run_async(
                                                enrichment_service.enrich_companies_batch(companies_to_enrich))

                                            st.session_state.enriched_results = {
                                                'companies': enriched_df,
                                                'contacts': contacts_df,
                                                'timestamp': datetime.now()
                                            }

                                            st.success(
                                                f"✅ Enriched {len(enriched_df)} companies!")
                                    else:
                                        st.error(
                                            "❌ Enrichment service not available")
                                except Exception as e:
                                    st.error(f"❌ Enrichment failed: {str(e)}")
                                finally:
                                    st.session_state.enrichment_running = False
                            else:
                                st.warning(
                                    "⚠️ No companies selected for enrichment")
                                st.session_state.enrichment_running = False
                else:
                    st.info("🔄 Enrichment in progress...")

                # Display enrichment results
                if st.session_state.enriched_results:
                    enriched_data = st.session_state.enriched_results
                    enriched_df = enriched_data['companies']
                    contacts_df = enriched_data['contacts']

                    st.markdown("#### 📊 Enrichment Results")

                    if not enriched_df.empty:
                        successful_companies = enriched_df[enriched_df['enrichment_status'] == 'Success']

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("✅ Enriched", len(successful_companies))
                        with col2:
                            qualified = len(
                                enriched_df[enriched_df.get('is_qualified_lead', False)])
                            st.metric("🎯 Qualified", qualified)
                        with col3:
                            st.metric("👥 Contacts", len(contacts_df)
                                      if not contacts_df.empty else 0)

                        # Show enriched data
                        if not successful_companies.empty:
                            display_cols = [
                                'company_name', 'nmls_id', 'lender_type']
                            if 'enriched_website' in successful_companies.columns:
                                display_cols.append('enriched_website')
                            if 'enriched_specializes_in_personal_loans' in successful_companies.columns:
                                display_cols.append(
                                    'enriched_specializes_in_personal_loans')

                            st.dataframe(
                                successful_companies[display_cols],
                                use_container_width=True)

                        # Export enriched data
                        if st.button("📊 Export Enriched Data"):
                            csv = enriched_df.to_csv(index=False)
                            st.download_button(
                                "📥 Download Enriched CSV",
                                csv,
                                f"enriched_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                "text/csv")
        else:
            st.info(
                "🔍 No companies match your filters. Try adjusting the filters above.")


if __name__ == "__main__":
    main()
