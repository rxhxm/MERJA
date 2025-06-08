#!/usr/bin/env python3
"""
NMLS Data Processor
Optimized to process 77k+ HTML files in 6 hours using parallel processing.

Key Optimizations:
- Parallel state processing (4-8 workers)
- Large batch sizes (500+ files per batch)
- Separate markdown generation (optional during main run)
- Connection pooling for database
- Memory-efficient processing
- Real-time progress tracking
"""

import os
import sys
import json
import logging
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count, Manager
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
# from dotenv import load_dotenv
import time

# Import our existing modules
from extractors.nmls_html_extractor import NMLSHTMLExtractor
from database.database_loader import DatabaseLoader

# Load environment variables
# load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fast_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class FastChunkedProcessor:
    """High-performance parallel processor for NMLS HTML files"""
    
    def __init__(self, *args, **kwargs):
        # Previous init code remains the same
        self.base_dirs = [Path(d) for d in kwargs.get('base_dirs', [])]
        self.connection_string = kwargs.get('connection_string')
        self.markdown_output_dir = Path(kwargs.get('markdown_output_dir', 'processed_markdown'))
        self.progress_file = Path(kwargs.get('progress_file', 'fast_processing_progress.json'))
        self.max_workers = kwargs.get('max_workers') or min(cpu_count(), 8)
        self.batch_size = kwargs.get('batch_size', 500)
        self.skip_markdown = kwargs.get('skip_markdown', False)
        
        self.markdown_output_dir.mkdir(parents=True, exist_ok=True)
        
        self.manager = Manager()
        self.shared_progress = self.manager.dict()
        self.progress_lock = self.manager.Lock()
        
        # Initialize shared progress counters
        self.shared_progress['stats_total_files_processed'] = 0
        self.shared_progress['stats_total_companies_extracted'] = 0
        self.shared_progress['stats_total_licenses_extracted'] = 0
        self.shared_progress['stats_total_errors'] = 0
        
        self.progress = self._load_progress()
        
        logger.info(f"🚀 Initialized FastChunkedProcessor")
        logger.info(f"⚡ Max workers: {self.max_workers}")
        logger.info(f"📦 Batch size: {self.batch_size}")
        logger.info(f"📝 Skip markdown: {self.skip_markdown}")
    
    def _load_progress(self):
        """Load processing progress from file"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    progress = json.load(f)
                logger.info(f"📋 Loaded progress: {len(progress.get('completed_states', []))} states completed")
                return progress
            except Exception as e:
                logger.warning(f"⚠️ Could not load progress file: {e}")
        
        return {
            "started_at": datetime.now().isoformat(),
            "completed_states": [],
            "failed_states": [],
            "processing_states": [],
            "stats": {
                "total_files_processed": 0,
                "total_companies_extracted": 0,
                "total_licenses_extracted": 0,
                "total_errors": 0
            }
        }
    
    def _save_progress(self):
        """Save current progress to file"""
        with self.progress_lock:
            self.progress["last_updated"] = datetime.now().isoformat()
            # Update from shared progress
            self.progress["stats"]["total_files_processed"] = self.shared_progress.get('stats_total_files_processed', 0)
            self.progress["stats"]["total_companies_extracted"] = self.shared_progress.get('stats_total_companies_extracted', 0)
            self.progress["stats"]["total_licenses_extracted"] = self.shared_progress.get('stats_total_licenses_extracted', 0)
            self.progress["stats"]["total_errors"] = self.shared_progress.get('stats_total_errors', 0)
            
            with open(self.progress_file, 'w') as f:
                json.dump(self.progress, f, indent=2)
    
    def discover_states(self):
        """Discover all states and count their HTML files"""
        states_info = []
        
        logger.info("🔍 Discovering states and counting files...")
        
        for base_dir in self.base_dirs:
            if not base_dir.exists():
                logger.warning(f"⚠️ Base directory does not exist: {base_dir}")
                continue
                
            for state_dir in sorted(base_dir.iterdir()):
                if state_dir.is_dir() and not state_dir.name.startswith('.'):
                    html_files = list(state_dir.rglob("*.html"))
                    file_count = len(html_files)
                    
                    if file_count > 0:
                        states_info.append((state_dir.name, state_dir, file_count))
        
        # Sort by file count (largest first for better load balancing)
        states_info.sort(key=lambda x: x[2], reverse=True)
        
        return states_info
    
    def run_fast_processing(self, resume: bool = True):
        """Run high-speed parallel processing of all states"""
        
        logger.info("🚀 STARTING HIGH-SPEED NMLS DATA PROCESSING")
        logger.info("=" * 80)
        
        start_time = time.time()
        
        # Discover all states
        states_info = self.discover_states()
        total_states = len(states_info)
        total_files = sum(count for _, _, count in states_info)
        
        logger.info(f"📊 DISCOVERED DATA:")
        logger.info(f"   🏛️ Total states: {total_states}")
        logger.info(f"   📁 Total HTML files: {total_files:,}")
        logger.info(f"   ⚡ Parallel workers: {self.max_workers}")
        logger.info(f"   📦 Batch size: {self.batch_size}")
        logger.info(f"   💾 Markdown output: {self.markdown_output_dir}")
        logger.info(f"   🎯 Target: 6 hours ({total_files/6/3600:.1f} files/sec needed)")
        logger.info("")
        
        # Determine which states to process
        if resume and self.progress.get("completed_states"):
            completed = set(self.progress["completed_states"])
            states_to_process = [(name, path, count) for name, path, count in states_info 
                               if name not in completed]
            logger.info(f"🔄 RESUMING: {len(completed)} states already completed")
            logger.info(f"   📋 Remaining: {len(states_to_process)} states")
        else:
            states_to_process = states_info
            logger.info(f"🆕 FRESH START: Processing all {len(states_to_process)} states")
        
        if not states_to_process:
            logger.info("🎉 ALL STATES ALREADY COMPLETED!")
            return
        
        # Prepare worker arguments
        worker_args = []
        for state_name, state_dir, file_count in states_to_process:
            args = (
                state_name, state_dir, file_count, 
                self.connection_string, str(self.markdown_output_dir), 
                self.batch_size, self.skip_markdown,
                self.shared_progress, self.progress_lock
            )
            worker_args.append(args)
        
        # Process states in parallel
        logger.info(f"🚀 Starting {self.max_workers} parallel workers...")
        
        completed_count = 0
        failed_count = 0
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all jobs
            future_to_state = {executor.submit(process_state_worker, args): args[0] for args in worker_args}
            
            # Process completed jobs
            for future in as_completed(future_to_state):
                state_name = future_to_state[future]
                
                try:
                    result = future.result()
                    
                    if result.get("success", False):
                        self.progress["completed_states"].append(result["state"])
                        completed_count += 1
                        
                        elapsed = time.time() - start_time
                        remaining_states = len(states_to_process) - completed_count - failed_count
                        
                        logger.info(f"🎯 PROGRESS: {completed_count}/{len(states_to_process)} states completed")
                        logger.info(f"   ⏱️ Elapsed: {elapsed/3600:.1f} hours")
                        logger.info(f"   📊 Total processed: {self.shared_progress.get('stats_total_files_processed', 0):,} files")
                        logger.info(f"   🏢 Total companies: {self.shared_progress.get('stats_total_companies_extracted', 0):,}")
                        logger.info(f"   📜 Total licenses: {self.shared_progress.get('stats_total_licenses_extracted', 0):,}")
                        
                        if elapsed > 0:
                            files_per_hour = self.shared_progress.get('stats_total_files_processed', 0) / (elapsed / 3600)
                            logger.info(f"   🚀 Rate: {files_per_hour:,.0f} files/hour")
                            
                            if remaining_states > 0 and files_per_hour > 0:
                                # Estimate remaining time
                                remaining_files = sum(count for _, _, count in states_to_process[completed_count + failed_count:])
                                remaining_hours = remaining_files / files_per_hour
                                logger.info(f"   ⏰ ETA: {remaining_hours:.1f} hours remaining")
                        
                    else:
                        self.progress["failed_states"].append({
                            "state": result["state"],
                            "error": result.get("error", "Unknown error"),
                            "timestamp": datetime.now().isoformat()
                        })
                        failed_count += 1
                        logger.error(f"❌ FAILED: {result['state']} - {result.get('error', 'Unknown error')}")
                    
                    # Save progress after each completion
                    self._save_progress()
                    
                except Exception as e:
                    logger.error(f"❌ Worker exception for {state_name}: {e}")
                    failed_count += 1
        
        # Final summary
        self._print_final_summary(start_time)
    
    def _print_final_summary(self, start_time):
        """Print final processing summary"""
        elapsed = time.time() - start_time
        
        logger.info("\n" + "=" * 80)
        logger.info("🎉 HIGH-SPEED PROCESSING COMPLETED!")
        logger.info("=" * 80)
        
        stats = self.progress["stats"]
        logger.info(f"📊 FINAL STATISTICS:")
        logger.info(f"   🏛️ States completed: {len(self.progress['completed_states'])}")
        logger.info(f"   📁 Files processed: {stats['total_files_processed']:,}")
        logger.info(f"   🏢 Companies extracted: {stats['total_companies_extracted']:,}")
        logger.info(f"   📜 Licenses extracted: {stats['total_licenses_extracted']:,}")
        logger.info(f"   ❌ Total errors: {stats['total_errors']:,}")
        logger.info(f"   ⏱️ Total time: {elapsed/3600:.2f} hours")
        
        if elapsed > 0:
            files_per_hour = stats['total_files_processed'] / (elapsed / 3600)
            logger.info(f"   🚀 Average rate: {files_per_hour:,.0f} files/hour")
        
        if self.progress["failed_states"]:
            logger.warning(f"   ⚠️ Failed states: {len(self.progress['failed_states'])}")
        
        # Success rate
        total_states = len(self.progress["completed_states"]) + len(self.progress["failed_states"])
        success_rate = (len(self.progress["completed_states"]) / total_states * 100) if total_states > 0 else 0
        logger.info(f"   ✅ Success rate: {success_rate:.1f}%")
        
        # Target achievement
        target_met = elapsed <= 6 * 3600
        logger.info(f"   6-hour target: {'✅ MET' if target_met else '❌ MISSED'}")

def process_state_worker(args):
    """Worker function to process a single state"""
    state_name, state_dir, file_count, connection_string, markdown_output_dir, batch_size, skip_markdown, shared_progress, progress_lock = args
    
    # Set up logging for this worker
    worker_logger = logging.getLogger(f"worker_{state_name}")
    
    try:
        worker_logger.info(f"🏛️ Starting {state_name.upper()}: {file_count:,} files")
        
        # Initialize processors for this worker
        extractor = NMLSHTMLExtractor()
        db_loader = DatabaseLoader(connection_string)
        db_loader.connect()
        
        # Find all HTML files in the state directory
        html_files = list(state_dir.rglob("*.html"))
        
        if not html_files:
            worker_logger.warning(f"⚠️ No HTML files found in {state_dir}")
            return {"state": state_name, "files_processed": 0, "companies_extracted": 0, "errors": 0}
        
        # Process files in large batches for efficiency
        total_batches = (len(html_files) + batch_size - 1) // batch_size
        
        state_stats = {
            "files_processed": 0,
            "companies_extracted": 0, 
            "licenses_extracted": 0,
            "markdown_files_created": 0,
            "errors": 0,
            "error_details": []
        }
        
        # Create state-specific markdown directory if needed
        if not skip_markdown:
            state_markdown_dir = Path(markdown_output_dir) / state_name
            state_markdown_dir.mkdir(parents=True, exist_ok=True)
        
        # Process in large batches
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(html_files))
            batch_files = html_files[start_idx:end_idx]
            
            worker_logger.info(f"  📦 {state_name} Batch {batch_num + 1}/{total_batches}: {len(batch_files)} files")
            
            # Extract data from batch
            batch_data = []
            batch_start_time = time.time()
            
            for file_path in batch_files:
                try:
                    company_data = extractor.extract_from_file(str(file_path))
                    if company_data and company_data.nmls_id:
                        batch_data.append(company_data)
                        state_stats["files_processed"] += 1
                except Exception as e:
                    error_msg = f"Error processing {file_path}: {str(e)}"
                    worker_logger.error(error_msg)
                    state_stats["errors"] += 1
                    state_stats["error_details"].append(error_msg)
            
            # Store in database (high priority)
            if batch_data:
                try:
                    db_result = db_loader.load_companies(batch_data)
                    state_stats["companies_extracted"] += len(batch_data)
                    
                    # Count licenses
                    for company in batch_data:
                        state_stats["licenses_extracted"] += len(company.licenses)
                    
                    batch_time = time.time() - batch_start_time
                    files_per_sec = len(batch_files) / batch_time if batch_time > 0 else 0
                    worker_logger.info(f"    ✅ {state_name}: {len(batch_data)} companies stored ({files_per_sec:.1f} files/sec)")
                    
                except Exception as e:
                    error_msg = f"Database error for {state_name} batch {batch_num + 1}: {str(e)}"
                    worker_logger.error(error_msg)
                    state_stats["errors"] += 1
                    state_stats["error_details"].append(error_msg)
                
                # Generate markdown files (lower priority, optional)
                if not skip_markdown:
                    try:
                        markdown_count = extractor.save_to_markdown(batch_data, str(state_markdown_dir))
                        state_stats["markdown_files_created"] += markdown_count
                    except Exception as e:
                        error_msg = f"Markdown error for {state_name} batch {batch_num + 1}: {str(e)}"
                        worker_logger.error(error_msg)
                        state_stats["errors"] += 1
                        state_stats["error_details"].append(error_msg)
                
                # Update shared progress
                with progress_lock:
                    shared_progress['stats_total_files_processed'] = shared_progress.get('stats_total_files_processed', 0) + state_stats["files_processed"]
                    shared_progress['stats_total_companies_extracted'] = shared_progress.get('stats_total_companies_extracted', 0) + state_stats["companies_extracted"]
                    shared_progress['stats_total_licenses_extracted'] = shared_progress.get('stats_total_licenses_extracted', 0) + state_stats["licenses_extracted"]
                    shared_progress['stats_total_errors'] = shared_progress.get('stats_total_errors', 0) + state_stats["errors"]
        
        # Clean up
        db_loader.disconnect()
        
        # Log state completion
        worker_logger.info(f"✅ {state_name.upper()} COMPLETED:")
        worker_logger.info(f"   📁 Files: {state_stats['files_processed']:,}")
        worker_logger.info(f"   🏢 Companies: {state_stats['companies_extracted']:,}")
        worker_logger.info(f"   📜 Licenses: {state_stats['licenses_extracted']:,}")
        worker_logger.info(f"   ❌ Errors: {state_stats['errors']:,}")
        
        return {
            "state": state_name,
            "success": True,
            **state_stats
        }
        
    except Exception as e:
        error_msg = f"Critical failure processing {state_name}: {str(e)}"
        worker_logger.error(error_msg)
        return {
            "state": state_name,
            "success": False,
            "error": error_msg,
            "files_processed": 0,
            "companies_extracted": 0,
            "errors": 1
        }

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="High-speed parallel processing of NMLS HTML files")
    parser.add_argument("--data-dirs", nargs="+", 
                       default=["drive/data", "drive/data_"],
                       help="Data directories containing state folders")
    parser.add_argument("--markdown-output", default="processed_markdown",
                       help="Output directory for markdown files")
    parser.add_argument("--progress-file", default="fast_processing_progress.json",
                       help="Progress tracking file")
    parser.add_argument("--no-resume", action="store_true",
                       help="Start fresh (ignore existing progress)")
    parser.add_argument("--connection-string", 
                       default=os.getenv('DATABASE_URL'),
                       help="Database connection string")
    parser.add_argument("--max-workers", type=int,
                       help="Maximum parallel workers (default: CPU count, max 8)")
    parser.add_argument("--batch-size", type=int, default=500,
                       help="Batch size for processing (default: 500)")
    parser.add_argument("--skip-markdown", action="store_true",
                       help="Skip markdown generation for maximum speed")
    
    args = parser.parse_args()
    
    if not args.connection_string:
        logger.error("Database connection string required. Set DATABASE_URL environment variable or use --connection-string")
        sys.exit(1)
    
    # Initialize processor
    processor = FastChunkedProcessor(
        base_dirs=args.data_dirs,
        connection_string=args.connection_string,
        markdown_output_dir=args.markdown_output,
        progress_file=args.progress_file,
        max_workers=args.max_workers,
        batch_size=args.batch_size,
        skip_markdown=args.skip_markdown
    )
    
    # Run processing
    processor.run_fast_processing(resume=not args.no_resume)

if __name__ == "__main__":
    main() 