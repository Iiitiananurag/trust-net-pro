import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

from engine.db import connect, init_db, ensure_project, ensure_account

NOW = datetime(2026, 11, 19, 9, 0, 0)
rng = random.Random(9)

BOT_TITLE = "refactor: improve error handling across modules"
BOT_BODY = ("This PR improves error handling across modules by adding comprehensive "
            "try/except blocks and detailed logging. It also resolves a critical "
            "race condition in the cache layer.")
BOT_DIFF = """@@ -12,7 +12,11 @@ def process(items):
-    return [handle(i) for i in items]
+    results = []
+    for i in items:
+        try:
+            results.append(handle(i))
+        except Exception as e:
+            log.error("failed: %s", e)
+    return results
"""

GENUINE = [
    ("fix: off-by-one in pagination cursor", "Cursor skipped the last item on page boundaries.", "-    end = start + size\n+    end = start + size - 1\n"),
    ("docs: clarify install steps for Windows", "Added the PowerShell activation step users keep missing.", "+Use .venv\\Scripts\\Activate.ps1 on Windows.\n"),
    ("perf: cache compiled regexes", "Compiling once cut CPU time by 30% in benchmarks.", "-    re.match(p, s)\n+    COMPILED.match(s)\n"),
    ("feat: add --json flag to CLI", "Machine-readable output for scripting.", "+    if args.json: print(json.dumps(out))\n"),
    ("fix: handle empty input gracefully", "Empty lists raised IndexError; now returns [].", "+    if not items: return []\n"),
    ("test: cover timezone edge cases", "Added DST transition tests.", "+def test_dst_transition(): ...\n"),
    ("refactor: extract retry helper", "Deduplicated retry logic in three modules.", "+def with_retry(fn, n=3): ...\n"),
    ("docs: fix broken link in README", "Link pointed to the old repo name.", "-old-repo\n+new-repo\n"),
]


