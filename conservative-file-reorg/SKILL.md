---
name: conservative-file-reorg
description: Conservative, transparent, context-aware file reorganization for local folders with deterministic taxonomy, duplicate staging, report generation, profile modulation, and rollback safety. Use when a user asks to clean up or systematize a directory tree, reclassify inbox folders, create repeatable file-overhaul workflows, generate audit/plan/apply reports, generate custom reorg profiles, or undo a prior reorganization run.
---

# Conservative File Reorg

## Workflow contract
1. Choose a profile file.
2. Run `audit`.
3. Run `plan` and inspect CSV outputs.
4. Run `apply` only after plan review.
5. Build rollback CSV.
6. Run `reclassify-inbox` as second pass when needed.

## Safety constraints
- Keep `no_delete=true` for conservative behavior.
- Stage exact duplicates under `99_Review_Duplicates/Exact/<date>/`.
- Stage variant mismatches under `99_Review_Duplicates/Needs_Review/<date>/`.
- Never mutate protected paths listed in profile.
- Keep append-only logs in `.docsys/reports/<date>/apply.log`.

## Commands
```bash
# Audit
python3 scripts/file_reorg.py audit \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --report-date 2026-02-22

# Plan
python3 scripts/file_reorg.py plan \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --scope loose \
  --report-date 2026-02-22

# Apply
python3 scripts/file_reorg.py apply \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --scope loose \
  --report-date 2026-02-22

# Reclassify inbox
python3 scripts/file_reorg.py reclassify-inbox \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --report-date 2026-02-22

# Build rollback
python3 scripts/file_reorg.py build-rollback \
  --root /ABSOLUTE/ROOT \
  --profile references/documents-default.toml \
  --report-date 2026-02-22

# Undo
python3 scripts/file_reorg.py undo \
  --rollback-csv /ABSOLUTE/ROOT/.docsys/reports/2026-02-22/rollback_from_apply_log.csv
```

## Profile modulation
Create a tailored profile with `new_profile.py`.

```bash
python3 scripts/new_profile.py \
  --template generic \
  --root /ABSOLUTE/ROOT \
  --detect-protected \
  --profile-id my-root-profile \
  --description "Conservative profile for my root" \
  --output references/my-root-profile.toml
```

Use your generated profile in subsequent runs.

## Transparency checks
Inspect:
- `.docsys/reports/<date>/inventory.csv`
- `.docsys/reports/<date>/exact_hash_duplicates.csv`
- `.docsys/reports/<date>/name_variant_candidates.csv`
- `.docsys/reports/<date>/move_plan.csv`
- `.docsys/reports/<date>/review_queue.csv`
- `.docsys/reports/<date>/apply.log`
- `.docsys/reports/<date>/rollback_from_apply_log.csv`
- `.docsys/reports/<date>/summary.json`

## Storage and versioning stance
- Store project files in `/Users/daedalus/Code/...`.
- Keep generated run artifacts inside target root `.docsys/reports/<date>/`.
- Keep profile definitions in git for reproducibility.
