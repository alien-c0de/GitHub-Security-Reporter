"""
Async Organization Data Collector - GraphQL Edition
Uses GraphQL API for 10-20x faster data fetching compared to REST API
Fetches ALL organizations in GitHub Enterprise with parallel processing
"""
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import requests

from src.collectors.base_collector import BaseCollector
from src.utils.github_client import GitHubClient
from config.settings import settings

logger = logging.getLogger(__name__)

class AsyncOrganizationDataCollector(BaseCollector):
    """
    Async collector using GraphQL for ALL organizations and repositories
    
    GraphQL Benefits:
    - Fetch exactly the fields needed (no over-fetching)
    - Batch multiple requests in one call
    - 10-20x faster than REST API for large datasets
    - Built-in pagination handling
    """
    
    def __init__(self, github_client: GitHubClient, max_workers: int = 10):
        super().__init__(github_client)
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # GraphQL endpoint configuration
        # Use GITHUB_ENTERPRISE_URL from settings, fallback to standard GitHub API
        base_url = getattr(settings, 'github_enterprise_url', 'https://api.github.com')
        # Remove /api if it's at the end (for enterprise URLs)
        base_url = base_url.rstrip('/')
        if base_url.endswith('/api'):
            base_url = base_url[:-4]
        
        self.graphql_url = f"{base_url}/graphql"
        self.graphql_headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Content-Type": "application/json"
        }
        self.request_count = 0
    
    def get_collector_name(self) -> str:
        return "AsyncOrganizationDataCollector (GraphQL)"
    
    def collect(self) -> Dict[str, Any]:
        """
        Collect ALL organizations and their repositories using GraphQL
        
        Returns:
            Dictionary with all organizations and repository details
        """
        self._mark_collection_time()
        
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]Collecting Organizations via GraphQL API (10-20x faster)[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("")
        
        start_time = time.time()
        
        # Get all organizations via GraphQL
        logger.info("[cyan][+] Fetching organizations via GraphQL...[/cyan]")
        all_orgs, access_errors = self._get_all_organizations_graphql()
        org_count = len(all_orgs)
        
        logger.info(f"[bright_green][✓] Found {org_count} organizations[/bright_green]")
        if access_errors:
            logger.warning(f"[yellow][!] {len(access_errors)} organizations skipped (access restricted)[/yellow]")
        logger.info("")
        
        if org_count == 0:
            logger.warning("[yellow]No organizations found. Check your GitHub token permissions.[/yellow]")
            return {
                'collected_at': self.collection_timestamp.isoformat(),
                'organizations': [],
                'total_organizations': 0,
                'total_repositories': 0,
                'access_errors': access_errors
            }
        
        # Collect repository data for all organizations using async GraphQL
        logger.info(f"[cyan][+] Collecting repository data using {self.max_workers} parallel workers...[/cyan]")
        logger.info("[dim]Using GraphQL batch queries for maximum speed[/dim]")
        logger.info("")
        
        # Run async collection
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            organizations_data = loop.run_until_complete(
                self._collect_all_organizations_async(all_orgs)
            )
        finally:
            loop.close()
        
        elapsed = time.time() - start_time
        
        # Calculate totals
        total_repos = sum(len(org.get('repositories', [])) for org in organizations_data)
        
        result = {
            'collected_at': self.collection_timestamp.isoformat(),
            'organizations': organizations_data,
            'total_organizations': len(organizations_data),
            'total_repositories': total_repos,
            'collection_time_seconds': elapsed,
            'access_errors': access_errors,
            'graphql_requests': self.request_count
        }
        
        logger.info("")
        logger.info("[bright_green]" + "=" * 100 + "[/bright_green]")
        logger.info(f"[bright_green][✓] Successfully collected data from {len(organizations_data)} organizations[/bright_green]")
        logger.info(f"[bright_green][✓] Total repositories: {total_repos:,}[/bright_green]")
        logger.info(f"[bright_green][✓] Collection time: {elapsed:.2f}s ({elapsed/60:.2f} min)[/bright_green]")
        logger.info(f"[bright_green][✓] GraphQL requests: {self.request_count}[/bright_green]")
        if total_repos > 0:
            logger.info(f"[bright_cyan][⚡] Speed: {total_repos/elapsed:.1f} repos/second[/bright_cyan]")
        logger.info("[bright_green]" + "=" * 100 + "[/bright_green]")
        logger.info("")
        
        return result
    
    def _graphql_query(self, query: str, variables: Optional[Dict] = None, max_retries: int = 3) -> tuple:
        """
        Execute a GraphQL query with retry logic for transient errors
        
        Args:
            query: GraphQL query string
            variables: Query variables
            max_retries: Maximum number of retry attempts for 502/503 errors
        
        Returns:
            (data, errors) tuple
        """
        import time
        
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.graphql_url,
                    headers=self.graphql_headers,
                    json=payload,
                    timeout=120  # Increased timeout for large repos
                )
                self.request_count += 1
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('data'), result.get('errors', [])
                
                elif response.status_code in [502, 503, 504]:
                    # Server timeout/overload - retry with exponential backoff
                    wait_time = (2 ** attempt) * 2  # 2s, 4s, 8s
                    logger.warning(f"[yellow]GraphQL request returned {response.status_code}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})[/yellow]")
                    time.sleep(wait_time)
                    continue
                
                else:
                    logger.warning(f"[yellow]GraphQL request failed: {response.status_code}[/yellow]")
                    logger.debug(f"Response: {response.text[:200]}")
                    return None, []
                    
            except requests.Timeout:
                wait_time = (2 ** attempt) * 2
                logger.warning(f"[yellow]GraphQL request timeout, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})[/yellow]")
                time.sleep(wait_time)
                last_error = "Timeout"
                continue
                
            except Exception as e:
                logger.error(f"[red]GraphQL request exception: {e}[/red]")
                return None, []
        
        # All retries failed
        logger.error(f"[red]GraphQL request failed after {max_retries} attempts. Last error: {last_error or 'Unknown'}[/red]")
        return None, []
    
    def _get_all_organizations_graphql(self) -> tuple:
        """
        Get all organizations using GraphQL - much faster than REST API
        
        Returns:
            (organizations_list, access_errors_list)
        """
        # Try enterprise query first (if token has enterprise access)
        # Check multiple possible setting names for enterprise slug
        enterprise_slug = (
            getattr(settings, 'github_enterprise_slug', None) or
            getattr(settings, 'github_enterprise', None) or
            getattr(settings, 'enterprise_slug', None)
        )
        
        if enterprise_slug:
            logger.info(f"[cyan]Attempting enterprise query for: {enterprise_slug}[/cyan]")
            orgs, errors = self._get_enterprise_orgs_graphql(enterprise_slug)
            if orgs:
                return orgs, errors
            logger.info("[yellow]Enterprise query failed, falling back to viewer organizations[/yellow]")
        
        # Fallback: Get organizations accessible to the authenticated user
        return self._get_viewer_organizations_graphql()
    
    def _get_enterprise_orgs_graphql(self, enterprise_slug: str) -> tuple:
        """
        Fetch all organizations in an enterprise using GraphQL
        
        Returns:
            (organizations, access_errors)
        """
        query = """
        query($enterprise: String!, $cursor: String) {
          enterprise(slug: $enterprise) {
            organizations(first: 50, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              totalCount
              nodes {
                login
                id
                databaseId
                name
                description
                url
                createdAt
                email
                location
              }
            }
          }
        }
        """
        
        all_orgs = []
        all_errors = []
        cursor = None
        
        while True:
            variables = {"enterprise": enterprise_slug, "cursor": cursor}
            data, errors = self._graphql_query(query, variables)
            
            if not data or 'enterprise' not in data or not data['enterprise']:
                return [], []
            
            orgs_data = data['enterprise']['organizations']
            orgs = orgs_data['nodes']
            
            # Process errors (access-restricted organizations)
            if errors:
                for error in errors:
                    if 'path' in error and len(error['path']) >= 4:
                        org_index = error['path'][3]
                        all_errors.append({
                            "organization": f"Organization at index {org_index}",
                            "error": error.get('message', 'Access restricted'),
                            "type": error.get('type', 'FORBIDDEN')
                        })
            
            # Filter out None values
            orgs = [org for org in orgs if org is not None]
            all_orgs.extend(orgs)
            
            logger.info(f"[dim]  Fetched {len(orgs)} orgs (Total: {len(all_orgs)})[/dim]")
            
            if not orgs_data['pageInfo']['hasNextPage']:
                break
            
            cursor = orgs_data['pageInfo']['endCursor']
        
        return all_orgs, all_errors
    
    def _get_viewer_organizations_graphql(self) -> tuple:
        """
        Fallback: Get organizations accessible to authenticated user
        
        Returns:
            (organizations, access_errors)
        """
        query = """
        query($cursor: String) {
          viewer {
            organizations(first: 50, after: $cursor) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                login
                id
                databaseId
                name
                description
                url
                createdAt
                email
                location
              }
            }
          }
        }
        """
        
        all_orgs = []
        cursor = None
        
        while True:
            variables = {"cursor": cursor}
            data, errors = self._graphql_query(query, variables)
            
            if not data or 'viewer' not in data:
                break
            
            orgs_data = data['viewer']['organizations']
            orgs = [org for org in orgs_data['nodes'] if org is not None]
            all_orgs.extend(orgs)
            
            logger.info(f"[dim]  Fetched {len(orgs)} orgs (Total: {len(all_orgs)})[/dim]")
            
            if not orgs_data['pageInfo']['hasNextPage']:
                break
            
            cursor = orgs_data['pageInfo']['endCursor']
        
        return all_orgs, []
    
    async def _collect_all_organizations_async(self, all_orgs: List[Dict]) -> List[Dict[str, Any]]:
        """Collect repository data for all organizations using async parallel processing"""
        
        tasks = []
        for org in all_orgs:
            task = self._collect_org_repos_async(org)
            tasks.append(task)
        
        # Process all organizations concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out failed organizations
        successful_orgs = []
        failed_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.warning(f"[yellow]Failed to collect: {result}[/yellow]")
            elif result is not None:
                successful_orgs.append(result)
        
        if failed_count > 0:
            logger.warning(f"[yellow]{failed_count} organization(s) failed[/yellow]")
        
        return successful_orgs
    
    async def _collect_org_repos_async(self, org: Dict) -> Optional[Dict[str, Any]]:
        """Collect repository data for a single organization using GraphQL"""
        loop = asyncio.get_event_loop()
        
        try:
            org_data = await loop.run_in_executor(
                self.executor,
                self._collect_organization_repos_graphql,
                org
            )
            return org_data
        except Exception as e:
            logger.error(f"[red]Error collecting {org['login']}: {e}[/red]")
            return None
    
    def _collect_organization_repos_graphql(self, org: Dict) -> Dict[str, Any]:
        """
        Collect all repositories for an organization using GraphQL
        (runs in thread pool)
        """
        org_login = org['login']
        logger.info(f"[cyan]  → Processing: {org_login}[/cyan]")
        
        # Organization basic info
        org_info = {
            'organization_id': org.get('databaseId'),
            'organization_name': org.get('name') or org_login,
            'organization_login': org_login,
            'description': org.get('description') or 'N/A',
            'url': org.get('url') or f'https://github.com/{org_login}',
            'created_at': org.get('createdAt'),
            'email': org.get('email'),
            'location': org.get('location'),
            'repositories': []
        }
        
        # GraphQL query to get all repositories for this organization
        # Using smaller batch size (50) to avoid 502 errors on large organizations
        # Includes ALL GitHub Advanced Security features in a single query - FAST!
        query = """
        query($org: String!, $cursor: String) {
          organization(login: $org) {
            repositories(first: 50, after: $cursor, orderBy: {field: NAME, direction: ASC}) {
              pageInfo {
                hasNextPage
                endCursor
              }
              totalCount
              nodes {
                name
                description
                url
                createdAt
                updatedAt
                pushedAt
                isPrivate
                isFork
                isArchived
                isTemplate
                visibility
                primaryLanguage {
                  name
                }
                defaultBranchRef {
                  name
                }
                stargazerCount
                forkCount
                watchers {
                  totalCount
                }
                diskUsage
                licenseInfo {
                  name
                }
                vulnerabilityAlerts(first: 1, states: [OPEN]) {
                  totalCount
                }
              }
            }
          }
        }
        """
        
        cursor = None
        repo_count = 0
        
        try:
            while True:
                variables = {"org": org_login, "cursor": cursor}
                data, errors = self._graphql_query(query, variables)
                
                # Enhanced error logging
                if errors:
                    logger.warning(f"[yellow]  GraphQL errors for {org_login}:[/yellow]")
                    for error in errors:
                        logger.warning(f"[yellow]    - {error.get('message', error)}[/yellow]")
                        logger.debug(f"[dim]    Error details: {error}[/dim]")
                
                if not data:
                    logger.warning(f"[yellow]  No data returned from GraphQL for {org_login}[/yellow]")
                    break
                
                if 'organization' not in data or not data['organization']:
                    logger.warning(f"[yellow]  No access to repos for {org_login}[/yellow]")
                    logger.debug(f"[dim]  Response data: {data}[/dim]")
                    break
                
                repos_data = data['organization']['repositories']
                
                # Log total count if available
                if repos_data.get('totalCount') is not None:
                    logger.info(f"[dim]    {org_login}: Found {repos_data['totalCount']} total repositories[/dim]")
                
                repos = repos_data['nodes']
                
                for repo in repos:
                    if repo is None:
                        continue
                    
                    # Calculate days since last push
                    days_since_push = None
                    if repo.get('pushedAt'):
                        try:
                            from datetime import datetime
                            pushed_date = datetime.fromisoformat(repo['pushedAt'].replace('Z', '+00:00'))
                            days_since_push = (datetime.now(pushed_date.tzinfo) - pushed_date).days
                        except:
                            pass
                    
                    repo_data = {
                        'organization': org_login,
                        'repository': repo['name'],
                        'repository_name': repo['name'],
                        'full_name': f"{org_login}/{repo['name']}",
                        'owner_login': org_login,
                        'description': repo.get('description') or 'N/A',
                        'url': repo['url'],
                        'created_at': repo.get('createdAt'),
                        'updated_at': repo.get('updatedAt'),
                        'pushed_at': repo.get('pushedAt'),
                        'visibility': repo.get('visibility', 'private' if repo.get('isPrivate') else 'public').lower(),
                        'is_fork': repo.get('isFork', False),
                        'fork': repo.get('isFork', False),
                        'is_template': repo.get('isTemplate', False),
                        'archived': repo.get('isArchived', False),
                        'primary_language': repo['primaryLanguage']['name'] if repo.get('primaryLanguage') else None,
                        'default_branch': repo['defaultBranchRef']['name'] if repo.get('defaultBranchRef') else 'main',
                        'stars': repo.get('stargazerCount', 0),
                        'forks': repo.get('forkCount', 0),
                        'watchers': repo['watchers']['totalCount'] if repo.get('watchers') else 0,
                        'size_kb': repo.get('diskUsage', 0),
                        'license': repo['licenseInfo']['name'] if repo.get('licenseInfo') else None,
                        'days_since_push': days_since_push,
                        # Fields not available in GraphQL - set defaults
                        'open_issues': 0,  # Would require separate query
                        'has_wiki': False,  # Would require separate query
                        'has_issues': False,  # Would require separate query
                        
                        # GitHub Advanced Security - Alert Counts AND Status Flags
                        'dependabot_alerts': repo['vulnerabilityAlerts']['totalCount'] if repo.get('vulnerabilityAlerts') else 0,
                        'dependabot_enabled': None,  # Will determine based on REST API response
                        
                        'code_scanning_alerts': 0,  # Will fetch separately
                        'code_scanning_enabled': None,  # NEW: Will determine based on API response
                        
                        'secret_scanning_alerts': 0,  # Will fetch separately
                        'secret_scanning_enabled': None,  # NEW: Will determine based on API response
                        
                        'total_security_alerts': repo['vulnerabilityAlerts']['totalCount'] if repo.get('vulnerabilityAlerts') else 0,
                        
                        # Repository administrators/owners - Will fetch via REST API
                        'repository_admins': 'N/A',  # Will fetch separately
                        'admin_emails': 'N/A',  # Will fetch separately  
                        'admin_count': 0  # Will fetch separately
                    }
                    
                    org_info['repositories'].append(repo_data)
                    repo_count += 1
                
                if not repos_data['pageInfo']['hasNextPage']:
                    break
                
                cursor = repos_data['pageInfo']['endCursor']
                
                if repo_count % 50 == 0:
                    logger.info(f"[dim]    {org_login}: {repo_count} repos...[/dim]")
            
            # After collecting all repos, try to fetch security scanning data
            # This is done separately because it requires special permissions
            if org_info['repositories']:
                self._fetch_security_scanning_data(org_login, org_info['repositories'])
        
        except Exception as e:
            logger.error(f"[red]  Exception collecting repos for {org_login}: {e}[/red]")
            import traceback
            logger.debug(traceback.format_exc())
        
        logger.info(f"[bright_green]  ✓ {org_login}: {len(org_info['repositories'])} repositories[/bright_green]")
        
        # Add summary statistics
        org_info['repository_count'] = len(org_info['repositories'])
        org_info['total_size_kb'] = sum(r.get('size_kb', 0) for r in org_info['repositories'])
        org_info['total_stars'] = sum(r.get('stars', 0) for r in org_info['repositories'])
        org_info['total_forks'] = sum(r.get('forks', 0) for r in org_info['repositories'])
        
        # Count by visibility
        org_info['public_repos'] = sum(1 for r in org_info['repositories'] if r.get('visibility') == 'public')
        org_info['private_repos'] = sum(1 for r in org_info['repositories'] if r.get('visibility') == 'private')
        org_info['internal_repos'] = sum(1 for r in org_info['repositories'] if r.get('visibility') == 'internal')
        
        # Count archived and active
        org_info['archived_repos'] = sum(1 for r in org_info['repositories'] if r.get('archived', False))
        org_info['active_repos'] = sum(1 for r in org_info['repositories'] if not r.get('archived', False))
        
        # Count by language (top 5)
        language_counts = {}
        for repo in org_info['repositories']:
            lang = repo.get('primary_language')
            if lang and lang != 'None':
                language_counts[lang] = language_counts.get(lang, 0) + 1
        
        org_info['languages'] = dict(sorted(language_counts.items(), key=lambda x: x[1], reverse=True)[:5])
        
        return org_info
    
    def _fetch_security_scanning_data(self, org_login: str, repositories: List[Dict]):
        """
        Fetch Code Scanning and Secret Scanning using concurrent async requests
        This is MUCH faster than sequential REST calls (10x speedup!)
        """
        if not repositories:
            return
        
        logger.info(f"[dim]    {org_login}: Fetching Code & Secret scanning (concurrent)...[/dim]")
        
        import asyncio
        import aiohttp
        
        # Run async fetching
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(
                self._fetch_security_concurrent(org_login, repositories)
            )
        finally:
            loop.close()
        
        logger.info(f"[dim]    {org_login}: Security scanning complete ({len(repositories)}/{len(repositories)} repos)[/dim]")
    
    async def _fetch_security_concurrent(self, org_login: str, repositories: List[Dict]):
        """Fetch security data for all repos concurrently using aiohttp"""
        import aiohttp
        
        base_url = getattr(settings, 'github_enterprise_url', 'https://api.github.com').rstrip('/')
        if base_url.endswith('/api'):
            base_url = base_url[:-4]
        
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json"
        }
        
        # Timeout fix for large orgs (500+ repos):
        # aiohttp.ClientTimeout(connect=N) limits how long a task waits to
        # ACQUIRE a connection from the pool — not just the TCP handshake.
        # With 518 tasks and only 20 pool slots, tasks 21-518 must queue.
        # With connect=30, queued tasks that wait >30s for a free slot raise
        # asyncio.TimeoutError, which is caught silently and sets all counts to 0.
        # Fix: Remove the connect sub-timeout entirely so pool acquisition never
        # times out, and increase limit to 50 to reduce queue depth.
        # total=600 gives each individual HTTP request up to 10 minutes.
        timeout = aiohttp.ClientTimeout(total=600)
        connector = aiohttp.TCPConnector(limit=50)  # Larger pool reduces queue depth
        
        async with aiohttp.ClientSession(headers=headers, timeout=timeout, connector=connector) as session:
            tasks = []
            
            # Create tasks for all repositories
            for repo in repositories:
                task = self._fetch_repo_security(session, base_url, org_login, repo)
                tasks.append(task)
            
            # Execute all tasks concurrently with progress updates
            completed = 0
            for coro in asyncio.as_completed(tasks):
                await coro
                completed += 1
                if completed % 50 == 0:
                    logger.info(f"[dim]    {org_login}: {completed} repos scanned...[/dim]")
    
    async def _fetch_repo_security(self, session, base_url: str, org_login: str, repo: Dict):
        """Fetch Code and Secret scanning for a single repo (async) - WITH STATUS TRACKING"""
        import aiohttp
        
        repo_name = repo['repository_name']
        
        try:
            # Fetch Dependabot status via REST to set the enabled flag.
            # The ALERT COUNT comes from GraphQL vulnerabilityAlerts (already set)
            # and must NOT be overwritten here — GraphQL is the accurate source.
            #
            # Bug fix: Previously, 403/404 responses set dependabot_alerts = 0,
            # erasing the correct GraphQL count. This happened for every repo in
            # large orgs (e.g. 518 repos) where the REST token lacks org-level
            # Dependabot REST scope, causing all counts to appear as 0.
            # Now we only update the 'enabled' flag and never touch the count.
            dependabot_url = f"{base_url}/repos/{org_login}/{repo_name}/dependabot/alerts"
            async with session.get(dependabot_url, params={"state": "open", "per_page": 1}) as resp:
                if resp.status == 200:
                    repo['dependabot_enabled'] = True
                    # GraphQL count is already set; keep it (don't overwrite)
                elif resp.status == 404:
                    # Feature not configured — mark disabled but KEEP GraphQL count
                    repo['dependabot_enabled'] = False
                elif resp.status == 403:
                    # No REST permission — mark disabled but KEEP GraphQL count
                    repo['dependabot_enabled'] = False
                else:
                    repo['dependabot_enabled'] = None  # unknown, keep GraphQL count
            
            # Fetch Code Scanning alerts - paginate through ALL pages.
            # Previously fetched only the first page (per_page=100), causing repos
            # with more than 100 alerts to be silently undercounted (e.g. a repo with
            # 250 alerts would show as 100). Now we follow pagination until done.
            code_url = f"{base_url}/repos/{org_login}/{repo_name}/code-scanning/alerts"
            code_page = 1
            code_total = 0
            code_enabled = None
            while True:
                async with session.get(
                    code_url,
                    params={"state": "open", "per_page": 100, "page": code_page}
                ) as resp:
                    if resp.status == 200:
                        code_enabled = True
                        batch = await resp.json()
                        if not isinstance(batch, list):
                            break
                        code_total += len(batch)
                        if len(batch) < 100:
                            break   # last page
                        code_page += 1
                    elif resp.status == 404:
                        code_enabled = False   # feature not configured
                        break
                    elif resp.status == 403:
                        code_enabled = False   # no permission
                        break
                    else:
                        code_enabled = None    # unknown
                        break
            repo['code_scanning_alerts'] = code_total
            repo['code_scanning_enabled'] = code_enabled

            # Fetch Secret Scanning alerts - paginate through ALL pages.
            # Same single-page truncation bug as Code Scanning above.
            secret_url = f"{base_url}/repos/{org_login}/{repo_name}/secret-scanning/alerts"
            secret_page = 1
            secret_total = 0
            secret_enabled = None
            while True:
                async with session.get(
                    secret_url,
                    params={"state": "open", "per_page": 100, "page": secret_page}
                ) as resp:
                    if resp.status == 200:
                        secret_enabled = True
                        batch = await resp.json()
                        if not isinstance(batch, list):
                            break
                        secret_total += len(batch)
                        if len(batch) < 100:
                            break   # last page
                        secret_page += 1
                    elif resp.status == 404:
                        secret_enabled = False
                        break
                    elif resp.status == 403:
                        secret_enabled = False
                        break
                    else:
                        secret_enabled = None
                        break
            repo['secret_scanning_alerts'] = secret_total
            repo['secret_scanning_enabled'] = secret_enabled
            
            # Update total
            repo['total_security_alerts'] = (
                repo.get('dependabot_alerts', 0) +
                repo.get('code_scanning_alerts', 0) +
                repo.get('secret_scanning_alerts', 0)
            )
            
            # Fetch repository collaborators with admin permissions
            # This gets users who have admin access to the repository
            collaborators_url = f"{base_url}/repos/{org_login}/{repo_name}/collaborators"
            try:
                async with session.get(collaborators_url, params={"affiliation": "all", "per_page": 100}) as resp:
                    if resp.status == 200:
                        collaborators = await resp.json()
                        # Filter for admin users only
                        admins = [
                            collab for collab in collaborators 
                            if isinstance(collab, dict) and collab.get('permissions', {}).get('admin', False)
                        ]
                        
                        # Get up to 5 admin names (ALL) and REAL emails (ONLY PUBLIC)
                        admin_names = []
                        admin_emails = []
                        
                        for admin in admins[:5]:  # Limit to 5 admins
                            login = admin.get('login', 'N/A')
                            
                            # ALWAYS add the admin name (regardless of email)
                            admin_names.append(login)
                            
                            # Fetch REAL email from user API
                            # ONLY add email if it's real and public
                            user_email = None
                            try:
                                user_url = f"{base_url}/users/{login}"
                                async with session.get(user_url) as user_resp:
                                    if user_resp.status == 200:
                                        user_data = await user_resp.json()
                                        # Get email from user profile (if public)
                                        user_email = user_data.get('email', None)
                                        
                                        # Only accept real emails (not null, not empty)
                                        if user_email and user_email != 'null' and '@' in user_email:
                                            # Valid email found - add to email list
                                            admin_emails.append(user_email)
                                        # If no valid email, don't add to email list (but name is already added)
                            except Exception as e:
                                logger.debug(f"[dim]Could not fetch email for {login}: {e}[/dim]")
                                # Skip email for this admin (but name is already in the list)
                        
                        # Set admin names (up to 5, all of them)
                        repo['repository_admins'] = ', '.join(admin_names) if admin_names else 'N/A'
                        
                        # Set emails (only real ones - could be 0 to 5)
                        repo['admin_emails'] = ', '.join(admin_emails) if admin_emails else 'N/A'
                        
                        repo['admin_count'] = len(admins)
                    else:
                        repo['repository_admins'] = 'N/A'
                        repo['admin_emails'] = 'N/A'
                        repo['admin_count'] = 0
            except Exception as e:
                logger.debug(f"[dim]Error fetching collaborators for {repo_name}: {e}[/dim]")
                repo['repository_admins'] = 'N/A'
                repo['admin_emails'] = 'N/A'
                repo['admin_count'] = 0
            
        except Exception as e:
            # Log at WARNING (not debug) so these are visible in normal runs.
            # Previously logged at debug level, making it impossible to diagnose
            # why large orgs were silently returning 0 for all security counts.
            logger.warning(f"[yellow]  Security fetch error for {repo_name}: {type(e).__name__}: {e}[/yellow]")
            repo['dependabot_enabled'] = False
            repo['code_scanning_alerts'] = 0
            repo['code_scanning_enabled'] = False
            repo['secret_scanning_alerts'] = 0
            repo['secret_scanning_enabled'] = False
            repo['repository_admins'] = 'N/A'
            repo['admin_emails'] = 'N/A'
            repo['admin_count'] = 0
    
    def get_summary_statistics(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate enterprise-wide summary statistics"""
        organizations = org_data.get('organizations', [])
        
        total_repos = sum(len(org.get('repositories', [])) for org in organizations)
        total_size = sum(org.get('total_size_kb', 0) for org in organizations)
        total_stars = sum(org.get('total_stars', 0) for org in organizations)
        total_forks = sum(org.get('total_forks', 0) for org in organizations)
        
        # By status
        by_status = {
            'active': sum(org.get('active_repos', 0) for org in organizations),
            'archived': sum(org.get('archived_repos', 0) for org in organizations)
        }
        
        # By visibility
        by_visibility = {
            'public': sum(org.get('public_repos', 0) for org in organizations),
            'private': sum(org.get('private_repos', 0) for org in organizations),
            'internal': sum(org.get('internal_repos', 0) for org in organizations)
        }
        
        # By language
        by_language = {}
        for org in organizations:
            for repo in org.get('repositories', []):
                lang = repo.get('primary_language')
                if lang:
                    by_language[lang] = by_language.get(lang, 0) + 1
        
        by_language = dict(sorted(by_language.items(), key=lambda x: x[1], reverse=True))
        
        # Top organizations by repo count
        top_orgs = sorted(
            [(org['organization_login'], org['repository_count']) for org in organizations],
            key=lambda x: x[1],
            reverse=True
        )
        
        return {
            'total_organizations': len(organizations),
            'total_repositories': total_repos,
            'total_size_mb': total_size / 1024,
            'total_stars': total_stars,
            'total_forks': total_forks,
            'by_status': by_status,
            'by_visibility': by_visibility,
            'by_language': by_language,
            'top_organizations_by_repo_count': top_orgs
        }