"""Native FreeCAD geometry for Gridfinity container shells.

Pure ``Part``/``math`` — no build123d, no external deps — so it runs inside
FreeCAD's own Python. The profiles reproduce the shells our build123d
generator makes (gridfinity-container-builder): the standard gridfinity foot
(0.8 / 1.8 / 2.15 mm chamfers, 42 mm pitch, 41.5 mm bin, 3.75 mm top corner),
a 2.8 mm platform, walls to ``units x 7 mm``, and the stacking lip formed as
the flared top of the interior cavity.

Everything is built from ruled lofts of rounded rectangles (straight 45-degree
chamfers and vertical faces), which is both exact for this geometry and fast.
"""

from __future__ import annotations

import math

import Part
from FreeCAD import Vector

# --- Gridfinity standard constants (mm) -------------------------------------
PITCH = 42.0        # grid pitch
TOL = 0.5           # bin is PITCH*n - TOL (0.25 clearance per side)
RAD = 3.75          # bin top outer corner radius (grid radius 4 - TOL/2)
UNIT = 7.0          # height unit
WALL = 2.6          # interior wall inset (matches container GF_WALL)
FLOOR = 2.0         # cavity floor above the base platform
BASE_H = 7.804      # foot (4.754) + platform (3.05)
CELL = PITCH - TOL  # 41.5, a single foot's top size

# foot cross-section as (inset_from_top, z) — the standard 0.8/1.8/2.15 foot
FOOT_PROFILE = [(2.954, 0.0), (2.15, 0.804), (2.15, 2.604), (0.0, 4.754)]
# stacking-lip inner flare as (inset, dz_above_wall_top); the base (WALL, 0) is
# the top of the straight cavity, so it is implied, not repeated here. The top
# stops at LIP_TOP_FLAT inset (not 0) so the rim is a flat ledge, not a fragile
# knife edge — a stacked bin's base rests on it cleanly.
LIP_TOP_FLAT = 0.6
LIP_FLARE = [(1.9, 0.7), (1.9, 2.5), (LIP_TOP_FLAT, 3.917)]
LIP_HEIGHT = LIP_FLARE[-1][1]  # 3.917

# bottom magnet / screw holes (gridfinity standard), 4 per cell
HOLE_OFFSET = 13.0  # from cell centre (21 - 8 mm from side)
MAGNET_R = 3.25
MAGNET_H = 2.4
SCREW_R = 1.5
SCREW_H = 6.0

# Pred filament-saving foot hollows: four quadrant "kite" pockets (split by a
# plus-cross) up to the base top, plus shallow corner "tombstone" pills at the
# magnet spots (skipped when magnet holes are on). Measured from Pred's bin.
KITE_BAND = 1.3     # pocket edge to the cell centreline
KITE_OUTER = 15.7   # pocket edge toward the cell edge
KITE_CORNER_D = 18.6  # 45-degree outer-corner cut: |x| + |y| = D
KITE_CENTRE = 5.8   # 45-degree chamfer at the centre corner
KITE_FILLET = 0.5
ARCH_POS = 13.0     # tombstone head at the magnet position
ARCH_R = 2.25       # tombstone half-width
ARCH_LEN = 3.25     # head-to-tail circle separation (toward the centre)
ARCH_DEPTH = 1.0

# Pred rim groove (a recessed ring around the outer wall just below the lip)
GROOVE_DEPTH = 0.7
GROOVE_FLAT = 1.0      # flat band below the wall top
GROOVE_CHAMFER = 0.7   # 45-degree run above and below the flat band


def rounded_rect_wire(w: float, l: float, r: float, z: float) -> Part.Wire:
    """A closed rounded-rectangle wire centred on the origin, at height ``z``."""
    hw, hl = w / 2.0, l / 2.0
    r = max(0.01, min(r, hw, hl))
    k = r * (1 - math.sqrt(2) / 2)  # arc midpoint offset
    e = [
        Part.LineSegment(Vector(hw, -(hl - r), z), Vector(hw, hl - r, z)).toShape(),
        Part.Arc(Vector(hw, hl - r, z), Vector(hw - k, hl - k, z), Vector(hw - r, hl, z)).toShape(),
        Part.LineSegment(Vector(hw - r, hl, z), Vector(-(hw - r), hl, z)).toShape(),
        Part.Arc(Vector(-(hw - r), hl, z), Vector(-(hw - k), hl - k, z), Vector(-hw, hl - r, z)).toShape(),
        Part.LineSegment(Vector(-hw, hl - r, z), Vector(-hw, -(hl - r), z)).toShape(),
        Part.Arc(Vector(-hw, -(hl - r), z), Vector(-(hw - k), -(hl - k), z), Vector(-(hw - r), -hl, z)).toShape(),
        Part.LineSegment(Vector(-(hw - r), -hl, z), Vector(hw - r, -hl, z)).toShape(),
        Part.Arc(Vector(hw - r, -hl, z), Vector(hw - k, -(hl - k), z), Vector(hw, -(hl - r), z)).toShape(),
    ]
    return Part.Wire(Part.__sortEdges__(e))


