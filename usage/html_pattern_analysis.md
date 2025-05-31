# HTML Pattern Analysis: NMLS Company Data Extraction Guide

## Overview
Analysis of 60 sample HTML files from NMLS Consumer Access database reveals consistent structure with specific variations. This document catalogues all identified patterns for building a robust data extractor.

## File Metadata Pattern
**Location**: HTML comment at top of every file
```html
<!--
====================================================================================================
URL: https://nmlsconsumeraccess.org/EntityDetails.aspx/COMPANY/{ID}
Type: company
ID: {NMLS_ID}
Timestamp: {ISO_TIMESTAMP}
ZIP: {ZIP_CODE}
-->
```

**Extraction Strategy**: Parse this comment block for URL, NMLS ID, timestamp, and ZIP code.

## Core Company Information Structure

### 1. Company Name
**Pattern**: `<p class="company"> {COMPANY_NAME} </p>`
**Location**: Within `<div class="grid_950 summary">`
**Variations**: Always present, single line
**Examples**: 
- "First Securities Financial Services, Inc."
- "The National Bank of Blacksburg"
- "Credit Karma Mortgage, Inc."
- "Virginia Federal Credit Union"
- "Cornerstone Capital Bank, SSB"

### 2. Basic Company Details Table
**Pattern**: Nested tables within `<table class="data">`
**Structure**: 4-column layout with contact and address information

#### Column 1: NMLS ID
```html
<td class="label"><span class="nowrap">NMLS ID:</span></td>
<td>{NMLS_ID}</td>
```

#### Column 2: Addresses
**Street Address**:
```html
<td class="label"><span class="nowrap">Street&nbsp;Address:</span></td>
<td>
    <span class="nowrap">{ADDRESS_LINE_1}</span><br>
    <span class="nowrap">{ADDRESS_LINE_2}</span><br>  <!-- Optional -->
    <span class="nowrap">{CITY}, {STATE} {ZIP}</span><br>
</td>
```

**Mailing Address**: Same structure, may be identical to street address

#### Column 3: Phone Information
```html
<td class="label">Phone:</td>
<td class="nowrap">{PHONE_NUMBER}</td>

<td class="label"><span class="nowrap">Toll-Free Number:</span></td>
<td class="nowrap">{TOLL_FREE_OR_STATUS}<br></td>  <!-- May be "Not provided", "N/A", or number -->

<td class="label">Fax:</td>
<td class="nowrap">{FAX_NUMBER}</td>
```

#### Column 4: Digital Contact
```html
<td class="label">Website:</td>
<td>{WEBSITE_OR_STATUS}</td>  <!-- May be "N/A" or actual URL -->

<td class="label">Email:</td>
<td>{EMAIL_ADDRESS}</td>
```

### 3. Trade Names and History
**Pattern**: Separate table with label-value pairs
```html
<td class="label">
    <span class="nowrap">Other&nbsp;Trade&nbsp;Names</span>
</td>
<td>{TRADE_NAMES_SEMICOLON_SEPARATED}</td>

<td class="label">
    <span class="nowrap">Prior&nbsp;Other&nbsp;Trade&nbsp;Names</span>
</td>
<td>{PRIOR_TRADE_NAMES_OR_NONE}</td>

<td class="label">
    <span class="nowrap">Prior&nbsp;Legal&nbsp;Names</span>
</td>
<td>{PRIOR_LEGAL_NAMES_OR_NONE}</td>
```

**Variations**: 
- May contain "None" for empty fields
- Multiple names separated by semicolons
- Some companies may not have all sections

### 4. MLO Information
**Two possible patterns**:

**Pattern A - Sponsored MLOs (Non-Bank)**:
```html
<td class="label">
    <span class="nowrap">Sponsored&nbsp;MLOs</span>
</td>
<td>{NUMBER}</td>
```

