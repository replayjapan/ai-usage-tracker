# AI Usage Tracker

## FOR HUMANS

**See how much AI allowance you have left—and where your project's tokens went.**
AI Usage Tracker reads Claude Code and Codex's local usage records. It gives you
a recorded remaining-allowance percentage and reset time where available, plus
token totals for a project and progress between milestone checkpoints.

It is useful for spotting expensive sessions and planning work around your account
limits. It does not stop your work, switch models, or buy extra usage. The data
stays on your computer; there is no hosted dashboard or separate paid service.

**Two important limits:** allowance is account-wide, even when you work on several
projects. Readings may be missing or stale; this tool shows their age instead of
pretending they are a live balance. It is not a billing statement.

### Install

You need **Python 3.9+** and local Claude Code and/or Codex usage logs. No Python
packages are required.

For a standalone command-line installation:

```sh
git clone https://github.com/replayjapan/ai-usage-tracker.git
cd ai-usage-tracker
./track status
```

Or install the optional skill through Claude Code:

```text
/plugin marketplace add replayjapan/ai-usage-tracker
/plugin install ai-usage-tracker@ai-usage-tracker
```

Restart Claude Code to load the skill. Ask it to use **Weekly Tracker** for your
project. The skill locates its installed launcher; you do not need to copy it into
each repository. The repository must contain the released plugin files before
marketplace installation can succeed.

### Get Claude allowance readings (optional, once)

Token records and Codex allowance can be read from existing logs. Claude allowance
needs its status-line collector. From the standalone installation folder, preview
the change, then explicitly apply it if you want the collector:

```sh
./track setup-claude
./track setup-claude --apply
```

This wraps your Claude status line and saves a private settings backup. It preserves
the existing display. For a plugin installation, ask the skill to locate `track`
and preview the same setup. Host permission policies still apply. Undo with
`./track uninstall-claude --apply`; recorded usage is kept.

### Everyday use

Run these from the tracker folder, substituting your project's path:

```sh
./track snapshot --project /path/to/project --milestone M1 --event start
./track snapshot --project /path/to/project --milestone M1 --event checkpoint --checkpoint A
./track report --project /path/to/project --milestone M1
```

The skill can record start, checkpoints, progress and end for you. You can also ask
for a read-only report when you do not want new data imported.

