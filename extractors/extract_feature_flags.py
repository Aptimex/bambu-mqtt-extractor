#!/usr/bin/env python3
"""
Extract feature flags matrix from printer configurations.
"""

import json
from pathlib import Path
from typing import Dict, Any, Set


def extract_flags_from_config(config: Dict[str, Any]) -> Set[str]:
    """Recursively extract support_/enable_ flags from a config dict."""
    flags = set()
    for key, value in config.items():
        if key.startswith("support_") or key.startswith("enable_"):
            flags.add(key)
        elif isinstance(value, dict):
            flags.update(extract_flags_from_config(value))
    return flags


def extract(repo_root: Path, config_dir: Path, printers: Dict[str, Any]) -> Dict[str, Any]:
    """Build feature flag matrix from printer configs."""
    output_dir = config_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    all_flags = set()
    printer_support = {}

    for model_id, printer_data in printers.items():
        printer_support[model_id] = {}
        for version, config in printer_data.get("firmware_versions", {}).items():
            printer_support[model_id][version] = {}

            # Check top-level config
            for key, value in config.items():
                if key.startswith("support_") or key.startswith("enable_"):
                    all_flags.add(key)
                    printer_support[model_id][version][key] = value

            # Check nested "print" object
            if "print" in config and isinstance(config["print"], dict):
                for key, value in config["print"].items():
                    if key.startswith("support_") or key.startswith("enable_"):
                        all_flags.add(key)
                        printer_support[model_id][version][key] = value

    flags = sorted(all_flags)

    feature_flags = {
        "flags": flags,
        "printer_support": printer_support
    }

    output_file = output_dir / "feature_flags.json"
    with open(output_file, "w") as f:
        json.dump(feature_flags, f, indent=2)

    return feature_flags


if __name__ == "__main__":
    import sys
    import json
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
    config_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "config"

    printers_dir = config_dir / "printers"
    printers = {}
    for f in printers_dir.glob("*.json"):
        if f.name != "index.json":
            with open(f) as fp:
                printers[f.stem] = json.load(fp)

    extract(repo_root, config_dir, printers)