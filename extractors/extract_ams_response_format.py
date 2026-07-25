#!/usr/bin/env python3
"""
Extract the AMS / external-spool push_status response contract from Bambu Studio.

Bambu Studio does NOT vary this per printer model or firmware: one parser
handles every device and decides at runtime which shape it got. See
DeviceManager.cpp (`vir_slot` / `vt_tray` branch) and
DeviceCore/DevFilaSystem.cpp (`ams.ams[].tray[]`).

So rather than inferring a per-model format (which is guesswork and was wrong
for several printers), this extractor reads the actual rules out of the C++ and
emits one authoritative `ams_response_format.json`. Each rule is verified
against the source; anything that no longer matches is reported so a Bambu
Studio update can't silently invalidate the config.

Key rules captured here:

  * External spool is read from `vir_slot` (an array) if present, else
    `vt_tray` (a single object). If neither is present the device has no
    virtual tray.
  * In the `vir_slot` form each entry carries its own id: 255 = main slot,
    254 = deputy slot.
  * In the `vt_tray` form the id reported by the printer is DISCARDED and the
    slot is treated as the main slot (255). This matters: the A1 reports
    `"id": "254"` in `vt_tray`, but Bambu Studio treats it as slot 255.
  * A slot id above 255 packs ams_id in bits 8-15 and slot_id in bits 0-7 and
    is decoded as `(id >> 8) + (id & 0xff)`.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List


def _read(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def _check(results: List[str], ok: bool, description: str) -> bool:
    """Record a source-verification result."""
    if not ok:
        results.append(description)
    return ok


def verify_against_source(repo_root: Path) -> Dict[str, Any]:
    """
    Confirm each rule we encode still holds in the Bambu Studio source.

    Returns a dict with 'verified' (list of rule names that matched) and
    'unverified' (list of human-readable descriptions that did not).
    """
    device_manager = _read(repo_root / "src" / "slic3r" / "GUI" / "DeviceManager.cpp")
    fila_system = _read(
        repo_root / "src" / "slic3r" / "GUI" / "DeviceCore" / "DevFilaSystem.cpp"
    )

    unverified: List[str] = []
    verified: List[str] = []

    def check(name: str, ok: bool, detail: str) -> None:
        if ok:
            verified.append(name)
        else:
            unverified.append(f"{name}: {detail}")

    # External spool: vir_slot (array) is tried before vt_tray (object).
    vir_pos = device_manager.find('jj.contains("vir_slot")')
    vt_pos = device_manager.find('jj.contains("vt_tray")')
    check(
        "external_spool_precedence",
        vir_pos != -1 and vt_pos != -1 and vir_pos < vt_pos,
        "expected `vir_slot` checked before `vt_tray` in DeviceManager.cpp",
    )
    check(
        "vir_slot_is_array",
        'jj["vir_slot"].is_array()' in device_manager,
        "expected `vir_slot` to be validated as an array",
    )

    # vt_tray's reported id is overwritten with the main virtual tray id.
    check(
        "vt_tray_id_forced_to_main",
        re.search(
            r'parse_vt_tray\(jj\["vt_tray"\][^;]*;\s*'
            r"\w+\.id\s*=\s*std::to_string\(VIRTUAL_TRAY_MAIN_ID\)",
            device_manager,
        )
        is not None,
        "expected the vt_tray slot id to be overwritten with VIRTUAL_TRAY_MAIN_ID",
    )

    # vir_slot entries are dispatched by their own id.
    check(
        "vir_slot_ids_are_per_entry",
        "VIRTUAL_TRAY_MAIN_ID" in device_manager
        and "VIRTUAL_TRAY_DEPUTY_ID" in device_manager
        and re.search(
            r"vslot\.id\s*==\s*std::to_string\(VIRTUAL_TRAY_DEPUTY_ID\)", device_manager
        )
        is not None,
        "expected vir_slot entries to be matched against main/deputy ids",
    )

    # Packed slot id decoding in parse_vt_tray.
    check(
        "packed_slot_id_decoding",
        re.search(r"\(id_int\s*>>\s*8\)\s*\+\s*\(id_int\s*&\s*0xff\)", device_manager)
        is not None,
        "expected `(id >> 8) + (id & 0xff)` packed-id decoding in parse_vt_tray",
    )

    # AMS array shape: push_status["ams"]["ams"][] with "id", trays under "tray".
    check(
        "ams_array_shape",
        'jj["ams"].contains("ams")' in fila_system
        and 'jj["ams"]["ams"]' in fila_system,
        "expected the AMS array at ams.ams in DevFilaSystem.cpp",
    )
    check(
        "ams_id_key",
        re.search(r'j_ams,\s*"id"', fila_system) is not None
        or 'j_ams.contains("id")' in fila_system,
        'expected each AMS entry keyed by "id"',
    )
    check(
        "tray_array_key",
        'j_ams.contains("tray")' in fila_system
        and 'j_ams["tray"]' in fila_system,
        'expected the tray array under "tray"',
    )
    check(
        "tray_id_key",
        'j_tray.contains("id")' in fila_system
        or re.search(r'j_tray,\s*"id"', fila_system) is not None,
        'expected each tray entry keyed by "id"',
    )

    # Command-side id mapping in command_ams_filament_settings.
    check(
        "virtual_tray_command_id",
        re.search(
            r"tag_ams_id\s*==\s*VIRTUAL_TRAY_MAIN_ID\s*\|\|\s*"
            r"tag_ams_id\s*==\s*VIRTUAL_TRAY_DEPUTY_ID[^}]*"
            r"tag_tray_id\s*=\s*VIRTUAL_TRAY_DEPUTY_ID",
            device_manager,
            re.DOTALL,
        )
        is not None,
        "expected virtual slots to send tray_id = VIRTUAL_TRAY_DEPUTY_ID",
    )
    check(
        "physical_tray_command_id",
        re.search(r"else\s*{\s*tag_tray_id\s*=\s*tag_slot_id;", device_manager)
        is not None,
        "expected physical AMS to send tray_id = slot_id",
    )

    return {"verified": verified, "unverified": unverified}


def build_format(virtual_ids: Dict[str, Any]) -> Dict[str, Any]:
    """Build the response-format contract, using ids extracted from DevDefs.h."""
    main_id = virtual_ids.get("VIRTUAL_TRAY_MAIN_ID", 255)
    deputy_id = virtual_ids.get("VIRTUAL_TRAY_DEPUTY_ID", 254)

    return {
        "detection": "runtime",
        "note": (
            "Bambu Studio applies one parser to every printer model and firmware "
            "and detects the shape at runtime. Do not branch on model id."
        ),
        "source": [
            "src/slic3r/GUI/DeviceManager.cpp",
            "src/slic3r/GUI/DeviceCore/DevFilaSystem.cpp",
            "src/slic3r/GUI/DeviceCore/DevDefs.h",
        ],
        "ams": {
            "container_key": "ams",
            "array_key": "ams",
            "id_key": "id",
            "tray_array_key": "tray",
            "tray_id_key": "id",
        },
        "external_spool": {
            # Ordered: first match wins, exactly as DeviceManager.cpp does it.
            "keys": [
                {
                    "key": "vir_slot",
                    "container": "array",
                    "id_source": "entry",
                    "comment": (
                        "Each entry carries its own id; "
                        f"{main_id} = main slot, {deputy_id} = deputy slot."
                    ),
                },
                {
                    "key": "vt_tray",
                    "container": "object",
                    "id_source": "forced",
                    "forced_id": main_id,
                    "comment": (
                        "The id reported by the printer is discarded and the slot "
                        f"is treated as the main slot ({main_id}). The A1 reports "
                        f'"id": "{deputy_id}" here but is still the main slot.'
                    ),
                },
            ],
            "main_id": main_id,
            "deputy_id": deputy_id,
            "packed_id": {
                "applies_when_id_greater_than": 255,
                "ams_id_bits": [8, 15],
                "slot_id_bits": [0, 7],
                "decode": "(id >> 8) + (id & 0xff)",
            },
        },
        # How the ids above map onto ams_filament_setting command fields.
        # From MachineObject::command_ams_filament_settings.
        "command_ids": {
            "virtual_slot": {
                "ams_id": [main_id, deputy_id],
                "tray_id": deputy_id,
                "slot_id": 0,
            },
            "physical_ams": {
                "ams_id": "the 0-based AMS id as reported in push_status",
                "tray_id": "equal to slot_id",
                "slot_id": "the 0-based tray id as reported in push_status",
            },
        },
    }


def extract(
    repo_root: Path,
    config_dir: Path,
    printers: Dict[str, Any],
    virtual_ids: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Extract the AMS response format contract and write it to the config dir."""
    if virtual_ids is None:
        vid_file = config_dir / "virtual_ids.json"
        virtual_ids = json.loads(vid_file.read_text()) if vid_file.exists() else {}

    checks = verify_against_source(repo_root)
    for name in checks["verified"]:
        print(f"  verified: {name}")
    for problem in checks["unverified"]:
        print(f"  WARNING: could not verify {problem}")
    if not checks["verified"]:
        print("  WARNING: no rules could be verified — is the repo path correct?")

    ams_format = build_format(virtual_ids)
    ams_format["verification"] = checks

    output_file = config_dir / "ams_response_format.json"
    with open(output_file, "w") as f:
        json.dump(ams_format, f, indent=2)
    print(f"  wrote {output_file.name}")

    # Older configs carried a per-printer/per-firmware guess at this format.
    # It is model-independent, so strip the stale copies rather than rewrite
    # them; consumers read ams_response_format.json.
    printers_dir = config_dir / "printers"
    stripped = 0
    for model_id, printer_data in printers.items():
        if model_id == "index.json":
            continue
        changed = False
        for _version, config in printer_data.get("firmware_versions", {}).items():
            base_config = config.get("print", config)
            for stale in ("ams_response_format", "ams_format_details"):
                if stale in base_config:
                    del base_config[stale]
                    changed = True
        if changed:
            stripped += 1
        output_file = printers_dir / f"{model_id}.json"
        with open(output_file, "w") as f:
            json.dump(printer_data, f, indent=2)
    if stripped:
        print(f"  removed stale per-printer format guesses from {stripped} printer(s)")

    return ams_format


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
