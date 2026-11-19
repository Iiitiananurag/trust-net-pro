# 🛡️ TrustNet: Decentralized Trust Network or Open Source

> **Catalyst Problem 5 Submission**  
> Protecting projects from AI slop campaigns without central authority.  
> Built in the open by [Aurix Inc](https://github.com/Aurix-inc).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

---
## 🌟Click for the [Release Notes](./Description.md)
The description is given here


## 🌟 Why TrustNet?

Most trust systems rely on centralized deny lists (like Ghostty's VOUCHED.td). This creates silos where Project A doesn't know what Project B knows. 

**TrustNet solves this by:**
1. **Graph-Based Trust Propagation:** If Patricia trusts David, and David trusts Sarah, Patricia implicitly trusts Sarah (with decay). No central arbiter needed.
2. **Cross-Repo Campaign Detection:** Uses MinHash LSH to spot near-identical PRs arriving at *multiple* repositories within hours — invisible to single-maintainer views.
3. **Sybil Resistance:** Detects mutual-vouch rings (SCCs) and mass-denouncing farms using volume-discounted reliability scores.
4. **Fair Governance:** Denouncements expire automatically (TTL), and contributors can appeal false flags via API.

---

## 🚀 Quick Start &Live Demo

### Option A: Use the Hosted GitHub App (Zero Setup)

Install TrustNet on your own repositories in one click:

👉 **[Install TrustNet Bot](https://github.com/apps/trustnet-bot/installations/new)**

1. Click the link above and choose the repositories to protect.
2. Open (or reopen) a pull request — TrustNet analyzes the contributor automatically.
3. The analysis covers: transitive trust score, cross-repo campaign membership, and Sybil-ring flags — each with human-readable evidence.

> 🛡️ **Safe by default:** The hosted webhook returns structured analysis JSON and does **not** auto-post comments (`auto_post_disabled: true`) until persistent storage is connected. To enable PR comments via GitHub Actions instead, set repo variables `TRUSTNET_DRY_RUN=false` and `TRUSTNET_ALLOW_SELF_REPO=1` (see [Compliance](#-hackathon-compliance-checklist)).

### Option B: Run Locally (Interactive Sandbox)

Why run locally? To reproduce our test results yourself, explore the API interactively, or develop against the engine without depending on the cloud instance.

#### 🪟 Windows (PowerShell)
```powershell
git clone https://github.com/Aurix-inc/trustnetnet-bot.git
cd trustnetnet-bot

# Create isolated environment (recommended)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Seed with REAL Ghostty data + synthetic adversarial scenarios
python -m simulator.seed --ghostty-vouch-file auto

# Launch API server
uvicorn server:app --reload --port 8000
```

#### 🍎 macOS (Terminal / zsh)
```bash
git clone https://github.com/Aurix-inc/trustnetnet-bot.git
cd trustnetnet-bot

# Requires Python 3.11+ (brew install python@3.11 if needed)
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python3 -m simulator.seed --ghostty-vouch-file auto
uvicorn server:app --reload --port 8000
```

#### 🐧 Linux (bash)
```bash
git clone https://github.com/Aurix-inc/trustnetnet-bot.git
cd trustnetnet-bot

# Debian/Ubuntu: sudo apt install python3.11 python3.11-venv
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
python3 -m simulator.seed --ghostty-vouch-file auto
uvicorn server:app --reload --port 8000
```

#### Verify It Works (All Platforms)
```bash
# In a second terminal (keep the server running in the first):
curl http://localhost:8000/health          # -> {"status":"ok"}
curl http://localhost:8000/campaigns       # -> detected bot cluster with evidence
curl http://localhost:8000/sybil-check     # -> Sybil analysis result

# Run the full adversarial test suite:
python -m tests.test_trust                 # -> ALL TRUST TESTS PASSED
python -m tests.test_campaigns             # -> ALL CAMPAIGN TESTS PASSED
```

👉 **Open Interactive Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)  
*(Try `/analyze-pr`, `/campaigns`, `/sybil-check` live in your browser!)*

> 💡 **Platform notes:**
> - On macOS/Linux use `python3`; on Windows use `python`. Inside an activated venv, plain `python` works everywhere.
> - Run scripts as modules (`python -m simulator.seed`, `python -m tests.test_trust`) from the repo root — running files directly (e.g., `python simulator/seed.py`) breaks package imports.
> - If port 8000 is busy, change `--port 8000` to any free port.

### Option C: View Cloud Instance (Render Deployment)
Our production instance runs on Render free tier:  
🔗 **[Health Check](https://trust-net-pro.onrender.com/health)** | 🔗 **[Swagger UI](https://trust-net-pro.onrender.com/docs)**

> ⚠️ Free-tier instances sleep after inactivity — first request may take ~50 seconds to wake. Cloud storage is ephemeral; writes are disabled by default (`TRUSTNET_ALLOW_WRITES=false`). See [Threat Model](#-threat-model--design-rationale).

### 🎨 Interactive Dashboard (No Extra Hosting Required)

Skip Swagger UI for demos — use our purpose-built dark-mode control panel served directly by FastAPI:

👉 **[Open TrustNet Dashboard](https://trust-net-pro.onrender.com/dashboard)** | Local: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

**What you'll see:**
- **Live stats bar**: Projects, trust edges, detected campaigns, Sybil accounts (updates on every API call)
- **Interactive trust graph**: Drag-and-zoom Cytoscape.js mesh showing decentralized peer-to-peer trust (patricia=red, ghostty=green, arrow thickness = weight)
- **Contributor analyzer**: Type any handle + viewer → instant risk card 🟢⚪🔴 with score, evidence lines, and Sybil flags
- **Quick-demo buttons**: One-click load of test personas (`john`, `sarah`, `bot-001`, `sybil-01`) to contrast genuine vs. adversarial behavior
- **Campaign table**: All detected clusters with burst/freshness evidence, sortable columns
- **Sybil panel**: Flagged farms, named ring members, and heuristic evidence

> 💡 **Why not Netlify/Vercel?** The dashboard is a single static HTML file served by FastAPI itself (`/dashboard` → `FileResponse`). Zero CORS config, no separate deployment, same-origin fetches to `/trust-graph` and `/campaigns`. Push once → both API and UI update together on Render. Perfect for demo day reliability.



| **Dashboard UI** | `static/dashboard.html` | Self-contained Cytoscape.js + vanilla JS frontend; served via `/dashboard` endpoint; zero external hosting or build step. |
