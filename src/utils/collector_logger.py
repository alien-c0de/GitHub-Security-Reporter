"""
Custom color tags for logging with terminal error display
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CollectorLogger:
    """Helper class for consistent and clean collector logging with error display"""
    
    def __init__(self, collector_name: str):
        self.collector_name = collector_name
        self.warnings = []
        self.errors = []
        self.skipped = []
        
    def log_start(self, total_repos: int):
        """Log collection start"""
        logger.info(f"[cyan][+] Collecting {self.collector_name} from {total_repos} repositories[/cyan]")
    
    def log_repo_error(self, repo_name: str, error: str, full_error: str = None):
        """
        Log repository error - shows in terminal and logs to file
        
        Args:
            repo_name: Repository name
            error: Short error message for terminal
            full_error: Full error details for log file
        """
        self.errors.append({
            'repo': repo_name,
            'error': error
        })
        
        # Terminal: Short, clear message
        terminal_msg = f"[red][✗] {repo_name}: {error}[/red]"
        logger.warning(terminal_msg)
        
        # File: Full detailed error
        if full_error:
            logger.debug(f"Error details for {repo_name}: {full_error}")
    
    def log_complete(self, total_collected: int):
        """Log collection completion with summary"""
        logger.info(f"[bright_green][✓] Total {self.collector_name} collected: {total_collected}[/bright_green]")
        
        # Show error count if any
        if self.errors:
            logger.info(f"[yellow]    {len(self.errors)} repositories had errors/warnings[/yellow]")

def parse_github_error(error_message: str, repo_name: str) -> Dict[str, Any]:
    """
    Parse GitHub API error and categorize it
    
    Args:
        error_message: Error message from GitHub API
        repo_name: Repository name
        
    Returns:
        Dictionary with error category and details
    """
    error_lower = str(error_message).lower()
    
    # Dependabot disabled
    if '403' in error_message and 'dependabot alerts are disabled' in error_lower:
        return {
            'type': 'disabled',
            'feature': 'Dependabot',
            'repo': repo_name,
            'short_message': 'Dependabot alerts are disabled for this repository',
            'full_message': error_message
        }
    
    # Archived repository
    if '403' in error_message and 'archived' in error_lower:
        return {
            'type': 'archived',
            'feature': 'All',
            'repo': repo_name,
            'short_message': 'Repository is archived',
            'full_message': error_message
        }
    
    # GHAS not enabled
    if '403' in error_message and 'advanced security must be enabled' in error_lower:
        return {
            'type': 'disabled',
            'feature': 'GitHub Advanced Security',
            'repo': repo_name,
            'short_message': 'Advanced Security must be enabled for this repository',
            'full_message': error_message
        }
    
    # Code scanning - no analysis found
    if '404' in error_message and 'no analysis found' in error_lower:
        return {
            'type': 'no_analysis',
            'feature': 'Code Scanning',
            'repo': repo_name,
            'short_message': 'No analysis found',
            'full_message': error_message
        }
    
    # No default branch
    if '404' in error_message and 'no default branch' in error_lower:
        return {
            'type': 'no_branch',
            'feature': 'Code Scanning',
            'repo': repo_name,
            'short_message': 'No default branch found',
            'full_message': error_message
        }
    
    # Secret scanning not available
    if '404' in error_message and 'secret' in error_lower:
        return {
            'type': 'not_found',
            'feature': 'Secret Scanning',
            'repo': repo_name,
            'short_message': 'Secret scanning not available for this repository',
            'full_message': error_message
        }
    
    # Generic 403 - no access
    if '403' in error_message:
        return {
            'type': 'no_access',
            'feature': 'Unknown',
            'repo': repo_name,
            'short_message': 'Permission denied (403 Forbidden)',
            'full_message': error_message
        }
    
    # Generic 404
    if '404' in error_message:
        return {
            'type': 'not_found',
            'feature': 'Unknown',
            'repo': repo_name,
            'short_message': 'Resource not found (404)',
            'full_message': error_message
        }
    
    # Unknown error
    return {
        'type': 'error',
        'feature': 'Unknown',
        'repo': repo_name,
        'short_message': str(error_message)[:100],
        'full_message': error_message
    }