"""Tool-cradle interior generator: parallel lanes that cradle the pieces of a
tool kit — round bits in troughs (optionally with a wider collar pocket), and
tapered blocks in shaped pockets — plus a raised label on the free top ledge.

Config (`bin["toolcradle"]`):
    {"label": "Pocket Hole Jig",
     "items": [
        {"kind": "rod",   "d": 8, "length": 158},
        {"kind": "rod",   "d": 8, "length": 160,
         "collar": {"d": 17, "fromEnd": 10, "len": 75}},
        {"kind": "block", "length": 105, "headW": 25, "tailW": 20,
         "headLen": 63, "depth": 30},
     ]}

`container.py` owns the shell + exterior; its toolcradle branch calls
`tool_cradle_interior()` -> (cavities, labels, background=None) and subtracts the
cavities. The footprint comes from `tool_cradle_size()`.
"""

from __future__ import annotations

import math

from build123d import (Align, Box, BuildLine, BuildSketch, Cylinder, Part, Polyline,
                       Pos, Rot, Sphere, extrude, make_face)

from .text import solid_label

GF_WALL = 2.6          # interior wall inset (matches container.GF_WALL)
PITCH = 42.0           # Gridfinity cell pitch (mm)
END_CLEAR = 2.0        # channel length past each item end
LANE_GAP = 4.0         # wall between lanes
EDGE_MARGIN = 3.0      # gap from the interior wall to the first/last lane
ROD_CLEAR = 0.8        # radial clearance for a rod trough
COLLAR_CLEAR = 1.0     # radial clearance for a collar pocket
BLOCK_CLEAR = 1.0      # per-side clearance for a block pocket
LABEL_CAP = 5.0        # top-ledge label cap height (mm)
LABEL_DEPTH = 0.6      # raised label height (mm)
SCOOP_R = 11.0         # finger-scoop radius at a block's tail end


def _pocket_hole_jig_items() -> list[dict]:
    return [
        {"kind": "rod", "d": 8.0, "length": 158.0},
        {"kind": "rod", "d": 8.0, "length": 160.0,
         "collar": {"d": 17.0, "fromEnd": 10.0, "len": 75.0}},
        {"kind": "block", "length": 105.0, "headW": 25.0, "tailW": 20.0,
         "headLen": 63.0, "depth": 30.0},
    ]


def _items(cfg: dict) -> list[dict]:
    its = cfg.get("items")
    return its if its else _pocket_hole_jig_items()


def _lane_width(it: dict) -> float:
    if it.get("kind") == "block":
        return max(float(it["headW"]), float(it["tailW"])) + 2 * BLOCK_CLEAR
    w = float(it["d"]) + 2 * ROD_CLEAR
    if it.get("collar"):
        w = max(w, float(it["collar"]["d"]) + 2 * COLLAR_CLEAR)
    return w


def tool_cradle_size(cfg: dict) -> tuple[int, int]:
    """Grid size (gx, gy) to fit the lanes (length) and their widths (depth)."""
    items = _items(cfg)
    if not items:
        return 2, 2
    max_len = max(float(it["length"]) for it in items)
    total_w = (sum(_lane_width(it) for it in items) + LANE_GAP * (len(items) - 1)
               + 2 * (GF_WALL + EDGE_MARGIN))
    g_len = max(1, math.ceil((max_len + 2 * GF_WALL + END_CLEAR) / PITCH))
    g_cross = max(1, math.ceil(total_w / PITCH))
    # orient "y" (portrait) runs the items along the depth, so the units swap
    if cfg.get("orient") == "y":
        return g_cross, g_len
    return g_len, g_cross


def _trough(xc: float, yc: float, r: float, length: float, total_h: float) -> Part:
    """Rounded (half-cylinder) channel along X, open at the rim, with flat ends."""
    return Pos(xc, yc, total_h) * Rot(0, 90, 0) * Cylinder(
        radius=r, height=length, align=(Align.CENTER, Align.CENTER, Align.CENTER))


def _block_pocket(xc: float, yc: float, it: dict, total_h: float) -> Part:
    """Tapered block pocket (wide head -> narrow tail), square corners, open top."""
    hw = float(it["headW"]) + 2 * BLOCK_CLEAR
    tw = float(it["tailW"]) + 2 * BLOCK_CLEAR
    pd = float(it["length"]) + 2 * BLOCK_CLEAR
    hl = float(it["headLen"])
    depth = float(it["depth"])
    pts = [(-pd / 2, hw / 2), (-pd / 2 + hl, hw / 2), (pd / 2, tw / 2),
           (pd / 2, -tw / 2), (-pd / 2 + hl, -hw / 2), (-pd / 2, -hw / 2)]
    with BuildSketch() as sk:
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
    return Pos(xc, yc, total_h - depth) * extrude(sk.sketch, amount=depth + 4)


