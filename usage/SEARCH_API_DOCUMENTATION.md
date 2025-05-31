# 🔍 NMLS Database Search & Filtering System

## Overview

A comprehensive FastAPI-based search and filtering system for the NMLS Consumer Access database containing **10,761 companies** and **62,757 licenses** across **52 states** with **473 different license types**.

## 🚀 Quick Start

### 1. Set up Environment
```bash
# Copy environment template
cp env.example .env
# Edit .env with your database credentials
```

### 2. Start the API Server
```bash
python search_api.py
```

### 3. Open the Frontend
Open `search_frontend.html` in your browser to access the web interface.

### 4. API Documentation
Visit `http://localhost:8000/docs` for interactive API documentation.

## 📊 Database Statistics

- **Total Companies**: 10,761
- **Total Licenses**: 62,757  
- **License Types**: 473 unique types
- **States Covered**: 52 (all US states + territories)

## 🔧 API Endpoints

### Base URL: `http://localhost:8000`

### 1. **GET /** - API Information
Returns basic API information and available endpoints.

### 2. **GET /stats** - Database Statistics
```json
{
  "total_companies": 10761,
  "total_licenses": 62757,
  "unique_license_types": 473,
  "states_covered": 52,
  "top_license_types": [...],
  "top_states": [...],
  "business_structures": [...]
}
```

### 3. **POST /search** - Advanced Company Search

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `page_size` (int): Items per page (1-100, default: 20)
- `sort_field` (enum): Field to sort by
  - `company_name` (default)
  - `nmls_id`
  - `business_structure`
  - `total_licenses`
  - `created_at`
- `sort_order` (enum): `asc` (default) or `desc`

**Request Body (SearchFilters):**
```json
{
  "query": "bank",                           // Text search
  "states": ["CA", "TX"],                    // State filter
  "license_types": ["Mortgage Lender"],      // License type filter
  "business_structures": ["Corporation"],     // Business structure filter
  "has_federal_registration": true,          // Boolean filters
  "has_website": true,
  "has_email": true,
  "min_licenses": 1,                         // Numeric filters
  "max_licenses": 100,
  "licensed_after": "2020-01-01",           // Date filters
  "licensed_before": "2023-12-31"
}
```

**Response:**
```json
{
  "companies": [...],
  "total_count": 502,
  "page": 1,
  "page_size": 20,
  "total_pages": 26,
  "filters_applied": {...},
  "search_time_ms": 1346.81
}
```

### 4. **GET /search/suggestions** - Autocomplete
**Parameters:**
- `query` (string): Search term (min 2 chars)
- `limit` (int): Max suggestions (1-50, default: 10)

### 5. **GET /company/{nmls_id}** - Company Details
Returns detailed information for a specific company.

### 6. **GET /company/{nmls_id}/licenses** - Company Licenses
Returns all licenses for a specific company.

## 🎯 Search Features

### Text Search
- **Company Names**: Full-text search across company names
- **Trade Names**: Search through trade names and aliases
- **Addresses**: Search street and mailing addresses
- **Case-insensitive**: Automatic ILIKE matching

### Advanced Filters

#### Geographic Filters
- **States**: Filter by one or multiple states (e.g., CA, TX, NY)
- **Multi-state companies**: Find companies licensed in multiple states

#### License Filters
- **License Types**: Filter by specific license types
- **License Count**: Min/max number of licenses
- **Active Status**: Show only active licenses

#### Business Filters
- **Business Structure**: Corporation, LLC, Bank, Credit Union, etc.
- **Federal Registration**: Companies with/without federal oversight
- **Contact Information**: Companies with websites, email addresses

#### Date Filters
- **License Issue Date**: Filter by when licenses were issued
- **Date Ranges**: Custom date range filtering

### Performance Features
- **Fast Search**: Optimized queries with proper indexing
- **Pagination**: Efficient handling of large result sets
- **Search Time Tracking**: Response time monitoring
- **Connection Pooling**: Async database connections

## 🌐 Web Interface Features

### Modern UI
- **Responsive Design**: Works on desktop and mobile
- **Real-time Search**: Instant results as you type
- **Filter Interface**: Easy-to-use filter controls
- **Pagination**: Navigate through large result sets

### Search Capabilities
- **Text Search Box**: Main search input with autocomplete
- **Filter Panels**: 
  - State selection (multi-select)
  - Business structure dropdown
  - License count input
  - Federal registration toggle
