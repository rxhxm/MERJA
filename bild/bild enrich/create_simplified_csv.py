import pandas as pd

# Read the full CSV file
print("Reading door_companies.csv...")
df = pd.read_csv('door_companies.csv')
print(f"Found {len(df)} companies")

# Select important columns
important_columns = [
    'company_number', 
    'company_name', 
    'description', 
    'door_product_types',
    'company_size', 
    'address',
    'region', 
    'phone_number',
    'website',
    'has_div8_estimator',
    'lead_name',
    'lead_title'
]

# Keep only columns that exist in the dataframe
columns = [col for col in important_columns if col in df.columns]

# Create a simplified dataframe
simplified_df = df[columns].copy()

# Write to CSV
output_file = 'door_companies_simplified.csv'
simplified_df.to_csv(output_file, index=False)
print(f"Created simplified CSV: {output_file}")

# Print a summary
print("\nDistribution of door companies by region:")
region_counts = df['region'].value_counts()
for region, count in region_counts.items():
    print(f"- {region}: {count}")

print("\nDistribution by company size:")
size_counts = df['company_size'].value_counts()
for size, count in size_counts.items():
    print(f"- {size}: {count}")

print("\nDivision 8 estimator presence:")
div8_counts = df['has_div8_estimator'].value_counts()
for status, count in div8_counts.items():
    print(f"- {status}: {count}") 