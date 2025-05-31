#!/usr/bin/env python3
"""
NMLS Database Search & Filtering API
Comprehensive search system for NMLS Consumer Access database.

Features:
- Text search across company names, addresses, trade names
- Advanced filtering by license types, states, business structures
- Fuzzy search capabilities
- Pagination and sorting
- Vector search ready (extensible)
- Real-time suggestions
- Export capabilities
"""

import os
import re
import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import psycopg2
from psycopg2.extras import RealDictCursor
import asyncpg
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Use environment variables only
DATABASE_URL = os.getenv('DATABASE_URL')

def set_dynamic_config(database_url=None):
    """Set dynamic configuration for database URL"""
    global DATABASE_URL
    
    if database_url:
        DATABASE_URL = database_url

# Pydantic Models
class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class SortField(str, Enum):
    company_name = "company_name"
    nmls_id = "nmls_id"
    business_structure = "business_structure"
    total_licenses = "total_licenses"
    created_at = "created_at"

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

class LicenseResponse(BaseModel):
    license_id: str
    company_nmls_id: str
    company_name: str
    license_type: str
    regulator: str
    status: Optional[str] = None
    license_number: Optional[str] = None
    original_issue_date: Optional[str] = None
    renewed_through: Optional[str] = None
    authorized_to_conduct_business: Optional[bool] = None
    active: bool = True

class SearchFilters(BaseModel):
    # Text search
    query: Optional[str] = Field(None, description="Text search across company names, addresses, trade names")
    
    # Basic filters
    states: Optional[List[str]] = Field(None, description="Filter by states (e.g., ['CA', 'TX'])")
    license_types: Optional[List[str]] = Field(None, description="Filter by license types")
    business_structures: Optional[List[str]] = Field(None, description="Filter by business structures")
    
    # Boolean filters
    has_federal_registration: Optional[bool] = Field(None, description="Filter companies with federal registration")
    has_website: Optional[bool] = Field(None, description="Filter companies with websites")
    has_email: Optional[bool] = Field(None, description="Filter companies with email")
    active_licenses_only: Optional[bool] = Field(True, description="Show only active licenses")
    
    # Numeric filters
    min_licenses: Optional[int] = Field(None, description="Minimum number of licenses")
    max_licenses: Optional[int] = Field(None, description="Maximum number of licenses")
    
    # Date filters
    licensed_after: Optional[str] = Field(None, description="Filter licenses issued after date (YYYY-MM-DD)")
    licensed_before: Optional[str] = Field(None, description="Filter licenses issued before date (YYYY-MM-DD)")

