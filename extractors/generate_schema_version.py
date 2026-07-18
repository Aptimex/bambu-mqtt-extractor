#!/usr/bin/env python3
"""
Generate schema_version.json with extraction metadata.
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime


def generate(config_dir: Path, repo_root: Path):
    """Generate schema_version.json"""
    output_file = config_dir / "schema_version.json"

    # Get git commit hash
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()[:12]
    except:
        commit = "unknown"

    # Count configs
    printers_count = len(list((config_dir / "printers").glob("*.json"))) - 1  # minus index.json
    commands_count = len(list((config_dir / "commands").glob("*.json"))) - 1
    enums_count = len(list((config_dir / "enums").glob("*.json"))) - 1
    filaments_count = len(list((config_dir / "filament_presets").glob("*.json"))) - 1

    version = {
        "version": 1,
        "extracted_from": commit,
        "extraction_date": datetime.utcnow().isoformat() + "Z",
        "counts": {
            "printers": max(0, printers_count),
            "commands": max(0, commands_count),
            "enums": max(0, enums_count),
            "filament_presets": max(0, filaments_count),
        }
    }

    with open(output_file, "w") as f:
        json.dump(version, f, indent=2)

    print(f"  Schema version: {version['version']}, commit: {commit}")


if __name__ == "__main__":
    import sys
    config_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "config"
    repo_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent.parent
    generate(config_dir, repo_root)