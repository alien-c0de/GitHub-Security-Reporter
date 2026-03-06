"""
Tests for Dependabot collector
"""
import unittest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.collectors.dependabot_collector import DependabotCollector

class TestDependabotCollector(unittest.TestCase):
    """Test Dependabot collector"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_client = Mock()
        self.mock_org = Mock()
        self.mock_client.org = self.mock_org
        
        self.collector = DependabotCollector(self.mock_client)
    
    def test_collector_name(self):
        """Test collector name"""
        self.assertEqual(self.collector.get_collector_name(), "DependabotCollector")
    
    @patch('src.collectors.dependabot_collector.logger')
    def test_collect_empty_repos(self, mock_logger):
        """Test collection with no repositories"""
        self.mock_org.get_repos.return_value = []
        
        result = self.collector.collect()
        
        self.assertEqual(result, [])
    
    def test_parse_alert(self):
        """Test alert parsing"""
        mock_alert = Mock()
        mock_alert.number = 1
        mock_alert.created_at = datetime.now()
        mock_alert.updated_at = datetime.now()
        
        mock_advisory = Mock()
        mock_advisory.severity = 'high'
        mock_advisory.cve_id = 'CVE-2024-1234'
        mock_advisory.ghsa_id = 'GHSA-xxxx-yyyy-zzzz'
        mock_advisory.summary = 'Test vulnerability'
        mock_advisory.description = 'Test description'
        mock_advisory.cvss = None
        mock_advisory.cwes = []
        
        mock_package = Mock()
        mock_package.name = 'test-package'
        mock_package.ecosystem = 'npm'
        
        mock_advisory.package = mock_package
        mock_alert.security_advisory = mock_advisory
        mock_alert.html_url = 'https://github.com/test'
        
        result = self.collector._parse_alert(mock_alert, 'test-repo', 'open')
        
        self.assertEqual(result['repository'], 'test-repo')
        self.assertEqual(result['state'], 'open')
        self.assertEqual(result['severity'], 'high')
        self.assertEqual(result['package_name'], 'test-package')

class TestCodeScanningCollector(unittest.TestCase):
    """Test Code Scanning collector"""
    
    def setUp(self):
        """Set up test fixtures"""
        from src.collectors.code_scanning_collector import CodeScanningCollector
        
        self.mock_client = Mock()
        self.mock_org = Mock()
        self.mock_client.org = self.mock_org
        
        self.collector = CodeScanningCollector(self.mock_client)
    
    def test_collector_name(self):
        """Test collector name"""
        self.assertEqual(self.collector.get_collector_name(), "CodeScanningCollector")

class TestSecretScanningCollector(unittest.TestCase):
    """Test Secret Scanning collector"""
    
    def setUp(self):
        """Set up test fixtures"""
        from src.collectors.secret_scanning_collector import SecretScanningCollector
        
        self.mock_client = Mock()
        self.mock_org = Mock()
        self.mock_client.org = self.mock_org
        
        self.collector = SecretScanningCollector(self.mock_client)
    
    def test_collector_name(self):
        """Test collector name"""
        self.assertEqual(self.collector.get_collector_name(), "SecretScanningCollector")

if __name__ == '__main__':
    unittest.main()