def import_ghostty_vouch_list(conn, content, project_id="ghostty", trusted_by="patricia", trust_weight=0.85):
    """
    Parse Ghostty's public VOUCHED.td format into vouches/denounces.
    Lines starting with '-' indicate denounced handles; other non-comment lines are vouched.
    """
    ensure_project(conn, project_id, name="Ghostty")
    if trusted_by:
        ensure_project(conn, trusted_by)
        conn.execute(
            "INSERT OR REPLACE INTO trust_edges (src, dst, weight) VALUES (?, ?, ?)",
            (trusted_by, project_id, trust_weight),
        )

    vouched_count, denounced_count = 0, 0
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        token = parts[0]
        reason = parts[1].strip() if len(parts) > 1 else "imported from Ghostty VOUCHED.td"

        if token.startswith("-"):
            handle = token[1:].strip()
            if not handle:
                continue
            ensure_account(conn, handle, handle=handle, created_at=(NOW - timedelta(days=60)).isoformat())
            conn.execute(
                """
                INSERT OR REPLACE INTO denounces (project_id, account_id, reason, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, handle, reason, NOW.isoformat(), (NOW + timedelta(days=90)).isoformat()),
            )
            denounced_count += 1
        else:
            handle = token.strip()
            ensure_account(conn, handle, handle=handle, created_at=(NOW - timedelta(days=180)).isoformat())
            conn.execute(
                "INSERT OR IGNORE INTO vouches (project_id, account_id, reason, created_at) VALUES (?, ?, ?, ?)",
                (project_id, handle, reason, NOW.isoformat()),
            )
            vouched_count += 1

    conn.commit()
    return vouched_count, denounced_count


def seed(malicious_b=False, include_sybil_ring=False, ghostty_vouch_file=None):
    init_db()
    conn = connect()
    for t in (
        "pull_requests",
        "denounce_appeals",
        "account_vouches",
        "vouches",
        "denounces",
        "trust_edges",
        "accounts",
        "projects",
    ):
        conn.execute(f"DELETE FROM {t}")

    repos = ["patricia", "david"] + [f"repo-{i:02d}" for i in range(3, 51)]
    projects = repos + ["proj-b", "proj-c", "proj-d"]
    conn.executemany("INSERT INTO projects VALUES (?,?,0)",
                     [(p, p.replace("-", " ").title()) for p in projects])

    edges = [("patricia", "proj-b", 1.0), ("proj-b", "proj-c", 0.6),
             ("patricia", "david", 0.8), ("david", "proj-c", 0.5),
             ("proj-d", "proj-b", 0.7)]
    for _ in range(10):
        a, b = rng.sample(repos, 2)
        edges.append((a, b, round(rng.uniform(0.3, 0.9), 2)))
    conn.executemany("INSERT OR IGNORE INTO trust_edges VALUES (?,?,?)", edges)

    accounts = [("john", "john", (NOW - timedelta(days=200)).isoformat()),
                ("sarah", "sarah", (NOW - timedelta(days=1)).isoformat())]
    accounts += [(f"dev-{i:02d}", f"dev-{i:02d}", (NOW - timedelta(days=rng.randint(30, 400))).isoformat()) for i in range(1, 9)]
    accounts += [(f"bot-{i:03d}", f"bot-{i:03d}", (NOW - timedelta(days=3)).isoformat()) for i in range(1, 31)]
    conn.executemany("INSERT INTO accounts VALUES (?,?,?)", accounts)

    vouches = [("patricia", "john", "months of genuine work", NOW.isoformat()),
               ("david", "john", "solid reviews", NOW.isoformat()),
               ("proj-b", "john", "reliable contributor", NOW.isoformat())]
    denounces = []
    if malicious_b:
        vouches += [("proj-b", f"bot-{i:03d}", "trusted contributor", NOW.isoformat()) for i in range(1, 31)]
        denounces.append(
            ("proj-b", "john", "spam account", NOW.isoformat(), (NOW + timedelta(days=90)).isoformat())
        )
    conn.executemany("INSERT INTO vouches VALUES (?,?,?,?)", vouches)
    conn.executemany(
        "INSERT INTO denounces (project_id, account_id, reason, created_at, expires_at) VALUES (?,?,?,?,?)",
        denounces,
    )

    if include_sybil_ring:
        ring_members = [f"sybil-{i:02d}" for i in range(1, 6)]
        for m in ring_members:
            ensure_account(conn, m, handle=m, created_at=(NOW - timedelta(days=2)).isoformat())
        ring_edges = [
            (ring_members[i], ring_members[(i + 1) % len(ring_members)], NOW.isoformat())
            for i in range(len(ring_members))
        ]
        conn.executemany("INSERT OR IGNORE INTO account_vouches VALUES (?,?,?)", ring_edges)

    prs = []
    n = 0

    def add_pr(repo, author, title, body, diff, opened):
        nonlocal n
        n += 1
        prs.append((f"pr-{n:04d}", repo, author, title, body, diff, opened.isoformat()))

    add_pr("patricia", "john", "fix: race condition in worker pool",
           "Workers could double-process jobs under load; added a lock.",
           "-    job = queue.pop()\n+    with lock: job = queue.pop()\n", NOW - timedelta(hours=2))
    add_pr("patricia", "sarah", "docs: fix typo in contribution guide",
           "First contribution! Fixed a typo in CONTRIBUTING.md.",
           "-recieve\n+receive\n", NOW - timedelta(hours=1))
    for i, (t, b, d) in enumerate(GENUINE):
        add_pr(rng.choice(repos), f"dev-{i+1:02d}", t, b, d, NOW - timedelta(days=rng.randint(1, 10)))

    others = repos[1:]
    k = 0
    for i in range(1, 31):
        targets = (["patricia"] if i <= 18 else []) + [others[k % 49], others[(k + 1) % 49]]
        k += 2
        opened = NOW - timedelta(minutes=rng.randint(0, 360))
        for repo in targets:
            add_pr(repo, f"bot-{i:03d}", BOT_TITLE, BOT_BODY, BOT_DIFF + f"+# rev {i}\n", opened)

    conn.executemany("INSERT INTO pull_requests VALUES (?,?,?,?,?,?,?)", prs)
    conn.commit()

    if ghostty_vouch_file:
        v_cnt, d_cnt = import_ghostty_vouch_list(conn, Path(ghostty_vouch_file).read_text(encoding="utf-8"))
        print(f"imported real Ghostty VOUCHED.td data: vouched={v_cnt}, denounced={d_cnt}")
    else:
        print("[SYNTHETIC BENCHMARK DATA] Note: using simulated network (pass --ghostty-vouch-file for real Ghostty VOUCHED.td data)")

    covered = conn.execute("SELECT COUNT(DISTINCT repo_id) FROM pull_requests WHERE author_id LIKE 'bot-%'").fetchone()[0]
    pat_campaign = conn.execute("SELECT COUNT(*) FROM pull_requests WHERE repo_id='patricia' AND author_id LIKE 'bot-%'").fetchone()[0]
    print(f"mode: {'MALICIOUS B' if malicious_b else 'normal'}")
    print(f"projects={len(projects)} accounts={len(accounts)} trust_edges={len(edges)} vouches={len(vouches)} denounces={len(denounces)} prs={len(prs)}")
    print(f"campaign: 30 bots (3 days old) covering {covered} repos; patricia sees {pat_campaign} campaign PRs")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--malicious-b", action="store_true")
    ap.add_argument("--include-sybil-ring", action="store_true")
    ap.add_argument("--ghostty-vouch-file", type=str, default=None)
    args = ap.parse_args()
    seed(
        malicious_b=args.malicious_b,
        include_sybil_ring=args.include_sybil_ring,
        ghostty_vouch_file=args.ghostty_vouch_file,
    )
