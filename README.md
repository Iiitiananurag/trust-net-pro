# 🛡️ MeshyTrust: Decentralized Trust Network for Open Source

> **Catalyst Problem 5 Submission**  
> Protecting projects from AI slop campaigns without central authority.  
> Built in the open by [Your Name/Org].

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