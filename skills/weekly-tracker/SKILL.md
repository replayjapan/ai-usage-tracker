---
name: weekly-tracker
description: Record Claude and Codex allowance readings and token usage for project sessions, milestones and checkpoints. Use when the user asks to start tracking usage, record a checkpoint, check remaining weekly allowance, or produce a usage report.
---

# Weekly Tracker

Resolve this SKILL.md's real path (including symlinks), go up two directories to the package root, and use its `track` launcher. When installed as a Claude plugin, `${CLAUDE_PLUGIN_ROOT}/track` is equivalent. Examples below use a placeholder, never a fixed machine path:

```text
/absolute/path/to/ai-usage-tracker/track
```

Do not assume the allowance collector is configured. Missing readings are unavailable, not a request to install it. Do not reinstall it, change Fabex, edit global instruction files, or add project configuration during normal tracking.

## Start and continue tracking

When asked to start tracking, use the milestone/session identifier and canonical project root from the conversation. Ask only if the identifier or intended project is genuinely ambiguous. Track the current work; do not invent historical start readings.

Run from that project root, replacing M003/A with the actual identifiers:

```bash
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --event start
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --checkpoint A --event checkpoint
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --event progress
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --event end
/absolute/path/to/ai-usage-tracker/track report --milestone M003
```

Run only the applicable command, not this whole sequence. After the start request, record subsequent checkpoint and closeout markers as the work reaches them, without asking the owner for percentages. On resume, use the existing identifier; check its report before creating another start. A status request alone uses `track status`, without inventing a milestone or starting tracking.

Use `--project /absolute/project/root` when the working directory differs. If work uses external worktrees, add `--include-project /absolute/worktree` to every snapshot and keep that root set consistent. Include the project root and milestone identifier in the session handoff so tracking can continue after compaction.

## Execution and permissions

In Fabex/shared sessions, Claude records one set of snapshots for both providers. Codex reuses that result rather than creating duplicate markers. Standalone clients may run the command themselves when their permissions allow writing the tool's data directory.

Use `status --read-only` or `report --read-only --milestone ACTUAL_ID` in discussion/read-only mode: these query existing records without importing or creating a database. Unflagged status/report and all snapshots may write. Defer recording to authorized work mode. Do not change allowlists, bypass a sandbox, silently move the data store, or claim a successful snapshot without a receipt.

## Report accurately

- Show Claude/Codex remaining allowance, observation time, reset time and freshness when present. Missing or stale data stays labelled; do not ask the owner to supply numbers or generate model requests just to refresh them.
- Allowance readings are account-wide. Per-model token columns are local project usage, not independent model quotas or a known number of remaining tokens.
- The report's input, cache-read, cache-write and output columns are non-overlapping. Do not add cached input to an already inclusive provider total or add reasoning to inclusive output again.
- Preserve reset-window and coverage warnings. An in-turn end snapshot can omit that turn's not-yet-recorded final usage. Never call it an exact full-session bill.
- Keep the reply short: marker saved, available balances with timestamps, and material coverage limitations. Use report output for checkpoint/milestone comparisons; do not infer missing history.

For setup or unusual source/coverage issues, read `README.md` at the resolved package root. Normal tracking does not require reading source code or scanning raw transcripts manually.
