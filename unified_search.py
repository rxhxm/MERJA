#!/usr/bin/env python3
"""
Unified NMLS Search System
Consolidates all search functionality into a single comprehensive module.

Features:
- Natural language processing with Claude AI
- Vector/semantic search with SentenceTransformers
- Traditional SQL-based search and filtering
- Business intelligence and lender classification
- Contact validation and scoring
- FastAPI endpoints for programmatic access
- Streamlit integration
"""

import os
import re
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from contextlib import asynccontextmanager

import httpx
import numpy as np
import asyncpg
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Try to import optional dependencies with fallbacks
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    logging.warning(
        "sentence_transformers not available - vector search will be disabled")

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
if STREAMLIT_AVAILABLE:
    try:
        ANTHROPIC_API_KEY = st.secrets.get(
            'ANTHROPIC_API_KEY', os.getenv(
                'ANTHROPIC_API_KEY', 'your-api-key-here'))
        DATABASE_URL = st.secrets.get(
            'DATABASE_URL', os.getenv('DATABASE_URL'))
        
        # Debug logging for Streamlit deployment
        if DATABASE_URL:
            logger.info(f"✅ DATABASE_URL loaded from secrets (length: {len(DATABASE_URL)})")
        else:
            logger.error("❌ DATABASE_URL not found in secrets or environment")
            # Try alternative secret names that might be used
            alt_names = ['DATABASE_URL', 'POSTGRES_URL', 'POSTGRESQL_URL', 'DB_URL']
            for name in alt_names:
                value = st.secrets.get(name) or os.getenv(name)
                if value:
                    DATABASE_URL = value
                    logger.info(f"✅ Found database URL using alternative name: {name}")
                    break
                    
    except Exception as e:
        # Fallback to environment variables if secrets not available
        logger.warning(f"Secrets access failed: {e}, falling back to environment variables")
        ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', 'your-api-key-here')
        DATABASE_URL = os.getenv('DATABASE_URL')
else:
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', 'your-api-key-here')
    DATABASE_URL = os.getenv('DATABASE_URL')

# Final check and logging
if not DATABASE_URL:
    logger.error("❌ CRITICAL: DATABASE_URL not configured anywhere!")
    DATABASE_URL = None  # Make it explicit
else:
    logger.info(f"✅ DATABASE_URL configured (starts with: {DATABASE_URL[:20]}...)")

claude_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# ============================================================================
# ENUMS AND DATA MODELS
# ============================================================================


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class SortField(str, Enum):
    company_name = "company_name"
    nmls_id = "nmls_id"
    business_structure = "business_structure"
    total_licenses = "total_licenses"
    created_at = "created_at"


class QueryIntent(str, Enum):
    FIND_LENDERS = "find_lenders"
    FIND_COMPANIES = "find_companies"
    FILTER_BY_LOCATION = "filter_by_location"
    FILTER_BY_LICENSES = "filter_by_licenses"
    FILTER_BY_CONTACT = "filter_by_contact"
    FIND_SPECIFIC_COMPANY = "find_specific_company"
    ANALYZE_MARKET = "analyze_market"


class LenderType(str, Enum):
    UNSECURED_PERSONAL = "unsecured_personal"  # TARGET: What Fido wants
    MORTGAGE = "mortgage"                      # EXCLUDE: Not wanted
    MIXED = "mixed"                           # REVIEW: Has both types
    UNKNOWN = "unknown"                       # INVESTIGATE: Unclear classification


class SearchFilters(BaseModel):
    # Text search
    query: Optional[str] = Field(
        None, description="Text search across company names, addresses, trade names")

    # Basic filters
    states: Optional[List[str]] = Field(
        None, description="Filter by states (e.g., ['CA', 'TX'])")
    license_types: Optional[List[str]] = Field(
        None, description="Filter by license types")
    business_structures: Optional[List[str]] = Field(
        None, description="Filter by business structures")

    # Boolean filters
    has_federal_registration: Optional[bool] = Field(
        None, description="Filter companies with federal registration")
    has_website: Optional[bool] = Field(
        None, description="Filter companies with websites")
    has_email: Optional[bool] = Field(
        None, description="Filter companies with email")
    active_licenses_only: Optional[bool] = Field(
        True, description="Show only active licenses")

    # Numeric filters
    min_licenses: Optional[int] = Field(
        None, description="Minimum number of licenses")
    max_licenses: Optional[int] = Field(
        None, description="Maximum number of licenses")

    # Date filters
    licensed_after: Optional[str] = Field(
        None, description="Filter licenses issued after date (YYYY-MM-DD)")
    licensed_before: Optional[str] = Field(
        None, description="Filter licenses issued before date (YYYY-MM-DD)")


class CompanyResponse(BaseModel):
    nmls_id: str
    company_name: str
    business_structure: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    street_address: Optional[str] = None
    mailing_address: Optional[str] = None
    total_licenses: int = 0
    active_licenses: int = 0
    license_types: List[str] = []
    states_licensed: List[str] = []
    federal_regulator: Optional[str] = None
    created_at: Optional[datetime] = None
    # Enhanced fields
    lender_type: Optional[str] = None
    has_valid_contact: Optional[bool] = None
    contact_issues: Optional[List[str]] = None
    business_score: Optional[float] = None


