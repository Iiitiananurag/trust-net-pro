from datetime import timedelta

from engine.db import connect
from engine.trust import build_graph, effective_trust, score_contributor, classify, reliability
from simulator.seed import seed, NOW


def main():
    seed(False)
    conn = connect()
    g = build_graph(conn)

    tb = effective_trust(g, "patricia", "proj-b")
    tc = effective_trust(g, "patricia", "proj-c")
    tc_decayed = effective_trust(g, "patricia", "proj-c", decay=0.8)
    td = effective_trust(g, "patricia", "david")
    print(f"trust paths: patricia->proj-b={tb:.1f}  patricia->proj-c={tc:.1f} (decayed={tc_decayed:.2f})  patricia->david={td:.1f}")
    assert abs(tb - 1.0) < 1e-9 and abs(tc - 0.6) < 1e-9
    assert abs(tc_decayed - 0.48) < 1e-9

    for who in ("john", "sarah", "bot-001"):
        s, has, ev = score_contributor(conn, "patricia", who)
        print(f"{who}: score={s:.2f} risk={classify(s, has)}")

    s, has, _ = score_contributor(conn, "patricia", "john")
    assert has and s > 0 and classify(s, has) == "low"
    s, has, _ = score_contributor(conn, "patricia", "sarah")
    assert s == 0 and not has and classify(s, has) == "neutral"
    s, has, _ = score_contributor(conn, "patricia", "bot-001")
    assert not has and classify(s, has) == "neutral"

    # Decentralized perspective: david evaluates john from david's own graph
    sd, has_d, _ = score_contributor(conn, "david", "john")
    assert has_d and sd > 0 and classify(sd, has_d) == "low"
    print("normal mode + decentralized perspective OK")

    seed(True)
    conn = connect()
    s, has, _ = score_contributor(conn, "patricia", "bot-001", now=NOW)
    assert has and s > 0                      # B's vouch counts; Sybil/campaign layers catch bots
    sj, _, _ = score_contributor(conn, "patricia", "john", now=NOW)
    assert classify(sj, True) == "low"        # genuine contributor survives a hostile denounce
    print("malicious mode OK (john survives hostile denounce)")

    # Denouncement expiry test: 100 days after NOW, 90-day denounce from proj-b expires
    sj_after_expiry, _, _ = score_contributor(conn, "patricia", "john", now=NOW + timedelta(days=100))
    assert sj_after_expiry > sj, "Expired denounce should no longer penalize contributor"
    print(f"expiry OK: john score rises from {sj:.2f} to {sj_after_expiry:.2f} after denounce expiry")

    # Appeal approval test: approved appeal waives active denounce immediately
    conn.execute(
        "INSERT INTO denounce_appeals (project_id, account_id, reason, status, created_at) VALUES (?,?,?,?,?)",
        ("proj-b", "john", "false flag by compromised project", "approved", NOW.isoformat()),
    )
    conn.commit()
    sj_appealed, _, ev_appealed = score_contributor(conn, "patricia", "john", now=NOW)
    assert sj_appealed > sj and any("appeal approved" in e for e in ev_appealed)
    print(f"appeal OK: john score restored to {sj_appealed:.2f} upon approved appeal")

    conn.execute("DELETE FROM vouches WHERE project_id='proj-b'")
    fakes = [(f"fake-{i:04d}", f"fake-{i:04d}", (NOW - timedelta(days=3)).isoformat()) for i in range(1000)]
    conn.executemany("INSERT INTO accounts VALUES (?,?,?)", fakes)
    conn.executemany("INSERT INTO vouches VALUES (?,?,?,?)",
                     [("proj-b", f[0], "farmed", NOW.isoformat()) for f in fakes])
    conn.commit()
    rel = reliability(conn, "proj-b")
    s, has, _ = score_contributor(conn, "patricia", "fake-0001", now=NOW)
    assert rel < 0.1 and s < 0.2 and classify(s, has) == "neutral"
    print(f"stress OK: proj-b influence capped at {rel:.3f}, fake score={s:.3f}")

    seed(False)                               # leave DB in normal mode for next steps
    print("ALL TRUST TESTS PASSED")


if __name__ == "__main__":
    main()
