#!/usr/bin/env python3
"""
Unified NMLS Search System
Streamlined search functionality with AI, vector search, and business intelligence.
"""

import os
import re
import json
import logging
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from enum import Enum
from contextlib import asynccontextmanager

import numpy as np
import asyncpg
from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Optional dependencies with fallbacks
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

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
        ANTHROPIC_API_KEY = st.secrets.get('ANTHROPIC_API_KEY', os.getenv('ANTHROPIC_API_KEY'))
        DATABASE_URL = st.secrets.get('DATABASE_URL', os.getenv('DATABASE_URL'))
    except Exception:
        ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
        DATABASE_URL = os.getenv('DATABASE_URL')
else:
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    DATABASE_URL = os.getenv('DATABASE_URL')

claude_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# ============================================================================
# DATA MODELS
# ============================================================================

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class SortField(str, Enum):
    company_name = "company_name"
    nmls_id = "nmls_id"
    total_licenses = "total_licenses"

class LenderType(str, Enum):
    UNSECURED_PERSONAL = "unsecured_personal"
    MORTGAGE = "mortgage"
    MIXED = "mixed"
    UNKNOWN = "unknown"

class SearchFilters(BaseModel):
    query: Optional[str] = None
    states: Optional[List[str]] = None
    has_email: Optional[bool] = None
    has_website: Optional[bool] = None
    min_licenses: Optional[int] = None
    max_licenses: Optional[int] = None

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
    lender_type: Optional[str] = None
    business_score: Optional[float] = None

