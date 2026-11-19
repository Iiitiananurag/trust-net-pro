import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from github import Github

from engine.campaigns import detect_campaigns_detailed, detect_sybil_rings
from engine.db import connect, init_db, upsert_pr_and_author
from engine.trust import classify, score_contributor


def format_comment(report):
    risk_emoji = {"low": "🟢", "neutral": "⚪", "elevated": "🔴"}[report["risk"]]
    viewer = report.get("viewer", "local")
    lines = [
        f"## {risk_emoji} Trust Network Analysis",
        f"**Viewer:** `{viewer}` | **Risk:** {report['risk'].upper()} | **Score:** {report['trust_score']:.2f}",
        "",
        "**Evidence:**",
    ]
    if not report["evidence"]:
        lines.append("- No signals yet (newcomers are treated neutrally)")
    else:
        for ev in report["evidence"]:
            lines.append(f"- {ev}")

    if report.get("campaign_id"):
        lines.append("")
        summary = report.get("campaign_summary") or "Coordinated cross-repository campaign detected."
        lines.append(f"⚠ **ALERT ({report['campaign_id']}):** {summary}")

    if report.get("sybil_flagged"):
        lines.append("")
        lines.append("⚠ **SYBIL ALERT:** Account is linked to a suspicious trust farm or mutual-vouch ring.")

    if report.get("synthetic_demo"):
        lines.append("")
        lines.append("> *Note: Evaluated against synthetic benchmark data for demonstration.*")

    lines.append("")
    lines.append("---")
    lines.append("*Powered by Catalyst Problem 5 — Decentralized Trust Network*")
    return "\n".join(lines)


def _analyze_via_api(api_url, payload, viewer):
    url = f"{api_url.rstrip('/')}/analyze-pr?viewer={viewer}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    details = data.get("campaign_details") or {}
    summary = None
    if data.get("campaign_id"):
        summary = (
            f"{details.get('size', '?')} accounts submitted "
            f"{details.get('pr_count', '?')} similar PRs across "
            f"{details.get('repo_count', '?')} repos."
        )
    return {
        "viewer": data.get("viewer", viewer),
        "risk": data["risk"],
        "trust_score": data["trust_score"],
        "evidence": data.get("evidence", []),
        "campaign_id": data.get("campaign_id"),
        "campaign_summary": summary,
        "sybil_flagged": data.get("sybil_flagged", False),
    }


def _analyze_locally(pr_id, repo_name, author, title, body, diff, opened_at, viewer):
    init_db()
    conn = connect()
    synthetic_demo = False
    try:
        pr_count = conn.execute("SELECT COUNT(*) FROM pull_requests").fetchone()[0]
        if pr_count == 0 and os.environ.get("SEED_DEMO_DB") == "1":
            conn.close()
            from simulator.seed import seed
            seed(False)
            conn = connect()
            synthetic_demo = True

        upsert_pr_and_author(
            conn,
            pr_id=pr_id,
            repo_id=repo_name,
            author_id=author,
            title=title,
            body=body,
            diff=diff,
            created_at=opened_at,
        )

        campaigns = detect_campaigns_detailed(conn, min_cluster_size=3)
        matched = next((c for c in campaigns if author in c["accounts"]), None)
        sybil = detect_sybil_rings(conn)
        sybil_flagged = author in sybil["sybil_accounts"]
        score, has, ev = score_contributor(conn, viewer, author)
    finally:
        conn.close()

    risk = "elevated" if (matched or sybil_flagged) else classify(score, has)
    if matched:
        ev = ev + [f"Campaign {matched['id']}: {matched['evidence_summary']}"]
    return {
        "viewer": viewer,
        "risk": risk,
        "trust_score": score,
        "evidence": ev,
        "campaign_id": matched["id"] if matched else None,
        "campaign_summary": matched["evidence_summary"] if matched else None,
        "sybil_flagged": sybil_flagged,
        "synthetic_demo": synthetic_demo,
    }


