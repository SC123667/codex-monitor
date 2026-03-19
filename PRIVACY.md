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
- It does not expose a public endpoint by default.

## UI and export behavior

- The dashboard is designed to run locally and bind to `127.0.0.1` by default.
- Workspace displays are anonymized in the UI so screenshots are safer to share.
- Raw local logs still contain original metadata on your machine.
- If you add your own custom exports or patches, review them before sharing publicly.