class SearchResponse(BaseModel):
    companies: List[CompanyResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: Dict[str, Any]
    search_time_ms: float

class SearchStats(BaseModel):
    total_companies: int
    total_licenses: int
    unique_license_types: int
    states_covered: int
    top_license_types: List[Dict[str, Union[str, int]]]
    top_states: List[Dict[str, Union[str, int]]]
    business_structures: List[Dict[str, Union[str, int]]]

# Database connection pool
class DatabaseManager:
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        """Initialize database connection pool"""
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")
        try:
            self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
            logger.info("✅ Database connection pool created")
        except Exception as e:
            logger.error(f"❌ Failed to create database pool: {e}")
            raise
    
    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("🔌 Database connection pool closed")

# Global database manager
db_manager = DatabaseManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db_manager.connect()
    yield
    # Shutdown
    await db_manager.disconnect()

# FastAPI app
app = FastAPI(
    title="NMLS Database Search API",
    description="Comprehensive search and filtering for NMLS Consumer Access database",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchService:
    """Service class for database search operations"""
    
    @staticmethod
    def build_search_query(filters: SearchFilters, page: int, page_size: int, 
                          sort_field: SortField, sort_order: SortOrder) -> tuple:
        """Build SQL query based on search filters"""
        
        # Base query with company and license aggregations
        base_query = """
        WITH company_stats AS (
            SELECT 
                c.id as company_id,
                c.nmls_id,
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
            c.nmls_id,
            c.company_name,
            c.business_structure,
            c.phone,
            c.email,
            c.website,
            c.federal_regulator,
            c.created_at,
            a.full_address as street_address,
            am.full_address as mailing_address,
            cs.total_licenses,
            cs.active_licenses,
            cs.license_types,
            cs.states_licensed
        FROM companies c
        LEFT JOIN company_stats cs ON c.id = cs.company_id
        LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
        LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
        """
        
        where_conditions = []
        params = []
        param_count = 0
        
        # Text search
        if filters.query:
            param_count += 1
            where_conditions.append(f"""
                (c.company_name ILIKE ${param_count} 
                 OR c.trade_names::text ILIKE ${param_count}
                 OR a.full_address ILIKE ${param_count}
                 OR am.full_address ILIKE ${param_count})
            """)
            params.append(f"%{filters.query}%")
        
        # State filter
        if filters.states:
            param_count += 1
            where_conditions.append(f"cs.states_licensed && ${param_count}")
            params.append(filters.states)
        
        # License type filter
        if filters.license_types:
            param_count += 1
            where_conditions.append(f"cs.license_types && ${param_count}")
            params.append(filters.license_types)
        
        # Business structure filter
        if filters.business_structures:
            param_count += 1
            where_conditions.append(f"c.business_structure = ANY(${param_count})")
            params.append(filters.business_structures)
        
        # Federal registration filter
        if filters.has_federal_registration is not None:
            if filters.has_federal_registration:
                where_conditions.append("c.federal_regulator IS NOT NULL")
            else:
                where_conditions.append("c.federal_regulator IS NULL")
        
        # Website filter
        if filters.has_website is not None:
            if filters.has_website:
                where_conditions.append("c.website IS NOT NULL AND c.website != ''")
            else:
                where_conditions.append("(c.website IS NULL OR c.website = '')")
        
        # Email filter
        if filters.has_email is not None:
            if filters.has_email:
                where_conditions.append("c.email IS NOT NULL AND c.email != ''")
            else:
                where_conditions.append("(c.email IS NULL OR c.email = '')")
        
        # License count filters
        if filters.min_licenses is not None:
            param_count += 1
            where_conditions.append(f"cs.total_licenses >= ${param_count}")
            params.append(filters.min_licenses)
        
        if filters.max_licenses is not None:
            param_count += 1
            where_conditions.append(f"cs.total_licenses <= ${param_count}")
            params.append(filters.max_licenses)
        
        # Add WHERE clause if conditions exist
        if where_conditions:
            base_query += " WHERE " + " AND ".join(where_conditions)
        
        # Add ORDER BY
        order_mapping = {
            "company_name": "c.company_name",
            "nmls_id": "c.nmls_id",
            "business_structure": "c.business_structure",
            "total_licenses": "cs.total_licenses",
            "created_at": "c.created_at"
        }
        
        order_field = order_mapping.get(sort_field.value, "c.company_name")
        base_query += f" ORDER BY {order_field} {sort_order.value.upper()}"
        
        # Add pagination
        param_count += 1
        params.append(page_size)
        param_count += 1
        params.append((page - 1) * page_size)
        base_query += f" LIMIT ${param_count - 1} OFFSET ${param_count}"
        
        return base_query, params
    
    @staticmethod
    def build_count_query(filters: SearchFilters) -> tuple:
        """Build count query for pagination"""
        
        base_query = """
        WITH company_stats AS (
            SELECT 
                c.id as company_id,
                c.nmls_id,
                COUNT(l.license_id) as total_licenses,
                ARRAY_AGG(DISTINCT l.license_type) FILTER (WHERE l.license_type IS NOT NULL) as license_types,
                ARRAY_AGG(DISTINCT SUBSTRING(a.state FROM 1 FOR 2)) FILTER (WHERE a.state IS NOT NULL) as states_licensed
            FROM companies c
            LEFT JOIN licenses l ON c.id = l.company_id
            LEFT JOIN addresses a ON c.id = a.company_id
            GROUP BY c.id, c.nmls_id
        )
        SELECT COUNT(DISTINCT c.nmls_id)
        FROM companies c
        LEFT JOIN company_stats cs ON c.id = cs.company_id
        LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
        LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
        """
        
        where_conditions = []
        params = []
        param_count = 0
        
        # Apply the same filters as main query (without ORDER BY and LIMIT)
        if filters.query:
            param_count += 1
            where_conditions.append(f"""
                (c.company_name ILIKE ${param_count} 
                 OR c.trade_names::text ILIKE ${param_count}
                 OR a.full_address ILIKE ${param_count}
                 OR am.full_address ILIKE ${param_count})
            """)
            params.append(f"%{filters.query}%")
        
        if filters.states:
            param_count += 1
            where_conditions.append(f"cs.states_licensed && ${param_count}")
            params.append(filters.states)
        
        if filters.license_types:
            param_count += 1
            where_conditions.append(f"cs.license_types && ${param_count}")
            params.append(filters.license_types)
        
        if filters.business_structures:
            param_count += 1
            where_conditions.append(f"c.business_structure = ANY(${param_count})")
            params.append(filters.business_structures)
        
        if filters.has_federal_registration is not None:
            if filters.has_federal_registration:
                where_conditions.append("c.federal_regulator IS NOT NULL")
            else:
                where_conditions.append("c.federal_regulator IS NULL")
        
        if filters.has_website is not None:
            if filters.has_website:
                where_conditions.append("c.website IS NOT NULL AND c.website != ''")
            else:
                where_conditions.append("(c.website IS NULL OR c.website = '')")
        
        if filters.has_email is not None:
            if filters.has_email:
                where_conditions.append("c.email IS NOT NULL AND c.email != ''")
            else:
                where_conditions.append("(c.email IS NULL OR c.email = '')")
        
        if filters.min_licenses is not None:
            param_count += 1
            where_conditions.append(f"cs.total_licenses >= ${param_count}")
            params.append(filters.min_licenses)
        
        if filters.max_licenses is not None:
            param_count += 1
            where_conditions.append(f"cs.total_licenses <= ${param_count}")
            params.append(filters.max_licenses)
        
        if where_conditions:
            base_query += " WHERE " + " AND ".join(where_conditions)
        
        return base_query, params

# API Endpoints
@app.get("/", response_model=Dict[str, str])
async def root():
    """API root endpoint"""
    return {
        "message": "NMLS Database Search API",
        "version": "1.0.0",
        "docs": "/docs",
        "search": "/search",
        "stats": "/stats"
    }

@app.get("/stats", response_model=SearchStats)
async def get_database_stats():
    """Get database statistics and overview"""
    try:
        async with db_manager.pool.acquire() as conn:
            # Basic counts
            total_companies = await conn.fetchval("SELECT COUNT(*) FROM companies")
            total_licenses = await conn.fetchval("SELECT COUNT(*) FROM licenses")
            unique_license_types = await conn.fetchval("SELECT COUNT(DISTINCT license_type) FROM licenses WHERE license_type IS NOT NULL")
            
            # States covered
            states_covered = await conn.fetchval("""
                SELECT COUNT(DISTINCT SUBSTRING(state FROM 1 FOR 2)) 
                FROM addresses 
                WHERE state IS NOT NULL
            """)
            
            # Top license types
            top_license_types = await conn.fetch("""
                SELECT license_type, COUNT(*) as count
                FROM licenses 
                WHERE license_type IS NOT NULL
                GROUP BY license_type
                ORDER BY count DESC
                LIMIT 10
            """)
            
            # Top states
            top_states = await conn.fetch("""
                SELECT SUBSTRING(state FROM 1 FOR 2) as state, COUNT(*) as count
                FROM addresses 
                WHERE state IS NOT NULL
                GROUP BY SUBSTRING(state FROM 1 FOR 2)
                ORDER BY count DESC
                LIMIT 10
            """)
            
            # Business structures
            business_structures = await conn.fetch("""
                SELECT business_structure, COUNT(*) as count
                FROM companies 
                WHERE business_structure IS NOT NULL
                GROUP BY business_structure
                ORDER BY count DESC
            """)
            
            return SearchStats(
                total_companies=total_companies,
                total_licenses=total_licenses,
                unique_license_types=unique_license_types,
                states_covered=states_covered,
                top_license_types=[{"name": row["license_type"], "count": row["count"]} for row in top_license_types],
                top_states=[{"name": row["state"], "count": row["count"]} for row in top_states],
                business_structures=[{"name": row["business_structure"], "count": row["count"]} for row in business_structures]
            )
            
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/search", response_model=SearchResponse)
async def search_companies(
    filters: SearchFilters,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_field: SortField = Query(SortField.company_name, description="Field to sort by"),
    sort_order: SortOrder = Query(SortOrder.asc, description="Sort order")
):
    """
    Search and filter companies with advanced options
    
    **Features:**
    - Text search across company names, trade names, addresses
    - Filter by states, license types, business structures
    - Boolean filters for federal registration, website, email
    - Numeric filters for license counts
    - Pagination and sorting
    - Performance optimized with proper indexing
    """
    start_time = datetime.now()
    
    try:
        async with db_manager.pool.acquire() as conn:
            # Get total count for pagination
            count_query, count_params = SearchService.build_count_query(filters)
            total_count = await conn.fetchval(count_query, *count_params)
            
            # Get paginated results
            search_query, search_params = SearchService.build_search_query(
                filters, page, page_size, sort_field, sort_order
            )
            
            rows = await conn.fetch(search_query, *search_params)
            
            # Convert to response models
            companies = []
            for row in rows:
                company = CompanyResponse(
                    nmls_id=row["nmls_id"],
                    company_name=row["company_name"],
                    business_structure=row["business_structure"],
                    phone=row["phone"],
                    email=row["email"],
                    website=row["website"],
                    street_address=row["street_address"],
                    mailing_address=row["mailing_address"],
                    total_licenses=row["total_licenses"] or 0,
                    active_licenses=row["active_licenses"] or 0,
                    license_types=row["license_types"] or [],
                    states_licensed=row["states_licensed"] or [],
                    federal_regulator=row["federal_regulator"],
                    created_at=row["created_at"]
                )
                companies.append(company)
            
            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size
            search_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return SearchResponse(
                companies=companies,
                total_count=total_count,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                filters_applied=filters.dict(exclude_unset=True),
                search_time_ms=round(search_time, 2)
            )
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/search/suggestions")
async def get_search_suggestions(
    query: str = Query(..., min_length=2, description="Search query for suggestions"),
    limit: int = Query(10, ge=1, le=50, description="Maximum suggestions to return")
):
    """Get search suggestions for autocomplete"""
    try:
        async with db_manager.pool.acquire() as conn:
            suggestions = await conn.fetch("""
                SELECT DISTINCT company_name, nmls_id
                FROM companies
                WHERE company_name ILIKE $1
                ORDER BY company_name
                LIMIT $2
            """, f"%{query}%", limit)
            
            return {
                "suggestions": [
                    {"company_name": row["company_name"], "nmls_id": row["nmls_id"]}
                    for row in suggestions
                ]
            }
            
    except Exception as e:
        logger.error(f"Suggestions error: {e}")
        raise HTTPException(status_code=500, detail=f"Suggestions failed: {str(e)}")

@app.get("/company/{nmls_id}", response_model=CompanyResponse)
async def get_company_details(nmls_id: str):
    """Get detailed information for a specific company"""
    try:
        async with db_manager.pool.acquire() as conn:
            row = await conn.fetchrow("""
                WITH company_stats AS (
                    SELECT 
                        c.id as company_id,
                        c.nmls_id,
                        COUNT(l.license_id) as total_licenses,
                        COUNT(CASE WHEN l.active = true THEN 1 END) as active_licenses,
                        ARRAY_AGG(DISTINCT l.license_type) FILTER (WHERE l.license_type IS NOT NULL) as license_types,
                        ARRAY_AGG(DISTINCT SUBSTRING(a.state FROM 1 FOR 2)) FILTER (WHERE a.state IS NOT NULL) as states_licensed
                    FROM companies c
                    LEFT JOIN licenses l ON c.id = l.company_id
                    LEFT JOIN addresses a ON c.id = a.company_id
                    WHERE c.nmls_id = $1
                    GROUP BY c.id, c.nmls_id
                )
                SELECT 
                    c.*,
                    cs.total_licenses,
                    cs.active_licenses,
                    cs.license_types,
                    cs.states_licensed,
                    a.full_address as street_address,
                    am.full_address as mailing_address
                FROM companies c
                LEFT JOIN company_stats cs ON c.id = cs.company_id
                LEFT JOIN addresses a ON c.id = a.company_id AND a.address_type = 'street'
                LEFT JOIN addresses am ON c.id = am.company_id AND am.address_type = 'mailing'
                WHERE c.nmls_id = $1
            """, nmls_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Company not found")
            
            return CompanyResponse(
                nmls_id=row["nmls_id"],
                company_name=row["company_name"],
                business_structure=row["business_structure"],
                phone=row["phone"],
                email=row["email"],
                website=row["website"],
                street_address=row["street_address"],
                mailing_address=row["mailing_address"],
                total_licenses=row["total_licenses"] or 0,
                active_licenses=row["active_licenses"] or 0,
                license_types=row["license_types"] or [],
                states_licensed=row["states_licensed"] or [],
                federal_regulator=row["federal_regulator"],
                created_at=row["created_at"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Company details error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get company details: {str(e)}")

@app.get("/company/{nmls_id}/licenses", response_model=List[LicenseResponse])
async def get_company_licenses(nmls_id: str):
    """Get all licenses for a specific company"""
    try:
        async with db_manager.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT l.*, c.company_name
                FROM licenses l
                JOIN companies c ON l.company_id = c.id
                WHERE c.nmls_id = $1
                ORDER BY l.active DESC, l.license_type
            """, nmls_id)
            
            return [
                LicenseResponse(
                    license_id=row["license_id"],
                    company_nmls_id=row["nmls_id"],
                    company_name=row["company_name"],
                    license_type=row["license_type"],
                    regulator=row["regulator"],
                    status=row["status"],
                    license_number=row["license_number"],
                    original_issue_date=row["original_issue_date"],
                    renewed_through=row["renewed_through"],
                    authorized_to_conduct_business=row["authorized_to_conduct_business"],
                    active=row["active"]
                )
                for row in rows
            ]
            
    except Exception as e:
        logger.error(f"Company licenses error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get company licenses: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "search_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 