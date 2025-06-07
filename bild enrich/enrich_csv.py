# mutliprocessing


import pandas as pd
import requests # Keep for synchronous examples if any, or remove if fully async
import time
import json
import asyncio
import httpx
import re
import os
import glob

# Configuration
API_KEY = "42342922-b737-43bf-8e67-68be5108be7b" # Replace with your actual API key if different
BASE_URL = "https://api.sixtyfour.ai"
ENRICH_COMPANY_ENDPOINT = "/enrich-company"
CSV_FILE_PATH = "combined_suppliers.csv"
OUTPUT_CSV_FILE_PATH = "enriched_suppliers.csv"
ROWS_TO_PROCESS = 0 # Set to 0 to process all rows, or a number for testing
CONCURRENCY_LIMIT = 50 # Number of concurrent API calls (e.g., 20-50)
REQUEST_TIMEOUT = 480.0 # Timeout for each API request in seconds (8 minutes)
BATCH_SIZE = 100 # Number of companies to process in each batch
ACCOUNTS_BATCH_DIR = "accounts_batches" # Directory to store batch outputs for accounts
LEADS_BATCH_DIR = "leads_batches" # Directory to store batch outputs for leads

# Define reference companies for ICP comparison
# We'll extract these dynamically from the CSV
REFERENCE_COMPANY_COUNT = 3  # Number of reference companies to extract

# Define the data you want to extract from the API for the company
COMPANY_ENRICH_STRUCT = {
    "company_linkedin": "LinkedIn profile URL of the company",
    "website": "Official website of the company",
    "num_employees": "Estimated number of employees",
    "industry": "Primary industry of the company",
    "short_summary": "A concise summary of the company's business.",
    "has_div8_estimators": "Does this company employ DIV 8 estimators on staff? A DIV 8 estimator is a professional who specializes in estimating costs for door, frame, and hardware components in construction projects.",
    "icp_match": "Is this company similar to other door suppliers or manufacturers like 'Overly Door Co.', 'Acudor Products, Inc.', and other door suppliers from the list? Yes or No, and explain why or why not.",
    "logic": "What specifically makes this company similar or different from other door suppliers and manufacturers? Focus on products, market focus, and services.",
    "notes": "Final breakdown on this company's relevance to the door supply/manufacturing industry."
}

# Define the people/leads you want to extract
PEOPLE_STRUCT = {
    "name": "Full name of the person",
    "title": "Job title or position at the company",
    "linkedin": "LinkedIn profile URL of the person",
    "email": "Email address of the person if available",
    "is_decision_maker": "Is this person likely a key decision maker? Answer 'Yes' ONLY for C-suite executives (CEO, COO, CTO, CFO, etc.), company presidents, vice presidents, directors, or heads of departments. For all others, answer 'No'.",
    "decision_maker_score": "Rate this person's likelihood of being a decision maker from 1-10, where 10 is highest. Give 9-10 for C-suite executives, 7-8 for VPs and directors, 5-6 for managers, 3-4 for team leads, 1-2 for individual contributors.",
    "is_relevant": "Is this person relevant to door supply/manufacturing decisions? Answer 'Yes' if they are in operations, sales, purchasing, estimating, or executive leadership. Answer 'No' for marketing, HR, finance (except CFO), or other unrelated departments."
}

def extract_reference_companies(csv_path, count=3):
    """
    Extract reference companies from the CSV to use for ICP comparison.
    """
    try:
        df = pd.read_csv(csv_path)
        if len(df) <= count:
            reference_companies = df['companyName'].tolist()
        else:
            # Take the first few companies as reference
            reference_companies = df['companyName'].head(count).tolist()
        
        # Filter out any None/NaN values
        reference_companies = [c for c in reference_companies if c and not pd.isna(c)]
        
        return reference_companies
    except Exception as e:
        print(f"Error extracting reference companies: {e}")
        return ["Overly Door Co.", "Acudor Products, Inc."]  # Default fallback