def _ruled_loft(sections):
    """Ruled (straight-sided) loft through rounded-rect sections (w, l, r, z)."""
    return Part.makeLoft([rounded_rect_wire(*s) for s in sections], True, True)


def _cell_centres(gx, gy):
    for i in range(gx):
        for j in range(gy):
            yield (i - (gx - 1) / 2.0) * PITCH, (j - (gy - 1) / 2.0) * PITCH


def _rim_groove_cutter(W, L, wall_top):
    """A ring cutter that recesses the outer wall GROOVE_DEPTH just below the lip."""
    z0 = wall_top - GROOVE_FLAT - GROOVE_CHAMFER
    secs = [(W, L, RAD, z0),
            (W - 2 * GROOVE_DEPTH, L - 2 * GROOVE_DEPTH, RAD - GROOVE_DEPTH, wall_top - GROOVE_FLAT),
            (W - 2 * GROOVE_DEPTH, L - 2 * GROOVE_DEPTH, RAD - GROOVE_DEPTH, wall_top),
            (W, L, RAD, wall_top + GROOVE_CHAMFER)]
    core = _ruled_loft(secs)
    band_h = GROOVE_FLAT + 2 * GROOVE_CHAMFER
    band = Part.makeBox(W + 2, L + 2, band_h, Vector(-(W + 2) / 2.0, -(L + 2) / 2.0, z0))
    return band.cut(core)


def _kite_solid(height: float) -> Part.Shape:
    """One quadrant kite pocket, filleted corners, extruded ``height`` up from z=0."""
    a, m, D, c = KITE_BAND, KITE_OUTER, KITE_CORNER_D, KITE_CENTRE
    pts = [(-a, -(c - a)), (-a, -m), (-(D - m), -m), (-m, -(D - m)), (-m, -a), (-(c - a), -a)]
    wire = Part.makePolygon([Vector(x, y, 0) for x, y in pts] + [Vector(pts[0][0], pts[0][1], 0)])
    sol = Part.Face(wire).extrude(Vector(0, 0, height))
    vedges = [e for e in sol.Edges
              if abs(e.tangentAt(e.FirstParameter).z) > 0.99]
    try:
        sol = sol.makeFillet(KITE_FILLET, vedges)
    except Exception:
        pass
    return sol


def _base_hollow_pattern(base_hollows: bool, magnet_holes: bool, screw_holes: bool):
    """Per-cell bottom cutters, centred on a cell at the origin: four kite pockets
    (+ corner tombstones when no magnets) and/or magnet/screw holes."""
    parts = []
    if base_hollows:
        kite = _kite_solid(BASE_H + 0.5)
        kite.translate(Vector(0, 0, -0.5))
        for ang in (0, 90, 180, 270):
            k = kite.copy()
            k.rotate(Vector(0, 0, 0), Vector(0, 0, 1), ang)
            parts.append(k)
        if not magnet_holes:   # tombstones share the magnet spots
            sep, r, depth = ARCH_LEN, ARCH_R, ARCH_DEPTH + 0.5
            slot = Part.makeBox(sep, 2 * r, depth, Vector(-sep / 2, -r, 0)).fuse([
                Part.makeCylinder(r, depth, Vector(-sep / 2, 0, 0)),
                Part.makeCylinder(r, depth, Vector(sep / 2, 0, 0))])
            slot.translate(Vector(-(ARCH_POS * 2 ** 0.5) + sep / 2, 0, -0.5))
            slot.rotate(Vector(0, 0, 0), Vector(0, 0, 1), 45)
            for ang in (0, 90, 180, 270):
                s = slot.copy()
                s.rotate(Vector(0, 0, 0), Vector(0, 0, 1), ang)
                parts.append(s)
    for dx in (-HOLE_OFFSET, HOLE_OFFSET):
        for dy in (-HOLE_OFFSET, HOLE_OFFSET):
            p = Vector(dx, dy, -0.01)
            if magnet_holes:
                parts.append(Part.makeCylinder(MAGNET_R, MAGNET_H + 0.01, p, Vector(0, 0, 1)))
            if screw_holes:
                parts.append(Part.makeCylinder(SCREW_R, SCREW_H + 0.01, p, Vector(0, 0, 1)))
    return parts


