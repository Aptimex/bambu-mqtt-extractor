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

    defines = {}
    for define in [
        "VIRTUAL_TRAY_MAIN_ID", "VIRTUAL_TRAY_DEPUTY_ID",
        "VIRTUAL_AMS_MAIN_ID_STR", "VIRTUAL_AMS_DEPUTY_ID_STR",
        "MAIN_EXTRUDER_ID", "DEPUTY_EXTRUDER_ID",
        "UNIQUE_EXTRUDER_ID", "INVALID_EXTRUDER_ID",
        "LOGIC_UNIQUE_EXTRUDER_ID", "LOGIC_L_EXTRUDER_ID",
        "LOGIC_R_EXTRUDER_ID",
        "AMS_LITE_MIXED_TRAY_INDEX_OFFSET",
        "INVALID_AMS_TEMPERATURE",
    ]:
        match = re.search(rf"#define\s+{define}\s+(\S+)", content)
        if match:
            val = match.group(1)
            try:
                val = int(val, 0)
            except:
                pass
            defines[define] = val

    # Write to config
    output_file = config_dir / "virtual_ids.json"
    with open(output_file, "w") as f:
        json.dump(defines, f, indent=2)

    return defines


if __name__ == "__main__":
    import sys
    import json
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
    config_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "config"
    extract(repo_root, config_dir)