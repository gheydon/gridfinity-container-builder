"""CLI.

  gridfinity-container-builder [--config <file.yaml> ...]
                               [--layouts-dir <dir>]
                               [--format 3mf|stl] [--height-units 6]
                               [--magnets] [--counts] [--list]
                               [--plates] [--plate-size 250x210]
                               [--purge-tower] [--purge-tower-size 60x60]
                               [--spacing 4]
                               [--force] [--out out]

Config files are screw-organiser layouts or container manifests (a
`containers:` list, optionally pulling in `layouts:`). The derived,
deduplicated catalog is built one file per container — or, with --plates,
packed onto build plates that spill across multiple files as needed.
Existing output files are skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import time
from pathlib import Path

from .catalog import ContainerSpec, build_catalog, find_layouts, load_source
from .container import LABEL_DEFAULTS, Container, build_container
from .export import export, export_labels, export_plate
from .filaments import patch_slicer_config, resolve_filaments
from .labelplate import LabelPlate, build_label_plate
from .printers import global_config_path, load_printers, resolve_printer, tower_size
from .plate import (
    DEFAULT_MARGIN,
    DEFAULT_PLATE,
    DEFAULT_PURGE_TOWER,
    DEFAULT_SPACING,
    pack_plates,
)

DEFAULT_LAYOUTS_DIR = "../screw-organiser/layouts"
BOX_GRID = (5, 4)  # the Pred storage box hides a 5x4 baseplate
ANCHOR = 4.0  # position-anchor tab side length


def _anchor() -> Container:
    """One-layer corner tab that pins the arrangement's bounding box."""
    from build123d import Box, Pos

    body = Pos(ANCHOR / 2, ANCHOR / 2, 0.1) * Box(ANCHOR, ANCHOR, 0.2)
    return Container(name="position-anchor", size=(ANCHOR, ANCHOR, 0.2),
                     body=body, labels=[])


def _compact_centered(placements, getter, plate_w, plate_d, spacing, reserve,
                      left_margin=0.0):
    """Repack one bed's items into a compact square-ish block, hug it
    against the left edge (X home) and centre it front-to-back, kept clear
    of the tower reserve zone. Left-justifying puts a layer shift into the
    X endstop sooner so crash detection can recover; the tight grouping
    keeps Y travel low, and geometry-import centring becomes a no-op."""
    items = [(p.item, *getter(p.item).size[:2]) for p in placements]
    area = sum(w * d for _, w, d in items)
    widest = max(w for _, w, d in items)
    target_w = max(widest, area ** 0.5 * 1.05)
    beds = pack_plates(items, target_w, plate_d, spacing=spacing,
                       margin=0.0, reserve=None)
    block = beds[0] if len(beds) == 1 else placements

    def size(p):
        return getter(p.item).size

    x0 = min(p.x for p in block)
    x1 = max(p.x + size(p)[0] for p in block)
    y0 = min(p.y for p in block)
    y1 = max(p.y + size(p)[1] for p in block)
    # hug the left edge; centre front-to-back for minimal Y travel
    dx = left_margin - x0
    dy = (plate_d - y0 - y1) / 2
    if reserve:
        rx, ry = reserve
        if x1 + dx > rx and y1 + dy > ry:
            # nudge toward the front so the block clears the tower corner
            dy = ry - y1
    return [(getter(p.item), p.x + dx, p.y + dy) for p in block]


def _layout_paths(args) -> list[Path]:
    paths = [Path(c) for c in args.config or []]
    if args.layouts_dir:
        paths.extend(find_layouts(Path(args.layouts_dir)))
    if not paths:
        default_dir = Path(DEFAULT_LAYOUTS_DIR)
        if default_dir.is_dir():
            paths = find_layouts(default_dir)
        else:
            raise SystemExit(
                "no configs given: use --config <file.yaml> or --layouts-dir <dir> "
                f"(default {DEFAULT_LAYOUTS_DIR} not found)"
            )
    return paths


def _size_pair(text: str, what: str) -> tuple[float, float]:
    try:
        w, d = (float(v) for v in str(text).lower().split("x"))
        return w, d
    except ValueError:
        raise SystemExit(f"bad {what} {text!r} — expected WIDTHxDEPTH, e.g. 250x210")


