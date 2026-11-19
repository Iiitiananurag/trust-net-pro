import os
import hmac
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.campaigns import detect_campaigns_detailed, detect_sybil_rings, contributor_history
from engine.contracts import AnalysisReport, AppealRequest, PREvent, TrustEdge
from engine.db import connect, ensure_account, ensure_project, init_db, upsert_pr_and_author
from engine.trust import DEFAULT_DENOUNCE_TTL_DAYS, classify, score_contributor

# --- CONFIGURATION ---
ALLOW_WRITES = os.getenv("TRUSTNET_ALLOW_WRITES", "false").lower() == "true"
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
APP_ID = os.getenv("GITHUB_APP_ID", "5827025")
PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY", "")
PRIVATE_KEY_PATH = os.getenv(
    "GITHUB_PRIVATE_KEY_PATH", 
    r"D:\dekstop\catalyst\trustnet\trustnet-bot.2026-11-18.private-key.pem"
)

# Load GitHub Integration lazily
try:
    from github import Github, GithubIntegration
    if not PRIVATE_KEY and os.path.exists(PRIVATE_KEY_PATH):
        with open(PRIVATE_KEY_PATH, "r") as f:
            PRIVATE_KEY = f.read()
    integration = GithubIntegration(APP_ID, PRIVATE_KEY) if (APP_ID and PRIVATE_KEY) else None
except Exception as e:
    print(f"Warning: Could not load GitHub App credentials. {e}")
    integration = None

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    # Auto-seed benchmark data if DB is empty (first boot after deploy)
    try:
        conn = connect()
        count = conn.execute("SELECT COUNT(*) FROM pull_requests").fetchone()[0]
        if count == 0:
            print("\U0001f331 Empty DB detected - auto-seeding benchmark data...")
            from simulator.seed import seed
            seed(malicious_b=False, include_sybil_ring=True, ghostty_vouch_file="auto")
        conn.close()
    except Exception as e:
        print(f"Auto-seed failed (will retry on next request): {e}")
    yield

app = FastAPI(title="Decentralized Trust Network API (Catalyst Problem 5)", lifespan=lifespan)

# --- SECURITY: RESTRICT CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:5500"], # Update when you have a real frontend
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- PYDANTIC MODELS ---
class VouchRequest(BaseModel):
    project: str
    account: str
    reason: str = ""

class DenounceRequest(BaseModel):
    project: str
    account: str
    reason: str = ""
    ttl_days: int = Field(default=DEFAULT_DENOUNCE_TTL_DAYS, ge=1, le=3650)

