# Product Requirements Document (PRD)

## Tender Search AI Agent — Tender Intelligence & Discovery Assistant

| | |
|---|---|
| **Document owner** | Aniket Karmakar (Product / Technology) |
| **Business input** | Presales/Tender questionnaire, 15-07-2026 |
| **Company** | Security Engineers Pvt. Ltd. |
| **Version** | 1.1 (Draft for review — adds subscribed aggregator sources and proposed implementation platform) |
| **Date** | 15 July 2026 |
| **Status** | Pending stakeholder review and Director approval |

---

## 1. Executive Summary

Security Engineers Pvt. Ltd. participates in public procurement tenders across India in the domains of electronic security (CCTV/surveillance, access control, biometrics), fire detection and suppression, building management, public address systems, and security & facility management services. Today, tender discovery is a fully manual process: the Presales team monitors GeM, CPPP, state portals, PSU and bank procurement pages throughout the day, opening and reviewing individual notices to judge relevance.

This PRD defines a **Tender Search AI Agent** — an intelligent first-level screening system that continuously monitors designated procurement sources, identifies opportunities matching the company's business profile, extracts and verifies critical details, classifies each opportunity by fit and confidence, and delivers them to the Presales team through a daily digest, instant alerts, and a live tracking dashboard.

The agent is strictly a **decision-support tool**. It finds, reads, classifies, summarizes, and recommends. It never registers, submits, pays, communicates externally, negotiates, or commits on behalf of the company. All bid/no-bid decisions, pricing, and submissions remain under human control.

---

## 2. Problem Statement

### 2.1 Current process

1. The Presales team manually monitors multiple procurement portals (GeM primary, plus CPPP/eProcure, state portals, PSU/bank/department sites) throughout the working day.
2. Each newly published tender is opened and reviewed individually against products, services, technical capability, geography, and commercial objectives.
3. Potentially suitable tenders are forwarded to the approving authority for a bid/no-bid decision.
4. Upon approval, the team prepares a tender synopsis, coordinates Sales, Technical, Finance, and OEM partners, manages pre-bid activities, and prepares and monitors the bid.

### 2.2 Pain points

- **Coverage gaps.** It is impossible to continuously monitor every relevant portal; opportunities are discovered late or missed entirely. A real example: the Botanical Survey of India CCTV AMC tender (GEM/2025/B/6723852) was directly aligned with the company's surveillance AMC capability and was missed (see §12, test case C).
- **Manual effort.** A significant share of Presales time goes to searching, opening, and rejecting irrelevant notices — repetitive, resource-intensive, and error-prone.
- **Compressed decision windows.** Late discovery leaves insufficient time for eligibility assessment, OEM authorizations (MAF), site surveys, pre-bid queries, and competitive bid preparation. Missing a mandatory pre-bid meeting or site visit can mean outright disqualification.

### 2.3 Why automate now

New tenders are published throughout the day across many platforms. The most time-consuming part of the tender lifecycle is not bid preparation — it is discovery and filtering. Automating first-level screening improves coverage, reduces manual effort, and gives the team more preparation time, directly improving bid quality and win probability.

---

## 3. Goals and Non-Goals

### 3.1 Goals

1. **Broader coverage** — monitor all designated procurement sources continuously, including weekends and holidays.
2. **Early discovery** — surface relevant tenders as soon as possible after publication to maximize preparation time.
3. **Intelligent relevance matching** — match on meaning and scope, not just exact keywords (e.g., a CCTV requirement described as "video surveillance," "IP camera system," or "integrated security system" must still be caught).
4. **Structured, verifiable information** — extract key tender parameters with source references so the team can trust and quickly act on the data.
5. **Reduced manual effort** — cut the time spent searching portals and reviewing irrelevant notices.
6. **Transparency** — every recommendation explains why the tender was identified, what matched, which documents were reviewed, and what is confirmed vs. uncertain.
7. **Continuous improvement** — capture user feedback (relevant / pursued / won / ignored) to improve future matching.

### 3.2 Non-Goals (explicitly out of scope)

The agent will **not**:

- Register the company or manage profiles on any portal
- Submit bids or upload documents to portals
- Accept terms and conditions or sign any declaration, undertaking, affidavit, or agreement
- Pay tender fees, EMD, security deposits, or any charge
- Send external communications (clients, OEMs, authorities) — it may draft, never send
- Negotiate prices or contractual terms, or make any commercial commitment
- Schedule meetings or confirm participation with external parties
- Make the final bid/no-bid decision
- Replace the Presales team's business judgment

---

## 4. Users and Stakeholders

