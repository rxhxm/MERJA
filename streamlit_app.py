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
    from search_api import SearchFilters, db_manager, SearchService, SortField, SortOrder
    from enrichment_service import create_enrichment_service, EnrichmentService
    import asyncpg
    import os
except ImportError as e:
    st.error(f"Failed to import required modules: {e}")
    st.stop()

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
            
    except Exception as e:
        logger.error(f"Async execution error: {e}")
        # Fallback: try with asyncio.run
        try:
            return asyncio.run(coro)
        except Exception as e2:
            logger.error(f"Fallback async execution error: {e2}")
            raise e2

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
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Ronin320320.@db.eissjxpcsxcktoanftjw.supabase.co:5432/postgres')
        
        # Use a simple connection instead of a pool for Streamlit
        conn = await asyncpg.connect(DATABASE_URL)
        
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

# Main app
def main():
    # Header
    st.markdown('<h1 class="main-header">NMLS Search</h1>', unsafe_allow_html=True)
    
    # Show only natural language search page
    show_natural_search_page()

def show_natural_search_page():
    """Natural language search interface"""
    st.header("Natural Language Search")
    
    # Search interface
    col1, col2 = st.columns([3, 1])
    
    with col1:
        query = st.text_input(
            "Enter your search query in natural language:",
            value=st.session_state.last_query,
            placeholder="e.g., Find personal loan companies in California with phone numbers",
            key="nl_search_input"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)  # Spacing
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True)
    
    # Search options
    col1, col2, col3 = st.columns(3)
    with col1:
        apply_business_filters = st.checkbox("Apply Fido's Business Filters", value=True, help="Prioritize unsecured personal lenders with contact info")
    with col2:
        page_size = st.selectbox("Results per page", [10, 20, 50, 100], index=1)
    with col3:
        show_analysis = st.checkbox("Show Query Analysis", value=True, help="Display AI's understanding of your query")
    
    # Perform search
    if search_clicked and query:
        st.session_state.last_query = query
        with st.spinner("🤖 Analyzing query and searching database..."):
            try:
                result = run_async(run_natural_search(query, apply_business_filters, 1, page_size))
                if result:
                    st.session_state.search_results = result
                    st.session_state.selected_companies = []  # Reset selections
                else:
                    st.error("❌ Search returned no results. Please try a different query.")
            except Exception as e:
                st.error(f"❌ Search failed: {str(e)}")
                logger.error(f"Search error in UI: {e}")
                import traceback
                st.code(traceback.format_exc())
                st.info("💡 Try refreshing the page or using a simpler query.")
    
    # Display results
    if st.session_state.search_results:
        result = st.session_state.search_results
        
        # Query analysis
        if show_analysis:
            with st.expander("🧠 AI Query Analysis", expanded=True):
                analysis = result['query_analysis']
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Intent", analysis['intent'].replace('_', ' ').title())
                with col2:
                    st.metric("Confidence", f"{analysis['confidence']:.1%}")
                with col3:
                    st.metric("Total Results", result['pagination']['total_count'])
                with col4:
                    bi_data = result.get('business_intelligence', {})
                    high_value_targets = bi_data.get('high_value_targets', 0)
                    st.metric("High-Value Targets", high_value_targets)
                
                st.markdown(f"**Explanation:** {analysis['explanation']}")
                
                if analysis['business_critical_flags']:
                    st.warning(f"⚠️ Business Flags: {', '.join(analysis['business_critical_flags'])}")
        
        # Business intelligence summary
        with st.expander("📊 Search Results Intelligence", expanded=True):
            bi = result.get('business_intelligence', {})
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**Lender Type Distribution**")
                lender_types = bi.get('lender_type_distribution', {})
                total = bi.get('total', 0)
                if lender_types and total > 0:
                    for lender_type, count in lender_types.items():
                        percentage = (count / total) * 100
                        if lender_type == 'unsecured_personal':
                            st.write(f"✅ **Target**: {count} ({percentage:.1f}%)")
                        elif lender_type == 'mixed':
                            st.write(f"⚠️ **Mixed**: {count} ({percentage:.1f}%)")
                        elif lender_type == 'mortgage':
                            st.write(f"❌ **Exclude**: {count} ({percentage:.1f}%)")
                        else:
                            st.write(f"❓ **Unknown**: {count} ({percentage:.1f}%)")
                else:
                    st.write("No lender type data available")
            
            with col2:
                st.markdown("**Contact Coverage**")
                contact_stats = bi.get('contact_statistics', {})
                total_contact = sum(contact_stats.values()) if contact_stats else 0
                if contact_stats and total_contact > 0:
                    for stat, count in contact_stats.items():
                        percentage = (count / total_contact) * 100
                        if stat == 'valid_contact':
                            st.write(f"✅ **Both**: {count} ({percentage:.1f}%)")
                        elif stat == 'email_only':
                            st.write(f"📧 **Email Only**: {count} ({percentage:.1f}%)")
                        elif stat == 'phone_only':
                            st.write(f"📞 **Phone Only**: {count} ({percentage:.1f}%)")
                        else:
                            st.write(f"❌ **No Contact**: {count} ({percentage:.1f}%)")
                else:
                    st.write("No contact data available")
            
            with col3:
                st.markdown("**Quality Indicators**")
                high_score_count = sum(1 for c in result.get('companies', []) if c.get('business_score', 0) >= 80)
                medium_score_count = sum(1 for c in result.get('companies', []) if 50 <= c.get('business_score', 0) < 80)
                low_score_count = sum(1 for c in result.get('companies', []) if c.get('business_score', 0) < 50)
                
                displayed_total = len(result.get('companies', []))
                if displayed_total > 0:
                    st.write(f"🔥 **High Score (80+)**: {high_score_count}")
                    st.write(f"⚡ **Medium Score (50-79)**: {medium_score_count}")  
                    st.write(f"⚠️ **Low Score (<50)**: {low_score_count}")
                    st.write(f"📊 **Showing**: {displayed_total} of {total}")
                
                recommendations = bi.get('business_recommendations', [])
                if recommendations:
                    st.markdown("**Key Recommendations**")
                    for rec in recommendations[:2]:  # Show top 2
                        st.write(f"• {rec}")
        
        # Results table with enrichment options
        st.subheader(f"📋 Search Results ({result['pagination']['total_count']} total)")
        
        if result['companies']:
            # Enrichment controls
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown("**🚀 Enrichment Options**")
            with col2:
                enrich_selected = st.button("🔍 Enrich Selected Companies", disabled=len(st.session_state.selected_companies) == 0)
            with col3:
                enrich_all = st.button("📊 Enrich All Results", disabled=len(result['companies']) == 0)
            
            # Company selection and display
            companies_data = []
            for i, company in enumerate(result['companies']):
                # Add checkbox for selection
                is_selected = st.checkbox(
                    f"Select {company['company_name'][:30]}...",
                    key=f"company_select_{company['nmls_id']}",
                    value=company['nmls_id'] in st.session_state.selected_companies
                )
                
                if is_selected and company['nmls_id'] not in st.session_state.selected_companies:
                    st.session_state.selected_companies.append(company['nmls_id'])
                elif not is_selected and company['nmls_id'] in st.session_state.selected_companies:
                    st.session_state.selected_companies.remove(company['nmls_id'])
                
                companies_data.append({
                    'NMLS ID': company['nmls_id'],
                    'Company Name': company['company_name'],
                    'Lender Type': format_lender_type(company.get('lender_type', 'unknown')),
                    'Business Score': format_business_score(company.get('business_score', 0)),
                    'Phone': '✅' if company.get('phone') else '❌',
                    'Email': '✅' if company.get('email') else '❌',
                    'Website': '✅' if company.get('website') else '❌',
                    'Total Licenses': company.get('total_licenses', 0),
                    'States': len(company.get('states_licensed', [])),
                    'Business Structure': company.get('business_structure', 'N/A')
                })
            
            df = pd.DataFrame(companies_data)
            st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)
            
            # Handle enrichment
            if enrich_selected or enrich_all:
                companies_to_enrich = []
                
                if enrich_selected:
                    companies_to_enrich = [c for c in result['companies'] if c['nmls_id'] in st.session_state.selected_companies]
                    st.info(f"🚀 Enriching {len(companies_to_enrich)} selected companies...")
                elif enrich_all:
                    companies_to_enrich = result['companies']
                    st.info(f"🚀 Enriching all {len(companies_to_enrich)} companies...")
                
                # Perform enrichment
                enrichment_service = create_enrichment_service()
                if enrichment_service:
                    with st.spinner("🔍 Enriching companies with SixtyFour API..."):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def update_progress(completed, total):
                            progress = completed / total
                            progress_bar.progress(progress)
                            status_text.text(f"Processed {completed}/{total} companies...")
                        
                        try:
                            enriched_df, contacts_df = run_async(
                                enrichment_service.enrich_companies_batch(
                                    companies_to_enrich, 
                                    update_progress
                                )
                            )
                            
                            st.session_state.enriched_results = {
                                'companies': enriched_df,
                                'contacts': contacts_df,
                                'timestamp': datetime.now().isoformat()
                            }
                            
                            progress_bar.progress(1.0)
                            status_text.text("✅ Enrichment complete!")
                            st.success(f"🎉 Successfully enriched {len(enriched_df)} companies and found {len(contacts_df)} contacts!")
                            
                        except Exception as e:
                            st.error(f"❌ Enrichment failed: {str(e)}")
                            logger.error(f"Enrichment error: {e}")
                else:
                    st.error("❌ Enrichment service not available. Please check your SixtyFour API key.")
            
            # Pagination
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                current_page = result['pagination']['page']
                total_pages = result['pagination']['total_pages']
                st.write(f"Page {current_page} of {total_pages}")
        else:
            st.info("No companies found matching your search criteria.")
    
    # Display enrichment results
    if st.session_state.enriched_results:
        st.markdown("---")
        st.header("🔍 Enrichment Results")
        
        enriched_data = st.session_state.enriched_results
        enriched_companies = enriched_data['companies']
        contacts = enriched_data['contacts']
        
        # Enrichment summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Companies Enriched", len(enriched_companies))
        with col2:
            successful_enrichments = len(enriched_companies[enriched_companies['enrichment_status'] == 'Success'])
            st.metric("Successful", successful_enrichments)
        with col3:
            qualified_leads = len(enriched_companies[enriched_companies.get('is_qualified_lead', False) == True])
            st.metric("Qualified Leads", qualified_leads)
        with col4:
            st.metric("Contacts Found", len(contacts))
        
        # Enriched companies table
        st.subheader("📊 Enriched Companies")
        if not enriched_companies.empty:
            # Create display dataframe
            display_cols = [
                'company_name', 'enrichment_status', 'enrichment_confidence', 
                'enriched_specializes_in_personal_loans', 'enriched_icp_match',
                'enrichment_quality_score', 'is_qualified_lead'
            ]
            
            display_df = enriched_companies[display_cols].copy()
            display_df.columns = [
                'Company Name', 'Status', 'Confidence', 'Personal Loan Focus', 
                'ICP Match', 'Quality Score', 'Qualified Lead'
            ]
            
            st.dataframe(display_df, use_container_width=True)
            
            # Download enriched data
            col1, col2 = st.columns(2)
            with col1:
                csv_companies = enriched_companies.to_csv(index=False)
                st.download_button(
                    "📥 Download Enriched Companies",
                    csv_companies,
                    f"enriched_companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv"
                )
            with col2:
                if not contacts.empty:
                    csv_contacts = contacts.to_csv(index=False)
                    st.download_button(
                        "📥 Download Contacts",
                        csv_contacts,
                        f"enriched_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        "text/csv"
                    )
        
        # Contacts table
        if not contacts.empty:
            st.subheader("👥 Decision Makers & Contacts")
            
            # Filter for decision makers
            decision_makers = contacts[contacts['is_decision_maker'].str.contains('yes', case=False, na=False)]
            
            if not decision_makers.empty:
                st.markdown("**🎯 Key Decision Makers**")
                dm_display = decision_makers[[
                    'company_name', 'contact_name', 'contact_title', 
                    'contact_email', 'contact_phone', 'contact_linkedin'
                ]].copy()
                dm_display.columns = [
                    'Company', 'Name', 'Title', 'Email', 'Phone', 'LinkedIn'
                ]
                st.dataframe(dm_display, use_container_width=True)
            
            # All contacts
            with st.expander("👥 All Contacts", expanded=False):
                contacts_display = contacts[[
                    'company_name', 'contact_name', 'contact_title',
                    'contact_email', 'contact_phone', 'is_decision_maker'
                ]].copy()
                contacts_display.columns = [
                    'Company', 'Name', 'Title', 'Email', 'Phone', 'Decision Maker'
                ]
                st.dataframe(contacts_display, use_container_width=True)

if __name__ == "__main__":
    main() 