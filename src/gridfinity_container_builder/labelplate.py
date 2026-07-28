"""Pred-style printable label plates.

The swappable label for the Gridfinity bins / storage box by Pred
(printables.com/model/592545): 0.8 mm thick, 11.5 mm tall, gx*42 - 4.2 mm
wide, with narrowed snap-in end tabs and semi-circular notches that let
the plate bend into the bin's label pocket and under its retaining tabs.
Outline geometry ported from gflabel's PredBase
(github.com/ndevenish/gflabel, BSD licence, (c) 2024 Nicholas Devenish).
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import (
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Circle,
    FilletPolyline,
    Locations,
    Mode,
    Part,
    Plane,
    Polyline,
    Pos,
    Sketch,
    fillet,
    make_face,
    mirror,
)
from build123d import extrude as _extrude

from .interior import PLATE_DEPTH, PLATE_THICKNESS
from .text import solid_label

TEXT_HEIGHT = 0.2  # raised text above the plate face
TEXT_OVERLAP = 0.1  # sunk into the plate so the parts fuse
EDGE_FILLET = 0.2


def plate_width(gx: int) -> float:
    """Pred's label width for a gx-unit bin (1u -> 37.8 mm)."""
    return gx * 42.0 - 4.2


@dataclass
class LabelPlate:
    name: str
    size: tuple[float, float, float]
    plate: Part
    text: Part | None


def _outline(width_mm: float, height_mm: float) -> Sketch:
    """Outer edge of a Pred label: straight body with narrowed tab ends."""
    straight = width_mm - 2 * 1.9
    x = -straight / 2
    with BuildSketch() as sk:
        with BuildLine() as line:
            l1 = Polyline([(x - 1.9, 0), (x - 1.9, 2.85), (x - 0.9, 2.85)])
            FilletPolyline(
                [l1 @ 1, (x - 0.9, height_mm / 2), (0, height_mm / 2)],
                radius=0.9,
            )
            mirror(line.line, Plane.XZ)
            mirror(line.line, Plane.YZ)
        make_face()
        with Locations([(x - 0.4, 0), (-x + 0.4, 0)]):
            Circle(0.75, mode=Mode.SUBTRACT)
    return sk.sketch


def build_label_plate(slug: str, label: str, gx: int,
                      labels_cfg: dict) -> LabelPlate:
    """Label plate lying flat on z=0, centred on the XY origin."""
    width = plate_width(gx)

    with BuildPart() as bp:
        _extrude(_outline(width, PLATE_DEPTH), amount=PLATE_THICKNESS)
        edges = [e for f in bp.faces().filter_by(Axis.Z) for e in f.edges()]
        fillet(edges, radius=EDGE_FILLET)
    plate = bp.part

    text = None
    if label:
        solid = solid_label(
            str(label),
            cap_height=labels_cfg["capHeight"],
            depth=TEXT_HEIGHT + TEXT_OVERLAP,
            line_spacing=labels_cfg["lineSpacing"],
            max_width=width - 2 * 3.5,
            font=labels_cfg["font"],
            bold=labels_cfg["bold"],
        )
        text = Pos(0, 0, PLATE_THICKNESS - TEXT_OVERLAP) * solid

    return LabelPlate(
        name=f"{slug}-label",
        size=(width, PLATE_DEPTH, PLATE_THICKNESS + (TEXT_HEIGHT if text else 0)),
        plate=plate,
        text=text,
    )