| Role | Involvement |
|---|---|
| **Presales / Tender team** | Primary users. Review shortlisted opportunities, perform initial assessment (technical fit, commercial viability, eligibility, timelines, pre-bid activities). |
| **Approving authority / Management** | Receive suitable tenders for formal bid/no-bid decision. Final approval authority. |
| **Sales / Business Development** | Review opportunities relevant to their accounts and territories. |
| **Technical team** | Consulted on technical fit for shortlisted tenders. |
| **Finance** | Consulted on EMD, fees, and commercial terms after shortlisting. |
| **OEM partners** | Downstream (human-managed) — authorizations and MAF requests remain human activities. |
| **Director** | Final approval before launch (see §14). |

Users are comfortable with procurement portals and digital systems, but the solution must remain simple and require minimal interaction. **Email-first** delivery integrates with the existing workflow; the dashboard supplements it.

### 4.1 Expected workflow

```
Agent identifies tender
→ Provides structured details + relevance analysis + confidence
→ Presales reviews and performs initial assessment
→ Suitable tenders go to approving authority for bid/no-bid
→ On approval, Presales initiates bid preparation with Sales / Technical / Finance / OEMs
```

The agent's role ends at the arrow into human review. Everything after is human-controlled.

---

## 5. Tender Sources (Coverage Scope)

| # | Source | Login required | New-tender frequency | Priority |
|---|---|---|---|---|
| 1 | **Tender Tiger** (subscribed aggregator) | Yes — company account | Continuous (aggregates GeM, CPPP, state, PSU, bank portals) | **Highest — primary ingestion channel** |
| 2 | **Tender247** (subscribed aggregator) | Yes — company account | Continuous (aggregates multiple official portals) | **Highest — primary ingestion channel** |
| 3 | Government e-Marketplace (**GeM**) | Yes | Multiple times daily | **Highest — verification + direct coverage** |
| 4 | Central Public Procurement Portal (**CPPP / eProcure**) | Mostly open; some functions need login | Daily | High |
| 5 | State Government e-Procurement portals | Varies by state | Daily | High |
| 6 | PSU procurement portals | Usually open; login for participation | Daily–weekly | High |
| 7 | Public sector bank procurement portals | Usually open | Daily–weekly | High |
| 8 | Government department procurement websites | Usually open | Daily | High |
| 9 | Defence & strategic organization portals | Varies | Daily | High |
| 10 | Corporate procurement portals (where applicable) | Usually requires registration | Occasional | Medium |
| 11 | Tender notification services, consultants, authorized partners | Depends on source | As received | Medium |

**Ingestion strategy (v1.1):** the company holds active subscriptions to **Tender Tiger** and **Tender247**, which already aggregate listings from GeM, CPPP, state, PSU, and bank portals. Phase 1 ingestion is therefore **aggregator-first**: these two services are the primary structured feed (search filters, listings, and parseable email alerts), with GeM/CPPP monitored directly as a verification channel and to catch anything the aggregators miss. Direct scraping of individual government portals is deferred unless a coverage gap is proven. This reduces build effort, fragility, and terms-of-use exposure on official portals.

**Source rules:**

- Official portals are authoritative. Secondary sources (consultants, notification services) are supplementary and never replace the official source.
- Where authentication is required, the agent uses **company-approved credentials solely for searching and retrieving tender information**, in compliance with each portal's terms of use. It must never perform any action that violates portal policy or jeopardizes the organization's account (see §9). **Credentials are never stored in this document, in code, or in configuration files — they are held in a secrets manager and injected at runtime.** The Tender Tiger and Tender247 account credentials currently exist and are held by the Presales team; they must be transferred to the secrets vault during Phase 0, and any credential previously shared over email or chat should be rotated.
- For every tender captured, record: **source portal, publication date, submission deadline, tender reference number, authority name, and direct link** to the original notice/documents.
- The architecture must allow **new portals to be added without significant redevelopment** (pluggable source connectors).

---

## 6. Relevance Model (Filtering & Matching Logic)

A tender is relevant only if it aligns with the company's technical capabilities, business objectives, eligibility criteria, and operational capacity. The agent evaluates each opportunity against technical, commercial, and administrative parameters — **not keyword presence alone**.

### 6.1 Product & service scope

Core business areas the agent matches against:

- CCTV surveillance systems
- Fire detection and fire alarm systems
- Fire suppression systems (clean agent / NOVEC / FK-5)
- Access control and biometric attendance systems
- Integrated electronic security solutions
- Annual Maintenance Contracts (AMC)
- Supply, Installation, Testing & Commissioning (SITC)
- Security manpower services (KAVACH division)
- Cash-in-transit services
- Facility management services

### 6.2 Keyword taxonomy (seed dictionary)

The agent uses the following predefined keyword groups as **signals interpreted in context**, not as strict filters:

