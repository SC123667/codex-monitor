# Contributing

Thanks for taking the time to contribute!

## Scope

This project is a **local-only** dashboard that parses Codex CLI session logs from `~/.codex/sessions/**.jsonl` and renders aggregated usage/cost estimates.

## Development setup

Requirements:
- Python 3.9+ (3.12 recommended)

Run locally:
```bash
python3 monitor.py
```

Front-end is embedded in `web_dashboard.py` (no Node.js toolchain).

## What to include in PRs

- A clear description of the user-facing change
- Screenshots for UI changes (redact local paths if needed)
- Notes about any config changes

## Privacy & security

- Do **not** commit any local session logs or configs:
  - `~/.codex/sessions/**`
  - `~/.codex/monitor_config.json`
  - `~/.codex/monitor.log`, `~/.codex/monitor.pid`
- Keep the dashboard default bind to `127.0.0.1` (localhost).
- If you discover a security issue, please follow `SECURITY.md`.

## Coding guidelines

- Prefer small, focused changes.
- Keep dependencies at **zero** (stdlib only).
- Avoid heavy refactors unless needed for the fix.
- UI: keep pages fast and avoid large payloads by default.

## Testing

At minimum:
```bash
python3 -m py_compile monitor.py web_dashboard.py codex_monitor_core.py
```

If you touch parsing logic, verify against a real `~/.codex/sessions` folder (locally).

## Pricing updates

Pricing is an **estimate** and can change over time.
- Update `codex_monitor_core.py` builtin rates.
- Keep README in sync.
- Mention the source and tier in the PR description.
