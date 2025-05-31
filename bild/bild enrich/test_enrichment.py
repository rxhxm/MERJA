import pandas as pd
import asyncio
import httpx
import json
import re
import time

# Configuration
API_KEY = "42342922-b737-43bf-8e67-68be5108be7b"
BASE_URL = "https://api.sixtyfour.ai"
ENRICH_ENDPOINT = "/enrich-company"
INPUT_CSV = "combined_suppliers.csv"
OUTPUT_BASE_NAME = "leads_test_sample"  # Base name for output files
MAX_CONCURRENT = 5
TIMEOUT = 600.0  # 10 minutes per API call
COMPANIES_TO_PROCESS = 5  # Process just 5 companies for quick testing

async def enrich_company(client, semaphore, company_name, description, reference_companies):
    """Enriches a single company via the SixtyFour API"""
    async with semaphore:
        print(f"Processing: {company_name}")
        
        # Create structs for company and people data
        company_struct = {
            "company_linkedin": "LinkedIn profile URL of the company",
            "website": "Official website of the company",
            "num_employees": "Estimated number of employees",
            "industry": "Primary industry of the company",
            "has_div8_estimators": "Does this company employ DIV 8 estimators on staff?",
            "icp_match": f"Is this company similar to other door suppliers like '{', '.join(reference_companies)}'? Yes or No, and explain why.",
            "notes": "Final breakdown on this company's relevance to door manufacturing or supply."
        }
        
        people_struct = {
            "name": "Full name of the person",
            "title": "Job title at the company",
            "linkedin": "LinkedIn profile URL",
            "email": "Email address if available",
            "is_decision_maker": "Is this person a key decision maker? Answer 'Yes' ONLY for C-suite executives, presidents, vice presidents, directors, or department heads."
        }
        
        headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
        payload = {
            "target_company": {"company_name": company_name, "description": description},
            "struct": company_struct,
            "find_people": True,
            "people_focus_prompt": "Find key decision-makers, especially C-suite executives, directors, VPs, and estimators.",
            "people_struct": people_struct,
            "max_people": 10
        }
        
        start_time = time.time()
        try:
            print(f"Starting API call for: {company_name}")
            response = await client.post(
                f"{BASE_URL}{ENRICH_ENDPOINT}",
                headers=headers,
                json=payload,
                timeout=TIMEOUT
            )
            elapsed = time.time() - start_time
            print(f"API call for {company_name} took {elapsed:.2f} seconds with status {response.status_code}")
            
            response.raise_for_status()
            data = response.json()
            
            print(f"Successfully processed {company_name}")
            return {"success": True, "company_name": company_name, "data": data}
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"Error enriching {company_name} after {elapsed:.2f} seconds: {str(e)}")
            return {"success": False, "company_name": company_name, "error": str(e)}