**Pattern B - Registered MLOs (Bank)**:
```html
<td class="label">
    <span class="nowrap">Registered&nbsp;MLOs</span>
</td>
<td>{NUMBER}</td>
```

### 5. Business Structure Information
**Pattern**: Single row table with multiple columns
```html
<td class="label">Fiscal&nbsp;Year&nbsp;End:</td>
<td class="divider">{MM/DD}</td>

<td class="label">Formed&nbsp;in:</td>
<td class="divider">{STATE}, United States</td>

<td class="label">Date&nbsp;Formed:</td>
<td class="divider">{MM/DD/YYYY}</td>

<td class="label">Stock&nbsp;Symbol:</td>
<td class="divider">{SYMBOL_OR_NONE}</td>

<td class="label">Business&nbsp;Structure:</td>
<td>{STRUCTURE}</td>  <!-- Corporation, LLC, etc. -->
```

### 6. Regulatory Actions
**Pattern**: Simple indicator
```html
<td class="label">
    <span class="nowrap">Regulatory&nbsp;Actions</span>
</td>
<td>
    <a href="#RegulatoryActions">Yes</a>  <!-- OR "No" -->
</td>
```

## Branch Locations Section

### Pattern 1: No Branches
```html
<div class="header">
    <h1>Branch Locations</h1>
    <div class="subText">No Branch Locations in NMLS</div>
</div>
```

### Pattern 2: Has Branches
```html
<div class="header">
    <h1>Branch Locations</h1>
    <div class="subText">
        ({ACTIVE_COUNT} Active, {INACTIVE_COUNT} Inactive)
    </div>
    <div class="button">
        <a href="/EntityDetails.aspx/Branches/{NMLS_ID}">
            <img src="/img/but-viewAllBranches.gif" alt="view all branches">
        </a>
    </div>
</div>
```

## State Licenses/Registrations Section

### Header Pattern
```html
<div class="header">
    <h1>State Licenses/Registrations</h1>
    <div class="text">
        (Displaying
        <span id="activeLicenseCount">{ACTIVE_COUNT}</span>
        Active<span id="inactiveLicenseText">, {INACTIVE_COUNT} Inactive</span> of
        {TOTAL_COUNT}
        Total)
    </div>
</div>
```

### License Table Structure
**Header Row**:
```html
<tr class="licenseHeader">
    <th align="left">Regulator</th>
    <th align="left">Lic/Reg Name</th>
    <th align="center">Authorized to Conduct Business</th>
    <th align="center">Consumer Complaint</th>
    <td align="right" class="colHeader">...</td>
</tr>
```

### License Row Patterns
**Active License**:
```html
<tr class="viewLicense">
    <td scope="row">
        <a class="externalLink" href="{REGULATOR_URL}" target="_blank">{STATE_NAME}</a>
    </td>
    <td>{LICENSE_TYPE}</td>
    <td align="center">{YES_OR_NO}</td>
    <td align="center">
        <a class="externalLink" href="{COMPLAINT_URL}" target="_blank">Submit to Regulator</a>
    </td>
    <td align="right">
        <div class="button">
            <a id="viewDetails_{LICENSE_ID}" href="#" class="hideDetails">Hide Details</a>
        </div>
    </td>
</tr>
```

**Inactive License**:
```html
<tr class="viewLicense inactive">
    <!-- Same structure but with "inactive" class -->
</tr>
```

