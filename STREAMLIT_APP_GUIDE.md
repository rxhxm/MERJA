# 🏦 NMLS Search Intelligence Platform

**AI-Powered Streamlit Application for Financial Services Database Search**

A comprehensive, user-friendly interface for searching and analyzing your NMLS database with Claude AI-powered natural language processing.

## 🌟 Features

### 🔍 **Natural Language Search**
- **AI-Powered Query Understanding**: Uses Claude Sonnet 4 to understand natural language queries
- **Business Intelligence**: Automatically classifies lenders as TARGET (unsecured personal) vs EXCLUDE (mortgage)
- **Smart Filtering**: Applies Fido's business requirements automatically
- **Confidence Scoring**: Shows AI confidence in query interpretation
- **Query Analysis**: Displays how the AI understood your search

### 📊 **Business Intelligence Dashboard**
- **Key Metrics**: Total companies, licenses, contact coverage
- **Visual Analytics**: Interactive charts for license types and geographic distribution
- **Business Relevance Scoring**: Companies ranked by value to Fido's business
- **Contact Coverage Analysis**: Email/phone availability statistics
- **Strategic Recommendations**: AI-generated business insights

### 🎯 **Advanced Search Capabilities**
- **Multi-dimensional Filtering**: State, license type, business structure, contact info
- **Lender Classification**: Automatic categorization for business relevance
- **Contact Validation**: Real-time validation of phone/email formats
- **Export Functions**: Download results as CSV for further analysis
- **Pagination**: Handle large result sets efficiently

### ⚙️ **Utilities & Tools**
- **Lender Type Classifier**: Determine if a company is relevant to Fido
- **Contact Validator**: Check phone/email format validity
- **Company Details Lookup**: Deep dive into specific NMLS entities
- **Data Export**: CSV download with business scoring

## 🚀 Quick Start

### 1. **Install Dependencies**
```bash
pip install -r requirements_streamlit.txt
```

### 2. **Run the Application**
```bash
# Option 1: Using the startup script (recommended)
python run_streamlit.py

# Option 2: Direct Streamlit launch
streamlit run streamlit_app.py
```

### 3. **Access the Application**
- Open your browser to: `http://localhost:8501`
- The app will automatically open in your default browser

## 📋 Usage Guide

### **Natural Language Search Examples**

**Finding Target Lenders:**
```
"Find personal loan companies in California with phone numbers"
"Show me consumer credit lenders that have email addresses"
"List companies that do payday loans but not mortgages"
```

**Geographic Searches:**
```
"Find lenders in Texas and Florida"
"Show companies licensed in multiple states"
"List large lenders with offices in New York"
```

**Contact-Focused Searches:**
```
"Find companies with both phone and email"
"Show lenders with websites for outreach"
"List companies with complete contact information"
```

**Business Intelligence Queries:**
```
"Find large lenders with more than 10 licenses"
"Show companies with consumer finance licenses"
"List established lenders with federal registration"
```

### **Understanding Results**

**Business Score (0-100):**
- **70-100**: 🟢 High-value targets for Fido
- **40-69**: 🟡 Medium relevance, review recommended
- **0-39**: 🔴 Low relevance or data quality issues

