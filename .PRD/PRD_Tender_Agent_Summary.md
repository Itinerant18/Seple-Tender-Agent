# Tender Search AI Agent

**From:** Aniket Karmakar · **Date:** 15 July 2026 · 
**Status:** For approval

---

## The problem

Our team manually checks GeM, CPPP, state portals, PSU and bank sites throughout the day, opening every new tender to judge whether it's relevant. Most aren't.

Three things go wrong:

- **We miss tenders.** No one can watch every portal all day. We recently missed the Botanical Survey of India CCTV AMC tender (GEM/2025/B/6723852) — a direct match for our capability.
- **Time is wasted.** Hours go into opening and rejecting irrelevant notices.
- **We find things late.** Late discovery means rushed eligibility checks, OEM authorizations, site surveys, and weaker bids.

The bottleneck isn't preparing bids. It's *finding* the right ones.

---

## What we're proposing

An AI agent that watches our tender sources 24×7 and brings only relevant opportunities to the team.

Every working morning, an **email digest** with the day's relevant tenders. **Instant alerts** for high-value or urgent ones. A **dashboard** to track everything.

For each tender it finds, the agent gives us:

- What it's for, and why it matched us
- Authority, tender number, deadline, value, EMD, location
- Eligibility requirements — and a flag if we look short on any
- Pre-bid meetings and site visits that could disqualify us if missed
- The downloaded documents, and a link to the original
- A rating: **Strong Fit / Needs Review / Low Fit** — with its confidence and reasoning

---

## What it will NOT do

This is a **search assistant, not a decision-maker.** It will never:

register us on a portal · submit a bid · upload documents · pay any fee or EMD · accept terms · email clients or OEMs · negotiate · sign anything · commit us to anything

Every bid/no-bid decision, price, and submission stays with the team, exactly as today. The agent finds and explains. People decide.

We enforce this by design: the agent is simply **not given** the ability to submit, pay, or send. It isn't told not to — it can't.

---

## Two decisions already made

**1. It will show us "maybes."**
If the agent isn't sure, it shows the tender anyway, marked *Needs Review*, with its reasoning. Missing a good tender costs more than glancing at a bad one. It will never stay silent about something it's unsure of.

**2. Past losses don't block future bids.**
The agent learns from our history, but it will never hide a tender just because we lost a similar one before. That judgment stays with the team.

---

## How we'll build it

We already subscribe to **Tender Tiger** and **Tender247**, which aggregate GeM, CPPP, state, PSU, and bank tenders. We'll use those as the main feed and check GeM directly as backup — far faster and safer than scraping ten government sites ourselves.

The agent itself is built on **Hermes**, a free, open-source agent platform we host on our own server. Our data and credentials never leave the company. No licence cost, no vendor lock-in.

| Phase | What happens |
|---|---|
| **0 — Baseline** | Track the current manual process for ~4 weeks so we can prove improvement. Move portal credentials to secure storage. |
| **1 — Core** | Monitoring, matching, summaries, eligibility flags, deadline reminders, morning digest, instant alerts. **Then launch.** |
| **2 — Convenience** | Dashboard, searchable archive, routing to the right team, Excel export. |
| **3 — Learning** | Feedback loop so results improve over time. |

---

## How we'll know it works

Before launch, we test the agent against **15 real tenders the team has already judged** — the ones we pursued, the borderline ones, and the BSI one we missed. If it can't find and correctly rate those, it doesn't launch.

After launch we measure: more relevant tenders found, less time spent searching, earlier discovery, fewer misses. We don't have baseline numbers today — Phase 0 establishes them.

---

## What we need from you

| | |
|---|---|
| **Approval to start** | From those responsible for tendering and automation |
| **Approval to launch** | From the Director, after the agent passes the real-tender test |
| **Decisions needed** | Who receives digests and alerts · what counts as "high value" for an instant alert · which customers are strategic |
| **Timeline** | No fixed deadline. We'd rather it be reliable than fast. |
| **Budget** | To be proposed once scope is confirmed. Software is free; cost is development effort and hosting. |

---

*Questions or corrections — send them to me and I'll fold them into the PRD.*
