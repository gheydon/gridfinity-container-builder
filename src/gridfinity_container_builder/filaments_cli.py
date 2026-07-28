"""gridfinity-filaments: record what filament is loaded in which tool.

  gridfinity-filaments                                  interactive
  gridfinity-filaments --list
  gridfinity-filaments --printer prusa-mk3s --tool 3 --color grey --material PLA
  gridfinity-filaments --printer prusa-mk3s --clear-tool 4

State is per printer and lives in a local filaments.yaml (working
directory copy wins, else the global user file) — print-shop state, not
model config; keep it out of git.
"""

from __future__ import annotations

import argparse

from .filaments import filaments_path, load_filaments, save_filaments, to_hex
from .printers import load_printers


def _show(data: dict) -> None:
    if not data:
        print(f"no filaments recorded yet ({filaments_path()})")
        return
    for printer, tools in sorted(data.items()):
        print(f"{printer}:")
        for tool, cfg in sorted(tools.items()):
            colour = cfg.get("color", "-")
            material = cfg.get("material", "-")
            print(f"  tool {tool}: {colour:<10} {material}")


def _interactive(data: dict) -> dict:
    known = sorted(load_printers()["printers"])
    recorded = sorted(data)
    print("known printers: " + ", ".join(known))
    default = recorded[0] if recorded else None
    prompt = f"printer{f' [{default}]' if default else ''}: "
    printer = input(prompt).strip() or (default or "")
    if not printer:
        raise SystemExit("no printer given")
    if printer not in known:
        print(f"  note: {printer!r} is not a known printer preset — recording anyway")

    tools = data.setdefault(printer, {})
    if tools:
        print("currently loaded:")
        for tool, cfg in sorted(tools.items()):
            print(f"  tool {tool}: {cfg.get('color', '-')} {cfg.get('material', '-')}")
    print("enter a tool number to set it, empty to finish; "
          "'-N' clears tool N (e.g. -4)")
    while True:
        raw = input("tool: ").strip()
        if not raw:
            break
        if raw.startswith("-") and raw[1:].isdigit():
            removed = tools.pop(int(raw[1:]), None)
            print("  cleared" if removed is not None else "  nothing recorded there")
            continue
        if not raw.isdigit() or int(raw) < 1:
            print("  tool numbers are 1, 2, 3, ...")
            continue
        tool = int(raw)
        current = tools.get(tool, {})
        colour = input(f"  colour [{current.get('color', '')}]: ").strip() or current.get("color")
        material = (input(f"  material [{current.get('material', '')}]: ").strip()
                    or current.get("material"))
        entry = {}
        if colour:
            to_hex(colour)  # validate early, keep the friendly name in the file
            entry["color"] = colour
        if material:
            entry["material"] = material
        if entry:
            tools[tool] = entry
            print(f"  tool {tool}: {entry.get('color', '-')} {entry.get('material', '-')}")
    return data


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Record which filament is loaded in which tool, per printer "
                    "(interactive when no options are given)")
    ap.add_argument("--list", action="store_true", help="show the recorded filaments")
    ap.add_argument("--printer", metavar="NAME", help="printer to update")
    ap.add_argument("--tool", type=int, metavar="N", help="tool number to set")
    ap.add_argument("--color", metavar="C", help="colour (HTML name or #RRGGBB)")
    ap.add_argument("--material", metavar="M", help="material (PLA, PETG, ...)")
    ap.add_argument("--clear-tool", type=int, metavar="N",
                    help="forget what's recorded for tool N")
    args = ap.parse_args()

    data = load_filaments()

    if args.list:
        _show(data)
        return

    if args.printer and (args.tool or args.clear_tool):
        tools = data.setdefault(args.printer, {})
        if args.clear_tool:
            tools.pop(args.clear_tool, None)
        if args.tool:
            if not args.color and not args.material:
                raise SystemExit("give --color and/or --material for --tool")
            entry = {}
            if args.color:
                to_hex(args.color)  # validate
                entry["color"] = args.color
            if args.material:
                entry["material"] = args.material
            tools[args.tool] = entry
    elif args.printer or args.tool or args.color or args.material or args.clear_tool:
        raise SystemExit("give --printer together with --tool/--clear-tool "
                         "(or run without options for the interactive interface)")
    else:
        data = _interactive(data)

    path = save_filaments(data)
    print(f"saved {path}")
    _show(load_filaments())


if __name__ == "__main__":
    main()
