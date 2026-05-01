# Rules Seed Policy

These files are NOT public rule pages.
They are machine-readable seed records for most countries/territories so the rules layer can scale quickly without fabricating regulatory content.

## Purpose
- reserve country slug and identity
- map country to ISO codes, region, and primary currency
- define official source targets for later verification
- support batch workflow for upgrading seeds into full verified rule files

## Important
Do not publish seed files directly.
Only full country rule files in `data/rules/` with `verified` or `published` status should be rendered into `/rules/`.
