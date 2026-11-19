import re
from datasketch import MinHash, MinHashLSH

TOKEN_RE = re.compile(r"[a-z0-9_]+")
MIN_TOKENS = 5


def _tokenize(text):
    """Normalize text into lowercase tokens plus 2-word shingles for robust matching."""
    words = TOKEN_RE.findall((text or "").lower())
    shingles = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return words + shingles


def compute_pr_minhash(title, body="", diff="", num_perm=128):
    """Build a privacy-friendly MinHash signature from PR/issue text."""
    tokens = _tokenize(f"{title} {body} {diff}")
    if len(tokens) < MIN_TOKENS:
        return None
    m = MinHash(num_perm=num_perm)
    for token in tokens:
        m.update(token.encode("utf-8"))
    return m


def find_similar_prs_with_scores(conn, threshold=0.6):
    """Returns triples (pr_id_1, pr_id_2, jaccard_similarity) for near-duplicate PRs."""
    prs = conn.execute("SELECT id, title, body, diff FROM pull_requests").fetchall()
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    hashes = {}

    for pr in prs:
        m = compute_pr_minhash(pr["title"], pr["body"], pr["diff"])
        if m is None:
            continue
        hashes[pr["id"]] = m
        lsh.insert(pr["id"], m)

    seen = set()
    results = []
    for pr_id, mh in hashes.items():
        for other_id in lsh.query(mh):
            if other_id == pr_id:
                continue
            key = (pr_id, other_id) if pr_id < other_id else (other_id, pr_id)
            if key in seen:
                continue
            sim = round(mh.jaccard(hashes[other_id]), 3)
            if sim >= threshold:
                seen.add(key)
                results.append((key[0], key[1], sim))
    return results


def find_similar_prs(conn, threshold=0.6):
    """Returns pairs of PR IDs with similar content."""
    return [(a, b) for a, b, _ in find_similar_prs_with_scores(conn, threshold=threshold)]