### License Details Pattern
**Expandable details section**:
```html
<tr id="licenseDetails_{LICENSE_ID}" class="viewLicenseDetails" style="display: table-row;">
    <td colspan="5" class="collapse">
        <table border="0" cellspacing="0" cellpadding="0" class="subData">
            <tr>
                <td>
                    <span class="label">Lic/Reg #:</span>
                    {LICENSE_NUMBER}
                </td>
                <td colspan="2">
                    <span class="label">Original Issue Date:</span>
                    {MM/DD/YYYY}
                </td>
            </tr>
            <tr>
                <td>
                    <span class="label">Status:</span>
                    {LICENSE_STATUS}  <!-- Approved, Revoked, Voluntary Surrender, etc. -->
                </td>
                <td>
                    <span class="label">Status Date:</span>
                    {MM/DD/YYYY}
                </td>
                <td>
                    <span class="label">Renewed Through:</span>
                    {YEAR_OR_NONE}
                </td>
            </tr>
        </table>
        <table border="0" cellspacing="0" cellpadding="0" class="subData">
            <tr>
                <td>
                    <span class="label">Other Trade Names used in {STATE_NAME}:</span>
                    {TRADE_NAMES_OR_NONE}
                </td>
            </tr>
        </table>
        <!-- OPTIONAL: Resident/Registered Agent Section -->
        <div class="grid_620 details residentAgent">
            <div class="header">
                <h1>Resident/Registered Agent for Service of Process</h1>
            </div>
            <div class="instructionalText">
                The agent(s) listed below have been designated to accept the delivery of legal documents,
                such as summons, complaints, subpoenas, and orders, on behalf of the company.
                This contact information is for the delivery of legal documents only.
            </div>
            <table class="popupData">
                <tr>
                    <td><span class="label">Company:</span></td>
                    <td>{AGENT_COMPANY_NAME}</td>
                </tr>
                <tr>
                    <td><span class="label">Name:</span></td>
                    <td>{AGENT_NAME_OR_NOT_PROVIDED}</td>
                </tr>
                <tr>
                    <td><span class="label">Title:</span></td>
                    <td>{AGENT_TITLE}</td>  <!-- Usually "Registered Agent" -->
                </tr>
                <tr>
                    <td><span class="label">Address:</span></td>
                    <td>{AGENT_ADDRESS_MULTILINE}</td>
                </tr>
            </table>
        </div>
    </td>
</tr>
```

## Federal Registration Section (Banks & Credit Unions)

### Pattern for Banks
```html
<div class="header">
    <h1>Federal Registration</h1>
</div>
<table class="data">
    <tr>
        <th align="left">Primary Federal Regulator</th>
        <th align="left">Status</th>
    </tr>
    <tr>
        <td>
            <a class="externalLink" href="{REGULATOR_URL}" target="_blank">{REGULATOR_NAME}</a>
        </td>
        <td>
            {REGISTRATION_STATUS}
        </td>
    </tr>
</table>
```

### Federal Regulators Identified
- **FDIC**: "Federal Deposit Insurance Corporation"
- **NCUA**: "National Credit Union Administration - Federally Insured"
- **OCC**: "Office of the Comptroller of the Currency" (confirmed)
- **Federal Reserve**: "Board of Governors of the Federal Reserve System" (confirmed)

## License Type Catalog (EXPANDED)
**Comprehensive list of observed license types**:

### Consumer/Personal Finance
- Consumer Credit License
- Consumer Collection Agency License
- Consumer Loan Company License
- Consumer Lender License
- Consumer Installment Loan License
- Consumer Installment Loan Act License
- Collection Agency License
- Collection Agency Registration
- Collection Agency Manager
- Debt Collection License
- Installment Lender License
- Supervised Lender License
- Lender License
- Money Lender License
- Regulated Lender License

### Check Cashing & Money Services
- Check Casher License
- Check Casher with Small Loan Endorsement
- Check Seller, Money Transmitter License
- Money Transmitter License
- Money Transmitters License
- Money Transmitters
- Sale of Checks and Money Transmitters
- Sale of Checks and Money Transmitter License

### Payday & Alternative Financial Services (NEW)
- Payday/Title Loan License

### Sales Finance
- Sales Finance Company License

### Industrial & Specialized Finance (NEW)
- Industrial Loan and Thrift Company Registration

