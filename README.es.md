<p align="center">
  <img src="assets/banner.png" alt="SEPLE T AGENT" width="100%">
</p>

# SEPLE T AGENT ☤

**The Autonomous Tender Intelligence & Discovery Agent for Security Engineers Pvt. Ltd.**

SEPLE T AGENT is a specialized, white-labeled version of the [Hermis Agent](https://hermes-agent.nousresearch.com/), customized to automate the end-to-end lifecycle of procurement tender discovery, classification, and analysis. It serves as a decision-support tool for the Presales and Tender teams, ensuring that no relevant opportunity is missed across the vast landscape of Indian procurement portals.

## 🚀 Overview

In the complex domain of electronic security, fire protection, and facility management, discovering relevant tenders is a resource-intensive manual task. SEPLE T AGENT automates this by:
*   **Continuous Monitoring**: Scanning aggregator sources like TenderTiger and Tender247, alongside official portals like GeM and CPPP.
*   **Intelligent Classification**: Using LLMs guided by a specialized [Tender Intelligence Skill](./skills/tender-intelligence/SKILL.md) to match opportunities against SEPLE's core capabilities.
*   **Deep Analysis**: Extracting technical requirements, eligibility criteria, and mandatory milestones (pre-bid meetings, site visits) from tender documents.
*   **Structured Reporting**: Delivering daily digests, instant alerts, and a live dashboard for bid/no-bid decision support.

## 🏗️ Architecture

SEPLE T AGENT extends the modular Hermis architecture with tender-specific components:

| Component | Description |
|-----------|-------------|
| **Tender MCP Server** | A dedicated [MCP server](./tender_mcp/server.py) bridging the agent to the tender database and pipeline tools. |
| **Custom Skill** | The [Tender Intelligence Skill](./skills/tender-intelligence/SKILL.md) defining classification rules, keyword taxonomy, and company profile. |
| **Connectors** | Specialized scrapers for [TenderTiger](./connectors/tender_tiger.py), [Tender247](./connectors/tender247.py), and direct portal access. |
| **Processor Pipeline** | Modules for [classification](./processor/classifier.py), [eligibility checking](./processor/eligibility_checker.py), and [synopsis generation](./processor/synopsis_generator.py). |
| **Web Dashboard** | A tailored [React interface](./web/src/pages/TendersPage.tsx) for tracking pipeline status and reviewing identified tenders. |

## 🛠️ Key Features

*   **Semantic Matching**: Goes beyond keywords to understand the intent and scope of work (e.g., matching "IP camera system" to CCTV capabilities).
*   **Recall-First Philosophy**: Prioritizes not missing a good tender over filtering out irrelevant ones, surfacing "Potential Fits" for human review.
*   **Automated Document Analysis**: Reads and summarizes NITs, Technical Specifications, and BOQs to extract mandatory requirements.
*   **Milestone Tracking**: Automatically identifies and tracks critical dates like pre-bid meetings and submission deadlines.
*   **Multi-Channel Alerts**: Delivers findings via Slack, Email, and the internal Dashboard.

## ⚙️ Setup & Configuration

### Environment Variables
The agent requires credentials for the primary aggregator sources and database:
```bash
# Aggregator Credentials
TENDER_TIGER_EMAIL=...
TENDER_TIGER_PASSWORD=...
TENDER_247_API_KEY=...

# Database & API
DATABASE_URL=postgresql://...
TENDER_API_URL=http://tender-api:8000
```

### Configuration
Primary agent settings are defined in `cli-config.seple.yaml`. This file gates the agent's behavior, ensuring it operates strictly as a read-only decision-support tool.

## 📈 Usage

### Starting the Agent
```bash
# Start the interactive tender assistant
hermes --config cli-config.seple.yaml
```

### Running a Scan
Scans are typically scheduled via cron, but can be triggered manually:
```bash
# Trigger a discovery scan across all sources
python -m scheduler.run_once
```

### Accessing the Dashboard
The web interface is available at the configured dashboard port (default: 3000). It provides a high-level overview of the pipeline:
*   **Total Tenders Found**
*   **Strong Fit vs. Potential Fit counts**
*   **Source-wise distribution**
*   **Direct links to portal notices**

## 📜 Compliance & Non-Goals
As per **PRD §3.2**, the agent is strictly a decision-support tool. It will **never**:
*   Register or manage profiles on portals.
*   Submit bids or upload documents.
*   Pay tender fees or EMDs.
*   Make final bid/no-bid decisions.

---
**Built for Security Engineers Pvt. Ltd. by the SEPLE T AGENT Development Team.**
