"""
Calculate security metrics from collected data
"""
from typing import Dict, List, Any
from datetime import datetime
import pandas as pd
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

class MetricsCalculator:
    """
    Calculate security metrics and KPIs
    """
    
    def __init__(self):
        self.severity_levels = settings.severity_levels
        self.sla_days = settings.sla_days
    
    def calculate_all_metrics(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate all metrics from a snapshot
        
        Args:
            snapshot: Data snapshot
            
        Returns:
            Dictionary of calculated metrics
        """
        metrics = {}
        
        # Dependabot metrics
        if 'dependabot' in snapshot:
            metrics['dependabot'] = self.calculate_dependabot_metrics(snapshot['dependabot'])
        
        # Code scanning metrics
        if 'code_scanning' in snapshot:
            metrics['code_scanning'] = self.calculate_code_scanning_metrics(snapshot['code_scanning'])
        
        # Secret scanning metrics
        if 'secret_scanning' in snapshot:
            metrics['secret_scanning'] = self.calculate_secret_scanning_metrics(snapshot['secret_scanning'])
        
        # Repository health metrics
        if 'repository_health' in snapshot:
            metrics['repository_health'] = self.calculate_repository_health_metrics(snapshot['repository_health'])
        
        # Overall summary metrics
        metrics['summary'] = self.calculate_summary_metrics(metrics)
        
        return metrics
    
    def calculate_dependabot_metrics(self, dependabot_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate Dependabot-specific metrics"""
        df = pd.DataFrame(dependabot_data)
        
        if df.empty:
            return self._empty_metrics()
        
        # Filter open alerts
        open_df = df[df['state'] == 'open']
        closed_df = df[df['state'].isin(['dismissed', 'fixed'])]
        
        metrics = {
            'total_open': len(open_df),
            'total_closed_this_week': len(closed_df),
            'by_severity': {},
            'by_ecosystem': {},
            'top_vulnerable_repos': [],
            'oldest_alerts': [],
            'mttr_days': 0,
            'sla_compliance': {}
        }
        
        # By severity
        for severity in self.severity_levels:
            count = len(open_df[open_df['severity'] == severity])
            metrics['by_severity'][severity] = count
        
        # By ecosystem
        if 'package_ecosystem' in open_df.columns:
            ecosystem_counts = open_df['package_ecosystem'].value_counts().to_dict()
            metrics['by_ecosystem'] = ecosystem_counts
        
        # Top vulnerable repos
        if not open_df.empty:
            repo_counts = open_df['repository'].value_counts().head(10)
            metrics['top_vulnerable_repos'] = [
                {'repository': repo, 'count': int(count)}
                for repo, count in repo_counts.items()
            ]
        
        # Oldest alerts
        if not open_df.empty and 'age_days' in open_df.columns:
            oldest = open_df.nlargest(10, 'age_days')[['repository', 'severity', 'package_name', 'age_days']]
            metrics['oldest_alerts'] = oldest.to_dict('records')
        
        # MTTR (Mean Time To Remediate)
        if not closed_df.empty and 'age_days' in closed_df.columns:
            metrics['mttr_days'] = float(closed_df['age_days'].mean())
        
        # SLA compliance
        for severity in self.severity_levels:
            if severity not in self.sla_days:
                continue
            
            sla = self.sla_days[severity]
            severity_open = open_df[open_df['severity'] == severity]
            
            if not severity_open.empty and 'age_days' in severity_open.columns:
                within_sla = len(severity_open[severity_open['age_days'] <= sla])
                total = len(severity_open)
                compliance_rate = (within_sla / total * 100) if total > 0 else 100
                
                metrics['sla_compliance'][severity] = {
                    'within_sla': within_sla,
                    'total': total,
                    'compliance_rate': round(compliance_rate, 2),
                    'sla_days': sla
                }
        
        return metrics
    
    def calculate_code_scanning_metrics(self, code_scanning_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate Code Scanning-specific metrics"""
        df = pd.DataFrame(code_scanning_data)
        
        if df.empty:
            return self._empty_metrics()
        
        open_df = df[df['state'] == 'open']
        closed_df = df[df['state'].isin(['dismissed', 'fixed'])]
        
        metrics = {
            'total_open': len(open_df),
            'total_closed_this_week': len(closed_df),
            'by_severity': {},
            'by_tool': {},
            'by_cwe': {},
            'top_vulnerable_repos': [],
            'false_positive_rate': 0
        }
        
        # By severity
        if 'security_severity_level' in open_df.columns:
            for severity in self.severity_levels:
                count = len(open_df[open_df['security_severity_level'] == severity])
                metrics['by_severity'][severity] = count
        
        # By tool
        if 'tool_name' in open_df.columns:
            tool_counts = open_df['tool_name'].value_counts().to_dict()
            metrics['by_tool'] = tool_counts
        
        # By CWE
        if 'cwe_ids' in open_df.columns:
            all_cwes = []
            for cwe_list in open_df['cwe_ids']:
                if isinstance(cwe_list, list):
                    all_cwes.extend(cwe_list)
            
            if all_cwes:
                cwe_series = pd.Series(all_cwes)
                cwe_counts = cwe_series.value_counts().head(10).to_dict()
                metrics['by_cwe'] = cwe_counts
        
        # Top vulnerable repos
        if not open_df.empty:
            repo_counts = open_df['repository'].value_counts().head(10)
            metrics['top_vulnerable_repos'] = [
                {'repository': repo, 'count': int(count)}
                for repo, count in repo_counts.items()
            ]
        
        # False positive rate (dismissed as false positive)
        if not closed_df.empty and 'dismissed_reason' in closed_df.columns:
            false_positives = len(closed_df[closed_df['dismissed_reason'] == 'false positive'])
            total_closed = len(closed_df)
            metrics['false_positive_rate'] = round((false_positives / total_closed * 100) if total_closed > 0 else 0, 2)
        
        return metrics
    
    def calculate_secret_scanning_metrics(self, secret_scanning_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate Secret Scanning-specific metrics"""
        df = pd.DataFrame(secret_scanning_data)
        
        if df.empty:
            return self._empty_metrics()
        
        open_df = df[df['state'] == 'open']
        resolved_df = df[df['state'] == 'resolved']
        
        metrics = {
            'total_open': len(open_df),
            'total_resolved_this_week': len(resolved_df),
            'by_secret_type': {},
            'top_vulnerable_repos': [],
            'push_protection_bypassed_count': 0,
            'mttr_days': 0
        }
        
        # By secret type
        if 'secret_type' in open_df.columns:
            type_counts = open_df['secret_type'].value_counts().to_dict()
            metrics['by_secret_type'] = type_counts
        
        # Top vulnerable repos
        if not open_df.empty:
            repo_counts = open_df['repository'].value_counts().head(10)
            metrics['top_vulnerable_repos'] = [
                {'repository': repo, 'count': int(count)}
                for repo, count in repo_counts.items()
            ]
        
        # Push protection bypassed
        if 'push_protection_bypassed' in df.columns:
            bypassed_count = df['push_protection_bypassed'].sum()
            metrics['push_protection_bypassed_count'] = int(bypassed_count)
        
        # MTTR
        if not resolved_df.empty and 'age_days' in resolved_df.columns:
            metrics['mttr_days'] = float(resolved_df['age_days'].mean())
        
        return metrics
    
    def calculate_repository_health_metrics(self, repo_health_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate Repository Health metrics"""
        df = pd.DataFrame(repo_health_data)
        
        if df.empty:
            return {}
        
        total_repos = len(df)
        
        metrics = {
            'total_repositories': total_repos,
            'security_features': {},
            'compliance': {},
            'average_compliance_score': 0,
            'non_compliant_repos': []
        }
        
        # Security feature adoption
        features = [
            'dependabot_enabled',
            'code_scanning_enabled',
            'secret_scanning_enabled',
            'branch_protection_enabled',
            'has_security_policy'
        ]
        
        for feature in features:
            if feature in df.columns:
                enabled_count = df[feature].sum()
                metrics['security_features'][feature] = {
                    'enabled': int(enabled_count),
                    'total': total_repos,
                    'coverage_percentage': round((enabled_count / total_repos * 100), 2)
                }
        
        # Compliance metrics
        if 'compliance_score' in df.columns:
            metrics['average_compliance_score'] = round(df['compliance_score'].mean(), 2)
            
            # Non-compliant repos (below 80%)
            non_compliant = df[df['compliance_score'] < 0.8]
            metrics['compliance']['below_80_percent'] = len(non_compliant)
            
            if not non_compliant.empty:
                metrics['non_compliant_repos'] = non_compliant[
                    ['repository', 'compliance_score']
                ].sort_values('compliance_score').head(10).to_dict('records')
        
        # Active vs inactive repos
        if 'is_active' in df.columns:
            active_count = df['is_active'].sum()
            metrics['activity'] = {
                'active_repos': int(active_count),
                'inactive_repos': total_repos - int(active_count),
                'active_percentage': round((active_count / total_repos * 100), 2)
            }
        
        return metrics
    
    def calculate_summary_metrics(self, all_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall summary metrics"""
        summary = {
            'total_vulnerabilities': 0,
            'critical_count': 0,
            'high_count': 0,
            'medium_count': 0,
            'low_count': 0,
            'exposed_secrets': 0,
            'vulnerabilities_closed_this_week': 0,
            'overall_health_score': 0
        }
        
        # Aggregate from different sources
        if 'dependabot' in all_metrics:
            dep = all_metrics['dependabot']
            summary['total_vulnerabilities'] += dep.get('total_open', 0)
            summary['critical_count'] += dep.get('by_severity', {}).get('critical', 0)
            summary['high_count'] += dep.get('by_severity', {}).get('high', 0)
            summary['medium_count'] += dep.get('by_severity', {}).get('medium', 0)
            summary['low_count'] += dep.get('by_severity', {}).get('low', 0)
            summary['vulnerabilities_closed_this_week'] += dep.get('total_closed_this_week', 0)
        
        if 'code_scanning' in all_metrics:
            code = all_metrics['code_scanning']
            summary['total_vulnerabilities'] += code.get('total_open', 0)
            summary['critical_count'] += code.get('by_severity', {}).get('critical', 0)
            summary['high_count'] += code.get('by_severity', {}).get('high', 0)
            summary['medium_count'] += code.get('by_severity', {}).get('medium', 0)
            summary['low_count'] += code.get('by_severity', {}).get('low', 0)
            summary['vulnerabilities_closed_this_week'] += code.get('total_closed_this_week', 0)
        
        if 'secret_scanning' in all_metrics:
            secrets = all_metrics['secret_scanning']
            summary['exposed_secrets'] = secrets.get('total_open', 0)
            summary['vulnerabilities_closed_this_week'] += secrets.get('total_resolved_this_week', 0)
        
        if 'repository_health' in all_metrics:
            health = all_metrics['repository_health']
            summary['overall_health_score'] = health.get('average_compliance_score', 0)
        
        return summary
    
    def _empty_metrics(self) -> Dict[str, Any]:
        """Return empty metrics structure"""
        return {
            'total_open': 0,
            'total_closed_this_week': 0,
            'by_severity': {severity: 0 for severity in self.severity_levels}
        }