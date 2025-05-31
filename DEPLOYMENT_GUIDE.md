# Streamlit Cloud Deployment Guide

## 📋 Pre-Deployment Checklist

Before deploying to Streamlit Cloud, ensure you have:

- [x] All code committed to a Git repository (GitHub, GitLab, or Bitbucket)
- [x] `requirements.txt` file with all dependencies
- [x] `.streamlit/config.toml` for app configuration
- [x] `packages.txt` for system packages
- [x] Environment variables documented
- [x] Database accessible from the internet

## 🚀 Step-by-Step Deployment

### 1. Prepare Your Repository

Ensure your repository has this structure:
```
your-repo/
├── streamlit_app.py          # Main Streamlit app
├── requirements.txt          # Python dependencies
├── packages.txt             # System packages
├── .streamlit/
│   └── config.toml          # Streamlit configuration
├── enrichment_service.py    # Enrichment service module
├── search_api.py           # Search API module
├── natural_language_search.py # NL search module
└── README.md               # Documentation
```

### 2. Deploy to Streamlit Cloud

1. **Go to Streamlit Cloud**: Visit [share.streamlit.io](https://share.streamlit.io)

2. **Sign in**: Use your GitHub, GitLab, or Google account

3. **Deploy a new app**:
   - Click "Deploy an app"
   - Select "From existing repo"
   - Choose your repository
   - Set branch: `main` (or your default branch)
   - Set main file path: `streamlit_app.py`

4. **Advanced settings** (optional):
   - App URL: Choose a custom subdomain
   - Python version: 3.11 (recommended)

### 3. Configure Environment Variables

In the Streamlit Cloud app settings, add these secrets:

```toml
[env]
# Database connection (required)
DATABASE_URL = "postgresql://user:password@host:port/database"

# API keys
SIXTYFOUR_API_KEY = "your-sixtyfour-api-key"
ANTHROPIC_API_KEY = "your-anthropic-api-key"  # Optional but recommended

# Optional configuration
DEBUG = "False"
LOG_LEVEL = "INFO"
```

### 4. Database Configuration

Your PostgreSQL database must be:
- **Accessible from the internet** (Streamlit Cloud will connect externally)
- **SSL enabled** (required for security)
- **Proper firewall rules** allowing connections from Streamlit Cloud IPs

For Supabase (recommended):
1. Go to your Supabase project settings
2. Navigate to Database → Connection pooling
3. Enable connection pooling
4. Use the pooled connection string in `DATABASE_URL`

Example Supabase connection string:
```
postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
```

## 🔧 Troubleshooting Common Issues

### Issue 1: Module Import Errors
**Problem**: `ModuleNotFoundError` for custom modules
**Solution**: Ensure all your custom Python files are in the repository root

### Issue 2: Database Connection Timeout
**Problem**: Database connection fails
**Solution**: 
- Check if your database allows external connections
- Verify the `DATABASE_URL` format
- Use connection pooling for better performance

### Issue 3: Memory Limits
**Problem**: App crashes due to memory usage
**Solution**:
- Reduce concurrent connections in `enrichment_service.py`
- Use pagination for large datasets
- Optimize DataFrame operations

### Issue 4: API Rate Limits
**Problem**: External API calls failing
**Solution**:
- Implement proper error handling
- Add retry logic with exponential backoff
- Cache API responses when possible

## ⚡ Performance Optimization

### 1. Database Optimization
```python
# In your code, use connection pooling
DATABASE_URL = os.getenv('DATABASE_URL')
pool = await asyncpg.create_pool(
    DATABASE_URL, 
    min_size=1,      # Reduced for Streamlit Cloud
    max_size=3       # Conservative limit
)
```

### 2. Streamlit Caching
Add caching decorators for expensive operations:
```python
@st.cache_data(ttl=300)  # Cache for 5 minutes
def expensive_operation():
    # Your expensive computation
    pass
```

### 3. Async Operations
Your app already uses async properly - maintain this pattern for API calls.

## 📊 Monitoring and Maintenance

### 1. App Health Monitoring
- Check Streamlit Cloud logs regularly
- Monitor app performance metrics
- Set up alerts for errors

### 2. Database Monitoring
- Monitor connection pool usage
- Check query performance
- Monitor storage usage

### 3. API Usage Tracking
- Track SixtyFour API usage
- Monitor Claude API costs
- Implement usage analytics

## 🔒 Security Best Practices

### 1. Environment Variables
- ✅ Store all secrets in Streamlit secrets
- ❌ Never commit API keys to Git
- ✅ Use strong, unique passwords

### 2. Database Security
- ✅ Use SSL connections
- ✅ Implement proper user permissions
- ✅ Regular security updates

### 3. API Security
- ✅ Validate all input data
- ✅ Implement rate limiting
- ✅ Monitor for unusual patterns

## 🎯 Production Readiness Checklist

Before going live:

- [ ] All environment variables configured
- [ ] Database connection tested
- [ ] Error handling tested
- [ ] Performance under load tested
- [ ] Security review completed
- [ ] Documentation updated
- [ ] Monitoring set up
- [ ] Backup strategy in place

## 📱 Post-Deployment Steps

1. **Test the deployed app thoroughly**
2. **Share the URL with stakeholders**
3. **Set up monitoring and alerts**
4. **Plan for regular updates**
5. **Gather user feedback**

## 🆘 Getting Help

If you encounter issues:

1. **Check Streamlit Cloud logs** in the app management interface
2. **Review this troubleshooting guide**
3. **Check Streamlit Community Forums** for similar issues
4. **Contact support** if needed

## 📈 Scaling Considerations

As your app grows:

- **Database**: Consider upgrading to higher-tier plans
- **API Limits**: Monitor and upgrade API plans as needed
- **Performance**: Profile and optimize bottlenecks
- **Features**: Plan feature rollouts carefully

---

**🎉 Congratulations!** Your NMLS Search application is now live on Streamlit Cloud! 