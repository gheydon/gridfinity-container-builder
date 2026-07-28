"""Screw / hardware icon silhouettes for labels.

Uses the SVG icon set from CNC Kitchen's Gridfinity Label Generator
(https://github.com/CNCKitchen/gridfinityLabelGenerator, MIT licence,
bundled under icons/). Each icon is imported as a face, normalised and
extruded like the label text so it prints in the label colour.

Enabled with `--symbols` (or `symbols: true`); the icon is auto-picked
from the container's head type / label, or set per box with
`symbol: <name>`.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

from build123d import BuildSketch, Mode, Part, Plane, Pos, add, extrude, import_svg, mirror

# symbol name -> bundled SVG file
_FILES = {
    "cap": "TRP_cylinderHeadScrew.svg",
    "cylinder": "TRP_cylinderHeadScrew.svg",
    "button": "TRP_ButtonHead.svg",
    "flush": "TRP_countersunkHead.svg",
    "countersunk": "TRP_countersunkHead.svg",
    "pan": "TRP_PanHead.svg",
    "grub": "TRP_grubscrew.svg",
    "hex": "TRP_hexagonHead.svg",
    "hexhead": "TRP_hexagonHead.svg",
    "lowhead": "TRP_lowHeadScrew.svg",
    "nut": "nut.svg",
    "nylock": "nylock.svg",
    "nyloc": "nylock.svg",
    "square_nut": "square_nut.svg",
    "squarenut": "square_nut.svg",
    "washer": "washer.svg",
    "washer_large": "washer_large.svg",
    "lockwasher": "lockwasher.svg",
    "insert": "insert.svg",
    "phillips": "phillips.svg",
    "torx": "torx.svg",
    "slot": "slot.svg",
    "robertson": "robertson.svg",
    "wingnut": "wingnut.svg",
}

# head-type / abbreviation aliases -> a key in _FILES
_ALIASES = {
    "socket": "cap", "shcs": "cap", "cylinder": "cap",
    "bhcs": "button", "dome": "button",
    "csk": "flush", "fhcs": "flush",
    "set": "grub", "none": "grub", "headless": "grub",
    "bolt": "hex", "hexagon": "hex",
    "wshr": "washer",
    "ns": "square_nut", "nn": "nylock",
}

KINDS = tuple(sorted(set(_FILES)))


def canonical(name: str) -> str | None:
    n = str(name).strip().lower().replace(" ", "").replace("-", "")
    if n in _FILES:
        return n
    return _ALIASES.get(n)


@lru_cache(maxsize=32)
def _icon_face(key: str):
    path = files(__package__).joinpath("icons", _FILES[key])
    face = import_svg(str(path))[0]
    # SVG y grows downward; flip so the icon reads upright, then centre
    face = mirror(face, Plane.XZ)
    bb = face.bounding_box()
    face = Pos(-bb.center().X, -bb.center().Y, 0) * face
    return face, bb.size.X, bb.size.Y


def build_symbol(kind: str, max_w: float, max_h: float, depth: float) -> Part:
    """Icon extruded 0..depth, scaled to fit within a max_w x max_h box
    (aspect kept), centred on the XY origin."""
    key = canonical(kind) or "cap"
    face, nw, nh = _icon_face(key)
    scale = min(max_w / nw, max_h / nh)
    with BuildSketch() as sk:
        add(face)
    sketch = sk.sketch.scale(scale)
    return extrude(sketch, amount=depth)


def symbol_for(bin_spec: dict, test: dict | None) -> str | None:
    """Auto-pick an icon: explicit head/type first, then the gauge head,
    then nut/washer keywords in the label."""
    if bin_spec.get("head"):
        c = canonical(bin_spec["head"])
        if c:
            return c
    label = str(bin_spec.get("label", "")).lower().replace(" ", "")
    if "wshr" in label or "washer" in label:
        return "washer"
    if "nylock" in label or "nyloc" in label or label.endswith("nn"):
        return "nylock"
    if label.endswith("ns"):
        return "square_nut"
    if test and test.get("head"):
        return canonical(test["head"])
    # bare "M3n"-style nut labels
    import re

    if re.match(r"^m\d+(\.\d+)?n$", label):
        return "nut"
    return None