- **Results Display**:
  - Company cards with key information
  - License types and states
  - Contact information
  - Click for detailed view

### Statistics Dashboard
- **Live Stats**: Real-time database statistics
- **Visual Indicators**: Company and license counts
- **Coverage Information**: States and license types covered

## 📈 Example Searches

### 1. Find Banks in California
```json
{
  "query": "bank",
  "states": ["CA"],
  "business_structures": ["Bank"]
}
```

### 2. Large Mortgage Lenders
```json
{
  "license_types": ["Mortgage Lender"],
  "min_licenses": 10,
  "has_federal_registration": true
}
```

### 3. Companies with Websites
```json
{
  "has_website": true,
  "has_email": true,
  "states": ["NY", "CA", "TX"]
}
```

### 4. Recent License Activity
```json
{
  "licensed_after": "2023-01-01",
  "min_licenses": 5
}
```

## 🔧 Technical Implementation

### Database Schema
- **Companies Table**: Main company information
- **Licenses Table**: License details (linked by company_id)
- **Addresses Table**: Street and mailing addresses (linked by company_id)

### Key Technologies
- **FastAPI**: Modern Python web framework
- **AsyncPG**: Async PostgreSQL driver
- **Pydantic**: Data validation and serialization
- **PostgreSQL**: Database with advanced querying
- **HTML/CSS/JavaScript**: Frontend interface

### Performance Optimizations
- **Connection Pooling**: Efficient database connections
- **Async Operations**: Non-blocking database queries
- **Indexed Searches**: Optimized database indexes
- **Pagination**: Memory-efficient result handling

## 🚀 Deployment Ready

### Production Considerations
- **Environment Variables**: Secure database configuration
- **CORS Support**: Cross-origin requests enabled
- **Error Handling**: Comprehensive error responses
- **Logging**: Detailed operation logging
- **Scalability**: Connection pooling and async operations

### API Documentation
- **OpenAPI/Swagger**: Auto-generated documentation at `/docs`
- **Type Safety**: Full Pydantic model validation
- **Response Models**: Structured JSON responses

## 📊 Performance Metrics

### Search Performance
- **Average Search Time**: ~1.3 seconds for complex queries
- **Database Size**: 10K+ companies, 60K+ licenses
- **Concurrent Users**: Supports multiple simultaneous searches
- **Memory Efficient**: Pagination prevents memory overload

### Scalability
- **Connection Pool**: 1-10 concurrent database connections
- **Async Architecture**: Non-blocking operations
- **Stateless Design**: Easy horizontal scaling

## 🎯 Use Cases

### Business Intelligence
- **Market Research**: Find competitors in specific markets
- **Compliance Tracking**: Monitor licensing requirements
- **Due Diligence**: Research potential partners/acquisitions

### Regulatory Compliance
- **License Verification**: Confirm company licensing status
- **Geographic Coverage**: Understand market presence
- **Federal Oversight**: Identify federally regulated entities

### Sales & Marketing
- **Lead Generation**: Find companies in target markets
- **Contact Discovery**: Companies with websites/emails
- **Market Segmentation**: Filter by business structure/size

## 🔮 Future Enhancements

### Planned Features
- **Vector Search**: Semantic similarity search
- **Export Functionality**: CSV/Excel export of results
- **Advanced Analytics**: Trend analysis and reporting
- **API Rate Limiting**: Production-ready rate limiting
- **Caching Layer**: Redis caching for frequent queries

### Integration Possibilities
- **CRM Integration**: Export to Salesforce, HubSpot
- **Compliance Tools**: Integration with regulatory systems
- **Business Intelligence**: Connect to Tableau, PowerBI
- **Notification System**: Alerts for license changes

---

## 🏆 Deliverable Summary

✅ **Complete Search System**: Full-featured search and filtering API  
✅ **Web Interface**: Modern, responsive frontend  
✅ **Performance Optimized**: Fast queries with proper indexing  
✅ **Production Ready**: Error handling, logging, documentation  
✅ **Scalable Architecture**: Async operations and connection pooling  
✅ **Comprehensive Documentation**: API docs and user guides  

**Total Processing**: 50,000+ HTML files → 10,761 companies + 62,757 licenses  
**Search Capability**: Text, geographic, license-based, and advanced filtering  
**Response Time**: Sub-2 second search across entire database  
**Coverage**: All US states and territories with 473 license types  

This search and filtering system provides a powerful, production-ready solution for exploring and analyzing the NMLS Consumer Access database with enterprise-grade performance and usability. 