"""Config builder: turn screw-organiser layouts into container manifests.

  gridfinity-config-builder [--layouts-dir ../screw-organiser/layouts]
                            [--config <layout.yaml> ...]
                            [--printer NAME] [--out configs] [--force]

Each layout becomes one editable manifest YAML in the output directory —
name, settings carried over (colors), and one `containers:` line per bin
with its label, size, count and gauge spec. Existing files are skipped
unless --force is given, so hand-edited manifests survive re-runs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .catalog import BIN_DEFAULTS, KNOWN_TYPES, find_layouts, load_source
from .printers import resolve_printer

# per-bin keys copied into the generated entries
_CARRY = ("count", "test", "head", "headDia", "headLength", "scoopRadius", "labels")


def _flow(value) -> str:
    return yaml.safe_dump(value, default_flow_style=True, sort_keys=False,
                          width=10_000).strip()


def _entries(layout: dict) -> list[str]:
    defaults = {**BIN_DEFAULTS, **layout.get("defaults", {})}
    lines = []
    for row in layout.get("rows", []):
        gy = row.get("units", 1)
        for bin_spec in row["bins"]:
            e: dict = {}
            if "label" in bin_spec:
                e["label"] = bin_spec["label"]
            btype = bin_spec.get("type", defaults["type"])
            if btype != "scoop" and btype in KNOWN_TYPES:
                e["type"] = btype
            e["size"] = f"{bin_spec.get('units', 1)}x{gy}"
            for key in _CARRY:
                if key in bin_spec:
                    e[key] = bin_spec[key]
            lines.append(f"  - {_flow(e)}")
    return lines


def build_manifest(layout: dict, source: Path, printer: str | None) -> str:
    head = [
        f"# Generated from {source} by gridfinity-config-builder — edit freely.",
        f"name: {layout['name']}",
        "heightUnits: 6",
    ]
    if printer:
        head.append(f"printer: {printer}")
    for key in ("colors", "testHoles"):
        if key in layout:
            head.append(f"{key}: {_flow(layout[key])}")
    return "\n".join(head) + "\ncontainers:\n" + "\n".join(_entries(layout)) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate container-manifest YAMLs from screw-organiser layouts")
    ap.add_argument("--config", action="append", metavar="LAYOUT",
                    help="layout file to convert (repeatable)")
    ap.add_argument("--layouts-dir", metavar="DIR",
                    help="convert every layout in DIR (default: ../screw-organiser/layouts)")
    ap.add_argument("--printer", metavar="NAME",
                    help="record this printer preset in the generated manifests")
    ap.add_argument("--out", default="configs", help="output directory (default: configs)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite manifests that already exist")
    args = ap.parse_args()

    if args.printer:
        resolve_printer(args.printer)  # validate the name early

    paths = [Path(c) for c in args.config or []]
    if args.layouts_dir:
        paths.extend(find_layouts(Path(args.layouts_dir)))
    if not paths:
        default_dir = Path("../screw-organiser/layouts")
        if default_dir.is_dir():
            paths = find_layouts(default_dir)
        else:
            raise SystemExit("no layouts given: use --config or --layouts-dir")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for path in paths:
        layout = load_source(path)
        if "rows" not in layout:
            print(f"  not a layout, skipping {path}")
            continue
        out_path = out_dir / f"{layout['name']}.yaml"
        if out_path.exists() and not args.force:
            print(f"  exists, skipping {out_path}")
            skipped += 1
            continue
        out_path.write_text(build_manifest(layout, path, args.printer))
        bins = sum(len(r["bins"]) for r in layout.get("rows", []))
        print(f"  wrote {out_path} ({bins} containers)")
        written += 1
    print(f"done: {written} written, {skipped} already existed")


if __name__ == "__main__":
    main()
