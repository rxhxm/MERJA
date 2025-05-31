# NMLS Search & Intelligence Platform

A comprehensive Streamlit application for searching and analyzing the NMLS database with AI-powered natural language processing and company enrichment capabilities.

## Features

- 🔍 **Natural Language Search**: Query the NMLS database using plain English
- 🤖 **AI-Powered Analysis**: Claude AI understands search intent and provides business intelligence
- 📊 **Company Classification**: Automatic classification of lenders (unsecured personal, mortgage, mixed)
- 🎯 **Business Scoring**: Relevance scoring for business needs
- 📈 **Data Enrichment**: Integration with SixtyFour API for additional company intelligence
- 👥 **Contact Discovery**: Find key decision makers and contacts
- 📱 **Responsive UI**: Clean, modern interface optimized for business use

## Live Demo

🚀 **Deploy your own instance using the instructions below**

## Quick Start

1. **Search Companies**: Enter natural language queries like "Find personal loan companies in California"
2. **Apply Filters**: Use business filters to prioritize target companies
3. **Analyze Results**: Review business intelligence and company classifications
4. **Enrich Data**: Select companies for enrichment with additional business data
5. **Export Data**: Download enriched company and contact data

## Architecture

- **Frontend**: Streamlit web application
- **Database**: PostgreSQL (Supabase recommended)
- **AI Services**: Claude AI, SixtyFour API
- **Data Processing**: Async Python with comprehensive error handling

## Environment Variables

The following environment variables are required:

- `DATABASE_URL`: PostgreSQL connection string
- `SIXTYFOUR_API_KEY`: API key for company enrichment (optional)
- `ANTHROPIC_API_KEY`: Claude AI API key (optional, enables natural language search)

## Local Development

```bash
# Clone the repository
git clone https://github.com/your-username/nmls-search.git
cd nmls-search

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp env.example .env
# Edit .env with your actual values

# Run the application
python run_streamlit.py
# OR directly with streamlit
streamlit run streamlit_app.py
```

## Deployment on Streamlit Cloud

### Step 1: Prepare Your Repository

1. Fork or clone this repository to your GitHub account
2. Ensure all files are committed to your Git repository
3. Make sure your `.env` file is NOT committed (it should be in `.gitignore`)

### Step 2: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "Deploy an app"
3. Select your repository
4. Set main file path: `streamlit_app.py`
5. Configure environment variables (see below)

### Step 3: Environment Variables Setup

In Streamlit Cloud, add these secrets in the app settings:

```toml
# Database configuration (REQUIRED)
DATABASE_URL = "postgresql://username:password@host:port/database"

# API keys (OPTIONAL - features will be disabled if not provided)
SIXTYFOUR_API_KEY = "your-sixtyfour-api-key"
ANTHROPIC_API_KEY = "your-anthropic-api-key"
```

### Step 4: Database Setup

You'll need a PostgreSQL database with NMLS data. Options include:

1. **Supabase** (Recommended for ease of use):
   - Create a free account at [supabase.com](https://supabase.com)
   - Create a new project
   - Use the provided connection string as your `DATABASE_URL`

2. **Other PostgreSQL providers**:
   - AWS RDS, Google Cloud SQL, Azure Database, etc.
   - Any PostgreSQL instance with public access

The database should contain tables for NMLS companies and licenses. See the database schema section below for details.

## Database Schema

The application expects a PostgreSQL database with the following main tables:

- `companies`: Company information and metadata
- `licenses`: License details and relationships
- Additional tables for contacts, business structures, etc.

Key fields used by the application:
- `companies.name`, `companies.phone`, `companies.email`, `companies.website`
- `licenses.license_type`, `licenses.state`, `licenses.status`

## API Integration

### SixtyFour API (Optional)
- Company enrichment and intelligence
- Contact discovery
- Business classification
- Get API key from SixtyFour to enable these features

### Claude AI (Optional)
- Natural language query processing
- Intent analysis
- Business recommendations
- Get API key from Anthropic to enable natural language search

## Performance Considerations

- **Async Processing**: All database and API calls are asynchronous
- **Connection Pooling**: Efficient database connection management
- **Rate Limiting**: Respects API rate limits
- **Pagination**: Handles large result sets efficiently
- **Caching**: Streamlit caching for improved performance

## Security

- Environment variables for sensitive data
- Input validation and sanitization
- Secure database connections
- API key protection

## Features That Work Without API Keys

Even without optional API keys, the application provides:
- Full database search and filtering
- Company and license information display
- Data export capabilities
- Basic business intelligence

## Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Verify your `DATABASE_URL` is correct
   - Ensure your database allows connections from Streamlit Cloud IPs
   - Check if your database is running and accessible

2. **Module Import Errors**
   - Ensure all dependencies are in `requirements.txt`
   - Check Python version compatibility

3. **Natural Language Search Not Working**
   - Verify `ANTHROPIC_API_KEY` is set correctly
   - Check API key permissions and credits

4. **Enrichment Features Disabled**
   - Verify `SIXTYFOUR_API_KEY` is set correctly
   - Check API key permissions

### Getting Help

For issues or questions:
1. Check the error messages in the application
2. Review the logs in Streamlit Cloud
3. Ensure all environment variables are set correctly
4. Verify database connectivity

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - feel free to use this project for your own purposes.

---

Built with ❤️ using Streamlit, Python, and modern web technologies. 