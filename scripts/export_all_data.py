"""
Export all security data to JSON for backup/analysis
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime

from src.utils.logger import setup_logger
from src.utils.github_client import GitHubClient
from src.storage.data_store import DataStore
from scripts.generate_weekly_report import collect_all_data
from config.settings import settings

logger = setup_logger()

def export_all_data():
    """Export all data to JSON"""
    try:
        logger.info("Exporting all security data...")
        
        # Connect to GitHub
        github_client = GitHubClient()
        
        # Collect all data
        snapshot = collect_all_data(github_client)
        
        # Save to exports directory
        data_store = DataStore()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"full_export_{timestamp}.json"
        
        filepath = data_store.save_json(snapshot, filename, subdir='exports')
        
        logger.info(f"✓ Data exported successfully: {filepath}")
        
        # Also save pretty-printed version
        import json
        pretty_filename = f"full_export_{timestamp}_pretty.json"
        pretty_path = settings.history_data_dir / 'exports' / pretty_filename
        
        with open(pretty_path, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
        
        logger.info(f"✓ Pretty-printed version: {pretty_path}")
        
        github_client.close()
        
        return 0
        
    except Exception as e:
        logger.error(f"[bright_red][❌] Error exporting data: {e}[/bright_red]", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(export_all_data())