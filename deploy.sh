#!/bin/bash

# NMLS Streamlit App Deployment Script
echo "🚀 NMLS Streamlit App Deployment"
echo "================================"

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
    git add .
    git commit -m "Initial commit: NMLS Streamlit app"
fi

# Check if remote exists
if ! git remote get-url origin > /dev/null 2>&1; then
    echo ""
    echo "📝 Next steps:"
    echo "1. Create a new repository on GitHub"
    echo "2. Run: git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git"
    echo "3. Run: git push -u origin main"
    echo ""
    echo "🌐 Then deploy to Streamlit Cloud:"
    echo "1. Go to https://streamlit.io/cloud"
    echo "2. Connect your GitHub account"
    echo "3. Deploy from your repository"
    echo "4. Configure credentials in the app sidebar"
else
    echo "Pushing to GitHub..."
    git push origin main
    echo ""
    echo "✅ Code pushed to GitHub!"
    echo "🌐 Deploy to Streamlit Cloud: https://streamlit.io/cloud"
fi

echo ""
echo "📋 Required for deployment:"
echo "- PostgreSQL database with NMLS data"
echo "- Anthropic API key (Claude AI)"
echo "- Optional: SixtyFour API key"
echo ""
echo "💡 Use the app's sidebar to configure these credentials!" 