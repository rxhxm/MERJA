#!/usr/bin/env python3
"""
Natural Language Search Interface for NMLS Database
Converts natural language queries to structured search filters using Claude Sonnet 4.

Features:
- Natural language query processing
- Automatic lender type classification (unsecured personal vs mortgage)
- Vector semantic search
- Contact validation and filtering
- Query intent understanding
- Business logic enforcement
"""

import os
import re
import json
import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

import asyncio
import httpx
from anthropic import AsyncAnthropic, Anthropic
from pydantic import BaseModel, Field
import numpy as np

# Try to import sentence_transformers with fallback
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None
    logging.warning("sentence_transformers not available - vector search will be disabled")

import asyncpg
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - Use environment variables only
DATABASE_URL = os.getenv('DATABASE_URL')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Anthropic client (optional)
claude_client = None
if ANTHROPIC_API_KEY:
    claude_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

# Import SearchFilters from the existing search API
from search_api import SearchFilters, CompanyResponse, SearchResponse, SortField, SortOrder, SearchService

class QueryIntent(str, Enum):
    """Types of search intents"""
    FIND_LENDERS = "find_lenders"
    FIND_COMPANIES = "find_companies"
    FILTER_BY_LOCATION = "filter_by_location"
    FILTER_BY_LICENSES = "filter_by_licenses"
    FILTER_BY_CONTACT = "filter_by_contact"
    FIND_SPECIFIC_COMPANY = "find_specific_company"
    ANALYZE_MARKET = "analyze_market"

class LenderType(str, Enum):
    """Critical business classification of lender types"""
    UNSECURED_PERSONAL = "unsecured_personal"  # TARGET: What Fido wants
    MORTGAGE = "mortgage"                      # EXCLUDE: Not wanted
    MIXED = "mixed"                           # REVIEW: Has both types
    UNKNOWN = "unknown"                       # INVESTIGATE: Unclear classification

@dataclass
class QueryAnalysis:
    """Results of natural language query analysis"""
    intent: QueryIntent
    filters: SearchFilters
    lender_type_preference: Optional[LenderType]
    semantic_query: Optional[str]
    confidence: float
    explanation: str
    business_critical_flags: List[str]