**Lender Type Classifications:**
- **✅ TARGET**: Unsecured personal lenders (Fido's focus)
- **❌ EXCLUDE**: Mortgage lenders (not relevant)
- **⚠️ MIXED**: Both personal and mortgage licenses
- **❓ UNKNOWN**: Unclear classification

**Contact Coverage:**
- **✅**: Valid contact information available
- **❌**: Missing or invalid contact data

## 🧠 AI-Powered Features

### **Query Analysis**
The AI analyzes your natural language input and provides:
- **Intent Recognition**: What type of search you're performing
- **Confidence Score**: How certain the AI is about its interpretation
- **Business Flags**: Warnings about potential issues
- **Filter Translation**: How your words become database filters

### **Business Intelligence**
Automatic analysis provides:
- **Target Identification**: Companies most relevant to Fido
- **Contact Quality Assessment**: Outreach readiness scoring
- **Market Analysis**: Industry segment breakdown
- **Strategic Recommendations**: AI-generated business insights

### **Smart Suggestions**
- **Query Completion**: AI suggests complete searches as you type
- **Business-Focused**: Suggestions prioritize Fido's needs
- **Context-Aware**: Learns from your search patterns

## 🎯 Page-by-Page Guide

### **🔍 Natural Language Search**
**Primary search interface with AI processing**

**Key Features:**
- Natural language query input
- Real-time AI analysis display
- Business intelligence summary
- Sortable, filterable results table
- Export capabilities

**Best Practices:**
- Use specific terms like "personal loans" vs generic "lending"
- Include location when relevant: "in California"
- Specify contact requirements: "with phone numbers"
- Mention business size: "large lenders" or "more than X licenses"

### **📊 Business Intelligence**
**Strategic dashboard for market analysis**

**Metrics Displayed:**
- Database overview statistics
- Contact coverage analysis
- License type distribution with business relevance
- Geographic distribution of companies
- Strategic recommendations for Fido

**Use Cases:**
- Market size assessment
- Data quality evaluation
- Target market identification
- Strategic planning support

### **🎯 Advanced Filters**
**Traditional database filtering interface**

**Filter Categories:**
- **Basic**: Company name, states, business structure
- **Licenses**: Count ranges, specific types, active status
- **Contact**: Email, phone, website availability
- **Federal**: Registration status

**When to Use:**
- Need precise control over search parameters
- Building complex multi-criteria searches
- Systematic data exploration
- Validation of natural language results

### **🏢 Company Details**
**Deep dive into specific companies**

**Information Displayed:**
- Complete company profile
- Full license portfolio
- Contact information validation
- Business relevance scoring
- Historical data trends

### **⚙️ Tools & Utilities**
**Specialized business tools**

**Lender Classification Tool:**
- Input: List of license types
- Output: Business relevance classification
- Use: Validate targeting decisions

**Contact Validation Tool:**
- Input: Phone numbers and email addresses
- Output: Format validation results
- Use: Ensure outreach data quality

## 🔧 Configuration

### **Environment Variables**
```bash
DATABASE_URL=postgresql://user:pass@host:port/db
ANTHROPIC_API_KEY=your_claude_api_key
```

### **Database Requirements**
- PostgreSQL with NMLS data
- Tables: companies, licenses, addresses
- Proper indexes for search performance

### **API Dependencies**
- Claude Sonnet 4 API access
- Vector search capabilities
- Database connection pooling

## 📈 Performance Tips

### **Search Optimization**
- Use specific terms rather than broad queries
- Apply business filters to reduce result sets
- Use pagination for large results
- Export data for offline analysis

### **Database Performance**
- Ensure proper database indexing
- Use connection pooling
- Monitor query performance
- Regular database maintenance

## 🛠️ Troubleshooting

### **Common Issues**

**"Database Connection Failed"**
- Check DATABASE_URL environment variable
- Verify network connectivity
- Confirm database credentials

**"Claude API Error"**
- Verify ANTHROPIC_API_KEY is set correctly
- Check API rate limits
- Ensure network access to Claude API

**"No Search Results"**
- Try broader search terms
- Disable business filters temporarily
- Check query analysis for issues
- Verify data exists in database

**"Slow Performance"**
- Reduce page size for large result sets
- Use more specific search criteria
- Check database indexing
- Monitor system resources

### **Getting Help**
1. Check the query analysis for AI interpretation issues
2. Use the advanced filters for precise control
3. Review business intelligence recommendations
4. Check the tools section for validation utilities

## 🎯 Business Value for Fido

### **Efficiency Gains**
- **10x Faster Searches**: Natural language vs manual filtering
- **Intelligent Targeting**: Automatic lender type classification
- **Quality Assurance**: Built-in contact validation
- **Export Ready**: CSV downloads for CRM integration

### **Strategic Insights**
- **Market Analysis**: Comprehensive industry landscape view
- **Target Identification**: AI-powered lead scoring
- **Data Quality**: Real-time contact information validation
- **Competitive Intelligence**: Market segment analysis

### **Risk Mitigation**
- **Relevance Filtering**: Automatic exclusion of non-target lenders
- **Data Validation**: Contact information quality checks
- **Business Logic**: Built-in understanding of Fido's requirements
- **Audit Trail**: Complete query analysis and reasoning

## 🚀 Next Steps

1. **Start with Natural Language Search** - Try example queries
2. **Explore Business Intelligence** - Understand your market
3. **Use Advanced Filters** - For precise requirements
4. **Validate Results** - Use tools for quality assurance
5. **Export and Act** - Download leads for outreach

---

**Built for Fido's Success** 🎯
*Transforming 50,000 HTML files into actionable business intelligence* 