class AppealDecision(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")

# --- ROUTES ---

@app.get("/health")
def health():
    return {"status": "ok", "bot": "alive"}

@app.post("/analyze-pr", response_model=AnalysisReport)
def analyze_pr(
    event: PREvent,
    viewer: Optional[str] = Query(default=None, description="Viewing repository perspective; defaults to event.repo"),
    decay: float = Query(default=1.0, ge=0.1, le=1.0),
):
    conn = connect()
    try:
        # 1. Persist incoming PR/issue so live submissions participate in cross-repo detection
        upsert_pr_and_author(
            conn,
            pr_id=event.pr_id,
            repo_id=event.repo,
            author_id=event.author,
            title=event.title,
            body=event.body,
            diff=event.diff,
            created_at=event.opened_at.isoformat(),
            author_created_at=event.author_created_at.isoformat() if event.author_created_at else None,
        )
        
        perspective = viewer or event.repo
        
        # 2. Check cross-repository coordinated campaigns
        campaigns = detect_campaigns_detailed(conn, min_cluster_size=3)
        matched_campaign = None
        for camp in campaigns:
            if event.author in camp["accounts"]:
                matched_campaign = camp
                break
                
        # 3. Check Sybil rings & trust farms
        sybil = detect_sybil_rings(conn)
        sybil_flagged = event.author in sybil["sybil_accounts"]
        
        # 4. Score contributor from the requesting repository's own trust graph
        score, has_signals, evidence = score_contributor(conn, perspective, event.author, decay=decay)
        risk = classify(score, has_signals)
        
        # 5. Inject campaign and Sybil evidence
        campaign_id = None
        campaign_details = None
        if matched_campaign:
            campaign_id = matched_campaign["id"]
            risk = "elevated"
            evidence.append(f"âš  Coordinated campaign ({campaign_id}): {matched_campaign['evidence_summary']}")
            campaign_details = {
                "size": matched_campaign["size"],
                "pr_count": matched_campaign["pr_count"],
                "repo_count": matched_campaign["repo_count"],
                "repos": matched_campaign["repos"][:10],
                "time_span_hours": matched_campaign["time_span_hours"],
                "is_burst": matched_campaign["is_burst"],
                "new_account_ratio": matched_campaign["new_account_ratio"],
            }
            
        if sybil_flagged:
            risk = "elevated"
            evidence.append(
                "âš  Sybil risk: account is vouched exclusively by a suspicious trust farm or mutual-vouch ring"
            )
            
        # 6. Persistent behavioral history (past campaigns, rings, external flags)
        hist = contributor_history(conn, event.author)

        for pc in hist["past_campaigns"]:
            if pc["id"] != campaign_id:
                risk = "elevated"
                evidence.append(
                    f"[!] Prior campaign history: member of {pc['id']} - {pc['summary']}"
                )

        if hist["ring_members"]:
            risk = "elevated"
            evidence.append(
                "[!] Mutual-vouch ring: cycles with " + ", ".join(hist["ring_members"][:8])
            )

        for d in hist["external_denounces"]:
            if d["project"] == "ghostty":
                evidence.append(
                    f"[FLAG] GHOSTTY: publicly denounced on Ghostty's VOUCHED.td ({d['reason']})"
                )
                if not has_signals:
                    risk = "elevated"
            elif d["project"] != perspective:
                evidence.append(
                    f"[i] Advisory: denounced by '{d['project']}' ({d['reason']}) - "
                    "not weighted unless you declare trust in that project"
                )

        confidence = 0.9 if (matched_campaign or sybil_flagged) else (0.8 if has_signals else 0.2)
        
        return AnalysisReport(
            pr_id=event.pr_id,
            contributor=event.author,
            viewer=perspective,
            trust_score=round(score, 4),
            risk=risk,
            confidence=confidence,
            evidence=evidence,
            campaign_id=campaign_id,
            sybil_flagged=sybil_flagged,
            campaign_details=campaign_details,
        )
    finally:
        conn.close()

@app.get("/campaigns")
def get_campaigns():
    conn = connect()
    try:
        return detect_campaigns_detailed(conn, min_cluster_size=3)
    finally:
        conn.close()

@app.get("/contributor/{account_id}")
def get_contributor(
    account_id: str,
    viewer: str = Query(default="patricia", description="Viewing project perspective"),
    decay: float = Query(default=1.0, ge=0.1, le=1.0),
):
    conn = connect()
    try:
        score, has_signals, evidence = score_contributor(conn, viewer, account_id, decay=decay)
        sybil = detect_sybil_rings(conn)
        sybil_flagged = account_id in sybil["sybil_accounts"]
        risk = "elevated" if sybil_flagged else classify(score, has_signals)
        if sybil_flagged:
            evidence.append("âš  Sybil risk: account flagged in Sybil/trust-farm analysis")
        return {
            "viewer": viewer,
            "account": account_id,
            "score": round(score, 4),
            "risk": risk,
            "sybil_flagged": sybil_flagged,
            "evidence": evidence,
        }
    finally:
        conn.close()

@app.post("/trust-edge")
def upsert_trust_edge(edge: TrustEdge):
    """Allow each project to independently declare which peer projects it trusts and by how much."""
    if edge.src == edge.dst:
        raise HTTPException(status_code=400, detail="A project cannot add a trust edge to itself")
    conn = connect()
    try:
        ensure_project(conn, edge.src)
        ensure_project(conn, edge.dst)
        conn.execute(
            "INSERT OR REPLACE INTO trust_edges (src, dst, weight) VALUES (?, ?, ?)",
            (edge.src, edge.dst, edge.weight),
        )
        conn.commit()
        return {"status": "saved", "src": edge.src, "dst": edge.dst, "weight": edge.weight}
    finally:
        conn.close()

@app.get("/trust-graph")
def get_trust_graph():
    """Return the decentralized project-to-project trust graph for visualization."""
    conn = connect()
    try:
        edges_rows = conn.execute("SELECT src, dst, weight FROM trust_edges").fetchall()
        node_ids = set()
        edges = []
        for r in edges_rows:
            node_ids.add(r["src"])
            node_ids.add(r["dst"])
            edges.append({"data": {"source": r["src"], "target": r["dst"], "weight": r["weight"]}})
        nodes = [{"data": {"id": pid}} for pid in sorted(node_ids)]
        return {"nodes": nodes, "edges": edges, "edge_count": len(edges)}
    finally:
        conn.close()

@app.post("/vouch")
def add_vouch(req: VouchRequest):
    if not ALLOW_WRITES:
        raise HTTPException(503, "Writes disabled; set TRUSTNET_ALLOW_WRITES=true after connecting persistent storage")
    conn = connect()
    try:
        ensure_project(conn, req.project)
        ensure_account(conn, req.account)
        conn.execute(
            "INSERT OR REPLACE INTO vouches (project_id, account_id, reason, created_at) VALUES (?,?,?,?)",
            (req.project, req.account, req.reason, datetime.now().isoformat()),
        )
        conn.commit()
        return {"status": "vouched"}
    finally:
        conn.close()

@app.post("/denounce")
def add_denounce(req: DenounceRequest):
    if not ALLOW_WRITES:
        raise HTTPException(503, "Writes disabled; set TRUSTNET_ALLOW_WRITES=true after connecting persistent storage")
    conn = connect()
    try:
        now = datetime.now()
        expires_at = (now + timedelta(days=req.ttl_days)).isoformat()
        ensure_project(conn, req.project)
        ensure_account(conn, req.account)
        conn.execute(
            """
            INSERT OR REPLACE INTO denounces (project_id, account_id, reason, created_at, expires_at)
            VALUES (?,?,?,?,?)
            """,
            (req.project, req.account, req.reason, now.isoformat(), expires_at),
        )
        conn.commit()
        return {"status": "denounced", "expires_at": expires_at}
    finally:
        conn.close()

@app.post("/appeal")
def submit_appeal(req: AppealRequest):
    """Allow a contributor to appeal a denouncement from a specific project."""
    if not ALLOW_WRITES:
        raise HTTPException(503, "Writes disabled; set TRUSTNET_ALLOW_WRITES=true after connecting persistent storage")
    conn = connect()
    try:
        ensure_project(conn, req.project)
        ensure_account(conn, req.account)
        cur = conn.execute(
            """
            INSERT INTO denounce_appeals (project_id, account_id, reason, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (req.project, req.account, req.reason, datetime.now().isoformat()),
        )
        conn.commit()
        return {"status": "pending", "appeal_id": cur.lastrowid}
    finally:
        conn.close()

@app.post("/appeal/{appeal_id}/resolve")
def resolve_appeal(appeal_id: int, decision: AppealDecision):
    if not ALLOW_WRITES:
        raise HTTPException(503, "Writes disabled; set TRUSTNET_ALLOW_WRITES=true after connecting persistent storage")
    conn = connect()
    try:
        cur = conn.execute(
            "UPDATE denounce_appeals SET status=? WHERE id=?",
            (decision.status, appeal_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Appeal not found")
        return {"appeal_id": appeal_id, "status": decision.status}
    finally:
        conn.close()

@app.get("/sybil-check")
def check_sybil():
    conn = connect()
    try:
        return detect_sybil_rings(conn)
    finally:
        conn.close()

@app.get("/campaigns-graph")
def campaigns_graph():
    conn = connect()
    try:
        campaigns = detect_campaigns_detailed(conn, min_cluster_size=3)
        out = []
        for camp in campaigns:
            nodes = [{"data": {"id": acc}} for acc in camp["accounts"]]
            # Cap rendered edges to keep Cytoscape snappy on large dense cliques while keeping real similarity edges
            real_edges = [
                {
                    "data": {
                        "source": e["source"],
                        "target": e["target"],
                        "weight": e["weight"],
                    }
                }
                for e in camp["edges"][:150]
            ]
            out.append(
                {
                    "id": camp["id"],
                    "nodes": nodes,
                    "edges": real_edges,
                    "size": camp["size"],
                    "pr_count": camp["pr_count"],
                    "repo_count": camp["repo_count"],
                    "time_span_hours": camp["time_span_hours"],
                    "is_burst": camp["is_burst"],
                    "evidence_summary": camp["evidence_summary"],
                }
            )
        return out
    finally:
        conn.close()

# --- GITHUB APP WEBHOOK HANDLER ---
@app.post("/webhook")
async def github_webhook(request: Request):
    body_bytes = await request.body()
    
    # 1. Verify Signature (Security)
    if WEBHOOK_SECRET:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig_header, expected):
            raise HTTPException(status_code=403, detail="Invalid signature")
    
    data = json.loads(body_bytes)
    event_type = request.headers.get("X-GitHub-Event")
    
    if event_type != "pull_request":
        return {"message": "Ignored"}

    action = data.get("action")
    if action not in ["opened", "reopened"]:
        return {"message": "Ignored"}

    pr = data["pull_request"]
    author = pr["user"]["login"]
    pr_number = pr["number"]
    repo_full_name = data["repository"]["full_name"]
    installation_id = data["installation"]["id"]

    print(f"Processing PR #{pr_number} by {author} in {repo_full_name}")

    conn = connect()
    try:
        # 2. Persist PR so it participates in future cross-repo detection
        upsert_pr_and_author(
            conn,
            pr_id=f"{repo_full_name}#{pr_number}",
            repo_id=repo_full_name,
            author_id=author,
            title=pr.get("title", ""),
            body=pr.get("body", "") or "",
            diff="",  # Diff requires extra API call; skip for speed in webhook
            created_at=pr["created_at"],
            author_created_at=pr["user"].get("created_at"),
        )
        
        campaigns = detect_campaigns_detailed(conn, min_cluster_size=3)
        sybil = detect_sybil_rings(conn)
        score, has_signals, evidence = score_contributor(conn, repo_full_name, author)
    finally:
        conn.close()

    # 3. Determine Risk
    matched_campaign = next((c for c in campaigns if author in c["accounts"]), None)
    sybil_flagged = author in sybil["sybil_accounts"]
    
    risk = "elevated" if (matched_campaign or sybil_flagged) else classify(score, has_signals)
    
    # 4. Format Comment
    risk_emoji = {"low": "ðŸŸ¢", "neutral": "âšª", "elevated": "ðŸ”´"}[risk]
    body_md = f"## {risk_emoji} TrustNet Analysis\n\n"
    body_md += f"**Risk:** {risk.upper()} | **Score:** {score:.2f}\n\n"
    
    if matched_campaign:
        body_md += f"âš ï¸ **ALERT ({matched_campaign['id']}):** {matched_campaign['evidence_summary']}\n"
    elif sybil_flagged:
        body_md += "âš ï¸ **SYBIL ALERT:** Account linked to suspicious trust farm/ring.\n"
    elif evidence:
        body_md += "**Evidence:**\n" + "\n".join([f"- {e}" for e in evidence]) + "\n"
    else:
        body_md += "No significant trust signals found. Proceed with standard review.\n"

    # 5. Post Comment via GitHub App
    if integration:
        try:
            installation = integration.get_access_token(installation_id)
            gh = Github(installation.token)
            repo_obj = gh.get_repo(repo_full_name)
            issue = repo_obj.get_issue(pr_number)
            issue.create_comment(body_md)
            print(f"Comment posted to PR #{pr_number}")
        except Exception as e:
            print(f"Failed to post comment: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        print("GitHub App not configured. Comment not posted.")

    return {"status": "ok"}

# --- GITHUB APP WEBHOOK HANDLER (SAFE MODE) ---

def _format_analysis_markdown(risk, score, evidence, campaign, sybil_flagged):
    """Helper to generate markdown without posting it."""
    emoji = {"low": "🟢", "neutral": "⚪", "elevated": "🔴"}[risk]
    lines = [f"## {emoji} TrustNet Analysis\n", f"**Risk:** {risk.upper()} | **Score:** {score:.2f}\n"]
    if campaign:
        lines.append(f"⚠️ **ALERT ({campaign['id']}):** {campaign['evidence_summary']}\n")
    elif sybil_flagged:
        lines.append("⚠️ **SYBIL ALERT:** Account linked to suspicious trust farm/ring.\n")
    elif evidence:
        lines.append("**Evidence:**\n" + "\n".join([f"- {e}" for e in evidence]) + "\n")
    else:
        lines.append("No significant trust signals found. Proceed with standard review.\n")
    return "\n".join(lines)



@app.get("/contributor/{account_id}/history")
def get_history(account_id: str):
    conn = connect()
    try:
        return contributor_history(conn, account_id)
    finally:
        conn.close()


# --- VISUAL TRUST GRAPH (Cytoscape.js) ---
from fastapi.responses import HTMLResponse

@app.get("/graph-view", response_class=HTMLResponse)
def graph_view():
    return """
<!DOCTYPE html>
<html>
<head>
  <title>TrustNet - Trust Graph</title>
  <script src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
  <style>
    body { margin: 0; font-family: sans-serif; background: #f7fafc; }
    h3 { margin: 8px; text-align: center; color: #1a365d; }
    #cy { width: 100vw; height: 90vh; }
    #stats { text-align: center; color: #4a5568; font-size: 13px; }
  </style>
</head>
<body>
  <h3>TrustNet: Decentralized Project-to-Project Trust Graph</h3>
  <div id="stats">Loading...</div>
  <div id="cy"></div>
  <script>
    fetch('/trust-graph').then(r => r.json()).then(g => {
      document.getElementById('stats').textContent =
        g.nodes.length + ' projects, ' + g.edge_count + ' trust edges (arrow thickness = weight)';
      cytoscape({
        container: document.getElementById('cy'),
        elements: { nodes: g.nodes, edges: g.edges },
        style: [
          { selector: 'node', style: {
              'label': 'data(id)', 'background-color': '#2b6cb0',
              'color': '#1a365d', 'font-size': 10, 'text-valign': 'bottom',
              'width': 22, 'height': 22 } },
          { selector: 'node[id = "patricia"]', style: { 'background-color': '#e53e3e', 'width': 34, 'height': 34 } },
          { selector: 'node[id = "ghostty"]', style: { 'background-color': '#38a169', 'width': 34, 'height': 34 } },
          { selector: 'edge', style: {
              'curve-style': 'bezier', 'target-arrow-shape': 'triangle',
              'line-color': '#a0aec0', 'target-arrow-color': '#a0aec0',
              'width': 'mapData(weight, 0, 1, 1, 6)',
              'label': 'data(weight)', 'font-size': 8, 'color': '#718096' } }
        ],
        layout: { name: 'cose', animate: false },
        wheelSensitivity: 0.2
      });
    });
  </script>
</body>
</html>
"""


# --- CUSTOM DASHBOARD UI ---
from fastapi.responses import FileResponse
from pathlib import Path as _Path

@app.get("/dashboard", response_class=FileResponse)
def dashboard():
    return FileResponse(_Path(__file__).parent / "static" / "dashboard.html")
