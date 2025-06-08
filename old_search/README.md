# Legacy Search Modules

This folder contains the original search modules that were replaced by the unified search system.

## Files

- **`natural_language_search.py`** (919 lines) - Original AI-powered natural language processing
- **`search_api.py`** (682 lines) - Original database search and FastAPI endpoints  
- **`enhanced_search_endpoints.py`** (467 lines) - Additional FastAPI endpoints

## Why Moved

These modules were replaced by `unified_search.py` which consolidates all search functionality into a single, cleaner system. The Streamlit app now only uses `unified_search.py`.

## Status

- ❌ **Not used by current application**
- ✅ **Kept for reference and potential future use**
- ⚠️ **May have dependencies on removed PyTorch packages**

## Migration

All functionality from these modules has been integrated into:
- `unified_search.py` - Main search engine
- `streamlit_app.py` - UI and business logic

Date moved: June 8, 2025 