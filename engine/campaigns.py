from datetime import datetime
import networkx as nx
from engine.similarity import find_similar_prs_with_scores
from engine.trust import VOUCH_LIMIT


def _parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def detect_campaigns_detailed(
    conn,
    min_cluster_size=3,
    threshold=0.6,
    burst_window_hours=24.0,
    new_account_days=14,
):
    """
    Detect coordinated cross-repository PR/issue campaigns and return rich evidence:
    matched accounts, real similarity edges, targeted repos, PR count, burst window,
    and fraction of newly created accounts.
    """
    similar_triples = find_similar_prs_with_scores(conn, threshold=threshold)
    pr_rows = {
        r["id"]: dict(r)
        for r in conn.execute(
            "SELECT id, repo_id, author_id, created_at FROM pull_requests"
        ).fetchall()
    }
    acc_created = {
        r["id"]: _parse_iso(r["created_at"])
        for r in conn.execute("SELECT id, created_at FROM accounts").fetchall()
    }

    G = nx.Graph()
    author_prs = {}
    for p1, p2, sim in similar_triples:
        r1, r2 = pr_rows.get(p1), pr_rows.get(p2)
        if not r1 or not r2:
            continue
        a1, a2 = r1["author_id"], r2["author_id"]
        if a1 and a2 and a1 != a2:
            if G.has_edge(a1, a2):
                G[a1][a2]["weight"] = max(G[a1][a2]["weight"], sim)
                G[a1][a2]["pair_count"] += 1
            else:
                G.add_edge(a1, a2, type="similar_pr", weight=sim, pair_count=1)
            author_prs.setdefault(a1, set()).add(p1)
            author_prs.setdefault(a2, set()).add(p2)

    campaigns = []
    components = sorted(
        (sorted(c) for c in nx.connected_components(G) if len(c) >= min_cluster_size),
        key=lambda c: (-len(c), c[0]),
    )

    for idx, accounts in enumerate(components, start=1):
        account_set = set(accounts)
        matched_pr_ids = set()
        for acc in accounts:
            matched_pr_ids.update(author_prs.get(acc, set()))

        repos = sorted({pr_rows[pid]["repo_id"] for pid in matched_pr_ids if pid in pr_rows})
        pr_times = [
            _parse_iso(pr_rows[pid]["created_at"])
            for pid in matched_pr_ids
            if pid in pr_rows
        ]
        pr_times = [t for t in pr_times if t is not None]

        if len(pr_times) >= 2:
            earliest_pr, latest_pr = min(pr_times), max(pr_times)
            time_span_hours = round((latest_pr - earliest_pr).total_seconds() / 3600.0, 2)
        else:
            latest_pr = pr_times[0] if pr_times else None
            time_span_hours = 0.0

        new_count = 0
        if latest_pr is not None:
            for acc in accounts:
                created = acc_created.get(acc)
                if created is not None and (latest_pr - created).total_seconds() <= new_account_days * 86400:
                    new_count += 1
        new_ratio = round(new_count / len(accounts), 2) if accounts else 0.0
        is_burst = time_span_hours <= burst_window_hours

        # Real similarity edges within this component (capped for clean UI rendering)
        sub = G.subgraph(account_set)
        edges = [
            {
                "source": u,
                "target": v,
                "weight": round(d.get("weight", 0.0), 3),
                "pair_count": d.get("pair_count", 1),
            }
            for u, v, d in sorted(sub.edges(data=True), key=lambda x: (-x[2].get("weight", 0), x[0], x[1]))
        ]

        burst_note = f" within {time_span_hours:.1f}h burst" if is_burst else f" over {time_span_hours:.1f}h"
        new_pct = int(round(new_ratio * 100))
        evidence_summary = (
            f"{len(accounts)} accounts ({new_pct}% created <={new_account_days}d) "
            f"submitted {len(matched_pr_ids)} near-identical PRs across {len(repos)} repos{burst_note}"
        )

        campaigns.append(
            {
                "id": f"campaign-{idx}",
                "accounts": accounts,
                "size": len(accounts),
                "pr_count": len(matched_pr_ids),
                "repos": repos,
                "repo_count": len(repos),
                "time_span_hours": time_span_hours,
                "is_burst": is_burst,
                "new_account_ratio": new_ratio,
                "edges": edges,
                "evidence_summary": evidence_summary,
            }
        )

    return campaigns