def process_results(results, original_df):
    """Processes API results and creates two dataframes: one for accounts and one for leads"""
    accounts_rows = []
    leads_rows = []
    
    for row_idx, result in enumerate(results):
        # Get original data for the account
        try:
            original_account_row = original_df.iloc[row_idx].to_dict()
        except:
            original_account_row = {"companyName": result.get("company_name", "Unknown")}
        
        account_row = original_account_row.copy()
        current_company_name = account_row.get("companyName", result.get("company_name"))

        if not result.get("success"):
            account_row["api_status"] = "Failed"
            account_row["api_error"] = result.get("error", "Unknown error")
            accounts_rows.append(account_row)
            # Add a placeholder lead row indicating failure for this company
            leads_rows.append({"companyName": current_company_name, "lead_api_status": "Failed due to company error"})
            continue
            
        api_data = result.get("data", {})
        structured_data = api_data.get("structured_data", {})
        api_leads = structured_data.get("leads", [])
        
        # Account Data processing
        account_row["api_status"] = "Success"
        account_row["api_confidence"] = api_data.get("confidence_score")
        
        # Add company fields from structured_data (excluding leads)
        for key, value in structured_data.items():
            if key != "leads":
                account_row[f"api_{key}"] = value
        
        account_row["api_leads_raw_json"] = json.dumps(api_leads) # Store raw leads with the account for reference
        account_row["api_lead_count"] = len(api_leads)

        # Qualification logic for the account
        is_qualified = False
        reasons = []
        if account_row.get("api_confidence", 0) >= 7.0:
            reasons.append("Good confidence score")
        icp_match = account_row.get("api_icp_match", "").lower()
        if "yes" in icp_match or "similar" in icp_match:
            reasons.append("Matches ICP")
            is_qualified = True
        else:
            reasons.append("Does not match ICP")
        
        decision_maker_count_for_qualification = 0
        for lead_data in api_leads:
            if isinstance(lead_data, dict) and "yes" in lead_data.get("is_decision_maker", "").lower():
                decision_maker_count_for_qualification += 1
        
        if decision_maker_count_for_qualification > 0:
            reasons.append(f"Found {decision_maker_count_for_qualification} decision makers")
            is_qualified = is_qualified and True # Can only be true if ICP matched
        else:
            reasons.append("No decision makers found")
            is_qualified = False
            
        account_row["is_qualified"] = is_qualified
        account_row["qualification_reason"] = "; ".join(reasons)
        accounts_rows.append(account_row)

        # Lead Data processing
        if not api_leads: # If no leads, add a row indicating that
            leads_rows.append({
                "companyName": current_company_name,
                "lead_api_status": "No leads found in API response"
            })
        else:
            for lead_data in api_leads:
                if not isinstance(lead_data, dict):
                    leads_rows.append({"companyName": current_company_name, "lead_api_status": "Malformed lead data"})
                    continue
                
                lead_row = {"companyName": current_company_name} # Link to account
                lead_row["lead_name"] = lead_data.get("name", "")
                lead_row["lead_title"] = lead_data.get("title", "")
                lead_row["lead_linkedin"] = lead_data.get("linkedin", "")
                lead_row["lead_email"] = lead_data.get("email", "")
                lead_row["lead_is_decision_maker"] = lead_data.get("is_decision_maker", "").lower()
                # You can add more lead-specific fields from people_struct if needed
                leads_rows.append(lead_row)
    
    accounts_df = pd.DataFrame(accounts_rows)
    leads_df = pd.DataFrame(leads_rows)
    
    return accounts_df, leads_df

async def main():
    # Load data
    start_time = time.time()
    try:
        df = pd.read_csv(INPUT_CSV)
        # Process only specified number of rows
        if COMPANIES_TO_PROCESS > 0:
            df = df.head(COMPANIES_TO_PROCESS)
        print(f"Loaded {len(df)} companies from {INPUT_CSV}")
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return
    
    # Get reference companies for comparison (first 3)
    reference_companies = df['companyName'].head(3).tolist()
    print(f"Using reference companies: {reference_companies}")
    
    # Set up concurrency
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENT, max_connections=MAX_CONCURRENT+5)
    
    # Process companies
    async with httpx.AsyncClient(limits=limits, timeout=TIMEOUT) as client:
        tasks = []
        for _, row in df.iterrows():
            company_name = row.get('companyName')
            description = row.get('description', '')
            
            if not company_name or pd.isna(company_name):
                continue
                
            task = enrich_company(client, semaphore, company_name, description, reference_companies)
            tasks.append(task)
        
        print(f"Processing {len(tasks)} companies using {MAX_CONCURRENT} concurrent workers...")
        results = await asyncio.gather(*tasks)
    
    # Process results and save to two files
    accounts_df, leads_df = process_results(results, df)
    
    accounts_filename = f"{OUTPUT_BASE_NAME}_accounts.csv"
    leads_filename = f"{OUTPUT_BASE_NAME}_leads.csv"
    
    accounts_df.to_csv(accounts_filename, index=False, escapechar='\\', doublequote=True, quoting=1)
    leads_df.to_csv(leads_filename, index=False, escapechar='\\', doublequote=True, quoting=1)
    
    elapsed = time.time() - start_time
    print(f"Successfully processed {len(accounts_df)} accounts and {len(leads_df)} lead entries in {elapsed:.2f} seconds.")
    print(f"Test accounts results saved to {accounts_filename}")
    print(f"Test leads results saved to {leads_filename}")

if __name__ == "__main__":
    asyncio.run(main()) 