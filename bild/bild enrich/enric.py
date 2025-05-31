import requests
import pandas as pd
import json
import os

# Set your API key
API_KEY = "42342922-b737-43bf-8e67-68be5108be7b"

# List of companies to enrich
companies = [
    "Granite Construction",
    "Acc Exteriors",
    "Coastal Doors",
    "Beacon Metals",
    "Giuliano Commerical Doors",
    "CM Controls",
    "Central Builders",
    "Madison Floors",
    "Four Corners Building Supply",
    "Doorwayz Inc",
    "EuroTherm",
    "Suffolk",
    "Central Valley Hardware",
    "RT Doors",
    "Goschiller",
    "Wausau Building Supply"
]

# companies = [
#     "Granite Construction",
#     "Acc Exteriors",
# ]

# Define the enrichment fields you want to collect
# struct = {
#     "company_name": "Full company name",
#     "website": "Company website URL",
#     "company_linkedin": "LinkedIn URL for the company",
#     "address": "Physical address",
#     "phone_number": "Contact phone number",
#     "description": "Brief description of their business",
#     "is_door_supplier": "Are they a door supplier? yes or no",
#     "is_Emullion_customer": "Are they an Emullion software customer? yes or no",
#     "has_div8_estimator": "Do they have a Div 8 estimator position? yes or no",
#     "would_be_good_Emullion_customer": "Would they be a good fit for Emullion's ICP? yes or no",
#     "target_decision_makers": "Who would be the decision makers for software procurement?"
# }

struct = {
    # Basic company information
    "company_name": "Full company name",
    "website": "Company website URL",
    "company_linkedin": "LinkedIn URL for the company",
    "description": "Brief description of their business",
    "company_size": "Approximate number of employees",
    
    # Location information
    "address": "Physical address",
    "phone_number": "Contact phone number",
    "region": "Which region of the US do they primarily operate in?",
    "other_locations": "Any additional office locations beyond their headquarters",
    
    # Door supplier information
    "is_door_supplier": "Are they a door supplier? yes or no",
    "door_product_types": "What types of doors do they supply? (commercial, residential, etc.)",
    
    # Estimation positions
    "has_div8_estimator": "Do they have a Div 8 estimator position? yes or no",
    "estimator_position_details": "Details about any estimator positions, especially Div 8 estimators",
    "has_job_postings_with_emilian": "Do they have job postings that mention Emilian as a skill? yes or no",
    
    # Software usage
    "is_Emullion_customer": "Are they an Emullion software customer? yes or no",
    "would_be_good_Emullion_customer": "Would they be a good fit for Emullion's ICP? yes or no",
    "uses_bluebeam": "Do they use Bluebeam for takeoffs and estimating? yes or no",
    "uses_planswift": "Are they using PlanSwift for door estimating? yes or no",
    "uses_stack": "Do they use STACK takeoff and estimating software? yes or no",
    "uses_proest": "Is this company using ProEst estimating software? yes or no",
    "uses_on_center": "Do they use On-Center software for estimating? yes or no",
    "technology_stack": "What other software tools they currently use",
    
    # Decision makers
    "target_decision_makers": "Who would be the decision makers for software procurement?",
    "software_decision_makers": "People who make decisions about software purchases"
}

# Function to enrich a company
def enrich_company(company_name):
    target_company = {"company_name": company_name}
    
    response = requests.post(
        "https://api.sixtyfour.ai/enrich-company",
        headers={
            "x-api-key": API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "target_company": target_company,
            "struct": struct,
            "find_people": True,
            "research_plan": "Look for information about whether they are door suppliers, if they use Emullion software, or if they have Div 8 estimator positions. Check job postings, company descriptions, and software mentions.",
            "people_focus_prompt": "Find C-level executives and anyone involved in procurement or software decisions"
        }
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error enriching {company_name}: {response.status_code}")
        print(response.text)
        return None

# Process each company
results = []
# Check if file exists to determine if headers should be written
file_exists = os.path.isfile("enriched_door_suppliers.csv")
qualified_file_exists = os.path.isfile("qualified_leads.csv")

for company in companies:
    print(f"Enriching {company}...")
    result = enrich_company(company)
    if result:
        # Process single company result
        company_enriched_data = []
        if "structured_data" in result:
            data = result["structured_data"]
            # Add confidence score
            data["confidence_score"] = result.get("confidence_score", 0)
            
            # Extract leads if available
            if "leads" in data:
                for lead in data["leads"]:
                    lead_data = data.copy()
                    del lead_data["leads"]
                    for key, value in lead.items():
                        lead_data[f"lead_{key}"] = value
                    company_enriched_data.append(lead_data)
            else:
                company_enriched_data.append(data)
        
        # Create DataFrame for this company only
        company_df = pd.DataFrame(company_enriched_data)
        
        # Save to CSV (append mode for all but first)
        company_df.to_csv("enriched_door_suppliers.csv", mode='a', header=not file_exists, index=False)
        print(f"Updated enriched_door_suppliers.csv with {len(company_df)} records for {company}")
        file_exists = True  # For subsequent writes
        
        # Filter qualified companies
        if not company_df.empty and "is_Emullion_customer" in company_df.columns and "would_be_good_Emullion_customer" in company_df.columns:
            qualified_company_df = company_df[(company_df["is_Emullion_customer"] == "yes") | 
                                         (company_df["would_be_good_Emullion_customer"] == "yes")]
        
        # Save qualified to CSV (append mode for all but first)
        if not qualified_company_df.empty:
            qualified_company_df.to_csv("qualified_leads.csv", mode='a', header=not qualified_file_exists, index=False)
            print(f"Updated qualified_leads.csv with {len(qualified_company_df)} qualified leads for {company}")
            qualified_file_exists = True  # For subsequent writes