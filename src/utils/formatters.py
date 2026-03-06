"""
Data formatting utilities
"""
from typing import Any, Dict, List
from datetime import datetime
import pandas as pd

class DataFormatter:
    """Utility class for formatting data"""
    
    @staticmethod
    def format_severity(severity: str) -> str:
        """Format severity for display"""
        severity_map = {
            'critical': '🔴 CRITICAL',
            'high': '🟠 HIGH',
            'medium': '🟡 MEDIUM',
            'low': '🟢 LOW',
        }
        return severity_map.get(severity.lower(), severity.upper())
    
    @staticmethod
    def format_date(date_str: str, format: str = '%Y-%m-%d') -> str:
        """Format ISO date string"""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime(format)
        except:
            return date_str
    
    @staticmethod
    def format_age_days(days: int) -> str:
        """Format age in days to human-readable string"""
        if days is None:
            return 'N/A'
        if days == 0:
            return 'Today'
        elif days == 1:
            return '1 day'
        elif days < 7:
            return f'{days} days'
        elif days < 30:
            weeks = days // 7
            return f'{weeks} week{"s" if weeks > 1 else ""}'
        elif days < 365:
            months = days // 30
            return f'{months} month{"s" if months > 1 else ""}'
        else:
            years = days // 365
            return f'{years} year{"s" if years > 1 else ""}'
    
    @staticmethod
    def format_boolean(value: bool) -> str:
        """Format boolean as emoji"""
        return '✅' if value else '❌'
    
    @staticmethod
    def format_percentage(value: float, decimals: int = 1) -> str:
        """Format percentage"""
        return f'{value:.{decimals}f}%'
    
    @staticmethod
    def format_trend(current: int, previous: int) -> str:
        """Format trend with arrow and percentage"""
        if previous == 0:
            return '➡️ N/A'
        
        change = current - previous
        percentage = (change / previous) * 100
        
        if change > 0:
            return f'⬆️ +{change} (+{percentage:.1f}%)'
        elif change < 0:
            return f'⬇️ {change} ({percentage:.1f}%)'
        else:
            return '➡️ No change'
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 100) -> str:
        """Truncate text with ellipsis"""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + '...'
    
    @staticmethod
    def format_list(items: List[str], max_items: int = 5) -> str:
        """Format list for display"""
        if not items:
            return 'None'
        
        if len(items) <= max_items:
            return ', '.join(items)
        
        displayed = ', '.join(items[:max_items])
        remaining = len(items) - max_items
        return f'{displayed} (+{remaining} more)'