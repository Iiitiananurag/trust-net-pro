from datetime import datetime
import networkx as nx

MAX_HOPS = 3
VOUCH_LIMIT = 50          # vouching for more accounts than this looks like a trust farm
LOW_THRESHOLD = 0.5
ELEVATED_THRESHOLD = -0.5
DEFAULT_DENOUNCE_TTL_DAYS = 90


def _parse_iso(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except ValueError:
        return None


def build_graph(conn):
    g = nx.DiGraph()
    for r in conn.execute("SELECT src, dst, weight FROM trust_edges"):
        g.add_edge(r["src"], r["dst"], weight=r["weight"])
    return g


def effective_trust(g, viewer, source, decay=1.0, max_hops=MAX_HOPS):
    """Best path product of edge weights, decayed per extra hop. Own signals = 1.0."""
    if viewer == source:
        return 1.0
    if viewer not in g or source not in g:
        return 0.0
    best = 0.0
    for path in nx.all_simple_paths(g, viewer, source, cutoff=max_hops):
        w = 1.0
        for a, b in zip(path, path[1:]):
            w *= g[a][b]["weight"]
        w *= decay ** (len(path) - 2)
        best = max(best, w)
    return best


def reliability(conn, project):
    """Volume discount: honest projects vouch for a bounded number of people."""
    n = conn.execute("SELECT COUNT(*) FROM vouches WHERE project_id=?", (project,)).fetchone()[0]
    return min(1.0, VOUCH_LIMIT / n) if n else 1.0


def _appeal_status(conn, project_id, account_id):
    row = conn.execute(
        """
        SELECT status FROM denounce_appeals
        WHERE project_id=? AND account_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (project_id, account_id),
    ).fetchone()
    return row["status"] if row else None


def score_contributor(conn, viewer, account, decay=1.0, now=None):
    """Weighted vouches minus active weighted denounces, from the viewer's perspective."""
    g = build_graph(conn)
    cache = {}
    ref_now = _parse_iso(now) if isinstance(now, str) else (now.replace(tzinfo=None) if isinstance(now, datetime) else datetime.now())

    def weight(src):
        if src not in cache:
            cache[src] = effective_trust(g, viewer, src, decay) * reliability(conn, src)
        return cache[src]

    score, has, evidence = 0.0, False, []
    for r in conn.execute("SELECT project_id, reason FROM vouches WHERE account_id=?", (account,)):
        has = True
        w = weight(r["project_id"])
        if w > 0:
            score += w
            reason_suffix = f" ({r['reason']})" if r["reason"] else ""
            evidence.append(f"+{w:.2f} vouch from {r['project_id']}{reason_suffix}")

    for r in conn.execute(
        "SELECT project_id, reason, created_at, expires_at FROM denounces WHERE account_id=?",
        (account,),
    ):
        expires_at = _parse_iso(r["expires_at"])
        if expires_at is not None and ref_now > expires_at:
            continue

        appeal = _appeal_status(conn, r["project_id"], account)
        if appeal == "approved":
            evidence.append(f"0.00 denounce from {r['project_id']} waived (appeal approved)")
            continue

        has = True
        w = weight(r["project_id"])
        if w > 0:
            score -= w
            reason_suffix = f" ({r['reason']})" if r["reason"] else ""
            appeal_suffix = " [appeal pending]" if appeal == "pending" else ""
            evidence.append(f"-{w:.2f} denounce from {r['project_id']}{reason_suffix}{appeal_suffix}")

    return score, has, evidence


def classify(score, has_signals):
    if not has_signals:
        return "neutral"          # unknown is NOT suspicious
    if score >= LOW_THRESHOLD:
        return "low"
    if score <= ELEVATED_THRESHOLD:
        return "elevated"
    return "neutral"
