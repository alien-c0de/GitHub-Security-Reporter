"""
Tests for Metrics Calculator
"""
import unittest
from src.analyzers.metrics_calculator import MetricsCalculator

class TestMetricsCalculator(unittest.TestCase):
    """Test Metrics Calculator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.calculator = MetricsCalculator()
    
    def test_empty_metrics(self):
        """Test calculation with empty data"""
        snapshot = {
            'dependabot': [],
            'code_scanning': [],
            'secret_scanning': [],
            'repository_health': []
        }
        
        metrics = self.calculator.calculate_all_metrics(snapshot)
        
        self.assertIn('summary', metrics)
        self.assertEqual(metrics['summary']['total_vulnerabilities'], 0)
    
    def test_dependabot_metrics(self):
        """Test Dependabot metrics calculation"""
        data = [
            {'state': 'open', 'severity': 'critical', 'package_ecosystem': 'npm'},
            {'state': 'open', 'severity': 'high', 'package_ecosystem': 'npm'},
            {'state': 'dismissed', 'severity': 'medium', 'package_ecosystem': 'pip'}
        ]
        
        metrics = self.calculator.calculate_dependabot_metrics(data)
        
        self.assertEqual(metrics['total_open'], 2)
        self.assertEqual(metrics['by_severity']['critical'], 1)
        self.assertEqual(metrics['by_severity']['high'], 1)
    
    def test_summary_metrics(self):
        """Test summary metrics aggregation"""
        all_metrics = {
            'dependabot': {
                'total_open': 5,
                'by_severity': {'critical': 1, 'high': 2, 'medium': 2, 'low': 0}
            },
            'code_scanning': {
                'total_open': 3,
                'by_severity': {'critical': 0, 'high': 1, 'medium': 2, 'low': 0}
            },
            'secret_scanning': {
                'total_open': 2
            }
        }
        
        summary = self.calculator.calculate_summary_metrics(all_metrics)
        
        self.assertEqual(summary['total_vulnerabilities'], 8)
        self.assertEqual(summary['critical_count'], 1)
        self.assertEqual(summary['high_count'], 3)
        self.assertEqual(summary['exposed_secrets'], 2)

if __name__ == '__main__':
    unittest.main()