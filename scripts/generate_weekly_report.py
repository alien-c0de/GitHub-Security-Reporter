"""
Generate weekly security report  —  Optimised v2
════════════════════════════════════════════════════════════════════════════════
PERFORMANCE vs v1 (500-repo org)
  ❌ OLD : collectors run sequentially:
           OrganisationCollector  → wait → DependabotCollector  → wait →
           CodeScanningCollector  → wait → SecretScanningCollector → wait →
           SupplyChainCollector   → wait → RepositoryHealthCollector
           Total wall-clock time: ~18+ min

  ✅ NEW : independent collectors run in parallel threads:
           DependabotCollector ─┐
           CodeScanningCollector─┤ all start at the same time
           SecretScanningCollector┤
           SupplyChainCollector ─┤
           RepositoryHealthCollector┘
           Total wall-clock time: max(slowest collector) ≈ 3–5 min

  The OrganisationCollector is still run first (small, needed by others).
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from src.analyzers.metrics_calculator import MetricsCalculator
from src.analyzers.trend_analyzer import TrendAnalyzer
from src.collectors.code_scanning_collector import CodeScanningCollector
from src.collectors.dependabot_collector import DependabotCollector
from src.collectors.organization_collector import OrganizationCollector
from src.collectors.repository_health_collector import RepositoryHealthCollector
from src.collectors.secret_scanning_collector import SecretScanningCollector
from src.collectors.supply_chain_collector import SupplyChainCollector
from src.reporters.excel_reporter import ExcelReporter
from src.storage.data_store import DataStore
from src.storage.history_manager import HistoryManager
from src.utils.github_client import GitHubClient
from src.utils.logger import setup_logger, log_footer

logger = setup_logger()


def _fmt(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}m {s}s" if m else f"{s}s"


# ── parallel collection ───────────────────────────────────────────────────────

def _run_collector(label: str, collector_fn, *args):
    """Run a single collector, returning (label, result, error, elapsed)."""
    t0 = time.time()
    try:
        result = collector_fn(*args)
        return label, result, None, time.time() - t0
    except Exception as exc:
        return label, None, exc, time.time() - t0


def collect_all_data(github_client: GitHubClient) -> dict:
    """
    Collect all security data.

    OrganisationCollector runs first (fast, ~1 s).
    Repositories are fetched once in the main thread — PyGithub is not
    thread-safe, so fetching inside multiple concurrent threads risks race
    conditions on the shared client object.
    All remaining collectors run concurrently in a thread pool, receiving
    the pre-fetched repo list so they never need to call PyGithub themselves.
    """
    logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
    logger.info("[bright_cyan]Starting weekly data collection  (v2 — parallel)[/bright_cyan]")
    logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")

    snapshot: dict = {
        "timestamp": datetime.now().isoformat(),
        "week_number": datetime.now().isocalendar()[1],
        "year": datetime.now().year,
        "organization": settings.github_org,
    }

    # ── Step 1: Organisation info (sequential — small, fast) ─────────────────
    org_collector = OrganizationCollector(github_client)
    snapshot["organization_info"] = org_collector.collect()

    # ── Step 2: Pre-fetch repositories ONCE in the main thread ───────────────
    # PyGithub's internal Requester is NOT thread-safe.  Fetching repos here
    # (before the ThreadPoolExecutor starts) means no collector needs to call
    # _get_repositories() from inside a worker thread, eliminating race
    # conditions on the shared github_client.
    logger.info("[cyan]  Fetching repository list (main thread)...[/cyan]")
    try:
        prefetched_repos = [r for r in github_client.org.get_repos() if not r.archived]
        logger.info(
            f"[bright_green]  ✓ {len(prefetched_repos)} repositories fetched[/bright_green]"
        )
    except Exception as exc:
        logger.warning(f"[yellow]  Could not pre-fetch repos: {exc} — collectors will fetch individually[/yellow]")
        prefetched_repos = None

    # ── Step 3: All remaining collectors in parallel ──────────────────────────
    logger.info("[cyan]  Launching all collectors in parallel...[/cyan]")

    # Build list of (label, enabled_flag, collector_class)
    collector_config = [
        ("dependabot",        settings.enable_dependabot,      DependabotCollector),
        ("code_scanning",     settings.enable_code_scanning,    CodeScanningCollector),
        ("secret_scanning",   settings.enable_secret_scanning,  SecretScanningCollector),
        ("supply_chain",      settings.enable_supply_chain,     SupplyChainCollector),
        ("repository_health", True,                             RepositoryHealthCollector),
    ]

    enabled = [(label, cls) for label, flag, cls in collector_config if flag]

    def _run_with_repos(label: str, cls, repos):
        """Run a collector, passing pre-fetched repos when the collector accepts them."""
        import inspect
        instance = cls(github_client)
        sig = inspect.signature(instance.collect)
        if "prefetched_repos" in sig.parameters and repos is not None:
            return _run_collector(label, instance.collect, repos)
        return _run_collector(label, instance.collect)

    # Each collector gets its own instance (they are not thread-safe to share)
    with ThreadPoolExecutor(max_workers=len(enabled)) as pool:
        futures = {
            pool.submit(_run_with_repos, label, cls, prefetched_repos): label
            for label, cls in enabled
        }

        for future in as_completed(futures):
            label, result, error, elapsed = future.result()
            if error:
                logger.error(
                    f"[red]  ✗ {label} collector failed after {_fmt(elapsed)}: {error}[/red]"
                )
            else:
                count = len(result) if isinstance(result, list) else (
                    len(result.get("repositories", [])) if isinstance(result, dict) else "?"
                )
                logger.info(
                    f"[bright_green]  ✓ {label}: {count} records  ({_fmt(elapsed)})[/bright_green]"
                )
                snapshot[label] = result

    logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
    logger.info("[bright_cyan]Data collection completed[/bright_cyan]")
    logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
    logger.info("")
    return snapshot


# ── analysis & reporting (unchanged from v1) ─────────────────────────────────

def analyze_data(snapshot: dict, history_manager: HistoryManager) -> tuple:
    logger.info("[cyan]  Analysing data and calculating metrics...[/cyan]")

    calculator = MetricsCalculator()
    metrics = calculator.calculate_all_metrics(snapshot)
    logger.info("[bright_green][✓] Metrics calculated[/bright_green]")

    trends = None
    comparison = history_manager.get_weekly_comparison()
    if comparison:
        logger.info("[cyan]  Analysing trends...[/cyan]")
        trend_analyzer = TrendAnalyzer()
        previous_metrics = calculator.calculate_all_metrics(comparison["previous_week"])
        trends = trend_analyzer.analyze_week_over_week(metrics, previous_metrics)
        logger.info("[bright_green][✓] Trends analysed[/bright_green]")
    else:
        logger.info("[yellow][!] No historical data available for trend analysis[/yellow]")

    return metrics, trends


def generate_reports(snapshot: dict, metrics: dict, trends: dict | None = None):
    excel_reporter = ExcelReporter()
    return excel_reporter.generate_report(snapshot, metrics, trends)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    overall_start = time.time()

    try:
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]GitHub Advanced Security  —  Weekly Report Generator  v2[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info(f"[cyan]Organization:[/cyan] {settings.github_org}")
        logger.info(f"[cyan]Date:[/cyan]         {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # Connect
        logger.info("[yellow]Connecting to GitHub...[/yellow]")
        t0 = time.time()
        github_client = GitHubClient()
        connection_time = time.time() - t0
        logger.info("")

        data_store = DataStore()
        history_manager = HistoryManager(data_store)

        # Collect (parallel)
        t0 = time.time()
        snapshot = collect_all_data(github_client)
        collection_time = time.time() - t0

        # Save snapshot
        logger.info("[cyan]  Saving snapshot...[/cyan]")
        data_store.save_json(
            snapshot,
            f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            subdir="snapshots",
        )
        history_manager.save_snapshot(snapshot)
        logger.info("[bright_yellow][+] Snapshot saved to history[/bright_yellow]")

        # Analyse
        t0 = time.time()
        metrics, trends = analyze_data(snapshot, history_manager)
        analysis_time = time.time() - t0

        # Report
        t0 = time.time()
        report_file = generate_reports(snapshot, metrics, trends)
        report_time = time.time() - t0

        total_time = time.time() - overall_start

        # ── Summary ───────────────────────────────────────────────────────────
        summary = metrics.get("summary", {})
        logger.info("")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("[bright_magenta]WEEKLY REPORT SUMMARY[/bright_magenta]")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info(f"[white]Total Vulnerabilities:[/white] {summary.get('total_vulnerabilities', 0)}")
        logger.info(f"  [red]- Critical:[/red] {summary.get('critical_count', 0)}")
        logger.info(f"  [yellow]- High:[/yellow]    {summary.get('high_count', 0)}")
        logger.info(f"  [cyan]- Medium:[/cyan]   {summary.get('medium_count', 0)}")
        logger.info(f"  [green]- Low:[/green]     {summary.get('low_count', 0)}")
        logger.info(f"[magenta]Exposed Secrets:[/magenta]       {summary.get('exposed_secrets', 0)}")
        logger.info(f"[green]Closed This Week:[/green]       {summary.get('vulnerabilities_closed_this_week', 0)}")
        logger.info(f"[blue]Health Score:[/blue]           {summary.get('overall_health_score', 0):.1f}%")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info(f"[bright_green]Report:[/bright_green] {report_file}")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")

        # ── Timing breakdown ──────────────────────────────────────────────────
        other = total_time - connection_time - collection_time - analysis_time - report_time
        logger.info("")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]EXECUTION TIME BREAKDOWN[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info(f"[white]Connection time:         [/white] {_fmt(connection_time)}")
        logger.info(f"[white]Data collection (parallel):[/white] {_fmt(collection_time)}")
        logger.info(f"[white]Data analysis:           [/white] {_fmt(analysis_time)}")
        logger.info(f"[white]Report generation:       [/white] {_fmt(report_time)}")
        logger.info(f"[white]Other operations:        [/white] {_fmt(max(other, 0))}")
        logger.info("[bright_cyan]" + "-" * 100 + "[/bright_cyan]")
        logger.info(
            f"[bright_yellow]TOTAL EXECUTION TIME:[/bright_yellow]  "
            f"{_fmt(total_time)} ({total_time/60:.2f} min)"
        )
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("")

        github_client.close()

        log_footer(logger)
        return 0

    except Exception as exc:
        total_time = time.time() - overall_start
        logger.error(f"[ERROR] Error generating weekly report: {exc}", exc_info=True)
        logger.error(f"[red]Failed after {_fmt(total_time)} ({total_time/60:.2f} min)[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
