"""
Data validation utilities
"""
from typing import Any, Dict, List
import re

class DataValidator:
    """Utility class for data validation"""
    
    @staticmethod
    def validate_severity(severity: str) -> bool:
        """Validate severity level"""
        valid_severities = ['critical', 'high', 'medium', 'low', 'note']
        return severity.lower() in valid_severities
    
    @staticmethod
    def validate_state(state: str, valid_states: List[str]) -> bool:
        """Validate state value"""
        return state.lower() in [s.lower() for s in valid_states]
    
    @staticmethod
    def validate_cve(cve: str) -> bool:
        """Validate CVE ID format"""
        if cve == 'N/A':
            return True
        pattern = r'^CVE-\d{4}-\d{4,}$'
        return bool(re.match(pattern, cve))
    
    @staticmethod
    def validate_ghsa(ghsa: str) -> bool:
        """Validate GHSA ID format"""
        pattern = r'^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$'
        return bool(re.match(pattern, ghsa))
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL"""
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(pattern, url))
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename by removing invalid characters"""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        # Remove leading/trailing dots and spaces
        filename = filename.strip('. ')
        return filename