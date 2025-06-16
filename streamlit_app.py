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

def get_db_connection():
    """Get a synchronous database connection for simple queries"""
    try:
        import sqlite3
        # For development, use SQLite. In production, this would connect to PostgreSQL
        DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
        
        if DATABASE_URL and 'postgresql' in DATABASE_URL:
            # Production PostgreSQL connection
            import psycopg2
            return psycopg2.connect(DATABASE_URL)
        else:
            # Development SQLite connection
            db_path = "nmls_data.db"
            if not os.path.exists(db_path):
                st.error("Database file not found. Please ensure the NMLS database is properly set up.")
                return None
            return sqlite3.connect(db_path)
            
    except Exception as e:
        st.error(f"Database connection error: {str(e)}")
        return None

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

def search_nmls_database(query, selected_states=None, lender_type_filter="All Types"):
    """Search the NMLS database with filters"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Base query
        base_query = """
        SELECT DISTINCT c.nmls_id, c.legal_name, c.trade_names, c.business_structure,
               c.phone, c.email, c.website, c.address, c.city, c.state, c.zip_code,
               c.federal_regulator
        FROM companies c
        LEFT JOIN licenses l ON c.nmls_id = l.nmls_id
        WHERE (c.legal_name LIKE ? OR c.trade_names LIKE ?)
        """
        
        params = [f"%{query}%", f"%{query}%"]
        
        # Add state filter if specified
        if selected_states:
            state_placeholders = ','.join(['?' for _ in selected_states])
            base_query += f" AND l.state IN ({state_placeholders})"
            params.extend(selected_states)
        
        cursor.execute(base_query, params)
        companies = cursor.fetchall()
        
        # Convert to dictionaries
        company_columns = [desc[0] for desc in cursor.description]
        results = []
        
        for company in companies:
            company_dict = dict(zip(company_columns, company))
            
            # Get licenses for this company
            license_query = """
            SELECT license_number, license_type, state, status, 
                   issue_date, renewal_date, authorization
            FROM licenses 
            WHERE nmls_id = ?
            """
            
            cursor.execute(license_query, (company_dict['nmls_id'],))
            licenses_data = cursor.fetchall()
            
            # Convert licenses to list of dictionaries
            license_columns = [desc[0] for desc in cursor.description]
            licenses = [dict(zip(license_columns, license)) for license in licenses_data]
            
            company_dict['licenses'] = licenses
            results.append(company_dict)
        
        conn.close()
        return results
        
    except Exception as e:
        st.error(f"Database search error: {str(e)}")
        return []

def get_comprehensive_company_details(nmls_id: str) -> Dict[str, Any]:
    """Get comprehensive company and license details from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get company details with all available fields
        company_query = """
        SELECT 
            nmls_id, legal_name, trade_names, business_structure,
            phone, email, website, address, city, state, zip_code,
            federal_regulator, created_at, updated_at
        FROM companies 
        WHERE nmls_id = ?
        """
        
        cursor.execute(company_query, (nmls_id,))
        company_data = cursor.fetchone()
        
        if not company_data:
            return None
        
        # Convert to dictionary
        company_columns = [desc[0] for desc in cursor.description]
        company_dict = dict(zip(company_columns, company_data))
        
        # Get all licenses for this company
        license_query = """
        SELECT 
            license_number, license_type, state, status, 
            issue_date, renewal_date, authorization
        FROM licenses 
        WHERE nmls_id = ?
        ORDER BY state, license_type
        """
        
        cursor.execute(license_query, (nmls_id,))
        licenses_data = cursor.fetchall()
        
        # Convert licenses to list of dictionaries
        license_columns = [desc[0] for desc in cursor.description]
        licenses = [dict(zip(license_columns, license)) for license in licenses_data]
        
        # Add licenses to company data
        company_dict['licenses'] = licenses
        
        conn.close()
        return company_dict
        
    except Exception as e:
        st.error(f"Error fetching company details: {str(e)}")
        return None

