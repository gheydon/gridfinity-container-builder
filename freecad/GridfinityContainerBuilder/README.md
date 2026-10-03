# Gridfinity Container Builder — FreeCAD workbench

A native FreeCAD port of the [gridfinity-container-builder](https://github.com/gheydon/gridfinity-container-builder)
design. It creates **parametric gridfinity container shells** directly with
FreeCAD's own `Part` kernel — no `build123d` / OCP dependency — so it runs
inside FreeCAD's Python with no external services.

> **v1 scope: the external shell.** Grid size, height, stacking lip and a hollow
> interior. The labelled Pred bin and the internal generators (money tray, belt
> tray, tool cradle + blade) are planned for later versions.

## Geometry

The shell reproduces what the build123d generator makes:

- **42 mm** grid pitch, **41.5 mm** bin footprint (0.25 mm clearance/side), **3.75 mm** top corner radius.
- Standard gridfinity **foot** (0.8 / 1.8 / 2.15 mm chamfers) + **2.8 mm platform** → 7.804 mm base.
- Walls to **`HeightUnits × 7 mm`** (excluding the lip).
- **Stacking lip** built as the flared top of the interior cavity, so it mates with real gridfinity bins/baseplates.
- Interior wall **2.6 mm**, floor **2 mm** above the base.

Built from ruled lofts of rounded rectangles — exact for these straight 45°
chamfers and fast (a 2×1 bin builds in ~1 s).

## Install

Clone/symlink this folder into your FreeCAD `Mod` directory, e.g. on macOS:

```bash
ln -s /path/to/gridfinity-container-builder/freecad/GridfinityContainerBuilder \
  "$HOME/Library/Application Support/FreeCAD/v1-1/Mod/GridfinityContainerBuilder"
```

Restart FreeCAD and pick **Gridfinity Container** from the workbench dropdown.

## Use

- Click **New Gridfinity Bin** (toolbar / menu) to add a `GridfinityBin` object.
- Edit it in the data panel:
  - **GridX / GridY** — footprint in grid units
  - **HeightUnits** — height in 7 mm units (≥ 2)
  - **StackingLip** — add the rim lip
  - **Hollow** — empty bin (off = solid block, a base for future internals)

The solid rebuilds on recompute. Export to STEP/STL as usual.

## Scripting

```python
import gridfinity_object
gridfinity_object.create_gridfinity_bin(GridX=3, GridY=2, HeightUnits=6)
```