| Category | Keywords |
|---|---|
| Video Surveillance | CCTV, Camera, Surveillance, NVR, Server, Switch, VMS, ANPR, 4MP, 2MP, PoE, PTZ, Fiber, Megapixel, HDD |
| Intrusion & Security Alarm | Security Alarm, Burglar Alarm |
| Public Address & Audio | Speaker, Amplifier, Conference, Microphone, Mic, Sound, Audio, Podium, Public Address |
| Access Control & Biometrics | Biometric, Access Control, RFID, Tablet |
| Security Screening | HHMD, DFMD, X-Ray Baggage Scanner System (XBIS) |
| Building Management | Building Management System (BMS) |
| Fire Detection & Alarm | Fire Alarm, Conventional/Addressable/Intelligent Fire Alarm, Smoke Detector, MCP, Detector, Microprocessor, EVAC, Gas Detection, Module, Fire Detection |
| Fire Safety & Suppression | Fire Door, Fire Protection, Fire Fighting, Valve, Pump, Suppression, NOVEC, Clean Agent, Fire Extinguisher, FK-5 |
| Communication & Specialized | Video Door Phone (VDP), Nurse Call System, Turnstile(s), Bollard, Boom Barrier, Visitor Management |
| OEM / Brands | Notifier, Morley, Apollo, ESSER |
| Supporting Infrastructure | WLD, Water Leak Detection, Rodent Detection, Smart Rack, Signage, Talkback, UPS, Interactive Display, Monitor, Walkie Talkie, Guard Tour System, Battery, OFC, CAT6, Installation |
| Security & Facility Services | Security, Manpower, Facility Management, Housekeeping, Guard, Cleaning, Sweeping |

**Semantic matching requirement:** tender language often differs from internal product names. The agent must understand related terminology, abbreviations, and technical descriptions — e.g., a CCTV requirement may appear as *surveillance system, video surveillance, security monitoring, IP camera system, NVR-based system,* or *integrated security system*; fire opportunities may appear as *fire detection, smoke detection,* or *addressable fire alarm systems*.

**Document-level analysis requirement:** titles alone are insufficient. Where available, the agent must analyze tender descriptions, technical specifications, **BOQ**, scope of work, and attached documents to determine suitability.

### 6.3 Other evaluation dimensions

| Dimension | Rule |
|---|---|
| **Geography** | Pan-India participation — geography is **not** a filter. The agent must, however, state the project location and flag location-specific eligibility (local office, regional registration, address proof). |
| **Client profile** | Preference: government departments, PSUs, public sector banks, defence organizations, autonomous bodies, educational/research institutions, airports, ports, and other reputable public organizations. Aligned private-sector opportunities may also be surfaced. |
| **Eligibility** | Identify mandatory qualification criteria: minimum turnover, similar work experience, OEM authorization / MAF, statutory registrations, certifications, financial capacity, local office requirements. **Eligibility gaps must be prominently flagged** — but flagged, not silently filtered out (see §6.5). |
| **Mandatory activities** | Highlight mandatory pre-bid meetings, compulsory site visits, product demonstrations, and other pre-submission requirements — missing these causes automatic disqualification. |
| **Timeline** | Prioritize opportunities with adequate preparation time. High-priority alerts for approaching deadlines. Flag tenders where remaining time makes participation impractical. |
| **Tender value** | No fixed floor/ceiling defined at this stage; value must always be extracted and displayed, and high-value opportunities in core categories trigger instant alerts (§8). |

### 6.4 Fit classification

Every surfaced tender receives one of three fit labels, driven by predefined business rules plus contextual analysis:

| Label | Meaning |
|---|---|
| **Strong Fit** | Clear match with product portfolio, keywords, customer segment, and business areas. Priority attention. |
| **Potential Fit / Needs Human Review** | Partial relevance or uncertainty — unclear product description, multi-system tender where only part matches, unfamiliar terminology, or broad category requiring interpretation. |
| **Low Fit** | Does not match business areas. Deprioritized (available in the repository, not pushed in digests). |

### 6.5 Bias & filtering philosophy — recall over precision

**Missing a good tender is a bigger risk than reviewing an irrelevant one.** Confirmed business decision (Q9):

- When uncertain, the agent must **show the opportunity** under "Needs Human Review" with an explanation — never silently drop it.
- Historical bid outcomes are used to **improve recommendations, not to auto-exclude**. A tender is never filtered out solely because similar opportunities were previously lost or had eligibility issues.
- There is **no artificial cap on daily results**; the priority is quality and accuracy of matching, with enough information per tender for a fast human decision.

---

## 7. Functional Requirements

### 7.1 Core capabilities (Phase 1 — Essential)

