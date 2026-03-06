"""
Risk scoring and prioritization
"""
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

class RiskScorer:
    """
    Calculate risk scores for vulnerabilities and repositories
    """
    
    def __init__(self):
        # Severity weights
        self.severity_weights = {
            'critical': 10,
            'high': 7,
            'medium': 4,
            'low': 2
        }
        
        # Age multipliers (older = higher risk)
        self.age_thresholds = {
            7: 1.0,    # < 1 week
            30: 1.5,   # < 1 month
            90: 2.0,   # < 3 months
            180: 3.0,  # < 6 months
            365: 4.0,  # < 1 year
        }
    
    def calculate_vulnerability_risk_score(self, vulnerability: Dict[str, Any]) -> float:
        """
        Calculate risk score for a single vulnerability
        
        Args:
            vulnerability: Vulnerability data
            
        Returns:
            Risk score (0-100)
        """
        # Base score from severity
        severity = vulnerability.get('severity', 'low').lower()
        base_score = self.severity_weights.get(severity, 1)
        
        # Age multiplier
        age_days = vulnerability.get('age_days', 0)
        age_multiplier = self._get_age_multiplier(age_days)
        
        # CVSS score bonus (if available)
        cvss_score = vulnerability.get('cvss_score', 0)
        cvss_bonus = cvss_score / 10 if cvss_score else 0
        
        # Calculate final score
        risk_score = (base_score * age_multiplier) + cvss_bonus
        
        # Normalize to 0-100
        normalized_score = min(risk_score * 10, 100)
        
        return round(normalized_score, 2)
    
    def calculate_repository_risk_score(self, repo_vulnerabilities: List[Dict[str, Any]], 
                                       repo_health: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate overall risk score for a repository
        
        Args:
            repo_vulnerabilities: List of vulnerabilities in repository
            repo_health: Repository health data
            
        Returns:
            Risk assessment dictionary
        """
        if not repo_vulnerabilities:
            return {
                'risk_score': 0,
                'risk_level': 'low',
                'vulnerability_count': 0,
                'critical_count': 0,
                'high_count': 0,
                'compliance_score': repo_health.get('compliance_score', 0),
                'factors': []
            }
        
        # Calculate individual vulnerability scores
        vuln_scores = [
            self.calculate_vulnerability_risk_score(v) 
            for v in repo_vulnerabilities
        ]
        
        # Count by severity
        severity_counts = {
            'critical': len([v for v in repo_vulnerabilities if v.get('severity') == 'critical']),
            'high': len([v for v in repo_vulnerabilities if v.get('severity') == 'high']),
            'medium': len([v for v in repo_vulnerabilities if v.get('severity') == 'medium']),
            'low': len([v for v in repo_vulnerabilities if v.get('severity') == 'low'])
        }
        
        # Base score from vulnerabilities
        avg_vuln_score = sum(vuln_scores) / len(vuln_scores)
        
        # Compliance penalty
        compliance_score = repo_health.get('compliance_score', 1.0)
        compliance_penalty = (1 - compliance_score) * 20
        
        # Critical vulnerability penalty
        critical_penalty = severity_counts['critical'] * 15
        
        # High vulnerability penalty
        high_penalty = severity_counts['high'] * 5
        
        # Calculate final score
        total_score = avg_vuln_score + compliance_penalty + critical_penalty + high_penalty
        final_score = min(total_score, 100)
        
        # Determine risk level
        risk_level = self._determine_risk_level(final_score)
        
        # Risk factors
        factors = self._identify_risk_factors(
            severity_counts, 
            compliance_score, 
            repo_vulnerabilities
        )
        
        return {
            'risk_score': round(final_score, 2),
            'risk_level': risk_level,
            'vulnerability_count': len(repo_vulnerabilities),
            'critical_count': severity_counts['critical'],
            'high_count': severity_counts['high'],
            'medium_count': severity_counts['medium'],
            'low_count': severity_counts['low'],
            'compliance_score': compliance_score,
            'factors': factors
        }
    
    def prioritize_vulnerabilities(self, vulnerabilities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prioritize vulnerabilities by risk score
        
        Args:
            vulnerabilities: List of vulnerabilities
            
        Returns:
            Sorted list with risk scores
        """
        # Calculate risk scores
        for vuln in vulnerabilities:
            vuln['risk_score'] = self.calculate_vulnerability_risk_score(vuln)
        
        # Sort by risk score (descending)
        sorted_vulns = sorted(vulnerabilities, key=lambda x: x['risk_score'], reverse=True)
        
        return sorted_vulns
    
    def identify_top_risks(self, vulnerabilities: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Identify top risks across all vulnerabilities
        
        Args:
            vulnerabilities: List of vulnerabilities
            limit: Number of top risks to return
            
        Returns:
            Top risks
        """
        prioritized = self.prioritize_vulnerabilities(vulnerabilities)
        return prioritized[:limit]
    
    def _get_age_multiplier(self, age_days: int) -> float:
        """Get age multiplier based on vulnerability age"""
        for threshold, multiplier in sorted(self.age_thresholds.items()):
            if age_days < threshold:
                return multiplier
        return 5.0  # > 1 year
    
    def _determine_risk_level(self, score: float) -> str:
        """Determine risk level from score"""
        if score >= 80:
            return 'critical'
        elif score >= 60:
            return 'high'
        elif score >= 40:
            return 'medium'
        else:
            return 'low'
    
    def _identify_risk_factors(self, severity_counts: Dict[str, int], 
                              compliance_score: float,
                              vulnerabilities: List[Dict[str, Any]]) -> List[str]:
        """Identify specific risk factors"""
        factors = []
        
        if severity_counts['critical'] > 0:
            factors.append(f"{severity_counts['critical']} critical vulnerabilities")
        
        if severity_counts['high'] > 5:
            factors.append(f"High vulnerability count ({severity_counts['high']})")
        
        if compliance_score < 0.5:
            factors.append(f"Low compliance score ({compliance_score*100:.0f}%)")
        
        # Check for old vulnerabilities
        old_vulns = [v for v in vulnerabilities if v.get('age_days', 0) > 90]
        if old_vulns:
            factors.append(f"{len(old_vulns)} vulnerabilities older than 90 days")
        
        # Check for exposed secrets
        secrets = [v for v in vulnerabilities if v.get('secret_type')]
        if secrets:
            factors.append(f"{len(secrets)} exposed secrets")
        
        return factors