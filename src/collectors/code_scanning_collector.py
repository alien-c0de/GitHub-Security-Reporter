"""
Code Scanning Collector  —  Optimised v2
════════════════════════════════════════════════════════════════════════════════
PERFORMANCE vs v1 (500-repo org)
  ❌ OLD : 500 repos × sequential PyGithub REST calls  ~8–12 min
  ✅ NEW : 1 paginated org-level API call for ALL repos at once  ~20 sec

Strategy
  1. GET /orgs/{org}/code-scanning/alerts   — all alerts across all repos.
  2. Filter dismissed/fixed to last 7 days in Python.
  3. Concurrent async per-repo fallback if org endpoint returns 404/403.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
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
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class CodeScanningCollector(BaseCollector):
    """
    Code Scanning (SAST) alert collector (optimised).

    Primary path  : /orgs/{org}/code-scanning/alerts  (one paginated call).
    Fallback path : concurrent async per-repo calls.
    """

    def __init__(self, github_client: GitHubClient):
        super().__init__(github_client)
        self.collector_logger = CollectorLogger("Code Scanning alerts")
        self._base = _api_base()
        self._hdrs = _make_headers()
        self._org = settings.github_org

    def get_collector_name(self) -> str:
        return "CodeScanningCollector"

    # ── public entry ──────────────────────────────────────────────────────────

    def collect(self) -> List[Dict[str, Any]]:
        self._mark_collection_time()
        self.collector_logger.log_start(0)

        result = self._fetch_org_alerts()
        if result is not None:
            self.collector_logger.log_complete(len(result))
            logger.info("")
            return result

        logger.info(
            "[yellow]  Org-level Code Scanning endpoint unavailable — "
            "falling back to per-repo concurrent calls...[/yellow]"
        )
        result = self._fallback_per_repo()
        self.collector_logger.log_complete(len(result))
        logger.info("")
        return result

    # ── fast path: org-level ──────────────────────────────────────────────────

    def _fetch_org_alerts(self) -> Optional[List[Dict[str, Any]]]:
        url = f"{self._base}/orgs/{self._org}/code-scanning/alerts"
        one_week_ago = datetime.now() - timedelta(days=7)
        all_alerts: List[Dict] = []
        page = 1

        while True:
            try:
                resp = requests.get(
                    url,
                    headers=self._hdrs,
                    # Fetch open + dismissed; "fixed" not supported on the filter param,
                    # so we fetch "open" first, then "dismissed" in a second pass below.
                    params={"state": "open", "per_page": 100, "page": page},
                    timeout=60,
                )
            except Exception as exc:
                logger.debug(f"Code scanning org request error: {exc}")
                return None

            if resp.status_code in (403, 404):
                logger.debug(f"Code scanning org endpoint HTTP {resp.status_code}")
                return None
            if resp.status_code != 200:
                logger.debug(f"Code scanning org endpoint HTTP {resp.status_code}")
                return None

            batch = resp.json()
            if not batch:
                break

            for raw in batch:
                repo_name = (raw.get("repository") or {}).get("name", "unknown")
                all_alerts.append(self._parse_raw(raw, repo_name, "open"))

            logger.info(f"[dim]  Code Scanning org page {page} (open): {len(all_alerts)} total[/dim]")

            if len(batch) < 100:
                break
            page += 1

        # Also fetch dismissed alerts (limited to last 7 days)
        page = 1
        while True:
            try:
                resp = requests.get(
                    url,
                    headers=self._hdrs,
                    params={"state": "dismissed", "per_page": 100, "page": page},
                    timeout=60,
                )
            except Exception:
                break

            if resp.status_code != 200:
                break

            batch = resp.json()
            if not batch:
                break

            for raw in batch:
                ds = raw.get("dismissed_at")
                if ds:
                    try:
                        if _naive(datetime.fromisoformat(ds.replace("Z", "+00:00"))) < one_week_ago:
                            continue
                    except Exception:
                        pass
                repo_name = (raw.get("repository") or {}).get("name", "unknown")
                all_alerts.append(self._parse_raw(raw, repo_name, "dismissed"))

            if len(batch) < 100:
                break
            page += 1

        logger.info(f"[bright_green]  ✓ Code Scanning batch fetch: {len(all_alerts)} alerts[/bright_green]")
        return all_alerts

    # ── fallback: async per-repo ──────────────────────────────────────────────

    def _fallback_per_repo(self) -> List[Dict[str, Any]]:
        repos = list(self._get_repositories())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._async_all(repos))
        finally:
            loop.close()

    async def _async_all(self, repos) -> List[Dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(limit=20, ssl=False)
        one_week_ago = datetime.now() - timedelta(days=7)

        async with aiohttp.ClientSession(headers=self._hdrs, timeout=timeout, connector=connector) as session:
            tasks = [self._async_repo(session, repo, one_week_ago) for repo in repos]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_alerts: List[Dict] = []
        for r in results:
            if isinstance(r, list):
                all_alerts.extend(r)
        return all_alerts

    async def _async_repo(self, session, repo, one_week_ago) -> List[Dict]:
        """Fetch Code Scanning alerts for a single repo with full pagination."""
        alerts: List[Dict] = []
        url = f"{self._base}/repos/{self._org}/{repo.name}/code-scanning/alerts"

        for state in ("open", "dismissed"):
            page = 1
            while True:   # ← paginate through ALL pages
                try:
                    async with session.get(
                        url, params={"state": state, "per_page": 100, "page": page}
                    ) as resp:
                        if resp.status in (403, 404):
                            return alerts   # feature not enabled
                        if resp.status != 200:
                            break
                        batch = await resp.json()
                        if not batch:
                            break
                        for raw in batch:
                            if state == "dismissed":
                                ds = raw.get("dismissed_at")
                                if ds:
                                    try:
                                        if _naive(datetime.fromisoformat(
                                            ds.replace("Z", "+00:00")
                                        )) < one_week_ago:
                                            continue
                                    except Exception:
                                        pass
                            alerts.append(self._parse_raw(raw, repo.name, state))
                        if len(batch) < 100:
                            break   # last page
                        page += 1
                except Exception as exc:
                    logger.debug(f"Code scanning async {repo.name}/{state} page {page}: {exc}")
                    break
        return alerts

    # ── parser ────────────────────────────────────────────────────────────────

    def _parse_raw(self, raw: Dict, repo_name: str, state: str) -> Dict[str, Any]:
        record = self._create_base_record(repo_name)
        try:
            rule = raw.get("rule") or {}
            tool = raw.get("tool") or {}
            most_recent = raw.get("most_recent_instance") or {}
            location = most_recent.get("location") or {}
            message = most_recent.get("message") or {}
            msg_text = message.get("text") if isinstance(message, dict) else str(message) if message else None

            tags = rule.get("tags") or []
            cwe_ids = [t.replace("external/cwe/cwe-", "CWE-") for t in tags if "cwe" in t.lower()]

            record.update({
                "alert_number": raw.get("number"),
                "state": state,
                "rule_id": rule.get("id", "unknown"),
                "rule_name": rule.get("name") or rule.get("id", "unknown"),
                "rule_description": rule.get("description", ""),
                "rule_severity": rule.get("severity", "unknown"),
                "security_severity_level": rule.get("security_severity_level"),
                "rule_tags": tags,
                "tool_name": tool.get("name", "unknown"),
                "tool_version": tool.get("version"),
                "cwe_ids": cwe_ids,
                "file_path": location.get("path"),
                "start_line": location.get("start_line"),
                "end_line": location.get("end_line"),
                "start_column": location.get("start_column"),
                "end_column": location.get("end_column"),
                "message": msg_text,
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
                        datetime.now() - _naive(datetime.fromisoformat(ca.replace("Z", "+00:00")))
                    ).days
                except Exception:
                    record["age_days"] = 0
            else:
                record["age_days"] = 0

        except Exception as exc:
            logger.warning(f"Error parsing Code Scanning alert for {repo_name}: {exc}")
            record.update({
                "alert_number": raw.get("number", "unknown"),
                "state": state,
                "rule_description": "Error parsing alert",
                "age_days": 0,
            })
        return record

    # ── helpers ───────────────────────────────────────────────────────────────

    def get_alerts_by_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if a.get("tool_name") == tool_name]

    def get_alerts_by_cwe(self, cwe_id: str) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if cwe_id in a.get("cwe_ids", [])]
