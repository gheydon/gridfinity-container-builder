"""Solid label text via build123d's real-font Text sketches.

Ported unchanged from the screw-organiser project.
"""

from __future__ import annotations

from functools import lru_cache

from build123d import (
    Align,
    BuildSketch,
    FontStyle,
    Locations,
    Part,
    Pos,
    Text,
    extrude,
)


@lru_cache(maxsize=8)
def _cap_factor(font: str, style: FontStyle) -> float:
    """Ratio of rendered uppercase height to font_size for this font."""
    with BuildSketch() as sk:
        Text("X", font_size=10, font=font, font_style=style,
             align=(Align.CENTER, Align.CENTER))
    return sk.sketch.bounding_box().size.Y / 10


def _build_sketch(lines: list[str], font_size: float, spacing: float, font: str,
                  style: FontStyle):
    with BuildSketch() as sk:
        n = len(lines)
        for i, line in enumerate(lines):
            y = ((n - 1) / 2 - i) * spacing
            with Locations((0, y)):
                Text(line, font_size=font_size, font=font, font_style=style,
                     align=(Align.CENTER, Align.CENTER))
    return sk.sketch


def solid_label(
    text: str,
    cap_height: float = 3.2,
    depth: float = 0.6,
    line_spacing: float = 1.4,
    max_width: float | None = None,
    font: str = "Arial",
    bold: bool = True,
) -> Part:
    """Label lying in the XY plane, extruded 0..depth, centred on the origin.

    Glyphs shrink uniformly if the text would exceed max_width. Bold is the
    default so strokes are wide enough to slice as solid two-perimeter
    regions at small cap heights.
    """
    style = FontStyle.BOLD if bold else FontStyle.REGULAR
    lines = text.split("\n")
    size = cap_height / _cap_factor(font, style)
    sketch = _build_sketch(lines, size, cap_height * line_spacing, font, style)

    if max_width:
        w = sketch.bounding_box().size.X
        if w > max_width:
            s = max_width / w
            sketch = _build_sketch(lines, size * s, cap_height * s * line_spacing, font, style)

    # centre on the overall bounding box (multi-line stacks may be asymmetric)
    bb = sketch.bounding_box()
    sketch = Pos(-bb.center().X, -bb.center().Y, 0) * sketch
    return extrude(sketch, amount=depth)


def solid_label_sized(
    lines: list[tuple[str, float]],
    depth: float = 0.6,
    line_gap: float = 1.6,
    max_width: float | None = None,
    max_height: float | None = None,
    font: str = "Arial",
    bold: bool = True,
) -> Part:
    """Multi-line label where each line has its own cap height.

    `lines` is [(text, cap_height), ...]. Every line is centred
    horizontally and the stack is centred on the origin; the whole block
    shrinks uniformly if it would exceed max_width or max_height.
    Extruded 0..depth.
    """
    style = FontStyle.BOLD if bold else FontStyle.REGULAR

    def build(scale: float):
        sketches = []
        for line, cap in lines:
            size = cap * scale / _cap_factor(font, style)
            with BuildSketch() as sk:
                Text(line, font_size=size, font=font, font_style=style,
                     align=(Align.CENTER, Align.CENTER))
            sketches.append((sk.sketch, cap * scale))
        # stack top-to-bottom with a gap proportional to the taller line
        parts = []
        y = 0.0
        for i, (sketch, cap) in enumerate(sketches):
            h = sketch.bounding_box().size.Y
            if i > 0:
                y -= line_gap * scale
            parts.append(Pos(0, y - h / 2, 0) * sketch)
            y -= h
        combined = parts[0]
        for p in parts[1:]:
            combined += p
        return combined

    sketch = build(1.0)
    bb = sketch.bounding_box()
    factors = [1.0]
    if max_width and bb.size.X > max_width:
        factors.append(max_width / bb.size.X)
    if max_height and bb.size.Y > max_height:
        factors.append(max_height / bb.size.Y)
    if min(factors) < 1.0:
        sketch = build(min(factors))

    bb = sketch.bounding_box()
    sketch = Pos(-bb.center().X, -bb.center().Y, 0) * sketch
    return extrude(sketch, amount=depth)