| # | Requirement | Priority |
|---|---|---|
| F1 | **Monitor** all §5 sources continuously (including weekends/holidays) and detect newly published tenders and corrigenda. | Essential |
| F2 | **Notify** the team of relevant tenders as early as possible, with a direct link to the original notice. | Essential |
| F3 | **Summarize** each tender: scope of work and major technical requirements, concise enough to assess without opening the full document. | Essential |
| F4 | **Extract key fields**: tendering authority, tender number, publication date, submission deadline, estimated value, EMD, tender fee, exemption status, project location, product category, mandatory pre-bid meeting, mandatory site survey, other milestones. | Essential |
| F5 | **Download & organize** complete tender documents, corrigenda, BOQ, technical specifications, and attachments into a structured repository. | Essential |
| F6 | **Classify fit** as Strong Fit / Potential Fit / Low Fit per §6.4, with confidence level and matching rationale. | Essential |
| F7 | **Assess eligibility** (first pass): identify OEM authorization, turnover, experience, certification, local-office and other mandatory conditions; prominently flag apparent gaps. | Essential |
| F8 | **Track milestones & remind**: pre-bid meetings, site visits, demonstrations, clarification deadlines, submission deadlines — with timely reminders. | Essential |
| F9 | **Generate a tender synopsis** consolidating commercial, technical, and administrative information for internal review and management approval. | Essential |
| F10 | **Explain itself**: for every tender — why identified, which keywords/categories/scope elements matched, which documents were reviewed, what is confirmed vs. uncertain. | Essential |

### 7.2 Phase 2 — Nice to have

| # | Requirement | Priority |
|---|---|---|
| F11 | **Searchable repository** of all identified tenders with status, documents, and evaluation history. Status values: New, Under Review, Submitted, Closed, etc. | Nice to have |
| F12 | **Stakeholder routing**: notify specific people based on business division, product category, or service (e.g., manpower tenders → KAVACH division). | Nice to have |
| F13 | **Export / integration**: export to Excel or integrate with the internal tender tracker to eliminate duplicate data entry. | Nice to have |
| F14 | **Feedback loop**: capture per-tender user feedback (relevant / pursued / won / ignored) and use it to improve future matching. | Nice to have (design for it from day one) |
| F15 | **Historical intelligence**: compare new tenders against previously pursued opportunities (won / lost / ongoing / rejected) to enrich recommendations — never to auto-exclude. | Nice to have |

### 7.3 Required fields per uncertain ("Needs Human Review") tender

- Tender name and authority
- Product/category detected
- Matching keywords or signals
- Reason it may be relevant
- What is uncertain or missing
- Deadline and important dates

---

## 8. Delivery & Notification Design

Three complementary channels:

### 8.1 Daily digest (primary channel — email)

- Sent every **working-day morning** at the start of the day.
- Contains all newly identified relevant tenders since the last digest, each with: tender authority, location, product/category match, tender value, submission deadline, tender type (GeM/other portal), document link, key eligibility requirements, pre-bid meeting/site survey details, and keyword/portfolio match.
- Weekend/holiday discoveries roll into the next working-day digest unless urgent (see 8.2).

### 8.2 Instant alerts

Triggered immediately for:

- **Strong-fit, high-value** opportunities in core categories (CCTV, Fire Alarm/Detection, Security Systems, Access Control, BMS, Fire Suppression, Security Manpower, Facility Management)
- **Strategic customers** or government organizations of interest
- **Short-deadline** tenders requiring quick action
- Important updates (e.g., corrigendum changing a deadline) on tracked tenders

### 8.3 Dashboard / live tracking sheet

- Continuously updated view of all identified opportunities.
- Filterable by: product category, tender authority, location, tender value, submission date, status (New / Under Review / Submitted / Closed…).
- Introduced as a supplement; email remains primary. (Per Q2, the dashboard may follow the email digest in phasing.)

### 8.4 Monitoring schedule

- **Monitoring runs 7 days a week including holidays** (portals publish at any time).
- Digest communication follows the working-day schedule; urgent items break through via instant alerts.

---

## 9. Guardrails, Permissions & Compliance

### 9.1 Prohibited autonomous actions

The agent must **never independently**:

