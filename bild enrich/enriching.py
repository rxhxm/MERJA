import requests
import pandas as pd
import json

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
for company in companies:
    print(f"Enriching {company}...")
    result = enrich_company(company)
    if result:
        results.append(result)

# Convert results to DataFrame
enriched_data = []
for result in results:
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
                enriched_data.append(lead_data)
        else:
            enriched_data.append(data)

# Create DataFrame
df = pd.DataFrame(enriched_data)

# Save to CSV
df.to_csv("enriched_door_suppliers.csv", index=False)
print(f"Saved {len(df)} enriched records to enriched_door_suppliers.csv")

# Filter qualified companies (door suppliers that are Emullion customers or have Div 8 estimators)
# qualified = df[(df["is_door_supplier"] == "yes") & 
#               ((df["is_Emullion_customer"] == "yes") | 
#                (df["has_div8_estimator"] == "yes") |
#                (df["would_be_good_Emullion_customer"] == "yes"))]

# Apply the new qualification criteria
qualified_df = df[(df["is_Emullion_customer"] == "yes") | 
                  (df["would_be_good_Emullion_customer"] == "yes")]


qualified_df.to_csv("qualified_leads.csv", index=False)
print(f"Saved {len(qualified_df)} qualified leads to qualified_leads.csv")