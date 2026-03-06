"""
GitHub API client wrapper
"""
import time
import logging
from typing import Optional
from github import Github, GithubException, RateLimitExceededException
from config.settings import settings

logger = logging.getLogger(__name__)

class GitHubClient:
    """
    Wrapper around PyGithub with rate limiting and retry logic
    """
    
    def __init__(self, token: Optional[str] = None, org_name: Optional[str] = None):
        """
        Initialize GitHub client
        
        Args:
            token: GitHub personal access token (defaults to settings)
            org_name: Organization name (defaults to settings)
        """
        self.token = token or settings.github_token
        self.org_name = org_name or settings.github_org
        
        if not self.token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable.")
        
        if not self.org_name:
            raise ValueError("GitHub organization is required. Set GITHUB_ORG environment variable.")
        
        # Initialize GitHub client
        base_url = settings.github_enterprise_url
        if base_url and base_url != 'https://github.com':
            # GitHub Enterprise Server
            self.client = Github(base_url=f"{base_url}", login_or_token=self.token)
        else:
            # GitHub.com
            self.client = Github(self.token)
        
        # Get organization
        try:
            self.org = self.client.get_organization(self.org_name)
            logger.info(f"[bright_green][✓] Successfully connected to GitHub organization: {self.org_name}[/bright_green]")
        except GithubException as e:
            logger.error(f"[bright_red][✗] Failed to connect to organization {self.org_name}: {e}[/bright_red]")
            raise
        
        # Log rate limit info
        self._log_rate_limit()
    
    def _log_rate_limit(self):
        """Log current rate limit status"""
        try:
            rate_limit = self.client.get_rate_limit()
            
            # Handle different rate limit object structures
            if hasattr(rate_limit, 'core'):
                core = rate_limit.core
                logger.info(f"[bright_yellow][+] GitHub API Rate Limit - Remaining: {core.remaining}/{core.limit}, "
                        f"Resets at: {core.reset}[/bright_yellow]")
            elif hasattr(rate_limit, 'rate'):
                # Alternative structure
                core = rate_limit.rate
                logger.info(f"[bright_yellow][+] GitHub API Rate Limit - Remaining: {core.remaining}/{core.limit}, "
                        f"Resets at: {core.reset}[/bright_yellow]")
            else:
                logger.info("Rate limit information available")
        except Exception as e:
            logger.debug(f"Could not fetch rate limit: {e}")
    
    def check_rate_limit(self, min_remaining: Optional[int] = None):
        """
        Check rate limit and wait if necessary
        
        Args:
            min_remaining: Minimum remaining requests before waiting
        """
        if min_remaining is None:
            min_remaining = settings.github_rate_limit_buffer
        
        try:
            rate_limit = self.client.get_rate_limit()
            
            # Handle different rate limit object structures
            if hasattr(rate_limit, 'core'):
                remaining = rate_limit.core.remaining
                reset_time = rate_limit.core.reset
            elif hasattr(rate_limit, 'rate'):
                remaining = rate_limit.rate.remaining
                reset_time = rate_limit.rate.reset
            else:
                logger.debug("Could not determine rate limit structure")
                return
            
            if remaining < min_remaining:
                wait_time = (reset_time - time.time()) + 10  # Add 10 second buffer
                
                if wait_time > 0:
                    logger.warning(f"Rate limit low ({remaining} remaining). "
                                f"Waiting {wait_time:.0f} seconds until reset...")
                    time.sleep(wait_time)
                    logger.info("Rate limit reset. Continuing...")
        except Exception as e:
            logger.debug(f"Could not check rate limit: {e}")
    
    def execute_with_retry(self, func, *args, max_retries: Optional[int] = None, **kwargs):
        """
        Execute a function with retry logic
        
        Args:
            func: Function to execute
            max_retries: Maximum retry attempts
            *args, **kwargs: Arguments to pass to function
            
        Returns:
            Function result
        """
        if max_retries is None:
            max_retries = settings.github_retry_attempts
        
        for attempt in range(max_retries):
            try:
                self.check_rate_limit()
                return func(*args, **kwargs)
            except RateLimitExceededException:
                logger.warning("Rate limit exceeded, waiting...")
                self.check_rate_limit(min_remaining=0)
            except GithubException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"GitHub API error (attempt {attempt + 1}/{max_retries}): {e}. "
                                 f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"[bright_red][❌] GitHub API error after {max_retries} attempts: {e}[/bright_red]")
                    raise
            except Exception as e:
                logger.error(f"[bright_red][❌] Unexpected error: {e}[/bright_red]")
                raise
        
        raise Exception(f"Failed after {max_retries} attempts")
    
    def get_organization(self):
        """Get the organization object"""
        return self.org
    
    def get_repositories(self):
        """Get all repositories in the organization"""
        return self.execute_with_retry(self.org.get_repos)
    
    def get_repository(self, repo_name: str):
        """
        Get a specific repository
        
        Args:
            repo_name: Repository name
            
        Returns:
            Repository object
        """
        return self.execute_with_retry(self.org.get_repo, repo_name)
    
    def close(self):
        """Close the GitHub client connection"""
        try:
            self.client.close()
            logger.info(f"[bright_green][✓] GitHub client connection closed[/bright_green]")
            logger.info("")

        except Exception as e:
            logger.warning(f"[bright_red][✗] Error closing GitHub client: {e}[bright_red]")