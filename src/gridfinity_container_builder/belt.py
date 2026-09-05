"""Belt-coil interior generator: one round pocket for loose coiled belts.

Sized for coiled timing belts (GT2 6 mm by default — what the Prusa MK-series
X/Y axes use). Several belts are coiled and dropped into a single cylindrical
pocket; the pocket fills the interior, its bottom rim is filleted so coils don't
wedge in a sharp corner and lift out cleanly, and two scalloped finger scoops in
the rim let you pinch the coils out. An optional centre hub keeps the coils from
collapsing inward when you want them wound neatly rather than piled loose.

`container.py` owns the shell + exterior post-processing; its belt branch calls
`belt_interior()` → (cavities, labels) and subtracts the cavities. The footprint
comes from `belt_tray_size()` (defaults to 4x4).
"""

from __future__ import annotations

from build123d import Align, Axis, Box, Cylinder, GeomType, Part, Pos, Sphere, fillet

from .interior import GUSSET_SPACING, GUSSET_THICKNESS, extrude_profile_x
from .text import solid_label_sized

GF_WALL = 2.6          # interior wall inset (matches container.GF_WALL)
PITCH = 42.0           # Gridfinity cell pitch (mm)

WALL_GAP = 0.0         # extra inset of the pocket from the interior wall (0 = fill)
BOTTOM_FILLET = 8.0    # rounding radius at the pocket floor
OVERSHOOT = 3.0        # pocket extends this far above the rim (keeps it open)
SCOOP_R = 15.0         # finger-scoop sphere radius
HUB_D = 22.0           # default centre-hub diameter when enabled
LABEL_CAP = 6.0        # top-label cap height (mm)
DEFAULT_LABEL = "GT2 6mm"
# Top label: a thin LEDGE across the FRONT of the pocket (like a Pred label
# shelf) carries a top-facing label — a raised background plate (own colour
# slot) with the text proud on top, the 0.8 plate + 0.2 text stack Pred uses.
# The ledge is only ROOF_T thick and the pocket stays open UNDERNEATH it (not a
# solid plug), carried by the front + side walls. It auto-sizes to the text, so
# multi-line labels (newlines) deepen the ledge.
ROOF_T = 3.0           # ledge thickness (mm); pocket is hollow below it
SHELF_MIN = 13.0       # min ledge depth (mm)
SHELF_MAX = 34.0       # max ledge depth (mm) — keeps a usable pocket behind it
BACKGROUND_THICKNESS = 0.8
LABEL_RAISE = 0.2      # text proud of the plate
LABEL_SINK = 0.1       # text sunk into the plate so the two fuse
PLATE_SINK = 0.6       # plate sunk into the ledge top so it fuses to the body
LABEL_MARGIN = 2.2     # plate border around the text


