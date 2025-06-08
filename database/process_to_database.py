#!/usr/bin/env python3
"""
Process NMLS HTML Files Directly to Database
All-in-one script that extracts data from HTML files and loads directly into Supabase
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Import our modules
from extractors.nmls_html_extractor import NMLSHTMLExtractor
from database.database_loader import DatabaseLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nmls_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """Main processing function"""
    parser = argparse.ArgumentParser(description="Process NMLS HTML files directly to Supabase database")
    parser.add_argument("input_path", help="Input directory containing HTML files")
    parser.add_argument("-m", "--max-files", type=int, help="Maximum number of files to process (for testing)")
    parser.add_argument("-p", "--pattern", default="*.html", help="File pattern to match (default: *.html)")
    parser.add_argument("--connection-string", help="Database connection string", 
                       default=os.getenv('DATABASE_URL'))
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for database commits (default: 100)")
    parser.add_argument("--markdown-output", help="Directory to save markdown files (optional)")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check if database connection is available
    if not args.connection_string:
        logger.error("Database connection string required. Set DATABASE_URL environment variable or use --connection-string")
        return 1
    
    # Check input path
    input_path = Path(args.input_path)
    if not input_path.exists():
        logger.error(f"Input path does not exist: {input_path}")
        return 1
    
    logger.info("🚀 Starting NMLS HTML to Database Processing")
    logger.info("=" * 60)
    logger.info(f"Input path: {input_path}")
    logger.info(f"File pattern: {args.pattern}")
    logger.info(f"Max files: {args.max_files or 'No limit'}")
    logger.info(f"Batch size: {args.batch_size}")
    if args.markdown_output:
        logger.info(f"Markdown output: {args.markdown_output}")
    
    try:
        # Initialize extractor and database loader
        extractor = NMLSHTMLExtractor()
        loader = DatabaseLoader(args.connection_string)
        
        # Connect to database
        loader.connect()
        logger.info("✅ Connected to Supabase database")
        
        # Find HTML files
        if input_path.is_file():
            html_files = [input_path]
        else:
            html_files = list(input_path.rglob(args.pattern))
            if args.max_files:
                html_files = html_files[:args.max_files]
        
        logger.info(f"📁 Found {len(html_files)} HTML files to process")
        
        # Process files in batches
        processed = 0
        batch_companies = []
        all_companies_for_markdown = []  # Store all companies for markdown generation
        
        for i, file_path in enumerate(html_files, 1):
            try:
                # Extract company data
                company_data = extractor.extract_from_file(str(file_path))
                
                # Store for markdown generation if requested
                if args.markdown_output and company_data.nmls_id:
                    all_companies_for_markdown.append(company_data)
                
                # Only add companies with valid NMLS IDs for database
                if company_data.nmls_id:
                    batch_companies.append(company_data)
                else:
                    logger.warning(f"Skipping file without NMLS ID: {file_path}")
                
                # Process batch when it's full or at the end
                if len(batch_companies) >= args.batch_size or i == len(html_files):
                    if batch_companies:
                        # Load batch to database
                        batch_stats = loader.load_companies(batch_companies)
                        processed += len(batch_companies)
                        
                        logger.info(f"✅ Processed batch: {len(batch_companies)} companies")
                        logger.info(f"📊 Total processed: {processed}/{len(html_files)}")
                        
                        # Clear batch
                        batch_companies = []
                
                # Log progress every 100 files
                if i % 100 == 0:
                    logger.info(f"🔄 Progress: {i}/{len(html_files)} files processed")
                    
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                continue
        
        # Generate markdown files if requested
        if args.markdown_output and all_companies_for_markdown:
            logger.info("\n📝 Generating markdown files...")
            extractor.save_to_markdown(all_companies_for_markdown, args.markdown_output)
        
        # Final statistics
        logger.info("\n" + "=" * 60)
        logger.info("🎉 Processing Complete!")
        logger.info("=" * 60)
        
        extractor_stats = extractor.stats
        loader_stats = loader.stats
        
        logger.info("📈 Extraction Statistics:")
        logger.info(f"  Files processed: {extractor_stats['processed']}")
        logger.info(f"  Successful extractions: {extractor_stats['successful']}")
        logger.info(f"  Extraction errors: {extractor_stats['errors']}")
        
        logger.info("📊 Database Statistics:")
        logger.info(f"  Companies inserted: {loader_stats['companies_inserted']}")
        logger.info(f"  Licenses inserted: {loader_stats['licenses_inserted']}")
        logger.info(f"  Addresses inserted: {loader_stats['addresses_inserted']}")
        logger.info(f"  Companies skipped (duplicates): {loader_stats['skipped']}")
        logger.info(f"  Database errors: {loader_stats['errors']}")
        
        if args.markdown_output:
            logger.info("📝 Markdown Generation:")
            logger.info(f"  Markdown files created: {len(all_companies_for_markdown)}")
        
        # Success rate
        if extractor_stats['processed'] > 0:
            success_rate = (extractor_stats['successful'] / extractor_stats['processed']) * 100
            logger.info(f"📈 Overall success rate: {success_rate:.2f}%")
        
        logger.info("\n✅ Your data is now in Supabase!")
        logger.info("🔗 View it at: https://supabase.com/dashboard")
        logger.info("📋 Check the 'Table Editor' to see your companies, licenses, and addresses")
        
        if args.markdown_output:
            logger.info(f"📝 Markdown files saved to: {args.markdown_output}")
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        return 1
    
    finally:
        # Clean up
        if 'loader' in locals():
            loader.disconnect()
    
    return 0

if __name__ == "__main__":
    exit(main()) 