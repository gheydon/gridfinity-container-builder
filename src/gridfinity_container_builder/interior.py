"""Container interior geometry: scoop cavity, labelled ramp, test gauges.

Ported from screw-organiser's bins/common.py — the same cavity profile is
carved into a Gridfinity bin shell instead of a tray cell, so containers
look and behave exactly like the organiser bins they replace.
"""

from __future__ import annotations

import math
import re
from typing import Any

from build123d import (
    BuildLine,
    BuildPart,
    BuildSketch,
    Cone,
    Cylinder,
    Part,
    Plane,
    Polyline,
    Pos,
    Rot,
    extrude,
    make_face,
)

from .text import solid_label


def arc_points(cx: float, cy: float, r: float, a0: float, a1: float, segments: int = 24):
    return [
        (cx + r * math.cos(a0 + (a1 - a0) * i / segments),
         cy + r * math.sin(a0 + (a1 - a0) * i / segments))
        for i in range(segments + 1)
    ]


def _clean(points):
    out: list[tuple[float, float]] = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    return out


def extrude_profile_x(points, width: float) -> Part:
    """Extrude a (y, z) profile polygon across `width` along world X."""
    with BuildPart() as bp:
        with BuildSketch(Plane.YZ):
            with BuildLine():
                Polyline(*_clean(points), close=True)
            make_face()
        extrude(amount=width)
    return bp.part


def test_spec(bin_spec: dict, params: dict) -> dict | None:
    """Resolve a bin's "test" option to a gauge spec (same rules as the JS)."""
    t = bin_spec.get("test")
    if t in (None, False):
        return None

    clearance = params["test"]["clearance"]
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        spec: dict[str, Any] = {"dia": float(t), "length": None}
    elif isinstance(t, dict):
        spec = {**t, "length": t.get("length")}
    else:
        src = t if isinstance(t, str) else str(bin_spec.get("label", ""))
        m = re.search(r"M?(\d+(?:\.\d+)?)(?:x(\d+(?:\.\d+)?))?", src, re.I)
        if not m:
            return None
        spec = {
            "dia": float(m.group(1)) + clearance,
            "length": float(m.group(2)) if m.group(2) else None,
        }

    # allow "head" as a sibling of "test" (for string/number test specs)
    if "head" not in spec and "head" in bin_spec:
        spec["head"] = bin_spec["head"]
    _resolve_head(spec, clearance)
    return spec


# Head geometry per type, ISO-derived. Diameter across flats/round =
# dia_m * nominal + dia_b (+ clearance); axial length = len_m * nominal.
#   cap    ISO 4762 socket head cap screw (SHCS): M3 5.5, M5 8.5, M8 13
#   button ISO 7380 button head          (BHCS): M3 5.7, M5 9.5, M8 14
#   flush  ISO 10642 countersunk 90deg    (FHCS): M3 6.0, M5 10, M8 16 (cone)
HEAD_TYPES = {
    "cap":    {"dia_m": 1.5,  "dia_b": 1.0, "len_m": 1.0,  "cone": False},
    "button": {"dia_m": 1.75, "dia_b": 0.4, "len_m": 0.55, "cone": False},
    "flush":  {"dia_m": 2.0,  "dia_b": 0.0, "len_m": None, "cone": True},
}
# accepted aliases for the "head" parameter, incl. the ISO abbreviations
_HEAD_ALIASES = {
    "cap": "cap", "shcs": "cap", "socket": "cap", "true": "cap",
    "button": "button", "bhcs": "button", "dome": "button", "round": "button", "pan": "button",
    "flush": "flush", "fhcs": "flush", "csk": "flush", "countersunk": "flush",
    "flat": "flush",
}


