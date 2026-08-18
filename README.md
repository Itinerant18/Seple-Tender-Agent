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

Fit labels are produced by the processing pipeline's LLM classifier using the criteria in [Tender Intelligence Skill](./skills/tender-intelligence/SKILL.md). When the LLM is unavailable, the platform records `analysis_model='fallback-regex'` so those non-LLM classifications are visible in the dashboard and can be reviewed by a human.

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

### 1. Environment Setup
Copy `.env.example` to `.env` before running Docker Compose (`.env` is gitignored, so a fresh clone has none and compose will fail without it):

```bash
cp .env.example .env      # then fill it in — see below
```

Minimum variables to fill in inside `.env`:
* **`OPENAI_API_KEY`**: Required for LLM classification (classification won't run without it).
* **`DB_PASSWORD`**: Postgres database password.
* **`HERMES_DASHBOARD_BASIC_AUTH_USERNAME` & `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`**: Mandatory dashboard authentication credentials.
* **`TENDER247_EMAIL` / `TENDER247_PASSWORD` & `TENDER_TIGER_EMAIL` / `TENDER_TIGER_PASSWORD`**: Credentials for Tender247 and TenderTiger sources (GeM requires no credentials).

### 2. Starting Services
Start the core infrastructure and web services:

```bash
docker compose up -d --build db tender-api hermes
```

Once services are up:
* **Dashboard / Tenders Page**: http://localhost:9119 (Basic auth using `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` / `PASSWORD`)
* **Tender API**: http://localhost:8000/api/tenders (`/docs` for Swagger UI)
* **PostgreSQL Database**: `localhost:5432` (`postgres` / `$DB_PASSWORD`, database `tenders` — schema auto-loads on first start)

### 3. Running Scans & Database Population

The database starts empty, so the Tenders page will display "No tenders" until a scan runs.

> [!NOTE]
> `tender-scanner` is deliberately left out of the initial `up` command. It has `RUN_ON_STARTUP=true`, so running `docker compose up -d` with no service list starts a full scan immediately — TenderTiger alone returns ~2700 tenders, each costing a `gpt-4o` call, and fires real Teams/Slack/email alerts to the team.

#### Dev / Testing Scan
For a fresh dev box, run an explicit scan:

```bash
docker compose run --rm -e SCAN_SOURCES=GeM,Tender247 tender-scanner python -m scheduler.run_once
```

To keep notifications off while testing, add blank webhook/SMTP overrides:

```bash
docker compose run --rm -e SCAN_SOURCES=GeM,Tender247 -e SLACK_WEBHOOK_URL= -e TEAMS_WEBHOOK_URL= -e SMTP_USER= -e SMTP_PASS= tender-scanner python -m scheduler.run_once
```

#### Production Daily Scans
For daily automated scans in production, start the `tender-scanner` container:

```bash
docker compose up -d tender-scanner
```

This scans daily at `SCAN_HOUR` and sends out the digest.

### 4. Useful Commands
* **Check service status**: `docker compose ps`
* **Tail API logs**: `docker compose logs -f tender-api`
* **Stop services**: `docker compose down` (add `-v` to also wipe the database)

**Windows (native alternative):** run `scripts/install.ps1` in PowerShell for a Docker-free local setup.

## 📜 Strategic Mandate
SEPLE T AGENT operates as a **Decision Support System**. It empowers human experts by removing the cognitive load of searching and filtering, allowing the team to focus on what matters most: **winning bids**.

---
**Developed and Maintained by the SEPLE T AGENT Engineering Team.**
