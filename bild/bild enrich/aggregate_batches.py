#!/usr/bin/env python3
"""
Utility script to aggregate batch files into a single CSV file.
This can be run separately from the main enrichment process.
"""

import pandas as pd
import glob
import os
import argparse


def aggregate_batches(batch_dir="batches", output_file="enriched_suppliers_aggregated.csv"):
    """
    Combine all batch files into one aggregated CSV file
    """
    try:
        print("Aggregating batch files...")
        # Get a list of all batch files
        batch_files = sorted(glob.glob(f"{batch_dir}/enriched_batch_*.csv"))
        
        if not batch_files:
            print("No batch files found to aggregate.")
            return
        
        # Read and concatenate all batch files
        dfs = []
        for file in batch_files:
            try:
                batch_df = pd.read_csv(file)
                print(f"Read {len(batch_df)} rows from {file}")
                dfs.append(batch_df)
            except Exception as e:
                print(f"Error reading batch file {file}: {e}")
        
        if not dfs:
            print("No valid batch data found to aggregate.")
            return
        
        # Combine all dataframes
        combined_df = pd.concat(dfs, ignore_index=True)
        
        # Save the combined data
        combined_df.to_csv(output_file, index=False)
        print(f"Successfully aggregated {len(combined_df)} rows from {len(dfs)} batches to {output_file}")
        
        # Save a qualified-only version
        qualified_df = combined_df[combined_df["is_qualified"] == True].copy()
        qualified_output = output_file.replace(".csv", "_qualified.csv")
        qualified_df.to_csv(qualified_output, index=False)
        print(f"Saved {len(qualified_df)} qualified leads to {qualified_output}")
        
        # Save a qualified decision-makers version
        decision_makers_df = qualified_df[qualified_df["api_relevant_lead_count"] > 0].copy()
        decision_makers_output = output_file.replace(".csv", "_qualified_with_decision_makers.csv")
        decision_makers_df.to_csv(decision_makers_output, index=False)
        print(f"Saved {len(decision_makers_df)} qualified leads with decision makers to {decision_makers_output}")
        
    except Exception as e:
        print(f"Error aggregating batch files: {e}")


def main():
    parser = argparse.ArgumentParser(description="Aggregate CSV batch files into a single file")
    parser.add_argument("--batch-dir", default="batches", help="Directory containing batch files (default: batches)")
    parser.add_argument("--output", default="enriched_suppliers_aggregated.csv", help="Output file name (default: enriched_suppliers_aggregated.csv)")
    
    args = parser.parse_args()
    
    # Ensure the batch directory exists
    if not os.path.isdir(args.batch_dir):
        print(f"Error: Batch directory '{args.batch_dir}' does not exist.")
        return
    
    aggregate_batches(args.batch_dir, args.output)


if __name__ == "__main__":
    main() 