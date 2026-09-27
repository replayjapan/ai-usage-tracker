# Changelog

## 0.1.1 — 2026-09-27

- Separate human introduction, installation and first-use instructions from the AI reference.
- Use the selected GitHub repository for installation instructions.
- Add plugin author, marketplace description and MIT license (rePlay, LLC).
- Preserve all collectors, read-only reports, usage data and opt-in behavior.

## 0.1.0 — 2026-09-27

- Package the existing standalone tracker as an optional Claude plugin/marketplace.
- Replace machine-specific instruction paths with portable launcher discovery.
- Preserve existing local data; support an explicit data directory or stable
  per-user storage for new plugin installations.
- Add SQLite read-only status/report without log imports or database creation.
- Add idempotent snapshot request keys for integration retries.
- New opt-in status-line setup uses a stable private launcher copy; existing
  launchers and settings are not silently replaced. Explicit refresh is available.
- Add portability, read-only, retry and public-tree privacy tests.

At 0.1.0, repository and licensing choices were pending; 0.1.1 supplies them.
Provider quotas are account-wide;
local project tokens are not exclusive session accounting or context occupancy.
