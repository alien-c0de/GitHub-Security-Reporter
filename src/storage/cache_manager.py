"""
Cache management for API responses
"""
from typing import Any, Optional
from datetime import datetime, timedelta
import hashlib
import logging

from src.storage.data_store import DataStore
from config.settings import settings

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Manage caching of API responses
    """
    
    def __init__(self, data_store: Optional[DataStore] = None, cache_dir: str = 'cache'):
        """
        Initialize cache manager
        
        Args:
            data_store: DataStore instance
            cache_dir: Cache subdirectory
        """
        self.data_store = data_store or DataStore()
        self.cache_dir = cache_dir
        self.ttl_hours = settings.get_config('storage.cache_ttl_hours', 24)
    
    def _generate_cache_key(self, key: str) -> str:
        """
        Generate cache key hash
        
        Args:
            key: Original key
            
        Returns:
            Hashed key
        """
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_cache_filename(self, key: str) -> str:
        """Get cache filename"""
        cache_key = self._generate_cache_key(key)
        return f"{cache_key}.pkl"
    
    def set(self, key: str, value: Any, ttl_hours: Optional[int] = None) -> None:
        """
        Set cache value
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_hours: Time to live in hours
        """
        if ttl_hours is None:
            ttl_hours = self.ttl_hours
        
        cache_data = {
            'value': value,
            'cached_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(hours=ttl_hours)).isoformat(),
            'key': key
        }
        
        filename = self._get_cache_filename(key)
        self.data_store.save_pickle(cache_data, filename, subdir=self.cache_dir)
        logger.debug(f"Cached data for key: {key}")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cache value
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        filename = self._get_cache_filename(key)
        cache_data = self.data_store.load_pickle(filename, subdir=self.cache_dir)
        
        if cache_data is None:
            logger.debug(f"Cache miss for key: {key}")
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(cache_data['expires_at'])
        if datetime.now() > expires_at:
            logger.debug(f"Cache expired for key: {key}")
            self.delete(key)
            return None
        
        logger.debug(f"Cache hit for key: {key}")
        return cache_data['value']
    
    def delete(self, key: str) -> None:
        """
        Delete cache entry
        
        Args:
            key: Cache key
        """
        filename = self._get_cache_filename(key)
        try:
            self.data_store.delete_file(filename, subdir=self.cache_dir)
            logger.debug(f"Deleted cache for key: {key}")
        except Exception as e:
            logger.warning(f"[bright_red][❌] Error deleting cache for key {key}: {e}[/bright_red]")
    
    def clear_all(self) -> None:
        """Clear all cache"""
        cache_files = self.data_store.list_files('*.pkl', subdir=self.cache_dir)
        
        for filepath in cache_files:
            try:
                filepath.unlink()
            except Exception as e:
                logger.warning(f"[bright_red][❌] Error deleting cache file {filepath}: {e}[/bright_red]")
        
        logger.info(f"Cleared {len(cache_files)} cache files")
    
    def cleanup_expired(self) -> None:
        """Clean up expired cache entries"""
        cache_files = self.data_store.list_files('*.pkl', subdir=self.cache_dir)
        removed_count = 0
        
        for filepath in cache_files:
            try:
                cache_data = self.data_store.load_pickle(filepath.name, subdir=self.cache_dir)
                if cache_data:
                    expires_at = datetime.fromisoformat(cache_data['expires_at'])
                    if datetime.now() > expires_at:
                        filepath.unlink()
                        removed_count += 1
            except Exception as e:
                logger.warning(f"[bright_red][❌] Error checking cache file {filepath}: {e}[/bright_red]")
        
        logger.info(f"Cleaned up {removed_count} expired cache entries")