### Loan Servicing
- Mortgage Servicer License
- Mortgage Lender Servicer License
- Mortgage Lender / Servicer License
- Mortgage Lender/Servicer License - Other Trade Name #1
- Mortgage Lender/Servicer License - Other Trade Name #4
- Mortgage Lender/Servicer License - Other Trade Name #6
- Third Party Loan Servicer License
- Loan Servicer License
- Supplemental Mortgage Servicer License
- 1st Mortgage Broker/Lender/Servicer License

### Mortgage-Related
- Mortgage License
- Mortgage Lender License
- Mortgage Lending License (NEW)
- Mortgage Broker License
- Mortgage Broker/Lender License
- Mortgage Lender/Broker License
- Mortgage Broker/Processor License
- Mortgage Banker License
- Mortgage Banker Registration
- Mortgage Company Registration (NEW)
- Mortgage Dual Authority License (NEW)
- Partially Exempt Mortgage Company Registration (NEW)
- Mortgage Loan Company License
- Residential Mortgage License
- Residential Mortgage Lender License
- Residential Mortgage Lending License (NEW)
- Residential Mortgage Lending Act License (NEW)
- Residential Mortgage Lending Act Certificate of Registration (NEW)
- Residential Mortgage Lending Act Letter of Exemption (NEW)
- Correspondent Residential Mortgage Lender License
- 1st Mortgage Broker/Lender License
- Combination Mortgage Banker-Broker-Servicer License

### Specialty Registration
- Master Loan Company Registration

### General Broker/Lender
- Broker License
- Loan Broker License

### License Status Variations (EXPANDED)
**All observed license statuses**:
- **Active Statuses**: Approved, Active
- **Inactive Statuses**: Revoked, Voluntary Surrender, Suspended, Terminated, Expired, Withdrawn, Denied
- **Special Cases**: "Present" (for ongoing licenses), "Not Currently Authorized"

## Resident/Registered Agent Section (NEW)

### Pattern: Legal Document Service Agent
**Location**: Within license detail sections for some licenses
**Purpose**: Designated agent for receiving legal documents

```html
<div class="grid_620 details residentAgent">
    <div class="header">
        <h1>Resident/Registered Agent for Service of Process</h1>
    </div>
    <div class="instructionalText">
        The agent(s) listed below have been designated to accept the delivery of legal documents,
        such as summons, complaints, subpoenas, and orders, on behalf of the company.
        This contact information is for the delivery of legal documents only.
    </div>
    <table class="popupData">
        <tr>
            <td><span class="label">Company:</span></td>
            <td>{AGENT_COMPANY_NAME}</td>
        </tr>
        <tr>
            <td><span class="label">Name:</span></td>
            <td>{AGENT_NAME_OR_NOT_PROVIDED}</td>
        </tr>
        <tr>
            <td><span class="label">Title:</span></td>
            <td>{AGENT_TITLE}</td>  <!-- Usually "Registered Agent" -->
        </tr>
        <tr>
            <td><span class="label">Address:</span></td>
            <td>{AGENT_ADDRESS_MULTILINE}</td>
        </tr>
    </table>
</div>
```

**Common Agent Companies**:
- Corporation Service Company
- Registered Agents Inc
- C T Corporation System
- The Corporation Trust Company

**Individual Agent Variations**:
- Company Presidents
- Company Owners
- Other company officers (when professional service not used)

**Agent Title Variations**:
- "Registered Agent" (professional services)
- "President" (company officers)
- "Owner" (individual business owners)
- "Not provided" (when agent company is used)

## Data Extraction Strategy

### Critical Fields to Extract:
1. **Metadata**: NMLS ID, URL, timestamp, ZIP
2. **Company Identity**: Legal name, trade names, prior names
3. **Location**: Street/mailing addresses, formed state
4. **Contact**: Phone, fax, toll-free, email, website
5. **Business Info**: Structure, formation date, fiscal year, stock symbol
6. **Personnel**: Sponsored/Registered MLO count
7. **Regulatory**: Actions indicator, all licenses with details
8. **Federal**: Primary regulator and status (for banks/credit unions)
9. **Geographic Presence**: All states with active licenses
10. **Legal Agents**: Resident/Registered agents for service of process (when present)

