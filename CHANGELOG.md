# Changelog

All notable changes to MyTimeLogger are documented here.

This project uses OpenSpec for detailed implementation history. This changelog is the short, public-facing release log for readers who do not need every proposal and execution report.

## [Unreleased]

### Changed

- Cleaned the repository boundary for open-source publishing: local databases, logs, runtime data, reports, caches, and personal agent state stay out of Git.
- Kept tool-required root entry files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `codex.md`) discoverable, while local agent state directories are ignored by Git and can be hidden in Windows Explorer.
- Updated legacy Python tests to target current `server.*` package boundaries instead of the removed `app.*` package.
- Updated `scripts/migrate_to_cloud.py` to write IDs and timestamps required by the current server schema.

### Fixed

- Fixed local `external_rewards` goal settlement to write `ext_id` instead of overloading the autoincrement `id` column.
- Fixed local reward claiming to use `ext_id` consistently when claiming external rewards.
- Fixed local schema migration v6 to v7 so `ensure_schema()` no longer references an undefined variable.

### Removed

- Removed an obsolete Python unit test for the deleted `MyTimeLoggerLogic` client module.

## Historical Notes

Older detailed implementation records live under `openspec/changes/archive/` and the Git history.
