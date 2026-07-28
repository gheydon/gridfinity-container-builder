"""Assemble one Gridfinity container from a catalog spec.

The shell is a standard Gridfinity bin (BaseEqual feet + StackingLip) from
the gridfinity-build123d package, built to `height_units` x 7 mm overall
(excluding the lip). The default 6 units (42 mm) matches the Gridfinity
Storage Box by Pred, whose lid accommodates the stacking lip and locks
onto full-height bins. The screw-organiser scoop/ramp/label interior is
carved into the shell's solid fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from build123d import Part, Pos

from .catalog import ContainerSpec
from .interior import (
    POCKET_DEPTH_Y,
    POCKET_RECESS,
    POCKET_SIDE_MARGIN,
    TAB_LENGTH,
    TAB_OVERHANG,
    TAB_THICKNESS,
    ramp_label,
    scoop_cavity,
    shelf_cavity,
    shelf_gussets,
    test_spec,
)

GF_WALL = 2.6  # wall thickness needed behind the gridfinity stacking lip
GF_INTERIOR_TRIM = 0.35  # stacked feet / the box lid reach this far below the wall top

# Pred's rim indentation, measured from his bin: the outer face steps in
# 0.7 mm just below the stacking lip — flat over the top 1 mm of the
# wall, 45-degree chamfers running out below and above
GROOVE_DEPTH = 0.7
GROOVE_FLAT_BOTTOM = 1.0   # below the wall top
GROOVE_CHAMFER = 0.7

# Pred hollows each foot from below to save filament — dimensions
# measured from his bin: four kite-shaped pockets in the quadrants
# (separated by a plus-cross of material), plus shallow tombstone pockets
# at the magnet positions, pointing at the corners. The tombstones are
# skipped when magnet holes are enabled.
KITE_BAND = 1.3        # pocket edge to cell centreline
KITE_OUTER = 15.7      # pocket edge from centre toward the cell edge
KITE_CORNER_D = 18.6   # 45-degree corner cut: |x'| + |y'| = D
KITE_CENTRE_C = 5.8    # 45-degree chamfer at the centre corner
KITE_FILLET = 0.5
ARCH_POS = 13.0        # tombstone head centre (the magnet position)
ARCH_R = 2.25          # tombstone half-width
ARCH_LEN = 3.25        # head centre to flat end (toward cell centre)
ARCH_DEPTH = 1.0
POCKET_FILLET = 0.4    # softening on the pocket mouth edges underneath
UNIT_HEIGHT = 7.0  # gridfinity height unit
FLOOR = 2.0  # cavity floor thickness above the base

LABEL_DEFAULTS = {
    "capHeight": 3.2,
    # 0.6 proud / 0.2 embedded: on the 63deg ramp each printed layer gets
    # a ~0.9 mm band of label colour so glyphs slice cleanly
    "depth": 0.6,
    "overlap": 0.2,
    "lineSpacing": 1.4,
    "showCounts": False,
    "font": "Arial",
    "bold": True,
}
TEST_DEFAULTS = {"clearance": 0.4, "rim": 1.2, "gaugeLength": 10.0}

# The label area is filled by a background plate (own colour slot,
# defaulting to the bin's) with the text raised on top — the same stack
# as Pred's swappable plates (0.8 plate + 0.2 text), fused in place, and
# the text tops out level with the wall top / checker surface.
BACKGROUND_THICKNESS = 0.8
LABEL_RAISE = 0.2  # text above the background plate
LABEL_SINK = 0.1   # sunk into the plate so the parts fuse


@dataclass
class Container:
    name: str
    size: tuple[float, float, float]
    body: Part
    labels: list[Part] = field(default_factory=list)
    background: Part | None = None  # label-area plate (own colour slot)


def build_container(
    spec: ContainerSpec,
    height_units: int = 6,
    magnets: bool = False,
    checkers: bool = True,
    label_style: str = "direct",
    labels_cfg: dict | None = None,
    test_cfg: dict | None = None,
    symbols: bool = False,
) -> Container:
    """label_style "direct" (default): Pred's label shelf with the text
    written straight onto the recessed label area; "plates" (alias
    "pred"): the same shelf with retaining tabs for swappable printable
    label plates; "embossed": text fused onto the organiser-style ramp.
    labels_cfg and test_cfg take the screw-organiser "labels" /
    "testHoles" settings."""
    from gridfinity_build123d import BaseEqual, Bin, BottomCorners, MagnetHole, StackingLip

    features = [MagnetHole(BottomCorners())] if magnets else []
    base = BaseEqual(grid_x=spec.gx, grid_y=spec.gy, features=features)
    base_h = base.bounding_box().size.Z
    total_h = height_units * UNIT_HEIGHT
    shell = Bin(base, height=total_h - base_h, lip=StackingLip())

    bb = shell.bounding_box()
    width, depth = bb.size.X, bb.size.Y
    lip_h = bb.size.Z - total_h
    shell = Pos(-bb.min.X, -bb.min.Y, -bb.min.Z) * shell

    params = {
        "height": total_h,
        "floor": base_h + FLOOR,
        "rampAngle": spec.ramp_angle,
        "scoopRadius": spec.scoop_radius,
        "labels": {**LABEL_DEFAULTS, **(labels_cfg or {})},
        "test": {**TEST_DEFAULTS, **(test_cfg or {})},
    }
    cell = {
        "x": GF_WALL,
        "y": GF_WALL,
        "width": width - 2 * GF_WALL,
        "depth": depth - 2 * GF_WALL,
        "shelf": 0.0,
    }

    body_groove = _rim_groove(width, depth, total_h)
    base_hollows = _base_hollows(spec.gx, spec.gy, base_h, magnets)

    labelled = spec.type != "open"
    if spec.type == "scoop":
        scoop_r = spec.bin.get("scoopRadius", params["scoopRadius"])
    else:  # deep and open use the small front fillet
        scoop_r = spec.bin.get("scoopRadius", 3)
    test = test_spec(spec.bin, params) if labelled and checkers else None

    symbol_kind = None
    if labelled:
        explicit = spec.bin.get("symbol")
        if explicit not in (None, False) and str(explicit).lower() not in ("false", "none", "no"):
            from .symbols import canonical
            symbol_kind = canonical(explicit)
        elif symbols:
            from .symbols import symbol_for
            gauge = test if test else test_spec(spec.bin, {**params, "test": params["test"]})
            symbol_kind = symbol_for(spec.bin, gauge)

    label = None
    background = None
    if labelled and label_style in ("direct", "plates", "pred"):
        body, label, background = _pred_shelf_body(
            shell, cell, params, scoop_r, test, width, depth, total_h, lip_h,
            spec.bin, direct=(label_style == "direct"), symbol=symbol_kind)
        body -= body_groove
        body -= base_hollows
        body = _fillet_bottom_pockets(body)
    else:
        cavity, ramp = scoop_cavity(cell, params, scoop_radius=scoop_r,
                                    with_ramp=labelled, test=test)
        body = shell - cavity
        # trim interior structure so stacked feet and the box lid seat fully
        body -= Pos(width / 2, depth / 2, total_h - GF_INTERIOR_TRIM) * _prism_centered(
            width - 2 * GF_WALL, depth - 2 * GF_WALL, 1.15, 2
        )
        if labelled:
            label = ramp_label(cell, spec.bin, params, ramp)
        body -= body_groove
        body -= base_hollows
        body = _fillet_bottom_pockets(body)

    return Container(
        name=spec.slug,
        size=(width, depth, total_h + lip_h),
        body=body,
        labels=[label] if label is not None else [],
        background=background,
    )


def _pred_shelf_body(shell, cell, params, scoop_r, test,
                     width, depth, total_h, lip_h, bin_spec, direct=True, symbol=None):
    """Carve the interior with Pred's label shelf at the top back.

    Geometry measured from Pred's own bin (model 592545): the pocket floor
    sits POCKET_RECESS below the wall top, POCKET_DEPTH_Y deep, reaching
    to POCKET_SIDE_MARGIN from the outer faces at the sides; the stacking
    lip is cleared above the pocket; 45-degree gussets support the shelf
    from below.

    With `direct` the label text is written straight onto the recessed
    label area (raised 0.2, safely below the wall top) and returned as
    the second colour; otherwise two retaining tabs are added over the
    pocket sides for a swappable printed label plate.

    Returns (body, label_part_or_None).
    """
    from build123d import Box

    from .text import solid_label

    H = params["height"]

    cavity, info = shelf_cavity(cell, params, scoop_radius=scoop_r, test=test)
    body = shell - cavity

    # trim the interior 0.35 below the wall top only in front of the
    # shelf — the shelf surround stays at wall-top level like Pred's bin
    trim_d = cell["depth"] - (POCKET_DEPTH_Y + info["rim"])
    body -= Pos(cell["x"] + cell["width"] / 2, cell["y"] + trim_d / 2,
                total_h - GF_INTERIOR_TRIM) * _prism_centered(
        cell["width"], trim_d, 1.15, 2)

    # label pocket: cut into the side walls down to POCKET_SIDE_MARGIN and
    # up through the stacking lip so the label drops in from above
    pocket_w = width - 2 * POCKET_SIDE_MARGIN
    pocket_back = depth - GF_WALL
    pocket_cy = pocket_back - POCKET_DEPTH_Y / 2
    body -= Pos(width / 2, pocket_cy,
                H - POCKET_RECESS + (POCKET_RECESS + lip_h + 1) / 2) * Box(
        pocket_w, POCKET_DEPTH_Y, POCKET_RECESS + lip_h + 1)

    label = None
    background = None
    if direct:
        # background plate fills the recessed label area (Pred's plate,
        # fused in place); the text sits on it, topping out at the wall top
        background = Pos(width / 2, pocket_cy,
                         H - POCKET_RECESS + BACKGROUND_THICKNESS / 2) * Box(
            pocket_w, POCKET_DEPTH_Y, BACKGROUND_THICKNESS)
        z_face = H - POCKET_RECESS + BACKGROUND_THICKNESS - LABEL_SINK

        # icon on the left of the label area (auto-picked screw/nut/washer)
        icon_part = None
        text_reserve = 0.0
        if symbol:
            from .symbols import build_symbol
            icon_w = min(11.0, pocket_w * 0.30)
            icon_h = POCKET_DEPTH_Y - 3.0
            icon = build_symbol(symbol, icon_w, icon_h, LABEL_RAISE + LABEL_SINK)
            iw = icon.bounding_box().size.X
            icon_cx = width / 2 - pocket_w / 2 + 2.0 + iw / 2
            icon_part = Pos(icon_cx, pocket_cy, z_face) * icon
            text_reserve = iw + 2.5

        raw = bin_spec["label"] if "label" in bin_spec else "Misc"
        if raw:
            cfg = {**params["labels"], **bin_spec.get("labels", {})}
            text = str(raw)
            if cfg["showCounts"] and bin_spec.get("count") is not None:
                text += f" ({bin_spec['count']})"
            solid = solid_label(
                text,
                cap_height=cfg["capHeight"],
                depth=LABEL_RAISE + LABEL_SINK,
                line_spacing=cfg["lineSpacing"],
                max_width=pocket_w - 4 - text_reserve,
                font=cfg["font"],
                bold=cfg["bold"],
            )
            label = Pos(width / 2 + text_reserve / 2, pocket_cy, z_face) * solid
        if icon_part is not None:
            label = icon_part if label is None else label + icon_part
    else:
        # retaining tabs over the pocket sides: the label plate's end tabs
        # slide under them (bend the plate slightly to insert, Pred-style)
        for x0 in (POCKET_SIDE_MARGIN, width - POCKET_SIDE_MARGIN - TAB_OVERHANG):
            body += Pos(x0 + TAB_OVERHANG / 2, pocket_cy,
                        H + TAB_THICKNESS / 2) * Box(
                TAB_OVERHANG, TAB_LENGTH, TAB_THICKNESS)

    if info["support"] != "solid":
        gussets = shelf_gussets(cell, params, info)
        if gussets is not None:
            body += gussets
    return body, label, background


def _base_hollows(gx: int, gy: int, base_h: float, magnets: bool = False) -> Part:
    """Pred's filament-saving foot hollows, one pattern per foot.

    Four quadrant kites cut from below up to the base top (leaving the
    floor plate above) plus the shallow corner tombstones — the latter
    only when magnet holes are off, since they share the magnet spots.
    """
    from build123d import BuildPart, BuildSketch, Pos, extrude

    from build123d import (
        BuildLine, Plane, Polyline, Rot, SlotCenterToCenter, fillet, make_face,
    )

    a, m, D, c = KITE_BAND, KITE_OUTER, KITE_CORNER_D, KITE_CENTRE_C
    with BuildPart() as kite_bp:
        with BuildSketch() as sk:
            with BuildLine():
                Polyline(
                    (-a, -(c - a)),
                    (-a, -m),
                    (-(D - m), -m),
                    (-m, -(D - m)),
                    (-m, -a),
                    (-(c - a), -a),
                    close=True,
                )
            make_face()
            fillet(sk.vertices(), radius=KITE_FILLET)
        extrude(amount=base_h + 0.5)
    kite = Pos(0, 0, -0.5) * kite_bp.part

    kites = kite
    for angle in (90, 180, 270):
        kites += Rot(0, 0, angle) * kite

    pattern = kites
    if not magnets:
        # tombstone lies along the cell diagonal, head at the magnet spot
        with BuildPart() as arch_bp:
            with BuildSketch(Plane.XY):
                SlotCenterToCenter(center_separation=ARCH_LEN, height=2 * ARCH_R)
            extrude(amount=ARCH_DEPTH + 0.5)
        # place the head-end circle at the magnet position: distance from
        # the cell centre along the -45 diagonal is ARCH_POS * sqrt(2)
        arch = (
            Rot(0, 0, 45)
            * Pos(-(ARCH_POS * 2 ** 0.5) + ARCH_LEN / 2, 0, -0.5)
            * arch_bp.part
        )
        arches = arch
        for angle in (90, 180, 270):
            arches += Rot(0, 0, angle) * arch
        pattern += arches

    cells = None
    for i in range(gx):
        for j in range(gy):
            cut = Pos(42.0 * i + 20.75, 42.0 * j + 20.75, 0) * pattern
            cells = cut if cells is None else cells + cut
    return cells


def _fillet_bottom_pockets(body: Part, radius: float = POCKET_FILLET) -> Part:
    """Round the mouth edges of the foot pockets (and any magnet holes)
    on the underside, like the softened rims on Pred's bin. Falls back to
    the unfilleted body if the fillet fails."""
    from build123d import Plane, fillet

    edges = []
    for f in body.faces().filter_by(Plane.XY):
        if abs(f.center().Z) < 0.05:
            for w in f.inner_wires():
                edges.extend(w.edges())
    if not edges:
        return body
    try:
        return fillet(edges, radius=radius)
    except Exception:
        return body


def _rim_groove(width: float, depth: float, H: float) -> Part:
    """Pred's rim indentation as a ring cutter around the outer walls.

    Built as a box band minus a lofted core whose inset follows the
    groove profile: full outline below, stepped in by GROOVE_DEPTH over
    the flat band, back out to full at the lip base.
    """
    from build123d import Box, BuildPart, BuildSketch, Mode, Plane, Pos, RectangleRounded, loft

    r = 3.75
    z0 = H - GROOVE_FLAT_BOTTOM - GROOVE_CHAMFER
    sections = [
        (z0, 0.0),
        (H - GROOVE_FLAT_BOTTOM, GROOVE_DEPTH),
        (H, GROOVE_DEPTH),
        (H + GROOVE_CHAMFER, 0.0),
    ]
    with BuildPart() as bp:
        for z, inset in sections:
            with BuildSketch(Plane.XY.offset(z)):
                RectangleRounded(width - 2 * inset, depth - 2 * inset, r - inset)
        loft(ruled=True)
    core = bp.part

    band_h = GROOVE_FLAT_BOTTOM + 2 * GROOVE_CHAMFER
    band = Pos(0, 0, z0 + band_h / 2) * Box(width + 2, depth + 2, band_h)
    return Pos(width / 2, depth / 2, 0) * (band - core)


def _prism_centered(width: float, depth: float, corner_r: float, height: float) -> Part:
    """Rounded-corner block centred on XY origin, sitting on z=0."""
    from build123d import BuildPart, BuildSketch, RectangleRounded, extrude

    with BuildPart() as bp:
        with BuildSketch():
            RectangleRounded(width, depth, corner_r)
        extrude(amount=height)
    return bp.part