class LenderClassifier:
    """Classifies companies as unsecured personal vs mortgage lenders"""
    
    # License types that indicate UNSECURED PERSONAL lending (TARGET)
    UNSECURED_PERSONAL_LICENSES = {
        # Core Consumer Lending Licenses (from actual database)
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
        
        # Sales Finance and Installment Lending
        "Sales Finance License",
        "Sales Finance Company License",
        "Sales Finance Agency License",
        "Installment Lender License",
        "Installment Loan License",
        "Installment Loan Company License",
        "Retail Installment Sales Finance Company",
        "Retail Installment Sales and Finance Company License",
        
        # Small Loans and Money Lending
        "Small Loan License",
        "Small Loan Company License",
        "Small Loan Lender License",
        "Small Lender License",
        "Money Lender License",
        "Supervised Lender License",
        "Supervised Loan License",
        "Payday Lender License",
        "Short-Term Lender License",
        "Title Pledge Lender License",
        
        # General Lending (non-mortgage)
        "Lender License",
        "Regulated Lender License",
        "Licensed Lender License",
        "Commercial Lender License",
        
        # Credit Services and Collection
        "Collection Agency License", 
        "Credit Services Business License",
        "Credit Services Organization License",
        "Credit Availability Company License",
        "Flexible Credit License",
        
        # Alternative Financial Services
        "Check Casher License",
        "Check Casher with Small Loan Endorsement",
        "Check Cashing License",
        "Check Cashing Company License",
        "Check Cashing Services License",
        "Money Transmitter License",
        "Check Seller, Money Transmitter License",
        
        # Specialty Lending
        "Motor Vehicle Sales Finance Company License",
        "Motor Vehicle Sales Finance License",
        "Insurance Premium Finance Company License",
        "Insurance Premium Finance License",
        "Premium Finance Company License",
        "Title Lender Registration",
        "Property Tax Lender License",
        
        # Student and Education Loans (personal lending)
        "Student Loan Servicer License",
        "Automatic Federal Student Loan Servicer License",
        "Federal Student Loan Servicer License",
        "Qualified Education Loan Servicer License",
        
        # Loan Servicing and Processing
        "Loan Servicer License",
        "Third Party Loan Servicer License",
        "Loan Processing Company Registration",
        "Loan Broker License",
        "Loan Solicitation License",
        
        # Legacy names that might still be in use
        "Personal Loan License",
        "Finance Company License",
        "Sale of Checks and Money Transmitter License"
    }
    
    # License types that indicate MORTGAGE lending (EXCLUDE)
    MORTGAGE_LICENSES = {
        # Primary Mortgage Lending Licenses
        "Mortgage Loan Company License",
        "Mortgage Lender License",
        "Mortgage Lending License",
        "Mortgage Broker License",
        "Mortgage Company License",
        "Mortgage Servicer License",
        "Mortgage Lender/Servicer License",
        "Mortgage Broker/Lender License",
        "Mortgage Lender/Broker License",
        "Mortgage Loan Servicer Registration",
        "Mortgage Loan Originator Company License",
        
        # Residential Mortgage Licenses
        "Residential Mortgage Lender License",
        "Residential Mortgage Lending License",
        "Residential Mortgage Lending Act License",
        "Residential Mortgage Lending Act Certificate of Registration",
        "Residential Mortgage Loan Servicer",
        "Residential Mortgage Loan Servicer Registration",
        "Correspondent Residential Mortgage Lender License",
        "Non-Residential Mortgage Lender License",
        
        # First and Second Mortgage Licenses
        "1st Mortgage Broker License",
        "1st Mortgage Broker/Lender License",
        "1st Mortgage Broker/Lender/Servicer License",
        "1st Mortgage Broker/Lender Registrant",
        "1st Mortgage Broker/Lender/Servicer Registrant",
        "2nd Mortgage Broker/Lender License",
        "2nd Mortgage Broker/Lender Registrant",
        "2nd Mortgage Broker/Lender/Servicer Registrant",
        
        # Mortgage Originator Licenses
        "Mortgage Loan Originator License",
        "Real Estate Corporation License Mortgage Loan Originator (MLO) License Endorsement",
        "Real Estate Broker License Mortgage Loan Originator (MLO) License Endorsement",
        
        # Auxiliary and Correspondent Services
        "Auxiliary Mortgage Loan Activity Company License",
        "Mortgage Correspondent Lender License",
        "Mortgage Loan Correspondent License",
        "Exempt Mortgage Loan Servicer Registration",
        
        # Specialty Mortgage
        "Reverse Mortgage (HECM) Lending",
        "Reverse Mortgage Lending Dual Authority",
        "Mortgage Consumer Discount Company License",
        
        # Commercial and Other
        "Commercial Mortgage Broker License"
    }
    
    @classmethod
    def classify_company(cls, license_types: List[str]) -> LenderType:
        """Classify a company based on its license types"""
        if not license_types:
            return LenderType.UNKNOWN
            
        has_unsecured = any(license_type in cls.UNSECURED_PERSONAL_LICENSES for license_type in license_types)
        has_mortgage = any(license_type in cls.MORTGAGE_LICENSES for license_type in license_types)
        
        if has_unsecured and has_mortgage:
            return LenderType.MIXED
        elif has_unsecured:
            return LenderType.UNSECURED_PERSONAL
        elif has_mortgage:
            return LenderType.MORTGAGE
        else:
            return LenderType.UNKNOWN

