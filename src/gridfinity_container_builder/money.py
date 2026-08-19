"""Money-tray interior generator: coins + (optional) notes.

Coins sit in rounded half-cylinder troughs (semicircular channels running front
to back) packed tangent across the tray, so adjacent troughs just meet at a
ridge — a scalloped surface, not square box holes. A solid label shelf runs
along the FRONT with each coin's denomination embossed on it (which also shows
the tray's orientation — labels face front). Behind the coins an optional
folded-note bay and/or a free-size slot are plain box recesses. The footprint
auto-sizes to the selected contents.

`container.py` owns the shell + exterior post-processing; its money branch uses
`money_interior()` → (cavities, labels), subtracts the cavities, and returns the
labels in their own colour volume.
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Part, Pos, Rot

from .text import solid_label

PITCH = 42.0            # Gridfinity cell pitch (mm)
GF_WALL = 2.6          # interior wall inset (matches container.GF_WALL)
COIN_CLEAR = 2.0       # added to a coin's diameter for its trough (fit slack)
END_MARGIN = 2.0       # slack at the two ends of the coin row
DIVIDER = 2.4          # wall between the coin zone and the note/slot zone (and between extras)
NOTE_MARGIN = 4.0      # added to the note-slot length
NOTE_SLOT_W = 15.0     # note-slot width (notes stand on their long edge, stacked) — unfolded
NOTE_SLOT_W_FOLD = 22.0  # ... a little wider when folded (folded notes are thicker)
LABEL_STRIP = 10.0     # solid front shelf depth that carries the denomination labels
LABEL_CAP = 5.0        # denomination label cap height (mm)
LABEL_DEPTH = 0.6      # raised label height (mm)
MAX_ROW_MM = 205.0     # cap a row's width (keeps trays bed-friendly)

# Coin diameters (mm); non-round coins use the across-flats size. From the mints.
COINS: dict[str, dict[str, float]] = {
    "AUD": {"5c": 19.41, "10c": 23.60, "20c": 28.65, "50c": 31.65, "$1": 25.00, "$2": 20.50},
    "NZD": {"10c": 20.50, "20c": 21.75, "50c": 24.75, "$1": 23.00, "$2": 26.50},
    "EUR": {"1c": 16.25, "2c": 18.75, "5c": 21.25, "10c": 19.75, "20c": 22.25,
            "50c": 24.25, "€1": 23.25, "€2": 25.75},
    "USD": {"1c": 19.05, "5c": 21.21, "10c": 17.91, "25c": 24.26, "50c": 30.61, "$1": 26.49},
    "GBP": {"1p": 20.30, "2p": 25.90, "5p": 18.00, "10p": 24.50, "20p": 21.40,
            "50p": 27.30, "£1": 23.43, "£2": 28.40},
}

# Largest banknote per currency as (width_mm, length_mm); folded in half → bay = (length/2) x width.
NOTES: dict[str, tuple[float, float]] = {
    "AUD": (65.0, 158.0), "NZD": (70.0, 155.0), "EUR": (82.0, 153.0),
    "USD": (66.3, 155.96), "GBP": (77.0, 146.0),
}

CURRENCIES = list(COINS)


def _selected(cfg: dict):
    cur = str(cfg.get("currency", "AUD")).upper()
    table = COINS.get(cur, COINS["AUD"])
    coins = [d for d in (cfg.get("coins") or list(table)) if d in table]
    extras: list[dict] = []
    if cfg.get("noteBay") and cur in NOTES:
        _, nl = NOTES[cur]          # longest note's length
        if cfg.get("noteFold"):
            slot_len, slot_w = nl / 2, NOTE_SLOT_W_FOLD
        else:
            slot_len, slot_w = nl, NOTE_SLOT_W
        extras.append({"kind": "note", "w": slot_len + NOTE_MARGIN, "d": slot_w})
    fs = cfg.get("freeSlot")
    if fs and float(fs.get("w", 0)) > 0 and float(fs.get("d", 0)) > 0:
        extras.append({"kind": "slot", "w": float(fs["w"]), "d": float(fs["d"])})
    if not coins and not extras:
        coins = [next(iter(table))]  # always build something
    return cur, table, coins, extras


def _layout(cfg: dict):
    """Plan the tray in a front-left block frame. Returns
    (troughs, strip, coin_zone_end, extras, total_w, total_h) where a coin trough is
    {cx, r, denom}; `strip` is the front label-shelf depth; troughs span strip..coin_zone_end."""
    _, table, coins, extras = _selected(cfg)

    troughs: list[dict] = []
    x = END_MARGIN
    max_dia = 0.0
    for denom in coins:
        r = (table[denom] + COIN_CLEAR) / 2
        troughs.append({"cx": x + r, "r": r, "denom": denom})
        x += 2 * r
        max_dia = max(max_dia, table[denom])
    coin_w = (x + END_MARGIN) if coins else 0.0

    # each coin sits in a scoop that curves front-to-back, so the coin zone is one coin deep
    strip = LABEL_STRIP if coins else 0.0
    coin_len = (max_dia + COIN_CLEAR) if coins else 0.0
    coin_zone_end = strip + coin_len

    # extras packed left-to-right in the back zone
    ex_y = coin_zone_end + (DIVIDER if coins and extras else 0.0)
    ex_x = 0.0
    extra_d = 0.0
    for e in extras:
        e["x"], e["y"] = ex_x, ex_y
        ex_x += e["w"] + DIVIDER
        extra_d = max(extra_d, e["d"])
    extra_w = max(0.0, ex_x - DIVIDER)

    total_w = max(coin_w, extra_w)
    total_h = coin_zone_end + ((DIVIDER + extra_d) if (coins and extras) else extra_d if extras else 0.0)
    return troughs, strip, coin_zone_end, extras, total_w, total_h


def money_tray_size(cfg: dict) -> tuple[int, int]:
    """Grid size (gx, gy) the money tray needs to fit its contents."""
    _, _, _, _, w, h = _layout(cfg)
    gx = max(1, math.ceil((min(w, MAX_ROW_MM) + 2 * GF_WALL + 0.5) / PITCH))
    gy = max(1, math.ceil((h + 2 * GF_WALL + 0.5) / PITCH))
    return gx, gy


def _edge_label(text: str, edge: str, rot: float, width: float, depth: float,
                total_h: float, floor: float) -> Part | None:
    """A raised text label on an outer wall (front/back/left/right), rotated `rot` degrees in-plane."""
    if not text:
        return None
    face = {"front": depth, "back": depth, "left": width, "right": width}.get(edge, depth)
    lbl = solid_label(text, cap_height=6.0, depth=0.6, max_width=face - 8)
    lbl = Rot(0, 0, rot) * lbl                      # in-plane orientation
    zc = floor + (total_h - floor) * 0.55           # vertical centre on the wall
    if edge == "back":
        return Pos(width / 2, depth, zc) * (Rot(90, 0, 180) * lbl)
    if edge == "left":
        return Pos(0, depth / 2, zc) * (Rot(0, -90, 90) * lbl)
    if edge == "right":
        return Pos(width, depth / 2, zc) * (Rot(0, 90, 90) * lbl)
    return Pos(width / 2, 0, zc) * (Rot(90, 0, 0) * lbl)   # front (default)


def money_interior(cell: dict, params: dict, total_h: float, width: float, depth: float,
                   cfg: dict) -> tuple[Part, list[Part]]:
    """(union of cavities, list of raised labels) — denomination labels + optional edge label."""
    troughs, strip, coin_end, extras, bw, bh = _layout(cfg)
    ox = cell["x"] + max(0.0, (cell["width"] - bw) / 2)
    oy = cell["y"] + max(0.0, (cell["depth"] - bh) / 2)
    floor = params["floor"]
    parts: list[Part] = []
    labels: list[Part] = []

    # coin scoops: half-cylinders with the axis along X (across the coin's width), so each scoop
    # curves front-to-back and opens toward the front. Rim at the interior top. Each scoop is
    # CENTRED in the coin zone (small coins get equal front/back margin); labels on the front shelf.
    coin_zone = coin_end - strip
    zone_mid = oy + strip + coin_zone / 2
    for t in troughs:
        L = 2 * t["r"]                                 # scoop spans the coin's width in X
        cav = Rot(0, 90, 0) * Cylinder(radius=t["r"], height=L)  # axis X
        parts.append(Pos(ox + t["cx"], zone_mid, total_h) * cav)
        if t["denom"]:
            lbl = solid_label(t["denom"], cap_height=LABEL_CAP, depth=LABEL_DEPTH,
                              max_width=2 * t["r"] - 2)
            labels.append(Pos(ox + t["cx"], oy + strip / 2, total_h) * lbl)

    # note bay / free slot: box recesses from the floor to (over) the top
    bh_box = total_h - floor + 0.5
    for e in extras:
        box = Box(e["w"], e["d"], bh_box)
        parts.append(Pos(ox + e["x"] + e["w"] / 2, oy + e["y"] + e["d"] / 2, floor + bh_box / 2) * box)

    # optional custom edge label on any outer wall
    el = cfg.get("edgeLabel") or {}
    edge_lbl = _edge_label(str(el.get("text", "")).strip(), str(el.get("edge", "front")),
                           float(el.get("rot", 0)), width, depth, total_h, floor)
    if edge_lbl is not None:
        labels.append(edge_lbl)

    union = parts[0]
    for p in parts[1:]:
        union = union + p
    return union, labels
