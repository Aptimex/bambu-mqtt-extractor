#!/usr/bin/env python3
"""
Extract filament presets from the Bambu Studio profile tree.

Profiles form an inheritance chain: a concrete profile such as
"Bambu PLA Basic @base" inherits "fdm_filament_pla", which inherits
"fdm_filament_common". Most fields — including the nozzle temperature range and
the filament type — are only defined partway up that chain, so a preset can
only be read correctly by resolving the whole chain.

Two things are easy to get wrong here and both produce silently bad data:

  * `nozzle_temperature` is the single recommended print temperature, NOT the
    allowed range. The range is `nozzle_temperature_range_low` /
    `nozzle_temperature_range_high`. Using the former yields min == max.
  * `filament_id` is NOT unique across vendors — QIDI's "PLA-CF" also claims
    GFA00. Bambu Lab (BBL) profiles must win, and within a vendor the "@base"
    profile must win over per-nozzle variants.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Vendor directory that defines the canonical meaning of a Bambu filament id.
CANONICAL_VENDOR = "BBL"

# Guard against a malformed profile tree sending us into a cycle.
MAX_INHERIT_DEPTH = 32

# Fallback filament type by filament_id prefix, used only when the resolved
# inheritance chain defines no filament_type at all.
TYPE_BY_PREFIX = {
    "GFA": "PLA",
    "GFB": "ABS",
    "GFC": "PC",
    "GFG": "PETG",
    "GFL": "PLA",
    "GFN": "PA",
    "GFP": "PVA",
    "GFR": "PA",
    "GFS": "PVA",
    "GFT": "TPU",
    "GFU": "TPU",
}


def first_value(raw: Any) -> Any:
    """
    Unwrap a Bambu Studio config value.

    Profile fields are stored as single-element lists of strings
    (e.g. ["220"]); a few are plain scalars.
    """
    if isinstance(raw, list):
        return raw[0] if raw else None
    return raw


def as_int(raw: Any) -> Optional[int]:
    """Coerce a profile value to int, or None if it isn't numeric."""
    value = first_value(raw)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_str(raw: Any) -> str:
    """Coerce a profile value to a stripped string."""
    value = first_value(raw)
    return str(value).strip() if value is not None else ""


