"""
Data storage and persistence
"""
import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

class DataStore:
    """
    Handle data storage and retrieval
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize data store
        
        Args:
            storage_dir: Directory for storing data (defaults to settings)
        """
        self.storage_dir = storage_dir or settings.history_data_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def save_json(self, data: Any, filename: str, subdir: str = None) -> Path:
        """
        Save data as JSON
        
        Args:
            data: Data to save
            filename: Filename
            subdir: Optional subdirectory
            
        Returns:
            Path to saved file
        """
        if subdir:
            save_dir = self.storage_dir / subdir
            save_dir.mkdir(parents=True, exist_ok=True)
        else:
            save_dir = self.storage_dir
        
        filepath = save_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(f"[bright_yellow][+] Data saved to {filepath}[/bright_yellow]")
            return filepath
        except Exception as e:
            logger.error(f"[bright_red][❌] Error saving JSON to {filepath}: {e}[/bright_red]")
            raise
    
    def load_json(self, filename: str, subdir: str = None) -> Any:
        """
        Load data from JSON
        
        Args:
            filename: Filename
            subdir: Optional subdirectory
            
        Returns:
            Loaded data
        """
        if subdir:
            filepath = self.storage_dir / subdir / filename
        else:
            filepath = self.storage_dir / filename
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            logger.info(f"[bright_yellow][+] Data loaded from {filepath}[/bright_yellow]")
            return data
        except FileNotFoundError:
            logger.warning(f"File not found: {filepath}")
            return None
        except Exception as e:
            logger.error(f"[bright_red][❌] Error loading JSON from {filepath}: {e}[/bright_red]")
            raise
    
    def save_pickle(self, data: Any, filename: str, subdir: str = None) -> Path:
        """
        Save data as pickle
        
        Args:
            data: Data to save
            filename: Filename
            subdir: Optional subdirectory
            
        Returns:
            Path to saved file
        """
        if subdir:
            save_dir = self.storage_dir / subdir
            save_dir.mkdir(parents=True, exist_ok=True)
        else:
            save_dir = self.storage_dir
        
        filepath = save_dir / filename
        
        try:
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
            logger.info(f"[bright_yellow][+] Data saved to {filepath}[/bright_yellow]")
            return filepath
        except Exception as e:
            logger.error(f"[bright_red][❌]Error saving pickle to {filepath}: {e}[/bright_red]")
            raise
    
    def load_pickle(self, filename: str, subdir: str = None) -> Any:
        """
        Load data from pickle
        
        Args:
            filename: Filename
            subdir: Optional subdirectory
            
        Returns:
            Loaded data
        """
        if subdir:
            filepath = self.storage_dir / subdir / filename
        else:
            filepath = self.storage_dir / filename
        
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
            logger.info(f"[bright_yellow][+] Data loaded from {filepath}[/bright_yellow]")
            return data
        except FileNotFoundError:
            logger.warning(f"File not found: {filepath}")
            return None
        except Exception as e:
            logger.error(f"[bright_red][❌] Error loading pickle from {filepath}: {e}[/bright_red]")
            raise
    
    def file_exists(self, filename: str, subdir: str = None) -> bool:
        """Check if file exists"""
        if subdir:
            filepath = self.storage_dir / subdir / filename
        else:
            filepath = self.storage_dir / filename
        return filepath.exists()
    
    def list_files(self, pattern: str = '*', subdir: str = None) -> List[Path]:
        """
        List files matching pattern
        
        Args:
            pattern: Glob pattern
            subdir: Optional subdirectory
            
        Returns:
            List of file paths
        """
        if subdir:
            search_dir = self.storage_dir / subdir
        else:
            search_dir = self.storage_dir
        
        if not search_dir.exists():
            return []
        
        return list(search_dir.glob(pattern))
    
    def delete_file(self, filename: str, subdir: str = None):
        """Delete a file"""
        if subdir:
            filepath = self.storage_dir / subdir / filename
        else:
            filepath = self.storage_dir / filename
        
        try:
            if filepath.exists():
                filepath.unlink()
                logger.info(f"Deleted file: {filepath}")
        except Exception as e:
            logger.error(f"[bright_red][❌] Error deleting file {filepath}: {e}[/bright_red]")
            raise