#!/usr/bin/env python3
"""
Extract command definitions from DeviceManager.cpp
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List


def extract(repo_root: Path, config_dir: Path, printers: Dict, enums: Dict, virtual_ids: Dict) -> Dict[str, Any]:
    """Extract command definitions from DeviceManager.cpp."""
    devicemanager_cpp = repo_root / "src" / "slic3r" / "GUI" / "DeviceManager.cpp"

    output_dir = config_dir / "commands"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not devicemanager_cpp.exists():
        print(f"  Warning: {devicemanager_cpp} not found")
        return {}

    content = devicemanager_cpp.read_text()

    commands = {}

    # Find all command_* methods - use a more robust approach to find method boundaries
    # First find all command_ method starts
    method_starts = list(re.finditer(r'int MachineObject::command_(\w+)\s*\([^)]*\)\s*{', content))

    for i, match in enumerate(method_starts):
        cmd_name = match.group(1)
        start_pos = match.end() - 1  # Position of opening brace

        # Find matching closing brace by counting braces
        brace_count = 1
        pos = start_pos + 1
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1

        method_body = content[start_pos:pos-1]  # Exclude outer braces

        spec = parse_command_method(cmd_name, method_body, enums, virtual_ids)
        if spec:
            commands[cmd_name] = spec

    # Also find direct publish_json calls with inline JSON
    publish_pattern = r'publish_json\s*\(\s*json\s*\(\s*({[^}]+})\s*\)\s*\)'
    for match in re.finditer(publish_pattern, content, re.DOTALL):
        json_str = match.group(1)
        try:
            j = json.loads(json_str)
            cmd = (j.get("print", {}).get("command") or
                   j.get("system", {}).get("command") or
                   j.get("info", {}).get("command") or
                   j.get("pushing", {}).get("command"))
            if cmd and cmd not in commands:
                commands[cmd] = infer_spec_from_json(j)
        except:
            pass

    # Write individual command files
    for cmd_name, spec in commands.items():
        output_file = output_dir / f"{cmd_name}.json"
        with open(output_file, "w") as f:
            json.dump(spec, f, indent=2)

    return commands


def parse_command_method(cmd_name: str, body: str, enums: Dict, virtual_ids: Dict) -> Dict:
    """Parse a command_* method body to extract JSON structure."""
    spec = {
        "command": cmd_name,
        "category": infer_category(cmd_name),
        "required_fields": [],
        "optional_fields": [],
        "field_definitions": {},
        "sections": {}
    }

    # Find JSON object construction: j["section"]["field"] = value;
    json_pattern = r'j\["(\w+)"\]\["(\w+)"\]\s*=\s*([^;]+);'
    seen_fields = set()  # Track (section, field) to deduplicate
    for match in re.finditer(json_pattern, body):
        section = match.group(1)
        field = match.group(2)
        value_expr = match.group(3).strip()

        # Deduplicate: same field assigned multiple times (e.g., in if/else branches)
        key = (section, field)
        if key in seen_fields:
            continue
        seen_fields.add(key)

        if section not in spec["sections"]:
            spec["sections"][section] = {}

        field_spec = {
            "section": section,
            "type": infer_type(value_expr),
            "description": "",
            "enum_ref": infer_enum_ref(field, enums, virtual_ids),
            "default": infer_default(value_expr),
        }

        spec["sections"][section][field] = field_spec
        spec["field_definitions"][field] = field_spec

        # Heuristic: if value is a variable/parameter, it's required
        if is_required_field(value_expr):
            spec["required_fields"].append(field)
        else:
            spec["optional_fields"].append(field)

    # Also look for j["section"] = ... assignments
    section_pattern = r'j\["(\w+)"\]\s*=\s*([^;]+);'
    for match in re.finditer(section_pattern, body):
        section = match.group(1)
        value = match.group(2).strip()
        if value.startswith("{"):
            # Nested object
            pass

    # Special handling for sequence_id
    if "sequence_id" not in spec["field_definitions"]:
        for section in spec["sections"]:
            if "sequence_id" in spec["sections"][section]:
                spec["required_fields"].append("sequence_id")

    return spec


def infer_type(expr: str) -> str:
    """Infer JSON type from C++ expression."""
    expr = expr.strip()
    if expr.startswith('"') or 'std::to_string' in expr:
        return "string"
    if expr in ("true", "false"):
        return "boolean"
    if expr.isdigit() or (expr.startswith('-') and expr[1:].isdigit()):
        return "integer"
    if expr.startswith('{') or '[' in expr:
        return "array"
    return "string"


def infer_enum_ref(field: str, enums: Dict, virtual_ids: Dict) -> str:
    """Map field name to enum reference."""
    enum_map = {
        "ams_id": "virtual_ids",
        "tray_id": "virtual_ids",
        "slot_id": None,
        "tray_type": "filament_type",
        "tray_info_idx": "filament_presets",
        "fan_type": "FanType",
        "door_open_check": "DoorOpenCheckState",
        "nozzle_type": "NozzleFlowType",
        "extruder_id": "extruder_id",
        "speed_level": "DevPrintingSpeedLevel",
        "firmware_state": "DevFirmwareUpgradeState",
        "ams_status": "AmsStatusMain",
        "filament_step": "DevFilamentStep",
    }
    return enum_map.get(field)


def infer_default(expr: str) -> Any:
    """Infer default value from expression."""
    expr = expr.strip()
    if expr.startswith('"') and expr.endswith('"'):
        return expr[1:-1]
    if expr in ("true", "false"):
        return expr == "true"
    if expr.isdigit():
        return int(expr)
    if expr.startswith('-') and expr[1:].isdigit():
        return int(expr)
    return None


def is_required_field(expr: str) -> bool:
    """Heuristic: required if it's a parameter, member variable, or sequence_id."""
    required_indicators = [
        "m_", "get_", "set_", "sequence_id",
        "ams_id", "tray_id", "slot_id", "tray_info_idx",
        "setting_id", "tray_color", "tray_type",
        "nozzle_temp_min", "nozzle_temp_max",
        "fan_type", "door_open_check",
    ]
    return any(ind in expr for ind in required_indicators)