class SearchResponse(BaseModel):
    companies: List[CompanyResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: Dict[str, Any]
    search_time_ms: float
    # Enhanced fields
    query_analysis: Optional[Dict[str, Any]] = None
    business_intelligence: Optional[Dict[str, Any]] = None


@dataclass
class QueryAnalysis:
    intent: QueryIntent
    filters: SearchFilters
    lender_type_preference: Optional[LenderType]
    semantic_query: Optional[str]
    confidence: float
    explanation: str
    business_critical_flags: List[str]

# ============================================================================
# BUSINESS LOGIC CLASSES
# ============================================================================


class LenderClassifier:
    """Classifies companies as unsecured personal vs mortgage lenders"""

    UNSECURED_PERSONAL_LICENSES = {
        "Consumer Credit License",
        "Consumer Loan Company License",
        "Consumer Lender License",
        "Consumer Loan License",
        "Consumer Finance License",
        "Consumer Collection Agency License",
        "Consumer Installment Loan License",
        "Consumer Installment Loan Act License",
        "Consumer Financial Services Class I License",
        "Consumer Financial Services Class II License",
        "Sales Finance License",
        "Sales Finance Company License",
        "Sales Finance Agency License",
        "Installment Lender License",
        "Installment Loan License",
        "Installment Loan Company License",
        "Small Loan License",
        "Small Loan Company License",
        "Small Loan Lender License",
        "Small Lender License",
        "Money Lender License",
        "Supervised Lender License",
        "Payday Lender License",
        "Short-Term Lender License",
        "Title Pledge Lender License",
        "Lender License",
        "Regulated Lender License",
        "Licensed Lender License",
        "Collection Agency License",
        "Credit Services Business License",
        "Check Casher License",
        "Check Cashing License",
        "Money Transmitter License",
        "Personal Loan License",
        "Finance Company License"}

    MORTGAGE_LICENSES = {
        "Mortgage Lender License",
        "Mortgage Broker License",
        "Mortgage Company License",
        "Mortgage Loan Originator License",
        "Mortgage Servicer License",
        "Residential Mortgage Lender License",
        "Residential Mortgage Broker License",
        "First Mortgage Lender License",
        "Second Mortgage Lender License",
        "Mortgage Banker License",
        "Mortgage Loan Broker License"}

    @classmethod
    def classify_company(cls, license_types: List[str]) -> LenderType:
        if not license_types:
            return LenderType.UNKNOWN

        has_unsecured = any(
            lt in cls.UNSECURED_PERSONAL_LICENSES for lt in license_types)
        has_mortgage = any(lt in cls.MORTGAGE_LICENSES for lt in license_types)

        if has_unsecured and has_mortgage:
            return LenderType.MIXED
        elif has_unsecured:
            return LenderType.UNSECURED_PERSONAL
        elif has_mortgage:
            return LenderType.MORTGAGE
        else:
            return LenderType.UNKNOWN


class ContactValidator:
    @staticmethod
    def validate_phone(phone: str) -> bool:
        if not phone:
            return False
        phone_clean = re.sub(r'[^\d]', '', phone)
        return len(phone_clean) >= 10

    @staticmethod
    def validate_email(email: str) -> bool:
        if not email:
            return False
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, email))

    @classmethod
    def has_valid_contact_info(
            cls, company: Dict[str, Any]) -> Tuple[bool, List[str]]:
        issues = []
        has_email = cls.validate_email(company.get('email', ''))
        has_phone = cls.validate_phone(company.get('phone', ''))

        if not has_email:
            issues.append("no_valid_email")
        if not has_phone:
            issues.append("no_valid_phone")

        return (has_email or has_phone), issues

# ============================================================================
# VECTOR SEARCH SERVICE
# ============================================================================


