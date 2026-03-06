"""Organization information collector"""
from typing import Dict, Any
import logging
from src.collectors.base_collector import BaseCollector
from src.utils.github_client import GitHubClient

logger = logging.getLogger(__name__)

class OrganizationCollector(BaseCollector):
    """Collector for organization-level information"""
    
    def __init__(self, github_client: GitHubClient):
        super().__init__(github_client)
    
    def get_collector_name(self) -> str:
        return "OrganizationCollector"
    
    def collect(self) -> Dict[str, Any]:
        """Collect organization information"""
        self._mark_collection_time()
        
        org_info = {
            'login': self.org.login,
            'name': self.org.name if hasattr(self.org, 'name') and self.org.name else self.org.login,
            'email': self.org.email if hasattr(self.org, 'email') and self.org.email else 'N/A',
            'owners': [],
            'admins': []
        }
        
        try:
            # Get organization members with admin role
            members = self.org.get_members(role='admin')
            
            admins = []
            for member in members:
                try:
                    user = self.client.client.get_user(member.login)
                    admin_info = {
                        'login': member.login,
                        'name': user.name if user.name else member.login,
                        'email': user.email if user.email else 'Not public',
                        'role': 'Admin'
                    }
                    admins.append(admin_info)
                    
                    if len(admins) >= 10:
                        break
                except Exception as e:
                    logger.debug(f"Could not fetch details for {member.login}: {e}")
            
            org_info['admins'] = admins
            org_info['owners'] = admins[:3]  # Top 3 as owners
            
        except Exception as e:
            logger.warning(f"Could not fetch organization members: {e}")
        
        return org_info