def _env(name: str) -> str | None:
    """Environment variable, falling back to a .env file in the cwd."""
    val = os.environ.get(name)
    if val is None and Path(".env").is_file():
        for line in Path(".env").read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}=") and not line.startswith("#"):
                val = line.split("=", 1)[1].strip().strip("'\"")
    return val if val else None


def _env_bool(name: str) -> bool | None:
    val = _env(name)
    return None if val is None else val.lower() in ("1", "true", "yes", "on")


def _slicer_config(args, settings: dict, printer: dict | None) -> str | None:
    """Exported PrusaSlicer config to embed: CLI > manifest > env/.env >
    printer preset's slicerConfig > ./slicer-config.ini. Embedding it
    makes plate 3MFs real projects, so positions (and therefore beds)
    survive opening."""
    plate_cfg = settings.get("plate") or {}
    path = (args.slicer_config or settings.get("slicerConfig")
            or plate_cfg.get("slicerConfig") or _env("SLICER_CONFIG")
            or (printer or {}).get("slicerConfig"))
    if path is None and Path("slicer-config.ini").is_file():
        path = "slicer-config.ini"
    if path is None:
        return None
    p = Path(path).expanduser()
    if not p.is_file():
        raise SystemExit(f"slicer config {p} not found")
    return p.read_text()


def _bed_shape_size(config_text: str) -> tuple[float, float] | None:
    """Plate size from a config's rectangular bed_shape, if present."""
    for line in config_text.splitlines():
        if line.startswith("bed_shape"):
            try:
                pts = [tuple(float(v) for v in pt.split("x"))
                       for pt in line.split("=", 1)[1].strip().split(",")]
                xs = [pt[0] for pt in pts]
                ys = [pt[1] for pt in pts]
                return max(xs) - min(xs), max(ys) - min(ys)
            except ValueError:
                return None
    return None


def _skirt_brim_allowance(config_text: str | None) -> float:
    """Outward clearance the slicer's skirt + brim need around each part,
    read from an embedded config (brim_width/brim_type, skirt_distance,
    skirts, extrusion width)."""
    if not config_text:
        return 0.0
    vals: dict[str, str] = {}
    for line in config_text.splitlines():
        for key in ("brim_width", "brim_type", "skirt_distance", "skirts",
                    "extrusion_width", "skirt_height"):
            if line.startswith(key + " ="):
                vals[key] = line.split("=", 1)[1].strip()

    def num(k, d=0.0):
        try:
            return float(vals.get(k, d))
        except ValueError:
            return d

    brim = num("brim_width") if vals.get("brim_type", "no_brim") not in ("no_brim", "") else 0.0
    ew = num("extrusion_width") or 0.45
    skirt = 0.0
    if int(num("skirts")) > 0 and int(num("skirt_height", 1)) > 0:
        skirt = num("skirt_distance", 2.0) + int(num("skirts")) * ew
    return round(brim + skirt, 2)