def _resolve_head(spec: dict, clearance: float) -> None:
    """Fill in the head pocket (type + dims) on a gauge spec.

    The "head" parameter is explicit: defaults to a socket cap ("cap"), with
    "button" and "flush" for other heads and "none" (or false) for headless
    screws like grub/set screws.
    """
    h = spec.get("head", "cap")
    if h is False or (isinstance(h, str) and h.lower() == "none"):
        spec["head"] = None
        spec["headCone"] = False
        return
    if h is True:
        h = "cap"

    key = _HEAD_ALIASES.get(str(h).lower())
    if key is None:
        raise ValueError(f"unknown head type {h!r} (cap, button, flush, none)")

    nominal = spec["dia"] - clearance
    ht = HEAD_TYPES[key]
    spec["head"] = key
    spec.setdefault("headDia", ht["dia_m"] * nominal + ht["dia_b"] + clearance)
    if ht["cone"]:
        # 90deg countersink: cone from thread radius up to head radius
        spec.setdefault("headLength", (spec["headDia"] - spec["dia"]) / 2)
    else:
        spec.setdefault("headLength", ht["len_m"] * nominal + 0.4)
    spec["headCone"] = ht["cone"]


def shelf_for(test: dict, params: dict) -> float:
    """Shelf depth needed behind the ramp crest for a gauge spec."""
    widest = max(test["dia"], test["headDia"] if test["head"] else 0.0)
    return widest / 2 + params["test"]["rim"]


def scoop_cavity(cell: dict, params: dict, scoop_radius: float, with_ramp: bool,
                 test: dict | None = None) -> tuple[Part, dict | None]:
    """Front scoop fillet, flat floor, optional labelled ramp + crest gauge.

    With `test` set, the ramp shifts forward to leave a flat shelf and the
    gauge channels run along the crest so the screw is cradled ~120 degrees
    and rolls out over the incline.
    """
    H = params["height"]
    F = params["floor"]
    Hc = H + 1

    angle = math.radians(params["rampAngle"])
    run = (H - F) / math.tan(angle) if with_ramp else 0.0

    shelf = 0.0
    if with_ramp and test:
        shelf = shelf_for(test, params)
    if with_ramp and cell.get("shelf"):
        shelf = max(shelf, cell["shelf"])
    back = cell["depth"] - shelf

    back_r = 0.0 if with_ramp else min(3.0, H - F)
    max_r = back - run - back_r - 1
    R = max(0.5, min(scoop_radius, H - F, max_r))

    pts = [
        (0, Hc),
        (0, F + R),
        *arc_points(R, F + R, R, math.pi, 1.5 * math.pi),
        (back - run - back_r, F),
    ]
    if with_ramp:
        pts.append((back, H))
    else:
        pts.extend(arc_points(back - back_r, F + back_r, back_r, 1.5 * math.pi, 2 * math.pi))
    pts.append((back, Hc))

    cavity = Pos(cell["x"], cell["y"], 0) * extrude_profile_x(pts, cell["width"])

    if shelf and test:
        head_len = test["headLength"] if test["head"] else 0.0
        thread_len = min(
            (test["length"] or params["test"]["gaugeLength"]) + 0.4,
            cell["width"] - 2 * params["test"]["rim"] - head_len,
        )
        total = head_len + thread_len
        x0 = cell["x"] + cell["width"] / 2 - total / 2
        my = cell["y"] + back  # channel axis on the crest

        def channel(radius: float, length: float, x_center: float) -> Part:
            return Pos(x_center, my, H) * Rot(0, 90, 0) * Cylinder(radius=radius, height=length)

        cavity += channel(test["dia"] / 2, thread_len, x0 + head_len + thread_len / 2)
        if test["head"]:
            xc = x0 + head_len / 2
            if test.get("headCone"):
                # countersunk seat: thread radius toward the groove (right),
                # head radius at the outer end (left)
                cone = Cone(
                    bottom_radius=test["headDia"] / 2,
                    top_radius=test["dia"] / 2,
                    height=head_len,
                )
                cavity += Pos(xc, my, H) * Rot(0, -90, 0) * cone
            else:
                cavity += channel(test["headDia"] / 2, head_len, xc)

    ramp = {"run": run, "angle": angle, "backOffset": shelf} if with_ramp else None
    return cavity, ramp


