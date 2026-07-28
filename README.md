# Gridfinity Container Builder

Builds labelled [Gridfinity](https://gridfinity.xyz/) containers from
container manifests or
[screw-organiser](https://github.com/gheydon/screw-organiser) layout files,
using Python and [build123d](https://build123d.readthedocs.io/) — the same
build method as the organiser itself. Every container gets the familiar
scoop front, Pred's swappable printable label holder with a screw test
gauge along the label's leading edge, auto-sizes so its contents fit, and
is dimensioned to fit the
[Gridfinity Storage Box by Pred](https://www.printables.com/model/543553-gridfinity-storage-box-by-pred-now-parametric).

## Quick start

```sh
uv sync

# list what would be built from every layout in ../screw-organiser/layouts
uv run gridfinity-container-builder --list

# build them all as multi-material 3MFs -> out/
uv run gridfinity-container-builder

# your own container list (see examples/containers.yaml)
uv run gridfinity-container-builder --config examples/containers.yaml

# pack everything onto 250x210 build plates, purge tower space reserved
uv run gridfinity-container-builder --config examples/containers.yaml --plates --purge-tower
```

Or via make: `make` (build all), `make list`, `make configs`,
`make plates`, `make stl`, `make force`, `make clean`. Point elsewhere
with `LAYOUTS_DIR=path/to/layouts`, pick a printer preset with
`PRINTER=prusa-core-one make plates`, and toggle magnets with
`MAGNETS=1 make` (also read from `.env`).

**Existing files are never overwritten**: before writing, the builder
checks whether the output file already exists and skips it
(`exists, skipping out/m3x10-2x1.3mf`). A re-run after adding a new layout
only builds the containers that are actually new. Use `--force` to rebuild.

## Container manifests

The straightforward way to say what you want built: a YAML file listing
the containers — see [examples/containers.yaml](examples/containers.yaml).
`gridfinity-config-builder` (or `make configs`) generates these from your
screw-organiser layouts — one editable manifest per layout in `configs/`,
skipping files that already exist so your edits survive re-runs:

```sh
uv run gridfinity-config-builder --layouts-dir ../screw-organiser/layouts --printer prusa-core-one
uv run gridfinity-container-builder --config configs/prusa-mmu3-upgrade.yaml
```

Settings use the **same names as screw-organiser layouts** wherever an
equivalent exists — `labels`, `testHoles`, `colors`, `gridfinity`,
`defaults` — so knowledge (and snippets) transfer directly:

```yaml
name: my-containers
heightUnits: 6
labels: { style: pred, showCounts: false, capHeight: 3.2, font: Arial }
gridfinity: { magnets: true }
testHoles: { clearance: 0.4, rim: 1.2 }
plate: { width: 250, depth: 210, purgeTower: true, platesPerFile: 9 }
overrides:                     # resize any container, wherever it came from
  M3x10: 2x2                   # plenty of stock -> bigger bin
layouts:                       # optionally pull whole layouts in too
  - ../../screw-organiser/layouts/prusa-mmu3-upgrade.yaml
containers:
  - { label: M3x8, count: 40 }           # 1x1, gauge with cap-head pocket
  - { label: M3x40 }                     # auto-sizes to 2x1
  - { label: M3x12 BHCS }                # button head inferred from label
  - { label: M3n, test: false }          # nuts: no gauge
  - { label: "625\nbearings", size: 2x1 }  # explicit size wins
```

When building straight from layout files, their `labels`, `testHoles` and
`colors` sections are honoured the same way (first file wins).

- **Auto-sizing**: the item length is parsed from the `test` spec or the
  label (`M3x40` → 40 mm, `5x120 shaft` with an explicit test → 120 mm)
  and the container grows to the smallest width whose interior fits the
  item lying flat — M3x40 becomes 2x1, a 120 mm shaft 4x1. `size: WxD`
  overrides (with a warning if the item then can't fit).
- **Screw checker** (opt-in: `--checkers`, `CHECKERS=1` in the
  environment/`.env`, or `checkers: true` in a manifest): any container
  whose label is a full screw size (`M3x8`, `M2.5x10` — nuts and washers
  like `M3n` get none) gets the organiser's test gauge cut along the
  leading edge of the label shelf — head pocket plus thread channel, so head type, diameter and
  length check in one go. Head pockets follow the label (`BHCS`, `FHCS`)
  or an explicit `head: cap|button|flush|none`; `test:` takes all the
  organiser's forms (`true`, `M3x16`, `3.9`, full dicts).
- **Overrides**: `overrides:` resizes or adjusts containers by label (or
  slug), including ones imported from layouts — `M3x10: 2x2` when a 1x1
  won't hold your stock. A dict value can also change `count`, `test`,
  `head`, `type` or `heightUnits`.

## Labels: Pred's label shelf

Containers carry the label area of the
[Gridfinity Bin with Printable Label by Pred](https://www.printables.com/model/592545-gridfinity-bin-with-printable-label-by-pred-parame)
— every dimension measured from Pred's own bin model: a **flat shelf at
the top back** whose recessed label area sits 1.0 mm below the wall top,
12.0 mm deep, reaching to 1.6 mm from the outer faces at the sides, the
stacking lip cleared above it, **45° gussets** (0.8 mm, every ~10.5 mm)
supporting it from below with the space underneath staying usable bin
volume. The screw checker runs along the shelf's front edge — the
leading edge of the label — with the channel's front open over the
cavity so the screw rolls out, and the shelf thickens automatically
under wide gauges.

Three label styles (`labels: { style: … }` or `--label-style`):

- **`direct`** (default): the label is built in place as Pred's plate
  stack — a 0.8 mm `background` plate fills the recessed area (its own
  filament slot via `--background-tool`, defaulting to the bin's, so by
  default it just looks like the bin) with the text raised on top,
  finishing flush with the wall top. Each container 3MF carries three
  volumes, `bin`, `background` and `label`; no separate label files.
- **`plates`** (alias `pred`): swappable printed labels instead — the
  shelf gains Pred's two 1.0 mm retaining tabs, and each container gets
  a matching plate in Pred's exact outline (via
  [gflabel](https://github.com/ndevenish/gflabel)'s PredBase, BSD:
  gx·42 − 4.2 mm wide, 11.5 mm tall, 0.8 mm thick, tabbed ends) written
  to `out/labels/<slug>-label.3mf`, or packed onto
  `<name>-labels-plates-NN.3mf` sheets in `--plates` mode. Pred's own
  labels fit these containers and vice versa.
- **`embossed`**: the original screw-organiser ramp with fused text.

## How layouts map to containers

The layouts are the screw-organiser YAML files, unchanged — this project
reads them directly, so one set of configurations drives both the trays
and the containers.

- Every entry in `rows[].bins[]` becomes one container. A bin's `units`
  (width) maps 1:1 to Gridfinity X units and its row's `units` (depth) to
  Y units, so `{ units: 2, label: M3x10 }` in a 1-deep row becomes a 2x1
  container (83.5 x 41.5 mm).
- The `label` is embossed on the back ramp exactly as on the tray,
  including two-line `\n` labels. Unlabelled ramped bins become **Misc**;
  `open` bins have no ramp or label.
- `test` gauges carry over: the head pocket + thread channel is cut along
  the ramp crest, same rules as the organiser (`test: true`, `test: M3x16`,
  explicit dicts, `head:` types).
- Auto-sizing applies here too, but only ever grows: a layout bin too
  narrow for its item's parsed length is widened (with a note); layout
  widths are otherwise kept as authored.
- The same screw in several layouts (same label, size and geometry) is
  built **once**; the container records all its source layouts and — with
  `--counts` — shows the largest count among them. Layouts that define the
  same container differently produce a warning and the first definition
  wins.
- `example-*` layouts are skipped in directory mode, matching the
  screw-organiser Makefile convention.

## Fit: the Pred storage box

The box hides a 5x4 Gridfinity baseplate in a 230 x 188 x 55 mm case whose
lid carries bin bottom profiles, locking full-height bins in place.
Containers are therefore built as standard spec Gridfinity bins:

- 42 mm grid, 41.5 mm footprint per unit, stacking lip on top, optional
  corner magnet holes (6.5 x 2.4 mm) via `--magnets`/`--no-magnets`,
  `MAGNETS=1` in the environment or a `.env` file, or
  `gridfinity: { magnets: true }` in the config (CLI wins, then env,
  then config);
- **6 gridfinity height units = 42 mm** overall excluding the lip
  (`--height-units` to change); the lid accommodates the ~4.4 mm lip, so a
  6-unit container is held snug with nothing spilling;
- anything larger than 5x4 gets a doesn't-fit warning (it still builds).

Interior geometry matches the organiser's gridfinity mode: 2.6 mm walls
behind the stacking lip, 2 mm floor above the base, and the interior
trimmed 0.35 mm below the wall top so stacked feet and the lid profiles
seat fully.

## Output

`--format 3mf` (default) writes PrusaSlicer-project multi-material files
(see below); `--format stl` writes combined single-colour files.
Individual files are named after the container: `m3x10-2x1.3mf`,
`fan-m3x14-16b-1x1.3mf`, `misc-1x1.3mf`, ...

### Printer presets

Printers are a **global lookup**, merged from three levels (later wins
by name):

1. [printers.yaml](printers.yaml) in the project root (the packaged copy
   of the same file) — ~35 common printers: Prusa, Bambu, Voron,
   Creality, Sovol, Qidi, Elegoo, RatRig, ...,
2. `~/.config/gridfinity-container-builder/printers.yaml` — **your**
   machines, shared by every project,
3. a `printers.yaml` in the working directory — per-project overrides.

Select one with `--printer`, `printer:` in a manifest, or set your
default once with `PRINTER=prusa-mk3s` in the environment or `.env`.

Each entry has the usable plate size and the waste-tower type its
multi-material system puts on the plate — `purge` (wipe tower, Prusa
MMU3), `prime` (small tower, Prusa XL toolchanger) or `none` (Bambu's
AMS purges to the waste chute; the Prusa INDX toolchanger for the Core
One swaps whole toolheads) — and optionally `slicerConfig: my.ini`
pointing at your exported PrusaSlicer config, so one `--printer
my-mk3s-mmu3` (or `printer:` in a manifest) brings the plate size, the
tower reservation *and* multi-bed project files in a single switch.
`--list-printers` shows the merged table and marks non-built-in entries;
explicit `--plate-size`/`--purge-tower`/`--slicer-config` flags always
win.

### PrusaSlicer project output

3MFs are written as **PrusaSlicer project files** (`Slic3r_PE_model.config`
and all): every container is one object with its `bin` and `label` as
separate volumes, pre-assigned to their filament slots' tools — open the
file (as a project, not import-geometry) and the filaments are already
mapped, no "multiple parts" questions.

Which filament sits in which tool is **printer state, not model
config** — it lives in a local `filaments.yaml` (working-directory copy
wins, else `~/.config/gridfinity-container-builder/filaments.yaml`;
gitignored), keyed per printer and maintained with the
`gridfinity-filaments` command:

```sh
gridfinity-filaments                   # interactive text interface
gridfinity-filaments --list
gridfinity-filaments --printer prusa-mk3s --tool 3 --color grey --material PLA
gridfinity-filaments --printer prusa-mk3s --clear-tool 4
```

At build time pick the tools with `--bin-tool N` / `--label-tool N`
(and `--text-tool` for plates-style label text; defaults 1/2/3). The
tools become the per-volume extruder assignments, and each tool's
recorded colour/material (HTML names or #RRGGBB) is patched into the
embedded slicer config's `filament_colour`/`filament_type` slots so the
project opens showing them — the patch sets colour and type, not
temperatures, so keep matching filament presets in those slots. Tools
with nothing recorded leave your profile untouched. This is also what makes multi-bed plate
files possible: a plain geometry 3MF gets re-centred onto one plate on
import, while a project load keeps every position.

### Build plates

`--plates` packs the whole catalog onto build plates instead of writing
one file per container, with a 4 mm gap between parts (`--spacing`).
More beds than fit one file split into `<name>-plates-01.3mf`, `-02`,
...; the exists-check applies per file.

**Multi-bed files need your slicer config.** PrusaSlicer only keeps
object positions when a 3MF is a full project — one that embeds print
settings. Export yours once (File > Export > Export Config) and pass it
via `--slicer-config my.ini`, `slicerConfig:` in the manifest,
`SLICER_CONFIG` in the environment/`.env`, or a `slicer-config.ini` in
the working directory. With a config embedded, each 3MF groups up to 9
beds (PrusaSlicer's maximum; `--plates-per-file` / `plate:
{ platesPerFile }`) at PrusaSlicer's bed pitch, the wipe tower is placed
into the reserved corner of every bed, the plate size is read from the
config's `bed_shape`, and the purge tower switches on when the config
has `wipe_tower = 1`. Without a config, the builder writes **one bed per
file**, anchors the tower clearance at the slicer's default tower
position (`towerPosition` in the printer preset — PrusaSlicer parks it
at 180, 140), and adds two one-layer **anchor tabs** at opposite corners
that pin the arrangement's bounding box to the full plate — geometry
import then keeps every position, tower clearance included. Peel the
tabs off the print or delete them in the slicer.

- `--plate-size 250x210` sets your printer's usable bed (or
  `plate: { width, depth }` in the manifest).
- `--tower purge|prime|none` (or `plate: { tower: … }`) keeps a
  rear-right rectangle of **every** bed clear for the slicer's waste
  tower — `purge` reserves 60x60 mm (MMU wipe tower), `prime` a smaller
  35x35 mm (toolchangers), `none` nothing. Containers flow around the
  reservation and across as many beds as required. `--purge-tower` /
  `--no-purge-tower` remain as shorthand, `--purge-tower-size` overrides
  the footprint, and the type defaults come from the printer preset.
- Dual-nozzle printers whose toolheads can't both reach the full bed
  (e.g. the Bambu H2D: 300 of 350 mm) declare `dualPlate:` in their
  preset — two-colour builds pack within that area automatically.
- Anything that doesn't fit one bed spills onto the next automatically;
  a container bigger than an empty bed is an error.
- `--exclude "misc,m3n*"` (repeatable, globs allowed, labels or slugs;
  or an `exclude:` list in the manifest) drops selected containers from
  the build — works in individual mode too.
- Pred label plates get their own `<name>-labels-plates-NN.3mf` sheets,
  packed and grouped the same way.

## How it fits together

```
src/gridfinity_container_builder/
  cli.py        CLI: args, catalog, exists-check, build loop, plate mode
  config_builder.py  gridfinity-config-builder: layouts -> manifest YAMLs
  printers.py/.yaml  printer presets (plate size, purge/prime/no tower)
  catalog.py    manifest/layout loading, auto-sizing, dedup + conflicts
  container.py  gridfinity shell (BaseEqual + StackingLip) + interior carve
  interior.py   scoop cavity, labelled ramp, test gauges (from screw-organiser)
  text.py       real-font solid labels (from screw-organiser)
  export.py     STL and colour-tagged multi-object 3MF writers (single + plate)
  plate.py      shelf packing onto plates, purge-tower reservation, overflow
```

The Gridfinity base, walls and stacking lip come from
[gridfinity-build123d](https://github.com/Ruudjhuu/gridfinity_build123d);
the interior is carved with the exact profile code the screw-organiser
uses, so containers and trays built from the same layout look identical
inside.

## Credits

A **remix of Pred's
[Gridfinity Bin with Printable Label (parametric)](https://www.printables.com/model/592545)**
— the container's label shelf, retaining pocket, foot hollows and the box
front-label are all measured from and derived from Pred's models, and the
containers are sized to drop into the
[Gridfinity Storage Box by Pred](https://www.printables.com/model/543553).

- The printable label-plate outline ([labelplate.py](src/gridfinity_container_builder/labelplate.py))
  is ported from [gflabel](https://github.com/ndevenish/gflabel)'s
  PredBase (BSD 3-Clause, © 2024 Nicholas Devenish).
- Optional label icons (`--symbols`) are the SVG set from
  [CNC Kitchen's Gridfinity Label Generator](https://github.com/CNCKitchen/gridfinityLabelGenerator)
  (MIT), bundled under `icons/`.
- Interior scoop / ramp / test-gauge geometry is ported from
  [screw-organiser](https://github.com/gheydon/screw-organiser).
- Built on [gridfinity-build123d](https://github.com/Ruudjhuu/gridfinity_build123d)
  and [build123d](https://build123d.readthedocs.io/).

## License

**CC BY-NC 4.0** (Attribution–NonCommercial) — because it remixes Pred's
CC BY-NC model, this project inherits the same licence. Share and adapt
for non-commercial use with credit to Gordon Heydon and Pred. See
[LICENSE](LICENSE) for full attribution and third-party terms.
