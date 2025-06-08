#!/usr/bin/env python3
"""
Enhanced Search API Endpoints
FastAPI endpoints that integrate natural language processing with the existing search API.

Features:
- Natural language search endpoint
- Business intelligence dashboard
- Lender classification API
- Contact validation endpoints
- Query suggestions and autocomplete
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from natural_language_search import enhanced_search_api, QueryAnalysis, LenderType, QueryIntent
from search_api import SearchFilters, CompanyResponse, SearchResponse

# FastAPI app
app = FastAPI(
    title="Enhanced NMLS Search API with Natural Language Processing",
    description="AI-powered search for NMLS database with business intelligence",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models for API
class NaturalLanguageQuery(BaseModel):
    query: str = Field(..., description="Natural language search query")
    apply_business_filters: bool = Field(True, description="Apply Fido's business requirements")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Results per page")

class QueryAnalysisResponse(BaseModel):
    original_query: str
    intent: str
    confidence: float
    explanation: str
    business_critical_flags: List[str]
    filters_applied: Dict[str, Any]

class BusinessIntelligence(BaseModel):
    total: int
    lender_type_distribution: Dict[str, int]
    contact_statistics: Dict[str, int]
    high_value_targets: int
    business_recommendations: List[str]

class EnhancedSearchResponse(BaseModel):
    query_analysis: QueryAnalysisResponse
    companies: List[Dict[str, Any]]  # Enhanced company objects
    pagination: Dict[str, Any]
    business_intelligence: BusinessIntelligence

class LenderClassificationRequest(BaseModel):
    license_types: List[str] = Field(..., description="List of license types to classify")

class LenderClassificationResponse(BaseModel):
    lender_type: str
    confidence: float
    reasoning: str
    is_target_for_fido: bool

class ContactValidationRequest(BaseModel):
    phone: Optional[str] = Field(None, description="Phone number to validate")
    email: Optional[str] = Field(None, description="Email address to validate")

class ContactValidationResponse(BaseModel):
    phone_valid: bool
    email_valid: bool
    issues: List[str]
    recommendations: List[str]

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the enhanced search API"""
    await enhanced_search_api.initialize()

# API Endpoints

@app.get("/", response_model=Dict[str, str])
async def root():
    """API root endpoint with enhanced features"""
    return {
        "message": "Enhanced NMLS Database Search API with AI",
        "version": "2.0.0",
        "features": [
            "Natural language search",
            "Business intelligence",
            "Lender classification",
            "Contact validation",
            "Vector semantic search"
        ],
        "endpoints": {
            "natural_search": "/search/natural",
            "classify_lender": "/classify/lender",
            "validate_contact": "/validate/contact",
            "business_insights": "/insights/dashboard",
            "query_suggestions": "/search/suggestions/smart"
        }
    }

@app.post("/search/natural", response_model=EnhancedSearchResponse)
async def natural_language_search(request: NaturalLanguageQuery):
    """
    Perform natural language search with AI-powered query understanding
    
    **Features:**
    - Converts natural language to structured search
    - Automatic lender type classification
    - Business intelligence and recommendations
    - Contact information validation
    - Semantic similarity matching
    
    **Example queries:**
    - "Find personal loan companies in California with phone numbers"
    - "Show me consumer credit lenders that have email addresses"
    - "List companies that do payday loans but not mortgages"
    - "Find large lenders with more than 10 licenses in Texas"
    """
    try:
        result = await enhanced_search_api.natural_language_search(
            query=request.query,
            apply_business_filters=request.apply_business_filters,
            page=request.page,
            page_size=request.page_size
        )
        
        return EnhancedSearchResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Natural language search failed: {str(e)}")