Optional with [Fabex](https://github.com/replayjapan/fabex), useful on its own.
Fabex tracking is off until enabled in its settings; that switch does not install
or remove an independently configured global collector.

### What's new?

- **0.1.1:** clearer installation and usage guide, complete plugin metadata and MIT
  licensing. [Release notes](CHANGELOG.md)
- **0.1.0:** local token accounting, allowance snapshots, milestone checkpoints and
  genuinely read-only reports. [Release notes](CHANGELOG.md)

By **rePlay, LLC**, under the [MIT License](LICENSE). Never publish your usage
database, private logs, credentials or settings backups.

---

## FOR AI BROTHREN

A standalone, local command-line tool for Claude Code and Codex usage across projects. Python 3.9+ and its standard library only. No Fabex dependency, plugin edits, network requests, model calls, paid service or background polling.

## What is measured

- **Tokens:** locally recorded requests, grouped by provider/model and selected project roots. Fresh input, cached-read input, cache-write input and output are separate, non-overlapping columns. Codex's cached input is subtracted from its inclusive input total; reasoning is not added again to output.
- **Allowance:** the latest provider-reported usage percentage, reset time and window duration available in logs. Remaining percentage is `100 - used`, bounded at zero. These are account-wide, not project-specific. Only supplied allowance buckets are recorded; Fable and Opus do not acquire invented individual quotas.
- **Snapshots:** milestone/checkpoint markers with token totals and allowance observations. Reports give token deltas between markers and account allowance changes only within the same reset window.

This is an operational estimate from retained local data, not an invoice or an exact remaining token balance. It does not fetch a fresh provider balance. Every allowance has an observation timestamp and freshness label (`recent`, `stale` after 15 minutes, or `expired-window`). Claude's status-line callback time is the observation time; the provider's underlying refresh time is not exposed. A missing field is unavailable, never zero usage.

## Installation location

Keep this entire new folder at:

```text
/absolute/path/to/ai-usage-tracker
```

The paths below are placeholders: use your installed folder. This optional plugin works alone and is recommended, not required, with Fabex. Its GitHub marketplace is `replayjapan/ai-usage-tracker`; local marketplace installation is also supported. Preparing local files does not itself publish a release.

Data selection: `AI_USAGE_TRACKER_DATA`, then an existing `data/` beside the code (legacy history is preserved), otherwise `$XDG_DATA_HOME/ai-usage-tracker` or `~/.local/share/ai-usage-tracker`. New plugin installations keep data outside the replaceable cache. `--data-dir` explicitly overrides these choices. Nothing migrates or deletes existing data automatically. Use the same explicit data directory across updates if you relocate an old standalone install.

The supplied `track` path and symlinked skill remain supported. Installed skills find the package by resolving their own file path, then moving up from `skills/weekly-tracker` to the package root. No copying into each project is needed.

### One-time Claude allowance capture

Token totals and Codex allowance records work directly from existing local logs. Claude weekly allowance needs the supported Claude Code status-line input. Preview the user-settings change:

```bash
/absolute/path/to/ai-usage-tracker/track setup-claude
```

Then enable it once:

```bash
/absolute/path/to/ai-usage-tracker/track setup-claude --apply
```

This changes **only the global Claude user settings' `statusLine` command**, saving a private backup first. It invokes your existing status-line command with the original JSON input and preserves its display options. It does not edit the Fabex plugin. Only run after final placement. If managed settings override user settings, the wrapper may not run; report missing data rather than bypassing managed settings. It may take the next Claude response for the first reading. Unsupported versions/accounts may omit weekly fields entirely.

Undo just this integration without overwriting later unrelated settings:

```bash
/absolute/path/to/ai-usage-tracker/track uninstall-claude --apply
```

The backup is for recovery; do not blindly restore the whole backup over newer settings. Usage records are preserved when uninstalling.

## Use in any project

From the project root, an agent runs these commands. Substitute its actual milestone and checkpoint:

```bash
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --event start
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --checkpoint A --event checkpoint
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --event progress
/absolute/path/to/ai-usage-tracker/track snapshot --milestone M003 --event end
/absolute/path/to/ai-usage-tracker/track report --milestone M003
```

`--project /absolute/path` selects a different project without changing directories. Repeat `--include-project /other/worktree` on **every snapshot** if the milestone uses worktrees outside the main project root. Descendant paths are included automatically. Reports refuse a misleading overall delta if the first/last project-root sets differ. Use distinct milestone IDs for distinct periods.

Give the agent [AGENT-INSTRUCTIONS.md](AGENT-INSTRUCTIONS.md) at the next session start. The tool itself cannot know a checkpoint has ended; the agent marks it. No owner-supplied percentages are needed once readings are available. Optional session hooks or global agent instructions can be added later; this package does not silently install them or edit projects.

`track status` imports new records and returns current recorded allowance observations. `track sync` imports without a milestone marker. JSON output is readable by both agents and scripts. `track report` reads saved snapshots without rescanning logs. For discussion or read-only permissions, use `track status --read-only` or `track report --read-only --milestone M003`: these open an existing SQLite database with `mode=ro` and query-only enforcement, never initialize it or scan logs. Missing data is reported as unavailable.

New `setup-claude --apply` installations use a private standalone `statusline-launcher.py` copy in the data directory, surviving plugin-cache replacement. `track refresh-launcher` refreshes that copy explicitly after updates, without editing settings. Existing direct wrappers still work and uninstall remains supported; they are not silently rewired. To adopt the stable wrapper, preview and explicitly uninstall/reinstall the status-line integration. Fabex's tracking toggle never installs or removes this global collector.

## Sources and coverage

Claude reads `~/.claude/projects/**/*.jsonl`; Codex reads `~/.codex/sessions/**/*.jsonl`. `CLAUDE_CONFIG_DIR` and `CODEX_HOME` are respected. Global options before the command can override `--claude-logs`, `--codex-logs`, or `--data-dir`. This permits isolated tests and other machines without project changes.

The initial import reads retained logs once; later calls read appended bytes. Partial lines wait for the next call. Duplicate Claude message IDs and repeated Codex cumulative totals are not counted again. The database stores whitelisted usage counts, model/session/project identifiers and log cursors, **not message bodies or credentials**. Original logs are read-only. A settings backup contains your existing settings and is private; do not publish `data/`.

Limits to preserve in reports:

- Concurrent sessions in the same selected project roots contribute to its totals. Snapshots delimit time, not an exclusive session. Project totals exclude other projects, but allowance balances still include their account use.
- Deleted, archived outside the configured roots, remote or inaccessible logs are not covered. Unreadable/malformed files and missing roots are reported. Historical retention may be incomplete even with no parser warnings.
- Model changes are attributed to the recorded model at each response. Codex counter jumps are attributed to the latest recorded model; missing events can reduce precision.
- Recognized forks and counter resets skip their inherited/reset baseline and surface a coverage note. Unknown future log formats cannot be guaranteed. Session copies without explicit fork metadata may affect historical accounting.
- Same-ID Claude updates use maximum counters rather than summing streaming records; different provider request formats require adapter updates.
- A start snapshot occurs after the agent has begun its first turn. An end snapshot cannot include the running turn's not-yet-emitted final tokens. A later snapshot can include that tail; never claim an exact full-session total from premature markers.
- Status-line callbacks can repeat the same balance: callback timestamps are observations, not proof of an upstream refresh. The wrapper does not request credentials or call undocumented quota endpoints.

## Tests

```bash
cd /absolute/path/to/ai-usage-tracker
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
```

Fixtures cover streaming/fork duplicates, Codex cache accounting and reset baselines, append/truncation handling, absence/expiry, project isolation, checkpoint reports, reset-window arithmetic, private storage and settings preservation/undo. Tests use temporary files and fake settings; they do not modify real user settings or send model requests.

## Official interface references

- Claude status-line fields: https://code.claude.com/docs/en/statusline
- Claude usage reporting: https://code.claude.com/docs/en/monitoring-usage
- Codex usage/allowance interfaces: https://learn.chatgpt.com/docs/app-server

This version reads installed-client log schemas rather than depending on live App Server access. It works independently of Fabex; no plugin upgrade is required. Before publication run the privacy test against staged/tracked files, verify the chosen repository and license, and exclude all usage databases, private launchers, settings backups and credentials. No repository is created by this package.
