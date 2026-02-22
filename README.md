# Conservative File Reorg Skill

A conservative, low-cognitive-load, transparent file-overhaul toolkit for Codex skills.

## What this is
- A reusable Codex skill: `conservative-file-reorg`
- A profile-driven Python engine for audit/plan/apply workflows
- A rollback-aware workflow with append-only logs and CSV artifacts

## What it does (safe by default)
- Audits a directory tree and fingerprints files
- Plans deterministic moves into a taxonomy
- Stages duplicates for review instead of deleting
- Reclassifies inboxes with stricter rules
- Archives large non-document artifacts by explicit rules
- Generates one-command rollback data

## 60-second quickstart (ADHD-friendly)
1. `cd /Users/daedalus/Code/personal/conservative-file-reorg-skill/conservative-file-reorg`
2. Run audit:

```bash
python3 scripts/file_reorg.py audit --root /ABSOLUTE/ROOT --profile references/documents-default.toml --report-date 2026-02-22
```

3. Run plan and inspect CSVs:

```bash
python3 scripts/file_reorg.py plan --root /ABSOLUTE/ROOT --profile references/documents-default.toml --scope loose --report-date 2026-02-22
```

4. Apply only after review:

```bash
python3 scripts/file_reorg.py apply --root /ABSOLUTE/ROOT --profile references/documents-default.toml --scope loose --report-date 2026-02-22
```

5. Build rollback:

```bash
python3 scripts/file_reorg.py build-rollback --root /ABSOLUTE/ROOT --profile references/documents-default.toml --report-date 2026-02-22
```

6. Undo if needed:

```bash
python3 scripts/file_reorg.py undo --rollback-csv /ABSOLUTE/ROOT/.docsys/reports/2026-02-22/rollback_from_apply_log.csv
```

## Key behavior constraints
- No deletion in normal workflow (`no_delete=true`)
- Protected paths are never reorganized
- Low-confidence routing goes to inbox
- Duplicate collisions are staged, not removed
- All meaningful operations are logged and reversible

## Modulation model
Adjust behavior by editing TOML profile files under `conservative-file-reorg/references/`.

- `documents-default.toml`: tuned for personal Documents cleanup
- `generic-default.toml`: reusable baseline for other roots

## Repository structure
- `conservative-file-reorg/SKILL.md`: trigger + workflow instructions
- `conservative-file-reorg/scripts/file_reorg.py`: engine
- `conservative-file-reorg/references/*.toml`: profile presets
- `conservative-file-reorg/agents/openai.yaml`: UI metadata

## Install as local Codex skill
Create/update symlink:

```bash
ln -sfn /Users/daedalus/Code/personal/conservative-file-reorg-skill/conservative-file-reorg /Users/daedalus/.codex/skills/conservative-file-reorg
```

## Best-practice alignment
This repo intentionally follows your filesystem-overhaul standards:
- canonical project storage under `/Users/daedalus/Code`
- deterministic path contracts
- aggressive transparency via reports and logs
- rollback-first safety controls
