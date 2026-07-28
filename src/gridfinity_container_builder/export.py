"""STL and 3MF export for containers.

3MF output is written as a PrusaSlicer project file (the structure a
"Save Project" produces): every container is one object with its bin and
label as separate volumes, extruders pre-assigned (bin -> 1, label -> 2),
and build items carrying the position transforms. Positions survive a
project load — which is what makes multi-bed plate files work; a plain
geometry 3MF gets re-centred onto a single plate on import.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from build123d import Compound, Part, export_stl

from .container import Container
from .filaments import DEFAULT_TOOLS

_TOL = 0.01
_ANG_TOL = 0.3

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


def _merged(parts: list[Part]) -> Part | Compound:
    return parts[0] if len(parts) == 1 else Compound(children=list(parts))


def _mesh(shape) -> tuple[list, list]:
    """Tessellate a shape into one welded vertex/triangle mesh."""
    verts, tris = shape.tessellate(_TOL, _ANG_TOL)
    index: dict[tuple, int] = {}
    remap: list[int] = []
    out_verts: list[tuple] = []
    for v in verts:
        key = (round(v.X, 4), round(v.Y, 4), round(v.Z, 4))
        if key not in index:
            index[key] = len(out_verts)
            out_verts.append(key)
        remap.append(index[key])
    out_tris = []
    for a, b, c in tris:
        a, b, c = remap[a], remap[b], remap[c]
        if a != b and b != c and c != a:
            out_tris.append((a, b, c))
    return out_verts, out_tris


def _write_project_3mf(path: Path, objects: list[dict], title: str,
                       slicer_config: str | None = None,
                       wipe_towers: list[tuple[int, float, float]] | None = None) -> None:
    """PrusaSlicer project 3MF.

    objects: [{name, volumes: [(vol_name, extruder, shape), ...], x, y}]
    Each object becomes one mesh whose volumes are triangle ranges in
    Metadata/Slic3r_PE_model.config, positioned by its item transform.

    slicer_config is the text of an exported PrusaSlicer config
    (File -> Export -> Export Config); embedding it is what makes
    PrusaSlicer treat the file as a full project and keep the positions —
    without it, 3MFs are imported as geometry and re-centred onto one
    plate. wipe_towers places the wipe tower per bed: (bed_idx, x, y).
    """
    model = [
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n'
        ' <metadata name="slic3rpe:Version3mf">1</metadata>\n'
        f" <metadata name=\"Title\">{title}</metadata>\n"
        ' <metadata name="Application">gridfinity-container-builder</metadata>\n'
        " <resources>\n"
    ]
    config = ['<?xml version="1.0" encoding="UTF-8"?>\n<config>\n']
    items = []

    for i, obj in enumerate(objects):
        oid = i + 1
        all_verts: list[tuple] = []
        all_tris: list[tuple] = []
        ranges = []
        for vol_name, extruder, shape in obj["volumes"]:
            verts, tris = _mesh(shape)
            off = len(all_verts)
            first = len(all_tris)
            all_verts.extend(verts)
            all_tris.extend((a + off, b + off, c + off) for a, b, c in tris)
            ranges.append((vol_name, extruder, first, len(all_tris) - 1))

        model.append(f'  <object id="{oid}" type="model">\n   <mesh>\n    <vertices>\n')
        model.extend(f'     <vertex x="{v[0]:g}" y="{v[1]:g}" z="{v[2]:g}"/>\n'
                     for v in all_verts)
        model.append("    </vertices>\n    <triangles>\n")
        model.extend(f'     <triangle v1="{t[0]}" v2="{t[1]}" v3="{t[2]}"/>\n'
                     for t in all_tris)
        model.append("    </triangles>\n   </mesh>\n  </object>\n")
        items.append(
            f'  <item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 '
            f'{obj["x"]:g} {obj["y"]:g} 0" printable="1"/>\n'
        )

        config.append(f' <object id="{oid}" instances_count="1">\n'
                      f'  <metadata type="object" key="name" value="{obj["name"]}"/>\n')
        for vol_name, extruder, first, last in ranges:
            config.append(
                f'  <volume firstid="{first}" lastid="{last}">\n'
                f'   <metadata type="volume" key="name" value="{vol_name}"/>\n'
                f'   <metadata type="volume" key="volume_type" value="ModelPart"/>\n'
                f'   <metadata type="volume" key="extruder" value="{extruder}"/>\n'
                f'   <metadata type="volume" key="matrix" '
                f'value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                "   <mesh edges_fixed=\"0\" degenerate_facets=\"0\" facets_removed=\"0\" "
                "facets_reversed=\"0\" backwards_edges=\"0\"/>\n"
                "  </volume>\n"
            )
        config.append(" </object>\n")

    model.append(" </resources>\n <build>\n")
    model.extend(items)
    model.append(" </build>\n</model>\n")
    config.append("</config>\n")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", "".join(model))
        z.writestr("Metadata/Slic3r_PE_model.config", "".join(config))
        if slicer_config:
            z.writestr("Metadata/Slic3r_PE.config", slicer_config)
        if wipe_towers:
            lines = ['<?xml version="1.0" encoding="utf-8"?>\n']
            lines += [f'<wipe_tower_information bed_idx="{b}" position_x="{x:g}" '
                      f'position_y="{y:g}" rotation_deg="0"/>\n'
                      for b, x, y in wipe_towers]
            z.writestr("Metadata/Prusa_Slicer_wipe_tower_information.xml", "".join(lines))


def _tool(filaments: dict | None, slot: str) -> int:
    if filaments and slot in filaments:
        return filaments[slot]["tool"]
    default = DEFAULT_TOOLS[slot]
    if default is None:  # background follows the bin
        return _tool(filaments, "bin")
    return default


def _container_volumes(container: Container, filaments: dict | None = None) -> list[tuple]:
    volumes = [("bin", _tool(filaments, "bin"), container.body)]
    if container.background is not None:
        volumes.append(("background", _tool(filaments, "background"),
                        container.background))
    if container.labels:
        volumes.append(("label", _tool(filaments, "label"), _merged(container.labels)))
    return volumes


def export(container: Container, fmt: str, out_path: Path,
           filaments: dict | None = None) -> Path:
    """STL -> one combined single-colour file; 3MF -> PrusaSlicer project
    with bin and label volumes on their filament slots' tools."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "stl":
        parts = [container.body, *container.labels]
        if container.background is not None:
            parts.append(container.background)
        export_stl(_merged(parts), str(out_path),
                   tolerance=_TOL, angular_tolerance=_ANG_TOL)
        return out_path

    _write_project_3mf(out_path, [{
        "name": container.name,
        "volumes": _container_volumes(container, filaments),
        "x": 0.0, "y": 0.0,
    }], container.name)
    return out_path