class VectorSearchService:
    def __init__(self):
        self.model = None
        self.pool = None

    def _load_model(self):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            return None

        try:
            if STREAMLIT_AVAILABLE:
                @st.cache_resource
                def load_cached_model():
                    return SentenceTransformer('all-MiniLM-L6-v2')
                return load_cached_model()
            else:
                return SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model: {e}")
            return None

    async def connect(self):
        self.model = self._load_model()
        if not self.pool and DATABASE_URL:
            try:
                self.pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=5,
                    statement_cache_size=0
                )
            except Exception as e:
                logger.error(f"Failed to create vector search pool: {e}")

    def _fallback_text_similarity(
            self,
            query: str,
            texts: List[str],
            nmls_ids: List[str],
            limit: int = 50) -> List[str]:
        try:
            from difflib import SequenceMatcher

            query_lower = query.lower()
            similarities = []

            for i, text in enumerate(texts):
                text_lower = text.lower()
                score = 0.0

                # Word overlap scoring
                query_words = set(query_lower.split())
                text_words = set(text_lower.split())
                if query_words and text_words:
                    overlap = len(query_words.intersection(text_words))
                    score += (overlap / len(query_words)) * 0.7

                # Sequence similarity
                seq_sim = SequenceMatcher(
                    None, query_lower, text_lower).ratio()
                score += seq_sim * 0.3

                # Substring matching bonus
                if query_lower in text_lower:
                    score += 0.2

                similarities.append((score, nmls_ids[i]))

            similarities.sort(reverse=True)
            return [nmls_id for score,
                    nmls_id in similarities[:limit] if score > 0.2]

        except Exception as e:
            logger.error(f"Fallback text similarity error: {e}")
            return []

    async def semantic_search(self, query: str, limit: int = 50) -> List[str]:
        if not self.pool:
            return []

        try:
            async with self.pool.acquire() as conn:
                # Limit the initial dataset to prevent long processing times
                rows = await conn.fetch("""
                    SELECT nmls_id, company_name,
                           COALESCE(trade_names, ARRAY[]::text[]) as trade_names
                    FROM companies
                    WHERE company_name IS NOT NULL
                    ORDER BY RANDOM()  -- Add randomization to get diverse results
                    LIMIT 1000         -- Reduced from 10000 to speed up processing
                """)

                if not rows:
                    return []

                texts = []
                nmls_ids = []

                for row in rows:
                    company_text = row['company_name']
                    if row['trade_names']:
                        company_text += " " + " ".join(row['trade_names'])
                    texts.append(company_text)
                    nmls_ids.append(row['nmls_id'])

                # Try sentence transformers first
                if self.model is not None:
                    try:
                        # Process in smaller batches to avoid memory issues
                        batch_size = 100
                        query_embedding = self.model.encode([query])
                        
                        # Process corpus in batches
                        similarities = []
                        for i in range(0, len(texts), batch_size):
                            batch_texts = texts[i:i + batch_size]
                            batch_embeddings = self.model.encode(batch_texts)
                            batch_similarities = np.dot(query_embedding, batch_embeddings.T)[0]
                            similarities.extend(batch_similarities)
                        
                        # Convert to numpy array and get top results
                        similarities = np.array(similarities)
                        top_indices = np.argsort(similarities)[-limit:][::-1]
                        return [nmls_ids[i] for i in top_indices if similarities[i] > 0.3]
                    except Exception as e:
                        logger.error(f"Model encoding error: {e}")
                        return self._fallback_text_similarity(query, texts, nmls_ids, limit)
                else:
                    return self._fallback_text_similarity(query, texts, nmls_ids, limit)

        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

# ============================================================================
# NATURAL LANGUAGE PROCESSOR
# ============================================================================


class NaturalLanguageProcessor:
    def __init__(self):
        self.vector_search = VectorSearchService()

    async def initialize(self):
        await self.vector_search.connect()

    async def analyze_query(self, query: str) -> QueryAnalysis:
        context = await self._get_search_context()
        prompt = self._create_analysis_prompt(query, context)

        try:
            response = await claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )

            analysis_result = self._parse_claude_response(
                response.content[0].text)

            # Enhance with vector search if semantic query detected
            if analysis_result.semantic_query:
                similar_companies = await self.vector_search.semantic_search(analysis_result.semantic_query)
                if similar_companies:
                    analysis_result.business_critical_flags.append(
                        f"semantic_matches_found:{len(similar_companies)}")

            return analysis_result

        except Exception as e:
            logger.error(f"Claude analysis error: {e}")
            return QueryAnalysis(
                intent=QueryIntent.FIND_COMPANIES,
                filters=SearchFilters(query=query),
                lender_type_preference=LenderType.UNKNOWN,
                semantic_query=query,
                confidence=0.3,
                explanation=f"Fallback analysis due to error: {str(e)}",
                business_critical_flags=["analysis_error"]
            )

    def _create_analysis_prompt(self, query: str, context: Dict) -> str:
        return f"""
You are analyzing search queries for Finosu, a personal lending company looking for business prospects.

BUSINESS GOAL: Find companies that offer UNSECURED PERSONAL LOANS (consumer credit, installment loans, personal loans).

Query: "{query}"

KEY RULES - KEEP IT SIMPLE:
1. Geographic searches (e.g., "banks in california") → states: ["CA"], license_types: null
2. Personal lending searches (e.g., "personal loan providers") → license_types: ["Personal", "Consumer Credit"]  
3. Consumer credit searches (e.g., "consumer credit companies") → license_types: ["Consumer Credit"]
4. General searches (e.g., "lenders", "financial companies") → no specific filters, let scoring handle it
5. Contact searches (e.g., "companies with email") → has_email: true
6. Size searches (e.g., "large lenders") → min_licenses: 10

EXAMPLES:
- "Banks in California" → {{"states": ["CA"], "license_types": null}}
- "Personal loan providers" → {{"license_types": ["Personal", "Consumer Credit"]}}
- "Consumer credit companies" → {{"license_types": ["Consumer Credit"]}}
- "Financial companies with email" → {{"has_email": true}}
- "Large lenders" → {{"min_licenses": 10}}

LICENSE TYPE TERMS (use general terms that will match multiple variations):
- "Personal" → matches "Personal Loan License", "Personal Loan", etc.
- "Consumer Credit" → matches "Consumer Credit License", "Consumer Credit", etc.
- "Consumer" → matches any consumer-related license
- "Installment" → matches installment loan licenses
- "Small Loan" → matches small loan licenses

STATE MAPPING: california→CA, new york→NY, texas→TX, florida→FL

Return ONLY this JSON structure:
{{
    "intent": "find_lenders",
    "confidence": 0.8,
    "explanation": "Brief explanation of what user wants",
    "lender_type_preference": "unsecured_personal",
    "semantic_query": null,
    "business_critical_flags": [],
    "filters": {{
        "query": "search terms or null",
        "states": ["CA"] or null,
        "license_types": ["Personal"] or null,
        "has_email": true/false/null,
        "min_licenses": number or null,
        "active_licenses_only": true
    }}
}}

CRITICAL: Only set specific filters when the user clearly requests them. For geographic searches, do NOT add license_types.
"""

    async def _get_search_context(self) -> Dict:
        try:
            if self.vector_search.pool:
                async with self.vector_search.pool.acquire() as conn:
                    states = await conn.fetch("SELECT DISTINCT SUBSTRING(state FROM 1 FOR 2) as state FROM addresses WHERE state IS NOT NULL ORDER BY state")
                    business_structures = await conn.fetch("SELECT DISTINCT business_structure FROM companies WHERE business_structure IS NOT NULL ORDER BY business_structure")

                    return {
                        "states": [
                            row['state'] for row in states], "business_structures": [
                            row['business_structure'] for row in business_structures]}
        except Exception as e:
            logger.error(f"Context fetch error: {e}")

        return {"states": [], "business_structures": []}

    def _parse_claude_response(self, response_text: str) -> QueryAnalysis:
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())

            # Parse filters
            filters_data = data.get('filters', {})
            filters = SearchFilters(
                **{k: v for k, v in filters_data.items() if v is not None})

            return QueryAnalysis(
                intent=QueryIntent(
                    data.get(
                        'intent',
                        'find_companies')),
                filters=filters,
                lender_type_preference=LenderType(
                    data.get(
                        'lender_type_preference',
                        'unknown')) if data.get('lender_type_preference') else None,
                semantic_query=data.get('semantic_query'),
                confidence=float(
                    data.get(
                        'confidence',
                        0.5)),
                explanation=data.get(
                    'explanation',
                    'Analysis completed'),
                business_critical_flags=data.get(
                    'business_critical_flags',
                    []))

        except Exception as e:
            logger.error(f"Failed to parse Claude response: {e}")
            return QueryAnalysis(
                intent=QueryIntent.FIND_COMPANIES,
                filters=SearchFilters(query=response_text[:100]),
                lender_type_preference=LenderType.UNKNOWN,
                semantic_query=None,
                confidence=0.3,
                explanation=f"Parse error: {str(e)}",
                business_critical_flags=["parse_error"]
            )