### Parsing Approach:
1. **Sequential Section Parsing**: Process each major section in order
2. **Table-Based Extraction**: Use CSS selectors for table data
3. **State-Aware Processing**: Track license sections and details
4. **Federal Registration Handling**: Special processing for banks/credit unions
5. **License Type Recognition**: Handle all identified license variations including servicer types
6. **Agent Extraction**: Capture resident/registered agent details when present
7. **Error Handling**: Graceful degradation for missing sections
8. **Validation**: Cross-check extracted data for consistency

### Edge Cases Identified:
1. **Missing Sections**: Some companies lack certain information blocks
2. **Empty Values**: "None", "N/A", "Not provided" variants
3. **Format Variations**: Phone numbers, dates, addresses
4. **Complex Trade Names**: Multiple names with various separators
5. **License Variations**: Different license types and statuses
6. **Bank vs Non-Bank**: Different MLO patterns and registration types
7. **Federal vs State-Only**: Banks have federal registration, others don't
8. **License Status History**: Some licenses have detailed status tracking
9. **Business Structure Variations**: Corporation, LLC, Credit Union, Bank, etc.
10. **Conditional Agent Sections**: Resident/Registered agents only present for certain licenses
11. **License Trade Name Variations**: Some licenses have numbered trade name variations
12. **Servicer License Complexity**: Multiple types of servicing licenses with overlapping names

### Quality Checks:
1. **Required Fields**: NMLS ID, company name must be present
2. **Format Validation**: Phone numbers, dates, email formats
3. **Business Logic**: License status consistency
4. **Geographic Validation**: State name standardization
5. **Completeness**: Ensure all sections are processed
6. **Federal Registration**: Validate presence for banks/credit unions
7. **License Type Validation**: Match against known license catalog including servicer types
8. **Agent Data Validation**: Ensure agent information is properly structured when present
9. **Business Structure Validation**: Handle Corporation, LLC, and other entity types properly
10. **Payday/Alternative Finance Recognition**: Identify payday loan and alternative financial service providers
11. **Industrial Finance Detection**: Recognize specialized industrial loan companies
12. **Exemption/Special Registration Recognition**: Identify exempt entities and special processing arrangements
13. **Mortgage Registration Variants**: Handle standard, dual authority, and partially exempt registrations

This analysis provides the foundation for building a robust, comprehensive data extractor that can handle the full range of variations in the NMLS HTML files, including all patterns discovered in the expanded 120-file sample set across diverse company types, license categories, business structures, and regulatory exemptions. The additional 20 files (101-120) confirmed existing patterns without revealing significant new variations, indicating that the documented patterns comprehensively cover the data structure variations present in the NMLS database.

## Business Structure Variations (NEW SECTION)

### Observed Business Structures
**Complete list of business entity types found**:
- **Corporation**: Traditional corporate structure
- **Limited Liability Company**: LLC entities 
- **Credit Union**: Federal credit unions (special regulatory structure)
- **Bank**: National and state banks with federal oversight

### Business Structure Pattern
**Location**: Within business information table
```html
<td class="label">Business&nbsp;Structure:</td>
<td>{STRUCTURE}</td>  <!-- Corporation, Limited Liability Company, etc. -->
```

**Variations**:
- "Corporation" (most common)
- "Limited Liability Company" (LLC entities)
- Credit unions typically don't show this field but are identified by NCUA regulation
- Banks typically don't show this field but are identified by federal regulation (OCC, FDIC) 

### Exempt/Special Registration Types (NEW CATEGORY)
- Exempt Registration
- Exempt Entity Registration
- Exempt Company Registration
- Exempt Entity Processor Registration
- Residential Mortgage Originator Exemption
- Third Party Processing and/or Underwriting Company Exemption 