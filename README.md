# 🔭 GitHub Advanced Security Reporter

<div align="center">

![GitHub License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-brightgreen.svg)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-enabled-2088FF?logo=github-actions&logoColor=white)
![Maintenance](https://img.shields.io/badge/maintained-yes-green.svg)

**A comprehensive automated reporting and analytics platform for GitHub Advanced Security — covering Dependabot, Code Scanning, Secret Scanning, and Supply Chain security.**

[Features](#-features) · [Quick Start](#-quick-start) · [Configuration](#-configuration) · [Usage](#-usage) · [Project Structure](#-project-structure)

</div>

---

## 📋 Overview

GitHub Advanced Security Reporter is an enterprise-grade automation platform that transforms raw GitHub security data into structured, actionable intelligence. Designed for security engineers, DevSecOps leads, and engineering managers, it eliminates the manual effort of aggregating vulnerability data across large GitHub organizations and delivers polished, decision-ready reports on a fully automated schedule.

The tool connects directly to the GitHub GraphQL and REST APIs using asynchronous parallel processing, enabling it to collect and consolidate security data across thousands of repositories and hundrerds of organizations in minutes. It covers the full spectrum of GitHub Advanced Security features — Dependabot dependency alerts, Code Scanning findings, Secret Scanning exposures, and Supply Chain posture — and presents this data in three purpose-built Excel report formats: a **Daily Critical Alert Report**, a **Weekly Security Report**, and an **Organization Inventory Report**.

Each report is structured with multiple analytical tabs tailored to different audiences, from executive summaries with high-level KPIs to raw, filterable data exports for hands-on security engineers. Reports are automatically delivered to configured stakeholders via email and can be versioned and archived for trend tracking and compliance evidence.

Beyond reporting, the platform includes an automated risk scoring engine that prioritizes vulnerabilities based on severity, exposure age, and repository impact — helping teams focus remediation effort where it matters most. Repository health checks audit the adoption of GitHub security features across all repositories, surfacing compliance gaps at a glance. All of this runs on GitHub Actions with zero additional infrastructure, making it straightforward to deploy, maintain, and extend.

---

## ✨ Features

### 📅 Daily Security Report

Generated every day, the Daily Report surfaces all new and critical security alerts detected in the last 24 hours. It is designed for rapid triage by security operations teams and includes the following tabs:

| Tab | Description |
|---|---|
| **Executive Summary** | High-level snapshot of the day's alert volume broken down by severity (Critical, High, Medium, Low), exposed secrets count, and alert type (Dependency, Code Scanning). Includes organization metadata and tool information. |
| **Critical Items** | Complete, filterable list of all critical and high-severity alerts raised today, showing alert type, affected repository, severity level, and full vulnerability description — ready for immediate triage. |
| **Exposed Secrets** | Lists all repositories with open Secret Scanning alerts, including the secret type (e.g., `openai_api_key`, `azure_storage_account_key`, `github_personal_access_token`) and the age of the exposure in days. |
| **Pivot Analysis** | Grouped breakdown of critical alert counts by repository, enabling quick identification of which repositories are contributing the highest volume of new issues each day. |

---

### 📊 Weekly Security Report

Generated every week, the Weekly Report provides a comprehensive view of the organization's overall security posture, trends over time, and prioritized remediation guidance. It is structured for both security team review and engineering leadership and includes the following tabs:

| Tab | Description |
|---|---|
| **Executive Summary** | Organization-level security KPIs for the week: total open vulnerabilities by severity, exposed secrets count, SLA timelines, and week-over-week change indicators. |
| **Analysis & Progress** | Trend analysis comparing the current week against the previous week across all vulnerability categories (Total, Critical, High, Medium, Low, Secrets, Remediation), with directional indicators and percentage changes. |
| **Top Risks** | Ranked list of the highest-risk open vulnerabilities across the organization, including alert type, affected repository, severity, package name, CVE reference, summary, age in days, and a direct link to the GitHub alert. |
| **Repository Health** | Per-repository security posture audit showing compliance percentage, Dependabot/Code Scanning/Secret Scanning enablement status and alert counts, total alerts, visibility, primary language, and days since last push. |
| **Recommendations** | Prioritized, SLA-driven action items generated automatically based on the week's findings — covering critical vulnerability remediation, secret rotation, scanning feature enablement, and supply chain hygiene. |
| **Repository Risk Pivot** | Vulnerability severity breakdown per repository (Critical / High / Medium / Low / Total) with a computed risk level rating to support prioritized remediation planning. |
| **Dependabot Details** | Raw export of all open Dependabot alerts across the organization, including repository, state, severity, package name, package ecosystem, CVE, advisory URL, and alert age. |
| **Code Scanning Details** | Raw export of all open Code Scanning alerts, including repository, state, severity level, rule description, scanning tool, affected file path, alert age in days, and a direct link to the alert. |
| **Secret Scanning Details** | Raw export of all open Secret Scanning alerts, including repository, state, secret type, resolution status, push protection bypass flag, age in days, and alert URL. |
| **Supply Chain** | Repository-level supply chain posture summary showing Dependency Review enablement, dependency file presence, Dependency Graph status, and total dependency count per repository. |

---

### 🏢 Organization Inventory Report

Generated on demand or on a scheduled basis, the Organization Inventory Report provides a complete snapshot of the entire GitHub Enterprise landscape — repositories, ownership, security feature adoption, and cross-organization risk concentration. It includes the following tabs:

| Tab | Description |
|---|---|
| **Executive Summary** | Enterprise-wide statistics covering total organizations, total repositories, repository size, activity breakdown (Active / Archived), visibility distribution (Public / Private / Internal), and a full GitHub Advanced Security alert summary by type. |
| **All Repositories** | Full inventory of every repository across all organizations, with 23 attributes per entry: organization, name, full path, description, owner, primary language, visibility, status, fork flag, size, stars, forks, default branch, days since last push, creation date, last update date, last push date, license, GitHub URL, and Dependabot / Code Scanning / Secret Scanning alert counts. |
| **Repository Health** | Cross-organization security feature adoption audit for every repository, showing compliance percentage, Dependabot/Code Scanning/Secret Scanning enablement and alert counts, total alerts, visibility, language, days since last push, and archived/active status. |
| **Organization Risk Pivot** | Aggregated vulnerability counts (Critical / High / Medium / Low / Total) per repository grouped by organization, enabling risk concentration analysis across organizational boundaries. |

---

## 🚀 Quick Start

### Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8+** — [python.org/downloads](https://www.python.org/downloads/)
- **Git** — [git-scm.com](https://git-scm.com/downloads/)
- **GitHub Personal Access Token (PAT)** with `repo`, `security_events`, and `read:org` scopes

> 💡 **Create a PAT:** GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic) → Generate new token.

Clone the repository and create a Python virtual environment as you normally would for any Python project, then proceed with the steps below.

---

### Step 1 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

### Step 2 — Configure Environment Variables

```bash
# Copy the environment template
cp .env.example .env

# Open and edit the file with your settings
nano .env        # macOS/Linux
notepad .env     # Windows
```

#### Required Variables

```env
# ──────────────────────────────────────────
# GitHub Configuration (Required)
# ──────────────────────────────────────────
GITHUB_TOKEN=Your_GitHub_API_Key_here
GITHUB_ORG=Your_ORG_NAME
GITHUB_ENTERPRISE_URL=Your_ENT_URL_NAME

# ──────────────────────────────────────────
# Report Branding & Metadata
# ──────────────────────────────────────────
REPORT_TITLE=GitHub Security Reporter
COMPANY_NAME=Your Company Name
DEVELOPED_BY=Dev Name
TOOL_VERSION=1.0.0
COPYRIGHT_YEAR=2026
COMPANY_WEBSITE=https://company.com
TOOL_GITHUB_REPO=https://github.com/repo/
SUPPORT_EMAIL=support@xyz.com

# ──────────────────────────────────────────
# Email Notifications (Optional)
# ──────────────────────────────────────────
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@example.com
EMAIL_PASSWORD=your-app-password
EMAIL_FROM=security-reporter@example.com
EMAIL_TO=security-team@example.com,manager@example.com
```

---

### Step 3 — Run Your First Report

```bash
# Generate a weekly security report (Excel output)
python main.py weekly

# Generate a daily critical-issue summary
python main.py daily

# Generate the organization & repository inventory report
python main.py orgdata
```

Reports are saved to the `data/reports/` directory by default.

---

## ⚙️ Configuration

For advanced configuration options including custom report schedules, risk scoring weights, repository filters, and SMTP settings, refer to the full documentation:

- 📖 [Setup Guide](docs/SETUP.md)
- 🔧 [Configuration Reference](docs/CONFIGURATION.md)
- 📡 [API Reference](docs/API.md)

---

## 🔄 Automating with GitHub Actions

This project includes pre-built GitHub Actions workflows for fully automated reporting. To enable them:

#### 1. Add Repository Secrets

Navigate to your forked repository → **Settings** → **Secrets and variables** → **Actions**, then add:

| Secret Name | Description |
|---|---|
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions (no action needed) |
| `ORG_SECURITY_TOKEN` | A PAT with `security_events` and `read:org` scopes |
| `EMAIL_USERNAME` | SMTP account username |
| `EMAIL_PASSWORD` | SMTP account password or app-specific password |

#### 2. Enable Workflows

GitHub Actions workflows are located in `.github/workflows/`. They will begin running automatically on the configured schedule once secrets are in place.

| Workflow | Schedule | Purpose |
|---|---|---|
| `weekly-report.yml` | Every Monday 08:00 UTC | Full Excel weekly security report |
| `daily-summary.yml` | Every day 07:00 UTC | Critical daily alert digest |

---

## 📁 Project Structure

```
github-security-reporter/
│
├── .github/
│   └── workflows/              # GitHub Actions automation workflows
│
├── config/                     # Application configuration files
│
├── src/
│   ├── collectors/             # GitHub API data ingestion modules
│   ├── analyzers/              # Metrics computation and trend analysis
│   ├── reporters/              # Report generation (Excel, email, etc.)
│   ├── storage/                # Historical data persistence layer
│   └── utils/                  # Shared utilities and helpers
│
├── scripts/                    # Standalone execution scripts
├── tests/                      # Unit and integration test suite
│
├── data/                       # Generated reports and output files
│   └── reports/                # Daily, Weely and Org security alert reports
│
├── main.py                     # Application entry point
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
└── README.md                   # This file
```

---

## 📄 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for full details.

---

## 🙏 Acknowledgements

Built with:
- [PyGitHub](https://github.com/PyGithub/PyGithub) — GitHub API client for Python
- [OpenPyXL](https://openpyxl.readthedocs.io/) — Excel report generation
- [GitHub Actions](https://github.com/features/actions) — CI/CD automation

---

<div align="center">
  <sub>Made with ❤️ for security-conscious engineering teams.</sub>
</div>