# ============================================================================
# DATABASE MANAGER
# ============================================================================


class DatabaseManager:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not DATABASE_URL:
            error_msg = "DATABASE_URL not configured. Please check Streamlit secrets or environment variables."
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        try:
            logger.info(f"🔌 Attempting to connect to database...")
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                statement_cache_size=0,
                setup=self._setup_connection
            )
            logger.info("✅ Database connection pool created successfully")
        except Exception as e:
            error_msg = f"Failed to create database pool: {e}"
            logger.error(f"❌ {error_msg}")
            logger.error(f"Database URL format: {DATABASE_URL[:30]}...")
            # Provide more specific error guidance
            if "password authentication failed" in str(e).lower():
                error_msg += " - Check database credentials"
            elif "could not connect to server" in str(e).lower():
                error_msg += " - Check database host and port"
            elif "database" in str(e).lower() and "does not exist" in str(e).lower():
                error_msg += " - Check database name"
            raise ConnectionError(error_msg)

    async def _setup_connection(self, conn):
        await conn.execute("DEALLOCATE ALL;")

    async def disconnect(self):
        if self.pool:
            try:
                # First, close all connections gracefully with timeout
                await asyncio.wait_for(self.pool.close(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Pool close timed out, terminating connections")
                # Force terminate if graceful close times out
                self.pool.terminate()
            except Exception as e:
                logger.error(f"Error during pool disconnect: {e}")
                self.pool.terminate()
            finally:
                self.pool = None
            logger.info("🔌 Database connection pool closed")

# ============================================================================
# SEARCH SERVICE
# ============================================================================


class SearchService:
    @staticmethod
    def build_search_query(
            filters: SearchFilters,
            page: int,
            page_size: int,
            sort_field: SortField,
            sort_order: SortOrder) -> tuple:
        # Fixed query structure to avoid GROUP BY issues
        base_query = """
        SELECT 
            c.nmls_id,
            c.company_name,
            c.business_structure,
            c.phone,
            c.email,
            c.website,
            (SELECT full_address FROM addresses WHERE company_id = c.id AND address_type = 'street' LIMIT 1) as street_address,
            (SELECT full_address FROM addresses WHERE company_id = c.id AND address_type = 'mailing' LIMIT 1) as mailing_address,
            c.federal_regulator,
            c.created_at,
            (SELECT COUNT(*) FROM licenses WHERE company_id = c.id) as total_licenses,
            (SELECT COUNT(*) FROM licenses WHERE company_id = c.id AND active = true) as active_licenses,
            (SELECT ARRAY_AGG(DISTINCT license_type) FROM licenses WHERE company_id = c.id AND active = true AND license_type IS NOT NULL) as license_types,
            (SELECT ARRAY_AGG(DISTINCT COALESCE(SUBSTRING(combined.state FROM 1 FOR 2), 'XX')) 
             FROM (
                 SELECT state FROM addresses WHERE company_id = c.id AND state IS NOT NULL
                 UNION 
                 SELECT regulator FROM licenses WHERE company_id = c.id AND active = true AND regulator IS NOT NULL
             ) as combined(state)
             WHERE combined.state IS NOT NULL) as states_licensed
        FROM companies c
        """

        conditions = []
        params = []
        param_count = 0

        # Text search across company name, addresses, and trade names
        if filters.query:
            param_count += 1
            param_count += 1
            param_count += 1
            conditions.append(f"""
                (c.company_name ILIKE ${param_count-2}
                 OR EXISTS (SELECT 1 FROM addresses WHERE company_id = c.id AND full_address ILIKE ${param_count-1})
                 OR EXISTS (SELECT 1 FROM unnest(c.trade_names) AS trade_name WHERE trade_name ILIKE ${param_count}))
            """)
            params.append(f"%{filters.query}%")
            params.append(f"%{filters.query}%")
            params.append(f"%{filters.query}%")

        # State filtering - check both addresses and license regulators
        if filters.states:
            param_count += 1
            param_count += 1
            # Handle single vs multiple states differently for PostgreSQL compatibility
            if len(filters.states) == 1:
                # Use direct equality for single state to avoid ANY() operator issues
                state_upper = filters.states[0].upper()
                conditions.append(f"""
                    (EXISTS (SELECT 1 FROM addresses WHERE company_id = c.id 
                             AND UPPER(SUBSTRING(state FROM 1 FOR 2)) = ${param_count-1})
                     OR EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                               AND active = true 
                               AND UPPER(SUBSTRING(regulator FROM '([A-Z]{{2}})')) = ${param_count}))
                """)
                params.append(state_upper)
                params.append(state_upper)
            else:
                # Use ANY() operator for multiple states
                conditions.append(f"""
                    (EXISTS (SELECT 1 FROM addresses WHERE company_id = c.id 
                             AND UPPER(SUBSTRING(state FROM 1 FOR 2)) = ANY(${param_count-1}))
                     OR EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                               AND active = true 
                               AND UPPER(SUBSTRING(regulator FROM '([A-Z]{{2}})')) = ANY(${param_count})))
                """)
                params.append([state.upper() for state in filters.states])
                params.append([state.upper() for state in filters.states])

        # License type filtering - use flexible matching
        if filters.license_types:
            param_count += 1
            # Use ILIKE for flexible matching instead of exact equality
            license_conditions = []
            for license_type in filters.license_types:
                license_conditions.append(f"license_type ILIKE ${param_count}")
                params.append(f"%{license_type}%")
                param_count += 1
            
            conditions.append(f"""
                EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                        AND active = true 
                        AND ({' OR '.join(license_conditions)}))
            """)
            param_count -= 1  # Adjust for the loop increment

        # Business structure filtering
        if filters.business_structures:
            param_count += 1
            conditions.append(f"c.business_structure = ANY(${param_count})")
            params.append(filters.business_structures)

        # Email filtering
        if filters.has_email is not None:
            if filters.has_email:
                conditions.append("c.email IS NOT NULL AND c.email != '' AND c.email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'")
            else:
                conditions.append("(c.email IS NULL OR c.email = '' OR c.email !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$')")

        # Website filtering
        if filters.has_website is not None:
            if filters.has_website:
                conditions.append("c.website IS NOT NULL AND c.website != ''")
            else:
                conditions.append("(c.website IS NULL OR c.website = '')")

        # Federal registration filtering
        if filters.has_federal_registration is not None:
            if filters.has_federal_registration:
                conditions.append("c.federal_regulator IS NOT NULL AND c.federal_regulator != ''")
            else:
                conditions.append("(c.federal_regulator IS NULL OR c.federal_regulator = '')")

        # License count filtering
        if filters.min_licenses is not None:
            param_count += 1
            conditions.append(f"""
                (SELECT COUNT(*) FROM licenses WHERE company_id = c.id AND active = true) >= ${param_count}
            """)
            params.append(filters.min_licenses)

        if filters.max_licenses is not None:
            param_count += 1
            conditions.append(f"""
                (SELECT COUNT(*) FROM licenses WHERE company_id = c.id AND active = true) <= ${param_count}
            """)
            params.append(filters.max_licenses)

        # Active licenses filter
        if filters.active_licenses_only:
            conditions.append("EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id AND active = true)")

        # Date filters for license issuance
        if filters.licensed_after:
            param_count += 1
            conditions.append(f"""
                EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                        AND original_issue_date >= ${param_count})
            """)
            params.append(filters.licensed_after)

        if filters.licensed_before:
            param_count += 1
            conditions.append(f"""
                EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                        AND original_issue_date <= ${param_count})
            """)
            params.append(filters.licensed_before)

        # Add WHERE clause if conditions exist
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        # Add ORDER BY
        sort_column = {
            SortField.company_name: "c.company_name",
            SortField.nmls_id: "c.nmls_id",
            SortField.business_structure: "c.business_structure",
            SortField.total_licenses: "total_licenses",
            SortField.created_at: "c.created_at"
        }[sort_field]

        base_query += f" ORDER BY {sort_column} {sort_order.value}"

        # Add pagination
        param_count += 1
        base_query += f" LIMIT ${param_count}"
        params.append(page_size)

        param_count += 1
        base_query += f" OFFSET ${param_count}"
        params.append((page - 1) * page_size)

        return base_query, params

    @staticmethod
    def build_count_query(filters: SearchFilters) -> tuple:
        # Simplified count query to match main query structure
        base_query = """
        SELECT COUNT(*)
        FROM companies c
        """

        conditions = []
        params = []
        param_count = 0

        # Text search across company name, addresses, and trade names
        if filters.query:
            param_count += 1
            param_count += 1
            param_count += 1
            conditions.append(f"""
                (c.company_name ILIKE ${param_count-2}
                 OR EXISTS (SELECT 1 FROM addresses WHERE company_id = c.id AND full_address ILIKE ${param_count-1})
                 OR EXISTS (SELECT 1 FROM unnest(c.trade_names) AS trade_name WHERE trade_name ILIKE ${param_count}))
            """)
            params.append(f"%{filters.query}%")
            params.append(f"%{filters.query}%")
            params.append(f"%{filters.query}%")

        # State filtering - check both addresses and license regulators
        if filters.states:
            param_count += 1
            param_count += 1
            # Handle single vs multiple states differently for PostgreSQL compatibility
            if len(filters.states) == 1:
                # Use direct equality for single state to avoid ANY() operator issues
                state_upper = filters.states[0].upper()
                conditions.append(f"""
                    (EXISTS (SELECT 1 FROM addresses WHERE company_id = c.id 
                             AND UPPER(SUBSTRING(state FROM 1 FOR 2)) = ${param_count-1})
                     OR EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                               AND active = true 
                               AND UPPER(SUBSTRING(regulator FROM '([A-Z]{{2}})')) = ${param_count}))
                """)
                params.append(state_upper)
                params.append(state_upper)
            else:
                # Use ANY() operator for multiple states
                conditions.append(f"""
                    (EXISTS (SELECT 1 FROM addresses WHERE company_id = c.id 
                             AND UPPER(SUBSTRING(state FROM 1 FOR 2)) = ANY(${param_count-1}))
                     OR EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                               AND active = true 
                               AND UPPER(SUBSTRING(regulator FROM '([A-Z]{{2}})')) = ANY(${param_count})))
                """)
                params.append([state.upper() for state in filters.states])
                params.append([state.upper() for state in filters.states])

        # License type filtering - use flexible matching
        if filters.license_types:
            param_count += 1
            # Use ILIKE for flexible matching instead of exact equality
            license_conditions = []
            for license_type in filters.license_types:
                license_conditions.append(f"license_type ILIKE ${param_count}")
                params.append(f"%{license_type}%")
                param_count += 1
            
            conditions.append(f"""
                EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                        AND active = true 
                        AND ({' OR '.join(license_conditions)}))
            """)
            param_count -= 1  # Adjust for the loop increment

        # Business structure filtering
        if filters.business_structures:
            param_count += 1
            conditions.append(f"c.business_structure = ANY(${param_count})")
            params.append(filters.business_structures)

        # Email filtering
        if filters.has_email is not None:
            if filters.has_email:
                conditions.append("c.email IS NOT NULL AND c.email != '' AND c.email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'")
            else:
                conditions.append("(c.email IS NULL OR c.email = '' OR c.email !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$')")

        # Website filtering
        if filters.has_website is not None:
            if filters.has_website:
                conditions.append("c.website IS NOT NULL AND c.website != ''")
            else:
                conditions.append("(c.website IS NULL OR c.website = '')")

        # Federal registration filtering
        if filters.has_federal_registration is not None:
            if filters.has_federal_registration:
                conditions.append("c.federal_regulator IS NOT NULL AND c.federal_regulator != ''")
            else:
                conditions.append("(c.federal_regulator IS NULL OR c.federal_regulator = '')")

        # License count filtering
        if filters.min_licenses is not None:
            param_count += 1
            conditions.append(f"""
                (SELECT COUNT(*) FROM licenses WHERE company_id = c.id AND active = true) >= ${param_count}
            """)
            params.append(filters.min_licenses)

        if filters.max_licenses is not None:
            param_count += 1
            conditions.append(f"""
                (SELECT COUNT(*) FROM licenses WHERE company_id = c.id AND active = true) <= ${param_count}
            """)
            params.append(filters.max_licenses)

        # Active licenses filter
        if filters.active_licenses_only:
            conditions.append("EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id AND active = true)")

        # Date filters for license issuance
        if filters.licensed_after:
            param_count += 1
            conditions.append(f"""
                EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                        AND original_issue_date >= ${param_count})
            """)
            params.append(filters.licensed_after)

        if filters.licensed_before:
            param_count += 1
            conditions.append(f"""
                EXISTS (SELECT 1 FROM licenses WHERE company_id = c.id 
                        AND original_issue_date <= ${param_count})
            """)
            params.append(filters.licensed_before)

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        return base_query, params

# ============================================================================
# UNIFIED SEARCH API
# ============================================================================


class UnifiedSearchAPI:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.nlp = NaturalLanguageProcessor()
        self.classifier = LenderClassifier()
        self.contact_validator = ContactValidator()

    async def initialize(self):
        await self.db_manager.connect()
        await self.nlp.initialize()
        # Share database pool with NLP processor
        self.nlp.vector_search.pool = self.db_manager.pool

    async def search(
        self,
        query: str = None,
        filters: SearchFilters = None,
        use_ai: bool = True,
        apply_business_filters: bool = True,
        page: int = 1,
        page_size: int = 20,
        sort_field: SortField = SortField.company_name,
        sort_order: SortOrder = SortOrder.asc
    ) -> SearchResponse:
        """
        Unified search method that handles both natural language and structured queries
        """
        start_time = datetime.now()

        # Determine search filters
        if query and use_ai:
            # Use AI to analyze natural language query
            analysis = await self.nlp.analyze_query(query)
            search_filters = analysis.filters
            logger.info(f"AI Analysis - Original filters: {search_filters.dict(exclude_unset=True)}")

            if apply_business_filters:
                search_filters = await self._apply_business_filters(search_filters, analysis.lender_type_preference)
                logger.info(f"After business filters: {search_filters.dict(exclude_unset=True)}")
        elif filters:
            # Use provided structured filters
            search_filters = filters
            analysis = None
            logger.info(f"Using provided filters: {search_filters.dict(exclude_unset=True)}")
        else:
            # Default search
            search_filters = SearchFilters(query=query)
            analysis = None
            logger.info(f"Default search filters: {search_filters.dict(exclude_unset=True)}")

        # Execute search
        async with self.db_manager.pool.acquire() as conn:
            # Get total count
            count_query, count_params = SearchService.build_count_query(
                search_filters)
            total_count = await conn.fetchval(count_query, *count_params)

            # Get results
            search_query, search_params = SearchService.build_search_query(
                search_filters, page, page_size, sort_field, sort_order
            )
            rows = await conn.fetch(search_query, *search_params)

            # Process results
            companies = []
            for row in rows:
                company_data = dict(row)

                # Add business intelligence
                lender_type = self.classifier.classify_company(
                    company_data.get('license_types', []))
                has_valid_contact, contact_issues = self.contact_validator.has_valid_contact_info(
                    company_data)
                business_score = self._calculate_business_score(
                    lender_type, has_valid_contact, company_data)

                company = CompanyResponse(
                    **company_data,
                    lender_type=lender_type.value,
                    has_valid_contact=has_valid_contact,
                    contact_issues=contact_issues,
                    business_score=business_score
                )
                companies.append(company)

            # Sort by business score if applying business filters
            if apply_business_filters and analysis:
                companies.sort(
                    key=lambda x: x.business_score or 0,
                    reverse=True)

        # Calculate response time
        search_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Build response
        response = SearchResponse(
            companies=companies,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=(total_count + page_size - 1) // page_size,
            filters_applied=search_filters.dict(exclude_unset=True),
            search_time_ms=search_time_ms
        )

        # Add AI analysis if available
        if analysis:
            response.query_analysis = {
                "original_query": query,
                "intent": analysis.intent.value,
                "confidence": analysis.confidence,
                "explanation": analysis.explanation,
                "business_critical_flags": analysis.business_critical_flags
            }

            response.business_intelligence = self._calculate_result_stats(
                companies, analysis)

        return response

    async def _apply_business_filters(
            self,
            filters: SearchFilters,
            lender_preference: LenderType) -> SearchFilters:
        """Apply Finosu's business requirements to search filters"""

        # Create a copy to avoid modifying the original
        enhanced_filters = SearchFilters(**filters.dict())
        
        # DO NOT auto-apply license type filters - let them be handled in scoring
        # This was causing the search to be too restrictive
        if lender_preference == LenderType.UNSECURED_PERSONAL:
            # Don't filter by license types automatically
            # Instead, let the scoring system prioritize personal lenders
            pass
        elif lender_preference == LenderType.MORTGAGE:
            # User explicitly wants mortgage lenders
            if not enhanced_filters.license_types:
                enhanced_filters.license_types = list(self.classifier.MORTGAGE_LICENSES)
        
        # For geographic searches, don't add additional restrictions
        # Let the user's original intent drive the search
        
        # DO NOT require contact information as hard filters
        # Use them for scoring instead - many good companies might not have perfect contact info
        # The original code was setting has_email and has_website to True automatically
        
        # Only prioritize active licenses - this is reasonable
        if enhanced_filters.active_licenses_only is None:
            enhanced_filters.active_licenses_only = True

        return enhanced_filters

    def _calculate_business_score(
            self,
            lender_type: LenderType,
            has_valid_contact: bool,
            company_data: Dict) -> float:
        """Calculate business relevance score"""
        score = 0.0

        # Lender type scoring
        if lender_type == LenderType.UNSECURED_PERSONAL:
            score += 50.0
        elif lender_type == LenderType.MIXED:
            score += 30.0
        elif lender_type == LenderType.MORTGAGE:
            score += 0.0
        else:
            score += 10.0

        # Contact information
        if has_valid_contact:
            score += 30.0

        # Additional factors
        if company_data.get('email'):
            score += 10.0
        if company_data.get('phone'):
            score += 10.0
        if company_data.get('website'):
            score += 5.0

        # License count
        license_count = company_data.get('total_licenses', 0)
        score += min(license_count * 2, 20.0)

        return min(score, 100.0)

    def _calculate_result_stats(self,
                                companies: List[CompanyResponse],
                                analysis: QueryAnalysis) -> Dict:
        """Calculate business intelligence statistics"""
        total = len(companies)
        if total == 0:
            return {"total": 0}

        lender_types = {}
        contact_stats = {
            "valid_contact": 0,
            "email_only": 0,
            "phone_only": 0,
            "no_contact": 0}
        high_value_targets = 0

        for company in companies:
            # Lender type counting
            lender_type = company.lender_type or 'unknown'
            lender_types[lender_type] = lender_types.get(lender_type, 0) + 1

            # Contact statistics
            has_email = self.contact_validator.validate_email(
                company.email or '')
            has_phone = self.contact_validator.validate_phone(
                company.phone or '')

            if has_email and has_phone:
                contact_stats["valid_contact"] += 1
            elif has_email:
                contact_stats["email_only"] += 1
            elif has_phone:
                contact_stats["phone_only"] += 1
            else:
                contact_stats["no_contact"] += 1

            # High-value targets
            if (lender_type == "unsecured_personal" and
                company.has_valid_contact and
                    (company.business_score or 0) > 70):
                high_value_targets += 1

        return {
            "total": total,
            "lender_type_distribution": lender_types,
            "contact_statistics": contact_stats,
            "high_value_targets": high_value_targets,
            "recommendations": self._generate_recommendations(
                lender_types,
                contact_stats,
                analysis)}

    def _generate_recommendations(
            self,
            lender_types: Dict,
            contact_stats: Dict,
            analysis: QueryAnalysis) -> List[str]:
        """Generate business recommendations"""
        recommendations = []

        total = sum(lender_types.values())
        if total == 0:
            return ["No results found. Try broadening your search criteria."]

        # Lender type recommendations
        unsecured_count = lender_types.get('unsecured_personal', 0)
        mortgage_count = lender_types.get('mortgage', 0)

        if unsecured_count > 0:
            recommendations.append(
                f"Found {unsecured_count} unsecured personal lenders - these are high-priority targets")

        if mortgage_count > unsecured_count:
            recommendations.append(
                "Results are mortgage-heavy. Consider refining search for consumer lenders")

        # Contact recommendations
        no_contact = contact_stats.get('no_contact', 0)
        if no_contact > total * 0.3:
            recommendations.append(
                "Many companies lack contact info. Consider filtering for companies with email/phone")

        return recommendations

# ============================================================================
# STREAMLIT INTEGRATION FUNCTIONS
# ============================================================================


async def run_unified_search(
    query: str = None,
    filters: SearchFilters = None,
    use_ai: bool = True,
    apply_business_filters: bool = True,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """
    Streamlit-compatible search function with proper connection lifecycle management.
    Creates a fresh UnifiedSearchAPI instance for each search to avoid event loop conflicts.
    """
    # Create a fresh API instance for this search
    api_instance = UnifiedSearchAPI()
    
    try:
        # Initialize connections within the current event loop
        await api_instance.initialize()
        
        # Perform the search
        response = await api_instance.search(
            query=query,
            filters=filters,
            use_ai=use_ai,
            apply_business_filters=apply_business_filters,
            page=page,
            page_size=page_size
        )
        
        # Convert to dict for Streamlit compatibility
        result = {
            "companies": [company.dict() for company in response.companies],
            "total_count": response.total_count,
            "page": response.page,
            "page_size": response.page_size,
            "total_pages": response.total_pages,
            "filters_applied": response.filters_applied,
            "search_time_ms": response.search_time_ms,
            "query_analysis": response.query_analysis,
            "business_intelligence": response.business_intelligence
        }
        
        return result
        
    except (ValueError, ConnectionError) as db_error:
        # Database configuration or connection issues
        logger.error(f"Database error in run_unified_search: {db_error}")
        return {
            "companies": [],
            "total_count": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "filters_applied": filters.dict(exclude_unset=True) if filters else {},
            "search_time_ms": 0,
            "query_analysis": None,
            "business_intelligence": None,
            "error": f"Database connection failed: {str(db_error)}"
        }
    except Exception as e:
        logger.error(f"Search error in run_unified_search: {e}")
        return {
            "companies": [],
            "total_count": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
            "filters_applied": filters.dict(exclude_unset=True) if filters else {},
            "search_time_ms": 0,
            "query_analysis": None,
            "business_intelligence": None,
            "error": f"Search failed: {str(e)}"
        }
    finally:
        # Always clean up connections
        try:
            await api_instance.db_manager.disconnect()
            # Also clean up vector search connections with timeout
            if hasattr(api_instance.nlp, 'vector_search') and api_instance.nlp.vector_search.pool:
                try:
                    await asyncio.wait_for(api_instance.nlp.vector_search.pool.close(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Vector search pool close timed out, terminating")
                    api_instance.nlp.vector_search.pool.terminate()
                except Exception:
                    api_instance.nlp.vector_search.pool.terminate()
        except Exception as cleanup_error:
            logger.warning(f"Cleanup error (non-critical): {cleanup_error}")

# ============================================================================
# FASTAPI ENDPOINTS (Keep global instance for FastAPI server)
# ============================================================================

# Global API instance only for FastAPI server
unified_api = UnifiedSearchAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await unified_api.initialize()
    yield
    await unified_api.db_manager.disconnect()

# FastAPI app
app = FastAPI(
    title="Unified NMLS Search API",
    description="Comprehensive search system with AI, vector search, and business intelligence",
    version="3.0.0",
    lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Unified NMLS Search API",
        "version": "3.0.0",
        "features": [
            "Natural language search with Claude AI",
            "Vector semantic search",
            "Traditional SQL filtering",
            "Business intelligence",
            "Lender classification",
            "Contact validation"
        ]
    }


@app.post("/search", response_model=SearchResponse)
async def search_endpoint(
    query: Optional[str] = None,
    filters: Optional[SearchFilters] = None,
    use_ai: bool = True,
    apply_business_filters: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_field: SortField = SortField.company_name,
    sort_order: SortOrder = SortOrder.asc
):
    """Unified search endpoint supporting both natural language and structured queries"""
    try:
        return await unified_api.search(
            query=query,
            filters=filters,
            use_ai=use_ai,
            apply_business_filters=apply_business_filters,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
