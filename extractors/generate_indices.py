#!/usr/bin/env python3
"""
Generate index.json files for all config directories.
"""

import json
from pathlib import Path


def generate(config_dir: Path):
    """Generate all index.json files."""

    # printers/index.json
    printers_dir = config_dir / "printers"
    printer_index = []
    for f in printers_dir.glob("*.json"):
        if f.name == "index.json":
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

    # commands/index.json
    commands_dir = config_dir / "commands"
    command_index = []
    for f in commands_dir.glob("*.json"):
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
    enum_index = [f.stem for f in enums_dir.glob("*.json") if f.name != "index.json"]
    with open(enums_dir / "index.json", "w") as f:
        json.dump(enum_index, f, indent=2)
    print(f"  enums/index.json: {len(enum_index)} entries")

    # filament_presets/index.json
    filament_dir = config_dir / "filament_presets"
    filament_index = []
    for f in filament_dir.glob("*.json"):
        if f.name == "index.json":
            continue
        with open(f) as fp:
            data = json.load(fp)
        filament_index.append({
            "filament_id": data.get("filament_id", f.stem),
            "filament_type": data.get("filament_type"),
            "file": f.name,
        })
    with open(filament_dir / "index.json", "w") as f:
        json.dump(filament_index, f, indent=2)
    print(f"  filament_presets/index.json: {len(filament_index)} entries")


if __name__ == "__main__":
    import sys
    config_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "config"
    generate(config_dir)