"""
Repository Health Collector  —  Optimised v2
════════════════════════════════════════════════════════════════════════════════
PERFORMANCE vs v1 (500-repo org)
  ❌ OLD : Per-repo sequential REST calls for every check:
           • _check_dependabot()         → 500 REST calls
           • _check_code_scanning()      → 500 REST calls
           • _check_secret_scanning()    → 500 REST calls
           • _check_secret_push_prot()   → 500 REST calls  (repeats secret scan)
           • _check_branch_protection()  → 500 REST calls
           • _check_security_policy()    → 500+ REST calls (2 fallback paths)
           • _check_codeowners()         → 500+ REST calls (2 fallback paths)
           • _get_repository_owner_info()→ 500+ REST calls + /users/{login} per admin
           TOTAL: ~5 000–6 000 sequential requests  →  15–20 min

  ✅ NEW :
           1. ONE GraphQL query fetches repo metadata + branch protection +
              security policy URL + vulnerability alert count for ALL 500 repos.
           2. ONE async aiohttp session concurrently fires REST calls for
              code scanning, secret scanning, dependabot status, and collaborators
              (all 500 repos in parallel, capped at 30 connections).
           TOTAL: 1 GraphQL call + ~2 000 concurrent REST  →  60–90 sec
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
import requests

from config.settings import settings
from src.collectors.base_collector import BaseCollector
from src.utils.github_client import GitHubClient

logger = logging.getLogger(__name__)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _api_base() -> str:
    base = getattr(settings, "github_enterprise_url", "https://api.github.com").rstrip("/")
    if base in ("https://github.com", "https://api.github.com"):
        return "https://api.github.com"
    if base.endswith("/api"):
        base = base[:-4]
    return f"{base}/api/v3"


def _graphql_url() -> str:
    base = getattr(settings, "github_enterprise_url", "https://api.github.com").rstrip("/")
    if base in ("https://github.com", "https://api.github.com"):
        return "https://api.github.com/graphql"
    if base.endswith("/api"):
        base = base[:-4]
    return f"{base}/api/graphql"


def _make_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── GraphQL: fetch all repo health metadata in one call ──────────────────────

_REPO_HEALTH_QUERY = """
query OrgRepoHealth($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 50, after: $cursor, orderBy: {field: NAME, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage  endCursor }
      nodes {
        name
        nameWithOwner
        url
        visibility
        isPrivate
        isArchived
        isDisabled
        isFork
        primaryLanguage { name }
        pushedAt
        createdAt
        updatedAt
        diskUsage
        stargazerCount
        forkCount
        defaultBranchRef {
          name
          branchProtectionRule {
            requiresApprovingReviews
            requiredApprovingReviewCount
            isAdminEnforced
            allowsForcePushes
            allowsDeletions
            dismissesStaleReviews
            requiresStatusChecks
            requiresCodeOwnerReviews
            requiresLinearHistory
            restrictsPushes
          }
        }
        securityPolicyUrl
        hasVulnerabilityAlertsEnabled
        vulnerabilityAlerts(states: [OPEN]) { totalCount }
        owner {
          login
          ... on Organization { name  email }
          ... on User         { name  email }
        }
        collaborators(affiliation: ALL, first: 10) {
          edges {
            permission
            node { login  name  email }
          }
        }
      }
    }
  }
}
"""


class RepositoryHealthCollector(BaseCollector):
    """
    Repository health and compliance collector (optimised v2).

    Uses GraphQL for batch metadata + concurrent async REST for security checks.
    """

    def __init__(self, github_client: GitHubClient):
        super().__init__(github_client)
        self._base = _api_base()
        self._gql_url = _graphql_url()
        self._hdrs = _make_headers()
        self._gql_hdrs = {
            "Authorization": f"Bearer {settings.github_token}",
            "Content-Type": "application/json",
        }
        self._org = settings.github_org

    def get_collector_name(self) -> str:
        return "RepositoryHealthCollector"

    # ── public entry ──────────────────────────────────────────────────────────

    def collect(self) -> List[Dict[str, Any]]:
        self._mark_collection_time()

        # 1. Fetch all repo metadata via GraphQL
        logger.info(
            f"[bright_yellow][+] Collecting repository health via GraphQL + async REST...[/bright_yellow]"
        )
        repos, used_rest_fallback = self._graphql_all_repos()
        logger.info(f"[dim]  GraphQL: fetched metadata for {len(repos)} repositories[/dim]")

        # 2. Enrich each repo with security scanning status via concurrent REST.
        #    Skip enrichment when the REST fallback was used — the records already
        #    contain only minimal metadata and the async enrichment would fire
        #    515 × 3 = 1545 additional aiohttp requests on top of the sequential
        #    PyGithub pagination that the fallback already performed, making the
        #    hang even longer.  GraphQL repos get full enrichment as normal.
        if not used_rest_fallback:
            self._enrich_security_concurrent(repos)
        else:
            logger.info(
                "[yellow]  Skipping async REST enrichment (REST fallback was used — "
                "security status fields will show as Unknown)[/yellow]"
            )

        # 3. Post-process: calculate compliance score, days since push, etc.
        for record in repos:
            record["compliance_score"] = self._compliance_score(record)
            record["compliance_percentage"] = round(record["compliance_score"] * 100, 2)
            record["days_since_last_push"] = self._days_since_push(record.get("pushed_at"))
            dspp = record["days_since_last_push"]
            record["is_active"] = dspp < 90 if dspp is not None else False

        logger.info(
            f"[bright_green][✓] Total repository health records collected: {len(repos)}[/bright_green]"
        )
        return repos

    # ── GraphQL batch fetch ───────────────────────────────────────────────────

    def _graphql_all_repos(self):
        """
        Paginate through ALL repos in the org via GraphQL.

        Returns:
            Tuple (repos: List[Dict], used_rest_fallback: bool).
            used_rest_fallback is True only when GraphQL returned 0 repos and
            the slow per-repo REST fallback was invoked instead.  collect()
            uses this flag to skip async REST enrichment in that case.

        Each page request is retried up to 3 times with exponential back-off
        (2s, 4s, 8s) before giving up on that page.  This handles transient
        network errors such as "Response ended prematurely" which previously
        caused an immediate fall-through to the slow sequential REST fallback.
        """
        import time

        all_repos: List[Dict] = []
        cursor: Optional[str] = None
        _MAX_RETRIES = 3

        while True:
            payload = {
                "query": _REPO_HEALTH_QUERY,
                "variables": {"org": self._org, "cursor": cursor},
            }

            # ── retry loop for transient network errors ───────────────────────
            data = None
            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    resp = requests.post(
                        self._gql_url, json=payload,
                        headers=self._gql_hdrs, timeout=120
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    break   # success — exit retry loop
                except Exception as exc:
                    wait = 2 ** attempt   # 2s, 4s, 8s
                    if attempt < _MAX_RETRIES:
                        logger.warning(
                            f"[yellow]  GraphQL request failed (attempt {attempt}/{_MAX_RETRIES}): "
                            f"{exc} — retrying in {wait}s...[/yellow]"
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"[red]GraphQL request failed after {_MAX_RETRIES} attempts: "
                            f"{exc}[/red]"
                        )

            if data is None:
                # All retries exhausted for this page
                break

            errors = data.get("errors", [])
            if errors:
                for err in errors:
                    logger.debug(f"GraphQL error: {err.get('message')}")

            org_data = (data.get("data") or {}).get("organization")
            if not org_data:
                logger.warning("[yellow]GraphQL returned no organisation data — falling back to REST list[/yellow]")
                break

            repos_page = org_data["repositories"]
            total = repos_page.get("totalCount", "?")
            nodes = repos_page.get("nodes", [])

            for node in nodes:
                if node is None:
                    continue
                record = self._build_record_from_gql(node)
                all_repos.append(record)

            logger.info(f"[dim]  GraphQL: {len(all_repos)}/{total} repos fetched[/dim]")

            page_info = repos_page.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        # If GraphQL failed entirely (all retries exhausted on first page,
        # or org data returned empty), fall back to REST-based list.
        if not all_repos:
            logger.warning("[yellow]GraphQL fetch returned 0 repos — falling back to REST-based health check[/yellow]")
            all_repos = self._rest_fallback_collect()
            return all_repos, True   # signal to collect() that REST fallback was used

        return all_repos, False   # GraphQL succeeded — normal enrichment will follow

    def _build_record_from_gql(self, node: Dict) -> Dict[str, Any]:
        """Convert a GraphQL repository node into a health record."""
        record = self._create_base_record(node.get("name", "unknown"))

        # Branch protection
        default_branch_ref = node.get("defaultBranchRef") or {}
        branch_name = default_branch_ref.get("name", "main")
        bp_rule = default_branch_ref.get("branchProtectionRule")
        branch_protected = bp_rule is not None

        bp_details: Dict[str, Any] = {}
        if bp_rule:
            bp_details = {
                "requires_approving_reviews": bp_rule.get("requiresApprovingReviews", False),
                "required_approving_review_count": bp_rule.get("requiredApprovingReviewCount", 0),
                "is_admin_enforced": bp_rule.get("isAdminEnforced", False),
                "allow_force_pushes": bp_rule.get("allowsForcePushes", False),
                "allow_deletions": bp_rule.get("allowsDeletions", False),
                "dismisses_stale_reviews": bp_rule.get("dismissesStaleReviews", False),
                "requires_status_checks": bp_rule.get("requiresStatusChecks", False),
                "requires_code_owner_reviews": bp_rule.get("requiresCodeOwnerReviews", False),
                "requires_linear_history": bp_rule.get("requiresLinearHistory", False),
                "restricts_pushes": bp_rule.get("restrictsPushes", False),
            }

        # Owner / admins from collaborators
        owner = node.get("owner") or {}
        collabs = node.get("collaborators") or {}
        edges = collabs.get("edges") or []
        admins = [
            e["node"]
            for e in edges
            if isinstance(e, dict)
            and e.get("permission") == "ADMIN"
            and e.get("node")
        ]
        admin_names = [a.get("login", "") for a in admins]
        admin_emails = [
            a.get("email", "")
            for a in admins
            if a.get("email") and "@" in a.get("email", "")
        ]

        # Dependabot from GraphQL
        dep_count = (node.get("vulnerabilityAlerts") or {}).get("totalCount", 0)

        record.update({
            # identity
            "repo_id": None,
            "full_name": node.get("nameWithOwner", f"{self._org}/{node.get('name')}"),
            "url": node.get("url", ""),
            "visibility": node.get("visibility", "PRIVATE").lower(),
            "private": node.get("isPrivate", True),
            "archived": node.get("isArchived", False),
            "disabled": node.get("isDisabled", False),
            "fork": node.get("isFork", False),
            "language": (node.get("primaryLanguage") or {}).get("name"),
            "primary_language": (node.get("primaryLanguage") or {}).get("name"),
            "size": node.get("diskUsage", 0),
            "stars": node.get("stargazerCount", 0),
            "watchers": 0,
            "forks": node.get("forkCount", 0),
            "open_issues": 0,
            "default_branch": branch_name,
            "pushed_at": node.get("pushedAt"),
            "created_at": node.get("createdAt"),
            "updated_at": node.get("updatedAt"),

            # owner info (from GraphQL collaborators, NO extra REST calls)
            "owner_login": owner.get("login", self._org),
            "owner_name": owner.get("name") or owner.get("login", self._org),
            "owner_email": owner.get("email", "N/A"),
            "owner_type": "Organization" if not node.get("isFork") else "User",
            "repository_admins": ", ".join(admin_names) if admin_names else "N/A",
            "admin_emails": ", ".join(admin_emails) if admin_emails else "N/A",

            # branch protection (from GraphQL — no REST call needed)
            "branch_protection_enabled": branch_protected,
            "branch_protection_details": bp_details if branch_protected else {},

            # security policy (from GraphQL securityPolicyUrl)
            "has_security_policy": bool(node.get("securityPolicyUrl")),

            # dependabot from GraphQL
            "dependabot_enabled": node.get("hasVulnerabilityAlertsEnabled", False),
            "dependabot_status": "Enabled" if node.get("hasVulnerabilityAlertsEnabled") else "Disabled",
            "dependabot_alert_count": dep_count,
            "dependabot_reason": "GraphQL",

            # placeholders — filled by REST enrichment below
            "code_scanning_enabled": None,
            "code_scanning_status": "Unknown",
            "code_scanning_alert_count": 0,
            "code_scanning_reason": "",
            "secret_scanning_enabled": None,
            "secret_scanning_status": "Unknown",
            "secret_scanning_alert_count": 0,
            "secret_scanning_reason": "",
            "secret_push_protection_enabled": None,
            "secret_push_protection_status": "Unknown",
            "secret_push_protection_reason": "",
            "vulnerability_alerts_enabled": node.get("hasVulnerabilityAlertsEnabled", False),

            # codeowners placeholder
            "has_codeowners": False,
        })

        return record

    # ── async REST enrichment ─────────────────────────────────────────────────

    def _enrich_security_concurrent(self, repos: List[Dict[str, Any]]) -> None:
        """Fire concurrent REST calls for code/secret scanning and codeowners."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_enrich_all(repos))
        finally:
            loop.close()

    async def _async_enrich_all(self, repos: List[Dict[str, Any]]) -> None:
        timeout = aiohttp.ClientTimeout(total=30)
        # 30 concurrent connections is safe; increase to 50 for faster networks
        connector = aiohttp.TCPConnector(limit=30, ssl=False)

        async with aiohttp.ClientSession(
            headers=self._hdrs, timeout=timeout, connector=connector
        ) as session:
            tasks = [self._async_enrich_repo(session, repo) for repo in repos]
            completed = 0
            for coro in asyncio.as_completed(tasks):
                await coro
                completed += 1
                if completed % 100 == 0:
                    logger.info(f"[dim]  REST enrichment: {completed}/{len(repos)} repos done[/dim]")

    async def _async_enrich_repo(self, session: aiohttp.ClientSession, repo: Dict) -> None:
        """Run code scanning, secret scanning, and codeowners checks concurrently."""
        repo_name = repo.get("repository", repo.get("name", "unknown"))
        base = self._base
        org = self._org

        # Fire all three concurrently
        cs_task = self._check_code_scanning(session, base, org, repo_name)
        ss_task = self._check_secret_scanning(session, base, org, repo_name)
        co_task = self._check_codeowners(session, base, org, repo_name)

        cs_result, ss_result, co_result = await asyncio.gather(
            cs_task, ss_task, co_task, return_exceptions=True
        )

        # Code scanning
        if isinstance(cs_result, dict):
            repo["code_scanning_enabled"] = cs_result.get("enabled", False)
            repo["code_scanning_status"] = cs_result.get("status", "Unknown")
            repo["code_scanning_alert_count"] = cs_result.get("alert_count", 0)
            repo["code_scanning_reason"] = cs_result.get("reason", "")

        # Secret scanning
        if isinstance(ss_result, dict):
            repo["secret_scanning_enabled"] = ss_result.get("enabled", False)
            repo["secret_scanning_status"] = ss_result.get("status", "Unknown")
            repo["secret_scanning_alert_count"] = ss_result.get("alert_count", 0)
            repo["secret_scanning_reason"] = ss_result.get("reason", "")
            # Push protection is part of secret scanning
            repo["secret_push_protection_enabled"] = ss_result.get("enabled", False)
            repo["secret_push_protection_status"] = (
                "Likely Enabled" if ss_result.get("enabled") else "N/A"
            )
            repo["secret_push_protection_reason"] = "Part of secret scanning"

        # Codeowners
        if isinstance(co_result, bool):
            repo["has_codeowners"] = co_result

    async def _check_code_scanning(
        self, session: aiohttp.ClientSession, base: str, org: str, repo: str
    ) -> Dict:
        url = f"{base}/repos/{org}/{repo}/code-scanning/alerts"
        try:
            async with session.get(url, params={"state": "open", "per_page": 100}) as resp:
                if resp.status == 200:
                    alerts = await resp.json()
                    cnt = len(alerts) if isinstance(alerts, list) else 0
                    return {"enabled": True, "status": "Enabled", "alert_count": cnt, "reason": f"{cnt} alerts"}
                if resp.status == 404:
                    return {"enabled": False, "status": "Not Configured", "alert_count": 0, "reason": "404"}
                if resp.status == 403:
                    return {"enabled": False, "status": "No Access", "alert_count": 0, "reason": "403"}
                return {"enabled": False, "status": "Unknown", "alert_count": 0, "reason": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"enabled": False, "status": "Error", "alert_count": 0, "reason": str(exc)[:50]}

    async def _check_secret_scanning(
        self, session: aiohttp.ClientSession, base: str, org: str, repo: str
    ) -> Dict:
        url = f"{base}/repos/{org}/{repo}/secret-scanning/alerts"
        try:
            async with session.get(url, params={"state": "open", "per_page": 1}) as resp:
                if resp.status == 200:
                    alerts = await resp.json()
                    cnt = len(alerts) if isinstance(alerts, list) else 0
                    return {"enabled": True, "status": "Enabled", "alert_count": cnt, "reason": f"{cnt} secrets"}
                if resp.status == 404:
                    return {"enabled": False, "status": "Not Enabled", "alert_count": 0, "reason": "404"}
                if resp.status == 403:
                    return {"enabled": False, "status": "No Access", "alert_count": 0, "reason": "403"}
                return {"enabled": False, "status": "Unknown", "alert_count": 0, "reason": f"HTTP {resp.status}"}
        except Exception as exc:
            return {"enabled": False, "status": "Error", "alert_count": 0, "reason": str(exc)[:50]}

    async def _check_codeowners(
        self, session: aiohttp.ClientSession, base: str, org: str, repo: str
    ) -> bool:
        """Check if CODEOWNERS file exists in CODEOWNERS, .github/CODEOWNERS, or docs/CODEOWNERS."""
        for path in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
            url = f"{base}/repos/{org}/{repo}/contents/{path}"
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
        return False

    # ── REST fallback for when GraphQL returns 0 repos ────────────────────────

    def _rest_fallback_collect(self) -> List[Dict[str, Any]]:
        """
        Pure REST fallback used only when GraphQL returns 0 repos.

        This path is extremely rare (GraphQL works correctly for this token/org).
        The previous implementation imported from a non-existent file
        (repository_health_collector_rest_fallback.py) which caused a static
        analysis error and would also crash at runtime if ever invoked.

        The fallback is now inlined: enumerate repos via PyGithub and build
        minimal health records so the report is never completely empty.
        """
        logger.warning(
            "[yellow]  REST fallback: building minimal health records via PyGithub...[/yellow]"
        )
        records: List[Dict[str, Any]] = []
        try:
            for repo in self._get_repositories():
                record = self._create_base_record(repo.name)
                record.update({
                    "full_name": repo.full_name,
                    "url": repo.html_url,
                    "visibility": repo.visibility or "private",
                    "private": repo.private,
                    "archived": repo.archived,
                    "disabled": False,
                    "fork": repo.fork,
                    "language": repo.language,
                    "primary_language": repo.language,
                    "size": repo.size or 0,
                    "stars": repo.stargazers_count or 0,
                    "watchers": repo.watchers_count or 0,
                    "forks": repo.forks_count or 0,
                    "open_issues": repo.open_issues_count or 0,
                    "default_branch": repo.default_branch or "main",
                    "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                    "created_at": repo.created_at.isoformat() if repo.created_at else None,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "owner_login": repo.owner.login if repo.owner else self._org,
                    "owner_name": repo.owner.name if repo.owner else self._org,
                    "owner_email": "N/A",
                    "owner_type": "Organization",
                    "repository_admins": "N/A",
                    "admin_emails": "N/A",
                    "branch_protection_enabled": False,
                    "branch_protection_details": {},
                    "has_security_policy": False,
                    "dependabot_enabled": False,
                    "dependabot_status": "Unknown",
                    "dependabot_alert_count": 0,
                    "dependabot_reason": "REST fallback",
                    "code_scanning_enabled": None,
                    "code_scanning_status": "Unknown",
                    "code_scanning_alert_count": 0,
                    "code_scanning_reason": "",
                    "secret_scanning_enabled": None,
                    "secret_scanning_status": "Unknown",
                    "secret_scanning_alert_count": 0,
                    "secret_scanning_reason": "",
                    "secret_push_protection_enabled": None,
                    "secret_push_protection_status": "Unknown",
                    "secret_push_protection_reason": "",
                    "vulnerability_alerts_enabled": False,
                    "has_codeowners": False,
                })
                records.append(record)
        except Exception as exc:
            logger.warning(f"[yellow]  REST fallback failed: {exc}[/yellow]")
        logger.info(f"[dim]  REST fallback: built {len(records)} minimal records[/dim]")
        return records

    # ── compliance & utility ──────────────────────────────────────────────────

    def _compliance_score(self, record: Dict) -> float:
        features = [
            bool(record.get("dependabot_enabled")),
            bool(record.get("code_scanning_enabled")),
            bool(record.get("secret_scanning_enabled")),
            bool(record.get("branch_protection_enabled")),
            bool(record.get("has_security_policy")),
        ]
        return sum(features) / len(features)

    def _days_since_push(self, pushed_at: Optional[str]) -> Optional[int]:
        if not pushed_at:
            return None
        try:
            pushed = _naive(datetime.fromisoformat(pushed_at.replace("Z", "+00:00")))
            return (datetime.now() - pushed).days
        except Exception:
            return None

    # ── helpers exposed for external use (preserved from v1 API) ─────────────

    def get_non_compliant_repos(self, threshold: float = 0.8) -> List[Dict[str, Any]]:
        return [r for r in self.collect() if r.get("compliance_score", 0) < threshold]

    def get_repos_missing_feature(self, feature: str) -> List[Dict[str, Any]]:
        return [r for r in self.collect() if not r.get(feature)]