def _describe(spec: ContainerSpec) -> str:
    label = spec.label or f"({spec.type})"
    return (f'{spec.slug:<28} {spec.gx}x{spec.gy}  '
            f'{label.replace(chr(10), " / "):<20} from {", ".join(spec.sources)}')


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build Gridfinity containers from screw-organiser layouts or "
                    "container manifests (sized for the Gridfinity Storage Box by Pred)")
    ap.add_argument("--config", action="append", metavar="FILE",
                    help="layout or container-manifest file (repeatable)")
    ap.add_argument("--layouts-dir", metavar="DIR",
                    help=f"build from every config in DIR (default: {DEFAULT_LAYOUTS_DIR})")
    ap.add_argument("--format", choices=["3mf", "stl"], default="3mf",
                    help="3mf: multi-material (bin/label objects); stl: one combined file")
    ap.add_argument("--height-units", type=int, default=None, metavar="N",
                    help="container height in 7 mm gridfinity units, excluding the "
                         "stacking lip (default 6 = 42 mm, fits the Pred box)")
    ap.add_argument("--magnets", action=argparse.BooleanOptionalAction, default=None,
                    help="magnet holes in the base corners (also: MAGNETS=1 in the "
                         "environment or a .env file)")
    ap.add_argument("--checkers", action=argparse.BooleanOptionalAction, default=None,
                    help="cut the screw checkers (test gauges) on the label shelf "
                         "edge — off by default; also CHECKERS=1 in the environment "
                         "or a .env file")
    ap.add_argument("--counts", action="store_true", default=None,
                    help='append each container\'s "count" to its label')
    ap.add_argument("--symbols", action=argparse.BooleanOptionalAction, default=None,
                    help="add a screw/nut/washer icon to the label, auto-picked from "
                         "the head type (also SYMBOLS=1 in the environment or .env, or "
                         "`symbols: true` / per-box `symbol:` in a manifest)")
    ap.add_argument("--bin-tool", type=int, default=None, metavar="N",
                    help="tool/extruder that prints the bins (default 1)")
    ap.add_argument("--label-tool", type=int, default=None, metavar="N",
                    help="tool/extruder that prints the labels (default 2)")
    ap.add_argument("--text-tool", type=int, default=None, metavar="N",
                    help="tool for plates-style label text (default 3)")
    ap.add_argument("--background-tool", type=int, default=None, metavar="N",
                    help="tool for the label-area background plate "
                         "(default: same as the bin)")
    ap.add_argument("--label-style", choices=["direct", "plates", "pred", "embossed"],
                    default=None,
                    help="direct: text written straight onto the Pred label shelf "
                         "(default); plates (alias pred): swappable printable label "
                         "plates as separate files; embossed: text fused onto the ramp")
    ap.add_argument("--exclude", action="append", metavar="PATTERN",
                    help="skip containers whose label or slug matches (glob patterns "
                         "allowed, repeatable or comma-separated; also `exclude:` "
                         "list in a manifest)")
    ap.add_argument("--list", action="store_true",
                    help="print the derived container list and exit without building")
    ap.add_argument("--plates", action="store_true",
                    help="pack the containers onto build plates instead of one file each")
    ap.add_argument("--plate-size", metavar="WxD",
                    help=f"build plate size in mm (default {DEFAULT_PLATE[0]:g}x{DEFAULT_PLATE[1]:g})")
    ap.add_argument("--printer", metavar="NAME",
                    help="printer preset (plate size + tower type) from printers.yaml; "
                         "see --list-printers")
    ap.add_argument("--list-printers", action="store_true",
                    help="list the known printer presets and exit")
    ap.add_argument("--tower", choices=["purge", "prime", "none"], default=None,
                    help="waste-tower reservation on each plate: purge (wipe tower, "
                         "60x60), prime (smaller, 35x35) or none — printer presets "
                         "set this automatically")
    ap.add_argument("--purge-tower", action=argparse.BooleanOptionalAction, default=None,
                    help="shorthand for --tower purge / --tower none")
    ap.add_argument("--purge-tower-size", metavar="WxD",
                    help=f"purge tower reservation in mm "
                         f"(default {DEFAULT_PURGE_TOWER[0]:g}x{DEFAULT_PURGE_TOWER[1]:g})")
    ap.add_argument("--spacing", type=float, default=None, metavar="MM",
                    help=f"gap between containers on a plate (default {DEFAULT_SPACING:g})")
    ap.add_argument("--brim", type=float, default=None, metavar="MM",
                    help="extra clearance around parts for the slicer's skirt + brim "
                         "(keeps them on the bed and out of the tower zone); read from "
                         "an embedded slicer config, or a printer preset's `brim`, when "
                         "not given")
    ap.add_argument("--plates-per-file", type=int, default=None, metavar="N",
                    help="build plates grouped into each 3MF as PrusaSlicer multi-bed "
                         "projects (default 9 with --slicer-config, else 1 — see below)")
    ap.add_argument("--slicer-config", metavar="INI",
                    help="exported PrusaSlicer config (File > Export > Export Config) "
                         "to embed; makes plate files full projects so PrusaSlicer "
                         "keeps the multi-bed arrangement (also: slicerConfig in the "
                         "manifest, SLICER_CONFIG in the environment/.env, or a "
                         "slicer-config.ini in the working directory)")
    ap.add_argument("--force", action="store_true",
                    help="rebuild outputs that already exist")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    if args.list_printers:
        data = load_printers()
        for pname, cfg in sorted(data["printers"].items()):
            plate = cfg.get("plate", {})
            extra = "" if cfg.get("_source") == "built-in" else f"  [{cfg['_source']}]"
            extra += "  +slicer config" if cfg.get("slicerConfig") else ""
            print(f"  {pname:<20} {plate.get('width', '?'):>3} x {plate.get('depth', '?'):<3} mm  "
                  f"tower: {cfg.get('tower', 'none')}{extra}")
        print(f"add your own printers in {global_config_path()} "
              "(or a printers.yaml in this directory)")
        return

    paths = _layout_paths(args)
    catalog, settings = build_catalog(paths)

    patterns = [p_ for arg in (args.exclude or []) for p_ in arg.split(",")]
    patterns += settings.get("exclude") or []
    if patterns:
        from .catalog import slugify

        def excluded(spec: ContainerSpec) -> bool:
            names = {spec.slug, slugify(spec.label) if spec.label else spec.type}
            return any(
                fnmatch.fnmatch(n, slugify(pat) if "*" not in pat and "?" not in pat
                                else pat.lower())
                for pat in patterns for n in names
            )

        kept = [spec for spec in catalog if not excluded(spec)]
        if len(kept) != len(catalog):
            print(f"  excluded {len(catalog) - len(kept)} container(s): "
                  + ", ".join(s_.slug for s_ in catalog if s_ not in kept))
        catalog = kept
    print(f"{len(catalog)} containers from {len(paths)} config(s)")

    # CLI > manifest settings > built-in defaults. Settings use the
    # screw-organiser names: labels.showCounts, gridfinity.magnets, testHoles
    height_units = args.height_units or settings.get("heightUnits") or 6
    gf_cfg = settings.get("gridfinity")
    gf_cfg = gf_cfg if isinstance(gf_cfg, dict) else {}
    env_magnets = _env_bool("MAGNETS")
    if args.magnets is not None:
        magnets = args.magnets
    elif env_magnets is not None:
        magnets = env_magnets
    else:
        magnets = bool(settings.get("magnets") or gf_cfg.get("magnets"))
    env_checkers = _env_bool("CHECKERS")
    if args.checkers is not None:
        checkers = args.checkers
    elif env_checkers is not None:
        checkers = env_checkers
    else:
        checkers = bool(settings.get("checkers"))
    env_symbols = _env_bool("SYMBOLS")
    if args.symbols is not None:
        symbols = args.symbols
    elif env_symbols is not None:
        symbols = env_symbols
    else:
        symbols = bool(settings.get("symbols"))
    labels_cfg = dict(settings.get("labels") or {})
    if args.counts or settings.get("counts"):
        labels_cfg["showCounts"] = True
    counts = bool(labels_cfg.get("showCounts"))
    label_style = (args.label_style or labels_cfg.get("style")
                   or settings.get("labelStyle") or "direct")
    make_plates_files = label_style in ("plates", "pred")
    test_cfg = settings.get("testHoles") or {}
    if settings.get("filaments"):
        print("  note: the manifest's `filaments:` section is ignored — filament "
              "state is printer-local; record it with `gridfinity-filaments` and "
              "pick tools with --bin-tool/--label-tool")
    printer_name = args.printer or settings.get("printer") or _env("PRINTER")
    filaments = resolve_filaments(printer_name, args.bin_tool,
                                  args.label_tool, args.text_tool,
                                  args.background_tool)

    # Pred storage-box front labels: any `boxLabels:` list in the configs
    # is built as flat two-colour labels (plate -> bin tool, text -> label
    # tool), regardless of --plates. Text spans 0.2 mm above the bed to
    # 0.2 mm above the label top.
    out_dir = Path(args.out)
    box_built = 0
    for path in paths:
        doc = load_source(path)
        entries = doc.get("boxLabels") or []
        if entries:
            from .boxlabel import build_box_label
        for entry in entries:
            if isinstance(entry, str):
                entry = {"text": entry}
            # per-entry style keys (capHeight, subScale, capHeights, lineGap,
            # font, bold...) may sit at the entry top level or under `labels`
            entry_style = {k: v for k, v in entry.items()
                           if k not in ("text", "width", "labels")}
            container = build_box_label(entry.get("text", ""),
                                        int(entry.get("width", 5)),
                                        {**(labels_cfg or {}), **entry_style,
                                         **entry.get("labels", {})})
            box_path = out_dir / f"{container.name}.{args.format}"
            if box_path.exists() and not args.force:
                print(f"  exists, skipping {box_path}")
                continue
            export(container, args.format, box_path, filaments)
            w, d, h = container.size
            print(f"  wrote {box_path} (box label, {w:g} x {d:g} x {h:g} mm)")
            box_built += 1
    if box_built:
        print(f"  {box_built} box label(s)")

    for spec in catalog:
        for w in spec.warnings:
            print(f"  warning: {w}")
        if spec.gx > BOX_GRID[0] or spec.gy > BOX_GRID[1]:
            print(f"  warning: {spec.slug} is {spec.gx}x{spec.gy} — larger than the "
                  f"{BOX_GRID[0]}x{BOX_GRID[1]} grid of the Pred storage box")
        if (spec.height_units or height_units) != 6:
            print(f"  note: {spec.slug} is {spec.height_units or height_units} units tall — "
                  "only 6-unit containers are held down by the Pred box lid")

    if args.list:
        for spec in catalog:
            print(f"  {_describe(spec)}")
        return

    out_dir = Path(args.out)
    t0 = time.time()

    built: dict[str, Container] = {}

    def get_container(spec: ContainerSpec) -> Container:
        if spec.slug not in built:
            built[spec.slug] = build_container(
                spec,
                height_units=spec.height_units or height_units,
                magnets=magnets,
                checkers=checkers,
                label_style=label_style,
                labels_cfg=labels_cfg,
                test_cfg=test_cfg,
                symbols=symbols,
            )
        return built[spec.slug]

    def label_text(spec: ContainerSpec) -> str | None:
        label = spec.bin["label"] if "label" in spec.bin else "Misc"
        if spec.type == "open" or not label:
            return None
        text = str(label)
        if counts and spec.bin.get("count") is not None:
            text += f" ({spec.bin['count']})"
        return text

    label_plates: dict[str, LabelPlate] = {}

    def get_label_plate(spec: ContainerSpec) -> LabelPlate | None:
        text = label_text(spec)
        if not make_plates_files or text is None:
            return None
        if spec.slug not in label_plates:
            label_plates[spec.slug] = build_label_plate(
                spec.slug, text, spec.gx, {**LABEL_DEFAULTS, **labels_cfg})
        return label_plates[spec.slug]

    if args.plates:
        plate_cfg = settings.get("plate") or {}
        printer = None
        if printer_name:
            printer = resolve_printer(printer_name)
        slicer_config = _slicer_config(args, settings, printer)
        if slicer_config:
            slicer_config = patch_slicer_config(slicer_config, filaments)

        # plate size: CLI > manifest plate > slicer config bed > printer > default
        cfg_bed = _bed_shape_size(slicer_config) if slicer_config else None
        if args.plate_size:
            plate_w, plate_d = _size_pair(args.plate_size, "--plate-size")
        elif "width" in plate_cfg or "depth" in plate_cfg:
            plate_w = plate_cfg.get("width", DEFAULT_PLATE[0])
            plate_d = plate_cfg.get("depth", DEFAULT_PLATE[1])
        elif cfg_bed:
            plate_w, plate_d = cfg_bed
        elif printer:
            # two-colour builds must stay in the area both nozzles reach
            dual = printer.get("dualPlate")
            if dual:
                plate_w, plate_d = dual["width"], dual["depth"]
                print(f"  note: dual-nozzle printer — packing within the "
                      f"{plate_w:g} x {plate_d:g} mm area both toolheads reach "
                      f"(full plate {printer['plate']['width']:g} x "
                      f"{printer['plate']['depth']:g})")
            else:
                plate_w = printer["plate"]["width"]
                plate_d = printer["plate"]["depth"]
        else:
            plate_w, plate_d = DEFAULT_PLATE
        spacing = args.spacing if args.spacing is not None else plate_cfg.get("spacing", DEFAULT_SPACING)

        # tower type: CLI > manifest (tower / purgeTower) > printer > slicer config
        tower_cfg = plate_cfg.get("purgeTower")
        if args.tower:
            tower_type = args.tower
        elif args.purge_tower is not None:
            tower_type = "purge" if args.purge_tower else "none"
        elif plate_cfg.get("tower"):
            tower_type = plate_cfg["tower"]
        elif tower_cfg is not None:
            tower_type = "purge" if tower_cfg else "none"
        elif printer:
            tower_type = printer.get("tower", "none")
        elif slicer_config and any(line.split("=", 1)[1].strip() == "1"
                                   for line in slicer_config.splitlines()
                                   if line.startswith("wipe_tower =")):
            tower_type = "purge"
        else:
            tower_type = "none"
        tower = None
        if tower_type != "none":
            type_size = tower_size(tower_type)
            if args.purge_tower_size:
                tower = _size_pair(args.purge_tower_size, "--purge-tower-size")
            elif isinstance(tower_cfg, dict) and not args.tower:
                # the manifest size belongs to the manifest's own tower
                # choice — an explicit --tower uses the type's default
                tower = (tower_cfg.get("width", DEFAULT_PURGE_TOWER[0]),
                         tower_cfg.get("depth", DEFAULT_PURGE_TOWER[1]))
            elif printer and printer.get("towerSize") and not args.tower:
                tower = (printer["towerSize"]["width"], printer["towerSize"]["depth"])
            elif type_size:
                tower = (type_size["width"], type_size["depth"])
            else:
                tower = DEFAULT_PURGE_TOWER

        # Skirt + brim clearance: CLI > manifest plate.brim > slicer config
        # > printer preset. Pads the edge margin and the tower zone so the
        # skirt/brim stays on the bed and out of the tower.
        if args.brim is not None:
            brim = args.brim
        elif plate_cfg.get("brim") is not None:
            brim = float(plate_cfg["brim"])
        elif slicer_config:
            brim = _skirt_brim_allowance(slicer_config)
        elif printer and printer.get("brim") is not None:
            brim = float(printer["brim"])
        else:
            brim = 0.0
        edge_margin = DEFAULT_MARGIN + brim

        # Reservation zone for the tower. With an embedded slicer config we
        # position the tower into the rear-right corner ourselves; without
        # one the tower sits wherever the slicer parks it by default, so
        # anchor the zone at the printer's known default tower position.
        reserve = None
        tower_at = None
        if tower:
            reserve = (plate_w - tower[0] - spacing, plate_d - tower[1] - spacing)
            if not slicer_config and printer and printer.get("towerPosition"):
                pos = printer["towerPosition"]
                if pos["x"] < plate_w - 10 and pos["y"] < plate_d - 10:
                    reserve = (min(reserve[0], pos["x"] - spacing),
                               min(reserve[1], pos["y"] - spacing))
                    tower_at = (pos["x"], pos["y"])
            reserve = (reserve[0] - brim, reserve[1] - brim)  # keep brim off the tower
        try:
            plates = pack_plates([(s_, *s_.footprint) for s_ in catalog],
                                 plate_w, plate_d, spacing=spacing,
                                 margin=edge_margin, reserve=reserve)
        except ValueError as e:
            raise SystemExit(f"error: {e}")

        name = settings.get("name") or (Path(paths[0]).stem if len(paths) == 1 else "containers")
        # Multi-bed grouping only works when the 3MF is a full PrusaSlicer
        # project (embedded config); a config-less 3MF is imported as
        # geometry and re-centred, so fall back to one bed per file.
        if args.plates_per_file:
            per_file = args.plates_per_file
        elif plate_cfg.get("platesPerFile"):
            per_file = plate_cfg["platesPerFile"]
        elif slicer_config:
            per_file = 9
        else:
            per_file = 1
        if per_file > 1 and not slicer_config:
            # without an embedded config PrusaSlicer imports as geometry
            # and re-centres — multi-bed files would land off the plate
            per_file = 1
            print("  note: no slicer config — writing one bed per 3MF so plates "
                  "survive geometry import; embed your exported PrusaSlicer "
                  "config (--slicer-config) to group up to 9 beds per file")
        # PrusaSlicer's multi-bed layout: beds along X, spaced by the
        # legacy project gap of 2/10 of the bed width
        bed_pitch = plate_w * 1.2
        tower_msg = ""
        if tower and tower_at:
            tower_msg = (f", {tower_type} tower zone reserved from "
                         f"({tower_at[0]:g}, {tower_at[1]:g}) to the rear-right "
                         "(the slicer's default tower spot)")
        elif tower:
            tower_msg = f", {tower_type} tower {tower[0]:g} x {tower[1]:g} mm reserved rear-right"
        if brim:
            tower_msg += f", {brim:g} mm skirt/brim clearance"
        print(f"{len(plates)} plate(s) of {plate_w:g} x {plate_d:g} mm, "
              f"up to {per_file} per 3MF{tower_msg}")

        def write_plate_files(all_plates, getter, exporter, suffix, what):
            files = [all_plates[i:i + per_file]
                     for i in range(0, len(all_plates), per_file)]
            for fi, group in enumerate(files, 1):
                out_path = out_dir / f"{name}-{suffix}-{fi:02d}.{args.format}"
                if out_path.exists() and not args.force:
                    print(f"  exists, skipping {out_path}")
                    continue
                t1 = time.time()
                if slicer_config is None and len(group) == 1:
                    # No embedded config: geometry import centres the parts
                    # on the bed anyway, so pack them into a compact block
                    # and centre it ourselves (clearing the tower zone) —
                    # tight grouping, minimal travel, no anchor tabs.
                    placed = _compact_centered(group[0], getter, plate_w,
                                               plate_d, spacing, reserve,
                                               left_margin=edge_margin)
                else:
                    placed = [
                        (getter(p.item), p.x + k * bed_pitch, p.y)
                        for k, placements in enumerate(group)
                        for p in placements
                    ]
                towers = None
                if tower and slicer_config:
                    towers = [(k, plate_w - tower[0] - 2, plate_d - tower[1] - 2)
                              for k in range(len(group))]
                exporter(placed, args.format, out_path, filaments,
                         slicer_config=slicer_config, wipe_towers=towers)
                kb = out_path.stat().st_size / 1024
                print(f"  wrote {out_path} ({len(group)} beds, {len(placed)} {what}, "
                      f"{kb:.0f} kB, {time.time() - t1:.1f} s)")

        write_plate_files(plates, get_container, export_plate, "plates", "containers")

        # the swappable labels print flat on their own plate(s)
        with_labels = [s_ for s_ in catalog if get_label_plate(s_) is not None]
        if with_labels:
            label_items = [
                (s_, get_label_plate(s_).size[0], get_label_plate(s_).size[1])
                for s_ in with_labels
            ]
            label_plates_packed = pack_plates(label_items, plate_w, plate_d,
                                              spacing=2.0, margin=edge_margin,
                                              reserve=reserve)
            write_plate_files(label_plates_packed, get_label_plate, export_labels,
                              "labels-plates", "labels")
        print(f"done in {time.time() - t0:.1f} s")
        return

    built_n = skipped = 0
    for spec in catalog:
        out_path = out_dir / f"{spec.slug}.{args.format}"
        if out_path.exists() and not args.force:
            print(f"  exists, skipping {out_path}")
            skipped += 1
        else:
            t1 = time.time()
            container = get_container(spec)
            export(container, args.format, out_path, filaments)
            w, d, h = container.size
            kb = out_path.stat().st_size / 1024
            print(f"  wrote {out_path} ({spec.gx}x{spec.gy}, {w:g} x {d:g} x {h:g} mm, "
                  f"{kb:.0f} kB, {time.time() - t1:.1f} s)")
            built_n += 1

        lp = get_label_plate(spec)
        if lp is not None:
            label_path = out_dir / "labels" / f"{spec.slug}-label.{args.format}"
            if label_path.exists() and not args.force:
                print(f"  exists, skipping {label_path}")
                skipped += 1
                continue
            export_labels([(lp, 0.0, 0.0)], args.format, label_path, filaments)
            print(f"  wrote {label_path} ({lp.size[0]:g} x {lp.size[1]:g} mm)")
            built_n += 1

    print(f"done: {built_n} built, {skipped} already existed ({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
