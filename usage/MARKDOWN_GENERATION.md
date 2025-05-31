# Markdown Generation Feature

The NMLS HTML processing system now includes **structured markdown generation** in addition to all existing functionality (Supabase database storage, JSON/CSV export).

## Overview

For each HTML file processed, the system can now generate a beautifully structured markdown file containing all extracted company information. This provides human-readable, searchable documentation alongside the database storage.

## Features

- **Structured Markdown**: Clean, organized markdown files with YAML frontmatter
- **Complete Data Coverage**: All extracted fields are included in the markdown
- **Metadata Headers**: YAML frontmatter with key identifiers and timestamps
- **Readable Filenames**: Named as `{nmls_id}_{company_name}.md`
- **Batch Processing**: Handles thousands of files efficiently
- **Quality Preservation**: Includes quality flags and processing errors

## Usage

### 1. Database Processing with Markdown (Main Script)

```bash
# Process files to database AND generate markdown
python process_to_database.py data/virginia --markdown-output ./company_markdown

# With additional options
python process_to_database.py data/virginia \
  --markdown-output ./company_markdown \
  --max-files 100 \
  --batch-size 50
```

### 2. Standalone Extraction with Markdown

```bash
# Extract to JSON/CSV and generate markdown
python nmls_html_extractor.py data/virginia \
  --markdown-output ./extracted_markdown \
  --max-files 10

# Using default markdown directory
python nmls_html_extractor.py data/virginia \
  -o my_extraction  # Creates my_extraction_markdown/ directory
```

## Generated Markdown Structure

Each markdown file contains:

### YAML Frontmatter
```yaml
---
nmls_id: 1232481
company_name: "DOUBLE Y INVESTMENT,INC"
extraction_timestamp: 2025-05-27T01:03:06.342439
source_file: data/virginia/22208/COMPANY/COMPANY_1232481.html
---
```

### Structured Content Sections

1. **Company Name** (H1 header)
2. **Contact Information** - Phone, email, website, fax
3. **Addresses** - Street and mailing addresses
4. **Business Information** - Structure, formation details, fiscal year
5. **MLO Information** - Type and count of mortgage loan originators
6. **Federal Registration** - For banks/credit unions
7. **Trade Names** - Current trade names
8. **Prior Trade Names** - Historical trade names
9. **Prior Legal Names** - Historical legal names  
10. **License Information** - Detailed license data with sub-sections
11. **Regulatory Actions** - Any regulatory issues
12. **Quality and Errors** - Data quality flags
13. **Processing Errors** - Any extraction issues

### License Detail Format

For each license:
```markdown
- License Type: Mortgage Lender License
  - License Number: 216225
  - Regulator: Maryland
  - Original Issue Date: 05/04/2007
  - Status Date: 01/15/2023
  - Renewed Through: 12/31/2023
  - Active: Yes
  - Resident Agent: Home Financial Corporation (Latha Devineni, President)
    - Address: 459 Herndon Parkway Suite # 16; Herndon, MD 20170
    - Phone: 703-456-0032
    - Fax: 703-435-8383
```

## File Organization

Generated files are organized as:
```
company_markdown/
├── 1232481_DOUBLE-Y-INVESTMENTINC.md
├── 1234752_Publix-Super-Markets-Inc.md
├── 216225_Home-Financial-Corporation.md
└── ...
```

**Filename Pattern**: `{nmls_id}_{sanitized_company_name}.md`
- Special characters removed/replaced with hyphens
- Spaces converted to hyphens
- Maximum readability maintained

## Integration with Existing Workflow

The markdown generation is **completely additive** - it doesn't interfere with existing functionality:

✅ **Still does everything it did before:**
- Extracts structured data from HTML
- Stores in Supabase vector database
- Exports JSON and CSV formats
- Provides comprehensive logging and statistics

✅ **Plus new markdown generation:**
- Individual markdown file per company
- Human-readable format
- Searchable with standard tools
- Git-friendly for version control

## Benefits

1. **Human Readability**: Beautiful, structured documentation
2. **Searchability**: Standard markdown tools and grep work perfectly
3. **Version Control**: Git-friendly format for tracking changes
4. **Documentation**: Self-documenting company profiles
5. **Integration**: Works with static site generators, wikis, etc.
6. **Backup**: Additional format for data preservation

## Command Line Options

### process_to_database.py
- `--markdown-output DIR`: Directory to save markdown files (optional)

### nmls_html_extractor.py  
- `--markdown-output DIR`: Directory to save markdown files (optional)
- If not specified, uses `{output_prefix}_markdown/`

## Examples

### Example 1: Process 50 companies to database + markdown
```bash
python process_to_database.py data/virginia \
  --max-files 50 \
  --markdown-output ./virginia_companies_md
```

### Example 2: Extract subset with all formats
```bash
python nmls_html_extractor.py data/virginia \
  --max-files 20 \
  --output virginia_test \
  --markdown-output ./test_markdown \
  --format both
```

## Performance

- **Memory Efficient**: Processes files in batches
- **Fast Generation**: Markdown creation is lightweight
- **Scalable**: Handles thousands of files without issues
- **Error Handling**: Failed markdown generation doesn't stop processing

## Quality Assurance

- **Complete Data**: All extracted fields included
- **Error Reporting**: Processing errors documented in markdown
- **Quality Flags**: Data quality issues highlighted
- **Validation**: Consistent structure across all files

---

This feature makes the NMLS processing system even more valuable by providing human-readable documentation alongside the structured database storage! 