"""Pred storage-box front labels (the big slide-in label).

Flat two-colour label, dimensions measured from Pred's box-label STEP
(and matching gflabel's PredBoxBase): a rounded-rectangle plate 0.85 mm
thick with 3.5 mm corners and a 0.2 mm edge chamfer, sized by the box
width in bins (4/5/6/7 units). The text prints in a second colour and,
by request, spans from 0.2 mm above the bed to 0.2 mm above the label —
so the bottom 0.2 mm and the whole plate outline stay body-colour, the
text colour runs through the thickness, and the letters stand 0.2 mm
proud on top for a crisp raised finish.
"""

from __future__ import annotations

from build123d import (
    Axis,
    BuildPart,
    BuildSketch,
    Pos,
    RectangleRounded,
    chamfer,
    extrude,
)

from .container import Container
from .text import solid_label, solid_label_sized

# gflabel PredBoxBase widths, confirmed against the STEP (5u -> 67.5)
BOX_WIDTHS = {4: 25.5, 5: 67.5, 6: 82.0, 7: 82.0}
HEIGHT = 24.5
THICKNESS = 0.85
CORNER_R = 3.5
CHAMFER = 0.2

TEXT_BOTTOM = 0.2          # text starts this far above the bed
TEXT_TOP_ABOVE = 0.2       # ... and finishes this far above the label top
DEFAULT_CAP_HEIGHT = 13.0  # big front text; auto-shrinks to width


def slugify(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "label"


def build_box_label(text: str, width_units: int, labels_cfg: dict | None = None) -> Container:
    """A Pred box label as a two-colour Container (body + text volumes).

    Reuses Container so the normal export maps body -> bin tool and the
    text -> label tool.
    """
    if width_units not in BOX_WIDTHS:
        raise SystemExit(f"box label width must be one of {sorted(BOX_WIDTHS)} units, "
                         f"got {width_units}")
    cfg = {"capHeight": DEFAULT_CAP_HEIGHT, "lineSpacing": 1.2,
           "font": "Arial", "bold": True, **(labels_cfg or {})}
    width = BOX_WIDTHS[width_units]

    with BuildPart() as bp:
        with BuildSketch():
            RectangleRounded(width, HEIGHT, CORNER_R)
        extrude(amount=THICKNESS)
        chamfer([e for f in bp.faces().filter_by(Axis.Z) for e in f.edges()],
                length=CHAMFER)
    plate = bp.part

    text_part = None
    body = plate
    if text:
        # per-line cap heights: explicit `capHeights: [8, 5.5]`, else the
        # base capHeight with each subsequent line scaled by `subScale`
        raw_lines = str(text).split("\n")
        heights = cfg.get("capHeights")
        if not heights:
            sub = cfg.get("subScale", 0.72)
            heights = [cfg["capHeight"] * (1.0 if i == 0 else sub)
                       for i in range(len(raw_lines))]
        sized = list(zip(raw_lines, [float(h) for h in heights]))
        solid = solid_label_sized(
            sized,
            depth=THICKNESS + TEXT_TOP_ABOVE - TEXT_BOTTOM,
            line_gap=cfg.get("lineGap", 2.2),
            max_width=width - 2 * (CORNER_R + 2),
            font=cfg["font"],
            bold=cfg["bold"],
        )
        text_part = Pos(0, 0, TEXT_BOTTOM) * solid
        body = plate - text_part

    return Container(
        name=f"boxlabel-{slugify(str(text) or f'{width_units}u')}",
        size=(width, HEIGHT, THICKNESS + TEXT_TOP_ABOVE),
        body=body,
        labels=[text_part] if text_part is not None else [],
    )
