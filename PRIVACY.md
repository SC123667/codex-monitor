# Privacy

This tool reads Codex CLI local session logs from `~/.codex/sessions/**.jsonl` on your machine to compute usage summaries.

## What it processes

- Session metadata (e.g., `cwd`)
- Model identifiers
- Token usage counters (`token_count` events)
- Rate limit snapshots (if present in the logs)

## What it does not do

- It does not send your data to third parties.
- It does not require network access.

## Sharing screenshots / JSON exports

Be careful: exports and screenshots may include local paths (`cwd`) and other identifying information.