async def enrich_company_data_async(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, company_name: str, company_description: str, original_row_data: dict, reference_companies: list):
    """
    Calls the SixtyFour API asynchronously to enrich company data.
    Includes original_row_data to pass through for result processing.
    """
    async with semaphore:
        headers = {
            "x-api-key": API_KEY,
            "Content-Type": "application/json"
        }
        
        # Create a custom struct with reference companies
        custom_struct = COMPANY_ENRICH_STRUCT.copy()
        ref_companies_str = "', '".join(reference_companies)
        custom_struct["icp_match"] = f"Is this company similar to other door suppliers or manufacturers like '{ref_companies_str}'? Yes or No, and explain why or why not."
        
        payload = {
            "target_company": {
                "company_name": company_name,
                "description": company_description
            },
            "struct": custom_struct,
            "find_people": True,  # Enable people search
            "people_focus_prompt": "Find key decision-makers at this company, focusing specifically on C-suite executives (CEO, COO, CTO, CFO), company presidents, vice presidents, directors, heads of departments, and specialists in door manufacturing, estimating, or sales. Prioritize people with these keywords in titles: 'estimator', 'director', 'VP', 'chief', 'CEO', 'COO', 'president', 'manager', 'sales', 'operations', 'purchasing'. Do not include non-decision makers like associates, assistants, or support staff.",
            "people_struct": PEOPLE_STRUCT,  # Add structure for people data
            "max_people": 15  # Get more people to filter through
        }

        try:
            print(f"Starting API call for: {company_name}")
            response = await client.post(
                f"{BASE_URL}{ENRICH_COMPANY_ENDPOINT}",
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            print(f"Finished API call for: {company_name}, Status: {response.status_code}")
            return {"success": True, "data": response.json(), "original_row": original_row_data, "company_name": company_name}
        except httpx.HTTPStatusError as e:
            error_message = f"HTTP error for {company_name}: {e.response.status_code} - {e.response.text} - Exception: {e!r}"
            print(error_message)
            return {"success": False, "error": error_message, "original_row": original_row_data, "company_name": company_name}
        except httpx.RequestError as e:
            error_message = f"Request error for {company_name}: {e!r}"
            print(error_message)
            return {"success": False, "error": error_message, "original_row": original_row_data, "company_name": company_name}
        except Exception as e:
            error_message = f"Unexpected error for {company_name}: {e!r}"
            print(error_message)
            return {"success": False, "error": error_message, "original_row": original_row_data, "company_name": company_name}

def parse_employee_count(employee_str):
    """
    Parses the 'num_employees' string to get a minimum employee count.
    Example inputs: "5-10 employees", "50+", "Less than 10", "1000".
    """
    if not employee_str or not isinstance(employee_str, str):
        return 0

    # General cleanup: remove common phrases, make lowercase
    cleaned_str = employee_str.lower()
    phrases_to_remove = ["employees", "staff members", "approximately", "about", "around", "listed on linkedin"]
    for phrase in phrases_to_remove:
        cleaned_str = cleaned_str.replace(phrase, "")

    # Remove content in parentheses often containing secondary info like (LinkedIn estimate)
    cleaned_str = re.sub(r'\(.*?\)', '', cleaned_str).strip()

    # Try to extract numbers
    numbers = re.findall(r'\d+', cleaned_str)

    if not numbers:
        return 0

    # Handle ranges like "50-100" -> take first number (lower bound)
    # Handle "50+" -> take the number
    # Handle single numbers "50"
    # After cleanup, we expect numbers to be the primary employee count indication

    # Prioritize the first number found as it's often the start of a range or the primary figure
    if numbers:
        return int(numbers[0])

    return 0 # Default if no parsable number is found after cleanup

def has_estimator(lead_titles, company_details):
    """
    Checks if the company has estimators based on titles or API response.
    """
    # Check lead titles first
    estimator_keywords = ['estimator', 'estimating', 'estimation', 'estimate']
    if lead_titles:
        for title in lead_titles:
            if title and any(keyword in title.lower() for keyword in estimator_keywords):
                return True, "Found estimator in employee titles"
    
    # Check API response for div8_estimators field
    has_div8 = company_details.get("has_div8_estimators", "").lower()
    if "yes" in has_div8 or "likely" in has_div8 or "probably" in has_div8:
        return True, has_div8
    
    return False, "No estimators found in titles or company details"

def is_qualified(api_data_content):
    """
    Determines if a company is qualified based on API response content.
    """
    if not api_data_content or "structured_data" not in api_data_content:
        return False, "No API response content or structured_data"

    structured_data = api_data_content.get("structured_data", {})
    confidence = api_data_content.get("confidence_score", 0)
    
    num_employees_str = structured_data.get("num_employees", "0")
    employee_count = parse_employee_count(num_employees_str)
    
    # Extract lead titles for estimator check
    leads = structured_data.get("leads", [])
    lead_titles = [lead.get("title", "") for lead in leads if isinstance(lead, dict)]
    
    # Check for estimators
    has_estimator_flag, estimator_reason = has_estimator(lead_titles, structured_data)
    
    # Check ICP match
    icp_match = structured_data.get("icp_match", "").lower()
    icp_positive = any(term in icp_match for term in ["yes", "similar", "match", "good fit"])
    
    # Check for decision makers
    has_decision_makers = False
    decision_maker_count = 0
    for lead in leads:
        if isinstance(lead, dict) and "yes" in lead.get("is_decision_maker", "").lower():
            has_decision_makers = True
            decision_maker_count += 1
    
    qualification_reasons = []
    qualified_overall = True
    
    min_confidence = 7.0
    min_employees = 10  # Lower threshold as we're primarily interested in finding decision makers
    min_decision_makers = 1  # Need at least one decision maker

    if confidence >= min_confidence:
        qualification_reasons.append(f"Confidence score {confidence} >= {min_confidence}")
    else:
        qualification_reasons.append(f"Confidence score {confidence} < {min_confidence}")
        qualified_overall = False

    if employee_count >= min_employees:
        qualification_reasons.append(f"Employee count {employee_count} (from '{num_employees_str}') >= {min_employees}")
    else:
        qualification_reasons.append(f"Employee count {employee_count} (from '{num_employees_str}') < {min_employees}")
        qualified_overall = False
    
    if has_estimator_flag:
        qualification_reasons.append(f"Has estimator: {estimator_reason}")
    else:
        qualification_reasons.append(f"No estimator detected: {estimator_reason}")
        # Not making this a disqualifier, just noting it
    
    if icp_positive:
        qualification_reasons.append(f"ICP match: {icp_match[:100]}")
    else:
        qualification_reasons.append(f"ICP mismatch: {icp_match[:100]}")
        qualified_overall = False
    
    if has_decision_makers:
        qualification_reasons.append(f"Found {decision_maker_count} decision makers")
    else:
        qualification_reasons.append("No decision makers found")
        qualified_overall = False

    return qualified_overall, "; ".join(qualification_reasons)

async def process_rows_concurrently(df_to_process, batch_id=None):
    enriched_rows_list = []
    leads_rows_list = []
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    # Explicitly set follow_redirects=True if needed, httpx default is False for client.post
    # Limits can be set for finer-grained control over connection pooling
    limits = httpx.Limits(max_keepalive_connections=CONCURRENCY_LIMIT, max_connections=CONCURRENCY_LIMIT + 5) # a bit more than concurrency
    timeout_config = httpx.Timeout(REQUEST_TIMEOUT, connect=10.0) # request_timeout, connect_timeout

    # Extract reference companies from the CSV
    reference_companies = extract_reference_companies(CSV_FILE_PATH, REFERENCE_COMPANY_COUNT)
    print(f"Using reference companies for ICP comparison: {reference_companies}")
    
    # Track progress
    total_rows = len(df_to_process)
    print(f"Starting to process {total_rows} companies with concurrency {CONCURRENCY_LIMIT}")
    
    # Create the dictionary to map task to company name for error tracking
    task_to_company = {}
    
    async with httpx.AsyncClient(timeout=timeout_config, limits=limits, follow_redirects=True) as client:
        tasks = []
        for index, row in df_to_process.iterrows():
            company_name = row.get("companyName")
            company_desc = row.get("description", "")
            original_row_dict = row.to_dict()

            if not company_name or pd.isna(company_name):
                print(f"Skipping row (original index {index}) due to missing company name.")
                skipped_row = original_row_dict.copy()
                skipped_row["api_enrichment_status"] = "Skipped - No company name"
                enriched_rows_list.append(skipped_row)
                
                # Add a skipped lead entry to maintain tracking
                lead_row = {
                    "companyName": company_name if company_name and not pd.isna(company_name) else "Unknown Company",
                    "lead_name": "",
                    "lead_title": "",
                    "lead_linkedin": "",
                    "lead_email": "",
                    "lead_is_decision_maker": "",
                    "lead_api_status": "Skipped - No company name"
                }
                leads_rows_list.append(lead_row)
                
                continue

            # Create a task for this company
            task = asyncio.create_task(
                enrich_company_data_async(client, semaphore, company_name, company_desc, original_row_dict, reference_companies)
            )
            
            # Map the task to company name for error tracking
            task_to_company[task] = company_name
            
            tasks.append(task)

        # Process all tasks and handle individual exceptions
        completed = 0
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                company_name = result.get("company_name", task_to_company.get(task, "Unknown Company"))
                
                if result.get("success"):
                    print(f"Completed API call for company {completed+1}/{total_rows}: {company_name} - Success")
                else:
                    print(f"Completed API call for company {completed+1}/{total_rows}: {company_name} - Failed: {result.get('error', 'Unknown error')}")
                
                completed += 1
                
                # Process the result
                new_row = {}
                original_row_data = result.get("original_row", {})
                new_row = original_row_data.copy()
                company_name = original_row_data.get("companyName", "Unknown Company")

                if result.get("success"):
                    api_data_content = result.get("data")
                    new_row["api_enrichment_status"] = "Success"
                    new_row["api_raw_response_preview"] = json.dumps(api_data_content)[:200]

                    structured_data = api_data_content.get("structured_data", {})
                    new_row["api_confidence_score"] = api_data_content.get("confidence_score")
                    new_row["api_notes"] = api_data_content.get("notes")
                    new_row["api_findings"] = "|".join(api_data_content.get("findings", []))

                    for key in COMPANY_ENRICH_STRUCT:
                        new_row[f"api_{key}"] = structured_data.get(key)

                    # Process leads more extensively
                    leads = structured_data.get("leads", [])
                    lead_linkedin_profiles = []
                    decision_makers = []
                    estimator_titles = []
                    relevant_leads = []
                    
                    if leads and isinstance(leads, list):
                        for i, lead in enumerate(leads):
                            if isinstance(lead, dict):
                                lead_name = lead.get("name", "")
                                lead_title = lead.get("title", "")
                                lead_linkedin = lead.get("linkedin", "")
                                lead_email = lead.get("email", "")
                                is_decision_maker = lead.get("is_decision_maker", "").lower()
                                is_relevant = lead.get("is_relevant", "").lower()
                                decision_maker_score = lead.get("decision_maker_score", 0)
                                try:
                                    decision_maker_score = int(decision_maker_score)
                                except (ValueError, TypeError):
                                    decision_maker_score = 0
                                
                                # Create lead row for leads file
                                lead_row = {
                                    "companyName": company_name,
                                    "lead_name": lead_name,
                                    "lead_title": lead_title,
                                    "lead_linkedin": lead_linkedin,
                                    "lead_email": lead_email,
                                    "lead_is_decision_maker": is_decision_maker,
                                    "lead_api_status": "Success"
                                }
                                leads_rows_list.append(lead_row)
                                
                                # Skip people who are neither decision makers nor relevant
                                if "yes" not in is_decision_maker and "yes" not in is_relevant:
                                    continue
                                    
                                # Skip people with very low decision maker scores
                                if decision_maker_score < 3:
                                    continue
                                
                                # Track this person as useful
                                relevant_leads.append(lead)
                                
                                if lead_linkedin:
                                    lead_linkedin_profiles.append(lead_linkedin)
                                
                                # Store decision maker info separately
                                if "yes" in is_decision_maker:
                                    decision_makers.append(f"{lead_name} ({lead_title})")
                                
                                # Check for estimator in title
                                if lead_title and any(keyword in lead_title.lower() for keyword in ["estimator", "estimating"]):
                                    estimator_titles.append(f"{lead_name} ({lead_title})")
                                
                                # Only store first 5 leads in detail to avoid cluttering output
                                if i < 5:
                                    new_row[f"lead_{i+1}_name"] = lead_name
                                    new_row[f"lead_{i+1}_title"] = lead_title
                                    new_row[f"lead_{i+1}_linkedin"] = lead_linkedin
                                    new_row[f"lead_{i+1}_email"] = lead_email
                                    new_row[f"lead_{i+1}_is_decision_maker"] = is_decision_maker
                                    new_row[f"lead_{i+1}_decision_maker_score"] = decision_maker_score
                                    new_row[f"lead_{i+1}_is_relevant"] = is_relevant
                    
                    new_row["api_lead_linkedin_profiles"] = "; ".join(filter(None, lead_linkedin_profiles))
                    new_row["api_decision_makers"] = "; ".join(filter(None, decision_makers))
                    new_row["api_estimator_leads"] = "; ".join(filter(None, estimator_titles))
                    new_row["api_lead_count"] = len(leads)
                    new_row["api_relevant_lead_count"] = len(relevant_leads)

                    qualified, reason = is_qualified(api_data_content)
                    new_row["is_qualified"] = qualified
                    new_row["qualification_reason"] = reason
                else:
                    new_row["api_enrichment_status"] = "Failed or No Data"
                    new_row["api_error_message"] = result.get("error", "Unknown error")
                    new_row["is_qualified"] = False
                    new_row["qualification_reason"] = result.get("error", "API call failed or returned no data")
                    
                    # Add a failed lead entry to maintain tracking
                    lead_row = {
                        "companyName": company_name,
                        "lead_name": "",
                        "lead_title": "",
                        "lead_linkedin": "",
                        "lead_email": "",
                        "lead_is_decision_maker": "",
                        "lead_api_status": "Failed"
                    }
                    leads_rows_list.append(lead_row)

                enriched_rows_list.append(new_row)
                
            except Exception as e:
                # Get the company name from our mapping
                company_name = task_to_company.get(task, "Unknown Company")
                
                print(f"Error processing company {completed+1}/{total_rows}: {company_name} - Exception: {str(e)}")
                
                # Create an error record for this company
                if company_name in task_to_company.values():
                    # Find the original row data for this company
                    original_row = None
                    for idx, row in df_to_process.iterrows():
                        if row.get("companyName") == company_name:
                            original_row = row.to_dict()
                            break
                    
                    if original_row:
                        error_row = original_row.copy()
                        error_row["api_enrichment_status"] = "Failed - Exception"
                        error_row["api_error_message"] = str(e)
                        error_row["is_qualified"] = False
                        error_row["qualification_reason"] = f"Exception: {str(e)}"
                        enriched_rows_list.append(error_row)
                        
                        # Add a failed lead entry
                        lead_row = {
                            "companyName": company_name,
                            "lead_name": "",
                            "lead_title": "",
                            "lead_linkedin": "",
                            "lead_email": "",
                            "lead_is_decision_maker": "",
                            "lead_api_status": "Failed - Exception"
                        }
                        leads_rows_list.append(lead_row)
                
                completed += 1

    print(f"Completed processing {len(enriched_rows_list)} companies with {len(leads_rows_list)} leads extracted")
    return enriched_rows_list, leads_rows_list

def process_in_batches(csv_file_path, batch_size=BATCH_SIZE, start_batch=18, end_batch=26):
    """
    Process the CSV file in batches and save each batch to a separate file
    """
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file_path)
        print(f"Successfully read {len(df)} rows from {csv_file_path}")
        
        if df.empty:
            print("No rows to process.")
            return
        
        # Create the output directories if they don't exist
        os.makedirs(ACCOUNTS_BATCH_DIR, exist_ok=True)
        os.makedirs(LEADS_BATCH_DIR, exist_ok=True)
        
        # Split into batches
        num_batches = (len(df) + batch_size - 1) // batch_size  # Ceiling division
        
        # Adjust batch range to process
        start_batch = max(1, min(start_batch, num_batches))
        end_batch = min(end_batch, num_batches)
        
        print(f"Processing batches {start_batch} through {end_batch} of {num_batches} total batches")
        print(f"Using concurrency limit of {CONCURRENCY_LIMIT} requests at a time")
        
        # Create a log file for batch processing
        with open("batch_processing_log.txt", "a") as log_file:
            log_file.write(f"Started processing batches {start_batch}-{end_batch} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        for batch_id in range(start_batch-1, end_batch):
            start_idx = batch_id * batch_size
            end_idx = min((batch_id + 1) * batch_size, len(df))
            batch_df = df.iloc[start_idx:end_idx].copy()
            
            batch_num = batch_id + 1
            print(f"\n{'='*80}")
            print(f"PROCESSING BATCH {batch_num}/{num_batches} (rows {start_idx+1}-{end_idx})")
            print(f"{'='*80}\n")
            
            try:
                # Process this batch
                enriched_data, leads_data = asyncio.run(process_rows_concurrently(batch_df, batch_id))
                
                if not enriched_data:
                    print(f"WARNING: No enriched data returned for batch {batch_num}.")
                    continue
                    
                enriched_df = pd.DataFrame(enriched_data)
                leads_df = pd.DataFrame(leads_data)
                
                # Save accounts batch
                accounts_output_file = f"batch_{batch_num}_of_{num_batches}_enriched_accounts.csv"
                accounts_output_path = os.path.join(ACCOUNTS_BATCH_DIR, accounts_output_file)
                enriched_df.to_csv(accounts_output_path, index=False)
                print(f"Saved accounts batch {batch_num} with {len(enriched_df)} rows to {accounts_output_path}")
                
                # Also save to root directory for backward compatibility
                enriched_df.to_csv(accounts_output_file, index=False)
                
                # Save leads batch
                leads_output_file = f"batch_{batch_num}_of_{num_batches}_enriched_leads.csv"
                leads_output_path = os.path.join(LEADS_BATCH_DIR, leads_output_file)
                leads_df.to_csv(leads_output_path, index=False)
                print(f"Saved leads batch {batch_num} with {len(leads_df)} rows to {leads_output_path}")
                
                # Also save to root directory for backward compatibility
                leads_df.to_csv(leads_output_file, index=False)
                
                # Update the log
                with open("batch_processing_log.txt", "a") as log_file:
                    log_file.write(f"Completed batch {batch_num}/{num_batches} with {len(enriched_df)} accounts and {len(leads_df)} leads at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                print(f"\nCompleted batch {batch_num}/{num_batches} successfully\n")
                
            except Exception as e:
                error_msg = f"Error processing batch {batch_num}: {str(e)}"
                print(error_msg)
                
                # Log the error
                with open("batch_processing_log.txt", "a") as log_file:
                    log_file.write(f"ERROR in batch {batch_num}/{num_batches}: {str(e)} at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                
                # Try to continue with the next batch
                continue
        
        print(f"\nCompleted processing batches {start_batch} through {end_batch}.")
        
        # After all batches are done, aggregate them
        aggregate_batches()
        
    except FileNotFoundError:
        print(f"Error: The file {csv_file_path} was not found.")
    except Exception as e:
        print(f"Error processing batches: {e}")

def aggregate_batches():
    """
    Combine all batch files into aggregated CSV files
    """
    try:
        # First aggregate accounts data
        print("Aggregating account batch files...")
        account_files = sorted(glob.glob(f"{ACCOUNTS_BATCH_DIR}/batch_*_enriched_accounts.csv"))
        
        if account_files:
            # Read and concatenate all batch files
            account_dfs = []
            for file in account_files:
                try:
                    batch_df = pd.read_csv(file)
                    print(f"Read {len(batch_df)} rows from {file}")
                    account_dfs.append(batch_df)
                except Exception as e:
                    print(f"Error reading batch file {file}: {e}")
            
            if account_dfs:
                # Combine all dataframes
                combined_account_df = pd.concat(account_dfs, ignore_index=True)
                
                # Save the combined data
                combined_account_df.to_csv("aggregated_accounts.csv", index=False)
                print(f"Successfully aggregated {len(combined_account_df)} rows from {len(account_dfs)} account batches to aggregated_accounts.csv")
        else:
            print("No account batch files found to aggregate.")
        
        # Then aggregate leads data
        print("Aggregating leads batch files...")
        leads_files = sorted(glob.glob(f"{LEADS_BATCH_DIR}/batch_*_enriched_leads.csv"))
        
        if leads_files:
            # Read and concatenate all batch files
            leads_dfs = []
            for file in leads_files:
                try:
                    batch_df = pd.read_csv(file)
                    print(f"Read {len(batch_df)} rows from {file}")
                    leads_dfs.append(batch_df)
                except Exception as e:
                    print(f"Error reading batch file {file}: {e}")
            
            if leads_dfs:
                # Combine all dataframes
                combined_leads_df = pd.concat(leads_dfs, ignore_index=True)
                
                # Save the combined data
                combined_leads_df.to_csv("aggregated_leads.csv", index=False)
                print(f"Successfully aggregated {len(combined_leads_df)} rows from {len(leads_dfs)} leads batches to aggregated_leads.csv")
        else:
            print("No leads batch files found to aggregate.")
        
    except Exception as e:
        print(f"Error aggregating batch files: {e}")

def main():
    try:
        if ROWS_TO_PROCESS > 0:
            # For testing with a small number of rows
            df = pd.read_csv(CSV_FILE_PATH, nrows=ROWS_TO_PROCESS)
            print(f"Successfully read {len(df)} rows from {CSV_FILE_PATH} to process.")
            if df.empty:
                print("No rows to process.")
                return
            
            # Run the asynchronous processing
            enriched_data, leads_data = asyncio.run(process_rows_concurrently(df))
            
            enriched_df = pd.DataFrame(enriched_data)
            leads_df = pd.DataFrame(leads_data)
            
            try:
                enriched_df.to_csv(OUTPUT_CSV_FILE_PATH, index=False)
                print(f"Successfully wrote {len(enriched_df)} enriched rows to {OUTPUT_CSV_FILE_PATH}")
                
                leads_output = "enriched_leads.csv"
                leads_df.to_csv(leads_output, index=False)
                print(f"Successfully wrote {len(leads_df)} enriched leads to {leads_output}")
            except Exception as e:
                print(f"Error writing CSV: {e}")
        else:
            # Process in batches for the full dataset, starting from batch 18
            process_in_batches(CSV_FILE_PATH, start_batch=18, end_batch=26)
    except FileNotFoundError:
        print(f"Error: The file {CSV_FILE_PATH} was not found.")
        return
    except Exception as e:
        print(f"Error in main function: {e}")
        return

if __name__ == "__main__":
    main()