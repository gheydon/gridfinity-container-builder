"""Money-tray interior generator: coins + (optional) notes.

A money tray is an external Gridfinity shell whose interior is a packed grid of
compartments — one sloped-floor pocket per selected coin denomination (coins lie
flat and gather at the low front edge), plus an optional folded-note bay and an
optional free-size slot. The footprint auto-sizes to the selected contents.

Only the geometry + sizing live here; `container.py` owns the shell and the
exterior post-processing (rim groove, base hollows, fillets, lid trim). See
`build_container` — the money branch subtracts `money_cavities()` from the shell.
"""

from __future__ import annotations

import math

from build123d import Part, Pos

from .interior import extrude_profile_x

PITCH = 42.0            # Gridfinity cell pitch (mm)
GF_WALL = 2.6          # interior wall inset (matches container.GF_WALL)
COIN_CLEAR = 2.2       # added to a coin's diameter for its pocket (fit + a little slack)
DIVIDER = 2.4          # wall left between adjacent compartments
NOTE_MARGIN = 4.0      # added around a folded note
SLOPE = 0.30           # coin-pocket floor rise back-to-front, as a fraction of pocket depth
SLOPE_MAX = 6.0        # cap the rise (mm)
MAX_ROW_MM = 205.0     # wrap compartments to a new row past this width (keeps trays bed-friendly)

# Coin diameters (mm). Non-round coins use the across-flats size (they still need
# that much lane width). Values from the issuing mints / central banks.
COINS: dict[str, dict[str, float]] = {
    "AUD": {"5c": 19.41, "10c": 23.60, "20c": 28.65, "50c": 31.65, "$1": 25.00, "$2": 20.50},
    "NZD": {"10c": 20.50, "20c": 21.75, "50c": 24.75, "$1": 23.00, "$2": 26.50},
    "EUR": {"1c": 16.25, "2c": 18.75, "5c": 21.25, "10c": 19.75, "20c": 22.25,
            "50c": 24.25, "€1": 23.25, "€2": 25.75},
    "USD": {"1c": 19.05, "5c": 21.21, "10c": 17.91, "25c": 24.26, "50c": 30.61, "$1": 26.49},
    "GBP": {"1p": 20.30, "2p": 25.90, "5p": 18.00, "10p": 24.50, "20p": 21.40,
            "50p": 27.30, "£1": 23.43, "£2": 28.40},
}

# Largest banknote per currency as (width_mm, length_mm); a note is folded in half
# along its length, so the bay is (length/2) x width.
NOTES: dict[str, tuple[float, float]] = {
    "AUD": (65.0, 158.0),
    "NZD": (70.0, 155.0),
    "EUR": (82.0, 153.0),
    "USD": (66.3, 155.96),
    "GBP": (77.0, 146.0),
}

CURRENCIES = list(COINS)


def _compartments(cfg: dict) -> list[dict]:
    """Resolve the money config into a list of {kind,label,w,d} compartments (mm)."""
    cur = str(cfg.get("currency", "AUD")).upper()
    table = COINS.get(cur, COINS["AUD"])
    coins = cfg.get("coins") or list(table)
    out: list[dict] = []
    for denom in coins:
        if denom not in table:
            continue
        s = table[denom] + COIN_CLEAR
        out.append({"kind": "coin", "label": denom, "w": s, "d": s})
    if cfg.get("noteBay") and cur in NOTES:
        nw, nl = NOTES[cur]
        out.append({"kind": "note", "label": "notes",
                    "w": nl / 2 + NOTE_MARGIN, "d": nw + NOTE_MARGIN})
    fs = cfg.get("freeSlot")
    if fs and float(fs.get("w", 0)) > 0 and float(fs.get("d", 0)) > 0:
        out.append({"kind": "slot", "label": "", "w": float(fs["w"]), "d": float(fs["d"])})
    if not out:  # nothing selected → a single small pocket so we always build something
        out.append({"kind": "coin", "label": "", "w": 24.0, "d": 24.0})
    return out


def _pack(items: list[dict]) -> tuple[list[dict], float, float]:
    """Shelf-pack compartments into rows (front to back); return (placed, width, depth).
    Each placed item gains x,y = its front-left corner in the packed block frame."""
    rows: list[tuple[list[dict], float]] = []
    row: list[dict] = []
    roww = 0.0
    for it in items:
        add = it["w"] + (DIVIDER if row else 0.0)
        if row and roww + add > MAX_ROW_MM:
            rows.append((row, roww))
            row, roww = [], 0.0
            add = it["w"]
        row.append({**it})
        roww += add
    if row:
        rows.append((row, roww))

    placed: list[dict] = []
    y = 0.0
    total_w = 0.0
    for r, roww in rows:
        rowh = max(i["d"] for i in r)
        x = 0.0
        for i in r:
            i["x"], i["y"] = x, y
            placed.append(i)
            x += i["w"] + DIVIDER
        total_w = max(total_w, roww)
        y += rowh + DIVIDER
    total_h = max(0.0, y - DIVIDER)
    return placed, total_w, total_h


def money_tray_size(cfg: dict) -> tuple[int, int]:
    """Grid size (gx, gy) the money tray needs to fit its contents."""
    _, w, h = _pack(_compartments(cfg))
    gx = max(1, math.ceil((w + 2 * GF_WALL + 0.5) / PITCH))
    gy = max(1, math.ceil((h + 2 * GF_WALL + 0.5) / PITCH))
    return gx, gy


def money_cavities(cell: dict, params: dict, total_h: float, cfg: dict) -> Part:
    """Union of the compartment cavities, positioned inside `cell` (centred)."""
    placed, bw, bh = _pack(_compartments(cfg))
    ox = cell["x"] + max(0.0, (cell["width"] - bw) / 2)
    oy = cell["y"] + max(0.0, (cell["depth"] - bh) / 2)
    floor = params["floor"]
    top = total_h + 0.5  # small over-cut so the compartment tops open cleanly
    parts: list[Part] = []
    for it in placed:
        px, py, w, d = ox + it["x"], oy + it["y"], it["w"], it["d"]
        if it["kind"] == "coin":
            rise = min(d * SLOPE, SLOPE_MAX)   # floor rises from the low front to the back
            prof = [(0.0, floor), (d, floor + rise), (d, top), (0.0, top)]
        else:                                   # note bay / free slot: flat floor
            prof = [(0.0, floor), (d, floor), (d, top), (0.0, top)]
        parts.append(Pos(px, py, 0) * extrude_profile_x(prof, w))
    union = parts[0]
    for p in parts[1:]:
        union = union + p
    return union