| Activity | Restriction |
|---|---|
| Register the company on any portal | May identify registration requirements only; never create accounts, submit details, accept terms, or represent the company |
| Create/modify/manage portal profiles | All changes to company info, credentials, certifications, catalogues by authorized personnel only |
| Submit any tender bid | Participation decision and submission are always human-controlled |
| Upload documents to portals | May prepare checklists and identify required documents; never upload, replace, or submit |
| Accept portal terms & conditions | Legal agreements/declarations always require human review |
| Pay tender fees, EMD, deposits, or any charge | Never initiate payments, approve transactions, or handle payment credentials |
| Send external emails/communications (clients, OEMs, authorities) | May draft; sending requires human review and approval |
| Commit the company to an opportunity | No participation decisions, confirmations, acceptance letters, or commercial commitments |
| Negotiate prices or contractual terms | Authorized personnel only |
| Sign declarations, undertakings, affidavits, agreements | Authorized representatives only |
| Communicate with OEMs as company representative | May suggest requirements/prepare drafts; never request quotations, authorizations, or commitments |
| Schedule meetings / confirm participation externally | Human-controlled |

**Summary rule:** the agent may *find, read, classify, compare, summarize, and recommend*. It must never *register, submit, pay, communicate externally, negotiate, approve, sign, or commit* on behalf of Security Engineers Pvt. Ltd.

### 9.2 Mandatory human decision points

The agent stops and hands over before:

- Finalizing whether a tender should be pursued
- Judging commercial attractiveness requiring business judgment
- Assessing risk on a strategic customer or project
- Confirming technical compliance where specification interpretation is needed
- Deciding whether deviations/exceptions are acceptable
- Selecting products, OEMs, or technical solutions
- Approving bid pricing or margins
- Confirming resource availability
- Any commitment on delivery, warranty, service levels, or contract terms

### 9.3 Data the agent must not access, store, or process

**Confidential company information:** usernames, passwords, OTPs, credentials, API keys, portal access details; bank/payment details; internal pricing strategies, unpublished cost structures, margin calculations; proprietary designs/drawings/IP not intended for tender evaluation; confidential customer agreements or internal correspondence unless specifically authorized.

**PII:** personal phone numbers, personal email addresses, identification documents, employee personal records, customer personal information. Only business information required for tender evaluation is processed.

**Restricted portal content:** the agent must not scrape beyond permitted access, use unauthorized automation methods, access restricted documents, store content prohibited from download/redistribution, or circumvent security controls, access restrictions, or authentication mechanisms. Only publicly available tender information or officially authorized channels may be used.

### 9.4 Data handling principles

1. **Minimum necessary access** — only what's required to identify and evaluate tenders.
2. **Human accountability** — final decisions, submissions, communications, and commitments rest with authorized employees.
3. **No autonomous external action** — the agent recommends and prepares; it never executes.
4. **Auditability** — records of searches, recommendations, and analysis are maintained.
5. **Transparency** — every recommendation states its sources, matching criteria, and reasoning.

Portal credentials used for authenticated search are handled by authorized systems/personnel per internal security policy; the agent itself must not persist raw credentials.

---

## 10. Confidence & Uncertainty Handling

- The agent never silently ignores a possibly relevant tender. Uncertain items are surfaced as **Potential Match / Needs Human Review** with the fields listed in §7.3.
- Every surfaced tender carries a **confidence level and stated reasons for uncertainty** (e.g., "value not stated in notice; BOQ not yet published").
- Key extracted details (deadline, value, EMD, eligibility) must be **verified against source documents** before presentation; unverifiable fields are marked *uncertain*, never guessed.
- Decision principle: *Agent identifies → explains relevance and confidence → human reviews → team decides.*

---

## 11. Success Metrics

### 11.1 Baseline first

No formal baseline currently exists for monthly discovery hours or missed-tender counts. **The first post-launch objective is to establish a baseline** by tracking the manual process for a defined period, then measure improvement against it.

### 11.2 Measurable parameters

| # | Metric | Direction |
|---|---|---|
| M1 | Relevant tenders identified vs. current manual process | ↑ |
| M2 | Weekly/monthly manual searching & review time | ↓ |
| M3 | Opportunities identified early enough for proper evaluation and participation | ↑ |
| M4 | Accuracy of tender categorization vs. defined categories/keywords | ↑ |
| M5 | Missed tenders due to search limitations or delayed discovery | ↓ |

### 11.3 Qualitative outcomes (3 months post-launch)

More relevant tenders discovered; reduced manual effort; faster identification with more preparation time; improved tracking/visibility in a consistent structured format; fewer missed opportunities; clearer information enabling faster bid/no-bid decisions. The agent is successful if it broadens coverage, cuts repetitive work, and shifts team time from searching to evaluation, qualification, and bid strategy.

---

## 12. Evaluation Plan & Test Cases

The agent will be validated against **real historical tenders already judged by the Presales team** before launch (a Director-approval precondition, §14).

### 12.1 Set A — Pursued / strong-fit tenders (agent must identify and classify as Strong Fit)

