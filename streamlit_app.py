#!/usr/bin/env python3
"""
MERJA - NMLS Lender Search & Analysis Tool
A streamlined Streamlit application for searching and analyzing NMLS database.
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
            
            # Advanced license analysis
            st.markdown("### 🔍 License Analysis")
            
            # Get all unique license types from results
            all_license_types = set()
            for company in companies:
                license_types = company.get('license_types', []) or []
                all_license_types.update(license_types)
            
            if all_license_types:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**📊 License Distribution:**")
                    license_counts = {}
                    for license_type in all_license_types:
                        count = sum(1 for c in companies if license_type in (c.get('license_types', []) or []))
                        license_counts[license_type] = count
                    
                    # Show top 10 most common licenses
                    sorted_licenses = sorted(license_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                    for license_type, count in sorted_licenses:
                        st.text(f"• {license_type}: {count} companies")
                
                with col2:
                    st.markdown("**🎯 License Type Filter:**")
                    selected_license_types = st.multiselect(
                        "Filter by specific license types:",
                        sorted(all_license_types),
                        help="Select specific license types to narrow down results"
                    )
                    
                    if selected_license_types:
                        companies = [
                            c for c in companies 
                            if any(lt in (c.get('license_types', []) or []) for lt in selected_license_types)
                        ]
                        st.info(f"Filtered to {len(companies)} companies with selected license types")
            
            # Enhanced company selection
            st.markdown("---")
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown("### 📋 Company Details")
                
                # Company selection
                if len(companies) > 0:
                    selected_company_names = [f"{c['company_name']} (NMLS: {c['nmls_id']})" for c in companies]
                    
                    # Multi-select for companies
                    selected_companies = st.multiselect(
                        "Select companies for detailed analysis:",
                        selected_company_names,
                        help="Select one or more companies to see detailed license information"
                    )
                    
                    if selected_companies:
                        st.markdown("### 📊 Selected Company Analysis")
                        
                        for selected_name in selected_companies:
                            # Find the company data
                            nmls_id = selected_name.split("NMLS: ")[1].replace(")", "")
                            company = next((c for c in companies if c['nmls_id'] == nmls_id), None)
                            
                            if company:
                                with st.expander(f"🏢 {company['company_name']}", expanded=True):
                                    col1, col2, col3 = st.columns(3)
                                    
                                    with col1:
                                        st.markdown("**📋 Basic Info:**")
                                        st.write(f"**NMLS ID:** {company['nmls_id']}")
                                        st.write(f"**Business Structure:** {company.get('business_structure', 'N/A')}")
                                        st.write(f"**Lender Type:** {format_lender_type(company.get('lender_type', 'unknown'), company.get('license_types', []))}")
                                        st.write(f"**Business Score:** {company.get('business_score', 0):.1f}/100")
                                    
                                    with col2:
                                        st.markdown("**📞 Contact Info:**")
                                        if company.get('email'):
                                            st.write(f"**Email:** {company['email']}")
                                        if company.get('phone'):
                                            st.write(f"**Phone:** {company['phone']}")
                                        if company.get('website'):
                                            st.write(f"**Website:** {company['website']}")
                                        
                                        # Contact validation status
                                        contact_issues = company.get('contact_issues', [])
                                        if not contact_issues:
                                            st.success("✅ Valid contact information")
                                        else:
                                            st.warning(f"⚠️ Issues: {', '.join(contact_issues)}")
                                    
                                    with col3:
                                        st.markdown("**📍 Address Info:**")
                                        if company.get('street_address'):
                                            st.write(f"**Street:** {company['street_address'][:100]}...")
                                        if company.get('mailing_address'):
                                            st.write(f"**Mailing:** {company['mailing_address'][:100]}...")
                                        
                                        states_licensed = company.get('states_licensed', [])
                                        if states_licensed:
                                            st.write(f"**States Licensed:** {len(states_licensed)} states")
                                            st.write(f"**States:** {', '.join(sorted(states_licensed))}")
                                    
                                    # Detailed License Analysis
                                    st.markdown("**📜 License Analysis:**")
                                    license_types = company.get('license_types', []) or []
                                    total_licenses = company.get('total_licenses', 0)
                                    active_licenses = company.get('active_licenses', 0)
                                    
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("Total Licenses", total_licenses)
                                    with col2:
                                        st.metric("Active Licenses", active_licenses)
                                    with col3:
                                        if total_licenses > 0:
                                            st.metric("Active Rate", f"{(active_licenses/total_licenses*100):.1f}%")
                                    
                                    if license_types:
                                        st.markdown("**License Types:**")
                                        
                                        # Categorize licenses
                                        personal_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                                        mortgage_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
                                        other_licenses = [lt for lt in license_types if lt not in LenderClassifier.UNSECURED_PERSONAL_LICENSES and lt not in LenderClassifier.MORTGAGE_LICENSES]
                                        
                                        if personal_licenses:
                                            st.success(f"🎯 **Personal/Unsecured Licenses ({len(personal_licenses)}):**")
                                            for license_type in personal_licenses:
                                                st.write(f"• {license_type}")
                                        
                                        if mortgage_licenses:
                                            st.error(f"❌ **Mortgage Licenses ({len(mortgage_licenses)}):**")
                                            for license_type in mortgage_licenses:
                                                st.write(f"• {license_type}")
                                        
                                        if other_licenses:
                                            st.info(f"❓ **Other Licenses ({len(other_licenses)}):**")
                                            for license_type in other_licenses:
                                                st.write(f"• {license_type}")
                                    else:
                                        st.warning("No license types available")
            
            with col2:
                st.markdown("### 🎯 Quick Actions")
                
                if selected_companies:
                    st.markdown("**📊 Bulk Analysis:**")
                    
                    # Calculate stats for selected companies
                    selected_nmls_ids = [sc.split("NMLS: ")[1].replace(")", "") for sc in selected_companies]
                    selected_company_data = [c for c in companies if c['nmls_id'] in selected_nmls_ids]
                    
                    target_count = sum(1 for c in selected_company_data if c.get('lender_type') == 'unsecured_personal')
                    mortgage_count = sum(1 for c in selected_company_data if c.get('lender_type') == 'mortgage')
                    mixed_count = sum(1 for c in selected_company_data if c.get('lender_type') == 'mixed')
                    
                    st.metric("Selected Companies", len(selected_companies))
                    st.metric("🎯 Target Companies", target_count)
                    st.metric("❌ Mortgage Companies", mortgage_count)
                    st.metric("⚠️ Mixed Companies", mixed_count)
                    
                    # Export selected companies
                    if selected_company_data:
                        selected_df_data = []
                        for company in selected_company_data:
                            license_types = company.get('license_types', []) or []
                            personal_licenses = [lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
                            mortgage_licenses = [lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES]
                            
                            selected_df_data.append({
                                'NMLS_ID': company['nmls_id'],
                                'Company_Name': company['company_name'],
                                'Lender_Type': company.get('lender_type', 'unknown'),
                                'Business_Score': company.get('business_score', 0),
                                'Email': company.get('email', ''),
                                'Phone': company.get('phone', ''),
                                'Website': company.get('website', ''),
                                'States_Licensed': '; '.join(company.get('states_licensed', [])),
                                'Total_Licenses': company.get('total_licenses', 0),
                                'Active_Licenses': company.get('active_licenses', 0),
                                'Personal_License_Count': len(personal_licenses),
                                'Mortgage_License_Count': len(mortgage_licenses),
                                'Personal_Licenses': '; '.join(personal_licenses),
                                'Mortgage_Licenses': '; '.join(mortgage_licenses),
                                'All_License_Types': '; '.join(license_types),
                                'Street_Address': company.get('street_address', ''),
                                'Mailing_Address': company.get('mailing_address', '')
                            })
                        
                        selected_df = pd.DataFrame(selected_df_data)
                        selected_csv = selected_df.to_csv(index=False).encode('utf-8')
                        
                        st.download_button(
                            label="📥 Export Selected",
                            data=selected_csv,
                            file_name=f"selected_lenders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            help="Download detailed analysis of selected companies"
                        )
            
            # Summary table (always show)
            st.markdown("---")
            st.markdown("### 📊 Summary Table")
            
            # Create display data
            display_data = []
            for company in companies:
                states_licensed = company.get('states_licensed', [])
                states_str = ', '.join(sorted(states_licensed)) if states_licensed else 'Unknown'
                if len(states_str) > 50:
                    states_str = states_str[:47] + '...'
                
                license_types = company.get('license_types', []) or []
                lender_type = company.get('lender_type', 'unknown')
                
                # Count license categories
                personal_count = len([lt for lt in license_types if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES])
                mortgage_count = len([lt for lt in license_types if lt in LenderClassifier.MORTGAGE_LICENSES])
                
                display_data.append({
                    'NMLS ID': company['nmls_id'],
                    'Company Name': company['company_name'],
                    'Lender Type': format_lender_type(lender_type, license_types),
                    'Business Score': f"{company.get('business_score', 0):.1f}",
                    'Personal Licenses': personal_count,
                    'Mortgage Licenses': mortgage_count,
                    'Total Licenses': company.get('total_licenses', 0),
                    'States Licensed': states_str,
                    'Total States': len(states_licensed),
                    'Contact Info': '✅' if (company.get('phone') and company.get('email')) else '📧' if company.get('email') else '📞' if company.get('phone') else '❌'
                })
            
            df = pd.DataFrame(display_data)
            st.dataframe(df, use_container_width=True, height=400)
            
            # Export all functionality
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export All Results",
                data=csv,
                file_name=f"lenders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv")
        else:
            st.info("🔍 No companies match your filters. Try adjusting the filters above.")


if __name__ == "__main__":
    main() 
