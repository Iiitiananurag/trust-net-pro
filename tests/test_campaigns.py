from simulator.seed import seed
from engine.db import connect
from engine.campaigns import detect_campaigns, detect_campaigns_detailed, detect_sybil_rings


def main():
    seed(False)
    conn = connect()

    clusters = detect_campaigns(conn, min_cluster_size=3)
    print(f"Found {len(clusters)} suspicious clusters")

    bot_cluster = None
    for c in clusters:
        if "bot-001" in c:
            bot_cluster = c
            break

    assert bot_cluster is not None, "Bot campaign not detected!"
    assert len(bot_cluster) == 30, f"Expected 30 bots, got {len(bot_cluster)}"
    print(f"Bot cluster size: {len(bot_cluster)} (PASS)")

    # Check John and Sarah are not in large clusters
    for c in clusters:
        assert "john" not in c, "John flagged in campaign!"
        assert "sarah" not in c, "Sarah flagged in campaign!"
    print("John and Sarah clean (PASS)")

    # Check detailed campaign metadata (repo spread, burst window, real edges)
    detailed = detect_campaigns_detailed(conn, min_cluster_size=3)
    assert len(detailed) >= 1
    camp = next(c for c in detailed if "bot-001" in c["accounts"])
    assert camp["repo_count"] >= 40, f"Expected broad repo spread, got {camp['repo_count']}"
    assert camp["is_burst"] is True, "Expected 6h bot burst to be flagged as burst"
    assert len(camp["edges"]) > 0, "Expected real similarity edges"
    print(f"Detailed campaign evidence: {camp['evidence_summary']} (PASS)")

    # Sybil check in normal mode: zero false positives
    sybil_normal = detect_sybil_rings(conn)
    assert len(sybil_normal["suspicious_projects"]) == 0
    assert len(sybil_normal["sybil_accounts"]) == 0
    print("Sybil normal mode clean (PASS)")

    # Sybil check in malicious mode + mutual-vouch ring: catch proj-b & bots, protect john
    seed(malicious_b=True, include_sybil_ring=True)
    conn = connect()
    sybil_mal = detect_sybil_rings(conn)
    assert "proj-b" in sybil_mal["suspicious_projects"], "Malicious trust farm proj-b not caught!"
    assert "bot-001" in sybil_mal["sybil_accounts"], "Bot vouched by malicious farm not flagged!"
    assert "john" not in sybil_mal["sybil_accounts"], "Genuine contributor john falsely flagged as Sybil!"
    assert "sarah" not in sybil_mal["sybil_accounts"], "Newcomer sarah falsely flagged as Sybil!"
    assert len(sybil_mal["mutual_rings"]) == 1 and len(sybil_mal["mutual_rings"][0]) == 5
    print(f"Sybil malicious+ring mode OK: {sybil_mal['ring_size']} sybil accounts, john protected (PASS)")

    seed(False)
    print("ALL CAMPAIGN TESTS PASSED")


if __name__ == "__main__":
    main()
