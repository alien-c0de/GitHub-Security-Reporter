"""
Secret Scanning Collector  —  Optimised v2
════════════════════════════════════════════════════════════════════════════════
PERFORMANCE vs v1 (500-repo org)
  ❌ OLD : 500 repos × 2 state REST calls  =  1 000 sequential requests  ~8 min
  ✅ NEW : 1 paginated org-level API call for ALL repos at once           ~15 sec

Strategy
  1. GET /orgs/{org}/secret-scanning/alerts  — all alerts across all repos.
  2. Filter resolved alerts to last 7 days in Python.
  3. Concurrent async per-repo fallback (GHAS required) if org endpoint fails.
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


class SecretScanningCollector(BaseCollector):
    """
    Secret Scanning alert collector (optimised).

    Primary path  : /orgs/{org}/secret-scanning/alerts  (one paginated call).
    Fallback path : concurrent async per-repo calls.
    """

    def __init__(self, github_client: GitHubClient):
        super().__init__(github_client)
        self.collector_logger = CollectorLogger("Secret Scanning alerts")
        self._base = _api_base()
        self._hdrs = _make_headers()
        self._org = settings.github_org
        # kept for fallback
        self.alert_states = ["open", "resolved"]
        self.token = settings.github_token
        self.base_url = self._base

    def get_collector_name(self) -> str:
        return "SecretScanningCollector"

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
            "[yellow]  Org-level Secret Scanning endpoint unavailable — "
            "falling back to per-repo concurrent calls...[/yellow]"
        )
        result = self._fallback_per_repo()
        self.collector_logger.log_complete(len(result))
        logger.info("")
        return result

    # ── fast path: org-level ──────────────────────────────────────────────────

    def _fetch_org_alerts(self) -> Optional[List[Dict[str, Any]]]:
        url = f"{self._base}/orgs/{self._org}/secret-scanning/alerts"
        one_week_ago = datetime.now() - timedelta(days=7)
        all_alerts: List[Dict] = []

        for state in ("open", "resolved"):
            page = 1
            while True:
                try:
                    resp = requests.get(
                        url,
                        headers=self._hdrs,
                        params={"state": state, "per_page": 100, "page": page},
                        timeout=60,
                    )
                except Exception as exc:
                    logger.debug(f"Secret scanning org request error: {exc}")
                    return None

                if resp.status_code == 404:
                    logger.debug("Secret scanning org endpoint 404 — GHAS not enabled or wrong URL.")
                    return None
                if resp.status_code == 403:
                    logger.debug("Secret scanning org endpoint 403 — missing permission.")
                    return None
                if resp.status_code != 200:
                    logger.debug(f"Secret scanning org endpoint HTTP {resp.status_code}")
                    break   # try next state

                batch = resp.json()
                if not batch:
                    break

                for raw in batch:
                    if state == "resolved":
                        rs = raw.get("resolved_at")
                        if rs:
                            try:
                                if _naive(datetime.fromisoformat(rs.replace("Z", "+00:00"))) < one_week_ago:
                                    continue
                            except Exception:
                                pass
                    repo_name = (raw.get("repository") or {}).get("name", "unknown")
                    all_alerts.append(self._parse_raw(raw, repo_name, state))

                logger.info(f"[dim]  Secret Scanning org page {page} ({state}): {len(all_alerts)} total[/dim]")

                if len(batch) < 100:
                    break
                page += 1

        logger.info(f"[bright_green]  ✓ Secret Scanning batch fetch: {len(all_alerts)} alerts[/bright_green]")
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
        """Fetch Secret Scanning alerts for a single repo with full pagination."""
        alerts: List[Dict] = []
        for state in self.alert_states:
            url = f"{self._base}/repos/{self._org}/{repo.name}/secret-scanning/alerts"
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
                            if state == "resolved":
                                rs = raw.get("resolved_at")
                                if rs:
                                    try:
                                        if _naive(datetime.fromisoformat(
                                            rs.replace("Z", "+00:00")
                                        )) < one_week_ago:
                                            continue
                                    except Exception:
                                        pass
                            alerts.append(self._parse_raw(raw, repo.name, state))
                        if len(batch) < 100:
                            break   # last page
                        page += 1
                except Exception as exc:
                    logger.debug(f"Secret scanning async {repo.name}/{state} page {page}: {exc}")
                    break
        return alerts

    # ── parser ────────────────────────────────────────────────────────────────

    def _parse_raw(self, raw: Dict, repo_name: str, state: str) -> Dict[str, Any]:
        record = self._create_base_record(repo_name)
        record.update({
            "alert_number": raw.get("number"),
            "state": state,
            "secret_type": raw.get("secret_type"),
            "secret_type_display_name": raw.get("secret_type_display_name"),
            "secret": raw.get("secret"),
            "resolution": raw.get("resolution"),
            "resolved_by": (raw.get("resolved_by") or {}).get("login"),
            "resolved_at": raw.get("resolved_at"),
            "resolution_comment": raw.get("resolution_comment"),
            "push_protection_bypassed": raw.get("push_protection_bypassed", False),
            "push_protection_bypassed_by": (raw.get("push_protection_bypassed_by") or {}).get("login"),
            "push_protection_bypassed_at": raw.get("push_protection_bypassed_at"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "url": raw.get("html_url"),
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

        return record

    # ── helpers ───────────────────────────────────────────────────────────────

    def get_exposed_secrets(self) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if a["state"] == "open"]

    def get_bypassed_secrets(self) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if a.get("push_protection_bypassed")]

    def get_secrets_by_type(self, secret_type: str) -> List[Dict[str, Any]]:
        return [a for a in self.collect() if a.get("secret_type") == secret_type]
