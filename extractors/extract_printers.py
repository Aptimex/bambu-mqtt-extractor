#!/usr/bin/env python3
"""
Extract printer configurations from resources/printers/*.json files.
Each printer JSON has a base config at "00.00.00.00" plus firmware-specific overrides.
"""

import json
import re
from pathlib import Path
from typing import Any


def extract(repo_root: Path, config_dir: Path) -> dict:
    """Extract all printer configurations."""
    printers_dir = repo_root / "resources" / "printers"
    output_dir = config_dir / "printers"

    printers = {}

    for json_file in sorted(printers_dir.glob("*.json")):
        if json_file.name == "filaments_blacklist.json" or json_file.name == "version.txt":
            continue

        model_id = json_file.stem
        print(f"  Processing {model_id}...")

        with open(json_file) as f:
            data = json.load(f)

        # Parse base config and firmware overrides
        base_config = data.get("00.00.00.00", {})
        firmware_configs = {}

        for key, value in data.items():
            if key == "00.00.00.00":
                continue
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", key):
                firmware_configs[key] = value

        # Merge base + each firmware version
        merged_versions = {}
        for version in sorted(firmware_configs.keys(), key=version_key):
            merged = deep_merge(base_config.copy(), firmware_configs[version])
            merged_versions[version] = merged

        # Also include base as a version
        merged_versions["00.00.00.00"] = base_config

        # Build printer entry
        printer_entry = {
            "model_id": base_config.get("model_id", model_id),
            "display_name": base_config.get("display_name", model_id),
            "printer_type": base_config.get("printer_type", model_id),
            "series": base_config.get("printer_series", "SERIES_UNKNOWN"),
            "arch": base_config.get("printer_arch", "core_xy"),
            "is_enclosed": base_config.get("printer_is_enclosed", False),
            "enable_set_nozzle_info": base_config.get("enable_set_nozzle_info", False),
            "support_safety_options": base_config.get("support_safety_options", False),
            "support_disable_cali_flow_type": base_config.get("support_disable_cali_flow_type", False),
            "has_cali_line": base_config.get("has_cali_line", False),
            "use_ams_type": base_config.get("use_ams_type", "generic"),
            "compatible_machines": base_config.get("compatible_machine", []),
            "bed_temperature_limit": base_config.get("bed_temperature_limit", 100),
            "camera_resolutions": base_config.get("camera_resolution", []),
            "nozzle_temp_range": base_config.get("nozzle_temp_range", [0, 300]),
            "printer_thumbnail_image": base_config.get("printer_thumbnail_image", ""),
            "printer_connect_help_image": base_config.get("printer_connect_help_image", ""),
            "printer_use_ams_image": base_config.get("printer_use_ams_image", ""),
            "printer_ext_image": base_config.get("printer_ext_image", []),
            "ftp_folder": base_config.get("ftp_folder", ""),
            "auto_cali_not_support_filaments": base_config.get("auto_cali_not_support_filaments", []),
            "support_wrapping_detection": base_config.get("support_wrapping_detection", False),
            "filament_load_image": base_config.get("filament_load_image", []),
            "nozzle_replace_wiki": base_config.get("nozzle_replace_wiki", {}),
            "ipcam": base_config.get("ipcam", {}),
            "fan": base_config.get("fan", {}),
            "tool_head_display_names": base_config.get("tool_head_display_names", {}),
            "firmware_versions": merged_versions,
        }

        printers[model_id] = printer_entry

        # Write individual printer file
        output_file = output_dir / f"{model_id}.json"
        with open(output_file, "w") as f:
            json.dump(printer_entry, f, indent=2)

    return printers


def version_key(v: str) -> tuple:
    """Convert version string to tuple for sorting."""
    return tuple(int(x) for x in v.split("."))


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


if __name__ == "__main__":
    import sys
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
    config_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "config"
    extract(repo_root, config_dir)