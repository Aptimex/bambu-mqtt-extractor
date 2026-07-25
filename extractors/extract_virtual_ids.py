#!/usr/bin/env python3
"""
Extract virtual ID constants from DevDefs.h
"""

import json
import re
from pathlib import Path
from typing import Dict, Any


def extract(repo_root: Path, config_dir: Path) -> Dict[str, Any]:
    """Extract #define constants from DevDefs.h"""
    devdefs_h = repo_root / "src" / "slic3r" / "GUI" / "DeviceCore" / "DevDefs.h"

    if not devdefs_h.exists():
        print(f"  Warning: {devdefs_h} not found")
        return {}

    content = devdefs_h.read_text()

    wanted = [
        "VIRTUAL_TRAY_MAIN_ID", "VIRTUAL_TRAY_DEPUTY_ID",
        "VIRTUAL_AMS_MAIN_ID_STR", "VIRTUAL_AMS_DEPUTY_ID_STR",
        "MAIN_EXTRUDER_ID", "DEPUTY_EXTRUDER_ID",
        "UNIQUE_EXTRUDER_ID", "INVALID_EXTRUDER_ID",
        "LOGIC_UNIQUE_EXTRUDER_ID", "LOGIC_L_EXTRUDER_ID",
        "LOGIC_R_EXTRUDER_ID",
        "AMS_LITE_MIXED_TRAY_INDEX_OFFSET",
        "INVALID_AMS_TEMPERATURE",
    ]

    raw = {}
    for define in wanted:
        match = re.search(rf"^\s*#define\s+{define}\s+(.+?)\s*(?://.*)?$",
                          content, re.MULTILINE)
        if match:
            raw[define] = match.group(1).strip()

    defines = {}
    for define in wanted:
        if define in raw:
            defines[define] = resolve_value(raw[define], raw)

    missing = [d for d in wanted if d not in defines]
    if missing:
        print(f"  Warning: not found in DevDefs.h: {', '.join(missing)}")

    # Write to config
    output_file = config_dir / "virtual_ids.json"
    with open(output_file, "w") as f:
        json.dump(defines, f, indent=2)

    return defines


def resolve_value(value: str, raw: Dict[str, str], depth: int = 0) -> Any:
    """
    Normalize a #define body into a JSON value.

    Handles the three shapes that appear in DevDefs.h: an integer literal, a
    quoted string (whose quotes are part of the C++ source, not the value), and
    an alias for another #define (e.g. UNIQUE_EXTRUDER_ID -> MAIN_EXTRUDER_ID).
    Anything else — such as a C++ expression — is passed through unchanged.
    """
    value = value.strip()

    # Alias for another define in this file.
    if depth < 8 and re.fullmatch(r"[A-Za-z_]\w*", value) and value in raw:
        return resolve_value(raw[value], raw, depth + 1)

    # Quoted string: the quotes belong to the C++ literal.
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]

    try:
        return int(value, 0)
    except ValueError:
        pass

    return value


if __name__ == "__main__":
    import sys
    import json
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
    config_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "config"
    extract(repo_root, config_dir)