def belt_tray_size(cfg: dict) -> tuple[int, int]:
    """Grid size (gx, gy). Defaults to 4x4 — a ~150 mm pocket that swallows
    several coiled Prusa belts. An explicit diameter grows the footprint to fit."""
    gx = int(cfg.get("gx", 2))
    gy = int(cfg.get("gy", 2))
    dia = cfg.get("diameter")
    if dia:
        need = int(-(-(float(dia) + 2 * GF_WALL + 0.5) // PITCH))  # ceil
        gx = max(gx, need)
        gy = max(gy, need)
    return max(1, gx), max(1, gy)


def belt_interior(cell: dict, params: dict, total_h: float, width: float,
                  depth: float, cfg: dict) -> tuple[Part, list, Part | None]:
    """Round coil pocket carved into the shell fill.
    Returns (cavities, labels, background-plate)."""
    floor = params["floor"]
    cx, cy = width / 2, depth / 2

    # Pocket radius: fill the interior unless an explicit diameter is asked for.
    r_fill = (min(width, depth) - 2 * GF_WALL) / 2 - WALL_GAP
    r = min(float(cfg["diameter"]) / 2, r_fill) if cfg.get("diameter") else r_fill

    poc_h = total_h - floor + OVERSHOOT
    pocket = Pos(cx, cy, floor) * Cylinder(
        radius=r, height=poc_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Round the bottom rim so coils drop to the centre and scoop out easily.
    fr = min(BOTTOM_FILLET, r - 0.6, (total_h - floor) - 0.6)
    if fr > 0.4:
        bottom_edge = pocket.edges().filter_by(GeomType.CIRCLE).sort_by(Axis.Z)[0]
        pocket = fillet(bottom_edge, radius=fr)

    cav = pocket

    # Optional centre hub: a slim round post (removed from the cavity being cut).
    # It rises to the fill top so it supports whatever sits on the top — a plain
    # box, or the central grid intersection of a "grid on top" baseplate (on an
    # even grid the hub lands under an intersection; on an odd grid, mid-cell).
    if cfg.get("hub"):
        hub_d = float(cfg.get("hubDiameter", HUB_D))
        hub = Pos(cx, cy, floor - 0.1) * Cylinder(
            radius=hub_d / 2, height=poc_h + 0.2,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        cav = cav - hub

    # Finger scoops (optional): scalloped dips in the rim on the left & right
    # sides (front and back stay clear for the label), so you can pinch and lift
    # the coils. A sphere at the rim carves a clean downward-facing scallop (no
    # overhang). `scoops` may be a bool (on/off, default on) or a count.
    want = cfg.get("scoops", True)
    n_scoops = (2 if want else 0) if isinstance(want, bool) else int(want)
    if n_scoops >= 1:
        cav = cav + Pos(cx - r, cy, total_h) * Sphere(SCOOP_R)
    if n_scoops >= 2:
        cav = cav + Pos(cx + r, cy, total_h) * Sphere(SCOOP_R)

    # TOP label: a thin LEDGE across the front top of the pocket carries a
    # top-facing label (background plate in its own colour slot + proud text),
    # so it reads when the bin sits on a shelf. The pocket stays open UNDERNEATH
    # the ledge (hollow, Pred-style — not a solid plug). Multi-line labels
    # (newlines) auto-deepen the ledge. "" suppresses both. Returns (cav, labels, plate).
    labels: list[Part] = []
    background = None
    text = cfg.get("label", DEFAULT_LABEL)
    if text:
        cap = float(cfg.get("labelSize", LABEL_CAP))
        sub = float(cfg.get("subScale", 0.65))
        lines = str(text).split("\n")
        caps = [(ln, cap if i == 0 else cap * sub) for i, ln in enumerate(lines)]
        depth = LABEL_RAISE + LABEL_SINK
        max_h = SHELF_MAX - 2 * LABEL_MARGIN

        # optional icon on the LEFT of the text (same colour slot as the text)
        icon = None
        icon_w = 0.0
        icon_gap = 0.0
        kind = cfg.get("icon")
        if kind:
            from .symbols import build_symbol, canonical
            k = canonical(kind)
            if k:
                icon = build_symbol(k, 10.0, min(cap * len(lines) + 3, max_h), depth)
                ib = icon.bounding_box()
                icon = Pos(-ib.center().X, -ib.center().Y, 0) * icon
                icon_w = ib.size.X
                icon_gap = 2.0

        lbl = solid_label_sized(caps, depth=depth, max_height=max_h,
                                max_width=width - 4 * GF_WALL - icon_w - icon_gap)
        tb = lbl.bounding_box()
        block_w = icon_w + icon_gap + tb.size.X
        block_h = max(tb.size.Y, icon.bounding_box().size.Y if icon else 0.0)
        pw = block_w + 2 * LABEL_MARGIN
        ph = block_h + 2 * LABEL_MARGIN
        shelf = max(SHELF_MIN, min(ph + 1.0, SHELF_MAX))
        # restore a thin solid ledge in the top ROOF_T of the front strip — the
        # pocket (already carved) stays open below it, so it's hollow underneath.
        cav = cav - (Pos(0, 0, total_h - ROOF_T) * Box(
            width, shelf, ROOF_T + OVERSHOOT, align=(Align.MIN, Align.MIN, Align.MIN)))
        # 45-degree support fins under the ledge (Pred-style gussets) so its
        # underside prints self-supported instead of bridging the pocket. Each fin
        # is a right triangle: vertical edge on the front wall, flat top under the
        # ledge, 45-degree hypotenuse underneath (each layer sits on the one below).
        z_led = total_h - ROOF_T
        run = shelf - GF_WALL
        if run > 1.0:
            pts = [(GF_WALL, z_led), (shelf, z_led), (GF_WALL, z_led - run)]
            n = max(1, round(width / GUSSET_SPACING) - 1)
            for i in range(n):
                fx = (i + 1) * width / (n + 1)
                cav = cav - (Pos(fx - GUSSET_THICKNESS / 2, 0, 0)
                             * extrude_profile_x(pts, GUSSET_THICKNESS))
        cyl = shelf / 2                             # label centred on the ledge
        z0 = total_h - PLATE_SINK                   # plate base (sunk into the ledge top)
        z_face = z0 + BACKGROUND_THICKNESS - LABEL_SINK
        # plate lies flat; icon (left) + text (right) sit proud on it and read
        # from above (no rotation). The block is centred on the ledge.
        left = cx - block_w / 2
        if icon is not None:
            labels.append(Pos(left + icon_w / 2, cyl, z_face) * icon)
        text_cx = left + icon_w + icon_gap + tb.size.X / 2
        labels.append(Pos(text_cx, cyl, z_face) * lbl)
        background = Pos(cx, cyl, z0 + BACKGROUND_THICKNESS / 2) * Box(pw, ph, BACKGROUND_THICKNESS)

    return cav, labels, background
