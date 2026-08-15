# M2.5 infrastructure fixtures

Brazil pack under `data/coverage/pipeline/brazil/` is the live **PENDING**
infrastructure fixture (five review rows, zero closed human decisions).

Deterministic PASS / BLOCK / stale / missing / vocabulary cases are built at
test time in `tests/test_human_claim_review.py` from a copy of that pack so
fingerprints stay fresh and Brazil is never auto-classified.
