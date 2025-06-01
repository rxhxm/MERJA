# NMLS Database Search & Intelligence Platform

A comprehensive Streamlit app for searching and analyzing NMLS database with AI-powered natural language processing.

## Features

- **Natural Language Search**: Search for lenders using plain English queries
- **Advanced Filtering**: Filter by states, lender types, and more
- **License State Mapping**: See which states each license type covers
- **Business Intelligence**: AI-powered classification of lender types
- **Contact Validation**: Identify companies with valid contact information
- **Export Capabilities**: Download results as CSV

## Deployment

This app is designed to be deployed on Streamlit Cloud.

### Environment Variables

Set the following environment variable in your Streamlit Cloud secrets:

```toml
DATABASE_URL = "your_postgresql_connection_string"
```

### Local Development

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up your `.env` file with `DATABASE_URL`
4. Run: `streamlit run streamlit_app.py`

## Usage

1. Enter your search query (e.g., "personal loan companies in California")
2. Use filters to refine results by state and lender type
3. View license breakdown with state information
4. Export results for further analysis

## Key Features

- **🎯 Target Identification**: Automatically identifies unsecured personal loan lenders
- **❌ Mortgage Filtering**: Flags mortgage-focused companies
- **📍 State Mapping**: Shows which states each license type covers
- **📊 Business Scoring**: Scores companies based on relevance and data quality 