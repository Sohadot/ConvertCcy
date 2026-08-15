# M2.5 review fixtures

Live Brazil pack under `data/coverage/pipeline/brazil/` is the closed 5/5
human-review pack. Mutation tests in `tests/test_human_claim_review.py`
reopen a copy to pending before constructing PASS / BLOCK / stale /
missing / vocabulary cases so fingerprints stay fresh and live decisions
are not overwritten.
