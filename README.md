# NMLS Search Intelligence Platform 🏦

A sophisticated AI-powered search and analysis platform for the Nationwide Multistate Licensing System (NMLS) database. This application combines natural language processing, advanced filtering, and business intelligence to provide comprehensive insights into financial institutions and lenders.

## 🌟 Features

### 🔍 **Natural Language Search**
- Ask questions in plain English about NMLS lenders
- AI-powered query understanding with Claude AI
- Smart context-aware search suggestions

### 🎯 **Advanced Filtering & Analysis**
- Filter by states, license types, business size
- Geographic and demographic analysis
- Business intelligence dashboard with real-time insights

### 🤖 **AI-Powered Classification**
- Automatic lender categorization (Target, Exclude, Mixed)
- Business scoring based on multiple factors
- Contact validation and verification

### 📊 **Business Intelligence**
- Interactive dashboards and visualizations
- Export capabilities (CSV, Excel)
- Comprehensive analytics and reporting

### 🔗 **API Integration**
- RESTful API endpoints
- Asynchronous processing for large datasets
- Real-time data enrichment services

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- PostgreSQL database (optional for full functionality)
- Claude AI API key (for natural language features)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/rxhxm/MERJ.git
   cd MERJ
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements_streamlit.txt
   ```

3. **Run the application:**
   ```bash
   python run_streamlit.py
   ```
   
   Or directly with Streamlit:
   ```bash
   streamlit run streamlit_app.py
   ```

4. **Access the application:**
   Open your browser and navigate to `http://localhost:8501`

## 📁 Project Structure

```
MERJ/
├── streamlit_app.py              # Main Streamlit application
├── run_streamlit.py              # Application startup script
├── natural_language_search.py    # AI-powered search engine
├── search_api.py                 # Core search API and database operations
├── enhanced_search_endpoints.py  # Advanced search endpoints
├── enrichment_service.py         # Data enrichment and validation
├── fast_chunked_processor.py     # High-performance data processing
├── nmls_html_extractor.py        # Web scraping and data extraction
├── configure_env.py              # Environment configuration
├── requirements_streamlit.txt    # Streamlit app dependencies
├── requirements_nlp.txt          # NLP-specific dependencies
├── requirements.txt              # Core dependencies
├── database/                     # Database schemas and migrations
├── context/                      # AI context and prompts
└── usage/                        # Usage examples and documentation
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file or set the following environment variables:

```bash
# Database Configuration (optional)
DATABASE_URL=postgresql://username:password@host:port/database

# AI Configuration
ANTHROPIC_API_KEY=your_claude_api_key_here
```

### Database Setup (Optional)

While the application can run without a database, full functionality requires PostgreSQL:

1. Set up a PostgreSQL database
2. Configure the `DATABASE_URL` environment variable
3. Run database migrations (if applicable)

## 🎯 Usage Examples

### Natural Language Queries

```python
# Example queries you can try:
"Show me personal loan companies in California"
"Find consumer lenders in Texas with valid contact info"
"List all installment loan companies with high business scores"
"Companies offering small loans in Florida"
```

### API Usage

```python
from search_api import SearchService, SearchFilters

# Initialize search service
service = SearchService()

# Create filters
filters = SearchFilters(
    states=["CA", "TX"],
    license_types=["Consumer Loan License"],
    min_business_score=0.7
)

# Perform search
results = await service.search(filters)
```

## 🧠 AI & Machine Learning

The platform leverages several AI technologies:

- **Claude AI** for natural language understanding
- **Sentence Transformers** for semantic search
- **Custom classification models** for lender categorization
- **Contact validation algorithms** using pattern recognition

## 📊 Business Intelligence Features

- **Lender Classification**: Automatic categorization of financial institutions
- **Business Scoring**: Multi-factor scoring algorithm for business viability
- **Geographic Analysis**: State and regional market analysis
- **Contact Validation**: Phone and email verification
- **Export Capabilities**: CSV and Excel export with custom formatting

## 🔒 Security & Privacy

- No sensitive data stored in repository
- API keys managed through environment variables
- Database connections use secure protocols
- Input validation and sanitization

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/rxhxm/MERJ/issues) page
2. Create a new issue with detailed information
3. Include logs and error messages when applicable

## 🔮 Future Enhancements

- [ ] Real-time data streaming
- [ ] Advanced ML models for predictive analytics
- [ ] Mobile application
- [ ] API rate limiting and authentication
- [ ] Enhanced data visualization options
- [ ] Integration with additional financial databases

## 📈 Performance

The platform is optimized for:
- **Large datasets**: Efficient chunked processing
- **Real-time search**: Async operations and caching
- **Scalability**: Modular architecture for easy scaling
- **Memory efficiency**: Optimized data structures and algorithms

---

Built with ❤️ using Python, Streamlit, and AI technologies. 