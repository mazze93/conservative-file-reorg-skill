#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
try:
    import tomllib  # py311+
except ModuleNotFoundError:
    import tomli as tomllib  # py39/py310
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

VARIANT_RE = re.compile(
    r"^(?P<stem>.*?)(?:\s+(?:2|3|4)|\s+copy(?:\s+\d+)?|\(\d+\))(?P<ext>\.[^.]+)?$",
    re.IGNORECASE,
)
MULTISPACE_RE = re.compile(r"\s+")


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class FileRec:
    path: Path
    size: int
    mtime: float
    sha256: str
    ext: str


@dataclass
class Action:
    source_path: Path
    target_path: Path
    reason: str
    confidence: float
    duplicate_group_id: str
    action_type: str


class ReorgProfile:
    def __init__(self, data: dict, profile_path: Path):
        self.data = data
        self.profile_path = profile_path

        taxonomy = data.get("taxonomy", {})
        policies = data.get("policies", {})
        ctx = data.get("context_awareness", {})

        self.folders: List[str] = taxonomy.get("folders", [])
        self.inbox: str = taxonomy.get("inbox", "00_Inbox")
        self.review_exact: str = taxonomy.get("review_exact", "99_Review_Duplicates/Exact")
        self.review_needs: str = taxonomy.get("review_needs", "99_Review_Duplicates/Needs_Review")
        self.archive: str = taxonomy.get("archive", "90_Archive")
        self.no_delete: bool = bool(policies.get("no_delete", True))
        self.conservative: bool = bool(policies.get("conservative", True))
        self.touch_symlinks: bool = bool(policies.get("touch_symlinks", False))
        self.min_confidence: float = float(policies.get("min_confidence", 0.72))
        self.low_conf_to_inbox: bool = bool(ctx.get("low_confidence_to_inbox", True))
        self.context_enabled: bool = bool(ctx.get("enabled", True))
        self.prefer_existing: bool = bool(ctx.get("prefer_existing_category", True))
        self.keep_inbox: set[str] = set(data.get("inbox_policy", {}).get("keep_filenames", ["README.md", ".DS_Store"]))
        self.root_exclude: set[str] = set(data.get("policies", {}).get("exclude_top_level", [".docsys", ".git", "node_modules"]))
        self.protected_paths: set[str] = set(p["path"] for p in data.get("protected_paths", []) if p.get("path"))
        self.archive_root_template: str = data.get("archive", {}).get("root", "{HOME}/Archives/Documents_Large_Artifacts")
        self.archive_non_doc_over_mb: int = int(data.get("archive", {}).get("non_document_over_mb", 200))
        self.archive_name_patterns: List[str] = list(data.get("archive", {}).get("name_patterns", ["trace"]))
        self.document_extensions: set[str] = set(data.get("archive", {}).get("document_extensions", []))
        self.categories: List[dict] = data.get("category", [])

    @staticmethod
    def load(profile_path: Path) -> "ReorgProfile":
        with profile_path.open("rb") as f:
            data = tomllib.load(f)
        return ReorgProfile(data, profile_path)


def default_report_date() -> str:
    return datetime.now().date().isoformat()


def normalize_spaces(name: str) -> str:
    return MULTISPACE_RE.sub(" ", name).strip()


def remove_variant_suffix(name: str) -> str:
    m = VARIANT_RE.match(name)
    if not m:
        return name
    return f"{m.group('stem')}{m.group('ext') or ''}"


def has_variant_suffix(name: str) -> bool:
    return VARIANT_RE.match(name) is not None


def extension(path: Path) -> str:
    s = path.suffix.lower().lstrip(".")
    return s if s else "[no_ext]"


