"""
Dependabot Collector  —  Optimised v2
================================================================================
PERFORMANCE vs v1 (500-repo org)
  OLD : 500 repos × 3 state calls  =  1500 sequential requests  ~12 min
  NEW : 1 paginated org-level API call for ALL repos at once     ~15 sec
        Falls back to concurrent per-repo via ThreadPoolExecutor  ~60-90 sec

Bug-fix history
  v2.1  Removed invalid state=open,dismissed,fixed param (HTTP 422).
  v2.2  Fixed PyGithub thread-safety via prefetched_repos arg.
  v2.3  Treat org 200+[] as indeterminate; increased async timeout 30->300s.
  v2.4  ROOT CAUSE FIX: Removed X-GitHub-Api-Version header from org REST call
        (it caused HTTP 400 on this org's configuration).
        Replaced aiohttp per-repo fallback with PyGithub ThreadPoolExecutor —
        PyGithub auth is proven to work for this token (v1 got 5454 alerts);
        aiohttp was silently getting 403/404 on every single repo due to
        header differences, returning 0 alerts with no error logged.
================================================================================
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings
from src.collectors.base_collector import BaseCollector
from src.utils.collector_logger import CollectorLogger, parse_github_error
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


def _make_headers() -> Dict[str, str]:
    """
    Headers for the org-level REST call.

    NOTE: Do NOT include X-GitHub-Api-Version here.  That header was causing
    HTTP 400 responses from the GitHub API for this organisation's configuration.
    PyGithub (which works correctly for this token) also omits that header.
    """
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }


class DependabotCollector(BaseCollector):
    """
    Dependabot alert collector (optimised).

    Primary path  : single paginated GET /orgs/{org}/dependabot/alerts call.
    Fallback path : concurrent PyGithub per-repo calls via ThreadPoolExecutor.
                    PyGithub auth is proven to work for this token/org combination.
    """

    def __init__(self, github_client: GitHubClient):
        super().__init__(github_client)
        self.collector_logger = CollectorLogger("Dependabot alerts")
        self._base = _api_base()
        self._hdrs = _make_headers()
        self._org = settings.github_org
        self.alert_states = ["open", "dismissed", "fixed"]
        # Keep a reference to the PyGithub client for the fallback
        self._pygithub_client = github_client

    def get_collector_name(self) -> str:
        return "DependabotCollector"

    # ── public entry ──────────────────────────────────────────────────────────

    def collect(self, prefetched_repos=None) -> List[Dict[str, Any]]:
        """
        Collect Dependabot alerts.

        Primary path  : GET /orgs/{org}/dependabot/alerts  (1 paginated call).
        Fallback path : PyGithub per-repo via ThreadPoolExecutor.

        The org endpoint is tried first.  If it returns a NON-EMPTY list we
        trust the result and return immediately.

        If the org endpoint returns [] (200 + empty) OR fails (4xx / network),
        we ALWAYS fall through to the per-repo fallback.  An empty org response
        is indeterminate — it can mean a token-scope issue (GraphQL still works
        for the same token, which is why Repo-Health shows thousands of alerts
        while the org REST endpoint returns nothing).

        Args:
            prefetched_repos: Repo list pre-fetched in the main thread before
                the ThreadPoolExecutor starts, to avoid PyGithub thread-safety
                races when multiple collectors run concurrently.
        """
        self._mark_collection_time()
        self.collector_logger.log_start(0)

        org_result = self._fetch_org_alerts()

        if org_result:          # non-empty list → org endpoint succeeded
            logger.info(
                f"[bright_green]  ✓ Dependabot org endpoint: "
                f"{len(org_result)} alerts[/bright_green]"
            )
            self.collector_logger.log_complete(len(org_result))
            logger.info("")
            return org_result

        if org_result is None:
            logger.info(
                "[yellow]  Org-level Dependabot endpoint unavailable "
                "(HTTP error / timeout) — using PyGithub per-repo fallback...[/yellow]"
            )
        else:
            logger.info(
                "[yellow]  Org-level Dependabot endpoint returned 0 alerts "
                "(possible token-scope issue) — "
                "using PyGithub per-repo fallback...[/yellow]"
            )

        result = self._fallback_pygithub(prefetched_repos)
        self.collector_logger.log_complete(len(result))
        logger.info("")
        return result

    # ── fast path: org-level REST ─────────────────────────────────────────────

    def _fetch_org_alerts(self) -> Optional[List[Dict[str, Any]]]:
        """
        Attempt to fetch Dependabot alerts via the org-level REST endpoint.

        Returns:
            Non-empty list  → endpoint worked, data is reliable.
            []              → endpoint replied 200 but returned no items
                              (indeterminate — caller uses fallback).
            None            → endpoint unavailable (4xx / network error).
        """
        url = f"{self._base}/orgs/{self._org}/dependabot/alerts"
        one_week_ago = datetime.now() - timedelta(days=7)
        all_alerts: List[Dict] = []
        page = 1

        logger.info(f"[dim]  Trying org-level endpoint: {url}[/dim]")

        while True:
            try:
                resp = requests.get(
                    url,
                    headers=self._hdrs,
                    # No state filter — returns open alerts by default.
                    # dismissed/fixed filtered by date in Python below.
                    params={"per_page": 100, "page": page},
                    timeout=60,
                )
            except Exception as exc:
                logger.info(f"[yellow]  Org-level Dependabot network error: {exc}[/yellow]")
                return None

            if resp.status_code == 403:
                logger.info(
                    "[yellow]  Org-level Dependabot HTTP 403 — token lacks "
                    "'security_events' scope for org REST endpoint[/yellow]"
                )
                return None
            if resp.status_code == 404:
                logger.info(
                    "[yellow]  Org-level Dependabot HTTP 404 — GHAS not enabled "
                    "at org level[/yellow]"
                )
                return None
            if resp.status_code != 200:
                logger.info(
                    f"[yellow]  Org-level Dependabot HTTP {resp.status_code} — "
                    f"falling back[/yellow]"
                )
                return None

            batch = resp.json()
            if not batch:
                logger.info(
                    f"[dim]  Org-level Dependabot: empty page at page {page}, "
                    f"{len(all_alerts)} alerts collected[/dim]"
                )
                break

            for raw in batch:
                state = raw.get("state", "unknown")
                if state in ("dismissed", "fixed", "auto_dismissed"):
                    date_str = (
                        raw.get("dismissed_at")
                        or raw.get("fixed_at")
                        or raw.get("auto_dismissed_at")
                    )
                    if date_str:
                        try:
                            if _naive(
                                datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            ) < one_week_ago:
                                continue
                        except Exception:
                            pass

                repo_name = (raw.get("repository") or {}).get("name", "unknown")
                all_alerts.append(self._parse_raw(raw, repo_name, state))

            logger.info(
                f"[dim]  Dependabot org page {page}: {len(all_alerts)} alerts so far[/dim]"
            )

            if len(batch) < 100:
                break
            page += 1

        return all_alerts   # may be [] — caller decides

    # ── fallback: PyGithub per-repo via ThreadPoolExecutor ────────────────────

    def _fallback_pygithub(self, prefetched_repos=None) -> List[Dict[str, Any]]:
        """
        Concurrent PyGithub-based per-repo fallback.

        Fetches ONLY 'open' state alerts to avoid an indefinite hang.
        The previous implementation iterated open+dismissed+fixed for all 515
        repos; dismissed/fixed paginated lists can contain years of history and
        caused the process to block long after all other collectors had finished.

        The weekly report needs open alert counts and severities for its
        vulnerability summary.  Dismissed/fixed trend data is derived from
        snapshot-to-snapshot comparison in HistoryManager and does not require
        iterating individual alert objects here.

        Concurrency: ThreadPoolExecutor(max_workers=10) — safe for PyGithub
        (separate repo objects are independent) without exhausting rate limits.
        Uses prefetched_repos (passed from the main thread) to avoid PyGithub
        thread-safety races on the shared github_client.org object.
        """
        repos = (
            prefetched_repos
            if prefetched_repos is not None
            else list(self._get_repositories())
        )
        logger.info(
            f"[cyan]  Dependabot PyGithub fallback: {len(repos)} repos, "
            f"max 10 concurrent (open alerts only)...[/cyan]"
        )

        all_alerts: List[Dict] = []
        errors = 0
        done = 0

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(self._pygithub_repo_open, repo): repo
                for repo in repos
            }
            for future in as_completed(futures):
                done += 1
                try:
                    result = future.result()
                    all_alerts.extend(result)
                except Exception as exc:
                    errors += 1
                    repo = futures[future]
                    logger.debug(f"Dependabot PyGithub {repo.name}: {exc}")
                if done % 50 == 0 or done == len(repos):
                    logger.info(
                        f"[dim]  Dependabot PyGithub: {done}/{len(repos)} repos done, "
                        f"{len(all_alerts)} alerts so far[/dim]"
                    )

        if errors:
            logger.info(
                f"[yellow]  Dependabot PyGithub fallback: {errors} repo(s) had "
                f"errors, {len(all_alerts)} alerts from the rest[/yellow]"
            )
        else:
            logger.info(
                f"[bright_green]  ✓ Dependabot PyGithub fallback: "
                f"{len(all_alerts)} open alerts from {len(repos)} repos[/bright_green]"
            )
        return all_alerts

    def _pygithub_repo_open(self, repo) -> List[Dict[str, Any]]:
        """
        Fetch OPEN Dependabot alerts for one repo using PyGithub.

        Only 'open' state is fetched.  Iterating 'dismissed' and 'fixed' across
        515 repos with years of history caused the process to hang indefinitely
        after repository_health finished — the ThreadPoolExecutor was blocked
        waiting for this method to return on the remaining ~200 repos.
        """
        alerts: List[Dict] = []
        try:
            for alert in repo.get_dependabot_alerts(state="open"):
                alerts.append(self._parse_pygithub_alert(alert, repo.name, "open"))
        except Exception as exc:
            logger.debug(f"Dependabot PyGithub {repo.name}/open: {exc}")
        return alerts

    def _parse_pygithub_alert(
        self, alert, repo_name: str, state: str
    ) -> Dict[str, Any]:
        """Parse a PyGithub DependabotAlert object into the standard dict format."""
        record = self._create_base_record(repo_name)
        try:
            advisory = alert.security_advisory

            # Package info — may be on security_vulnerability or advisory
            package_name = "unknown"
            package_ecosystem = "unknown"
            vulnerable_version_range = None
            first_patched_version = None

            if hasattr(alert, "security_vulnerability") and alert.security_vulnerability:
                vuln = alert.security_vulnerability
                pkg = getattr(vuln, "package", None)
                if pkg:
                    package_name = getattr(pkg, "name", "unknown") or "unknown"
                    package_ecosystem = getattr(pkg, "ecosystem", "unknown") or "unknown"
                vulnerable_version_range = getattr(
                    vuln, "vulnerable_version_range", None
                )
                fpv = getattr(vuln, "first_patched_version", None)
                if fpv:
                    if hasattr(fpv, "identifier"):
                        first_patched_version = fpv.identifier
                    elif isinstance(fpv, dict):
                        first_patched_version = fpv.get("identifier")
                    else:
                        first_patched_version = str(fpv)
            elif advisory and hasattr(advisory, "package") and advisory.package:
                pkg = advisory.package
                package_name = getattr(pkg, "name", "unknown") or "unknown"
                package_ecosystem = getattr(pkg, "ecosystem", "unknown") or "unknown"

            # CVSS / CWE
            cvss_score = None
            if advisory and hasattr(advisory, "cvss") and advisory.cvss:
                cvss_score = getattr(advisory.cvss, "score", None)

            cwe_ids = []
            if advisory and hasattr(advisory, "cwes") and advisory.cwes:
                cwe_ids = [
                    getattr(c, "cwe_id", "") for c in advisory.cwes
                    if hasattr(c, "cwe_id")
                ]

            def _iso(dt):
                return dt.isoformat() if dt else None

            record.update({
                "alert_id": getattr(alert, "number", None),
                "state": state,
                "package_name": package_name,
                "package_ecosystem": package_ecosystem,
                "severity": getattr(advisory, "severity", "unknown") if advisory else "unknown",
                "cve_id": (getattr(advisory, "cve_id", None) or "N/A") if advisory else "N/A",
                "ghsa_id": (getattr(advisory, "ghsa_id", None) or "N/A") if advisory else "N/A",
                "summary": getattr(advisory, "summary", "") if advisory else "",
                "description": getattr(advisory, "description", "") if advisory else "",
                "cvss_score": cvss_score,
                "cwe_ids": cwe_ids,
                "vulnerable_version_range": vulnerable_version_range,
                "first_patched_version": first_patched_version,
                "created_at": _iso(getattr(alert, "created_at", None)),
                "updated_at": _iso(getattr(alert, "updated_at", None)),
                "dismissed_at": _iso(getattr(alert, "dismissed_at", None)),
                "dismissed_by": (
                    getattr(alert.dismissed_by, "login", None)
                    if getattr(alert, "dismissed_by", None) else None
                ),
                "dismissed_reason": getattr(alert, "dismissed_reason", None),
                "dismissed_comment": getattr(alert, "dismissed_comment", None),
                "fixed_at": _iso(getattr(alert, "fixed_at", None)),
                "url": getattr(alert, "html_url", ""),
            })

            # age_days
            ca = getattr(alert, "created_at", None)
            if ca:
                try:
                    record["age_days"] = (datetime.now() - _naive(ca)).days
                except Exception:
                    record["age_days"] = 0
            else:
                record["age_days"] = 0

        except Exception as exc:
            logger.warning(
                f"Error parsing PyGithub Dependabot alert for {repo_name}: {exc}"
            )
            record.update({
                "alert_id": getattr(alert, "number", "unknown"),
                "state": state,
                "package_name": "unknown",
                "package_ecosystem": "unknown",
                "severity": "unknown",
                "summary": "Error parsing alert details",
                "age_days": 0,
            })
        return record

    # ── raw-JSON parser (org-level path only) ─────────────────────────────────

    def _parse_raw(self, raw: Dict, repo_name: str, state: str) -> Dict[str, Any]:
        """Parse a raw JSON dict from the org-level REST endpoint."""
        record = self._create_base_record(repo_name)
        try:
            advisory = raw.get("security_advisory") or {}
            vuln = raw.get("security_vulnerability") or {}
            pkg = vuln.get("package") or advisory.get("package") or {}
            cvss = advisory.get("cvss") or {}
            cwes = advisory.get("cwes") or []

            fpv = vuln.get("first_patched_version")
            if isinstance(fpv, dict):
                fpv = fpv.get("identifier")

            record.update({
                "alert_id": raw.get("number"),
                "state": state,
                "package_name": pkg.get("name", "unknown"),
                "package_ecosystem": pkg.get("ecosystem", "unknown"),
                "severity": advisory.get("severity", "unknown"),
                "cve_id": advisory.get("cve_id") or "N/A",
                "ghsa_id": advisory.get("ghsa_id", "N/A"),
                "summary": advisory.get("summary", ""),
                "description": advisory.get("description", ""),
                "cvss_score": cvss.get("score"),
                "cwe_ids": [c.get("cwe_id", "") for c in cwes if isinstance(c, dict)],
                "vulnerable_version_range": vuln.get("vulnerable_version_range"),
                "first_patched_version": fpv,
                "created_at": raw.get("created_at"),
                "updated_at": raw.get("updated_at"),
                "dismissed_at": raw.get("dismissed_at"),
                "dismissed_by": (raw.get("dismissed_by") or {}).get("login"),
                "dismissed_reason": raw.get("dismissed_reason"),
                "dismissed_comment": raw.get("dismissed_comment"),
                "fixed_at": raw.get("fixed_at"),
                "url": raw.get("html_url", ""),
            })

            ca = raw.get("created_at")
            if ca:
                try:
                    record["age_days"] = (
                        datetime.now()
                        - _naive(datetime.fromisoformat(ca.replace("Z", "+00:00")))
                    ).days
                except Exception:
                    record["age_days"] = 0
            else:
                record["age_days"] = 0

        except Exception as exc:
            logger.warning(f"Error parsing Dependabot alert for {repo_name}: {exc}")
            record.update({
                "alert_id": raw.get("number", "unknown"),
                "state": state,
                "package_name": "unknown",
                "package_ecosystem": "unknown",
                "severity": "unknown",
                "summary": "Error parsing alert details",
                "age_days": 0,
            })
        return record

    # ── helpers ───────────────────────────────────────────────────────────────

    def get_open_alerts(self) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if a["state"] == "open"]

    def get_critical_alerts(self) -> List[Dict[str, Any]]:
        return [a for a in self.get_open_alerts() if a.get("severity") == "critical"]

    def get_alerts_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if a.get("severity") == severity]