def make_shell(grid_x: int = 2, grid_y: int = 1, height_units: int = 6,
               stacking_lip: bool = True, hollow: bool = True,
               fill_inside: bool = False, rim_groove: bool = True,
               base_hollows: bool = True, magnet_holes: bool = False,
               screw_holes: bool = False) -> Part.Shape:
    """Build a gridfinity container shell solid, base bottom on the XY plane.

    Args:
        grid_x, grid_y: footprint in grid units (>= 1).
        height_units: overall height in 7 mm units (>= 2), excluding the lip.
        stacking_lip: add the gridfinity stacking lip on the rim.
        hollow: carve the interior cavity (an empty bin); False = solid block.
        fill_inside: keep the full exterior (lip/groove/feet/base hollows) but
            leave the interior SOLID to the rim — a blank to subtract your own
            compartments from. Overrides ``hollow``.
        rim_groove: recess the Pred ring around the outer wall below the lip.
        base_hollows: Pred kite pockets (+ corner tombstones) under each foot.
        magnet_holes: 6.5 mm magnet holes (x4/cell) — replaces the tombstones.
        screw_holes: 3 mm screw holes (x4/cell) in the base.
    """
    gx = max(1, int(grid_x))
    gy = max(1, int(grid_y))
    units = max(2, int(height_units))
    W = PITCH * gx - TOL
    L = PITCH * gy - TOL
    wall_top = units * UNIT
    lip_top = wall_top + (LIP_HEIGHT if stacking_lip else 0.0)

    # feet (one per cell, each a 41.5 mm chamfered foot) + merged body prism
    foot = _ruled_loft([(CELL - 2 * ins, CELL - 2 * ins, RAD - ins, z)
                        for ins, z in FOOT_PROFILE])
    feet = []
    for cx, cy in _cell_centres(gx, gy):
        f = foot.copy()
        f.translate(Vector(cx, cy, 0))
        feet.append(f)
    prism = Part.Face(rounded_rect_wire(W, L, RAD, FOOT_PROFILE[-1][1])).extrude(
        Vector(0, 0, lip_top - FOOT_PROFILE[-1][1]))
    solid = prism.fuse(feet)

    if fill_inside:
        # solid interior to the rim; only carve the lip recess so the lip remains
        if stacking_lip:
            cav = [(W - 2 * WALL, L - 2 * WALL, RAD - WALL, wall_top)]
            for ins, dz in LIP_FLARE:
                cav.append((W - 2 * ins, L - 2 * ins, RAD - ins, wall_top + dz))
            cav.append((W - 2 * LIP_TOP_FLAT, L - 2 * LIP_TOP_FLAT, RAD - LIP_TOP_FLAT, lip_top + 2))
            solid = solid.cut(_ruled_loft(cav))
        # without a lip there is nothing to carve — the body is already solid
    elif hollow:
        floor_z = BASE_H + FLOOR
        cav = [(W - 2 * WALL, L - 2 * WALL, RAD - WALL, floor_z),
               (W - 2 * WALL, L - 2 * WALL, RAD - WALL, wall_top)]
        if stacking_lip:
            for ins, dz in LIP_FLARE:
                cav.append((W - 2 * ins, L - 2 * ins, RAD - ins, wall_top + dz))
            cav.append((W - 2 * LIP_TOP_FLAT, L - 2 * LIP_TOP_FLAT, RAD - LIP_TOP_FLAT, lip_top + 2))
        else:
            cav.append((W - 2 * WALL, L - 2 * WALL, RAD - WALL, wall_top + 2))
        solid = solid.cut(_ruled_loft(cav))

    if rim_groove:
        solid = solid.cut(_rim_groove_cutter(W, L, wall_top))

    # bottom hollows / holes — one per-cell pattern replicated across the grid
    pattern = _base_hollow_pattern(base_hollows, magnet_holes, screw_holes)
    if pattern:
        cutters = []
        for cx, cy in _cell_centres(gx, gy):
            for c in pattern:
                cc = c.copy()
                cc.translate(Vector(cx, cy, 0))
                cutters.append(cc)
        solid = solid.cut(cutters)

    return solid.removeSplitter()
