"""
Generate organization and repository data report for ALL organizations in enterprise
Uses async processing for better performance with hundreds of organizations
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime
import time

from src.utils.logger import setup_logger, log_footer
from src.utils.github_client import GitHubClient
from src.collectors.async_organization_data_collector import AsyncOrganizationDataCollector
from src.reporters.organization_data_reporter import OrganizationDataReporter
from config.settings import settings

logger = setup_logger()

def format_duration(seconds: float) -> str:
    """Format duration in human-readable way"""
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    
    if minutes > 0:
        return f"{minutes}m {remaining_seconds}s"
    else:
        return f"{remaining_seconds}s"

def generate_organization_report():
    """Generate organization and repository data report for entire enterprise"""
    overall_start_time = time.time()
    
    try:
        logger.info("[bright_blue]" + "=" * 100 + "[/bright_blue]")
        logger.info("[bright_blue]GitHub Enterprise - Complete Organization & Repository Inventory[/bright_blue]")
        logger.info("[bright_blue]" + "=" * 100 + "[/bright_blue]")
        logger.info("")
        
        # Connect to GitHub
        logger.info("[yellow]Connecting to GitHub Enterprise...[/yellow]")
        connection_start = time.time()
        github_client = GitHubClient()
        connection_time = time.time() - connection_start
        # logger.info(f"[OK] Connected ({format_duration(connection_time)})")
        logger.info("")
        
        # Collect ALL organization and repository data using async processing
        collection_start = time.time()
        
        # Use 10 parallel workers for faster processing
        # Adjust this number based on your API rate limits
        max_workers = 10
        
        logger.info(f"[cyan]Using {max_workers} parallel workers for faster collection[/cyan]")
        logger.info("")
        
        collector = AsyncOrganizationDataCollector(github_client, max_workers=max_workers)
        org_data = collector.collect()
        
        collection_time = time.time() - collection_start
        
        # Display enterprise-wide summary
        logger.info("")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("[bright_magenta]ENTERPRISE-WIDE SUMMARY[/bright_magenta]")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        
        # Get summary statistics
        summary = collector.get_summary_statistics(org_data)
        
        logger.info(f"[bright_cyan]Total Organizations:[/bright_cyan] {summary['total_organizations']}")
        logger.info(f"[bright_cyan]Total Repositories:[/bright_cyan] {summary['total_repositories']}")
        logger.info(f"[cyan]Total Size:[/cyan] {summary['total_size_mb']:.2f} MB")
        logger.info(f"[cyan]Total Stars:[/cyan] {summary['total_stars']:,}")
        logger.info(f"[cyan]Total Forks:[/cyan] {summary['total_forks']:,}")
        logger.info("")
        
        logger.info("[bright_green]Repository Distribution:[/bright_green]")
        logger.info(f"  [green]• Active:[/green] {summary['by_status']['active']:,}")
        logger.info(f"  [yellow]• Archived:[/yellow] {summary['by_status']['archived']:,}")
        logger.info("")
        
        logger.info("[bright_blue]Visibility Distribution:[/bright_blue]")
        logger.info(f"  [blue]• Public:[/blue] {summary['by_visibility']['public']:,}")
        logger.info(f"  [magenta]• Private:[/magenta] {summary['by_visibility']['private']:,}")
        logger.info(f"  [cyan]• Internal:[/cyan] {summary['by_visibility']['internal']:,}")
        logger.info("")
        
        # Top languages
        if summary['by_language']:
            logger.info("[bright_yellow]Top 10 Languages Across Enterprise:[/bright_yellow]")
            for i, (lang, count) in enumerate(list(summary['by_language'].items())[:10], 1):
                logger.info(f"  {i}. {lang}: {count:,} repositories")
            logger.info("")
        
        # Top organizations by repo count
        if summary['top_organizations_by_repo_count']:
            logger.info("[bright_cyan]Top 10 Organizations by Repository Count:[/bright_cyan]")
            for i, (org, count) in enumerate(summary['top_organizations_by_repo_count'][:10], 1):
                logger.info(f"  {i}. {org}: {count:,} repositories")
            logger.info("")
        
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("")
        
        # Generate Excel report
        logger.info("[cyan]Generating comprehensive Excel report...[/cyan]")
        logger.info("[dim]Note: This may take a few minutes for large datasets[/dim]")
        logger.info("")
        
        report_start = time.time()
        
        reporter = OrganizationDataReporter()
        filename = reporter.generate_report(org_data)
        
        report_time = time.time() - report_start
        
        logger.info(f"[OK] Report generated ({format_duration(report_time)})")
        logger.info("")
        logger.info(f"[bright_green]📊 Report location:[/bright_green] {filename}")
        logger.info("")
        
        # Display what's in the report
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("[bright_magenta]EXCEL REPORT CONTENTS[/bright_magenta]")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("[white]Sheet 1:[/white] [cyan]Overview[/cyan] - Executive summary and enterprise statistics")
        logger.info(f"[white]Sheet 2:[/white] [cyan]All Repositories[/cyan] - {summary['total_repositories']:,} repositories with complete details")
        logger.info(f"[white]Sheet 3:[/white] [cyan]Organization Summary[/cyan] - {summary['total_organizations']} organizations with metrics")
        logger.info("[white]Sheet 4:[/white] [cyan]Pivot Analysis[/cyan] - Statistical breakdowns and top 10 rankings")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("")
        
        # Calculate total time
        total_time = time.time() - overall_start_time
        total_minutes = total_time / 60
        
        # Performance metrics
        if summary['total_repositories'] > 0:
            repos_per_second = summary['total_repositories'] / collection_time
            logger.info("[bright_cyan]Performance Metrics:[/bright_cyan]")
            logger.info(f"[cyan]Processing Speed:[/cyan] {repos_per_second:.2f} repositories/second")
            logger.info(f"[cyan]Average per Organization:[/cyan] {collection_time/summary['total_organizations']:.2f} seconds")
            logger.info("")
        
        # Execution time summary
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]EXECUTION TIME[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info(f"[white]Connection:[/white]        {format_duration(connection_time)}")
        logger.info(f"[white]Data Collection:[/white]  {format_duration(collection_time)}")
        logger.info(f"[white]Report Generation:[/white] {format_duration(report_time)}")
        logger.info("[bright_cyan]" + "-" * 100 + "[/bright_cyan]")
        logger.info(f"[bright_yellow]TOTAL TIME:[/bright_yellow]        {format_duration(total_time)} ({total_minutes:.2f} minutes)")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("")
        
        # Performance tip
        if summary['total_organizations'] > 100:
            logger.info("[bright_yellow]💡 Tip:[/bright_yellow] For {summary['total_organizations']} organizations, async processing saved significant time!")
            logger.info("")
        
        github_client.close()
        
        logger.info("[bright_green][✓] Enterprise organization inventory completed successfully[/bright_green]")
        logger.info("")
        
        # Summary box
        logger.info("[bright_blue]" + "=" * 100 + "[/bright_blue]")
        logger.info(f"[bright_blue]✓ Collected: {summary['total_organizations']} organizations, {summary['total_repositories']:,} repositories[/bright_blue]")
        logger.info(f"[bright_blue]✓ Report: {filename.name}[/bright_blue]")
        logger.info(f"[bright_blue]✓ Time: {format_duration(total_time)}[/bright_blue]")
        logger.info("[bright_blue]" + "=" * 100 + "[/bright_blue]")
        logger.info("")

        log_footer(logger)
        
        return 0
        
    except Exception as e:
        total_time = time.time() - overall_start_time
        total_minutes = total_time / 60
        logger.error(f"[ERROR] Error generating organization report: {e}", exc_info=True)
        logger.error(f"[red]Failed after {format_duration(total_time)} ({total_minutes:.2f} minutes)[/red]")
        return 1

if __name__ == "__main__":
    sys.exit(generate_organization_report())