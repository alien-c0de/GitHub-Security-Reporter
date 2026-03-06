"""
Base collector class for all security data collectors
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime
import logging

from src.utils.github_client import GitHubClient
from config.settings import settings

logger = logging.getLogger(__name__)

class BaseCollector(ABC):
    """Abstract base class for all collectors"""
    
    def __init__(self, github_client: GitHubClient):
        self.client = github_client
        self.org = github_client.org
        self.settings = settings
        self.collection_timestamp = None
    
    @abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        """
        Collect security data from GitHub
        
        Returns:
            List of dictionaries containing security data
        """
        pass
    
    @abstractmethod
    def get_collector_name(self) -> str:
        """Return the name of this collector"""
        pass
    
    def _get_repositories(self, skip_archived: bool = True):
        """
        Get all repositories in the organization
        
        Args:
            skip_archived: Skip archived repositories
        """
        try:
            repos = self.org.get_repos()
            if skip_archived:
                return [repo for repo in repos if not repo.archived]
            return repos
        except Exception as e:
            logger.error(f"[bright_red][❌] Error fetching repositories: {e}[/bright_red]")
            return []
    
    def _mark_collection_time(self):
        """Mark the current collection timestamp"""
        self.collection_timestamp = datetime.now()
    
    def _create_base_record(self, repo_name: str) -> Dict[str, Any]:
        """
        Create a base record with common fields
        
        Args:
            repo_name: Repository name
            
        Returns:
            Dictionary with base fields
        """
        return {
            'collected_at': self.collection_timestamp.isoformat() if self.collection_timestamp else datetime.now().isoformat(),
            'collector': self.get_collector_name(),
            'repository': repo_name,
            'organization': self.settings.github_org
        }
    
    def collect_with_retry(self, max_retries: int = None) -> List[Dict[str, Any]]:
        """
        Collect data with retry logic
        
        Args:
            max_retries: Maximum number of retry attempts
            
        Returns:
            List of collected data
        """
        if max_retries is None:
            max_retries = self.settings.github_retry_attempts
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[bright_yellow][+] Collecting data with {self.get_collector_name()} (attempt {attempt + 1}/{max_retries})[/bright_yellow]")
                return self.collect()
            except Exception as e:
                logger.warning(f"Collection attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"[bright_red]❌ All retry attempts failed for {self.get_collector_name()}[/bright_red]")
                    raise
        
        return []