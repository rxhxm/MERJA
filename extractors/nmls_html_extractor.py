#!/usr/bin/env python3
"""
NMLS HTML Data Extractor
Ultimate script for extracting structured data from NMLS Consumer Access HTML files.
Based on comprehensive pattern analysis of 160+ sample files.

Features:
- Handles all documented license types (50+ variations)
- Supports all business structures (Corporation, LLC, Bank, Credit Union)
- Extracts federal registration for banks/credit unions
- Captures resident/registered agent information
- Comprehensive error handling and validation
- Configurable batch processing
- Quality checks and data validation
- Supports both JSON and CSV output formats
"""

import os
import re
import json
import csv
import logging
import argparse
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from bs4 import BeautifulSoup
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('nmls_extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class ContactInfo:
    """Contact information structure"""
    phone: Optional[str] = None
    toll_free: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

@dataclass
class Address:
    """Address structure"""
    street_lines: List[str] = field(default_factory=list)
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    full_address: Optional[str] = None

@dataclass
class BusinessInfo:
    """Business structure and formation information"""
    structure: Optional[str] = None
    formed_in: Optional[str] = None
    date_formed: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    stock_symbol: Optional[str] = None

@dataclass
class MLOInfo:
    """MLO (Mortgage Loan Originator) information"""
    type: Optional[str] = None  # "sponsored" or "registered"
    count: Optional[int] = None

@dataclass
class FederalRegistration:
    """Federal registration for banks and credit unions"""
    regulator: Optional[str] = None
    status: Optional[str] = None
    regulator_url: Optional[str] = None

@dataclass
class ResidentAgent:
    """Resident/Registered agent for service of process"""
    company: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None

@dataclass
class LicenseDetails:
    """License/Registration details"""
    license_id: Optional[str] = None
    license_number: Optional[str] = None
    regulator: Optional[str] = None
    license_type: Optional[str] = None
    status: Optional[str] = None
    original_issue_date: Optional[str] = None
    status_date: Optional[str] = None
    renewed_through: Optional[str] = None
    authorized_to_conduct_business: Optional[bool] = None
    active: bool = True
    state_trade_names: Optional[str] = None
    resident_agent: Optional[ResidentAgent] = None

@dataclass
class CompanyData:
    """Main company data structure"""
    # Metadata
    nmls_id: Optional[str] = None
    url: Optional[str] = None
    timestamp: Optional[str] = None
    zip_code: Optional[str] = None
    
    # Company Identity
    company_name: Optional[str] = None
    trade_names: List[str] = field(default_factory=list)
    prior_trade_names: List[str] = field(default_factory=list)
    prior_legal_names: List[str] = field(default_factory=list)
    
    # Location and Contact
    street_address: Optional[Address] = None
    mailing_address: Optional[Address] = None
    contact_info: Optional[ContactInfo] = None
    
    # Business Information
    business_info: Optional[BusinessInfo] = None
    mlo_info: Optional[MLOInfo] = None
    
    # Regulatory
    regulatory_actions: Optional[str] = None
    federal_registration: Optional[FederalRegistration] = None
    licenses: List[LicenseDetails] = field(default_factory=list)
    
    # Processing metadata
    extraction_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    file_path: Optional[str] = None
    processing_errors: List[str] = field(default_factory=list)
    quality_flags: List[str] = field(default_factory=list)

class NMLSHTMLExtractor:
    """Main extraction class for NMLS HTML files"""
    
    def __init__(self):
        self.known_license_types = self._load_known_license_types()
        self.known_business_structures = {
            "Corporation", "Limited Liability Company", "Credit Union", "Bank"
        }
        self.known_federal_regulators = {
            "Federal Deposit Insurance Corporation": "FDIC",
            "National Credit Union Administration - Federally Insured": "NCUA", 
            "Office of the Comptroller of the Currency": "OCC",
            "Board of Governors of the Federal Reserve System": "Federal Reserve"
        }
        self.stats = {
            "processed": 0,
            "successful": 0,
            "errors": 0,
            "quality_issues": 0
        }
    
    def _load_known_license_types(self) -> set:
        """Load all known license types from the analysis"""
        return {
            # Consumer/Personal Finance
            "Consumer Credit License", "Consumer Collection Agency License",
            "Consumer Loan Company License", "Consumer Lender License",
            "Consumer Installment Loan License", "Consumer Installment Loan Act License",
            "Collection Agency License", "Collection Agency Registration",
            "Collection Agency Manager", "Debt Collection License",
            "Installment Lender License", "Supervised Lender License",
            "Lender License", "Money Lender License", "Regulated Lender License",
            
            # Check Cashing & Money Services
            "Check Casher License", "Check Casher with Small Loan Endorsement",
            "Check Seller, Money Transmitter License", "Money Transmitter License",
            "Money Transmitters License", "Money Transmitters",
            "Sale of Checks and Money Transmitters", "Sale of Checks and Money Transmitter License",
            
            # Payday & Alternative Financial Services
            "Payday/Title Loan License",
            
            # Sales Finance
            "Sales Finance Company License",
            
            # Industrial & Specialized Finance
            "Industrial Loan and Thrift Company Registration",
            
            # Loan Servicing
            "Mortgage Servicer License", "Mortgage Lender Servicer License",
            "Mortgage Lender / Servicer License", "Mortgage Lender/Servicer License",
            "Third Party Loan Servicer License", "Loan Servicer License",
            "Supplemental Mortgage Servicer License", "1st Mortgage Broker/Lender/Servicer License",
            
            # Mortgage-Related
            "Mortgage License", "Mortgage Lender License", "Mortgage Lending License",
            "Mortgage Broker License", "Mortgage Broker/Lender License",
            "Mortgage Lender/Broker License", "Mortgage Broker/Processor License",
            "Mortgage Banker License", "Mortgage Banker Registration",
            "Mortgage Company Registration", "Mortgage Dual Authority License",
            "Partially Exempt Mortgage Company Registration", "Mortgage Loan Company License",
            "Residential Mortgage License", "Residential Mortgage Lender License",
            "Residential Mortgage Lending License", "Residential Mortgage Lending Act License",
            "Residential Mortgage Lending Act Certificate of Registration",
            "Residential Mortgage Lending Act Letter of Exemption",
            "Correspondent Residential Mortgage Lender License",
            "1st Mortgage Broker/Lender License", "Combination Mortgage Banker-Broker-Servicer License",
            
            # Specialty Registration
            "Master Loan Company Registration",
            
            # General Broker/Lender
            "Broker License", "Loan Broker License",
            
            # Exempt/Special Registration Types
            "Exempt Registration", "Exempt Entity Registration", "Exempt Company Registration",
            "Exempt Entity Processor Registration", "Residential Mortgage Originator Exemption",
            "Third Party Processing and/or Underwriting Company Exemption"
        }
    
    def extract_metadata(self, html_content: str) -> Dict[str, str]:
        """Extract metadata from HTML comment at top of file"""
        metadata = {}
        
        # Look for the metadata comment block
        comment_pattern = r'<!--\s*={40,}\s*URL:\s*([^\n]+)\s*Type:\s*([^\n]+)\s*ID:\s*([^\n]+)\s*Timestamp:\s*([^\n]+)\s*ZIP:\s*([^\n]+)'
        match = re.search(comment_pattern, html_content, re.MULTILINE | re.DOTALL)
        
        if match:
            metadata['url'] = match.group(1).strip()
            metadata['type'] = match.group(2).strip()
            metadata['nmls_id'] = match.group(3).strip()
            metadata['timestamp'] = match.group(4).strip()
            metadata['zip_code'] = match.group(5).strip()
        
        return metadata
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return None
        
        # Remove extra whitespace and HTML entities
        text = re.sub(r'\s+', ' ', text.strip())
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        
        # Handle common "empty" values
        if text.lower() in ['none', 'n/a', 'not provided', 'not available', '']:
            return None
        
        return text
    
    def parse_address(self, address_element) -> Address:
        """Parse address from HTML element"""
        if not address_element:
            return None
        
        address = Address()
        spans = address_element.find_all('span', class_='nowrap')
        
        if spans:
            lines = []
            for span in spans:
                line = self.clean_text(span.get_text())
                if line:
                    lines.append(line)
            
            if lines:
                address.street_lines = lines[:-1] if len(lines) > 1 else []
                
                # Parse city, state, zip from last line
                if lines:
                    last_line = lines[-1]
                    # Pattern: City, ST ZIP
                    match = re.match(r'^(.+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', last_line)
                    if match:
                        address.city = match.group(1).strip()
                        address.state = match.group(2).strip()
                        address.zip_code = match.group(3).strip()
                    else:
                        address.street_lines.append(last_line)
                
                address.full_address = '; '.join(lines)
        
        return address if address.street_lines or address.city else None
    
    def extract_company_name(self, soup: BeautifulSoup) -> str:
        """Extract company name"""
        company_elem = soup.find('p', class_='company')
        if company_elem:
            return self.clean_text(company_elem.get_text())
        return None
    
    def extract_basic_info(self, soup: BeautifulSoup) -> Dict:
        """Extract basic company information from main data tables"""
        data = {
            'nmls_id': None,
            'contact_info': ContactInfo(),
            'street_address': None,
            'mailing_address': None,
            'trade_names': [],
            'prior_trade_names': [],
            'prior_legal_names': [],
            'mlo_info': MLOInfo(),
            'business_info': BusinessInfo(),
            'regulatory_actions': None
        }
        
        # Find all data tables
        data_tables = soup.find_all('table', class_='data')
        
        for table in data_tables:
            # Process main table rows
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label_elem = cells[0]
                    value_elem = cells[1]
                    
                    label = self.clean_text(label_elem.get_text())
                    value = self.clean_text(value_elem.get_text())
                    
                    if not label:
                        continue
                    
                    # NMLS ID
                    if 'NMLS ID' in label:
                        data['nmls_id'] = value
                    
                    # Addresses
                    elif 'Street Address' in label:
                        data['street_address'] = self.parse_address(value_elem)
                    elif 'Mailing Address' in label:
                        data['mailing_address'] = self.parse_address(value_elem)
                    
                    # Trade Names
                    elif 'Other Trade Names' in label and 'Prior' not in label:
                        if value:
                            data['trade_names'] = [name.strip() for name in value.split(';') if name.strip()]
                    elif 'Prior Other Trade Names' in label:
                        if value:
                            data['prior_trade_names'] = [name.strip() for name in value.split(';') if name.strip()]
                    elif 'Prior Legal Names' in label:
                        if value:
                            data['prior_legal_names'] = [name.strip() for name in value.split(';') if name.strip()]
                    
                    # MLO Information
                    elif 'Sponsored MLOs' in label:
                        data['mlo_info'].type = 'sponsored'
                        try:
                            data['mlo_info'].count = int(value) if value else 0
                        except ValueError:
                            pass
                    elif 'Registered MLOs' in label:
                        data['mlo_info'].type = 'registered'
                        try:
                            data['mlo_info'].count = int(value) if value else 0
                        except ValueError:
                            pass
                    
                    # Business Information
                    elif 'Business Structure' in label:
                        data['business_info'].structure = value
                    elif 'Formed in' in label:
                        data['business_info'].formed_in = value
                    elif 'Date Formed' in label:
                        data['business_info'].date_formed = value
                    elif 'Fiscal Year End' in label:
                        data['business_info'].fiscal_year_end = value
                    elif 'Stock Symbol' in label:
                        data['business_info'].stock_symbol = value
                    
                    # Regulatory Actions
                    elif 'Regulatory Actions' in label:
                        data['regulatory_actions'] = value
            
            # Process nested contact info tables (table.dataDetail within td.divider)
            divider_cells = table.find_all('td', class_='divider')
            for cell in divider_cells:
                detail_tables = cell.find_all('table', class_='dataDetail')
                for detail_table in detail_tables:
                    detail_rows = detail_table.find_all('tr')
                    for detail_row in detail_rows:
                        detail_cells = detail_row.find_all('td')
                        if len(detail_cells) >= 2:
                            detail_label = self.clean_text(detail_cells[0].get_text())
                            detail_value = self.clean_text(detail_cells[1].get_text())
                            
                            # Contact Information from nested tables
                            if detail_label == 'Phone:' or detail_label == 'Phone':
                                data['contact_info'].phone = detail_value if detail_value != 'N/A' else None
                            elif 'Toll-Free' in detail_label:
                                data['contact_info'].toll_free = detail_value if detail_value != 'N/A' else None
                            elif detail_label == 'Fax:' or detail_label == 'Fax':
                                data['contact_info'].fax = detail_value if detail_value != 'N/A' else None
                            elif detail_label == 'Email:' or detail_label == 'Email':
                                data['contact_info'].email = detail_value if detail_value != 'N/A' else None
                            elif detail_label == 'Website:' or detail_label == 'Website':
                                data['contact_info'].website = detail_value if detail_value != 'N/A' else None
        
        return data
    
    def extract_federal_registration(self, soup: BeautifulSoup) -> FederalRegistration:
        """Extract federal registration information for banks/credit unions"""
        federal_section = soup.find('h1', string='Federal Registration')
        if not federal_section:
            return None
        
        # Find the table following the Federal Registration header
        table = federal_section.find_parent().find_next('table', class_='data')
        if not table:
            return None
        
        registration = FederalRegistration()
        
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                # Look for regulator link and status
                regulator_elem = cells[0].find('a')
                if regulator_elem:
                    registration.regulator = self.clean_text(regulator_elem.get_text())
                    registration.regulator_url = regulator_elem.get('href')
                
                registration.status = self.clean_text(cells[1].get_text())
        
        return registration if registration.regulator else None
    
    def extract_resident_agent(self, license_details_elem) -> ResidentAgent:
        """Extract resident/registered agent information"""
        agent_section = license_details_elem.find('div', class_='residentAgent')
        if not agent_section:
            return None
        
        agent = ResidentAgent()
        
        # Find the agent data table within the agent section
        agent_tables = agent_section.find_all('table', class_='popupData')
        for agent_table in agent_tables:
            rows = agent_table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    label_elem = cells[0]
                    value_elem = cells[1]
                    
                    # Check if this is a label cell (contains "label" class or ends with colon)
                    if label_elem.get('class') and 'label' in label_elem.get('class'):
                        label = self.clean_text(label_elem.get_text())
                        value = self.clean_text(value_elem.get_text())
                    else:
                        # Look for label text that ends with colon
                        label_text = label_elem.get_text().strip()
                        if label_text.endswith(':'):
                            label = label_text
                            value = self.clean_text(value_elem.get_text())
                        else:
                            continue
                    
                    if not label or not value or value.lower() in ['not provided', 'none']:
                        continue
                    
                    # Map label to agent fields
                    if 'Company' in label:
                        agent.company = value
                    elif 'Name' in label:
                        agent.name = value
                    elif 'Title' in label:
                        agent.title = value
                    elif 'Address' in label:
                        # Handle address with line breaks
                        address_lines = []
                        for br in value_elem.find_all('br'):
                            br.replace_with('\n')
                        address_text = value_elem.get_text()
                        agent.address = address_text.replace('\n', '; ').strip()
                    elif 'Phone' in label:
                        agent.phone = value
                    elif 'Fax' in label:
                        agent.fax = value
        
        # Return agent only if we found substantial information
        return agent if any([agent.company, agent.name, agent.title]) else None
    
    def extract_licenses(self, soup: BeautifulSoup) -> List[LicenseDetails]:
        """Extract all license/registration information"""
        licenses = []
        
        # Find the State Licenses/Registrations section - handle whitespace in h1 text
        licenses_header = None
        for h1 in soup.find_all('h1'):
            if 'State Licenses' in h1.get_text():
                licenses_header = h1
                break
        
        if not licenses_header:
            return licenses
        
        # Find the main license table
        license_table = licenses_header.find_parent().find_next('table', class_='data')
        if not license_table:
            return licenses
        
        # Process license rows
        license_rows = license_table.find_all('tr', class_='viewLicense')
        
        for row in license_rows:
            license = LicenseDetails()
            
            # Check if license is inactive
            license.active = 'inactive' not in row.get('class', [])
            
            cells = row.find_all('td')
            if len(cells) >= 4:
                # Regulator
                regulator_elem = cells[0].find('a')
                if regulator_elem:
                    license.regulator = self.clean_text(regulator_elem.get_text())
                
                # License Type
                license.license_type = self.clean_text(cells[1].get_text())
                
                # Authorized to Conduct Business
                authorized_text = self.clean_text(cells[2].get_text())
                license.authorized_to_conduct_business = authorized_text and authorized_text.lower() == 'yes'
                
                # Extract license ID from the details link
                details_link = cells[-1].find('a')
                if details_link:
                    link_id = details_link.get('id', '')
                    match = re.search(r'viewDetails_(\d+)', link_id)
                    if match:
                        license.license_id = match.group(1)
            
            # Find corresponding license details
            if license.license_id:
                details_row = soup.find('tr', id=f'licenseDetails_{license.license_id}')
                if details_row:
                    self._extract_license_details(details_row, license)
            
            licenses.append(license)
        
        return licenses
    
    def _extract_license_details(self, details_row, license: LicenseDetails):
        """Extract detailed license information from details row"""
        # Find sub-data tables
        sub_tables = details_row.find_all('table', class_='subData')
        
        for table in sub_tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                
                # License number extraction - look for span with "Lic/Reg #:" label
                lic_spans = row.find_all('span', class_='label')
                for span in lic_spans:
                    span_text = span.get_text()
                    if 'Lic' in span_text and '#' in span_text:
                        # Get the next text content after the span
                        next_element = span.next_sibling
                        while next_element:
                            if hasattr(next_element, 'get_text'):
                                license_num = self.clean_text(next_element.get_text())
                                if license_num and license_num not in [':', '']:
                                    license.license_number = license_num
                                    break
                            elif isinstance(next_element, str):
                                license_num = self.clean_text(next_element)
                                if license_num and license_num not in [':', '']:
                                    license.license_number = license_num
                                    break
                            next_element = next_element.next_sibling
                
                # Also try the original text-based extraction for other fields
                if len(cells) >= 1:
                    text = row.get_text()
                    
                    # Original Issue Date
                    if 'Original Issue Date:' in text:
                        match = re.search(r'Original Issue Date[^:]*:\s*([^\s]+)', text)
                        if match:
                            license.original_issue_date = match.group(1).strip()
                    
                    # Status and Status Date
                    if 'Status:' in text and 'Status Date:' in text:
                        status_match = re.search(r'Status[^:]*:\s*([^S]+?)Status Date:', text)
                        if status_match:
                            license.status = status_match.group(1).strip()
                        
                        date_match = re.search(r'Status Date:\s*([^\s]+)', text)
                        if date_match:
                            license.status_date = date_match.group(1).strip()
                    
                    # Renewed Through
                    if 'Renewed Through:' in text:
                        match = re.search(r'Renewed Through[^:]*:\s*([^\s]+)', text)
                        if match:
                            license.renewed_through = match.group(1).strip()
                    
                    # State Trade Names
                    if 'Other Trade Names used in' in text:
                        match = re.search(r'Other Trade Names used in [^:]+:\s*(.+)', text)
                        if match:
                            trade_names = match.group(1).strip()
                            if trade_names.lower() != 'none':
                                license.state_trade_names = trade_names
        
        # Extract resident agent information
        license.resident_agent = self.extract_resident_agent(details_row)
    
    def validate_and_flag_quality_issues(self, company_data: CompanyData) -> List[str]:
        """Validate extracted data and flag quality issues"""
        flags = []
        
        # Required field checks
        if not company_data.nmls_id:
            flags.append("missing_nmls_id")
        
        if not company_data.company_name:
            flags.append("missing_company_name")
        
        # Contact information validation
        if company_data.contact_info:
            if company_data.contact_info.email and '@' not in company_data.contact_info.email:
                flags.append("invalid_email_format")
        
        # Business logic checks
        if company_data.mlo_info and company_data.mlo_info.type:
            if company_data.federal_registration and company_data.mlo_info.type != 'registered':
                flags.append("bank_should_have_registered_mlos")
            elif not company_data.federal_registration and company_data.mlo_info.type != 'sponsored':
                flags.append("non_bank_should_have_sponsored_mlos")
        
        # License validation
        if company_data.licenses:
            for license_info in company_data.licenses:
                if license_info.license_type and license_info.license_type not in self.known_license_types:
                    flags.append(f"unknown_license_type_{license_info.license_type}")
        
        # Business structure validation
        if (company_data.business_info and 
            company_data.business_info.structure and 
            company_data.business_info.structure not in self.known_business_structures):
            flags.append(f"unknown_business_structure_{company_data.business_info.structure}")
        
        return flags
    
    def extract_from_file(self, file_path: str) -> CompanyData:
        """Extract data from a single HTML file"""
        self.stats["processed"] += 1
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Initialize company data
            company_data = CompanyData()
            company_data.file_path = file_path
            
            # Extract metadata
            metadata = self.extract_metadata(html_content)
            company_data.nmls_id = metadata.get('nmls_id')
            company_data.url = metadata.get('url')
            company_data.timestamp = metadata.get('timestamp')
            company_data.zip_code = metadata.get('zip_code')
            
            # Extract company name
            company_data.company_name = self.extract_company_name(soup)
            
            # Extract basic information
            basic_info = self.extract_basic_info(soup)
            
            # Populate company data from basic info
            if not company_data.nmls_id:
                company_data.nmls_id = basic_info['nmls_id']
            
            company_data.contact_info = basic_info['contact_info']
            company_data.street_address = basic_info['street_address']
            company_data.mailing_address = basic_info['mailing_address']
            company_data.trade_names = basic_info['trade_names']
            company_data.prior_trade_names = basic_info['prior_trade_names']
            company_data.prior_legal_names = basic_info['prior_legal_names']
            company_data.mlo_info = basic_info['mlo_info']
            company_data.business_info = basic_info['business_info']
            company_data.regulatory_actions = basic_info['regulatory_actions']
            
            # Extract federal registration
            company_data.federal_registration = self.extract_federal_registration(soup)
            
            # Extract licenses
            company_data.licenses = self.extract_licenses(soup)
            
            # Validate and flag quality issues
            company_data.quality_flags = self.validate_and_flag_quality_issues(company_data)
            
            if company_data.quality_flags:
                self.stats["quality_issues"] += 1
            
            self.stats["successful"] += 1
            logger.info(f"Successfully processed {file_path}")
            
            return company_data
            
        except Exception as e:
            self.stats["errors"] += 1
            error_msg = f"Error processing {file_path}: {str(e)}"
            logger.error(error_msg)
            
            # Return partial data with error information
            company_data = CompanyData()
            company_data.file_path = file_path
            company_data.processing_errors = [error_msg]
            
            return company_data
    
    def extract_from_directory(self, directory_path: str, 
                             pattern: str = "*.html", 
                             max_files: Optional[int] = None) -> List[CompanyData]:
        """Extract data from all HTML files in a directory"""
        directory = Path(directory_path)
        html_files = list(directory.rglob(pattern))
        
        if max_files:
            html_files = html_files[:max_files]
        
        logger.info(f"Found {len(html_files)} HTML files to process")
        
        results = []
        for file_path in html_files:
            company_data = self.extract_from_file(str(file_path))
            results.append(company_data)
            
            # Log progress every 100 files
            if len(results) % 100 == 0:
                logger.info(f"Processed {len(results)}/{len(html_files)} files")
        
        self._log_final_stats()
        return results
    
    def _log_final_stats(self):
        """Log final processing statistics"""
        logger.info("=== Processing Complete ===")
        logger.info(f"Total processed: {self.stats['processed']}")
        logger.info(f"Successful: {self.stats['successful']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Quality issues: {self.stats['quality_issues']}")
        
        if self.stats['processed'] > 0:
            success_rate = (self.stats['successful'] / self.stats['processed']) * 100
            logger.info(f"Success rate: {success_rate:.2f}%")
    
    def save_to_json(self, data: List[CompanyData], output_path: str):
        """Save extracted data to JSON file"""
        json_data = [asdict(company) for company in data]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(data)} records to {output_path}")
    
    def save_to_csv(self, data: List[CompanyData], output_path: str):
        """Save extracted data to CSV file (flattened structure)"""
        if not data:
            logger.warning("No data to save to CSV")
            return
        
        # Flatten the data structure for CSV
        flattened_data = []
        
        for company in data:
            row = {
                'nmls_id': company.nmls_id,
                'company_name': company.company_name,
                'url': company.url,
                'timestamp': company.timestamp,
                'zip_code': company.zip_code,
                'file_path': company.file_path,
                'extraction_timestamp': company.extraction_timestamp,
                
                # Contact info
                'phone': company.contact_info.phone if company.contact_info else None,
                'toll_free': company.contact_info.toll_free if company.contact_info else None,
                'fax': company.contact_info.fax if company.contact_info else None,
                'email': company.contact_info.email if company.contact_info else None,
                'website': company.contact_info.website if company.contact_info else None,
                
                # Addresses
                'street_address': company.street_address.full_address if company.street_address else None,
                'mailing_address': company.mailing_address.full_address if company.mailing_address else None,
                
                # Business info
                'business_structure': company.business_info.structure if company.business_info else None,
                'formed_in': company.business_info.formed_in if company.business_info else None,
                'date_formed': company.business_info.date_formed if company.business_info else None,
                'fiscal_year_end': company.business_info.fiscal_year_end if company.business_info else None,
                'stock_symbol': company.business_info.stock_symbol if company.business_info else None,
                
                # MLO info
                'mlo_type': company.mlo_info.type if company.mlo_info else None,
                'mlo_count': company.mlo_info.count if company.mlo_info else None,
                
                # Federal registration
                'federal_regulator': company.federal_registration.regulator if company.federal_registration else None,
                'federal_status': company.federal_registration.status if company.federal_registration else None,
                
                # Trade names
                'trade_names': '; '.join(company.trade_names) if company.trade_names else None,
                'prior_trade_names': '; '.join(company.prior_trade_names) if company.prior_trade_names else None,
                'prior_legal_names': '; '.join(company.prior_legal_names) if company.prior_legal_names else None,
                
                # License summary
                'total_licenses': len(company.licenses),
                'active_licenses': len([l for l in company.licenses if l.active]),
                'license_types': '; '.join(set(l.license_type for l in company.licenses if l.license_type)),
                
                # Quality and errors
                'regulatory_actions': company.regulatory_actions,
                'quality_flags': '; '.join(company.quality_flags) if company.quality_flags else None,
                'processing_errors': '; '.join(company.processing_errors) if company.processing_errors else None,
            }
            
            flattened_data.append(row)
        
        df = pd.DataFrame(flattened_data)
        df.to_csv(output_path, index=False, encoding='utf-8')
        
        logger.info(f"Saved {len(flattened_data)} records to {output_path}")

    def save_to_markdown(self, data: List[CompanyData], output_dir: str) -> int:
        """Save extracted data to markdown files in the specified directory
        
        Args:
            data: List of CompanyData objects to save
            output_dir: Directory path where markdown files will be saved
            
        Returns:
            int: Number of markdown files created
        """
        if not data:
            logger.warning("No data to save to markdown")
            return 0
        
        # Ensure output directory exists
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        files_created = 0
        
        for company in data:
            if not company.nmls_id:
                continue
                
            # Create filename from NMLS ID
            filename = f"COMPANY_{company.nmls_id}.md"
            file_path = output_path / filename
            
            try:
                # Generate markdown content
                markdown_content = self._generate_company_markdown(company)
                
                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                
                files_created += 1
                
            except Exception as e:
                logger.error(f"Error creating markdown for {company.nmls_id}: {str(e)}")
        
        logger.info(f"Created {files_created} markdown files in {output_dir}")
        return files_created
    
    def _generate_company_markdown(self, company: CompanyData) -> str:
        """Generate markdown content for a single company"""
        lines = []
        
        # Header
        lines.append(f"# {company.company_name or 'Unknown Company'}")
        lines.append("")
        lines.append(f"**NMLS ID:** {company.nmls_id}")
        lines.append("")
        
        # Metadata
        if company.url or company.timestamp:
            lines.append("## Metadata")
            if company.url:
                lines.append(f"- **Source URL:** {company.url}")
            if company.timestamp:
                lines.append(f"- **Data Timestamp:** {company.timestamp}")
            if company.file_path:
                lines.append(f"- **Source File:** {company.file_path}")
            lines.append(f"- **Extraction Time:** {company.extraction_timestamp}")
            lines.append("")
        
        # Contact Information
        if company.contact_info and any([company.contact_info.phone, company.contact_info.email, company.contact_info.website]):
            lines.append("## Contact Information")
            if company.contact_info.phone:
                lines.append(f"- **Phone:** {company.contact_info.phone}")
            if company.contact_info.toll_free:
                lines.append(f"- **Toll Free:** {company.contact_info.toll_free}")
            if company.contact_info.fax:
                lines.append(f"- **Fax:** {company.contact_info.fax}")
            if company.contact_info.email:
                lines.append(f"- **Email:** {company.contact_info.email}")
            if company.contact_info.website:
                lines.append(f"- **Website:** {company.contact_info.website}")
            lines.append("")
        
        # Addresses
        if company.street_address or company.mailing_address:
            lines.append("## Addresses")
            if company.street_address:
                lines.append("### Street Address")
                lines.append(f"{company.street_address.full_address}")
                lines.append("")
            if company.mailing_address and company.mailing_address != company.street_address:
                lines.append("### Mailing Address")
                lines.append(f"{company.mailing_address.full_address}")
                lines.append("")
        
        # Business Information
        if company.business_info and any([company.business_info.structure, company.business_info.formed_in, 
                                        company.business_info.date_formed, company.business_info.fiscal_year_end]):
            lines.append("## Business Information")
            if company.business_info.structure:
                lines.append(f"- **Business Structure:** {company.business_info.structure}")
            if company.business_info.formed_in:
                lines.append(f"- **Formed In:** {company.business_info.formed_in}")
            if company.business_info.date_formed:
                lines.append(f"- **Date Formed:** {company.business_info.date_formed}")
            if company.business_info.fiscal_year_end:
                lines.append(f"- **Fiscal Year End:** {company.business_info.fiscal_year_end}")
            if company.business_info.stock_symbol:
                lines.append(f"- **Stock Symbol:** {company.business_info.stock_symbol}")
            lines.append("")
        
        # Trade Names
        if company.trade_names or company.prior_trade_names or company.prior_legal_names:
            lines.append("## Trade Names & History")
            if company.trade_names:
                lines.append("### Current Trade Names")
                for name in company.trade_names:
                    lines.append(f"- {name}")
                lines.append("")
            if company.prior_trade_names:
                lines.append("### Prior Trade Names")
                for name in company.prior_trade_names:
                    lines.append(f"- {name}")
                lines.append("")
            if company.prior_legal_names:
                lines.append("### Prior Legal Names")
                for name in company.prior_legal_names:
                    lines.append(f"- {name}")
                lines.append("")
        
        # MLO Information
        if company.mlo_info and (company.mlo_info.type or company.mlo_info.count):
            lines.append("## MLO Information")
            if company.mlo_info.type:
                lines.append(f"- **Type:** {company.mlo_info.type}")
            if company.mlo_info.count:
                lines.append(f"- **Count:** {company.mlo_info.count}")
            lines.append("")
        
        # Federal Registration
        if company.federal_registration and company.federal_registration.regulator:
            lines.append("## Federal Registration")
            lines.append(f"- **Regulator:** {company.federal_registration.regulator}")
            if company.federal_registration.status:
                lines.append(f"- **Status:** {company.federal_registration.status}")
            lines.append("")
        
        # Licenses
        if company.licenses:
            lines.append("## Licenses & Registrations")
            lines.append("")
            
            for i, license_info in enumerate(company.licenses, 1):
                lines.append(f"### License {i}")
                if license_info.license_type:
                    lines.append(f"- **Type:** {license_info.license_type}")
                if license_info.license_number:
                    lines.append(f"- **Number:** {license_info.license_number}")
                if license_info.regulator:
                    lines.append(f"- **Regulator:** {license_info.regulator}")
                if license_info.status:
                    lines.append(f"- **Status:** {license_info.status}")
                if license_info.original_issue_date:
                    lines.append(f"- **Issue Date:** {license_info.original_issue_date}")
                if license_info.renewed_through:
                    lines.append(f"- **Renewed Through:** {license_info.renewed_through}")
                if license_info.authorized_to_conduct_business is not None:
                    lines.append(f"- **Authorized to Conduct Business:** {'Yes' if license_info.authorized_to_conduct_business else 'No'}")
                lines.append("")
        
        # Quality & Error Information
        if company.quality_flags or company.processing_errors:
            lines.append("## Quality & Processing Notes")
            if company.quality_flags:
                lines.append("### Quality Flags")
                for flag in company.quality_flags:
                    lines.append(f"- {flag}")
                lines.append("")
            if company.processing_errors:
                lines.append("### Processing Errors")
                for error in company.processing_errors:
                    lines.append(f"- {error}")
                lines.append("")
        
        return '\n'.join(lines)

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Extract data from NMLS HTML files")
    parser.add_argument("input_path", help="Input directory or file path")
    parser.add_argument("-o", "--output", default="nmls_extracted_data", 
                       help="Output file prefix (default: nmls_extracted_data)")
    parser.add_argument("-f", "--format", choices=["json", "csv", "both"], 
                       default="both", help="Output format (default: both)")
    parser.add_argument("-m", "--max-files", type=int, 
                       help="Maximum number of files to process")
    parser.add_argument("-p", "--pattern", default="*.html", 
                       help="File pattern to match (default: *.html)")
    parser.add_argument("-v", "--verbose", action="store_true", 
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize extractor
    extractor = NMLSHTMLExtractor()
    
    # Process files
    input_path = Path(args.input_path)
    
    if input_path.is_file():
        # Single file processing
        logger.info(f"Processing single file: {input_path}")
        company_data = extractor.extract_from_file(str(input_path))
        results = [company_data]
    elif input_path.is_dir():
        # Directory processing
        logger.info(f"Processing directory: {input_path}")
        results = extractor.extract_from_directory(
            str(input_path), 
            args.pattern, 
            args.max_files
        )
    else:
        logger.error(f"Input path does not exist: {input_path}")
        return 1
    
    # Save results
    if args.format in ["json", "both"]:
        json_output = f"{args.output}.json"
        extractor.save_to_json(results, json_output)
    
    if args.format in ["csv", "both"]:
        csv_output = f"{args.output}.csv"
        extractor.save_to_csv(results, csv_output)
    
    # Save detailed license information separately
    if results:
        license_details = []
        for company in results:
            for license_info in company.licenses:
                license_row = asdict(license_info)
                license_row['company_nmls_id'] = company.nmls_id
                license_row['company_name'] = company.company_name
                license_details.append(license_row)
        
        if license_details:
            license_df = pd.DataFrame(license_details)
            license_output = f"{args.output}_licenses.csv"
            license_df.to_csv(license_output, index=False, encoding='utf-8')
            logger.info(f"Saved {len(license_details)} license records to {license_output}")
    
    logger.info("Extraction complete!")
    return 0

if __name__ == "__main__":
    exit(main()) 