def load_all_profiles(repo_root: Path) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Load every filament profile in the repo, keyed by vendor then profile name.

    The name (not the filename) is what `inherits` refers to. Profiles must be
    kept per vendor because the base profile names are NOT unique: every vendor
    ships its own `fdm_filament_pla`, and they disagree (Anker's PLA tops out at
    230C, Bambu's at 240C). Flattening them into one namespace silently
    resolves Bambu filaments against another vendor's temperatures.
    """
    profiles: Dict[str, Dict[str, Dict[str, Any]]] = {}
    profiles_root = repo_root / "resources" / "profiles"
    if not profiles_root.exists():
        return profiles

    for vendor_dir in sorted(profiles_root.iterdir()):
        if not vendor_dir.is_dir():
            continue
        filament_dir = vendor_dir / "filament"
        if not filament_dir.is_dir():
            continue

        vendor_profiles: Dict[str, Dict[str, Any]] = {}
        # Recursive: a vendor tree may group profiles into subdirectories
        # (BBL keeps the Fiberon/Polymaker and SUNLU lines that way). Those are
        # still that vendor's profiles, so they share its namespace.
        for profile_file in sorted(filament_dir.rglob("*.json")):
            try:
                with open(profile_file) as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            name = data.get("name")
            if not name:
                continue
            data["_vendor"] = vendor_dir.name
            data["_path"] = str(profile_file.relative_to(repo_root))
            vendor_profiles[name] = data

        if vendor_profiles:
            profiles[vendor_dir.name] = vendor_profiles

    return profiles


def lookup_profile(
    name: str, vendor: str, profiles: Dict[str, Dict[str, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """
    Find a profile by name, preferring the vendor that referenced it.

    A profile's `inherits` names a profile in its own vendor tree; only fall
    back to the canonical vendor if that tree doesn't define it.
    """
    vendor_profiles = profiles.get(vendor, {})
    if name in vendor_profiles:
        return vendor_profiles[name]
    return profiles.get(CANONICAL_VENDOR, {}).get(name)


def resolve_chain(
    profile: Dict[str, Any], profiles: Dict[str, Dict[str, Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Flatten a profile and everything it inherits into one dict.

    Child values win over parent values, matching how Bambu Studio layers
    presets.
    """
    vendor = profile.get("_vendor", CANONICAL_VENDOR)
    chain: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = profile
    seen = set()

    for _ in range(MAX_INHERIT_DEPTH):
        if current is None:
            break
        name = current.get("name")
        if name in seen:
            break
        seen.add(name)
        chain.append(current)
        parent_name = as_str(current.get("inherits"))
        current = lookup_profile(parent_name, vendor, profiles) if parent_name else None

    # Apply oldest ancestor first so the concrete profile overrides it.
    resolved: Dict[str, Any] = {}
    for entry in reversed(chain):
        resolved.update(entry)
    return resolved


def profile_priority(profile: Dict[str, Any]) -> tuple:
    """
    Rank competing profiles that claim the same filament_id (lower is better).

    Bambu Lab profiles define the canonical meaning of a Bambu filament id;
    within a vendor the "@base" profile beats per-nozzle/per-printer variants.
    """
    vendor = profile.get("_vendor", "")
    name = profile.get("name", "")
    return (
        0 if vendor == CANONICAL_VENDOR else 1,
        0 if name.endswith("@base") else 1,
        len(name),
        name,
    )


def build_preset(
    profile: Dict[str, Any], profiles: Dict[str, Dict[str, Dict[str, Any]]]
) -> Dict[str, Any]:
    """Build a preset record from a profile and its resolved inheritance chain."""
    resolved = resolve_chain(profile, profiles)
    filament_id = as_str(profile.get("filament_id"))

    filament_type = as_str(resolved.get("filament_type"))
    if not filament_type:
        filament_type = TYPE_BY_PREFIX.get(filament_id[:3], "")

    # The allowed range, not the single recommended temperature. Fall back to
    # nozzle_temperature only when a profile defines no range at all.
    nozzle_min = as_int(resolved.get("nozzle_temperature_range_low"))
    nozzle_max = as_int(resolved.get("nozzle_temperature_range_high"))
    recommended = as_int(resolved.get("nozzle_temperature"))
    if nozzle_min is None:
        nozzle_min = recommended
    if nozzle_max is None:
        nozzle_max = recommended

    vendor = as_str(resolved.get("filament_vendor"))

    preset = {
        "filament_id": filament_id,
        "filament_name": as_str(profile.get("name")),
        "filament_type": filament_type,
        "nozzle_temp_min": nozzle_min if nozzle_min is not None else 0,
        "nozzle_temp_max": nozzle_max if nozzle_max is not None else 0,
        "bed_temp": as_int(resolved.get("hot_plate_temp")) or 0,
        "color": as_str(resolved.get("filament_color")),
        "is_bambu": vendor == "Bambu Lab" or profile.get("_vendor") == CANONICAL_VENDOR,
    }

    if recommended is not None:
        preset["nozzle_temp_recommended"] = recommended
    return preset


def extract(repo_root: Path, config_dir: Path, printers: Dict[str, Any]) -> Dict[str, Any]:
    """Extract filament presets, one JSON file per filament id."""
    output_dir = config_dir / "filament_presets"
    output_dir.mkdir(parents=True, exist_ok=True)

    profiles = load_all_profiles(repo_root)
    if not profiles:
        print(f"  Warning: no filament profiles found under {repo_root}")

    # Group every profile that declares a filament_id, then keep the
    # highest-priority one per id.
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    total_profiles = 0
    for vendor_profiles in profiles.values():
        for profile in vendor_profiles.values():
            total_profiles += 1
            filament_id = as_str(profile.get("filament_id"))
            if filament_id:
                by_id.setdefault(filament_id, []).append(profile)

    presets: Dict[str, Dict[str, Any]] = {}
    for filament_id, candidates in by_id.items():
        best = min(candidates, key=profile_priority)
        presets[filament_id] = build_preset(best, profiles)

    print(f"  Resolved {len(presets)} filament ids from {total_profiles} profiles "
          f"across {len(profiles)} vendors")

    incomplete = [
        fid
        for fid, preset in presets.items()
        if not preset["filament_type"] or not preset["nozzle_temp_max"]
    ]
    if incomplete:
        print(f"  Warning: {len(incomplete)} preset(s) missing type or temperature: "
              f"{', '.join(sorted(incomplete)[:10])}"
              f"{' ...' if len(incomplete) > 10 else ''}")

    # Filament ids that appear in printer configs but have no profile at all —
    # record them so a lookup returns something rather than failing outright.
    for model_id, printer_data in printers.items():
        for version, config in printer_data.get("firmware_versions", {}).items():
            for filament_id in config.get("auto_cali_not_support_filaments", []):
                if filament_id not in presets:
                    presets[filament_id] = {
                        "filament_id": filament_id,
                        "filament_name": "",
                        "filament_type": TYPE_BY_PREFIX.get(filament_id[:3], ""),
                        "nozzle_temp_min": 0,
                        "nozzle_temp_max": 0,
                        "bed_temp": 0,
                        "color": "",
                        "is_bambu": True,
                        "note": f"No profile found; seen in {model_id} v{version} "
                                f"auto_cali_not_support_filaments",
                    }

    # Blacklisted filaments are flagged in place so callers can warn.
    blacklist_file = repo_root / "resources" / "printers" / "filaments_blacklist.json"
    if blacklist_file.exists():
        with open(blacklist_file) as f:
            blacklist = json.load(f)
        for item in blacklist.get("filaments", []):
            filament_id = item.get("filament_id")
            if not filament_id:
                continue
            if filament_id in presets:
                presets[filament_id]["is_blacklisted"] = True
            else:
                presets[filament_id] = {
                    "filament_id": filament_id,
                    "filament_name": item.get("filament_name", ""),
                    "filament_type": item.get("filament_type", ""),
                    "nozzle_temp_min": 0,
                    "nozzle_temp_max": 0,
                    "bed_temp": 0,
                    "color": "",
                    "is_bambu": True,
                    "is_blacklisted": True,
                }

    # Clear out presets from a previous run so removed ids don't linger.
    for stale in output_dir.glob("*.json"):
        if stale.name != "index.json":
            stale.unlink()

    for filament_id, data in presets.items():
        with open(output_dir / f"{filament_id}.json", "w") as f:
            json.dump(data, f, indent=2)

    return presets