def main():
  def main():
    # === SAFETY GATE: Default to DRY RUN unless explicitly opted-in ===
    DRY_RUN = os.environ.get("TRUSTNET_DRY_RUN", "true").lower() == "true"
    
    if DRY_RUN:
        print("\n" + "=" * 70)
        print("🛡️  TRUSTNET DRY-RUN MODE (default)")
        print("=" * 70)
        print("This tool will NOT post comments to GitHub.")
        print("To enable live posting, set TRUSTNET_DRY_RUN=false AND")
        print("add the target repo to ALLOWED_REPOS env var.")
        print("=" * 70 + "\n")
    
    # Mock mode for local testing
    if os.environ.get("MOCK_GITHUB") == "1":
        print("MOCK MODE: Generating comment for 'bot-001'...")
        init_db()
        conn = connect()
        try:
            campaigns = detect_campaigns_detailed(conn, min_cluster_size=3)
            matched = next((c for c in campaigns if "bot-001" in c["accounts"]), None)
            sybil = detect_sybil_rings(conn)
            sybil_flagged = "bot-001" in sybil["sybil_accounts"]
            score, has, ev = score_contributor(conn, "patricia", "bot-001")
        finally:
            conn.close()
        
        report = {
            "viewer": "patricia",
            "risk": "elevated" if (matched or sybil_flagged) else classify(score, has),
            "trust_score": score,
            "evidence": ev + ([matched["evidence_summary"]] if matched else []),
            "campaign_id": matched["id"] if matched else None,
            "campaign_summary": matched["evidence_summary"] if matched else None,
            "sybil_flagged": sybil_flagged,
            "synthetic_demo": True,
        }
        print("\n" + "=" * 50)
        print(format_comment(report))
        print("=" * 50 + "\n")
        return
    
    # Real GitHub Actions mode
    token = os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("GITHUB_REPOSITORY")
    pr_number = int(os.environ.get("PR_NUMBER", 0))
    
    if not token or not repo_name or not pr_number:
        print("Error: Missing GITHUB_TOKEN, GITHUB_REPOSITORY, or PR_NUMBER")
        sys.exit(1)
    
    allowed_repos = {
        r.strip().lower()
        for r in os.environ.get("ALLOWED_REPOS", "").split(",")
        if r.strip()
    }
    allow_self = os.environ.get("TRUSTNET_ALLOW_SELF_REPO") == "1"
    
    # Double safety check even outside dry-run
    if not DRY_RUN and not allow_self and repo_name.lower() not in allowed_repos:
        print(
            f"Safety guard: '{repo_name}' is not in ALLOWED_REPOS. "
            "Set ALLOWED_REPOS (or TRUSTNET_ALLOW_SELF_REPO=1 on your own sandbox repo) to post comments."
        )
        sys.exit(0)
    
    g = Github(token)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    
    viewer = os.environ.get("TRUSTNET_VIEWER_PROJECT", "").strip() or repo_name
    api_url = os.environ.get("TRUSTNET_API_URL", "").strip()
    
    opened_at = (pr.created_at or datetime.now()).isoformat()
    author_created = pr.user.created_at.isoformat() if pr.user and pr.user.created_at else None
    
    if api_url:
        payload = {
            "pr_id": f"{repo_name}#{pr_number}",
            "repo": repo_name,
            "author": pr.user.login,
            "title": pr.title or "",
            "body": pr.body or "",
            "diff": "",
            "opened_at": opened_at,
            "author_created_at": author_created,
        }
        report = _analyze_via_api(api_url, payload, viewer)
    else:
        report = _analyze_locally(
            pr_id=f"{repo_name}#{pr_number}",
            repo_name=repo_name,
            author=pr.user.login,
            title=pr.title or "",
            body=pr.body or "",
            diff="",
            opened_at=opened_at,
            viewer=viewer,
        )
    
    # Only post if explicitly opted-in AND passed all guards
    if DRY_RUN:
        print("\n[DRY RUN] Would have posted this comment:")
        print("-" * 60)
        print(format_comment(report))
        print("-" * 60)
        print(f"\n✅ Analysis complete. Risk={report['risk']} Score={report['trust_score']:.2f}")
        print("💡 To enable live posting: set TRUSTNET_DRY_RUN=false and add repo to ALLOWED_REPOS\n")
    else:
        pr.create_issue_comment(format_comment(report))
        print(f"Posted analysis to PR #{pr_number} (risk={report['risk']})")

if __name__ == "__main__":
    main()