| # | Authority | Tender No. | Category / Signals |
|---|---|---|---|
| 1 | ISRO, Sriharikota | GEM/2025/B/6045815 | Fire Detection — fire alarm, smoke detector, module |
| 2 | NALCO, Bhubaneswar | GEM/2025/B/6098096 | CCTV AMC & SITC — CCTV, NVR, HDD, switch |
| 3 | Oil India Ltd., West Bengal | GEM/2025/B/6313270 | Fire Detection & Alarm |
| 4 | NESAC, Meghalaya | GEM/2025/B/6324028 | Smoke Detector & Fire Alarm AMC |
| 5 | IOCL, Bihar | GEM/2025/B/6380763 | Clean Agent — NOVEC, FK-5, suppression |
| 6 | AAI, Odisha | GEM/2025/B/6365354 | CCTV + Biometric Access Control — RFID |
| 7 | SPMCIL, West Bengal | GEM/2025/B/6286564 | Fire Detection AMC |
| 8 | Canara Bank, West Bengal | GEM/2025/B/6368258 | Security Manpower — KAVACH division routing |
| 9 | Balmer Lawrie, West Bengal | GEM/2025/B/5940725 | Fire Detection AMC |

### 12.2 Set B — Relevant-looking but requiring careful evaluation (agent must surface with appropriate caveats, not overstate fit)

| # | Authority | Tender No. | Why careful evaluation was needed |
|---|---|---|---|
| 1 | Indian Navy, Kolkata | GEM/2025/B/6068542 | Product match, but commercial competitiveness/positioning needed assessment |
| 2 | Directorate of Purchase & Stores, Mumbai | GEM/2025/B/6000398 | Technically aligned; specs and execution feasibility needed review |
| 3 | IOCL, Bihar | GEM/2025/B/6351214 | Relevant; technical/commercial viability review needed |
| 4 | HPCL, Hyderabad | GEM/2025/B/6561152 | Relevant benchmark opportunity |
| 5 | AAI, Raipur | GEM/2025/B/6524683 | Scope, competition, and commercial feasibility needed review |

### 12.3 Set C — Missed & regretted (the headline test)

| Authority | Tender No. | Category |
|---|---|---|
| Botanical Survey of India, West Bengal | GEM/2025/B/6723852 | CCTV System AMC |

**Pass condition:** in a historical replay, the agent identifies this tender promptly after publication, classifies it Strong Fit, and flags its milestones — demonstrating the early-discovery value that motivated the project.

### 12.4 Validation criteria

The agent passes pre-launch validation if it can, on these cases and a broader replay window:

1. Identify tenders across all keyword groups in §6.2 including semantic variants
2. Classify Set A as Strong Fit and Set C as Strong Fit (early)
3. Surface Set B with correct caveats rather than overconfident recommendations
4. Extract key fields (§7.1 F4) accurately with source references
5. Correctly flag eligibility requirements and mandatory pre-bid activities
6. Produce explanations (§7.1 F10) a Presales reviewer judges as accurate and useful

The same sets become the **regression suite**: every change to matching logic or keyword taxonomy is re-validated against them before deployment.

---

## 13. Risks and Mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **Missed important tender** (not identified, or surfaced too late) | Highest — unrecoverable after deadline | Recall-over-precision bias (§6.5); continuous 7-day monitoring; multi-source redundancy; "Needs Human Review" bucket; missed-tender metric M5; Set C regression test |
| R2 | **Incorrect/incomplete information** (deadline, scope, eligibility, value) leading to bad bid decisions | High | Verification of key details against source documents before presentation; source references on every field; confidence levels; uncertain fields marked, never guessed |
| R3 | **Incorrect classification** (wrong product/business area) | Medium-high | Semantic + document-level analysis (§6.2); explanation requirement (F10); user feedback loop (F14); categorization-accuracy metric M4 |
| R4 | **Unauthorized action** by the agent | High (commercial/legal) | Hard prohibition list (§9.1); read-only portal interaction; no payment/submission capability built at all; audit logs |
| R5 | **Portal terms-of-use or data-policy violation**; account blocked | High (operational/compliance) | §9.3 restrictions; approved credentials used only for search/retrieval; rate-respectful access; per-portal compliance review before onboarding a source |
| R6 | **Alert fatigue / ignored digests** | Medium | Fit-tiered delivery (§8); instant alerts reserved for defined triggers; feedback loop to tune relevance |
| R7 | **Stale corrigenda** (deadline changed after capture) | Medium | Continuous re-check of tracked tenders; corrigendum alerts (§8.2) |

### Safety checks (required in the build)

- Clear source references for every identified tender
- Verification of key details before presenting
- Confidence levels with reasons for uncertainty
- Human review before any business decision or action
- Audit logs of information collected and analysis performed
- Strict access controls and secure handling of company data

---

## 14. Constraints, Approvals & Governance

