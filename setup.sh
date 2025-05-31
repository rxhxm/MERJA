#!/bin/bash

echo "🚀 Setting up NMLS Streamlit App"
echo "================================"

# Copy credentials file to .env
if [ -f "credentials.env" ]; then
    echo "📋 Setting up environment variables..."
    cp credentials.env .env
    echo "✅ Copied credentials.env to .env"
else
    echo "❌ credentials.env file not found!"
    exit 1
fi

# Install requirements
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 To run the app:"
echo "   streamlit run streamlit_app.py"
echo ""
echo "🌐 Or deploy to Streamlit Cloud:"
echo "   https://streamlit.io/cloud"
echo ""
echo "⚠️  Security Note: The .env file contains real credentials."
echo "   Keep it secure and don't commit it to public repositories." 