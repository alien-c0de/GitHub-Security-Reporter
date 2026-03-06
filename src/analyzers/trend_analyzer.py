"""
Analyze trends in security data
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class TrendAnalyzer:
    """
    Analyze trends over time
    """
    
    def __init__(self):
        pass
    
    def analyze_week_over_week(self, current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare current week with previous week
        
        Args:
            current: Current week metrics
            previous: Previous week metrics
            
        Returns:
            Trend analysis
        """
        trends = {}
        
        # Overall vulnerability trend
        current_total = current.get('summary', {}).get('total_vulnerabilities', 0)
        previous_total = previous.get('summary', {}).get('total_vulnerabilities', 0)
        
        trends['total_vulnerabilities'] = self._calculate_change(current_total, previous_total)
        
        # By severity
        trends['by_severity'] = {}
        for severity in ['critical', 'high', 'medium', 'low']:
            current_count = current.get('summary', {}).get(f'{severity}_count', 0)
            previous_count = previous.get('summary', {}).get(f'{severity}_count', 0)
            trends['by_severity'][severity] = self._calculate_change(current_count, previous_count)
        
        # Secrets
        current_secrets = current.get('summary', {}).get('exposed_secrets', 0)
        previous_secrets = previous.get('summary', {}).get('exposed_secrets', 0)
        trends['exposed_secrets'] = self._calculate_change(current_secrets, previous_secrets)
        
        # Remediation
        current_closed = current.get('summary', {}).get('vulnerabilities_closed_this_week', 0)
        previous_closed = previous.get('summary', {}).get('vulnerabilities_closed_this_week', 0)
        trends['remediation'] = self._calculate_change(current_closed, previous_closed)
        
        # Health score
        current_health = current.get('summary', {}).get('overall_health_score', 0)
        previous_health = previous.get('summary', {}).get('overall_health_score', 0)
        trends['health_score'] = self._calculate_change(current_health, previous_health)
        
        return trends
    
    def analyze_multi_week_trend(self, snapshots: List[Dict[str, Any]], metric_path: str) -> Dict[str, Any]:
        """
        Analyze trend over multiple weeks
        
        Args:
            snapshots: List of snapshots (oldest to newest)
            metric_path: Path to metric to analyze
            
        Returns:
            Trend analysis
        """
        if len(snapshots) < 2:
            return {'status': 'insufficient_data', 'message': 'Need at least 2 data points'}
        
        # Extract values
        values = []
        dates = []
        
        for snapshot in snapshots:
            value = self._get_nested_value(snapshot, metric_path)
            if value is not None:
                values.append(value)
                dates.append(snapshot.get('timestamp'))
        
        if len(values) < 2:
            return {'status': 'insufficient_data', 'message': 'Metric not found in snapshots'}
        
        # Create DataFrame
        df = pd.DataFrame({
            'date': pd.to_datetime(dates),
            'value': values
        })
        
        # Calculate statistics
        trend = {
            'metric': metric_path,
            'data_points': len(values),
            'current_value': values[-1],
            'previous_value': values[-2],
            'min_value': min(values),
            'max_value': max(values),
            'average_value': sum(values) / len(values),
            'change_from_previous': values[-1] - values[-2],
            'percent_change': ((values[-1] - values[-2]) / values[-2] * 100) if values[-2] != 0 else 0,
            'overall_change': values[-1] - values[0],
            'overall_percent_change': ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0,
            'trend_direction': self._determine_trend_direction(values),
            'volatility': self._calculate_volatility(values),
            'values': [{'date': d, 'value': v} for d, v in zip(dates, values)]
        }
        
        return trend
    
    def _calculate_change(self, current: float, previous: float) -> Dict[str, Any]:
        """Calculate change metrics"""
        change = current - previous
        percent_change = ((change / previous) * 100) if previous != 0 else 0
        
        return {
            'current': current,
            'previous': previous,
            'absolute_change': change,
            'percent_change': round(percent_change, 2),
            'direction': 'up' if change > 0 else 'down' if change < 0 else 'unchanged',
            'improved': change < 0  # For vulnerabilities, decrease is improvement
        }
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """Get nested dictionary value using dot notation"""
        keys = path.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        
        return value
    
    def _determine_trend_direction(self, values: List[float]) -> str:
        """Determine overall trend direction"""
        if len(values) < 2:
            return 'unknown'
        
        # Simple linear regression
        n = len(values)
        x = list(range(n))
        
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 'flat'
        
        slope = numerator / denominator
        
        if slope > 0.1:
            return 'increasing'
        elif slope < -0.1:
            return 'decreasing'
        else:
            return 'stable'
    
    def _calculate_volatility(self, values: List[float]) -> float:
        """Calculate volatility (standard deviation)"""
        if len(values) < 2:
            return 0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return round(variance ** 0.5, 2)