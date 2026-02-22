#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import tomllib  # py311+
except ModuleNotFoundError:
    import tomli as tomllib  # py39/py310


KNOWN_APP_MANAGED_DIRS = [
    "Obsidian Vault",
    "Welcome to Bear 👋",
    "BFD Drums",
    "BearBk",
    "MPC",
    "MPC 3",
    "PhoenixDown",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a conservative TOML profile for file_reorg.py"
    )
    p.add_argument(
        "--template",
        choices=["documents", "generic"],
        default="generic",
        help="Base template preset",
    )
    p.add_argument(
        "--template-path",
        help="Optional explicit template path (overrides --template)",
    )
    p.add_argument("--output", required=True, help="Output TOML profile path")
    p.add_argument("--profile-id", help="metadata.name override")
    p.add_argument("--description", help="metadata.description override")
    p.add_argument("--root", help="Target root path for optional protected-path inference")
    p.add_argument(
        "--detect-protected",
        action="store_true",
        default=False,
        help="Infer app-managed protected directories from --root",
    )
    p.add_argument("--min-confidence", type=float, help="policies.min_confidence override")
    p.add_argument("--archive-root", help="archive.root override")
    return p.parse_args()


def template_path(args: argparse.Namespace) -> Path:
    if args.template_path:
        return Path(args.template_path).expanduser().resolve()
    base = Path(__file__).resolve().parent.parent / "references"
    if args.template == "documents":
        return base / "documents-default.toml"
    return base / "generic-default.toml"


def fmt_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # Keep concise float formatting.
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return json.dumps(str(v), ensure_ascii=False)


def fmt_list(values) -> str:
    return "[" + ", ".join(fmt_scalar(v) for v in values) + "]"


def write_kv(lines: list[str], key: str, val) -> None:
    if isinstance(val, list):
        lines.append(f"{key} = {fmt_list(val)}")
    else:
        lines.append(f"{key} = {fmt_scalar(val)}")


def dumps_profile(data: dict) -> str:
    lines: list[str] = []

    section_order = [
        "metadata",
        "taxonomy",
        "policies",
        "context_awareness",
        "inbox_policy",
        "archive",
    ]

    for sec in section_order:
        if sec not in data:
            continue
        lines.append(f"[{sec}]")
        for k, v in data[sec].items():
            write_kv(lines, k, v)
        lines.append("")

    for item in data.get("protected_paths", []):
        lines.append("[[protected_paths]]")
        for k, v in item.items():
            write_kv(lines, k, v)
        lines.append("")

    for item in data.get("category", []):
        lines.append("[[category]]")
        for k, v in item.items():
            write_kv(lines, k, v)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def infer_protected(root: Path, existing: list[dict]) -> list[dict]:
    existing_paths = {x.get("path") for x in existing}
    updated = list(existing)

    if not root.exists() or not root.is_dir():
        return updated

    present = {p.name for p in root.iterdir() if p.is_dir()}
    for name in KNOWN_APP_MANAGED_DIRS:
        if name in present and name not in existing_paths:
            updated.append({"path": name, "reason": "auto-detected app-managed"})

    return updated


def main() -> int:
    args = parse_args()
    tpath = template_path(args)

    if not tpath.exists():
        raise SystemExit(f"Template not found: {tpath}")

    with tpath.open("rb") as f:
        data = tomllib.load(f)

    data.setdefault("metadata", {})
    data.setdefault("policies", {})
    data.setdefault("archive", {})

    if args.profile_id:
        data["metadata"]["name"] = args.profile_id
    if args.description:
        data["metadata"]["description"] = args.description
    if args.min_confidence is not None:
        data["policies"]["min_confidence"] = float(args.min_confidence)
    if args.archive_root:
        data["archive"]["root"] = args.archive_root

    protected = data.get("protected_paths", [])
    if args.detect_protected and args.root:
        root = Path(args.root).expanduser().resolve()
        protected = infer_protected(root, protected)
    data["protected_paths"] = protected

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_profile(data), encoding="utf-8")

    print(
        json.dumps(
            {
                "template": str(tpath),
                "output": str(out),
                "profile_name": data.get("metadata", {}).get("name", ""),
                "protected_paths": len(data.get("protected_paths", [])),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
