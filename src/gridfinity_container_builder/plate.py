"""Pack containers onto build plates.

Simple shelf packing: containers are sorted deepest/widest first and laid
out in rows from the plate's front-left corner. When the purge tower is
enabled, a rectangle in the rear-right corner of every plate is kept clear
for the slicer's wipe tower. Containers that don't fit the current plates
spill onto new ones, so one config can span multiple plate files.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PLATE = (250.0, 210.0)
DEFAULT_SPACING = 4.0
DEFAULT_MARGIN = 2.0
DEFAULT_PURGE_TOWER = (60.0, 60.0)


@dataclass
class Placement:
    item: object
    x: float  # front-left corner of the item on the plate
    y: float


@dataclass
class _Shelf:
    y: float
    depth: float
    x_cursor: float


@dataclass
class _Plate:
    shelves: list[_Shelf] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    top: float = DEFAULT_MARGIN


def pack_plates(
    items: list[tuple[object, float, float]],
    plate_w: float,
    plate_d: float,
    spacing: float = DEFAULT_SPACING,
    margin: float = DEFAULT_MARGIN,
    reserve: tuple[float, float] | None = None,
) -> list[list[Placement]]:
    """Pack every (item, width, depth) onto as many plates as needed.

    `reserve` is the front-left corner (x0, y0) of a zone kept clear for
    the waste tower; the zone extends to the plate's rear-right corner.
    Raises ValueError if an item cannot fit an empty plate at all.
    """
    plates: list[_Plate] = []

    def usable_width(shelf_y: float, item_d: float) -> float:
        """Row x-limit, pulled in when the row overlaps the tower zone."""
        if reserve and shelf_y + item_d > reserve[1]:
            return min(plate_w - margin, reserve[0])
        return plate_w - margin

    def try_place(plate: _Plate, item: object, w: float, d: float) -> Placement | None:
        for shelf in plate.shelves:
            if d <= shelf.depth and shelf.x_cursor + w <= usable_width(shelf.y, d):
                p = Placement(item, shelf.x_cursor, shelf.y)
                shelf.x_cursor += w + spacing
                plate.placements.append(p)
                return p
        # open a new shelf at the top of the packed area
        y = plate.top
        if y + d <= plate_d - margin and margin + w <= usable_width(y, d):
            shelf = _Shelf(y=y, depth=d, x_cursor=margin + w + spacing)
            plate.shelves.append(shelf)
            plate.top = y + d + spacing
            p = Placement(item, margin, y)
            plate.placements.append(p)
            return p
        return None

    # deepest, then widest first packs the neatest shelves
    for item, w, d in sorted(items, key=lambda t: (-t[2], -t[1])):
        placed = None
        for plate in plates:
            placed = try_place(plate, item, w, d)
            if placed:
                break
        if not placed:
            plate = _Plate()
            plates.append(plate)
            if not try_place(plate, item, w, d):
                label = getattr(item, "slug", None) or str(item)
                raise ValueError(
                    f"{label} ({w:g} x {d:g} mm) does not fit a "
                    f"{plate_w:g} x {plate_d:g} mm plate"
                    + (" with the tower zone reserved" if reserve else "")
                )
    return [p.placements for p in plates]
