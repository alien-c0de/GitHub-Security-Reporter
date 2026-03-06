"""
Base reporter class
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from pathlib import Path

class BaseReporter(ABC):
    """Abstract base class for all reporters"""
    
    @abstractmethod
    def generate_report(self, snapshot: Dict[str, Any], metrics: Dict[str, Any], 
                       trends: Dict[str, Any] = None) -> Path:
        """
        Generate report
        
        Args:
            snapshot: Data snapshot
            metrics: Calculated metrics
            trends: Trend analysis
            
        Returns:
            Path to generated report
        """
        pass