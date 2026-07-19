#!/usr/bin/env python3
"""
Extract AMS response format information from printer configs.

Different printers/firmwares return AMS/slot data in different JSON structures.
This extractor infers the format based on printer model and firmware version.
"""

import json
from pathlib import Path
from typing import Any, Dict


AMS_RESPONSE_FORMATS = {
    "standard": {
        "external_spool_key": "vt_tray",      # single object
        "ams_array_key": "ams",               # array under ams.ams
        "ams_id_key": "id",                   # AMS id field
        "tray_array_key": "tray",             # tray array under each AMS
        "tray_id_key": "id",                  # tray id field
        "has_vir_slot": False,
    },
    "x1c": {
        "external_spool_key": "vir_slot",     # array of 1
        "ams_array_key": "ams",               # array under ams.ams
        "ams_id_key": "id",
        "tray_array_key": "tray",
        "tray_id_key": "id",
        "has_vir_slot": True,
    },
    "p1p": {
        "external_spool_key": "vt_tray",      # single object
        "ams_array_key": "ams",
        "ams_id_key": "id",
        "tray_array_key": "tray",
        "tray_id_key": "id",
        "has_vir_slot": False,
    },
    "a1": {
        "external_spool_key": "vt_tray",
        "ams_array_key": "ams",
        "ams_id_key": "id",
        "tray_array_key": "tray",
        "tray_id_key": "id",
        "has_vir_slot": False,
    },
    "standard_vir": {
        "external_spool_key": "vir_slot",     # array of 1
        "ams_array_key": "ams",
        "ams_id_key": "id",
        "tray_array_key": "tray",
        "tray_id_key": "id",
        "has_vir_slot": True,
    },
}


def infer_ams_format(model_id: str, firmware_version: str, config: Dict[str, Any]) -> str:
    """
    Infer AMS response format from printer model and firmware.
    
    Based on analysis of QRSpool/bambu-server/mqtt.py and bambu.py:
    - X1C uses vir_slot (array) for external spool
    - P1P, A1 use vt_tray (object) for external spool
    - Some firmwares use vir_slot instead of vt_tray
    """
    series = config.get("printer_series", "").lower()
    arch = config.get("printer_arch", "").lower()
    ams_type = config.get("use_ams_type", "generic")
    
    # X1 series
    if model_id in ["BL-P001", "BL-P002"] or "x1" in series:
        return "x1c"
    
    # P1 series
    if model_id in ["C11", "C12", "C13"] or "p1" in series:
        return "p1p"
    
    # A1 series
    if model_id in ["N1", "N2S"] or "a1" in series:
        return "a1"
    
    # Default to standard
    return "standard"


def extract(repo_root: Path, config_dir: Path, printers: Dict[str, Any]) -> Dict[str, Any]:
    """Extract AMS response format info and add to printer configs."""
    
    for model_id, printer_data in printers.items():
        for version, config in printer_data.get("firmware_versions", {}).items():
            base_config = config.get("print", config)
            
            # Infer AMS format
            ams_format = infer_ams_format(model_id, version, base_config)
            
            # Add to config
            base_config["ams_response_format"] = ams_format
            
            # Add format details
            format_info = AMS_RESPONSE_FORMATS.get(ams_format, AMS_RESPONSE_FORMATS["standard"])
            base_config["ams_format_details"] = format_info
    
    # Write updated printer configs
    printers_dir = config_dir / "printers"
    for model_id, printer_data in printers.items():
        if model_id == "index.json":
            continue
        output_file = printers_dir / f"{model_id}.json"
        with open(output_file, "w") as f:
            json.dump(printer_data, f, indent=2)
    
    return {"ams_response_formats": AMS_RESPONSE_FORMATS}


if __name__ == "__main__":
    import sys
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
    config_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "config"

    printers_dir = config_dir / "printers"
    printers = {}
    for f in printers_dir.glob("*.json"):
        if f.name != "index.json":
            with open(f) as fp:
                printers[f.stem] = json.load(fp)

    extract(repo_root, config_dir, printers)