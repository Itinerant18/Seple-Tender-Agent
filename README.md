<p align="center">
  <img src="assets/banner.png" alt="SEPLE T AGENT" width="100%">
</p>

# SEPLE T AGENT ☤

**The Next-Generation Autonomous Tender Intelligence & Discovery System**

SEPLE T AGENT is a sophisticated, self-improving AI ecosystem designed to dominate the procurement landscape. It automates the entire lifecycle of tender discovery, classification, and deep technical analysis, serving as the primary intelligence engine for **Security Engineers Pvt. Ltd. (SEPLE)**. 

Built with a focus on **semantic precision** and **autonomous decision support**, this agent ensures that every relevant opportunity in electronic security, fire protection, and facility management is captured, analyzed, and delivered with surgical accuracy.

## 🚀 The Intelligence Engine

SEPLE T AGENT is not just a scraper; it is a cognitive assistant that understands the nuance of procurement.

*   **Autonomous Discovery**: Continuously monitors aggregator feeds (TenderTiger, Tender247) and primary portals (GeM, CPPP, State Portals) 24/7.
*   **Semantic Reasoning Engine**: Leverages advanced LLMs guided by a proprietary [Tender Intelligence Skill](./skills/tender-intelligence/SKILL.md) to interpret intent, matching "video surveillance" to CCTV portfolios even when keywords don't overlap.
*   **Deep Document Analysis**: Automatically parses complex NITs, Technical Specifications, and BOQs to extract mandatory eligibility, turnover requirements, and MAF needs.
*   **Closed Learning Loop**: Learns from human feedback (Relevant / Pursued / Won) to refine its classification logic over time, building a deepening model of the company's strategic interests.

## 🏗️ Technical Architecture

The system is built on a modular, high-performance stack designed for reliability and scale:

| Component | Technical Excellence |
|-----------|----------------------|
| **Tender MCP Bridge** | A custom [Model Context Protocol server](./tender_mcp/server.py) that exposes the tender database as native tools for the AI. |
| **Cognitive Skills** | Proprietary [logic modules](./skills/tender-intelligence/SKILL.md) defining the company's technical DNA and matching heuristics. |
| **Resilient Connectors** | High-reliability scrapers using Playwright with session persistence to navigate complex WAF-protected portals. |
| **Processing Pipeline** | An asynchronous pipeline for [classification](./processor/classifier.py), [eligibility extraction](./processor/eligibility_checker.py), and [synopsis generation](./processor/synopsis_generator.py). |
| **Intelligence Dashboard** | A high-performance [React-based UI](./web/src/pages/TendersPage.tsx) for real-time pipeline monitoring and strategic review. |

## 🛠️ Key Capabilities

*   **Zero-Miss Discovery**: A recall-first philosophy ensures "Potential Fits" are surfaced for human review rather than being silently dropped.
*   **Milestone Automation**: Automatically identifies and tracks pre-bid meetings, site visits, and submission deadlines.
*   **Multi-Channel Communication**: Integrated notification system that delivers instant alerts and detailed tender summaries directly via **Slack** and **Email**, ensuring the team can act within hours of publication.
*   **Proprietary Knowledge Base**: Builds a historical repository of tenders, corrigenda, and outcomes to support long-term business development.

## ⚙️ Configuration & Deployment

### Strategic Environment
The system is designed to run in isolated, high-security environments, leveraging encrypted secrets for portal access:
```bash
# Core Intelligence Configuration
DATABASE_URL=postgresql://...
TENDER_API_URL=http://tender-api:8000

# Portal Access (Managed via Secrets Vault)
TENDER_TIGER_CREDENTIALS=...
TENDER_247_API_KEY=...
```

### Deployment
SEPLE T AGENT supports containerized deployment for maximum uptime and scalability across cloud and local infrastructure.

**Windows (native):** run `scripts/install.ps1` in PowerShell for a Docker-free local setup.

## 📜 Strategic Mandate
SEPLE T AGENT operates as a **Decision Support System**. It empowers human experts by removing the cognitive load of searching and filtering, allowing the team to focus on what matters most: **winning bids**.

---
**Developed and Maintained by the SEPLE T AGENT Engineering Team.**
