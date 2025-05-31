# NMLS Streamlit Search Application

A powerful Streamlit application for searching and analyzing NMLS (Nationwide Multistate Licensing System) data with AI-powered natural language search capabilities.

## 🚀 Quick Deploy

[![Deploy to Streamlit Cloud](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io/cloud)

1. **Fork this repository**
2. **Connect to Streamlit Cloud**
3. **Configure credentials in the app sidebar**
4. **Start searching!**

## ✨ Features

- **🔍 Natural Language Search**: Search using plain English queries
- **🤖 AI-Powered Analysis**: Leverage Claude AI for intelligent data analysis
- **🏢 Company Classification**: Automatic categorization of financial services companies
- **📊 Business Intelligence Scoring**: Comprehensive company evaluation metrics
- **🔗 Data Enrichment**: Enhanced company information and contact discovery
- **⚙️ Flexible Configuration**: Support for both UI-based and environment variable configuration

## 🛠️ Quick Start

### Option 1: UI Configuration (Recommended)

1. **Deploy to Streamlit Cloud**:
   - Fork this repository
   - Connect your GitHub account to [Streamlit Cloud](https://streamlit.io/cloud)
   - Deploy the app directly from your fork

2. **Configure via UI**:
   - Open the deployed app
   - Use the sidebar configuration panel to enter your credentials:
     - Database URL (PostgreSQL connection string)
     - Anthropic API Key (for Claude AI)
     - SixtyFour API Key (optional, for enhanced features)

3. **Start Searching**:
   - Use natural language queries like "Find credit unions in Texas"
   - Explore AI-powered company analysis and insights

### Option 2: Environment Variables (Production)

1. **Set up your environment**:
   ```bash
   cp env.example .env
   # Edit .env with your actual credentials
   ```

2. **For Streamlit Cloud**:
   ```bash
   cp secrets.toml.example .streamlit/secrets.toml
   # Edit secrets.toml with your credentials
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run locally**:
   ```bash
   streamlit run streamlit_app.py
   ```

## 🔧 Required Services

### Database (Required)
You need a PostgreSQL database with NMLS data. Options:
- **Supabase** (Recommended for free tier): [https://supabase.com](https://supabase.com)
- **Neon**: [https://neon.tech](https://neon.tech)
- **Railway**: [https://railway.app](https://railway.app)
- **Your own PostgreSQL instance**

### AI Services (Required)
- **Anthropic Claude API**: Get your API key at [https://console.anthropic.com](https://console.anthropic.com)

### Optional Services
- **SixtyFour API**: For enhanced data enrichment features

## ⚙️ Configuration

### Environment Variables
```bash
DATABASE_URL=postgresql://username:password@host:port/database
ANTHROPIC_API_KEY=sk-ant-api03-...
SIXTYFOUR_API_KEY=your_sixtyfour_key  # Optional
```

### Streamlit Cloud Secrets
```toml
[connections.postgresql]
url = "postgresql://username:password@host:port/database"

[api_keys]
anthropic = "sk-ant-api03-..."
sixtyfour = "your_sixtyfour_key"  # Optional
```

## 🏗️ Application Architecture

```
streamlit_app.py              # Main Streamlit application
├── natural_language_search.py   # AI-powered search logic
├── search_api.py             # Database query interface
└── enrichment_service.py     # Data enrichment features
```

## 🎯 Key Features

### Natural Language Search
Query examples:
- "Find all mortgage companies in California"
- "Show me credit unions with assets over $100M"  
- "List collection agencies licensed in Texas"
- "What are the top personal loan companies?"

### AI Analysis
- Company business model analysis
- Risk assessment
- Market positioning insights
- Regulatory compliance overview

### Data Export
- CSV export of search results
- Detailed company reports
- Analysis summaries

## 🚀 Deployment Options

### Streamlit Cloud (Recommended)
1. Fork this repository
2. Connect to Streamlit Cloud
3. Configure secrets in the app settings
4. Deploy automatically

### Other Platforms
- **Heroku**: Add `Procfile` with `web: streamlit run streamlit_app.py --server.port=$PORT`
- **Railway**: Configure build and start commands
- **Render**: Use Python environment with Streamlit

## 📁 Files Included

- `streamlit_app.py` - Main application with UI and configuration
- `natural_language_search.py` - AI-powered search functionality
- `search_api.py` - Database interface and query logic
- `enrichment_service.py` - Data enrichment and company intelligence
- `requirements.txt` - Python dependencies
- `packages.txt` - System packages for Streamlit Cloud
- `env.example` - Environment variable template
- `secrets.toml.example` - Streamlit secrets template

## 🆘 Support

- Check the configuration sidebar for setup help
- Verify your database connection and API keys
- Ensure your database has the required NMLS tables
- For issues, check the error messages in the app

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

---

**Ready to deploy?** Click the "Deploy to Streamlit Cloud" button above and start searching NMLS data with AI! 🎉 