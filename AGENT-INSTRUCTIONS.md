# Using AI Usage Tracker in a project

Use `/absolute/path/to/ai-usage-tracker/track` from the canonical project root. No Fabex changes are needed.

1. At milestone/session start: `track snapshot --milestone ACTUAL_ID --event start` (use the full path above).
2. At checkpoint closeout: `track snapshot --milestone ACTUAL_ID --checkpoint ACTUAL_CHECKPOINT --event checkpoint`.
3. On request or a meaningful progress boundary: same command with `--event progress`.
4. At milestone closeout: `--event end`, then `track report --milestone ACTUAL_ID`.

Use the same `--project` and optional `--include-project` root set throughout. Record model token columns separately and allowance changes as account-wide. Reset windows are provider-specific. Do not double-count cached input or use context-window capacity as spend.

Read freshness and coverage warnings. Missing/stale allowance is not an instruction to ask the owner for numbers, start model calls, poll, or change settings: record it honestly and continue. End-of-turn tokens may not yet be logged; say the report covers the snapshot interval. Never claim every model has an independent weekly allowance.

Do not install hooks or alter any project/plugin. The one-time global Claude status-line wrapper, if desired, is explicitly set up using the README. Do not re-run setup routinely.
