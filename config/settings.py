"""
Configuration management for GitHub Security Reporter
"""
import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, List

# Load environment variables
load_dotenv()

class Settings:
    """Application settings manager"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.parent
        self.config_file = self.base_dir / 'config' / 'config.yaml'
        self._config = self._load_yaml_config()
    
    def _load_yaml_config(self) -> Dict[str, Any]:
        """Load YAML configuration file"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        return {}
    
    # GitHub Settings
    @property
    def github_enterprise_url(self) -> str:
        url = os.getenv('GITHUB_ENTERPRISE_URL', 'https://github.com')
        return url.strip() if url else 'https://github.com'  # Strip whitespace
    
    # GitHub Settings
    @property
    def github_enterprise_slug(self) -> str:
        url = os.getenv('GITHUB_ENTERPRISE_SLUG', 'https://github.com')
        return url.strip() if url else 'https://github.com'  # Strip whitespace

    @property
    def github_token(self) -> str:
        token = os.getenv('GITHUB_TOKEN', '')
        return token.strip() if token else ''  # Strip whitespace

    @property
    def github_org(self) -> str:
        org = os.getenv('GITHUB_ORG', '')
        return org.strip() if org else ''  # Strip whitespace
    
    @property
    def report_title(self) -> str:
        val = os.getenv('REPORT_TITLE', 'GitHub Advanced Security Reporter')
        return val.strip() if val else 'GitHub Advanced Security Reporter'

    @property
    def company_name(self) -> str:
        val = os.getenv('COMPANY_NAME', '')
        return val.strip() if val else ''

    @property
    def developed_by(self) -> str:
        val = os.getenv('DEVELOPED_BY', 'Security Engineering Team')
        return val.strip() if val else 'Security Engineering Team'

    @property
    def tool_version(self) -> str:
        val = os.getenv('TOOL_VERSION', '1.0.0')
        return val.strip() if val else '1.0.0'

    @property
    def copyright_year(self) -> str:
        val = os.getenv('COPYRIGHT_YEAR', '')
        return val.strip() if val else ''

    @property
    def company_website(self) -> str:
        val = os.getenv('COMPANY_WEBSITE', '')
        return val.strip() if val else ''

    @property
    def tool_github_repo(self) -> str:
        val = os.getenv('TOOL_GITHUB_REPO', '')
        return val.strip() if val else ''

    @property
    def support_email(self) -> str:
        val = os.getenv('SUPPORT_EMAIL', '')
        return val.strip() if val else ''

    @property
    def github_rate_limit_buffer(self) -> int:
        return self._config.get('github', {}).get('rate_limit_buffer', 100)
    
    @property
    def github_retry_attempts(self) -> int:
        return self._config.get('github', {}).get('retry_attempts', 3)
    
    # Email Settings
    @property
    def smtp_server(self) -> str:
        return os.getenv('SMTP_SERVER', '')
    
    @property
    def smtp_port(self) -> int:
        return int(os.getenv('SMTP_PORT', '587'))
    
    @property
    def smtp_username(self) -> str:
        return os.getenv('SMTP_USERNAME', '')
    
    @property
    def smtp_password(self) -> str:
        return os.getenv('SMTP_PASSWORD', '')
    
    @property
    def email_from(self) -> str:
        return os.getenv('EMAIL_FROM', '')
    
    @property
    def email_to(self) -> List[str]:
        email_str = os.getenv('EMAIL_TO', '')
        return [e.strip() for e in email_str.split(',') if e.strip()]
    
    # Report Settings
    @property
    def report_output_dir(self) -> Path:
        path = Path(os.getenv('REPORT_OUTPUT_DIR', 'data/reports'))
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def history_data_dir(self) -> Path:
        path = Path(os.getenv('HISTORY_DATA_DIR', 'data/history'))
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def cache_dir(self) -> Path:
        path = Path(os.getenv('CACHE_DIR', 'data/cache'))
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Feature Flags
    @property
    def enable_dependabot(self) -> bool:
        return os.getenv('ENABLE_DEPENDABOT', 'true').lower() == 'true'
    
    @property
    def enable_code_scanning(self) -> bool:
        return os.getenv('ENABLE_CODE_SCANNING', 'true').lower() == 'true'
    
    @property
    def enable_secret_scanning(self) -> bool:
        return os.getenv('ENABLE_SECRET_SCANNING', 'true').lower() == 'true'
    
    @property
    def enable_supply_chain(self) -> bool:
        return os.getenv('ENABLE_SUPPLY_CHAIN', 'true').lower() == 'true'
    
    # Security Settings
    @property
    def severity_levels(self) -> List[str]:
        return self._config.get('security', {}).get('severity_levels', 
                                                     ['critical', 'high', 'medium', 'low'])
    
    @property
    def sla_days(self) -> Dict[str, int]:
        return self._config.get('security', {}).get('sla_days', {
            'critical': 2,
            'high': 7,
            'medium': 30,
            'low': 90
        })
    
    # Thresholds
    @property
    def critical_alert_threshold(self) -> int:
        return int(os.getenv('CRITICAL_ALERT_THRESHOLD', '1'))
    
    @property
    def high_alert_threshold(self) -> int:
        return int(os.getenv('HIGH_ALERT_THRESHOLD', '5'))
    
    # Logging
    @property
    def log_level(self) -> str:
        return os.getenv('LOG_LEVEL', 'INFO')
    
    @property
    def log_file(self) -> Path:
        return Path(os.getenv('LOG_FILE', 'data/app.log'))
    
    # Report Configuration
    @property
    def report_sections(self) -> List[str]:
        return self._config.get('reports', {}).get('sections', [
            'executive_summary',
            'trend_analysis',
            'top_risks',
            'remediation_progress',
            'repository_health',
            'recommendations'
        ])
    
    @property
    def weekly_report_enabled(self) -> bool:
        return self._config.get('reports', {}).get('weekly', {}).get('enabled', True)
    
    @property
    def weekly_report_recipients(self) -> List[str]:
        return self._config.get('reports', {}).get('weekly', {}).get('recipients', [])
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation key"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

# Global settings instance
settings = Settings()