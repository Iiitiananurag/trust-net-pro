# 🛡️ TrustNet: Decentralized Trust Network for Open Source

> **Catalyst Problem 5 Submission**  
> Protecting projects from AI slop campaigns without central authority.  
> Built in the open by [Aurix Inc](https://github.com/Aurix-inc).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

---

## 🌟 Why TrustNet?

Most trust systems rely on centralized deny lists (like Ghostty's VOUCHED.td). This creates silos where Project A doesn't know what Project B knows. 

**TrustNet solves this by:**
1. **Graph-Based Trust Propagation:** If Patricia trusts David, and David trusts Sarah, Patricia implicitly trusts Sarah (with decay). No central arbiter needed.
2. **Cross-Repo Campaign Detection:** Uses MinHash LSH to spot near-identical PRs arriving at *multiple* repositories within hours — invisible to single-maintainer views.
3. **Sybil Resistance:** Detects mutual-vouch rings (SCCs) and mass-denouncing farms using volume-discounted reliability scores.
4. **Fair Governance:** Denouncements expire automatically (TTL), and contributors can appeal false flags via API.

---

## 🚀 Quick Start & Live Demo

### 1. Run Locally (Interactive Sandbox)
```bash
git clone https://github.com/Aurix-inc/trustnetnet-bot.git
cd trustnetnet-bot
pip install -r requirements.txt

# Seed with REAL Ghostty data + synthetic adversarial scenarios
python -m simulator.seed --ghostty-vouch-file auto

# Launch FastAPI server with Swagger UI enabled
uvicorn server:app --reload --port 8000