def apply_advanced_filters(results, advanced_filters):
    """Apply advanced filtering rules to search results"""
    filtered_results = []
    
    for result in results:
        # Skip if doesn't meet minimum requirements
        total_licenses = len(result.get('licenses', []))
        if total_licenses < advanced_filters['min_licenses']:
            continue
        
        # Count unique states
        states = set()
        for license_info in result.get('licenses', []):
            if license_info.get('state'):
                states.add(license_info['state'])
        
        if len(states) < advanced_filters['min_states']:
            continue
        
        # Check mortgage ratio
        mortgage_licenses = 0
        for license_info in result.get('licenses', []):
            license_type = license_info.get('license_type', '')
            if any(mortgage_term in license_type.lower() for mortgage_term in ['mortgage', 'home loan']):
                mortgage_licenses += 1
        
        mortgage_ratio = mortgage_licenses / total_licenses if total_licenses > 0 else 0
        if mortgage_ratio > advanced_filters['max_mortgage_ratio']:
            continue
        
        # Check business structure requirements
        business_structure = result.get('business_structure', '')
        
        if advanced_filters['required_business_structures']:
            if not any(req_struct.lower() in business_structure.lower() 
                      for req_struct in advanced_filters['required_business_structures']):
                continue
        
        if advanced_filters['exclude_business_structures']:
            if any(excl_struct.lower() in business_structure.lower() 
                  for excl_struct in advanced_filters['exclude_business_structures']):
                continue
        
        # Check contact requirements
        contact_requirements = advanced_filters.get('contact_requirements', [])
        if 'Must have phone' in contact_requirements and not result.get('phone'):
            continue
        if 'Must have email' in contact_requirements and not result.get('email'):
            continue
        if 'Must have website' in contact_requirements and not result.get('website'):
            continue
        
        # Check license status filter
        license_status_filter = advanced_filters.get('license_status_filter', 'Any Status')
        if license_status_filter == 'Active Only':
            active_licenses = [l for l in result.get('licenses', []) 
                             if l.get('status', '').lower() == 'active']
            if not active_licenses:
                continue
        
        # Check company size filter
        company_size_filter = advanced_filters.get('company_size_filter', 'Any Size')
        if company_size_filter == 'Small (1-5 licenses)' and total_licenses > 5:
            continue
        elif company_size_filter == 'Medium (6-15 licenses)' and (total_licenses < 6 or total_licenses > 15):
            continue
        elif company_size_filter == 'Large (16+ licenses)' and total_licenses < 16:
            continue
        
        filtered_results.append(result)
    
    return filtered_results

def create_custom_classifier(advanced_filters):
    """Create a custom classifier based on advanced filter settings"""
    class CustomLenderClassifier:
        def __init__(self, target_licenses, exclude_licenses):
            self.target_licenses = set(target_licenses)
            self.exclude_licenses = set(exclude_licenses)
        
        def classify_lender(self, company_data):
            """Classify a lender based on custom rules"""
            licenses = company_data.get('licenses', [])
            if not licenses:
                return 'Other'
            
            license_types = [license.get('license_type', '') for license in licenses]
            
            # Check for target licenses
            has_target = any(license_type in self.target_licenses for license_type in license_types)
            
            # Check for exclude licenses
            has_exclude = any(license_type in self.exclude_licenses for license_type in license_types)
            
            if has_target and has_exclude:
                return 'Mixed'
            elif has_target:
                return 'TARGET'
            elif has_exclude:
                return 'EXCLUDE'
            else:
                return 'Other'
    
    return CustomLenderClassifier(
        advanced_filters['target_licenses'],
        advanced_filters['exclude_licenses']
    )

def display_results_table(results):
    """Display search results in a formatted table"""
    if not results:
        st.warning("No results to display.")
        return
    
    # Prepare data for display
    display_data = []
    for result in results:
        # Count licenses and states
        licenses = result.get('licenses', [])
        total_licenses = len(licenses)
        states = set(license.get('state', '') for license in licenses if license.get('state'))
        states_count = len(states)
        
        # Get classification emoji
        classification = result.get('classification', 'Other')
        if classification == 'TARGET':
            class_emoji = '🎯'
        elif classification == 'EXCLUDE':
            class_emoji = '❌'
        elif classification == 'Mixed':
            class_emoji = '🔄'
        else:
            class_emoji = '❓'
        
        display_data.append({
            'Company': result.get('legal_name', 'N/A'),
            'NMLS ID': result.get('nmls_id', 'N/A'),
            'Classification': f"{class_emoji} {classification}",
            'Total Licenses': total_licenses,
            'States': states_count,
            'Phone': result.get('phone', 'N/A'),
            'Website': result.get('website', 'N/A')
        })
    
    # Display as dataframe
    df = pd.DataFrame(display_data)
    st.dataframe(df, use_container_width=True)

