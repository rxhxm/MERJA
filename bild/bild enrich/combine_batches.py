#!/usr/bin/env python3
"""
Utility script to combine all batch CSV files into two aggregated files:
1. One file for all accounts
2. One file for all leads
"""

import pandas as pd
import glob
import os
import argparse
from tqdm import tqdm


def combine_batch_files(pattern, output_file):
    """
    Combine all files matching the pattern into one aggregated CSV file
    """
    try:
        print(f"Processing files matching: {pattern}")
        # Get a list of all matching files
        batch_files = sorted(glob.glob(pattern))
        
        if not batch_files:
            print(f"No files found matching pattern: {pattern}")
            return
        
        print(f"Found {len(batch_files)} files to combine")
        
        # Read and concatenate all batch files
        dfs = []
        for file in tqdm(batch_files, desc="Reading files"):
            try:
                batch_df = pd.read_csv(file)
                dfs.append(batch_df)
            except Exception as e:
                print(f"Error reading file {file}: {e}")
        
        if not dfs:
            print("No valid data found to combine.")
            return
        
        # Combine all dataframes
        combined_df = pd.concat(dfs, ignore_index=True)
        
        # Drop duplicates if needed
        original_count = len(combined_df)
        combined_df = combined_df.drop_duplicates()
        deduped_count = len(combined_df)
        
        if original_count > deduped_count:
            print(f"Removed {original_count - deduped_count} duplicate rows")
            
        # Save the combined data
        combined_df.to_csv(output_file, index=False)
        print(f"Successfully combined {len(combined_df)} rows from {len(dfs)} files to {output_file}")
        
    except Exception as e:
        print(f"Error combining files: {e}")


def main():
    parser = argparse.ArgumentParser(description="Combine all batch CSV files into aggregated files")
    parser.add_argument("--accounts-output", default="combined_enriched_accounts.csv", 
                        help="Output file for combined accounts (default: combined_enriched_accounts.csv)")
    parser.add_argument("--leads-output", default="combined_enriched_leads.csv", 
                        help="Output file for combined leads (default: combined_enriched_leads.csv)")
    
    args = parser.parse_args()
    
    # Combine accounts files
    combine_batch_files("batch_*_enriched_accounts.csv", args.accounts_output)
    
    # Combine leads files
    combine_batch_files("batch_*_enriched_leads.csv", args.leads_output)


if __name__ == "__main__":
    main() 