def detect_campaigns(conn, min_cluster_size=3):
    """Backward-compatible helper returning clusters of account IDs connected by similar PRs."""
    return [c["accounts"] for c in detect_campaigns_detailed(conn, min_cluster_size=min_cluster_size)]


def detect_sybil_rings(conn, fresh_days=14, min_farm_vouches=10, fresh_ratio_threshold=0.7):
    """
    Detect Sybil threats without falsely flagging genuine multi-vouched contributors:
    1. Trust-farm projects: projects exceeding VOUCH_LIMIT OR vouching for >= min_farm_vouches
       where >= 70% of vouched accounts are newly created and lack independent vouches.
    2. Mutual-vouch account rings: strongly connected components (>= 3 accounts) in
       account_vouches where accounts artificially vouch for one another.
    Genuine contributors independently vouched by clean projects are protected from false flags.
    """
    vouches = conn.execute(
        "SELECT project_id, account_id, created_at FROM vouches"
    ).fetchall()
    acc_created = {
        r["id"]: _parse_iso(r["created_at"])
        for r in conn.execute("SELECT id, created_at FROM accounts").fetchall()
    }

    project_vouches = {}
    account_vouchers = {}
    for v in vouches:
        pid, aid = v["project_id"], v["account_id"]
        project_vouches.setdefault(pid, []).append(v)
        account_vouchers.setdefault(aid, set()).add(pid)

    suspicious_projects = []
    evidence = []

    for pid, vlist in project_vouches.items():
        count = len(vlist)
        if count > VOUCH_LIMIT:
            suspicious_projects.append(pid)
            evidence.append(f"Project '{pid}' vouched for {count} accounts (exceeds limit {VOUCH_LIMIT})")
            continue

        if count >= min_farm_vouches:
            isolated_fresh = 0
            for v in vlist:
                aid = v["account_id"]
                v_time = _parse_iso(v["created_at"])
                c_time = acc_created.get(aid)
                is_fresh = (
                    v_time is not None
                    and c_time is not None
                    and (v_time - c_time).total_seconds() <= fresh_days * 86400
                )
                is_isolated = len(account_vouchers.get(aid, set())) == 1
                if is_fresh and is_isolated:
                    isolated_fresh += 1

            ratio = isolated_fresh / count
            if ratio >= fresh_ratio_threshold:
                suspicious_projects.append(pid)
                evidence.append(
                    f"Project '{pid}' vouched for {count} accounts, of which "
                    f"{isolated_fresh} ({int(ratio * 100)}%) are fresh (<={fresh_days}d) and unvouched elsewhere"
                )

    suspicious_set = set(suspicious_projects)

    # Protect genuine contributors who also hold vouches from non-suspicious projects
    sybil_accounts = set()
    for v in vouches:
        if v["project_id"] in suspicious_set:
            aid = v["account_id"]
            clean_vouchers = account_vouchers.get(aid, set()) - suspicious_set
            if not clean_vouchers:
                sybil_accounts.add(aid)

    # Detect mutual-vouch rings among accounts (if account_vouches table exists)
    mutual_rings = []
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_vouches'"
    ).fetchone()
    if has_table:
        ag = nx.DiGraph()
        for row in conn.execute("SELECT voucher_id, account_id FROM account_vouches"):
            if row["voucher_id"] != row["account_id"]:
                ag.add_edge(row["voucher_id"], row["account_id"])
        for scc in nx.strongly_connected_components(ag):
            if len(scc) >= 3:
                ring = sorted(scc)
                mutual_rings.append(ring)
                for acc in ring:
                    if not (account_vouchers.get(acc, set()) - suspicious_set):
                        sybil_accounts.add(acc)
                evidence.append(
                    f"Mutual-vouch account ring detected ({len(ring)} accounts vouching in a cycle)"
                )

    return {
        "suspicious_projects": sorted(suspicious_projects),
        "sybil_accounts": sorted(sybil_accounts),
        "mutual_rings": mutual_rings,
        "ring_size": len(sybil_accounts),
        "evidence": evidence,
    }