# Pred's printable-label holder, dimensions measured from his actual bin
# (GridfinityBin_1x1x6_D1_L12_S10, printables.com/model/592545): a flat
# shelf at the top back whose pocket floor sits 1.0 below the wall top,
# 12.0 deep, reaching 1.6 from the bin's outer faces at the sides (1.0
# into the walls); two 1.0 mm tabs over the pocket sides (6.7 long,
# centred) retain the label; 0.8 mm gussets at 45 deg support the shelf.
PLATE_DEPTH = 11.5     # the label plate itself (fits the 12.0 pocket)
PLATE_THICKNESS = 0.8
POCKET_DEPTH_Y = 12.0
POCKET_RECESS = 1.0
POCKET_SIDE_MARGIN = 1.6  # pocket edge to bin outer face at the sides
SHELF_PLATE = 2.0      # shelf slab thickness below the wall top
TAB_OVERHANG = 1.0
TAB_LENGTH = 6.7
TAB_THICKNESS = 0.6
GUSSET_THICKNESS = 0.8
GUSSET_SPACING = 10.5
SHELF_FRONT_RIM = 0.8  # flat strip in front of the pocket (no gauge)


def shelf_cavity(cell: dict, params: dict, scoop_radius: float,
                 test: dict | None = None,
                 support: str = "gussets") -> tuple[Part, dict]:
    """Front scoop + flat floor + Pred label shelf at the top back.

    The cavity keeps the space under the shelf open (bounded by the shelf
    underside at H - SHELF_PLATE); the shelf slab left behind carries the
    label pocket. With `test`, the gauge channels run along the shelf's
    front edge — the leading edge of the label — with the front side open
    over the cavity so the screw rolls out, exactly like the organiser's
    crest gauge.
    """
    H = params["height"]
    F = params["floor"]
    Hc = H + 1

    rim = shelf_for(test, params) if test else SHELF_FRONT_RIM
    if cell.get("shelf"):
        rim = max(rim, cell["shelf"])
    shelf_front = cell["depth"] - POCKET_DEPTH_Y - rim

    # a gauge channel must not punch through the shelf underside
    plate = SHELF_PLATE
    if test:
        widest = max(test["dia"], test["headDia"] if test["head"] else 0.0)
        plate = max(plate, widest / 2 + 1.2)

    back_r = min(3.0, H - F)
    max_r = shelf_front - back_r - 1
    R = max(0.5, min(scoop_radius, H - F, max_r))

    reach = 0.0
    if test:
        reach = max(test["dia"], test["headDia"] if test["head"] else 0.0) / 2
    kink1 = shelf_front + reach
    kink2 = kink1 + max(0.0, plate - SHELF_PLATE)

    if support == "solid":
        # solid 45-degree wedge under the shelf: every layer sits on the
        # one below, so nothing bridges and slicers stay quiet (the
        # gusset variant trips PrusaSlicer's "long bridging" alert, as
        # does Pred's own bin)
        wedge_z = max(F + back_r, H - plate - (cell["depth"] - shelf_front))
        pts = [
            (0, Hc),
            (0, F + R),
            *arc_points(R, F + R, R, math.pi, 1.5 * math.pi),
            (cell["depth"] - back_r, F),
            *arc_points(cell["depth"] - back_r, F + back_r, back_r,
                        1.5 * math.pi, 2 * math.pi),
            (cell["depth"], wedge_z),
            (shelf_front, H - plate),
            (shelf_front, Hc),
        ]
    else:
        # gusset-supported plate: a gauge thickens the slab at the front;
        # keep that thickness under the trough's full reach, then taper
        # back to the standard plate at 45 degrees
        pts = [
            (0, Hc),
            (0, F + R),
            *arc_points(R, F + R, R, math.pi, 1.5 * math.pi),
            (cell["depth"] - back_r, F),
            *arc_points(cell["depth"] - back_r, F + back_r, back_r,
                        1.5 * math.pi, 2 * math.pi),
            (cell["depth"], H - SHELF_PLATE),
            (kink2, H - SHELF_PLATE),
            (kink1, H - plate),
            (shelf_front, H - plate),
            (shelf_front, Hc),
        ]
    cavity = Pos(cell["x"], cell["y"], 0) * extrude_profile_x(pts, cell["width"])

    if test:
        head_len = test["headLength"] if test["head"] else 0.0
        thread_len = min(
            (test["length"] or params["test"]["gaugeLength"]) + 0.4,
            cell["width"] - 2 * params["test"]["rim"] - head_len,
        )
        total = head_len + thread_len
        x0 = cell["x"] + cell["width"] / 2 - total / 2
        my = cell["y"] + shelf_front  # channel axis on the shelf's front edge

        def channel(radius: float, length: float, x_center: float) -> Part:
            return Pos(x_center, my, H) * Rot(0, 90, 0) * Cylinder(radius=radius, height=length)

        cavity += channel(test["dia"] / 2, thread_len, x0 + head_len + thread_len / 2)
        if test["head"]:
            xc = x0 + head_len / 2
            if test.get("headCone"):
                cone = Cone(
                    bottom_radius=test["headDia"] / 2,
                    top_radius=test["dia"] / 2,
                    height=head_len,
                )
                cavity += Pos(xc, my, H) * Rot(0, -90, 0) * cone
            else:
                cavity += channel(test["headDia"] / 2, head_len, xc)

    return cavity, {"shelfFront": shelf_front, "rim": rim, "plate": plate,
                    "kink1": kink1, "kink2": kink2, "support": support}


