"""
Historical data management for trend analysis
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import logging

from src.storage.data_store import DataStore
from config.settings import settings

logger = logging.getLogger(__name__)

class HistoryManager:
    """
    Manage historical security data for trend analysis
    """
    
    def __init__(self, data_store: Optional[DataStore] = None):
        """
        Initialize history manager
        
        Args:
            data_store: DataStore instance
        """
        self.data_store = data_store or DataStore()
        self.history_file = 'security_history.json'
    
    def save_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """
        Save a weekly snapshot
        
        Args:
            snapshot_data: Snapshot data to save
        """
        # Add metadata
        snapshot_data['timestamp'] = datetime.now().isoformat()
        snapshot_data['week_number'] = datetime.now().isocalendar()[1]
        snapshot_data['year'] = datetime.now().year
        
        # Load existing history
        history = self.load_history()
        
        # Add new snapshot
        history['snapshots'].append(snapshot_data)
        
        # Clean up old snapshots
        retention_weeks = settings.get_config('storage.history_retention_weeks', 52)
        cutoff_date = datetime.now() - timedelta(weeks=retention_weeks)
        
        history['snapshots'] = [
            s for s in history['snapshots']
            if datetime.fromisoformat(s['timestamp']) > cutoff_date
        ]
        
        # Sort by timestamp
        history['snapshots'].sort(key=lambda x: x['timestamp'])
        
        # Update metadata
        history['last_updated'] = datetime.now().isoformat()
        history['total_snapshots'] = len(history['snapshots'])
        
        # Save
        self.data_store.save_json(history, self.history_file)
        logger.info(f"[bright_yellow][+] Saved snapshot. Total snapshots: {len(history['snapshots'])}[/bright_yellow]")
    
    def load_history(self) -> Dict[str, Any]:
        """
        Load complete history
        
        Returns:
            Dictionary with historical data
        """
        history = self.data_store.load_json(self.history_file)
        
        if history is None:
            # Initialize new history
            history = {
                'created_at': datetime.now().isoformat(),
                'last_updated': None,
                'total_snapshots': 0,
                'snapshots': []
            }
        
        return history
    
    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent snapshot
        
        Returns:
            Latest snapshot or None
        """
        history = self.load_history()
        if history['snapshots']:
            return history['snapshots'][-1]
        return None
    
    def get_snapshot_by_date(self, target_date: datetime) -> Optional[Dict[str, Any]]:
        """
        Get snapshot closest to target date
        
        Args:
            target_date: Target date
            
        Returns:
            Closest snapshot or None
        """
        history = self.load_history()
        
        if not history['snapshots']:
            return None
        
        # Find closest snapshot
        closest = min(
            history['snapshots'],
            key=lambda s: abs(datetime.fromisoformat(s['timestamp']) - target_date)
        )
        
        return closest
    
    def get_snapshots_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get snapshots within date range
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of snapshots
        """
        history = self.load_history()
        
        return [
            s for s in history['snapshots']
            if start_date <= datetime.fromisoformat(s['timestamp']) <= end_date
        ]
    
    def get_last_n_snapshots(self, n: int) -> List[Dict[str, Any]]:
        """
        Get last N snapshots
        
        Args:
            n: Number of snapshots
            
        Returns:
            List of snapshots
        """
        history = self.load_history()
        return history['snapshots'][-n:] if len(history['snapshots']) >= n else history['snapshots']
    
    def get_weekly_comparison(self) -> Optional[Dict[str, Any]]:
        """
        Compare current week with previous week
        
        Returns:
            Comparison data
        """
        snapshots = self.get_last_n_snapshots(2)
        
        if len(snapshots) < 2:
            return None
        
        previous = snapshots[0]
        current = snapshots[1]
        
        return {
            'previous_week': previous,
            'current_week': current,
            'comparison_date': datetime.now().isoformat()
        }
    
    def calculate_trend(self, metric_path: str, weeks: int = 4) -> List[Dict[str, Any]]:
        """
        Calculate trend for a specific metric
        
        Args:
            metric_path: Dot-separated path to metric (e.g., 'dependabot.critical_count')
            weeks: Number of weeks to analyze
            
        Returns:
            List of trend data points
        """
        snapshots = self.get_last_n_snapshots(weeks)
        
        trend_data = []
        for snapshot in snapshots:
            # Navigate to metric using path
            value = self._get_nested_value(snapshot, metric_path)
            
            trend_data.append({
                'date': snapshot['timestamp'],
                'week': snapshot['week_number'],
                'year': snapshot['year'],
                'value': value
            })
        
        return trend_data
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """
        Get nested dictionary value using dot notation
        
        Args:
            data: Dictionary to search
            path: Dot-separated path
            
        Returns:
            Value or None
        """
        keys = path.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value
    
    def cleanup_old_snapshots(self, retention_weeks: Optional[int] = None):
        """
        Clean up old snapshots
        
        Args:
            retention_weeks: Number of weeks to retain
        """
        if retention_weeks is None:
            retention_weeks = settings.get_config('storage.history_retention_weeks', 52)
        
        history = self.load_history()
        cutoff_date = datetime.now() - timedelta(weeks=retention_weeks)
        
        original_count = len(history['snapshots'])
        
        history['snapshots'] = [
            s for s in history['snapshots']
            if datetime.fromisoformat(s['timestamp']) > cutoff_date
        ]
        
        removed_count = original_count - len(history['snapshots'])
        
        if removed_count > 0:
            history['last_updated'] = datetime.now().isoformat()
            history['total_snapshots'] = len(history['snapshots'])
            self.data_store.save_json(history, self.history_file)
            logger.info(f"Cleaned up {removed_count} old snapshots")