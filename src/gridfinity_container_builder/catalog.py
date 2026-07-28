"""Build the list of containers to make from config files.

Two config schemas are accepted, distinguished by their keys:

- a screw-organiser **layout** (has `rows`): every bin entry becomes one
  container, the bin's width in layout units mapping 1:1 to Gridfinity X
  units and its row's depth to Y units;
- a container **manifest** (has `containers` and/or `layouts`): a direct
  list of containers to build, plus optional layout files to pull in.

Containers are auto-sized to fit their contents: the item length parsed
from the test spec or label (M3x30 -> 30 mm) sets the minimum width so the
item can lie flat inside. The same container appearing twice (same label,
size and geometry) is deduplicated and records all its sources.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BIN_DEFAULTS = {"type": "scoop", "scoopRadius": 10.0, "rampAngle": 63.435}
KNOWN_TYPES = ("scoop", "deep", "open")

GF_PITCH = 42.0
GF_CLEARANCE = 0.5  # bin footprint = pitch - clearance
GF_WALL = 2.6
ITEM_MARGIN = 2.0  # free length around an item lying flat

# bin_spec keys that change the geometry — used to detect conflicting
# definitions of the same container across sources
_GEOMETRY_KEYS = ("test", "head", "headDia", "headLength", "scoopRadius", "labels")

# "M3x30", "2.9x8.5", "5x120sh" — needs the explicit length part
_ITEM_RE = re.compile(r"\bM?\d+(?:\.\d+)?x(\d+(?:\.\d+)?)", re.I)
# a full screw size (M3x8, M2.5x10) — bare "M3n"/"M3 wshr"/"M5-4 fit"
# are nuts, washers and friends, which get no gauge
_SCREW_LABEL_RE = re.compile(r"\bM\d+(?:\.\d+)?x\d", re.I)


@dataclass
class ContainerSpec:
    slug: str
    gx: int
    gy: int
    type: str
    ramp_angle: float
    scoop_radius: float
    bin: dict  # raw bin entry (label, test, head, count, ...)
    height_units: int | None = None  # override of the global height
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str | None:
        if self.type == "open":
            return None
        return self.bin["label"] if "label" in self.bin else "Misc"

    @property
    def footprint(self) -> tuple[float, float]:
        return (self.gx * GF_PITCH - GF_CLEARANCE, self.gy * GF_PITCH - GF_CLEARANCE)

    def geometry_key(self) -> str:
        geo = {k: self.bin.get(k) for k in _GEOMETRY_KEYS if k in self.bin}
        geo.update(type=self.type, rampAngle=self.ramp_angle,
                   scoopRadius=self.scoop_radius, label=self.label,
                   heightUnits=self.height_units)
        return json.dumps(geo, sort_keys=True)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "bin"


def interior_width(gx: int) -> float:
    return gx * GF_PITCH - GF_CLEARANCE - 2 * GF_WALL


def item_length(bin_spec: dict) -> float | None:
    """Length of the item the container holds, in mm, if it can be parsed.

    Explicit test lengths win; otherwise the label is parsed, but only
    patterns with an explicit length part (M3x30, 2.9x8.5, 5x120sh) count —
    a bare number like "625 brg" is a part name, not a dimension.
    """
    t = bin_spec.get("test")
    if isinstance(t, dict) and t.get("length"):
        return float(t["length"])
    if isinstance(t, str):
        m = _ITEM_RE.search(t)
        if m:
            return float(m.group(1))
    m = _ITEM_RE.search(str(bin_spec.get("label", "")))
    return float(m.group(1)) if m else None


def units_for_length(length: float) -> int:
    """Smallest gridfinity width whose interior fits the item lying flat."""
    return max(1, math.ceil((length + ITEM_MARGIN + GF_CLEARANCE + 2 * GF_WALL) / GF_PITCH))


def load_source(path: str | Path) -> dict:
    p = Path(path)
    with p.open() as f:
        doc = yaml.safe_load(f) if p.suffix in (".yaml", ".yml") else json.load(f)
    doc.setdefault("name", p.stem)
    doc["_dir"] = p.parent
    return doc


def is_manifest(doc: dict) -> bool:
    return "containers" in doc or "layouts" in doc


def _autosized(gx: int, bin_spec: dict, grow_only: bool, warnings: list[str],
               slug_hint: str) -> int:
    length = item_length(bin_spec)
    if length is None:
        return gx
    need = units_for_length(length)
    if need > gx:
        if grow_only:
            warnings.append(
                f"{slug_hint}: grew to {need} units wide so a {length:g} mm item fits")
        return need
    return gx


def containers_from_layout(layout: dict) -> list[ContainerSpec]:
    defaults = {**BIN_DEFAULTS, **layout.get("defaults", {})}
    source = layout["name"]
    specs: list[ContainerSpec] = []
    for row in layout.get("rows", []):
        gy = row.get("units", 1)
        for bin_spec in row["bins"]:
            btype = bin_spec.get("type", defaults["type"])
            warnings: list[str] = []
            if btype not in KNOWN_TYPES:
                warnings.append(f'unknown bin type "{btype}" in {source} — using scoop')
                btype = "scoop"
            gx = bin_spec.get("units", 1)
            label = bin_spec.get("label") if btype != "open" else None
            hint = str(label or btype)
            gx = _autosized(gx, bin_spec, grow_only=True, warnings=warnings, slug_hint=hint)
            spec = ContainerSpec(
                slug="", gx=gx, gy=gy, type=btype,
                ramp_angle=defaults["rampAngle"], scoop_radius=defaults["scoopRadius"],
                bin=dict(bin_spec), sources=[source], warnings=warnings,
            )
            spec.slug = f"{slugify(spec.label or btype)}-{gx}x{gy}"
            specs.append(spec)
    return specs


def _entry_size(entry: dict) -> tuple[int, int] | None:
    """Explicit size from a manifest entry: `size: 2x1`, `size: [2, 1]`,
    or `units`/`depth` keys. None means auto-size."""
    if "size" in entry:
        s = entry["size"]
        if isinstance(s, str):
            gx, gy = (int(v) for v in s.lower().split("x"))
        else:
            gx, gy = int(s[0]), int(s[1])
        return gx, gy
    if "units" in entry or "depth" in entry:
        return int(entry.get("units", 1)), int(entry.get("depth", 1))
    return None


def containers_from_manifest(manifest: dict) -> list[ContainerSpec]:
    defaults = {**BIN_DEFAULTS, **manifest.get("defaults", {})}
    source = manifest["name"]
    specs: list[ContainerSpec] = []
    for entry in manifest.get("containers", []):
        if isinstance(entry, str):
            entry = {"label": entry}
        bin_spec = dict(entry)
        btype = bin_spec.get("type", defaults["type"])
        warnings: list[str] = []
        if btype not in KNOWN_TYPES:
            warnings.append(f'unknown container type "{btype}" in {source} — using scoop')
            btype = "scoop"

        # screw checker on by default for screw labels (M3x8, M5, ...);
        # set `test: false` to opt out, or an explicit spec/head to tune it
        label = bin_spec.get("label")
        if ("test" not in bin_spec and btype != "open" and label
                and _SCREW_LABEL_RE.search(str(label))):
            bin_spec["test"] = True

        explicit = _entry_size(bin_spec)
        if explicit:
            gx, gy = explicit
            length = item_length(bin_spec)
            if length is not None and units_for_length(length) > gx:
                warnings.append(
                    f"{label}: size {gx}x{gy} is too small for a {length:g} mm item "
                    f"({units_for_length(length)} units needed)")
        else:
            gy = 1
            gx = _autosized(1, bin_spec, grow_only=False, warnings=warnings,
                            slug_hint=str(label or btype))

        spec = ContainerSpec(
            slug="", gx=gx, gy=gy, type=btype,
            ramp_angle=defaults["rampAngle"], scoop_radius=defaults["scoopRadius"],
            bin=bin_spec, height_units=bin_spec.get("heightUnits"),
            sources=[source], warnings=warnings,
        )
        spec.slug = f"{slugify(spec.label or btype)}-{gx}x{gy}"
        specs.append(spec)
    return specs


def build_catalog(paths: list[Path]) -> tuple[list[ContainerSpec], dict]:
    """Load all config files and merge their bins into a deduplicated
    catalog. Returns (catalog, settings) — settings are the non-container
    options collected from manifests (plate, heightUnits, magnets, ...)."""
    by_slug: dict[str, ContainerSpec] = {}
    settings: dict = {}

    def add(spec: ContainerSpec) -> None:
        existing = by_slug.get(spec.slug)
        if existing is None:
            by_slug[spec.slug] = spec
            return
        if spec.sources[0] not in existing.sources:
            existing.sources.append(spec.sources[0])
        if spec.geometry_key() != existing.geometry_key():
            existing.warnings.append(
                f"{spec.slug}: {spec.sources[0]} defines it differently "
                f"than {existing.sources[0]} — using {existing.sources[0]}'s geometry"
            )
        # a shared container should hold the largest kit's quantity
        counts = [s.bin.get("count") for s in (existing, spec)]
        counts = [c for c in counts if c is not None]
        if counts:
            existing.bin["count"] = max(counts)

    overrides: dict = {}
    for path in paths:
        doc = load_source(path)
        if is_manifest(doc):
            # settings use the same names as screw-organiser layouts where
            # an equivalent exists: labels, testHoles, colors, gridfinity
            for key in ("name", "plate", "printer", "heightUnits", "gridfinity",
                        "magnets", "counts", "colors", "labels", "testHoles",
                        "labelStyle", "exclude", "filaments", "checkers"):
                if key in doc and key not in settings:
                    settings[key] = doc[key]
            overrides.update(doc.get("overrides") or {})
            for layout_path in doc.get("layouts", []):
                layout = load_source(doc["_dir"] / layout_path)
                for spec in containers_from_layout(layout):
                    add(spec)
            for spec in containers_from_manifest(doc):
                add(spec)
        else:
            for key in ("labels", "testHoles", "colors"):
                if key in doc and key not in settings:
                    settings[key] = doc[key]
            for spec in containers_from_layout(doc):
                add(spec)

    if overrides:
        specs = list(by_slug.values())
        by_slug.clear()
        for spec in specs:
            _apply_override(spec, overrides)
            add(spec)
    return list(by_slug.values()), settings


def _apply_override(spec: ContainerSpec, overrides: dict) -> None:
    """Apply a manifest override to a spec, matched by label or slug.

    `overrides: { M3x10: 2x2 }` resizes every M3x10 container regardless
    of where it came from; a dict value can also change count, test, head,
    type or heightUnits."""
    key = None
    for k in overrides:
        if k == spec.slug or (spec.label and slugify(str(k)) == slugify(spec.label)):
            key = k
            break
    if key is None:
        return
    ov = overrides[key]
    if not isinstance(ov, dict):
        ov = {"size": ov}
    ov = dict(ov)

    if "size" in ov:
        spec.gx, spec.gy = _entry_size({"size": ov.pop("size")})
        length = item_length(spec.bin)
        if length is not None and units_for_length(length) > spec.gx:
            spec.warnings.append(
                f"{spec.label}: override size {spec.gx}x{spec.gy} is too small for a "
                f"{length:g} mm item ({units_for_length(length)} units needed)")
    if "heightUnits" in ov:
        spec.height_units = ov.pop("heightUnits")
    if "type" in ov:
        spec.type = ov.pop("type")
    spec.bin.update(ov)
    spec.slug = f"{slugify(spec.label or spec.type)}-{spec.gx}x{spec.gy}"


def find_layouts(directory: Path) -> list[Path]:
    """All config files in a directory, skipping the example-* ones."""
    paths = sorted(
        p for p in directory.iterdir()
        if p.suffix in (".yaml", ".yml", ".json") and not p.name.startswith("example-")
    )
    if not paths:
        raise FileNotFoundError(f"no layout files found in {directory}")
    return paths