@app.post("/classify/lender", response_model=LenderClassificationResponse)
async def classify_lender_type(request: LenderClassificationRequest):
    """
    Classify a lender based on their license types
    
    **Critical for Fido's business:**
    - Identifies unsecured personal lenders (TARGET)
    - Flags mortgage lenders (EXCLUDE)
    - Detects mixed-type lenders (REVIEW)
    """
    try:
        from natural_language_search import LenderClassifier
        
        lender_type = LenderClassifier.classify_company(request.license_types)
        
        # Generate reasoning
        unsecured_licenses = [lt for lt in request.license_types 
                            if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES]
        mortgage_licenses = [lt for lt in request.license_types 
                           if lt in LenderClassifier.MORTGAGE_LICENSES]
        
        if lender_type == LenderType.UNSECURED_PERSONAL:
            reasoning = f"Classified as unsecured personal lender based on: {', '.join(unsecured_licenses)}"
            confidence = 0.9
        elif lender_type == LenderType.MORTGAGE:
            reasoning = f"Classified as mortgage lender based on: {', '.join(mortgage_licenses)}"
            confidence = 0.9
        elif lender_type == LenderType.MIXED:
            reasoning = f"Mixed lender - Personal: {unsecured_licenses}, Mortgage: {mortgage_licenses}"
            confidence = 0.8
        else:
            reasoning = f"Unknown lender type - no clear classification from: {', '.join(request.license_types)}"
            confidence = 0.3
        
        return LenderClassificationResponse(
            lender_type=lender_type.value,
            confidence=confidence,
            reasoning=reasoning,
            is_target_for_fido=(lender_type in [LenderType.UNSECURED_PERSONAL, LenderType.MIXED])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lender classification failed: {str(e)}")

@app.post("/validate/contact", response_model=ContactValidationResponse)
async def validate_contact_information(request: ContactValidationRequest):
    """
    Validate contact information quality for outreach
    
    **Critical for Fido's outreach success:**
    - Validates phone number formats
    - Validates email address formats
    - Provides recommendations for data quality
    """
    try:
        from natural_language_search import ContactValidator
        
        phone_valid = ContactValidator.validate_phone(request.phone) if request.phone else False
        email_valid = ContactValidator.validate_email(request.email) if request.email else False
        
        issues = []
        recommendations = []
        
        if request.phone and not phone_valid:
            issues.append("Invalid phone number format")
            recommendations.append("Verify phone number follows US format (10-11 digits)")
        
        if request.email and not email_valid:
            issues.append("Invalid email format")
            recommendations.append("Verify email address format and domain")
        
        if not request.phone and not request.email:
            issues.append("No contact information provided")
            recommendations.append("At least one contact method (phone or email) is required for outreach")
        
        if phone_valid and email_valid:
            recommendations.append("Excellent - both phone and email available for outreach")
        elif phone_valid or email_valid:
            recommendations.append("Good - one contact method available, consider finding the missing one")
        
        return ContactValidationResponse(
            phone_valid=phone_valid,
            email_valid=email_valid,
            issues=issues,
            recommendations=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Contact validation failed: {str(e)}")

@app.get("/search/suggestions/smart")
async def get_smart_suggestions(
    query: str = Query(..., min_length=2, description="Partial query for suggestions"),
    limit: int = Query(10, ge=1, le=50, description="Maximum suggestions to return")
):
    """
    Get intelligent search suggestions based on natural language understanding
    
    **Features:**
    - Context-aware suggestions
    - Business-focused recommendations
    - Query completion and expansion
    """
    try:
        from natural_language_search import claude_client
        
        # Generate smart suggestions using Claude
        prompt = f"""
Given the partial search query "{query}", suggest {limit} complete, business-relevant search queries for an NMLS financial database.

Focus on queries that would help find:
1. Unsecured personal lenders (preferred)
2. Companies with contact information
3. Location-based searches
4. License-type filtering

Return suggestions as a JSON array of strings, ordered by business relevance.
Example: ["find personal loan companies in California", "show consumer credit lenders with emails"]

Query fragment: "{query}"
"""
        
        response = await claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse suggestions (simplified - in production, add better error handling)
        import json
        suggestions_text = response.content[0].text
        
        # Try to extract JSON array from response
        try:
            # Look for JSON array in the response
            import re
            json_match = re.search(r'\[(.*?)\]', suggestions_text, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group(0))
            else:
                # Fallback to simple suggestions
                suggestions = [
                    f"find personal loan companies matching {query}",
                    f"show consumer credit lenders with {query}",
                    f"list companies in {query} with contact info"
                ]
        except:
            suggestions = [
                f"search for companies with {query}",
                f"find lenders matching {query}",
                f"show companies in {query}"
            ]
        
        return {
            "suggestions": suggestions[:limit],
            "query_fragment": query,
            "suggestion_type": "ai_powered"
        }
        
    except Exception as e:
        # Fallback to simple suggestions
        return {
            "suggestions": [
                f"find companies with {query}",
                f"search for lenders containing {query}",
                f"list companies in {query}"
            ],
            "query_fragment": query,
            "suggestion_type": "fallback",
            "error": str(e)
        }

@app.get("/insights/dashboard")
async def get_business_insights_dashboard():
    """
    Get comprehensive business intelligence dashboard
    
    **Provides:**
    - Overall database statistics
    - Lender type distribution
    - Contact information coverage
    - Business recommendations
    """
    try:
        from search_api import db_manager
        
        async with db_manager.pool.acquire() as conn:
            # Get overall statistics
            total_companies = await conn.fetchval("SELECT COUNT(*) FROM companies")
            
            # Contact coverage
            with_email = await conn.fetchval("SELECT COUNT(*) FROM companies WHERE email IS NOT NULL AND email != ''")
            with_phone = await conn.fetchval("SELECT COUNT(*) FROM companies WHERE phone IS NOT NULL AND phone != ''")
            with_both = await conn.fetchval("SELECT COUNT(*) FROM companies WHERE email IS NOT NULL AND email != '' AND phone IS NOT NULL AND phone != ''")
            
            # License statistics
            total_licenses = await conn.fetchval("SELECT COUNT(*) FROM licenses")
            active_licenses = await conn.fetchval("SELECT COUNT(*) FROM licenses WHERE active = true")
            
            # Top license types
            top_license_types = await conn.fetch("""
                SELECT license_type, COUNT(*) as count
                FROM licenses
                WHERE license_type IS NOT NULL
                GROUP BY license_type
                ORDER BY count DESC
                LIMIT 10
            """)
            
            # Classify license types for business intelligence
            from natural_language_search import LenderClassifier
            
            unsecured_license_count = 0
            mortgage_license_count = 0
            
            for row in top_license_types:
                if row['license_type'] in LenderClassifier.UNSECURED_PERSONAL_LICENSES:
                    unsecured_license_count += row['count']
                elif row['license_type'] in LenderClassifier.MORTGAGE_LICENSES:
                    mortgage_license_count += row['count']
            
            # Generate business recommendations
            recommendations = []
            
            contact_coverage = (with_email + with_phone - with_both) / total_companies if total_companies > 0 else 0
            if contact_coverage < 0.5:
                recommendations.append("Low contact coverage - consider data enrichment services")
            
            if mortgage_license_count > unsecured_license_count:
                recommendations.append("Database contains more mortgage than personal lending licenses")
            
            if unsecured_license_count < total_licenses * 0.2:
                recommendations.append("Limited unsecured personal lending data - may need additional sources")
            
            return {
                "overview": {
                    "total_companies": total_companies,
                    "total_licenses": total_licenses,
                    "active_licenses": active_licenses,
                    "license_utilization": round(active_licenses / total_licenses * 100, 2) if total_licenses > 0 else 0
                },
                "contact_coverage": {
                    "companies_with_email": with_email,
                    "companies_with_phone": with_phone,
                    "companies_with_both": with_both,
                    "contact_coverage_percentage": round(contact_coverage * 100, 2)
                },
                "business_relevance": {
                    "unsecured_personal_licenses": unsecured_license_count,
                    "mortgage_licenses": mortgage_license_count,
                    "fido_relevance_score": round(unsecured_license_count / (unsecured_license_count + mortgage_license_count) * 100, 2) if (unsecured_license_count + mortgage_license_count) > 0 else 0
                },
                "top_license_types": [
                    {
                        "license_type": row['license_type'],
                        "count": row['count'],
                        "business_category": (
                            "target" if row['license_type'] in LenderClassifier.UNSECURED_PERSONAL_LICENSES
                            else "exclude" if row['license_type'] in LenderClassifier.MORTGAGE_LICENSES
                            else "unknown"
                        )
                    }
                    for row in top_license_types
                ],
                "recommendations": recommendations,
                "last_updated": datetime.now().isoformat()
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard insights failed: {str(e)}")

@app.get("/analyze/query")
async def analyze_query_intent(
    query: str = Query(..., description="Query to analyze"),
    return_filters: bool = Query(False, description="Whether to return the generated filters")
):
    """
    Analyze a natural language query without executing the search
    
    **Use cases:**
    - Query validation
    - Intent understanding
    - Filter preview
    - Confidence assessment
    """
    try:
        analysis = await enhanced_search_api.nlp.analyze_query(query)
        
        result = {
            "query": query,
            "analysis": {
                "intent": analysis.intent.value,
                "confidence": analysis.confidence,
                "explanation": analysis.explanation,
                "lender_type_preference": analysis.lender_type_preference.value if analysis.lender_type_preference else None,
                "semantic_query": analysis.semantic_query,
                "business_critical_flags": analysis.business_critical_flags
            }
        }
        
        if return_filters:
            result["generated_filters"] = analysis.filters.dict(exclude_unset=True)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query analysis failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "enhanced_search_endpoints:app",
        host="0.0.0.0",
        port=8001,  # Different port from original search API
        reload=True,
        log_level="info"
    ) 