def shelf_gussets(cell: dict, params: dict, info: dict,
                  spacing: float = GUSSET_SPACING) -> Part:
    """45-degree support gussets under the shelf, Pred-style: 0.8 mm thick
    fins from the shelf's front edge down to the back wall, spaced evenly
    about every `spacing` mm across the bin width."""
    H = params["height"]
    shelf_front = info["shelfFront"]
    plate = info["plate"]
    top_front = H - plate
    top_back = H - SHELF_PLATE
    run = cell["depth"] - shelf_front
    bottom = max(params["floor"], top_front - run)

    pts = [
        (shelf_front, top_front),
        (info["kink1"], top_front),
        (info["kink2"], top_back),
        (cell["depth"], top_back),
        (cell["depth"], bottom),
    ]
    n = max(1, round((cell["width"] + 2 * TAB_OVERHANG) / spacing) - 1)
    gusset = None
    for i in range(n):
        cx = cell["x"] + (i + 1) * cell["width"] / (n + 1)
        fin = Pos(cx - GUSSET_THICKNESS / 2, cell["y"], 0) * extrude_profile_x(
            pts, GUSSET_THICKNESS)
        gusset = fin if gusset is None else gusset + fin
    return gusset


def ramp_label(cell: dict, bin_spec: dict, params: dict, ramp: dict | None) -> Part | None:
    """Raised label on the bin's back ramp face, sunk `overlap` into it.

    A bin without a "label" key defaults to "Misc"; an explicitly empty
    label (null or "") leaves the ramp blank.
    """
    label = bin_spec["label"] if "label" in bin_spec else "Misc"
    if not label or not ramp:
        return None
    cfg = {**params["labels"], **bin_spec.get("labels", {})}

    text = str(label)
    if cfg["showCounts"] and bin_spec.get("count") is not None:
        text += f" ({bin_spec['count']})"

    solid = solid_label(
        text,
        cap_height=cfg["capHeight"],
        depth=cfg["depth"] + cfg["overlap"],
        line_spacing=cfg["lineSpacing"],
        max_width=cell["width"] - 3,
        font=cfg["font"],
        bold=cfg["bold"],
    )

    run, angle, back_off = ramp["run"], ramp["angle"], ramp["backOffset"]
    sin, cos = math.sin(angle), math.cos(angle)
    mx = cell["x"] + cell["width"] / 2
    my = cell["y"] + cell["depth"] - back_off - run / 2
    mz = (params["floor"] + params["height"]) / 2
    return (
        Pos(mx, my + sin * cfg["overlap"], mz - cos * cfg["overlap"])
        * Rot(math.degrees(angle), 0, 0)
        * solid
    )
