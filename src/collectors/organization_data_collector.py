"""
Organization Data Collector - Fetches all organizations and their repositories
"""
from typing import List, Dict, Any
import logging
from datetime import datetime

from src.collectors.base_collector import BaseCollector
from src.utils.github_client import GitHubClient

logger = logging.getLogger(__name__)

class OrganizationDataCollector(BaseCollector):
    """Collector for organization and repository data across the enterprise"""
    
    def __init__(self, github_client: GitHubClient):
        super().__init__(github_client)
    
    def get_collector_name(self) -> str:
        return "OrganizationDataCollector"
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect all organizations and their repositories
        
        Returns:
            Dictionary with organizations list and repository details
        """
        self._mark_collection_time()
        
        logger.info("[cyan][+] Collecting organization and repository data...[/cyan]")
        
        # Get current organization (we're already connected to one)
        org_data = self._collect_organization_data(self.org)
        
        # Structure: Single org for now, but designed for multiple orgs
        result = {
            'collected_at': self.collection_timestamp.isoformat(),
            'organizations': [org_data],
            'total_organizations': 1,
            'total_repositories': len(org_data['repositories'])
        }
        
        logger.info(f"[bright_green][✓] Collected data for {result['total_organizations']} organization(s) with {result['total_repositories']} repositories[/bright_green]")
        
        return result
    
    def _collect_organization_data(self, org) -> Dict[str, Any]:
        """Collect detailed data for a single organization"""
        
        logger.info(f"[cyan]  → Collecting data for organization: {org.login}[/cyan]")
        
        # Organization basic info
        org_info = {
            'organization_id': org.id,
            'organization_name': org.name if hasattr(org, 'name') and org.name else org.login,
            'organization_login': org.login,
            'description': org.description if hasattr(org, 'description') and org.description else 'N/A',
            'url': org.html_url if hasattr(org, 'html_url') else f'https://github.com/{org.login}',
            'created_at': org.created_at.isoformat() if hasattr(org, 'created_at') and org.created_at else None,
            'repositories': []
        }
        
        # Get all repositories
        try:
            repos = org.get_repos()
            repo_count = 0
            
            for repo in repos:
                try:
                    repo_data = self._collect_repository_data(repo, org_info['organization_login'])
                    org_info['repositories'].append(repo_data)
                    repo_count += 1
                    
                    if repo_count % 5 == 0:
                        logger.info(f"[dim]    Processed {repo_count} repositories...[/dim]")
                except Exception as e:
                    logger.warning(f"[yellow]    Warning: Could not collect data for repository {repo.name}: {e}[/yellow]")
                    continue
            
            logger.info(f"[bright_green]  ✓ Collected {len(org_info['repositories'])} repositories from {org.login}[/bright_green]")
            
        except Exception as e:
            logger.error(f"[red]Error collecting repositories for {org.login}: {e}[/red]")
        
        # Add summary statistics
        org_info['repository_count'] = len(org_info['repositories'])
        org_info['total_size_kb'] = sum(r['size_kb'] for r in org_info['repositories'])
        org_info['total_stars'] = sum(r['stars'] for r in org_info['repositories'])
        org_info['total_forks'] = sum(r['forks'] for r in org_info['repositories'])
        
        # Count by visibility
        org_info['public_repos'] = sum(1 for r in org_info['repositories'] if r['visibility'] == 'public')
        org_info['private_repos'] = sum(1 for r in org_info['repositories'] if r['visibility'] == 'private')
        org_info['internal_repos'] = sum(1 for r in org_info['repositories'] if r['visibility'] == 'internal')
        
        # Count archived and active
        org_info['archived_repos'] = sum(1 for r in org_info['repositories'] if r['archived'])
        org_info['active_repos'] = sum(1 for r in org_info['repositories'] if not r['archived'])
        
        # Count by language (top 5)
        language_counts = {}
        for repo in org_info['repositories']:
            lang = repo['primary_language']
            if lang and lang != 'None':
                language_counts[lang] = language_counts.get(lang, 0) + 1
        
        org_info['languages'] = dict(sorted(language_counts.items(), key=lambda x: x[1], reverse=True)[:5])
        
        return org_info
    
    def _collect_repository_data(self, repo, org_login: str) -> Dict[str, Any]:
        """Collect detailed data for a single repository"""
        
        # Calculate days since last push
        days_since_push = None
        if hasattr(repo, 'pushed_at') and repo.pushed_at:
            try:
                delta = datetime.now() - repo.pushed_at.replace(tzinfo=None)
                days_since_push = delta.days
            except:
                pass
        
        # Get owner information
        owner_type = 'User'
        owner_name = repo.owner.login if hasattr(repo, 'owner') else org_login
        
        if hasattr(repo, 'organization') and repo.organization:
            owner_type = 'Organization'
            owner_name = repo.organization.login
        elif hasattr(repo.owner, 'type'):
            owner_type = repo.owner.type
        
        # Determine visibility
        visibility = 'private' if repo.private else 'public'
        if hasattr(repo, 'visibility'):
            visibility = repo.visibility
        
        repo_data = {
            'organization_login': org_login,
            'repository_id': repo.id,
            'repository_name': repo.name,
            'full_name': repo.full_name,
            'owner_login': owner_name,
            'owner_type': owner_type,
            'description': repo.description if repo.description else 'No description',
            'primary_language': repo.language if repo.language else 'None',
            'visibility': visibility,
            'private': repo.private,
            'archived': repo.archived,
            'disabled': repo.disabled if hasattr(repo, 'disabled') else False,
            'fork': repo.fork,
            'default_branch': repo.default_branch,
            'size_kb': repo.size,
            'stars': repo.stargazers_count,
            'watchers': repo.watchers_count,
            'forks': repo.forks_count,
            'open_issues': repo.open_issues_count,
            'has_issues': repo.has_issues,
            'has_projects': repo.has_projects if hasattr(repo, 'has_projects') else False,
            'has_wiki': repo.has_wiki,
            'has_pages': repo.has_pages if hasattr(repo, 'has_pages') else False,
            'has_downloads': repo.has_downloads if hasattr(repo, 'has_downloads') else False,
            'created_at': repo.created_at.isoformat() if repo.created_at else None,
            'updated_at': repo.updated_at.isoformat() if repo.updated_at else None,
            'pushed_at': repo.pushed_at.isoformat() if repo.pushed_at else None,
            'days_since_push': days_since_push,
            'url': repo.html_url,
            'clone_url': repo.clone_url if hasattr(repo, 'clone_url') else None,
            'homepage': repo.homepage if repo.homepage else None,
            'license': repo.license.name if hasattr(repo, 'license') and repo.license else 'None',
            'topics': list(repo.get_topics()) if hasattr(repo, 'get_topics') else []
        }
        
        return repo_data
    
    def get_repository_summary(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary statistics from collected data"""
        
        summary = {
            'total_organizations': len(org_data.get('organizations', [])),
            'total_repositories': 0,
            'total_size_mb': 0,
            'total_stars': 0,
            'total_forks': 0,
            'by_visibility': {'public': 0, 'private': 0, 'internal': 0},
            'by_status': {'active': 0, 'archived': 0},
            'by_language': {},
            'by_organization': {}
        }
        
        for org in org_data.get('organizations', []):
            org_login = org['organization_login']
            repo_count = len(org['repositories'])
            
            summary['total_repositories'] += repo_count
            summary['total_size_mb'] += org['total_size_kb'] / 1024
            summary['total_stars'] += org['total_stars']
            summary['total_forks'] += org['total_forks']
            
            summary['by_visibility']['public'] += org.get('public_repos', 0)
            summary['by_visibility']['private'] += org.get('private_repos', 0)
            summary['by_visibility']['internal'] += org.get('internal_repos', 0)
            
            summary['by_status']['active'] += org.get('active_repos', 0)
            summary['by_status']['archived'] += org.get('archived_repos', 0)
            
            summary['by_organization'][org_login] = repo_count
            
            # Aggregate languages
            for lang, count in org.get('languages', {}).items():
                summary['by_language'][lang] = summary['by_language'].get(lang, 0) + count
        
        # Sort languages by count
        summary['by_language'] = dict(sorted(summary['by_language'].items(), 
                                            key=lambda x: x[1], reverse=True)[:10])
        
        return summary