#!/usr/bin/env python3
"""
Generate index.json files for all config directories.
"""

import json
import re
from pathlib import Path

# Files in printers/ that describe the set of printers rather than one printer.
PRINTER_META_FILES = {"index.json", "names.json"}


def normalize_printer_name(name: str) -> str:
    """Normalize a printer name for matching: lowercase, collapse whitespace.

    Must stay in sync with ConfigLoader._normalize_printer_name in
    bambu-mqtt-generator, which normalizes user input the same way.
    """
    return re.sub(r"\s+", " ", name.strip().lower())


def generate(config_dir: Path):
    """Generate all index.json files."""

    # printers/index.json
    printers_dir = config_dir / "printers"
    printer_index = []
    for f in sorted(printers_dir.glob("*.json")):
        if f.name in PRINTER_META_FILES:
            continue
        with open(f) as fp:
            data = json.load(fp)
        printer_index.append({
            "model_id": data.get("model_id", f.stem),
            "display_name": data.get("display_name"),
            "series": data.get("series"),
            "arch": data.get("arch"),
            "file": f.name,
        })
    with open(printers_dir / "index.json", "w") as f:
        json.dump(printer_index, f, indent=2)
    print(f"  printers/index.json: {len(printer_index)} entries")

    # printers/names.json
    generate_printer_names(printers_dir, printer_index)

    # commands/index.json
    commands_dir = config_dir / "commands"
    command_index = []
    for f in sorted(commands_dir.glob("*.json")):
        if f.name == "index.json":
            continue
        with open(f) as fp:
            data = json.load(fp)
        command_index.append({
            "command": data.get("command", f.stem),
            "category": data.get("category"),
            "file": f.name,
        })
    with open(commands_dir / "index.json", "w") as f:
        json.dump(command_index, f, indent=2)
    print(f"  commands/index.json: {len(command_index)} entries")

    # enums/index.json
    enums_dir = config_dir / "enums"
    enum_index = sorted(f.stem for f in enums_dir.glob("*.json") if f.name != "index.json")
    with open(enums_dir / "index.json", "w") as f:
        json.dump(enum_index, f, indent=2)
    print(f"  enums/index.json: {len(enum_index)} entries")

    # filament_presets/index.json
    filament_dir = config_dir / "filament_presets"
    filament_index = []
    for f in sorted(filament_dir.glob("*.json")):
        if f.name == "index.json":
            continue
        with open(f) as fp:
            data = json.load(fp)
        filament_index.append({
            "filament_id": data.get("filament_id", f.stem),
            # filament_name is what consumers derive the brand from, so it has
            # to be in the index or every filament reads as "Generic".
            "filament_name": data.get("filament_name", ""),
            "filament_type": data.get("filament_type"),
            # The type as the printer is told it, which support filaments spell
            # differently from filament_type. In the index so a consumer can
            # build a complete code -> tray_type map without opening every file.
            "tray_type": data.get("tray_type", data.get("filament_type")),
            "is_bambu": data.get("is_bambu", False),
            "file": f.name,
        })
    with open(filament_dir / "index.json", "w") as f:
        json.dump(filament_index, f, indent=2)
    print(f"  filament_presets/index.json: {len(filament_index)} entries")


def generate_printer_names(printers_dir: Path, printer_index: list):
    """Generate printers/names.json: printer name -> model id.

    Bambu Studio does not guarantee display names are unique. H2C, for example,
    ships as two model ids (O1C and O1C2) with the same display_name but
    different feature flags and subseries, so a name map built by iterating the
    printer configs silently resolves "H2C" to whichever file happened to load
    last. Resolving that here — deterministically, and recording the collision
    rather than hiding it — keeps consumers from having to guess.

    Names that map to exactly one model id go in "names". Names claimed by more
    than one go in "ambiguous", with every candidate listed, so a consumer can
    reject them and say which model ids to choose between.
    """
    claims: dict = {}
    for entry in printer_index:
        display_name = entry.get("display_name") or ""
        if not display_name:
            continue
        # Names are stored without the vendor prefix; users say "X1 Carbon".
        if display_name.lower().startswith("bambu lab "):
            display_name = display_name[len("bambu lab "):]
        claims.setdefault(normalize_printer_name(display_name), set()).add(
            entry["model_id"]
        )

    names = {n: sorted(ids)[0] for n, ids in sorted(claims.items()) if len(ids) == 1}
    ambiguous = {n: sorted(ids) for n, ids in sorted(claims.items()) if len(ids) > 1}

    with open(printers_dir / "names.json", "w") as f:
        json.dump({"names": names, "ambiguous": ambiguous}, f, indent=2)

    print(f"  printers/names.json: {len(names)} names, {len(ambiguous)} ambiguous")
    for name, ids in ambiguous.items():
        print(f"    ambiguous: '{name}' -> {', '.join(ids)}")


if __name__ == "__main__":
    import sys
    config_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "config"
    generate(config_dir)