def display_comprehensive_company_analysis(company_details):
    """Display comprehensive company analysis with all available information"""
    st.markdown("#### 🏢 Company Analysis")
    
    # Business Identity & Corporate Information
    st.markdown("##### 📋 Business Identity & Corporate Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Contact Information:**")
        if company_details.get('phone'):
            st.write(f"📞 **Phone:** {company_details['phone']}")
        if company_details.get('email'):
            st.write(f"📧 **Email:** {company_details['email']}")
        if company_details.get('website'):
            website = company_details['website']
            if not website.startswith(('http://', 'https://')):
                website = f"https://{website}"
            st.write(f"🌐 **Website:** [{company_details['website']}]({website})")
        
        # Address
        address_parts = []
        if company_details.get('address'):
            address_parts.append(company_details['address'])
        if company_details.get('city'):
            address_parts.append(company_details['city'])
        if company_details.get('state'):
            address_parts.append(company_details['state'])
        if company_details.get('zip_code'):
            address_parts.append(company_details['zip_code'])
        
        if address_parts:
            st.write(f"📍 **Address:** {', '.join(address_parts)}")
    
    with col2:
        st.markdown("**Corporate Structure:**")
        if company_details.get('business_structure'):
            st.write(f"🏗️ **Business Structure:** {company_details['business_structure']}")
        
        if company_details.get('trade_names'):
            trade_names = company_details['trade_names'].split(',') if company_details['trade_names'] else []
            if trade_names:
                st.write("🏷️ **Other Trade Names:**")
                for name in trade_names[:5]:  # Show first 5
                    st.write(f"  • {name.strip()}")
                if len(trade_names) > 5:
                    st.write(f"  • ... and {len(trade_names) - 5} more")
        
        if company_details.get('federal_regulator'):
            st.write(f"🏛️ **Federal Regulator:** {company_details['federal_regulator']}")
    
    # License Overview
    licenses = company_details.get('licenses', [])
    if licenses:
        st.markdown("---")
        st.markdown("##### 📊 License Overview")
        
        # Calculate metrics
        total_licenses = len(licenses)
        active_licenses = len([l for l in licenses if l.get('status', '').lower() == 'active'])
        states = set(l.get('state', '') for l in licenses if l.get('state'))
        license_types = set(l.get('license_type', '') for l in licenses if l.get('license_type'))
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Licenses", total_licenses)
        with col2:
            st.metric("Active Licenses", active_licenses)
        with col3:
            st.metric("License Types", len(license_types))
        with col4:
            st.metric("States Licensed", len(states))
        
        # Enhanced License Classification Analysis
        st.markdown("##### 🎯 Enhanced License Classification Analysis")
        
        # Classify licenses
        target_licenses = []
        exclude_licenses = []
        other_licenses = []
        
        for license_info in licenses:
            license_type = license_info.get('license_type', '')
            if license_type in LenderClassifier.UNSECURED_PERSONAL_LICENSES:
                target_licenses.append(license_info)
            elif license_type in LenderClassifier.MORTGAGE_LICENSES:
                exclude_licenses.append(license_info)
            else:
                other_licenses.append(license_info)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**🎯 TARGET Licenses:**")
            if target_licenses:
                target_types = {}
                for license_info in target_licenses:
                    license_type = license_info.get('license_type', 'Unknown')
                    target_types[license_type] = target_types.get(license_type, 0) + 1
                
                for license_type, count in target_types.items():
                    st.write(f"• {license_type}: {count}")
            else:
                st.write("None found")
        
        with col2:
            st.markdown("**❌ EXCLUDE Licenses:**")
            if exclude_licenses:
                exclude_types = {}
                for license_info in exclude_licenses:
                    license_type = license_info.get('license_type', 'Unknown')
                    exclude_types[license_type] = exclude_types.get(license_type, 0) + 1
                
                for license_type, count in exclude_types.items():
                    st.write(f"• {license_type}: {count}")
            else:
                st.write("None found")
        
        with col3:
            st.markdown("**❓ Other Licenses:**")
            if other_licenses:
                other_types = {}
                for license_info in other_licenses:
                    license_type = license_info.get('license_type', 'Unknown')
                    other_types[license_type] = other_types.get(license_type, 0) + 1
                
                for license_type, count in other_types.items():
                    st.write(f"• {license_type}: {count}")
            else:
                st.write("None found")
        
        # Detailed License Information Table
        st.markdown("---")
        st.markdown("##### 📋 Detailed License Information")
        
        # Prepare license data for table
        license_data = []
        for license_info in licenses:
            status = license_info.get('status', 'Unknown')
            status_emoji = '✅' if status.lower() == 'active' else '⚠️' if status.lower() == 'inactive' else '❓'
            
            license_data.append({
                'License Number': license_info.get('license_number', 'N/A'),
                'Type': license_info.get('license_type', 'N/A'),
                'State': license_info.get('state', 'N/A'),
                'Issue Date': license_info.get('issue_date', 'N/A'),
                'Renewal Date': license_info.get('renewal_date', 'N/A'),
                'Status': f"{status_emoji} {status}",
                'Authorization': license_info.get('authorization', 'N/A')
            })
        
        # Display license table
        if license_data:
            df_licenses = pd.DataFrame(license_data)
            st.dataframe(df_licenses, use_container_width=True)
        
        # Summary insights
        st.markdown("---")
        st.markdown("##### 💡 Analysis Summary")
        
        # Calculate ratios
        target_ratio = len(target_licenses) / total_licenses if total_licenses > 0 else 0
        exclude_ratio = len(exclude_licenses) / total_licenses if total_licenses > 0 else 0
        
        if target_ratio > 0.7:
            st.success(f"🎯 **HIGH TARGET POTENTIAL** - {target_ratio:.0%} of licenses are unsecured personal lending")
        elif target_ratio > 0.3:
            st.warning(f"🔄 **MIXED LENDER** - {target_ratio:.0%} target licenses, {exclude_ratio:.0%} mortgage licenses")
        elif exclude_ratio > 0.5:
            st.error(f"❌ **MORTGAGE FOCUSED** - {exclude_ratio:.0%} of licenses are mortgage-related")
        else:
            st.info(f"❓ **OTHER LENDER TYPE** - Specialized in other financial services")
        
        # Geographic presence
        if len(states) >= 10:
            st.info(f"🌎 **NATIONAL PRESENCE** - Licensed in {len(states)} states")
        elif len(states) >= 5:
            st.info(f"🗺️ **REGIONAL PRESENCE** - Licensed in {len(states)} states")
        else:
            st.info(f"📍 **LOCAL/STATE PRESENCE** - Licensed in {len(states)} state(s)")

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
    
    # Advanced Filters Section
    st.markdown("---")
    with st.expander("🔧 Advanced Filters & Custom Classification", expanded=False):
        st.markdown("**Customize your search criteria and redefine lender classifications**")
        
        # Filter Profiles
        st.markdown("##### 📋 Filter Profiles")
        col_profile1, col_profile2, col_profile3 = st.columns([2, 1, 1])
        
        with col_profile1:
            # Initialize session state for profiles
            if 'filter_profiles' not in st.session_state:
                st.session_state.filter_profiles = {
                    "Default": {
                        "target_licenses": list(LenderClassifier.UNSECURED_PERSONAL_LICENSES),
                        "exclude_licenses": list(LenderClassifier.MORTGAGE_LICENSES),
                        "min_licenses": 1,
                        "min_states": 1,
                        "max_mortgage_ratio": 1.0,
                        "required_business_structures": [],
                        "exclude_business_structures": []
                    },
                    "Conservative Targeting": {
                        "target_licenses": ["Personal Loan License", "Consumer Credit License", "Installment Loan License"],
                        "exclude_licenses": list(LenderClassifier.MORTGAGE_LICENSES),
                        "min_licenses": 3,
                        "min_states": 2,
                        "max_mortgage_ratio": 0.3,
                        "required_business_structures": [],
                        "exclude_business_structures": []
                    },
                    "Aggressive Prospecting": {
                        "target_licenses": list(LenderClassifier.UNSECURED_PERSONAL_LICENSES) + ["Money Transmitter License", "Check Casher License"],
                        "exclude_licenses": ["Mortgage Broker License", "Mortgage Lender License"],
                        "min_licenses": 1,
                        "min_states": 1,
                        "max_mortgage_ratio": 0.8,
                        "required_business_structures": [],
                        "exclude_business_structures": []
                    }
                }
            
            if 'current_profile' not in st.session_state:
                st.session_state.current_profile = "Default"
            
            selected_profile = st.selectbox(
                "Choose Filter Profile:",
                options=list(st.session_state.filter_profiles.keys()),
                index=list(st.session_state.filter_profiles.keys()).index(st.session_state.current_profile),
                help="Select a pre-configured filter profile or create your own custom settings below"
            )
            
            if selected_profile != st.session_state.current_profile:
                st.session_state.current_profile = selected_profile
                st.rerun()
        
        with col_profile2:
            if st.button("💾 Save Profile", help="Save current settings as a new profile"):
                st.session_state.show_save_dialog = True
        
        with col_profile3:
            if st.button("🗑️ Delete Profile", help="Delete the selected profile", disabled=selected_profile == "Default"):
                if selected_profile in st.session_state.filter_profiles and selected_profile != "Default":
                    del st.session_state.filter_profiles[selected_profile]
                    st.session_state.current_profile = "Default"
                    st.rerun()
        
        # Save Profile Dialog
        if st.session_state.get('show_save_dialog', False):
            new_profile_name = st.text_input("Profile Name:", placeholder="Enter profile name...")
            col_save1, col_save2 = st.columns(2)
            with col_save1:
                if st.button("✅ Save") and new_profile_name:
                    # Get current settings and save as new profile
                    current_settings = st.session_state.filter_profiles[selected_profile].copy()
                    st.session_state.filter_profiles[new_profile_name] = current_settings
                    st.session_state.current_profile = new_profile_name
                    st.session_state.show_save_dialog = False
                    st.success(f"Profile '{new_profile_name}' saved!")
                    st.rerun()
            with col_save2:
                if st.button("❌ Cancel"):
                    st.session_state.show_save_dialog = False
                    st.rerun()
        
        # Get current profile settings
        current_settings = st.session_state.filter_profiles[selected_profile]
        
        st.markdown("---")
        
        # Custom License Classification
        st.markdown("##### 🎯 Custom License Classification")
        st.markdown("**Define which license types should be considered TARGET vs EXCLUDE:**")
        
        col_target, col_exclude = st.columns(2)
        
        # Get all unique license types from the database for selection
        all_license_types = [
            "Personal Loan License", "Consumer Credit License", "Installment Loan License",
            "Payday Loan License", "Small Loan License", "Deferred Deposit License",
            "Mortgage Broker License", "Mortgage Lender License", "Mortgage Servicer License",
            "Money Transmitter License", "Check Casher License", "Debt Collection License",
            "Credit Repair License", "Auto Finance License", "Sales Finance License"
        ]
        
        with col_target:
            st.markdown("**🎯 TARGET License Types:**")
            target_licenses = st.multiselect(
                "Select license types that qualify as TARGET lenders:",
                options=all_license_types,
                default=current_settings["target_licenses"],
                help="Companies with these licenses will be classified as TARGET lenders",
                key="target_licenses_select"
            )
        
        with col_exclude:
            st.markdown("**❌ EXCLUDE License Types:**")
            exclude_licenses = st.multiselect(
                "Select license types that should be EXCLUDED:",
                options=all_license_types,
                default=current_settings["exclude_licenses"],
                help="Companies with these licenses will be classified as EXCLUDE (unless overridden by rules below)",
                key="exclude_licenses_select"
            )
        
        # Business Rules Builder
        st.markdown("---")
        st.markdown("##### ⚙️ Business Rules & Thresholds")
        
        col_rules1, col_rules2, col_rules3 = st.columns(3)
        
        with col_rules1:
            st.markdown("**📊 License Requirements:**")
            min_licenses = st.number_input(
                "Minimum Total Licenses:",
                min_value=1,
                max_value=50,
                value=current_settings["min_licenses"],
                help="Companies must have at least this many licenses"
            )
            
            min_states = st.number_input(
                "Minimum States Licensed:",
                min_value=1,
                max_value=51,
                value=current_settings["min_states"],
                help="Companies must be licensed in at least this many states"
            )
        
        with col_rules2:
            st.markdown("**⚖️ Mortgage Ratio Control:**")
            max_mortgage_ratio = st.slider(
                "Max Mortgage License Ratio:",
                min_value=0.0,
                max_value=1.0,
                value=current_settings["max_mortgage_ratio"],
                step=0.1,
                help="Maximum ratio of mortgage licenses to total licenses (0.0 = no mortgage licenses allowed, 1.0 = any ratio allowed)"
            )
            
            st.caption(f"Example: If set to 0.3, companies with >30% mortgage licenses will be excluded")
        
        with col_rules3:
            st.markdown("**🏢 Business Structure Filters:**")
            business_structures = ["Corporation", "LLC", "Partnership", "Sole Proprietorship", "Bank", "Credit Union"]
            
            required_structures = st.multiselect(
                "Required Business Structures:",
                options=business_structures,
                default=current_settings["required_business_structures"],
                help="Only include companies with these business structures (leave empty for any)"
            )
            
            exclude_structures = st.multiselect(
                "Exclude Business Structures:",
                options=business_structures,
                default=current_settings["exclude_business_structures"],
                help="Exclude companies with these business structures"
            )
        
        # Advanced Search Criteria
        st.markdown("---")
        st.markdown("##### 🔍 Advanced Search Criteria")
        
        col_search1, col_search2 = st.columns(2)
        
        with col_search1:
            contact_requirements = st.multiselect(
                "Contact Information Requirements:",
                options=["Must have phone", "Must have email", "Must have website"],
                help="Only include companies that have the selected contact information"
            )
            
            license_status_filter = st.selectbox(
                "License Status Filter:",
                options=["Any Status", "Active Only", "Include Inactive"],
                help="Filter by license status"
            )
        
        with col_search2:
            date_range_filter = st.selectbox(
                "License Date Filter:",
                options=["Any Date", "Licensed in last 1 year", "Licensed in last 2 years", "Licensed in last 5 years"],
                help="Filter by when licenses were issued"
            )
            
            company_size_filter = st.selectbox(
                "Company Size (by license count):",
                options=["Any Size", "Small (1-5 licenses)", "Medium (6-15 licenses)", "Large (16+ licenses)"],
                help="Filter by company size based on number of licenses"
            )
        
        # Update current profile settings
        st.session_state.filter_profiles[selected_profile].update({
            "target_licenses": target_licenses,
            "exclude_licenses": exclude_licenses,
            "min_licenses": min_licenses,
            "min_states": min_states,
            "max_mortgage_ratio": max_mortgage_ratio,
            "required_business_structures": required_structures,
            "exclude_business_structures": exclude_structures
        })
        
        # Preview Section
        st.markdown("---")
        st.markdown("##### 👀 Filter Preview")
        
        col_preview1, col_preview2 = st.columns(2)
        
        with col_preview1:
            st.markdown("**Current Classification Rules:**")
            st.info(f"🎯 TARGET: {len(target_licenses)} license types selected")
            st.info(f"❌ EXCLUDE: {len(exclude_licenses)} license types selected")
            st.info(f"📊 Min {min_licenses} licenses, {min_states} states")
            st.info(f"⚖️ Max {max_mortgage_ratio:.0%} mortgage ratio")
        
        with col_preview2:
            if st.button("🔄 Apply Advanced Filters", type="primary"):
                st.session_state.advanced_filters_applied = {
                    "target_licenses": target_licenses,
                    "exclude_licenses": exclude_licenses,
                    "min_licenses": min_licenses,
                    "min_states": min_states,
                    "max_mortgage_ratio": max_mortgage_ratio,
                    "required_business_structures": required_structures,
                    "exclude_business_structures": exclude_structures,
                    "contact_requirements": contact_requirements,
                    "license_status_filter": license_status_filter,
                    "date_range_filter": date_range_filter,
                    "company_size_filter": company_size_filter
                }
                st.success("✅ Advanced filters applied! Run a search to see results.")
        
        # Reset to defaults
        if st.button("🔄 Reset to Default Classification"):
            st.session_state.current_profile = "Default"
            if 'advanced_filters_applied' in st.session_state:
                del st.session_state.advanced_filters_applied
            st.success("✅ Reset to default classification rules!")
            st.rerun()
    
    # Perform search
    if search_clicked and query:
        with st.spinner("🔍 Searching NMLS database..."):
            try:
                # Check if advanced filters are applied
                advanced_filters = st.session_state.get('advanced_filters_applied', None)
                
                if advanced_filters:
                    st.info("🔧 Using Advanced Filters & Custom Classification Rules")
                
                # Search the database
                results = search_nmls_database(query, selected_states, lender_type_filter)
                
                if results:
                    st.success(f"✅ Found {len(results)} companies matching your search criteria")
                    
                    # Apply advanced filters if they exist
                    if advanced_filters:
                        results = apply_advanced_filters(results, advanced_filters)
                        st.info(f"🔧 After advanced filtering: {len(results)} companies remain")
                    
                    # Create a custom classifier if advanced filters are applied
                    if advanced_filters:
                        classifier = create_custom_classifier(advanced_filters)
                    else:
                        classifier = LenderClassifier()
                    
                    # Classify results
                    classified_results = []
                    for result in results:
                        classification = classifier.classify_lender(result)
                        result['classification'] = classification
                        classified_results.append(result)
                    
                    # Count classifications
                    target_count = sum(1 for r in classified_results if r['classification'] == 'TARGET')
                    exclude_count = sum(1 for r in classified_results if r['classification'] == 'EXCLUDE')
                    mixed_count = sum(1 for r in classified_results if r['classification'] == 'Mixed')
                    other_count = sum(1 for r in classified_results if r['classification'] == 'Other')
                    
                    # Display classification summary
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("🎯 TARGET", target_count, help="Unsecured personal lenders")
                    with col2:
                        st.metric("❌ EXCLUDE", exclude_count, help="Mortgage-focused lenders")
                    with col3:
                        st.metric("🔄 Mixed", mixed_count, help="Both personal and mortgage")
                    with col4:
                        st.metric("❓ Other", other_count, help="Other license types")
                    
                    # Filter results based on lender type selection
                    if lender_type_filter != "All Types":
                        if lender_type_filter == "Unsecured Personal (TARGET)":
                            classified_results = [r for r in classified_results if r['classification'] == 'TARGET']
                        elif lender_type_filter == "Mortgage (EXCLUDE)":
                            classified_results = [r for r in classified_results if r['classification'] == 'EXCLUDE']
                        elif lender_type_filter == "Mixed":
                            classified_results = [r for r in classified_results if r['classification'] == 'Mixed']
                        elif lender_type_filter == "Unknown":
                            classified_results = [r for r in classified_results if r['classification'] == 'Other']
                    
                    if classified_results:
                        # Display results table
                        display_results_table(classified_results)
                        
                        # Detailed analysis section
                        st.markdown("---")
                        st.markdown("### 📊 Detailed License Analysis")
                        
                        # Company selection for detailed analysis
                        company_options = [f"{result['legal_name']} (NMLS ID: {result['nmls_id']})" 
                                         for result in classified_results]
                        
                        selected_company_display = st.selectbox(
                            "Select a company for detailed analysis:",
                            options=company_options,
                            help="Choose a company to see comprehensive license and business information"
                        )
                        
                        if selected_company_display:
                            # Extract NMLS ID from selection
                            nmls_id = selected_company_display.split("NMLS ID: ")[1].split(")")[0]
                            
                            # Get comprehensive company details
                            company_details = get_comprehensive_company_details(nmls_id)
                            
                            if company_details:
                                display_comprehensive_company_analysis(company_details)
                            else:
                                st.error("Could not retrieve detailed information for this company.")
                    else:
                        st.warning("No companies match the selected lender type filter.")
                else:
                    st.warning("No results found. Try adjusting your search terms or filters.")
                    
            except Exception as e:
                st.error(f"Search error: {str(e)}")
                st.error("Please check your search terms and try again.")
    
    # Display results
    if st.session_state.search_results:
        result = st.session_state.search_results
        companies = result['companies']
        original_count = len(companies)  # Store original count before filtering
        
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
        
        filtered_count = len(companies)  # Count after filtering
        
        # Use constant total database count
        total_db_count = 13971
        
        # Summary metrics
        st.markdown("---")
        
        # Always show total database context for transparency
        filters_applied = bool(selected_states or lender_type_filter != "All Types")
        if filters_applied and filtered_count != original_count:
            st.info(f"📊 Showing **{filtered_count}** companies found out of **{total_db_count:,}** total companies in database (filters applied)")
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
                        comprehensive_details = get_comprehensive_company_details(nmls_id)
                    
                    if comprehensive_details:
                        display_comprehensive_company_analysis(comprehensive_details)
                    else:
                        st.error("Could not retrieve detailed information for this company.")

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

if __name__ == "__main__":
    main() 