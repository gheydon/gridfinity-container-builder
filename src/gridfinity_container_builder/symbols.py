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

import re
from functools import lru_cache
from importlib.resources import files

from build123d import (
    Align,
    BuildSketch,
    Locations,
    Mode,
    Part,
    Plane,
    Pos,
    Rectangle,
    add,
    extrude,
    import_svg,
    mirror,
)

# side-profile screw icons (head on the left, shaft to the right) — these
# get cropped to just the head for the compact head-profile look
_SCREWS = {"cap", "button", "flush", "pan", "grub", "lowhead", "hexhead"}

# symbol name -> bundled SVG file
_FILES = {
    "cap": "TRP_cylinderHeadScrew.svg",
    "cylinder": "TRP_cylinderHeadScrew.svg",
    "button": "TRP_ButtonHead.svg",
    "flush": "TRP_countersunkHead.svg",
    "countersunk": "TRP_countersunkHead.svg",
    "pan": "TRP_PanHead.svg",
    "grub": "TRP_grubscrew.svg",
    "hex": "hex.svg",                       # top-view hex socket (Allen drive)
    "hexhead": "TRP_hexagonHead.svg",       # side-profile hex-head bolt
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
    "bolt": "hexhead", "hexagon": "hexhead", "allen": "hex", "socket_drive": "hex",
    "wshr": "washer",
    "ns": "square_nut", "nn": "nylock",
}

KINDS = tuple(sorted(set(_FILES)))

# a full screw size like M3x8 -> gets the hex-socket drive icon
_SCREW_RE = re.compile(r"\bM\d+(?:\.\d+)?x\d", re.I)


def canonical(name: str) -> str | None:
    n = str(name).strip().lower().replace(" ", "").replace("-", "")
    if n in _FILES:
        return n
    return _ALIASES.get(n)


@lru_cache(maxsize=64)
def _icon_face(key: str, head_only: bool):
    path = files(__package__).joinpath("icons", _FILES[key])
    face = import_svg(str(path))[0]
    # SVG y grows downward; flip so the icon reads upright, then centre
    face = mirror(face, Plane.XZ)
    bb = face.bounding_box()
    face = Pos(-bb.center().X, -bb.center().Y, 0) * face

    if head_only and key in _SCREWS:
        # keep just the head (left of the drawing) — the head is roughly
        # as wide as the icon is tall, plus a short shaft stub
        nh = bb.size.Y
        crop_w = nh * 1.2
        x_left = -bb.size.X / 2
        with BuildSketch() as sk:
            add(face)
            with Locations((x_left + crop_w / 2, 0)):
                Rectangle(crop_w, nh * 1.2, mode=Mode.INTERSECT)
        cb = sk.sketch.bounding_box()
        face = Pos(-cb.center().X, -cb.center().Y, 0) * sk.sketch
        bb = face.bounding_box()

    return face, bb.size.X, bb.size.Y


def build_symbol(kind: str, max_w: float, max_h: float, depth: float,
                 head_only: bool = True) -> Part:
    """Icon extruded 0..depth, scaled to fit within a max_w x max_h box
    (aspect kept), centred on the XY origin. `head_only` crops screws to
    just the head (compact); False keeps the full side profile."""
    key = canonical(kind) or "cap"
    face, nw, nh = _icon_face(key, head_only)
    scale = min(max_w / nw, max_h / nh)
    with BuildSketch() as sk:
        add(face)
    sketch = sk.sketch.scale(scale)
    return extrude(sketch, amount=depth)


def symbol_for(bin_spec: dict, test: dict | None) -> str | None:
    """Auto-pick a top-view drive / hardware icon (like the CNC Kitchen
    symbol set): drive type from the label, hardware (nut/washer/insert)
    from the label, else a socket-head screw gets the hex-socket icon.

    Explicit `symbol:` on the box (handled by the caller) overrides this.
    """
    raw = str(bin_spec.get("label", ""))
    label = raw.lower()
    flat = label.replace(" ", "").replace("-", "")

    # drive types (what you see looking down at the head)
    if "phillips" in label or "pozi" in label or re.search(r"\bph\b", label) or flat.endswith("ph"):
        return "phillips"
    if "torx" in label or re.search(r"\btrx\b", label) or re.search(r"\bt\d", label):
        return "torx"
    if "robertson" in label or "square drive" in label:
        return "robertson"
    if "slot" in label or "slotted" in label:
        return "slot"

    # hardware
    if "insert" in label or "heatset" in label or "heat-set" in label:
        return "insert"
    if "lockwasher" in flat or "lock washer" in label or "spring washer" in label:
        return "lockwasher"
    if "washer" in label or "wshr" in flat:
        return "washer_large" if ("large" in label or flat.endswith("l")) else "washer"
    if "nylock" in flat or "nyloc" in flat or flat.endswith("nn"):
        return "nylock"
    if flat.endswith("ns"):
        return "square_nut"
    if "wingnut" in flat or "wing nut" in label:
        return "wingnut"
    if re.match(r"^m\d+(\.\d+)?n$", flat):        # bare M3n-style nut
        return "nut"

    # a screw with a gauge head -> hex-socket (Allen) drive icon
    if (test and test.get("head")) or _SCREW_RE.search(raw):
        return "hex"
    return None