| Area | Constraint |
|---|---|
| **Timeline** | No fixed deadline. Timeline driven by development effort, testing with real tender examples (§12), validation, and reliability — **reliability, security, and workflow alignment take priority over speed of deployment**. |
| **Budget** | No ceiling defined. To be evaluated against proposed solution, expected value, implementation effort, and ongoing operating cost. |
| **Data storage & security** | Must follow internal data security requirements. Confidential business/bid/customer/commercial information, credentials, and internal documents stored and handled securely. Store only what is necessary; respect portal terms of use. |
| **Approval — before development** | Approval from personnel responsible for tendering and automation initiatives; agreement on scope, objectives, access requirements, and data handling approach. |
| **Approval — before launch** | **Final approval from the Director**, plus validation against real tender examples confirming accuracy, usefulness, and guardrail compliance (§12). |

---

## 15. Phasing (Proposed)

| Phase | Contents | Exit criteria |
|---|---|---|
| **Phase 0 — Baseline & setup** | Track current manual process to establish baseline metrics (M1–M5); finalize source list, credentials, and per-portal compliance review; freeze keyword taxonomy v1 | Baseline documented; sources approved |
| **Phase 1 — Core discovery (Essential, F1–F10)** | **Aggregator-first ingestion**: Tender Tiger + Tender247 as primary feeds, GeM/CPPP direct as verification channel; extraction, summarization, fit classification, eligibility flagging, milestone reminders, synopsis, daily digest + instant alerts | Passes §12 validation; Director approval; launch |
| **Phase 2 — Repository & routing (F11–F13)** | Searchable repository with statuses; stakeholder routing by division/category; Excel export / tracker integration; dashboard | Adopted by Presales in daily workflow |
| **Phase 3 — Learning loop (F14–F15)** | Feedback capture (relevant / pursued / won / ignored); historical-bid intelligence for enriched (never exclusionary) recommendations | Measurable improvement in M4 over ≥1 quarter |

---

## 16. Open Questions

| # | Question | Owner |
|---|---|---|
| O1 | Final list of state e-procurement portals and specific PSU/bank/defence portals for Phase 1 vs. later phases | Presales (Aniket) |
| O2 | Which internal tender tracker/system should F13 integrate with, and its format | Presales + Debayan |
| O3 | Definition of "large-value" per category for instant-alert thresholds (§8.2), and the strategic-customer list | Presales / Management |
| O4 | Named recipients for digests, alerts, and division-based routing (e.g., KAVACH) | Presales / Management |
| O5 | Who administers portal credentials and under what internal policy | IT / Security |
| O6 | Baseline-tracking window length for Phase 0 (suggested: 4 weeks) | Presales |
| O7 | Retention period for downloaded tender documents and audit logs | Management / IT |
| O8 | Handling of consultant/notification-service inputs (email parsing? manual forward?) | Presales |
| O9 | Do Tender Tiger and/or Tender247 offer an official API or structured export (Excel/RSS/email alert) under our subscription tier? API access removes the need for browser automation on these services. | Debayan (to check with both vendors) |
| O10 | Do the Tender Tiger / Tender247 subscription terms permit automated retrieval? Confirm before Phase 1 build. | Debayan / Presales |
| O11 | Credential rotation and vault transfer for Tender Tiger / Tender247 accounts (Phase 0 task). | IT / Security |

---

## 17. Glossary

| Term | Meaning |
|---|---|
| **GeM** | Government e-Marketplace — primary tender source |
| **CPPP / eProcure** | Central Public Procurement Portal |
| **EMD** | Earnest Money Deposit |
| **BOQ** | Bill of Quantities |
| **SITC** | Supply, Installation, Testing & Commissioning |
| **AMC** | Annual Maintenance Contract |
| **MAF** | Manufacturer Authorization Form/Letter |
| **OEM** | Original Equipment Manufacturer |
| **Pre-bid meeting** | Mandatory meeting before bid submission; missing it can disqualify |
| **Corrigendum** | Official amendment to a published tender |
| **Bid/no-bid** | Formal internal decision on whether to pursue a tender |
| **KAVACH** | Company division handling security manpower services |

---

## 18. Appendix — Approved Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│  SOURCES: GeM · CPPP · State portals · PSU/Bank/Dept sites  │
│           Defence portals · Corporate · Consultants         │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
                 ┌──────────────────┐
                 │  AI AGENT        │  monitors 24×7
                 │  find · read ·   │  extracts + verifies
                 │  classify ·      │  Strong / Potential / Low fit
                 │  summarize ·     │  eligibility + milestone flags
                 │  recommend       │  confidence + reasoning
                 └────────┬─────────┘
                          ▼
        ┌────────────────────────────────────┐
        │  DELIVERY: morning digest (email)  │
        │  instant alerts · dashboard/sheet  │
        └────────────────┬───────────────────┘
                         ▼
              ┌────────────────────┐
              │  PRESALES REVIEW   │  human judgment begins here
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │  BID / NO-BID      │  approving authority
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │  BID PREPARATION   │  Sales · Technical · Finance · OEM
              └────────────────────┘

  The agent NEVER crosses below the delivery line:
  no registration · no submission · no payment · no external
  communication · no negotiation · no signing · no commitment.
