#!/usr/bin/env python3
"""
Extract filament presets from printer configs, blacklist, and filament profile files.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional


def extract_filament_from_profile(file_path: Path, base_profiles: Dict[str, Any]) -> Dict[str, Any]:
    """Extract filament data from a profile JSON file, including inherited base profile data."""
    try:
        with open(file_path) as f:
            data = json.load(f)
    except:
        return None

    filament_id = data.get("filament_id")
    if not filament_id:
        return None

    # Extract useful fields
    result = {
        "filament_id": filament_id,
        "filament_name": data.get("name", ""),
        "filament_type": "",
        "nozzle_temp_min": 0,
        "nozzle_temp_max": 0,
        "bed_temp": 0,
        "color": "",
        "is_bambu": False,
    }

    # Extract filament type from inherits or other fields
    inherits = data.get("inherits", "")
    if "pla" in inherits.lower():
        result["filament_type"] = "PLA"
    elif "abs" in inherits.lower():
        result["filament_type"] = "ABS"
    elif "petg" in inherits.lower() or "fdm_filament_pet" in inherits.lower():
        result["filament_type"] = "PETG"
    elif "tpu" in inherits.lower():
        result["filament_type"] = "TPU"
    elif "asa" in inherits.lower():
        result["filament_type"] = "ASA"
    elif "pva" in inherits.lower():
        result["filament_type"] = "PVA"
    elif "pc" in inherits.lower():
        result["filament_type"] = "PC"
    elif "pa" in inherits.lower() or "nylon" in inherits.lower():
        result["filament_type"] = "PA"
    elif "cf" in inherits.lower() or "carbon" in inherits.lower():
        result["filament_type"] = "CF"
    
    # Fallback: determine from filament_id prefix
    if not result["filament_type"]:
        fid = result["filament_id"]
        if fid.startswith("GFA") or fid.startswith("GFL"):
            result["filament_type"] = "PLA"
        elif fid.startswith("GFB"):
            result["filament_type"] = "ABS"
        elif fid.startswith("GFG"):
            result["filament_type"] = "PETG"
        elif fid.startswith("GFU"):
            result["filament_type"] = "TPU"
        elif fid.startswith("GFB") and not fid.startswith("GFB9"):
            result["filament_type"] = "ABS"
        elif fid.startswith("GFN"):
            result["filament_type"] = "PA"
        elif fid.startswith("GFC"):
            result["filament_type"] = "PC"
        elif fid.startswith("GFP"):
            result["filament_type"] = "PVA"
        elif fid.startswith("GFR"):
            result["filament_type"] = "PA"
        elif fid.startswith("GFS"):
            result["filament_type"] = "PVA"
        elif fid.startswith("GFT"):
            result["filament_type"] = "TPU"

    # Try to get temperature settings from this profile first
    for key in ["nozzle_temp_min", "filament_nozzle_temp_min"]:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                result["nozzle_temp_min"] = val[0] if isinstance(val[0], (int, float)) else int(val[0])
            elif isinstance(val, (int, float)):
                result["nozzle_temp_min"] = int(val)

    for key in ["nozzle_temp_max", "filament_nozzle_temp_max"]:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                result["nozzle_temp_max"] = val[0] if isinstance(val[0], (int, float)) else int(val[0])
            elif isinstance(val, (int, float)):
                result["nozzle_temp_max"] = int(val)

    for key in ["bed_temp", "filament_bed_temp"]:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                result["bed_temp"] = val[0] if isinstance(val[0], (int, float)) else int(val[0])
            elif isinstance(val, (int, float)):
                result["bed_temp"] = int(val)

    # Extract color
    for key in ["filament_color", "color"]:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                result["color"] = val[0] if isinstance(val[0], str) else str(val[0])
            elif isinstance(val, str):
                result["color"] = val

    # Mark Bambu Lab filaments
    if data.get("filament_vendor", [""])[0] == "Bambu Lab" or "Bambu" in data.get("name", ""):
        result["is_bambu"] = True

    # If we have inherits, try to get base profile temperatures
    inherits = data.get("inherits", "")
    if inherits and base_profiles:
        base = base_profiles.get(inherits)
        if base:
            # Get base nozzle temperature
            if result["nozzle_temp_min"] == 0:
                for key in ["nozzle_temperature"]:
                    if key in base:
                        val = base[key]
                        if isinstance(val, list) and val:
                            result["nozzle_temp_min"] = val[0] if isinstance(val[0], (int, float)) else int(val[0])
                        elif isinstance(val, (int, float)):
                            result["nozzle_temp_min"] = int(val)
                        break

            if result["nozzle_temp_max"] == 0:
                for key in ["nozzle_temperature"]:
                    if key in base:
                        val = base[key]
                        if isinstance(val, list) and val:
                            result["nozzle_temp_max"] = val[0] if isinstance(val[0], (int, float)) else int(val[0])
                        elif isinstance(val, (int, float)):
                            result["nozzle_temp_max"] = int(val)
                        break

            if result["bed_temp"] == 0:
                for key in ["hot_plate_temp"]:
                    if key in base:
                        val = base[key]
                        if isinstance(val, list) and val:
                            result["bed_temp"] = val[0] if isinstance(val[0], (int, float)) else int(val[0])
                        elif isinstance(val, (int, float)):
                            result["bed_temp"] = int(val)
                        break

    return result


def load_base_profiles(repo_root: Path) -> Dict[str, Any]:
    """Load base filament profiles (fdm_filament_*) from BBL profiles."""
    base_profiles = {}
    profiles_root = repo_root / "resources" / "profiles"
    if not profiles_root.exists():
        return base_profiles

    # Look in BBL/filament for base profiles
    filament_dir = profiles_root / "BBL" / "filament"
    if not filament_dir.exists():
        return base_profiles

    for profile_file in filament_dir.glob("fdm_filament_*.json"):
        try:
            with open(profile_file) as f:
                data = json.load(f)
        except:
            continue

        name = data.get("name", "")
        if name:
            base_profiles[name] = data

    return base_profiles


def extract(repo_root: Path, config_dir: Path, printers: Dict[str, Any]) -> Dict[str, Any]:
    """Extract known filament IDs and their default properties."""
    output_dir = config_dir / "filament_presets"
    output_dir.mkdir(parents=True, exist_ok=True)

    presets = {}

    # Known Bambu filament IDs with defaults (hardcoded fallbacks)
    known_filaments = {
        "GFU01": {"filament_id": "GFU01", "filament_name": "Bambu PLA Basic", "filament_type": "PLA", "nozzle_temp_min": 190, "nozzle_temp_max": 230, "bed_temp": 65, "color": "00FF00FF", "is_bambu": True},
        "GFU02": {"filament_id": "GFU02", "filament_name": "Bambu PETG Basic", "filament_type": "PETG", "nozzle_temp_min": 230, "nozzle_temp_max": 250, "bed_temp": 75, "color": "0000FFFF", "is_bambu": True},
        "GFU03": {"filament_id": "GFU03", "filament_name": "Bambu TPU 95A", "filament_type": "TPU", "nozzle_temp_min": 210, "nozzle_temp_max": 230, "bed_temp": 45, "color": "FF00FFFF", "is_bambu": True},
        "GFU04": {"filament_id": "GFU04", "filament_name": "Bambu PVA", "filament_type": "PVA", "nozzle_temp_min": 190, "nozzle_temp_max": 210, "bed_temp": 60, "color": "FFFF00FF", "is_bambu": True},
        "GFU05": {"filament_id": "GFU05", "filament_name": "Bambu PLA-CF", "filament_type": "PLA-CF", "nozzle_temp_min": 220, "nozzle_temp_max": 260, "bed_temp": 65, "color": "333333FF", "is_bambu": True},
        "GFU06": {"filament_id": "GFU06", "filament_name": "Bambu PETG-CF", "filament_type": "PETG-CF", "nozzle_temp_min": 240, "nozzle_temp_max": 270, "bed_temp": 80, "color": "444444FF", "is_bambu": True},
        "GFU07": {"filament_id": "GFU07", "filament_name": "Bambu PA-CF", "filament_type": "PA-CF", "nozzle_temp_min": 260, "nozzle_temp_max": 300, "bed_temp": 90, "color": "555555FF", "is_bambu": True},
        "GFU08": {"filament_id": "GFU08", "filament_name": "Bambu PET-CF", "filament_type": "PET-CF", "nozzle_temp_min": 260, "nozzle_temp_max": 300, "bed_temp": 90, "color": "666666FF", "is_bambu": True},
        "GFU09": {"filament_id": "GFU09", "filament_name": "Bambu PAHT-CF", "filament_type": "PAHT-CF", "nozzle_temp_min": 280, "nozzle_temp_max": 320, "bed_temp": 100, "color": "777777FF", "is_bambu": True},
        "GFU10": {"filament_id": "GFU10", "filament_name": "Bambu ASA", "filament_type": "ASA", "nozzle_temp_min": 250, "nozzle_temp_max": 270, "bed_temp": 100, "color": "FF8800FF", "is_bambu": True},
        "GFU11": {"filament_id": "GFU11", "filament_name": "Bambu PC", "filament_type": "PC", "nozzle_temp_min": 270, "nozzle_temp_max": 310, "bed_temp": 110, "color": "888888FF", "is_bambu": True},
    }

    # Load base profiles for inheritance lookup
    base_profiles = load_base_profiles(repo_root)

    # Add known filaments
    presets.update(known_filaments)

    # Scan filament profile files from resources/profiles/*/filament/
    profiles_root = repo_root / "resources" / "profiles"
    if profiles_root.exists():
        for vendor_dir in profiles_root.iterdir():
            if not vendor_dir.is_dir():
                continue
            filament_dir = vendor_dir / "filament"
            if not filament_dir.exists():
                continue

            for profile_file in filament_dir.glob("*.json"):
                # Skip variant profiles (those with @ in name), only use @base or base profiles
                # Exception: include "Generic" brand filaments as they are base profiles
                if "@" in profile_file.stem and not profile_file.stem.endswith("@base"):
                    if not profile_file.stem.startswith("Generic "):
                        continue

                filament_data = extract_filament_from_profile(profile_file, base_profiles)
                if filament_data:
                    fid = filament_data["filament_id"]
                    if fid not in presets:
                        presets[fid] = filament_data

    # Add from printer configs (auto_cali_not_support_filaments)
    for model_id, printer_data in printers.items():
        for version, config in printer_data.get("firmware_versions", {}).items():
            for fid in config.get("auto_cali_not_support_filaments", []):
                if fid not in presets:
                    presets[fid] = {
                        "filament_id": fid,
                        "filament_type": "Unknown",
                        "is_bambu": True,
                        "note": f"Found in {model_id} v{version} auto_cali_not_support_filaments",
                    }

    # From filaments_blacklist.json
    blacklist_file = repo_root / "resources" / "printers" / "filaments_blacklist.json"
    if blacklist_file.exists():
        with open(blacklist_file) as f:
            blacklist = json.load(f)

        for item in blacklist.get("filaments", []):
            fid = item.get("filament_id")
            if fid and fid not in presets:
                presets[fid] = {
                    "filament_id": fid,
                    "filament_name": item.get("filament_name", ""),
                    "filament_type": item.get("filament_type", ""),
                    "is_blacklisted": True,
                    "is_bambu": True,
                }

    # Write individual preset files
    for fid, data in presets.items():
        output_file = output_dir / f"{fid}.json"
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

    return presets