class SearchResponse(BaseModel):
    companies: List[CompanyResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    search_time_ms: float
    query_analysis: Optional[Dict[str, Any]] = None

# ============================================================================
# BUSINESS LOGIC
# ============================================================================

class LenderClassifier:
    """Simplified lender classification"""
    
    UNSECURED_LICENSES = {
        "Consumer Credit License", "Consumer Loan License", "Consumer Finance License",
        "Installment Loan License", "Small Loan License", "Personal Loan License",
        "Payday Lender License", "Finance Company License"
    }
    
    MORTGAGE_LICENSES = {
        "Mortgage Lender License", "Mortgage Broker License", "Mortgage Company License",
        "Residential Mortgage Lender License", "Mortgage Banker License"
    }
    
    @classmethod
    def classify_company(cls, license_types: List[str]) -> LenderType:
        if not license_types:
            return LenderType.UNKNOWN
        
        has_unsecured = any(lt in cls.UNSECURED_LICENSES for lt in license_types)
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
    def validate_email(email: str) -> bool:
        if not email:
            return False
        return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        if not phone:
            return False
        return len(re.sub(r'[^\d]', '', phone)) >= 10

# ============================================================================
# SEARCH SERVICES
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
        except Exception:
            return None
    
    async def connect(self):
        self.model = self._load_model()
        if not self.pool and DATABASE_URL:
            try:
                self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
            except Exception as e:
                logger.error(f"Vector search pool error: {e}")
    
    async def semantic_search(self, query: str, limit: int = 50) -> List[str]:
        if not self.pool:
            return []
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT nmls_id, company_name FROM companies 
                    WHERE company_name IS NOT NULL LIMIT 5000
                """)
                
                if not rows or not self.model:
                    return []
                
                texts = [row['company_name'] for row in rows]
                nmls_ids = [row['nmls_id'] for row in rows]
                
                query_embedding = self.model.encode([query])
                corpus_embeddings = self.model.encode(texts)
                similarities = np.dot(query_embedding, corpus_embeddings.T)[0]
                top_indices = np.argsort(similarities)[-limit:][::-1]
                
                return [nmls_ids[i] for i in top_indices if similarities[i] > 0.3]
                
        except Exception:
            return []

class NaturalLanguageProcessor:
    def __init__(self):
        self.vector_search = VectorSearchService()
    
    async def initialize(self):
        await self.vector_search.connect()
    
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        if not claude_client:
            return {"filters": SearchFilters(query=query), "explanation": "AI analysis unavailable"}
        
        prompt = f"""
Analyze this search query for an NMLS database and return JSON with search filters:

Query: "{query}"

Return this structure:
{{
    "explanation": "what you understood",
    "filters": {{
        "query": "text search terms or null",
        "states": ["CA", "TX"] or null,
        "has_email": true/false/null,
        "has_website": true/false/null
    }}
}}
"""
        
        try:
            response = await claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            json_match = re.search(r'\{.*\}', response.content[0].text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                filters_data = data.get('filters', {})
                return {
                    "filters": SearchFilters(**{k: v for k, v in filters_data.items() if v is not None}),
                    "explanation": data.get('explanation', 'Analysis completed')
                }
        except Exception:
            pass
        
        return {"filters": SearchFilters(query=query), "explanation": "Fallback analysis"}

class DatabaseManager:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not configured")
        
        self.pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=2, max_size=10, statement_cache_size=0
        )
    
    async def disconnect(self):
        if self.pool:
            await self.pool.close()

class SearchService:
    @staticmethod
    def build_query(filters: SearchFilters, page: int, page_size: int, 
                   sort_field: SortField, sort_order: SortOrder, count_only: bool = False) -> tuple:
        
        if count_only:
            base_query = "SELECT COUNT(DISTINCT c.id) FROM companies c"
        else:
            base_query = """
            WITH company_stats AS (
                SELECT 
                    c.id as company_id, c.nmls_id,
                    COUNT(l.license_id) as total_licenses,
                    COUNT(CASE WHEN l.active = true THEN 1 END) as active_licenses,
                    ARRAY_AGG(DISTINCT l.license_type) FILTER (WHERE l.license_type IS NOT NULL) as license_types,
                    ARRAY_AGG(DISTINCT SUBSTRING(a.state FROM 1 FOR 2)) FILTER (WHERE a.state IS NOT NULL) as states_licensed
                FROM companies c
                LEFT JOIN licenses l ON c.id = l.company_id
                LEFT JOIN addresses a ON c.id = a.company_id
                GROUP BY c.id, c.nmls_id
            )
            SELECT 
                c.nmls_id, c.company_name, c.business_structure, c.phone, c.email, c.website,
                a.full_address as street_address, am.full_address as mailing_address,
                COALESCE(cs.total_licenses, 0) as total_licenses,
                COALESCE(cs.active_licenses, 0) as active_licenses,
                COALESCE(cs.license_types, ARRAY[]::text[]) as license_types,
                COALESCE(cs.states_licensed, ARRAY[]::text[]) as states_licensed
            FROM companies c
            LEFT JOIN company_stats cs ON c.id = cs.company_id
            LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
            LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
            """
        
        conditions = []
        params = []
        param_count = 0
        
        # Add joins for filtering
        if not count_only:
            joins = ""
        else:
            joins = """
            LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
            LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
            """
            base_query += joins
        
        # Build WHERE conditions
        if filters.query:
            param_count += 1
            conditions.append(f"(c.company_name ILIKE ${param_count} OR a.full_address ILIKE ${param_count} OR am.full_address ILIKE ${param_count})")
            params.append(f"%{filters.query}%")
        
        if filters.states:
            param_count += 1
            conditions.append(f"SUBSTRING(a.state FROM 1 FOR 2) = ANY(${param_count})")
            params.append(filters.states)
        
        if filters.has_email is not None:
            conditions.append("c.email IS NOT NULL AND c.email != ''" if filters.has_email else "(c.email IS NULL OR c.email = '')")
        
        if filters.has_website is not None:
            conditions.append("c.website IS NOT NULL AND c.website != ''" if filters.has_website else "(c.website IS NULL OR c.website = '')")
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        if not count_only:
            # Add sorting and pagination
            sort_column = {
                SortField.company_name: "c.company_name",
                SortField.nmls_id: "c.nmls_id",
                SortField.total_licenses: "cs.total_licenses"
            }[sort_field]
            
            base_query += f" ORDER BY {sort_column} {sort_order.value}"
            
            param_count += 1
            base_query += f" LIMIT ${param_count}"
            params.append(page_size)
            
            param_count += 1
            base_query += f" OFFSET ${param_count}"
            params.append((page - 1) * page_size)
        
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
        self.nlp.vector_search.pool = self.db_manager.pool
    
    async def search(
        self,
        query: str = None,
        filters: SearchFilters = None,
        use_ai: bool = True,
        page: int = 1,
        page_size: int = 20,
        sort_field: SortField = SortField.company_name,
        sort_order: SortOrder = SortOrder.asc
    ) -> SearchResponse:
        start_time = datetime.now()
        
        # Determine search filters
        if query and use_ai:
            analysis = await self.nlp.analyze_query(query)
            search_filters = analysis["filters"]
            query_analysis = {"explanation": analysis["explanation"]}
        elif filters:
            search_filters = filters
            query_analysis = None
        else:
            search_filters = SearchFilters(query=query)
            query_analysis = None
        
        # Execute search
        async with self.db_manager.pool.acquire() as conn:
            # Get total count
            count_query, count_params = SearchService.build_query(search_filters, page, page_size, sort_field, sort_order, count_only=True)
            total_count = await conn.fetchval(count_query, *count_params)
            
            # Get results
            search_query, search_params = SearchService.build_query(search_filters, page, page_size, sort_field, sort_order)
            rows = await conn.fetch(search_query, *search_params)
            
            # Process results
            companies = []
            for row in rows:
                company_data = dict(row)
                
                # Add business intelligence
                lender_type = self.classifier.classify_company(company_data.get('license_types', []))
                business_score = self._calculate_business_score(lender_type, company_data)
                
                company = CompanyResponse(
                    **company_data,
                    lender_type=lender_type.value,
                    business_score=business_score
                )
                companies.append(company)
        
        # Calculate response time
        search_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return SearchResponse(
            companies=companies,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=(total_count + page_size - 1) // page_size,
            search_time_ms=search_time_ms,
            query_analysis=query_analysis
        )
    
    def _calculate_business_score(self, lender_type: LenderType, company_data: Dict) -> float:
        """Simplified business scoring"""
        score = 0.0
        
        # Lender type scoring
        if lender_type == LenderType.UNSECURED_PERSONAL:
            score += 50.0
        elif lender_type == LenderType.MIXED:
            score += 30.0
        elif lender_type == LenderType.UNKNOWN:
            score += 10.0
        
        # Contact information
        if self.contact_validator.validate_email(company_data.get('email', '')):
            score += 25.0
        if self.contact_validator.validate_phone(company_data.get('phone', '')):
            score += 15.0
        if company_data.get('website'):
            score += 10.0
        
        return min(score, 100.0)

# ============================================================================
# FASTAPI ENDPOINTS
# ============================================================================

unified_api = UnifiedSearchAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await unified_api.initialize()
    yield
    await unified_api.db_manager.disconnect()

app = FastAPI(
    title="Unified NMLS Search API",
    description="Streamlined search system with AI and business intelligence",
    version="3.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Unified NMLS Search API", "version": "3.1.0"}

@app.post("/search", response_model=SearchResponse)
async def search_endpoint(
    query: Optional[str] = None,
    filters: Optional[SearchFilters] = None,
    use_ai: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_field: SortField = SortField.company_name,
    sort_order: SortOrder = SortOrder.asc
):
    try:
        return await unified_api.search(
            query=query,
            filters=filters,
            use_ai=use_ai,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STREAMLIT INTEGRATION
# ============================================================================

async def run_unified_search(
    query: str = None,
    filters: SearchFilters = None,
    use_ai: bool = True,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """Streamlit-compatible search function"""
    if not unified_api.db_manager.pool:
        await unified_api.initialize()
    
    response = await unified_api.search(
        query=query,
        filters=filters,
        use_ai=use_ai,
        page=page,
        page_size=page_size
    )
    
    return {
        "companies": [company.dict() for company in response.companies],
        "total_count": response.total_count,
        "page": response.page,
        "page_size": response.page_size,
        "total_pages": response.total_pages,
        "search_time_ms": response.search_time_ms,
        "query_analysis": response.query_analysis
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 