def infer_category(cmd_name: str) -> str:
    """Infer command category from name."""
    if cmd_name.startswith("ams_"):
        return "print"
    if cmd_name in ("pushall", "start", "stop"):
        return "pushing"
    if cmd_name in ("get_version", "get_access_code"):
        return "info"
    if cmd_name in ("clean_print_error", "skip_objects", "stop_print", "task_cancel"):
        return "print"
    if cmd_name in ("set_ctt", "control_fan", "set_door_open_check", "set_nozzle_info"):
        return "print"
    if cmd_name in ("extrusion_cali", "flow_cali", "vibration_cali", "bed_leveling", "first_layer_inspect"):
        return "calibration"
    return "print"


def infer_spec_from_json(j: dict) -> Dict:
    """Infer command spec from a JSON object."""
    spec = {
        "command": "",
        "category": "print",
        "required_fields": [],
        "optional_fields": [],
        "field_definitions": {},
        "sections": {}
    }

    # Find command field
    for section in ["print", "system", "info", "pushing"]:
        if section in j and "command" in j[section]:
            spec["command"] = j[section]["command"]
            spec["category"] = infer_category(spec["command"])
            break

    # Extract all fields
    for section_name, section_data in j.items():
        if isinstance(section_data, dict):
            spec["sections"][section_name] = {}
            for field, value in section_data.items():
                field_spec = {
                    "section": section_name,
                    "type": infer_type(str(value)),
                    "description": "",
                    "enum_ref": None,
                    "default": value if not isinstance(value, (dict, list)) else None,
                }
                spec["sections"][section_name][field] = field_spec
                spec["field_definitions"][field] = field_spec

                if field in ("command", "sequence_id") or field_spec["default"] is None:
                    spec["required_fields"].append(field)
                else:
                    spec["optional_fields"].append(field)

    return spec


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

    enums_dir = config_dir / "enums"
    enums = {}
    for f in enums_dir.glob("*.json"):
        if f.name != "index.json":
            with open(f) as fp:
                enums[f.stem] = json.load(fp)

    virtual_ids = {}
    vid_file = config_dir / "virtual_ids.json"
    if vid_file.exists():
        with open(vid_file) as fp:
            virtual_ids = json.load(fp)

    extract(repo_root, config_dir, printers, enums, virtual_ids)