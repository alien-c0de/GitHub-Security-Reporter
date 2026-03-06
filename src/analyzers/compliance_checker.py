"""
Compliance checking and validation
"""
from typing import Dict, List, Any
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

class ComplianceChecker:
    """
    Check compliance with security policies
    """
    
    def __init__(self):
        self.required_features = settings.get_config('compliance.required_features', [
            'dependabot',
            'code_scanning',
            'secret_scanning',
            'branch_protection'
        ])
        self.target_coverage = settings.get_config('compliance.target_coverage', 0.9)
    
    def check_repository_compliance(self, repo_health: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if repository meets compliance requirements
        
        Args:
            repo_health: Repository health data
            
        Returns:
            Compliance status
        """
        compliance_issues = []
        passed_checks = []
        
        # Check each required feature
        feature_checks = {
            'dependabot': repo_health.get('dependabot_enabled', False),
            'code_scanning': repo_health.get('code_scanning_enabled', False),
            'secret_scanning': repo_health.get('secret_scanning_enabled', False),
            'branch_protection': repo_health.get('branch_protection_enabled', False),
        }
        
        for feature, enabled in feature_checks.items():
            if feature in self.required_features:
                if enabled:
                    passed_checks.append(f"{feature} enabled")
                else:
                    compliance_issues.append(f"{feature} not enabled")
        
        # Check for security policy
        if not repo_health.get('has_security_policy', False):
            compliance_issues.append("No SECURITY.md file")
        else:
            passed_checks.append("Security policy present")
        
        # Check branch protection details
        if repo_health.get('branch_protection_enabled'):
            bp_details = repo_health.get('branch_protection_details', {})
            
            if bp_details.get('required_approving_review_count', 0) < 1:
                compliance_issues.append("Branch protection: No required reviews")
            
            if not bp_details.get('require_code_owner_reviews', False):
                compliance_issues.append("Branch protection: Code owner reviews not required")
        
        # Calculate compliance score
        total_checks = len(self.required_features) + 1  # +1 for security policy
        passed = total_checks - len(compliance_issues)
        compliance_score = passed / total_checks
        
        is_compliant = compliance_score >= self.target_coverage
        
        return {
            'repository': repo_health.get('repository'),
            'is_compliant': is_compliant,
            'compliance_score': round(compliance_score, 2),
            'compliance_percentage': round(compliance_score * 100, 2),
            'passed_checks': passed_checks,
            'compliance_issues': compliance_issues,
            'target_coverage': self.target_coverage
        }
    
    def check_organization_compliance(self, all_repo_health: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check overall organization compliance
        
        Args:
            all_repo_health: List of all repository health data
            
        Returns:
            Organization compliance status
        """
        total_repos = len(all_repo_health)
        compliant_repos = 0
        non_compliant_repos = []
        
        feature_coverage = {
            'dependabot': 0,
            'code_scanning': 0,
            'secret_scanning': 0,
            'branch_protection': 0,
            'security_policy': 0
        }
        
        for repo in all_repo_health:
            repo_compliance = self.check_repository_compliance(repo)
            
            if repo_compliance['is_compliant']:
                compliant_repos += 1
            else:
                non_compliant_repos.append({
                    'repository': repo.get('repository'),
                    'issues': repo_compliance['compliance_issues'],
                    'score': repo_compliance['compliance_score']
                })
            
            # Track feature coverage
            if repo.get('dependabot_enabled'):
                feature_coverage['dependabot'] += 1
            if repo.get('code_scanning_enabled'):
                feature_coverage['code_scanning'] += 1
            if repo.get('secret_scanning_enabled'):
                feature_coverage['secret_scanning'] += 1
            if repo.get('branch_protection_enabled'):
                feature_coverage['branch_protection'] += 1
            if repo.get('has_security_policy'):
                feature_coverage['security_policy'] += 1
        
        # Calculate percentages
        for feature in feature_coverage:
            feature_coverage[feature] = {
                'count': feature_coverage[feature],
                'total': total_repos,
                'percentage': round((feature_coverage[feature] / total_repos * 100), 2) if total_repos > 0 else 0
            }
        
        org_compliance_rate = (compliant_repos / total_repos) if total_repos > 0 else 0
        
        return {
            'total_repositories': total_repos,
            'compliant_repositories': compliant_repos,
            'non_compliant_repositories': total_repos - compliant_repos,
            'compliance_rate': round(org_compliance_rate, 2),
            'compliance_percentage': round(org_compliance_rate * 100, 2),
            'meets_target': org_compliance_rate >= self.target_coverage,
            'target_coverage': self.target_coverage,
            'feature_coverage': feature_coverage,
            'non_compliant_repos': sorted(non_compliant_repos, key=lambda x: x['score'])[:10]
        }