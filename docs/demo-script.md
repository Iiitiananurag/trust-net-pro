# 🎥 MeshyTrust Demo Video Script (Catalyst Problem 5)

[Segment 1: Normal Mode – Campaign Detection] (~45 sec)
Narrator: "Watch Patricia receive eighteen seemingly innocent refactor PRs..."
Screen: Dashboard shows single-repo view looking benign
Transition: Zoom out to global campaign graph revealing thirty synchronized bots across fifty repositories
Callout: "One maintainer sees noise. Our system sees coordination."
Technical beat: Show /campaigns endpoint returning JSON with evidence_summary field

[Segment 2: Newcomer Inclusion] (~30 sec)
Narrator: "Sarah submits her first contribution—a typo fix."
Screen: Bot card displays ⚪ NEUTRAL with zero penalty
Emphasis: "Unknown ≠ Suspicious. Genuine newcomers enter freely."
Technical beat: Show classify() function returning "neutral" when has_signals=False

[Segment 3: Adversarial Resilience] (~45 sec)
Narrator: "Project B joins maliciously, vouching for all thirty bots while denouncing legitimate contributor John."
Screen: Toggle malicious_b=True reruns simulation
Result: Despite direct hostility, John retains LOW risk thanks to volume discount collapsing proj-b influence below 0.1
Quote: "Trust flows transitively—but toxicity doesn't propagate unchecked."
Technical beat: Show reliability() calculation capping proj-b at 0.050 with 1000 fake accounts

[Segment 4: Sybil Resistance] (~30 sec)
Narrator: "Five fresh accounts form a mutual-vouch ring hoping to game reputation."
Screen: /sybil-check returns detected cycle
Protection: Meanwhile Alice—who earned genuine vouches elsewhere—remains unflagged
Lesson: "Rings collapse mathematically; independence protects truth-tellers."
Technical beat: Show SCC detection finding 5-node cycle while clean_vouchers check saves Alice

[Segment 5: Governance Lifecycle] (~30 sec)
Narrator: "A wrongly accused user files appeal; moderator approves."
Screen: Denouncement waived instantly; score recovers fully
Closing: "Every flag carries evidence. Every accusation expires. Every voice gets heard."
Technical beat: Show _appeal_status() waiver logic + expires_at column enforcement

[Outro] (~15 sec)
Narrator: "MeshyTrust: decentralized trust without central authority. Built for Catalyst Problem 5."
Screen: Repo URL + GitHub App installation link
