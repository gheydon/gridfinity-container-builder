"""Local filament state: what's loaded in which tool, per printer.

This is deliberately NOT part of the model configs — which filament sits
in which slot is printer state, not a property of the containers. It
lives in a local filaments.yaml (a `filaments.yaml` in the working
directory wins, else ~/.config/gridfinity-container-builder/filaments.yaml):

    prusa-mk3s:
      2: { color: black, material: PLA }
      3: { color: grey, material: PLA }

Maintain it with the `gridfinity-filaments` command (flags or the
interactive text interface). At build time `--bin-tool` / `--label-tool`
pick the tools; each tool's colour/material comes from this table and is
patched into the embedded slicer config's filament slots.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .exceptions import SpecError

DEFAULT_TOOLS = {"bin": 1, "label": 2, "text": 3, "background": None}
# background: the label-area plate; None means "same tool as the bin"


def global_filaments_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "gridfinity-container-builder" / "filaments.yaml"


def filaments_path() -> Path:
    local = Path("filaments.yaml")
    return local if local.is_file() else global_filaments_path()


def load_filaments() -> dict:
    """{printer: {tool(int): {color, material}}} from the local file."""
    path = filaments_path()
    if not path.is_file():
        return {}
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return {
        printer: {int(tool): dict(cfg or {}) for tool, cfg in (tools or {}).items()}
        for printer, tools in data.items()
    }


def save_filaments(data: dict, path: Path | None = None) -> Path:
    path = path or filaments_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {p: {int(t): cfg for t, cfg in sorted(tools.items())}
           for p, tools in sorted(data.items())}
    header = ("# What filament is loaded in which tool, per printer.\n"
              "# Maintained by `gridfinity-filaments` — local state, keep out of git.\n")
    path.write_text(header + yaml.safe_dump(out, sort_keys=False))
    return path


def to_hex(color: str) -> str:
    """'#RRGGBB' from a hex value or an HTML/CSS colour name."""
    c = str(color).strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", c):
        return "#" + c.lstrip("#").upper()
    if re.fullmatch(r"#?[0-9a-fA-F]{3}", c):
        return "#" + "".join(ch * 2 for ch in c.lstrip("#")).upper()
    try:
        import webcolors

        return webcolors.name_to_hex(c.lower()).upper()
    except ValueError:
        raise SpecError(f"unknown colour {color!r} — use an HTML colour name "
                        "or #RRGGBB")


def resolve_filaments(printer: str | None, bin_tool: int | None = None,
                      label_tool: int | None = None,
                      text_tool: int | None = None,
                      background_tool: int | None = None) -> dict:
    """Slots {bin/label/text/background: {tool, color, material,
    explicit}} — tools from the build flags (defaults 1/2/3; the label
    background follows the bin's tool unless set), colour and material
    for each tool from the printer's entry in the local filaments.yaml."""
    table = load_filaments().get(printer or "", {})
    slots: dict = {}
    for name, default_tool in DEFAULT_TOOLS.items():
        requested = {"bin": bin_tool, "label": label_tool, "text": text_tool,
                     "background": background_tool}[name]
        if name == "background":
            tool = requested or slots["bin"]["tool"]
        else:
            tool = requested or default_tool
        if tool < 1:
            raise SpecError(f"{name} tool must be >= 1, got {tool}")
        loaded = table.get(tool, {})
        slot = {"tool": tool, "color": None, "material": None, "explicit": set()}
        if loaded.get("color"):
            slot["color"] = to_hex(loaded["color"])
            slot["explicit"].add("color")
        if loaded.get("material"):
            slot["material"] = str(loaded["material"])
            slot["explicit"].add("material")
        slots[name] = slot
    return slots


def patch_slicer_config(text: str, filaments: dict) -> str:
    """Write known colours/materials into the config's filament slots at
    each part's tool position; everything else stays untouched."""
    keys = (("filament_colour", "color"), ("filament_type", "material"))
    if not any(field in slot["explicit"] and slot[field]
               for _, field in keys for slot in filaments.values()):
        return text

    lines = text.splitlines()
    for i, line in enumerate(lines):
        for key, field in keys:
            if not line.startswith(f"{key} ="):
                continue
            values = line.split("=", 1)[1].strip().split(";")
            for slot in filaments.values():
                if field not in slot["explicit"] or not slot[field]:
                    continue
                idx = slot["tool"] - 1
                while len(values) <= idx:
                    values.append(values[-1] if values else "")
                values[idx] = slot[field]
            lines[i] = f"{key} = " + ";".join(values)
    return "\n".join(lines) + "\n"