def top_component(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else ""


def is_under_top(path: Path, root: Path, names: set[str]) -> bool:
    try:
        t = top_component(path, root)
    except Exception:
        return False
    return t in names


def iter_files(root: Path, touch_symlinks: bool = False) -> Iterable[Path]:
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.is_symlink() and not touch_symlinks:
                continue
            yield p


def collect_inventory(root: Path, profile: ReorgProfile) -> List[FileRec]:
    records: List[FileRec] = []
    for p in iter_files(root, touch_symlinks=profile.touch_symlinks):
        if is_under_top(p, root, profile.root_exclude):
            continue
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        except PermissionError:
            continue
        try:
            file_hash = sha256sum(p)
        except (FileNotFoundError, PermissionError, OSError):
            continue
        records.append(
            FileRec(path=p, size=st.st_size, mtime=st.st_mtime, sha256=file_hash, ext=extension(p))
        )
    return records


def route_file(
    rec: FileRec,
    profile: ReorgProfile,
    root: Path,
    duplicate_canonical_category: Optional[str],
) -> Tuple[str, str, float]:
    name = rec.path.name.lower()
    parent = str(rec.path.parent).lower()
    corpus = f"{name} {parent}"

    if duplicate_canonical_category:
        return duplicate_canonical_category, "duplicate canonical category hint", 0.99

    best_folder = profile.inbox
    best_score = 0.0
    best_reason = "ambiguous"

    for cat in profile.categories:
        folder = cat.get("folder", profile.inbox)
        keywords = [k.lower() for k in cat.get("keywords", [])]
        exts = set(x.lower() for x in cat.get("extensions", []))
        weight = float(cat.get("weight", 1.0))

        score = 0.0
        hits = []
        for kw in keywords:
            if kw and kw in corpus:
                score += 1.0
                hits.append(kw)

        if exts and rec.ext.lower() in exts:
            score += 0.6

        score *= weight

        if score > best_score:
            best_score = score
            best_folder = folder
            best_reason = f"keyword/ext match: {', '.join(hits[:4])}" if hits else "extension weighted match"

    # Keep conservative defaults while allowing single strong keyword hits to route.
    confidence = min(0.99, 0.58 + best_score * 0.22) if best_score > 0 else 0.45

    if profile.context_enabled and profile.prefer_existing:
        if is_under_top(rec.path, root, set(profile.folders)):
            existing = top_component(rec.path, root)
            if existing:
                best_folder = existing
                best_reason = "existing taxonomy placement"
                confidence = max(confidence, 0.95)

    if profile.low_conf_to_inbox and confidence < profile.min_confidence:
        return profile.inbox, f"low confidence ({confidence:.2f}) -> inbox", confidence

    return best_folder, best_reason, confidence


def canonical_sort_key(path: Path, mtime: float, root: Path) -> Tuple[int, int, float, str]:
    non_variant = 0 if not has_variant_suffix(path.name) else 1
    legacy = 1 if path.is_relative_to(root / "2021_Documents") else 0
    return (non_variant, legacy, -mtime, str(path))


def write_csv(path: Path, headers: List[str], rows: List[List[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def unique_target(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        cand = path.with_name(f"{stem}__dup{i}{suffix}")
        if not cand.exists():
            return cand
        i += 1


def paths_from_log(log_path: Path) -> List[Tuple[str, Path, Path]]:
    moves = []
    rex = re.compile(r" MOVE action=(.*?) src=(.*?) dst=(.*?) reason=")
    if not log_path.exists():
        return moves
    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = rex.search(line)
        if m:
            moves.append((m.group(1), Path(m.group(2)), Path(m.group(3))))
    return moves


def build_report_paths(root: Path, report_date: str) -> dict:
    rep = root / ".docsys" / "reports" / report_date
    return {
        "report_dir": rep,
        "inventory": rep / "inventory.csv",
        "exact": rep / "exact_hash_duplicates.csv",
        "same_size": rep / "same_size_candidates.csv",
        "variants": rep / "name_variant_candidates.csv",
        "move_plan": rep / "move_plan.csv",
        "review_queue": rep / "review_queue.csv",
        "apply_log": rep / "apply.log",
        "summary": rep / "summary.json",
        "rollback_csv": rep / "rollback_from_apply_log.csv",
        "large_moves": rep / "large_artifact_moves.csv",
        "inbox_second_pass": rep / "second_pass_inbox_reclassify.csv",
        "inbox_second_log": rep / "second_pass_apply.log",
    }


def ensure_taxonomy(root: Path, profile: ReorgProfile, report_date: str) -> None:
    for d in profile.folders:
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / profile.review_exact / report_date).mkdir(parents=True, exist_ok=True)
    (root / profile.review_needs / report_date).mkdir(parents=True, exist_ok=True)


def build_plan(
    root: Path,
    profile: ReorgProfile,
    report_date: str,
    scope: str,
    inventory: List[FileRec],
    second_pass_inbox: bool = False,
) -> Tuple[List[Action], List[List[object]], dict]:
    rec_by_path = {r.path: r for r in inventory}

    by_hash: Dict[str, List[FileRec]] = defaultdict(list)
    by_size: Dict[int, List[FileRec]] = defaultdict(list)
    for r in inventory:
        by_hash[r.sha256].append(r)
        by_size[r.size].append(r)

    dup_groups = {h: rs for h, rs in by_hash.items() if len(rs) > 1}
    dup_gid = {h: f"dup_{i:04d}" for i, h in enumerate(sorted(dup_groups.keys()), start=1)}

    canonical_by_hash: Dict[str, Path] = {}
    for h, rs in dup_groups.items():
        sorted_rs = sorted(rs, key=lambda r: canonical_sort_key(r.path, r.mtime, root))
        canonical_by_hash[h] = sorted_rs[0].path

    # Duplicate reports.
    exact_rows: List[List[object]] = []
    for h, rs in sorted(dup_groups.items()):
        canon = canonical_by_hash[h]
        gid = dup_gid[h]
        for r in sorted(rs, key=lambda x: str(x.path)):
            exact_rows.append([
                gid,
                h,
                str(canon),
                1 if r.path == canon else 0,
                str(r.path),
                r.size,
                datetime.fromtimestamp(r.mtime).isoformat(timespec="seconds"),
            ])

    same_rows: List[List[object]] = []
    for size, rs in sorted(by_size.items(), key=lambda kv: kv[0], reverse=True):
        if len(rs) < 2:
            continue
        gid = f"size_{size}"
        for r in sorted(rs, key=lambda x: str(x.path)):
            same_rows.append([gid, size, len(rs), str(r.path), r.sha256])

    # Name variants report.
    variant_rows: List[List[object]] = []
    variant_mismatch: set[Path] = set()
    missing_canonical: List[Tuple[Path, str]] = []
    for r in inventory:
        if r.path.parent != root:
            continue
        name = r.path.name
        canonical_name = remove_variant_suffix(name)
        if canonical_name == name:
            continue
        cpath = root / canonical_name
        exists = cpath.exists()
        hm = ""
        if exists and cpath in rec_by_path:
            hm = "1" if rec_by_path[cpath].sha256 == r.sha256 else "0"
            if hm == "0":
                variant_mismatch.add(r.path)
        elif exists:
            hm = "unknown"
        else:
            missing_canonical.append((r.path, canonical_name))
        variant_rows.append([str(r.path), name, canonical_name, str(cpath), 1 if exists else 0, hm])

    # Candidate selection.
    candidates: List[FileRec] = []
    for r in inventory:
        if is_under_top(r.path, root, profile.protected_paths):
            continue
        if is_under_top(r.path, root, profile.root_exclude):
            continue
        if scope == "inbox":
            if r.path.parent != (root / profile.inbox):
                continue
            if r.path.name in profile.keep_inbox:
                continue
        elif scope == "loose":
            if r.path.parent != root:
                continue
            if r.path.name.startswith("."):
                continue
        elif scope == "all":
            if is_under_top(r.path, root, set(profile.folders)):
                continue
        candidates.append(r)

    duplicate_category_hint: Dict[Path, str] = {}
    for h, rs in dup_groups.items():
        canon = canonical_by_hash[h]
        top = top_component(canon, root)
        if top in profile.folders:
            for r in rs:
                duplicate_category_hint[r.path] = top

    actions: List[Action] = []
    review_rows: List[List[object]] = []

    exact_review_dir = root / profile.review_exact / report_date
    need_review_dir = root / profile.review_needs / report_date

    # Non-canonical exact duplicates.
    noncanon_exact: set[Path] = set()
    for h, rs in dup_groups.items():
        canon = canonical_by_hash[h]
        for r in rs:
            if r.path != canon:
                noncanon_exact.add(r.path)

    for r in sorted(candidates, key=lambda x: str(x.path)):
        gid = dup_gid.get(r.sha256, "")

        if r.path in noncanon_exact:
            tgt = exact_review_dir / normalize_spaces(r.path.name)
            actions.append(Action(r.path, tgt, "exact duplicate non-canonical", 1.0, gid, "stage_exact_duplicate"))
            continue

        if r.path in variant_mismatch:
            tgt = need_review_dir / normalize_spaces(r.path.name)
            actions.append(Action(r.path, tgt, "name variant hash mismatch", 0.80, gid, "stage_needs_review"))
            review_rows.append([str(r.path), "name_variant_hash_mismatch", "stage_to_needs_review", "Canonical sibling exists with different content hash"]) 
            continue

        folder, reason, conf = route_file(r, profile, root, duplicate_category_hint.get(r.path))
        tgt_name = normalize_spaces(r.path.name)

        if has_variant_suffix(r.path.name):
            canonical_name = remove_variant_suffix(r.path.name)
            cpath = r.path.parent / canonical_name
            if cpath.exists() and cpath in rec_by_path and rec_by_path[cpath].sha256 == r.sha256:
                tgt_name = normalize_spaces(canonical_name)

        tgt = root / folder / tgt_name
        action_type = "move_to_category" if not second_pass_inbox else "reclassify_inbox"
        actions.append(Action(r.path, tgt, reason, conf, gid, action_type))

    for p, expected in missing_canonical:
        review_rows.append([str(p), "missing_canonical_filename", "manual_review", f"Expected canonical filename missing: {expected}"])

    counts = {
        "inventory_count": len(inventory),
        "candidate_count": len(candidates),
        "duplicate_group_count": len(dup_groups),
        "actions_count": len(actions),
        "variant_mismatch_count": len(variant_mismatch),
        "missing_canonical_count": len(missing_canonical),
    }

    return actions, review_rows, {
        "exact_rows": exact_rows,
        "same_rows": same_rows,
        "variant_rows": variant_rows,
        "counts": counts,
    }


def write_plan_reports(
    root: Path,
    report_paths: dict,
    inventory: List[FileRec],
    plan_actions: List[Action],
    review_rows: List[List[object]],
    extras: dict,
) -> None:
    inv_rows = []
    for r in sorted(inventory, key=lambda x: str(x.path)):
        inv_rows.append([
            str(r.path),
            r.size,
            datetime.fromtimestamp(r.mtime).isoformat(timespec="seconds"),
            r.sha256,
            top_component(r.path, root),
            r.ext,
        ])

    write_csv(report_paths["inventory"], ["path", "size_bytes", "mtime_iso", "sha256", "top_level_dir", "extension"], inv_rows)
    write_csv(report_paths["exact"], ["duplicate_group_id", "sha256", "canonical_path", "is_canonical", "path", "size_bytes", "mtime_iso"], extras["exact_rows"])
    write_csv(report_paths["same_size"], ["size_group_id", "size_bytes", "group_count", "path", "sha256"], extras["same_rows"])
    write_csv(report_paths["variants"], ["path", "filename", "canonical_filename", "canonical_path", "canonical_exists", "hash_match_with_canonical"], extras["variant_rows"])

    move_rows = [
        [str(a.source_path), str(a.target_path), a.reason, f"{a.confidence:.2f}", a.duplicate_group_id, a.action_type]
        for a in plan_actions
    ]
    write_csv(report_paths["move_plan"], ["source_path", "target_path", "reason", "confidence", "duplicate_group_id", "action_type"], move_rows)
    write_csv(report_paths["review_queue"], ["path", "issue_type", "recommended_action", "notes"], review_rows)

    summary = {
        "generated_at": utc_now(),
        **extras["counts"],
        "move_plan_csv": str(report_paths["move_plan"]),
        "review_queue_csv": str(report_paths["review_queue"]),
    }
    report_paths["summary"].parent.mkdir(parents=True, exist_ok=True)
    report_paths["summary"].write_text(json.dumps(summary, indent=2), encoding="utf-8")


def apply_actions(root: Path, profile: ReorgProfile, actions: List[Action], report_paths: dict) -> List[List[object]]:
    log = report_paths["apply_log"]
    large_rows: List[List[object]] = []
    exact_review_dir = root / profile.review_exact / default_report_date()
    need_review_dir = root / profile.review_needs / default_report_date()

    with log.open("a", encoding="utf-8") as lf:
        lf.write(f"[{datetime.now().isoformat(timespec='seconds')}] START apply\n")
        for a in actions:
            src = a.source_path
            dst = a.target_path

            if not src.exists():
                lf.write(f"[{datetime.now().isoformat(timespec='seconds')}] SKIP missing src={src}\n")
                continue
            if src == dst:
                lf.write(f"[{datetime.now().isoformat(timespec='seconds')}] SKIP no-op src={src}\n")
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            final = dst

            if final.exists():
                src_h = sha256sum(src)
                dst_h = sha256sum(final)
                if src_h == dst_h:
                    final = unique_target(exact_review_dir / normalize_spaces(src.name))
                    reason = "target already exists with identical hash"
                    act = "stage_exact_duplicate"
                else:
                    final = unique_target(need_review_dir / normalize_spaces(src.name))
                    reason = "target collision with different hash"
                    act = "stage_needs_review"
            else:
                reason = a.reason
                act = a.action_type

            final.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(final))
            lf.write(
                f"[{datetime.now().isoformat(timespec='seconds')}] MOVE action={act} src={src} dst={final} reason={reason} confidence={a.confidence:.2f} dup_gid={a.duplicate_group_id}\n"
            )

        lf.write(f"[{datetime.now().isoformat(timespec='seconds')}] END apply\n")

    # Archive large artifacts after apply.
    archive_root = Path(profile.archive_root_template.format(HOME=str(Path.home())))
    archive_date = default_report_date()
    archive_dir = archive_root / archive_date
    archive_dir.mkdir(parents=True, exist_ok=True)

    mb_cutoff = profile.archive_non_doc_over_mb * 1024 * 1024

    for p in iter_files(root, touch_symlinks=profile.touch_symlinks):
        if is_under_top(p, root, profile.root_exclude):
            continue
        if is_under_top(p, root, profile.protected_paths):
            continue
        if is_under_top(p, root, {profile.review_exact.split("/")[0], profile.review_needs.split("/")[0]}):
            continue
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        ext = extension(p)
        is_trace = any(pat.lower() in p.name.lower() for pat in profile.archive_name_patterns)
        is_large_non_doc = st.st_size > mb_cutoff and ext not in profile.document_extensions
        if not (is_trace or is_large_non_doc):
            continue
        dst = unique_target(archive_dir / normalize_spaces(p.name))
        shutil.move(str(p), str(dst))
        large_rows.append([str(p), str(dst), st.st_size, "name pattern" if is_trace else f"non-document > {profile.archive_non_doc_over_mb}MB", utc_now()])

    write_csv(report_paths["large_moves"], ["source_path", "archive_path", "size_bytes", "rule", "moved_at"], large_rows)
    return large_rows


def build_rollback_csv(report_paths: dict) -> None:
    moves = paths_from_log(report_paths["apply_log"])
    remap = {}
    if report_paths["large_moves"].exists():
        with report_paths["large_moves"].open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                remap[row["source_path"]] = row["archive_path"]

    rows = []
    for order, (act, src, dst) in enumerate(reversed(moves), start=1):
        current = Path(remap.get(str(dst), str(dst)))
        rows.append([order, str(current), str(src), act, str(dst)])

    write_csv(
        report_paths["rollback_csv"],
        ["rollback_order", "current_path", "rollback_destination", "original_action", "original_logged_dst"],
        rows,
    )


def undo_from_csv(csv_path: Path) -> Tuple[int, int]:
    moved = 0
    skipped = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cur = Path(row["current_path"])
            dst = Path(row["rollback_destination"])
            if cur.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                cur.rename(dst)
                moved += 1
            else:
                skipped += 1
    return moved, skipped


def resolve_profile_path(args: argparse.Namespace) -> Path:
    if args.profile:
        return Path(args.profile).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "references" / "documents-default.toml")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Conservative file reorganization with reports and rollback")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--root", required=True, help="Root folder to reorganize")
        sp.add_argument("--profile", help="Path to TOML profile")
        sp.add_argument("--report-date", default=default_report_date(), help="Report date key (YYYY-MM-DD)")

    sp_audit = sub.add_parser("audit", help="Generate inventory and duplicate reports only")
    add_common(sp_audit)

    sp_plan = sub.add_parser("plan", help="Generate move plan and review queue without moving files")
    add_common(sp_plan)
    sp_plan.add_argument("--scope", choices=["loose", "all", "inbox"], default="loose")

    sp_apply = sub.add_parser("apply", help="Apply planned moves conservatively and archive large artifacts")
    add_common(sp_apply)
    sp_apply.add_argument("--scope", choices=["loose", "all", "inbox"], default="loose")

    sp_inbox = sub.add_parser("reclassify-inbox", help="Run stricter second pass on inbox only")
    add_common(sp_inbox)

    sp_rb = sub.add_parser("build-rollback", help="Build rollback CSV from apply log")
    add_common(sp_rb)

    sp_undo = sub.add_parser("undo", help="Undo using rollback CSV")
    sp_undo.add_argument("--rollback-csv", required=True, help="Path to rollback CSV")

    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.command == "undo":
        moved, skipped = undo_from_csv(Path(args.rollback_csv).expanduser().resolve())
        print(json.dumps({"moved": moved, "skipped_missing": skipped}, indent=2))
        return 0

    root = Path(args.root).expanduser().resolve()
    profile = ReorgProfile.load(resolve_profile_path(args))
    report_paths = build_report_paths(root, args.report_date)

    ensure_taxonomy(root, profile, args.report_date)
    inv = collect_inventory(root, profile)

    scope = getattr(args, "scope", "loose")
    second_pass = args.command == "reclassify-inbox"
    if second_pass:
        scope = "inbox"

    actions, review_rows, extras = build_plan(root, profile, args.report_date, scope, inv, second_pass_inbox=second_pass)
    write_plan_reports(root, report_paths, inv, actions, review_rows, extras)

    if args.command == "audit":
        out = {
            "mode": "audit",
            "report_dir": str(report_paths["report_dir"]),
            **extras["counts"],
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.command == "plan":
        out = {
            "mode": "plan",
            "report_dir": str(report_paths["report_dir"]),
            "move_plan": str(report_paths["move_plan"]),
            "review_queue": str(report_paths["review_queue"]),
            **extras["counts"],
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.command in {"apply", "reclassify-inbox"}:
        large = apply_actions(root, profile, actions, report_paths)
        build_rollback_csv(report_paths)

        if second_pass:
            # Emit focused second-pass artifact for transparency.
            rows = []
            rex = re.compile(r" MOVE action=(.*?) src=(.*?) dst=(.*?) reason=(.*?) confidence=([0-9.]+)")
            for line in report_paths["apply_log"].read_text(encoding="utf-8").splitlines():
                m = rex.search(line)
                if m and m.group(1) == "reclassify_inbox":
                    rows.append([m.group(2), m.group(3), m.group(4), m.group(5)])
            write_csv(report_paths["inbox_second_pass"], ["source_path_before", "destination_path_after", "reason", "confidence"], rows)

        out = {
            "mode": args.command,
            "report_dir": str(report_paths["report_dir"]),
            "applied_actions": len(actions),
            "large_artifacts_archived": len(large),
            "rollback_csv": str(report_paths["rollback_csv"]),
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.command == "build-rollback":
        build_rollback_csv(report_paths)
        print(json.dumps({"rollback_csv": str(report_paths["rollback_csv"])}, indent=2))
        return 0

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
