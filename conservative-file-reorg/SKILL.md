---
name: conservative-file-reorg
description: Conservative, transparent, context-aware file reorganization for local folders with deterministic taxonomy, duplicate staging, report generation, and rollback safety. Use when a user asks to clean up or systematize a directory tree, reclassify inbox folders, create repeatable file-overhaul workflows, generate audit/plan/apply reports, or undo a prior reorganization run.
---

# Conservative File Reorg

## Use this workflow
1. Select a profile:
- `references/documents-default.toml` for personal Documents workflows.
- `references/generic-default.toml` for general folders.
2. Run `audit` first.
3. Run `plan` and inspect `move_plan.csv` and `review_queue.csv`.
4. Run `apply` only after validating the plan.
5. Build rollback CSV and keep it with the same report date.

## Safety constraints
- Keep `no_delete=true` for conservative operation.
- Stage exact duplicates under `99_Review_Duplicates/Exact/<date>/`.
- Stage variant mismatches under `99_Review_Duplicates/Needs_Review/<date>/`.
- Never mutate protected paths listed in profile.
- Keep append-only logs in `.docsys/reports/<date>/apply.log`.

## Run commands
Use absolute paths for reproducibility.

```bash
# 1) Audit only
python3 scripts/file_reorg.py audit \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --report-date 2026-02-22

# 2) Plan without moving files
python3 scripts/file_reorg.py plan \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --scope loose \
  --report-date 2026-02-22

# 3) Apply conservative moves
python3 scripts/file_reorg.py apply \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --scope loose \
  --report-date 2026-02-22

# 4) Reclassify inbox with stricter pass
python3 scripts/file_reorg.py reclassify-inbox \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --report-date 2026-02-22

# 5) Build rollback CSV from apply.log
python3 scripts/file_reorg.py build-rollback \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --report-date 2026-02-22

# 6) Undo from rollback CSV
python3 scripts/file_reorg.py undo \
  --rollback-csv /ABSOLUTE/ROOT/.docsys/reports/2026-02-22/rollback_from_apply_log.csv
```

## Modulate behavior through profiles
Edit profile TOML instead of rewriting logic.

- Tune taxonomy with `taxonomy.folders` and `taxonomy.inbox`.
- Tune conservatism with `policies.min_confidence` and `context_awareness.low_confidence_to_inbox`.
- Tune protected areas with `[[protected_paths]]`.
- Tune categorization with `[[category]]` keyword and extension lists.
- Tune large-file archiving with `[archive]` settings.

## Preserve transparency and checks
Inspect these outputs on every run:
- `.docsys/reports/<date>/inventory.csv`
- `.docsys/reports/<date>/exact_hash_duplicates.csv`
- `.docsys/reports/<date>/name_variant_candidates.csv`
- `.docsys/reports/<date>/move_plan.csv`
- `.docsys/reports/<date>/review_queue.csv`
- `.docsys/reports/<date>/apply.log`
- `.docsys/reports/<date>/rollback_from_apply_log.csv`
- `.docsys/reports/<date>/summary.json`

## Keep project storage aligned with filesystem-overhaul best practices
- Store this skill project in `/Users/daedalus/Code/...`.
- Keep versioned project files in git.
- Avoid developing this skill directly inside `Desktop` or `Documents`.
- Keep generated run artifacts in target folder `.docsys/reports/<date>/`.
