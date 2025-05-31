#!/bin/bash

# NMLS Search Platform - Deployment Setup Script
# This script helps prepare your repository for deployment to Streamlit Cloud

echo "🚀 Setting up NMLS Search Platform for deployment..."

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "📦 Initializing Git repository..."
    git init
    echo "✅ Git repository initialized"
else
    echo "✅ Git repository already exists"
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp env.example .env
    echo "⚠️  Please edit .env file with your actual credentials"
    echo "✅ .env file created"
else
    echo "✅ .env file already exists"
fi

# Add all files to git (except those in .gitignore)
echo "📁 Adding files to Git..."
git add .

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo "✅ No changes to commit"
else
    echo "💾 Committing changes..."
    git commit -m "Initial commit: NMLS Search Platform ready for deployment"
    echo "✅ Changes committed"
fi

echo ""
echo "🎉 Setup complete! Next steps:"
echo ""
echo "1. 📝 Edit your .env file with actual credentials:"
echo "   - DATABASE_URL (required)"
echo "   - SIXTYFOUR_API_KEY (optional)"
echo "   - ANTHROPIC_API_KEY (optional)"
echo ""
echo "2. 🌐 Create a GitHub repository and push your code:"
echo "   git remote add origin https://github.com/your-username/your-repo-name.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "3. 🚀 Deploy to Streamlit Cloud:"
echo "   - Go to https://share.streamlit.io"
echo "   - Click 'Deploy an app'"
echo "   - Select your GitHub repository"
echo "   - Set main file: streamlit_app.py"
echo "   - Add your secrets using the template in secrets.toml.example"
echo ""
echo "4. ✅ Your app will be live at: https://your-app-name.streamlit.app"
echo ""
echo "📚 For detailed instructions, see README.md" 