def tool_cradle_interior(cell: dict, params: dict, total_h: float, width: float,
                         depth: float, cfg: dict) -> tuple[Part, list, None]:
    """Lay the item lanes across the depth (front -> back). Returns
    (cavities, labels, background). Rods run centred along the length; blocks are
    shifted to the LEFT wall so their freed top ledge can carry the label."""
    items = _items(cfg)
    # orient "x" (default): items run along the width (left-right). orient "y"
    # (portrait): items run along the depth — we build in a local length×cross
    # frame (Lx = length axis, Ly = cross axis) and rotate it onto the bin at the end.
    orient = cfg.get("orient", "x")
    Lx = depth if orient == "y" else width      # length-axis extent (local x)
    Ly = width if orient == "y" else depth       # cross-axis extent (local y)
    cx = Lx / 2
    cav: Part | None = None

    def cut(p: Part) -> None:
        nonlocal cav
        cav = p if cav is None else cav + p

    y = GF_WALL + EDGE_MARGIN
    lanes = []                                  # (item, y_centre, free_ledge_x0 or None)
    for it in items:
        w = _lane_width(it)
        yc = y + w / 2
        ledge_x0 = None
        if it.get("kind") == "block":
            pd = float(it["length"]) + 2 * BLOCK_CLEAR
            xc = GF_WALL + EDGE_MARGIN + pd / 2      # align to the left wall
            cut(_block_pocket(xc, yc, it, total_h))
            if it.get("scoop", True):                # finger scoop at the narrow tail end
                cut(Pos(xc + pd / 2 - 3, yc, total_h) * Sphere(SCOOP_R))
            ledge_x0 = xc + pd / 2
        else:
            L = float(it["length"])
            cut(_trough(cx, yc, float(it["d"]) / 2 + ROD_CLEAR, L + END_CLEAR, total_h))
            col = it.get("collar")
            if col:
                tip_x = cx - L / 2                    # collar-pocket ("from") end
                cxc = tip_x + float(col["fromEnd"]) + float(col["len"]) / 2
                cut(_trough(cxc, yc, float(col["d"]) / 2 + COLLAR_CLEAR,
                            float(col["len"]), total_h))
        lanes.append((it, yc, ledge_x0))
        y += w + LANE_GAP

    # LIGHTEN: sealed voids under each lane (below the pocket/trough floor) so the
    # bin isn't a near-solid block. Kept narrow per lane so the floor above bridges
    # cleanly, and started above the gridfinity base so the feet stay intact.
    if cfg.get("lighten", True):
        base_top = params["floor"] - 2.0            # params["floor"] = base_h + FLOOR(2)
        z0 = base_top + 0.6
        VW = 1.6                                    # void inset from the lane walls
        for it, yc, ledge_x0 in lanes:
            w = _lane_width(it)
            if it.get("kind") == "block":
                pd = float(it["length"]) + 2 * BLOCK_CLEAR
                bx = GF_WALL + EDGE_MARGIN + pd / 2
                ceil = (total_h - float(it["depth"])) - 1.5      # under the block pocket
                if ceil - z0 > 3:
                    cut(Pos(bx, yc, z0) * Box(pd - 2 * VW, w - 2 * VW, ceil - z0,
                                              align=(Align.CENTER, Align.CENTER, Align.MIN)))
                if ledge_x0 is not None:                          # under the label ledge
                    ir = Lx - GF_WALL
                    lw = ir - ledge_x0
                    if lw > 6:
                        cut(Pos((ledge_x0 + ir) / 2, yc, z0) * Box(
                            lw - 2 * VW, w - 2 * VW, (total_h - 4) - z0,
                            align=(Align.CENTER, Align.CENTER, Align.MIN)))
            else:
                L = float(it["length"])
                rr = float(it["d"]) / 2 + ROD_CLEAR
                if it.get("collar"):
                    rr = max(rr, float(it["collar"]["d"]) / 2 + COLLAR_CLEAR)
                ceil = (total_h - rr) - 1.5
                if ceil - z0 > 3:
                    cut(Pos(cx, yc, z0) * Box(L - 2 * VW, w - 2 * VW, ceil - z0,
                                              align=(Align.CENTER, Align.CENTER, Align.MIN)))

    # label on the top ledge — the free flat top at the right of a block lane
    # orient "y": rotate the whole (local length×cross) assembly +90° about Z so the
    # length axis lands along the bin depth, then shift back into the [0,width]×[0,depth] box.
    if orient == "y" and cav is not None:
        cav = Pos(Ly, 0, 0) * Rot(0, 0, 90) * cav

    # Label: always read HORIZONTALLY on the finished bin (never rotated with the
    # assembly). Placed on the free ledge; T maps the local ledge centre to global.
    labels: list[Part] = []
    text = cfg.get("label", "")
    if text:
        interior_right = Lx - GF_WALL
        spot = next(((x0, yc, _lane_width(it)) for (it, yc, x0) in lanes
                     if x0 is not None and interior_right - x0 > 20), None)
        if spot is None:                             # fallback: back lane, right end
            spot = (cx + 20, lanes[-1][1], _lane_width(lanes[-1][0]))
        x0, yc, lane_w = spot
        xl = (x0 + interior_right) / 2
        if orient == "y":
            # ledge is now narrow in global X (= lane width) and deep in global Y;
            # keep the text upright, fit to the lane width.
            gx, gy = Ly - yc, xl
            lbl = solid_label(str(text), cap_height=LABEL_CAP, depth=LABEL_DEPTH,
                              max_width=lane_w - 4)
        else:
            gx, gy = xl, yc
            lbl = solid_label(str(text), cap_height=LABEL_CAP, depth=LABEL_DEPTH,
                              max_width=interior_right - x0 - 5)
        labels.append(Pos(gx, gy, total_h) * lbl)

    return cav, labels, None
