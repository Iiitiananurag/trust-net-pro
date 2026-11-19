# 🛡️ TrustNet

**Decentralized Open-Source Trust & Reputation Network** — built by **Team AURIX** for **Catalyst 1.0 (Problem 5)**

[![Live Dashboard](https://img.shields.io/badge/Dashboard-Live%20Demo-00c853?style=for-the-badge)](https://trust-net-pro.onrender.com/dashboard)
[![Swagger UI](https://img.shields.io/badge/API%20Docs-Swagger%20UI-2563eb?style=for-the-badge)](https://trust-net-pro.onrender.com/docs)
[![Install GitHub App](https://img.shields.io/badge/GitHub%20App-Install%20Bot-18181b?style=for-the-badge&logo=github)](https://github.com/apps/trustnet-bot/installations/new)

## Overview

**TrustNet** (`Aurix-inc/trustnetnet-bot`) is a decentralized, graph-based reputation and coordinated-spam detection engine for open-source maintainers. Moving beyond isolated, manually maintained deny lists, each repository independently manages its own vouches, denouncements, and peer trust weights—turning single-repo blind spots into shared network visibility without a central authority.

* **Decentralized Trust Propagation:** Projects independently vouch, denounce, and weight peer repositories; trust propagates across the directed graph with hop decay so no central arbiter is required.
* **Cross-Repo Campaign Detection:** Uses MinHash LSH to surface near-identical PRs arriving across multiple repositories within short time windows—patterns invisible to any single maintainer.
* **Sybil Resistance & Fair Governance:** Identifies mutual-vouch rings (strongly connected components) and mass-vouching/denouncing farms via volume-discounted reliability scores, while protecting contributors through automatic denouncement TTL expiry and an appeals API.
* **Built-In Interactive Dashboard:** Served directly by FastAPI at `/dashboard` (`static/dashboard.html`) using Cytoscape.js with live stats, an interactive peer trust mesh, a contributor risk analyzer (`🟢 ⚪ 🔴`), quick-demo personas (`john`, `sarah`, `bot-001`, `sybil-01`), campaign tables, and a Sybil audit panel—requiring zero separate frontend hosting or build step.
* **Flexible, Safe-by-Default Deployment:** Available as a one-click hosted GitHub App (`auto_post_disabled: true` by default), an opt-in GitHub Action (`TRUSTNET_DRY_RUN=true` default), a Render cloud API, or a local Python 3.11+ sandbox seeded with real Ghostty `VOUCHED.td` data and adversarial test suites.
