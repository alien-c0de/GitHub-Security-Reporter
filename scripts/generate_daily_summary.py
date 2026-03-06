"""
Generate daily security summary with professional Excel report
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime
import time

from src.utils.logger import setup_logger, log_footer
from src.utils.github_client import GitHubClient
from src.collectors.dependabot_collector import DependabotCollector
from src.collectors.code_scanning_collector import CodeScanningCollector
from src.collectors.secret_scanning_collector import SecretScanningCollector
from src.reporters.daily_excel_reporter import DailyExcelReporter
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

def generate_daily_summary():
    """Generate daily summary of critical items with professional Excel report"""
    overall_start_time = time.time()
    
    try:

        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]GitHub Advanced Security - Daily Report Generator[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info(f"[cyan]Organization:[/cyan] {settings.github_org}")
        logger.info(f"[cyan]Date:[/cyan] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")

        # logger.info("[bright_blue]" + "=" * 100 + "[/bright_blue]")
        # logger.info("[bright_blue]GitHub Advanced Security - Daily Summary[/bright_blue]")
        # logger.info("[bright_blue]" + "=" * 100 + "[/bright_blue]")
        # logger.info("")
        
        # Connect to GitHub
        logger.info("[yellow]Connecting to GitHub...[/yellow]")
        connection_start = time.time()
        github_client = GitHubClient()
        connection_time = time.time() - connection_start
        # logger.info(f"[OK] Connected ({format_duration(connection_time)})")
        logger.info("")
        
        # Collect only open critical/high items
        summary = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'critical_items': [],
            'exposed_secrets': []
        }
        
        collection_start = time.time()
        
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]Starting daily data collection[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        # Dependabot critical alerts
        if settings.enable_dependabot:
            logger.info("[cyan]Checking Dependabot critical alerts...[/cyan]")
            dep_start = time.time()
            dependabot_collector = DependabotCollector(github_client)
            critical_deps = dependabot_collector.get_critical_alerts()
            dep_time = time.time() - dep_start
            
            summary['critical_items'].extend([
                {
                    'type': 'Dependency',
                    'repository': alert['repository'],
                    'severity': alert['severity'],
                    'description': f"{alert['package_name']}: {alert['summary']}"
                }
                for alert in critical_deps
            ])
            logger.info(f"[OK] Found {len(critical_deps)} critical dependencies ({format_duration(dep_time)})")
        
        # Code Scanning critical alerts
        if settings.enable_code_scanning:
            logger.info("[cyan]Checking Code Scanning critical alerts...[/cyan]")
            code_start = time.time()
            code_collector = CodeScanningCollector(github_client)
            all_alerts = code_collector.collect()
            critical_code = [
                a for a in all_alerts 
                if a.get('state') == 'open' and a.get('security_severity_level') == 'critical'
            ]
            code_time = time.time() - code_start
            
            summary['critical_items'].extend([
                {
                    'type': 'Code Scanning',
                    'repository': alert['repository'],
                    'severity': 'critical',
                    'description': alert['rule_description']
                }
                for alert in critical_code
            ])
            logger.info(f"[OK] Found {len(critical_code)} critical code issues ({format_duration(code_time)})")
        
        # Exposed secrets
        if settings.enable_secret_scanning:
            logger.info("[cyan]Checking for exposed secrets...[/cyan]")
            secret_start = time.time()
            secret_collector = SecretScanningCollector(github_client)
            exposed = secret_collector.get_exposed_secrets()
            secret_time = time.time() - secret_start
            
            summary['exposed_secrets'] = [
                {
                    'repository': alert['repository'],
                    'secret_type': alert['secret_type'],
                    'age_days': alert.get('age_days', 0)
                }
                for alert in exposed
            ]
            logger.info(f"[OK] Found {len(exposed)} exposed secrets ({format_duration(secret_time)})")
        
        collection_time = time.time() - collection_start
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]Data collection completed successfully[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("")
        
        # Display summary
        logger.info("")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info("[bright_magenta]DAILY SECURITY SUMMARY[/bright_magenta]")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        logger.info(f"[cyan]Date:[/cyan] {summary['date']}")
        logger.info(f"[red]Critical Vulnerabilities:[/red] {len(summary['critical_items'])}")
        logger.info(f"[magenta]Exposed Secrets:[/magenta] {len(summary['exposed_secrets'])}")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        
        if summary['critical_items']:
            logger.info("")
            logger.info("[bright_red]CRITICAL ITEMS REQUIRING IMMEDIATE ATTENTION:[/bright_red]")
            for item in summary['critical_items'][:10]:
                logger.info(f"  [red][{item['type']}][/red] {item['repository']}: {item['description'][:80]}")
        
        if summary['exposed_secrets']:
            logger.info("")
            logger.info("[bright_magenta]EXPOSED SECRETS:[/bright_magenta]")
            for secret in summary['exposed_secrets'][:10]:
                logger.info(f"  [magenta]{secret['repository']}:[/magenta] {secret['secret_type']} (Age: {secret['age_days']} days)")
        
        logger.info("")
        logger.info("[bright_magenta]" + "=" * 100 + "[/bright_magenta]")
        
        # Generate professional Excel report
        if summary['critical_items'] or summary['exposed_secrets']:
            logger.info("[cyan]Generating Excel report...[/cyan]")
            excel_start = time.time()
            
            reporter = DailyExcelReporter()
            filename = reporter.generate_daily_report(summary)
            
            excel_time = time.time() - excel_start
            # logger.info(f"[OK] Daily report saved ({format_duration(excel_time)})")
            logger.info(f"[bright_green]📊 Report location:[/bright_green] {filename}")
        else:
            logger.info("[bright_green]✓ No critical items or exposed secrets found - No report needed[/bright_green]")
        
        # Calculate total time
        total_time = time.time() - overall_start_time
        total_minutes = total_time / 60
        
        # Execution time summary
        logger.info("")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("[bright_cyan]EXECUTION TIME[/bright_cyan]")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info(f"[white]Connection:[/white]     {format_duration(connection_time)}")
        logger.info(f"[white]Data Collection:[/white] {format_duration(collection_time)}")
        logger.info("[bright_cyan]" + "-" * 100 + "[/bright_cyan]")
        logger.info(f"[bright_yellow]TOTAL TIME:[/bright_yellow]     {format_duration(total_time)} ({total_minutes:.2f} minutes)")
        logger.info("[bright_cyan]" + "=" * 100 + "[/bright_cyan]")
        logger.info("")
        
        github_client.close()
         # logger.info("[OK] Weekly report generation completed successfully")
        log_footer(logger)
        # logger.info("[OK] Daily summary completed successfully")
        return 0
        
    except Exception as e:
        total_time = time.time() - overall_start_time
        total_minutes = total_time / 60
        logger.error(f"[ERROR] Error generating daily summary: {e}", exc_info=True)
        logger.error(f"[red]Failed after {format_duration(total_time)} ({total_minutes:.2f} minutes)[/red]")
        return 1

if __name__ == "__main__":
    sys.exit(generate_daily_summary())