class ContactValidator:
    """Validates and filters companies by contact information quality"""
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format"""
        if not phone:
            return False
        # Remove all non-digits
        digits = re.sub(r'\D', '', phone)
        # US phone numbers should have 10 or 11 digits
        return len(digits) in [10, 11]
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format"""
        if not email:
            return False
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None
    
    @classmethod
    def has_valid_contact_info(cls, company: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if company has valid contact information"""
        issues = []
        has_phone = cls.validate_phone(company.get('phone', ''))
        has_email = cls.validate_email(company.get('email', ''))
        
        if not has_phone:
            issues.append("missing_valid_phone")
        if not has_email:
            issues.append("missing_valid_email")
            
        return (has_phone or has_email), issues

class VectorSearchService:
    """Semantic vector search for company names and descriptions"""
    
    def __init__(self):
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
        else:
            self.model = None
        self.pool = None
    
    async def connect(self):
        """Initialize database connection for vector search"""
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set")
        try:
            self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        except Exception as e:
            logger.error(f"Vector search database connection failed: {e}")
            raise
    
    async def semantic_search(self, query: str, limit: int = 50) -> List[str]:
        """Perform semantic search on company names and trade names"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning("Vector search disabled - sentence_transformers not available")
            return []
            
        try:
            # Get company names and trade names
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT nmls_id, company_name, trade_names
                    FROM companies
                    WHERE company_name IS NOT NULL
                    LIMIT 10000
                """)
            
            # Create text corpus
            texts = []
            nmls_ids = []
            
            for row in rows:
                company_text = row['company_name']
                if row['trade_names']:
                    # Add trade names as additional context
                    trade_names = ' '.join(row['trade_names']) if isinstance(row['trade_names'], list) else str(row['trade_names'])
                    company_text += f" {trade_names}"
                
                texts.append(company_text)
                nmls_ids.append(row['nmls_id'])
            
            # Encode query and corpus
            query_embedding = self.model.encode([query])
            corpus_embeddings = self.model.encode(texts)
            
            # Calculate cosine similarity
            similarities = np.dot(query_embedding, corpus_embeddings.T)[0]
            
            # Get top matches
            top_indices = np.argsort(similarities)[-limit:][::-1]
            top_nmls_ids = [nmls_ids[i] for i in top_indices if similarities[i] > 0.3]  # Threshold
            
            return top_nmls_ids
            
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

class NaturalLanguageProcessor:
    """Processes natural language queries using Claude Sonnet 4"""
    
    def __init__(self):
        self.vector_search = VectorSearchService()
    
    async def initialize(self):
        """Initialize services"""
        await self.vector_search.connect()
    
    async def analyze_query(self, query: str) -> QueryAnalysis:
        """Analyze natural language query and convert to structured filters"""
        
        # Get available data for context
        context = await self._get_search_context()
        
        # Create comprehensive prompt for Claude
        prompt = self._create_analysis_prompt(query, context)
        
        try:
            # Call Claude Sonnet 4
            response = await claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",  # Using latest available model
                max_tokens=2000,
                temperature=0.1,  # Low temperature for consistent parsing
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Parse Claude's response
            analysis_result = self._parse_claude_response(response.content[0].text)
            
            # Enhance with vector search if semantic query detected
            if analysis_result.semantic_query:
                similar_companies = await self.vector_search.semantic_search(analysis_result.semantic_query)
                if similar_companies:
                    # Add semantic results to filters
                    existing_nmls_ids = analysis_result.filters.dict().get('nmls_ids', [])
                    if existing_nmls_ids:
                        analysis_result.filters.nmls_ids = list(set(existing_nmls_ids + similar_companies))
                    else:
                        # Create a new field for semantic matches (would need to extend SearchFilters)
                        analysis_result.business_critical_flags.append(f"semantic_matches_found:{len(similar_companies)}")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Claude analysis error: {e}")
            # Return fallback analysis
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
        """Create comprehensive prompt for Claude analysis"""
        
        return f"""
You are an expert NMLS financial database analyst helping convert natural language queries into structured search filters.

CRITICAL BUSINESS CONTEXT:
- The client (Fido) ONLY wants UNSECURED PERSONAL LENDERS for outreach
- They DO NOT want MORTGAGE LENDERS  
- Phone numbers and emails are CRITICAL for outreach success
- Every license must be captured - missing licenses is a major business risk

AVAILABLE LICENSE TYPES:
{json.dumps(list(LenderClassifier.UNSECURED_PERSONAL_LICENSES | LenderClassifier.MORTGAGE_LICENSES), indent=2)}

AVAILABLE STATES: {context['states']}
AVAILABLE BUSINESS STRUCTURES: {context['business_structures']}

USER QUERY: "{query}"

Please analyze this query and return a JSON response with the following structure:

{{
    "intent": "find_lenders|find_companies|filter_by_location|filter_by_licenses|filter_by_contact|find_specific_company|analyze_market",
    "filters": {{
        "query": "text search terms or null",
        "states": ["state codes"] or null,
        "license_types": ["specific license types"] or null,
        "business_structures": ["structures"] or null,
        "has_federal_registration": true/false/null,
        "has_website": true/false/null,
        "has_email": true/false/null,
        "min_licenses": number or null,
        "max_licenses": number or null,
        "licensed_after": "YYYY-MM-DD" or null,
        "licensed_before": "YYYY-MM-DD" or null
    }},
    "lender_type_preference": "unsecured_personal|mortgage|mixed|unknown",
    "semantic_query": "terms for semantic search" or null,
    "confidence": 0.0-1.0,
    "explanation": "clear explanation of interpretation",
    "business_critical_flags": ["missing_contact_risk", "mortgage_lender_risk", "license_completeness_risk", etc.]
}}

ANALYSIS RULES:
1. If query mentions personal loans, consumer credit, payday loans, installment loans -> "unsecured_personal"
2. If query mentions mortgages, home loans, real estate -> "mortgage" 
3. If query asks for contact info, set has_email=true and has_phone=true
4. For location queries, convert to state codes (e.g., "California" -> ["CA"])
5. Flag any risks that could impact Fido's business goals

Respond ONLY with valid JSON, no additional text.
"""
    
    async def _get_search_context(self) -> Dict:
        """Get available search options for context"""
        try:
            async with self.vector_search.pool.acquire() as conn:
                states = await conn.fetch("SELECT DISTINCT SUBSTRING(state FROM 1 FOR 2) as state FROM addresses WHERE state IS NOT NULL ORDER BY state")
                business_structures = await conn.fetch("SELECT DISTINCT business_structure FROM companies WHERE business_structure IS NOT NULL ORDER BY business_structure")
                
                return {
                    "states": [row['state'] for row in states],
                    "business_structures": [row['business_structure'] for row in business_structures]
                }
        except Exception as e:
            logger.error(f"Context fetch error: {e}")
            return {"states": [], "business_structures": []}
    
    def _parse_claude_response(self, response_text: str) -> QueryAnalysis:
        """Parse Claude's JSON response into QueryAnalysis object"""
        try:
            # Extract JSON from response (handle potential markdown formatting)
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                json_text = response_text.strip()
            
            data = json.loads(json_text)
            
            # Create SearchFilters object
            filters_data = data.get('filters', {})
            filters = SearchFilters(**{k: v for k, v in filters_data.items() if v is not None})
            
            return QueryAnalysis(
                intent=QueryIntent(data.get('intent', 'find_companies')),
                filters=filters,
                lender_type_preference=LenderType(data.get('lender_type_preference', 'unknown')),
                semantic_query=data.get('semantic_query'),
                confidence=float(data.get('confidence', 0.5)),
                explanation=data.get('explanation', 'Analysis completed'),
                business_critical_flags=data.get('business_critical_flags', [])
            )
            
        except Exception as e:
            logger.error(f"Response parsing error: {e}")
            # Return minimal fallback
            return QueryAnalysis(
                intent=QueryIntent.FIND_COMPANIES,
                filters=SearchFilters(),
                lender_type_preference=LenderType.UNKNOWN,
                semantic_query=None,
                confidence=0.2,
                explanation=f"Parsing error: {str(e)}",
                business_critical_flags=["parsing_error"]
            )

class EnhancedSearchAPI:
    """Enhanced search API with natural language processing"""
    
    def __init__(self):
        self.nlp = NaturalLanguageProcessor()
        self.classifier = LenderClassifier()
        self.contact_validator = ContactValidator()
    
    async def initialize(self):
        """Initialize the enhanced search API"""
        await self.nlp.initialize()
    
    async def natural_language_search(
        self, 
        query: str,
        apply_business_filters: bool = True,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Perform natural language search with business logic enforcement
        
        Args:
            query: Natural language query
            apply_business_filters: Whether to apply Fido's business requirements
            page: Page number for pagination
            page_size: Results per page
            
        Returns:
            Enhanced search results with business intelligence
        """
        
        # Analyze the query
        analysis = await self.nlp.analyze_query(query)
        
        # Apply business filters if requested
        if apply_business_filters:
            analysis.filters = await self._apply_business_filters(analysis.filters, analysis.lender_type_preference)
        
        # Execute search using existing search API
        from search_api import SearchService, db_manager
        
        try:
            async with db_manager.pool.acquire() as conn:
                # Get total count
                count_query, count_params = SearchService.build_count_query(analysis.filters)
                total_count = await conn.fetchval(count_query, *count_params)
                
                # Get results
                search_query, search_params = SearchService.build_search_query(
                    analysis.filters, page, page_size, 
                    SearchService.SortField.company_name, SearchService.SortOrder.asc
                )
                
                rows = await conn.fetch(search_query, *search_params)
                
                # Enhance results with business intelligence
                enhanced_companies = []
                for row in rows:
                    company_data = dict(row)
                    
                    # Classify lender type
                    lender_classification = self.classifier.classify_company(
                        company_data.get('license_types', [])
                    )
                    
                    # Validate contact info
                    has_valid_contact, contact_issues = self.contact_validator.has_valid_contact_info(company_data)
                    
                    # Create enhanced company response
                    enhanced_company = {
                        **company_data,
                        "lender_type": lender_classification.value,
                        "has_valid_contact": has_valid_contact,
                        "contact_issues": contact_issues,
                        "business_score": self._calculate_business_score(
                            lender_classification, has_valid_contact, company_data
                        )
                    }
                    
                    enhanced_companies.append(enhanced_company)
                
                # Sort by business score if applying business filters
                if apply_business_filters:
                    enhanced_companies.sort(key=lambda x: x['business_score'], reverse=True)
                
                # Calculate statistics
                stats = self._calculate_result_stats(enhanced_companies, analysis)
                
                return {
                    "query_analysis": {
                        "original_query": query,
                        "intent": analysis.intent.value,
                        "confidence": analysis.confidence,
                        "explanation": analysis.explanation,
                        "business_critical_flags": analysis.business_critical_flags
                    },
                    "filters_applied": analysis.filters.dict(exclude_unset=True),
                    "companies": enhanced_companies,
                    "pagination": {
                        "total_count": total_count,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": (total_count + page_size - 1) // page_size
                    },
                    "business_intelligence": stats
                }
                
        except Exception as e:
            logger.error(f"Enhanced search error: {e}")
            raise
    
    async def _apply_business_filters(self, filters: SearchFilters, lender_preference: LenderType) -> SearchFilters:
        """Apply Fido's business requirements to search filters"""
        
        # Ensure contact information is prioritized
        if not filters.has_email and not filters.has_website:
            filters.has_email = True  # Prefer email for outreach
        
        # Filter by lender type if specified
        if lender_preference == LenderType.UNSECURED_PERSONAL:
            if not filters.license_types:
                filters.license_types = list(LenderClassifier.UNSECURED_PERSONAL_LICENSES)
            else:
                # Intersect with unsecured personal licenses
                filters.license_types = [
                    lt for lt in filters.license_types 
                    if lt in LenderClassifier.UNSECURED_PERSONAL_LICENSES
                ]
        elif lender_preference == LenderType.MORTGAGE:
            # This should be rare given Fido's requirements, but handle it
            if not filters.license_types:
                filters.license_types = list(LenderClassifier.MORTGAGE_LICENSES)
        
        return filters
    
    def _calculate_business_score(
        self, 
        lender_type: LenderType, 
        has_valid_contact: bool, 
        company_data: Dict
    ) -> float:
        """Calculate business relevance score for Fido"""
        
        score = 0.0
        
        # Lender type scoring (most important)
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
        score += min(license_count * 2, 20.0)  # Cap at 20 points
        
        return min(score, 100.0)  # Cap at 100
    
    def _calculate_result_stats(self, companies: List[Dict], analysis: QueryAnalysis) -> Dict:
        """Calculate business intelligence statistics"""
        
        total = len(companies)
        if total == 0:
            return {"total": 0}
        
        # Lender type distribution
        lender_types = {}
        contact_stats = {"valid_contact": 0, "email_only": 0, "phone_only": 0, "no_contact": 0}
        high_value_targets = 0
        
        for company in companies:
            # Lender type counting
            lender_type = company.get('lender_type', 'unknown')
            lender_types[lender_type] = lender_types.get(lender_type, 0) + 1
            
            # Contact statistics
            has_email = self.contact_validator.validate_email(company.get('email', ''))
            has_phone = self.contact_validator.validate_phone(company.get('phone', ''))
            
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
            "business_recommendations": self._generate_recommendations(lender_types, contact_stats, analysis)
        }
    
    def _generate_recommendations(self, lender_types: Dict, contact_stats: Dict, analysis: QueryAnalysis) -> List[str]:
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
        
        # Business critical flags
        for flag in analysis.business_critical_flags:
            if "missing_contact_risk" in flag:
                recommendations.append("Priority: Validate contact information before outreach")
            elif "license_completeness_risk" in flag:
                recommendations.append("Warning: Some licenses may be missing from results")
        
        return recommendations

# Initialize global enhanced search API
enhanced_search_api = EnhancedSearchAPI()

async def main():
    """Example usage and testing"""
    await enhanced_search_api.initialize()
    
    # Test queries
    test_queries = [
        "Find personal loan companies in California with phone numbers",
        "Show me consumer credit lenders that have email addresses",
        "List mortgage companies in Texas",  # Should be flagged as non-target
        "Find large lenders with more than 10 licenses",
        "Show companies that do payday loans in New York",
        "Find all financial companies with valid contact information"
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        try:
            result = await enhanced_search_api.natural_language_search(
                query=query,
                apply_business_filters=True,
                page=1,
                page_size=5
            )
            
            print(f"Intent: {result['query_analysis']['intent']}")
            print(f"Confidence: {result['query_analysis']['confidence']}")
            print(f"Explanation: {result['query_analysis']['explanation']}")
            print(f"Found: {result['pagination']['total_count']} companies")
            print(f"High-value targets: {result['business_intelligence']['high_value_targets']}")
            
            if result['business_intelligence']['business_recommendations']:
                print("Recommendations:")
                for rec in result['business_intelligence']['business_recommendations']:
                    print(f"  - {rec}")
                    
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 