"""Printer presets: build-plate size, waste-tower type, slicer config.

Presets merge from three levels, later ones overriding by printer name:

1. the bundled printers.yaml next to this module (common printers),
2. the global user file ~/.config/gridfinity-container-builder/printers.yaml
   (XDG_CONFIG_HOME honoured) — the place for your own machines,
3. a printers.yaml in the current directory (per-project overrides).

A printer entry may also carry `slicerConfig: path/to/exported.ini` (an
exported PrusaSlicer config, relative paths resolved against the file
that defines it) so selecting the printer brings plate size, tower AND
the slicer config for multi-bed project 3MFs in one go.
"""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path

import yaml

from .exceptions import SpecError


def global_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "gridfinity-container-builder" / "printers.yaml"


def _layers() -> list[tuple[str, dict, Path | None]]:
    """(source label, data, dir for relative paths) per existing layer."""
    layers: list[tuple[str, dict, Path | None]] = [
        ("built-in", yaml.safe_load(
            files(__package__).joinpath("printers.yaml").read_text()), None),
    ]
    for label, path in (("global", global_config_path()),
                        ("local", Path("printers.yaml"))):
        if path.is_file():
            with path.open() as f:
                data = yaml.safe_load(f) or {}
            layers.append((label, data, path.parent))
    return layers


def load_printers() -> dict:
    """Merged printer table: {printers: {...}, towerSizes: {...},
    sources: [labels]}. Per-printer entries remember which layer defined
    them (for relative slicerConfig paths and the listing)."""
    printers: dict = {}
    tower_sizes: dict = {}
    sources = []
    for label, data, base_dir in _layers():
        sources.append(label)
        tower_sizes.update(data.get("towerSizes") or {})
        for name, cfg in (data.get("printers") or {}).items():
            cfg = dict(cfg)
            cfg["_source"] = label
            cfg["_dir"] = base_dir
            printers[name] = cfg
    return {"printers": printers, "towerSizes": tower_sizes, "sources": sources}


def tower_size(tower_type: str) -> dict | None:
    """Default reservation footprint for a tower type (merged tables)."""
    return load_printers()["towerSizes"].get(tower_type)


def resolve_printer(name: str) -> dict:
    """Return {plate, tower, towerSize|None, slicerConfig: abs path|None}."""
    data = load_printers()
    printers = data["printers"]
    if name not in printers:
        known = ", ".join(sorted(printers))
        raise SpecError(f"unknown printer {name!r} — known printers: {known}\n"
                        f"add your own in {global_config_path()}")
    p = dict(printers[name])
    tower = p.get("tower", "none")
    if "towerSize" not in p and tower != "none":
        p["towerSize"] = data["towerSizes"].get(tower)
    if p.get("slicerConfig"):
        cfg = Path(p["slicerConfig"]).expanduser()
        if not cfg.is_absolute() and p.get("_dir"):
            cfg = p["_dir"] / cfg
        p["slicerConfig"] = str(cfg)
    return p