```

---

## 19. Proposed Implementation Approach — Hermes Agent (v1.1)

### 19.1 Platform under evaluation

The team proposes building on **Hermes Agent** (NousResearch, open source, MIT license) as the agent runtime, rather than developing an agent loop from scratch.

### 19.2 Why Hermes fits this PRD

| PRD requirement | Hermes capability |
|---|---|
| Self-hosted; internal data security (§14) | Fully self-hostable on company infrastructure; data stays in-house; MIT license permits commercial use and modification |
| Continuous monitoring + morning digest (§8.1, F1) | Built-in cron scheduler for recurring jobs |
| Email-first delivery + instant alerts (§8) | Native messaging gateway: Email, Slack, Telegram, WhatsApp, and others from one process |
| Keyword taxonomy, relevance rules, synopsis format (§6, F9) | Skills system — business rules encoded as versioned, editable skill documents |
| Feedback loop / learning over time (F14, Phase 3) | Built-in learning loop: creates and refines skills from experience, captures usage feedback |
| Model flexibility / no lock-in | Supports Anthropic, OpenAI, AWS Bedrock, local models and others; switchable without code changes |
| Audit logs (§9.4) | Conversation and action history persisted; supplemented by pipeline-level audit logging (19.4) |

### 19.3 What Hermes does NOT provide (must be built)

Hermes is a general agent runtime, not a tender pipeline. The following components are custom builds around it:

1. **Ingestion connectors** — authenticated retrieval and parsing of listings from Tender Tiger, Tender247, and GeM. This is the largest single build item.
2. **Tender database** — structured store with cross-source **deduplication** (the same tender will appear on GeM and both aggregators), status lifecycle, document repository, corrigendum detection, and audit log. Hermes memory is conversational and does not replace this.
3. **Deterministic extraction & verification layer** — key fields (deadline, value, EMD, eligibility) parsed with rules and verified against source documents per §10; the LLM classifies and summarizes, it does not guess facts.
4. **Dashboard / tracking sheet** (§8.3) — separate lightweight frontend over the tender database.
5. **Hard guardrail enforcement** — §9.1 prohibitions are enforced at the tool level: the Hermes instance is provisioned with **read-only connectors only**. No payment, upload, form-submission, registration, or external-send capability is installed at all — prohibition by absence, not by instruction.

### 19.4 Target architecture

```
  Tender Tiger ─┐
  Tender247 ────┼── Ingestion & parsing layer (custom, authenticated,
  GeM (verify) ─┘    read-only, rate-respectful)
                          │
                          ▼
              Tender Database & Document Repository
              (dedup · status · corrigenda · audit log)
                          │
                          ▼
                   HERMES AGENT (self-hosted)
        classification (Strong/Potential/Low fit) · eligibility
        flagging · summary & synopsis generation · confidence +
        reasoning · cron digests · instant alerts via email/Slack
                          │
                          ▼
                    Presales team review
              (human judgment begins here — §9)
```

### 19.5 Conditions and risks of this approach

- **Aggregator dependency:** Phase 1 relies on Tender Tiger/Tender247 coverage and account continuity. Mitigation: GeM direct monitoring as verification channel; subscription renewals tracked; O9/O10 resolved before build.
- **Open-source project risk:** Hermes is actively developed but externally maintained. Mitigation: pin to a tested release; the custom pipeline (ingestion, DB, dashboard) is framework-independent and survives a future runtime swap.
- **Guardrail verification:** §12 validation must include negative tests confirming the agent cannot perform any §9.1 prohibited action.

---

## 20. Change Log

| Version | Date | Changes |
|---|---|---|
| 1.0 | 15-07-2026 | Initial PRD from completed stakeholder questionnaire (Aniket Karmakar, R&N) |
| 1.1 | 15-07-2026 | Added Tender Tiger and Tender247 as subscribed primary ingestion sources (§5); aggregator-first Phase 1 strategy (§15); credential-handling rule; open questions O9–O11; proposed implementation approach on Hermes Agent (§19) |

---

*Prepared by Debayan from the completed PRD questionnaire (Aniket Karmakar, R&N, 15-07-2026). Pending stakeholder review; changes will be versioned.*
