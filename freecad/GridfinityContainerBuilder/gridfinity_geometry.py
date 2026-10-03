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
# the top of the straight cavity, so it is implied, not repeated here.
LIP_FLARE = [(1.9, 0.7), (1.9, 2.5), (0.0, 3.917)]
LIP_HEIGHT = LIP_FLARE[-1][1]  # 3.917


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


def make_shell(grid_x: int = 2, grid_y: int = 1, height_units: int = 6,
               stacking_lip: bool = True, hollow: bool = True) -> Part.Shape:
    """Build a gridfinity container shell solid, base bottom on the XY plane.

    Args:
        grid_x, grid_y: footprint in grid units (>= 1).
        height_units: overall height in 7 mm units (>= 2), excluding the lip.
        stacking_lip: add the gridfinity stacking lip on the rim.
        hollow: carve the interior cavity (an empty bin); False = solid block.
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
    for i in range(gx):
        for j in range(gy):
            f = foot.copy()
            f.translate(Vector((i - (gx - 1) / 2.0) * PITCH,
                               (j - (gy - 1) / 2.0) * PITCH, 0))
            feet.append(f)
    prism = Part.Face(rounded_rect_wire(W, L, RAD, FOOT_PROFILE[-1][1])).extrude(
        Vector(0, 0, lip_top - FOOT_PROFILE[-1][1]))
    solid = prism.fuse(feet)

    if not hollow:
        return solid.removeSplitter()

    floor_z = BASE_H + FLOOR
    cav = [(W - 2 * WALL, L - 2 * WALL, RAD - WALL, floor_z),
           (W - 2 * WALL, L - 2 * WALL, RAD - WALL, wall_top)]
    if stacking_lip:
        for ins, dz in LIP_FLARE:
            cav.append((W - 2 * ins, L - 2 * ins, RAD - ins, wall_top + dz))
        cav.append((W, L, RAD, lip_top + 2))          # punch through the rim
    else:
        cav.append((W - 2 * WALL, L - 2 * WALL, RAD - WALL, wall_top + 2))
    return solid.cut(_ruled_loft(cav)).removeSplitter()
