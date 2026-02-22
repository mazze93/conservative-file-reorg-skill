# Installation & Usage

## 1) Clone
```bash
git clone https://github.com/mazze93/conservative-file-reorg-skill.git
cd conservative-file-reorg-skill/conservative-file-reorg
```

## 2) Python compatibility
Requires Python `3.9+`.

No external runtime dependency is required for core workflow.

## 3) Use defaults
```bash
python3 scripts/file_reorg.py audit --root /ABSOLUTE/ROOT --profile references/generic-default.toml --report-date 2026-02-22
python3 scripts/file_reorg.py plan --root /ABSOLUTE/ROOT --profile references/generic-default.toml --scope loose --report-date 2026-02-22
python3 scripts/file_reorg.py apply --root /ABSOLUTE/ROOT --profile references/generic-default.toml --scope loose --report-date 2026-02-22
```

## 4) Optional second pass for inbox
```bash
python3 scripts/file_reorg.py reclassify-inbox --root /ABSOLUTE/ROOT --profile references/generic-default.toml --report-date 2026-02-22
```

## 5) Rollback
```bash
python3 scripts/file_reorg.py build-rollback --root /ABSOLUTE/ROOT --profile references/generic-default.toml --report-date 2026-02-22
python3 scripts/file_reorg.py undo --rollback-csv /ABSOLUTE/ROOT/.docsys/reports/2026-02-22/rollback_from_apply_log.csv
```

## 6) Create custom profile quickly
```bash
python3 scripts/new_profile.py --template generic --root /ABSOLUTE/ROOT --detect-protected --output references/custom.toml
```
