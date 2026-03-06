"""
Main entry point for GitHub Security Reporter
"""
import sys
import argparse
import os
import pyfiglet
from time import perf_counter
from colorama import Back, Fore, Style
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.generate_weekly_report import main as weekly_report
from scripts.generate_daily_summary import generate_daily_summary
from scripts.export_all_data import export_all_data
from scripts.generate_organization_report import generate_organization_report
from src.utils.logger import setup_logger

logger = setup_logger()

def main():
    """Main entry point"""
    start_time = perf_counter()

    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')
    
    figlet_name = "GitHub Security Reporter"
    terminal_header = pyfiglet.figlet_format(figlet_name, font = "ansi_regular")
    print(Fore.YELLOW + Style.BRIGHT + terminal_header + Fore.RESET + Style.RESET_ALL)
    
    parser = argparse.ArgumentParser(
                description='GitHub Advanced Security Reporter - Automated security reporting tool',
                formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog="""
                        Examples:
                        python main.py weekly      Generate weekly comprehensive security report
                        python main.py daily       Generate daily critical items summary
                        python main.py orgdata     Generate organization and repository inventory
                        
                        For more information, see README.md
                """
            )
    
    parser.add_argument(
        'command',
        choices=['weekly', 'daily', 'export', 'orgdata'],
        help='Command to execute'
    )
    
    args = parser.parse_args()
    
    try:
        if args.command == 'weekly':
            return weekly_report()
        elif args.command == 'daily':
            return generate_daily_summary()
        elif args.command == 'export':
            return export_all_data()
        elif args.command == 'orgdata':
            return generate_organization_report()
    except KeyboardInterrupt:
        logger.warning("\n[yellow]Process interrupted by user[/yellow]")
        return 130
    
    except Exception as e:
        logger.error(f"[red]Fatal error: {e}[/red]", exc_info=True)
        return 1    

if __name__ == "__main__":
    sys.exit(main())