def export_labels(placed: list, fmt: str, out_path: Path,
                  filaments: dict | None = None,
                  slicer_config: str | None = None,
                  wipe_towers: list[tuple[int, float, float]] | None = None) -> Path:
    """Pred label plates: each plate an object with plate/text volumes at
    its packed spot (label plates are modelled centred on the origin)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "stl":
        from build123d import Pos

        parts = []
        for lp, x, y in placed:
            shift = Pos(x + lp.size[0] / 2, y + lp.size[1] / 2, 0)
            parts.append(shift * lp.plate)
            if lp.text is not None:
                parts.append(shift * lp.text)
        export_stl(_merged(parts), str(out_path),
                   tolerance=_TOL, angular_tolerance=_ANG_TOL)
        return out_path

    objects = []
    for lp, x, y in placed:
        volumes = [("plate", _tool(filaments, "label"), lp.plate)]
        if lp.text is not None:
            volumes.append(("text", _tool(filaments, "text"), lp.text))
        objects.append({
            "name": lp.name,
            "volumes": volumes,
            "x": x + lp.size[0] / 2, "y": y + lp.size[1] / 2,
        })
    _write_project_3mf(out_path, objects, out_path.stem,
                       slicer_config=slicer_config, wipe_towers=wipe_towers)
    return out_path


def export_plate(placed: list[tuple[Container, float, float]], fmt: str,
                 out_path: Path, filaments: dict | None = None,
                 slicer_config: str | None = None,
                 wipe_towers: list[tuple[int, float, float]] | None = None) -> Path:
    """One or more build plates in a single file: every container is its
    own object placed by transform, so a PrusaSlicer project load keeps
    the arrangement and assigns the beds."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "stl":
        from build123d import Pos

        parts = []
        for c, x, y in placed:
            parts.append(Pos(x, y, 0) * c.body)
            if c.background is not None:
                parts.append(Pos(x, y, 0) * c.background)
            parts.extend(Pos(x, y, 0) * lab for lab in c.labels)
        export_stl(_merged(parts), str(out_path),
                   tolerance=_TOL, angular_tolerance=_ANG_TOL)
        return out_path

    objects = [{
        "name": c.name,
        "volumes": _container_volumes(c, filaments),
        "x": x, "y": y,
    } for c, x, y in placed]
    _write_project_3mf(out_path, objects, out_path.stem,
                       slicer_config=slicer_config, wipe_towers=wipe_towers)
    return out_path
