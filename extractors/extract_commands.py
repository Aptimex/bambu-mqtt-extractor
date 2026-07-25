#!/usr/bin/env python3
"""
Extract command definitions from DeviceManager.cpp.

Each `MachineObject::command_*` method builds a JSON payload with statements
like `j["print"]["ams_id"] = tag_ams_id;`. To describe those fields correctly we
need the C++ type behind the right-hand side: `ams_id` and the nozzle
temperatures go on the wire as JSON numbers, while `tray_color` and
`tray_info_idx` go as strings. Inferring from the expression text alone marks
everything a string, so this resolves identifiers against the method signature
and its local declarations.

Whether a field is required is likewise read from the code: a field assigned
unconditionally from a parameter must be supplied by the caller, a field with a
literal value has a usable default, and a field assigned inside a conditional
(such as `cols`/`ctype`, which Bambu Studio only sends when a colour array was
given) is optional.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# C++ type -> JSON type. Checked as substrings, longest/most specific first.
CPP_TYPE_TO_JSON = [
    ("std::vector", "array"),
    ("std::string", "string"),
    ("char", "string"),
    ("bool", "boolean"),
    ("float", "number"),
    ("double", "number"),
    ("unsigned", "integer"),
    ("int", "integer"),
    ("long", "integer"),
    ("short", "integer"),
    ("size_t", "integer"),
]

INT_LITERAL = re.compile(r"^[+-]?\d+$")
FLOAT_LITERAL = re.compile(r"^[+-]?\d*\.\d+f?$")
IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")

# `type name` pairs: a declaration or a parameter.
DECLARATION = re.compile(
    r"\b((?:const\s+)?(?:unsigned\s+|signed\s+)?"
    r"(?:std::)?[A-Za-z_][\w:]*\s*(?:<[^<>;]*>)?)\s*[&*]?\s*"
    r"(\w+)\s*(?==|;|,|\)|$)"
)


def cpp_type_to_json(cpp_type: str) -> Optional[str]:
    """Map a C++ type spelling to a JSON type name."""
    lowered = cpp_type.lower()
    for needle, json_type in CPP_TYPE_TO_JSON:
        if needle in lowered:
            return json_type
    return None


def split_params(param_list: str) -> List[str]:
    """Split a C++ parameter list on top-level commas (ignoring <> and ())."""
    params: List[str] = []
    depth = 0
    current = ""
    for char in param_list:
        if char in "<(":
            depth += 1
        elif char in ">)":
            depth -= 1
        if char == "," and depth == 0:
            params.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        params.append(current)
    return params


def collect_var_types(signature_params: str, body: str) -> Dict[str, str]:
    """
    Map identifier -> JSON type for a method's parameters and local variables.

    Parameters take precedence: a local usually just copies a parameter, and a
    later shadowing declaration is far rarer than a plain copy.
    """
    var_types: Dict[str, str] = {}

    # Local declarations first, so parameters can overwrite them.
    # Split on braces as well as semicolons so the statement opening a block
    # isn't glued to the one before it.
    for statement in re.split(r"[;{}]", body):
        statement = statement.strip()
        if not statement or statement.startswith(("//", "#")):
            continue
        match = DECLARATION.match(statement)
        if match:
            json_type = cpp_type_to_json(match.group(1))
            if json_type:
                var_types.setdefault(match.group(2), json_type)

    for param in split_params(signature_params):
        param = param.strip()
        if not param:
            continue
        # Drop any default value so the name is the last token.
        param = param.split("=")[0].strip()
        match = DECLARATION.match(param + ";")
        if match:
            json_type = cpp_type_to_json(match.group(1))
            if json_type:
                var_types[match.group(2)] = json_type

    return var_types


def infer_type(expr: str, var_types: Dict[str, str] = None) -> str:
    """Infer the JSON type produced by a C++ expression."""
    var_types = var_types or {}
    expr = expr.strip()

    if expr.startswith('"'):
        return "string"
    if "std::to_string" in expr:
        return "string"
    if expr in ("true", "false"):
        return "boolean"
    if INT_LITERAL.match(expr):
        return "integer"
    if FLOAT_LITERAL.match(expr):
        return "number"
    if expr.startswith("{") or expr.startswith("["):
        return "array"

    if IDENTIFIER.match(expr) and expr in var_types:
        return var_types[expr]

    # A cast or call such as `(int)foo` or `std::stoi(x)`.
    cast = re.match(r"^\(\s*([A-Za-z_][\w:]*)\s*\)", expr)
    if cast:
        json_type = cpp_type_to_json(cast.group(1))
        if json_type:
            return json_type
    if expr.startswith(("std::stoi", "std::stol", "atoi")):
        return "integer"
    if expr.startswith(("std::stof", "std::stod")):
        return "number"

    # Member/accessor expressions: fall back to the trailing identifier.
    trailing = re.search(r"([A-Za-z_]\w*)\s*$", expr)
    if trailing and trailing.group(1) in var_types:
        return var_types[trailing.group(1)]

    return "string"


def infer_default(expr: str) -> Any:
    """Return the literal default a field is assigned, or None if it isn't one."""
    expr = expr.strip()
    if expr.startswith('"') and expr.endswith('"'):
        return expr[1:-1]
    if expr in ("true", "false"):
        return expr == "true"
    if INT_LITERAL.match(expr):
        return int(expr)
    if FLOAT_LITERAL.match(expr):
        return float(expr.rstrip("f"))
    return None


# Keywords that make the block they introduce conditional. A `try` block or a
# bare scope is unconditional: the statements inside always run.
CONDITIONAL_KEYWORD = re.compile(r"\b(if|else|for|while|switch|case|catch)\s*$")


def open_block_positions(body: str, position: int) -> List[int]:
    """Return the positions of the `{` of every block enclosing `position`."""
    stack: List[int] = []
    in_string = False
    in_char = False
    escaped = False

    for index in range(min(position, len(body))):
        char = body[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif in_string:
            if char == '"':
                in_string = False
        elif in_char:
            if char == "'":
                in_char = False
        elif char == '"':
            in_string = True
        elif char == "'":
            in_char = True
        elif char == "{":
            stack.append(index)
        elif char == "}":
            if stack:
                stack.pop()
    return stack


def conditional_blocks_at(body: str, position: int) -> Tuple[int, ...]:
    """
    Positions of the branching blocks enclosing `position`.

    Brace depth alone is not enough: Bambu Studio wraps whole command bodies in
    `try { ... }`, which would otherwise make every field look conditional. Only
    blocks introduced by a branching keyword are reported.
    """
    blocks: List[int] = []
    for brace_pos in open_block_positions(body, position):
        prefix = body[:brace_pos].rstrip()

        # Step back over a `(...)` condition so the keyword before it is visible.
        if prefix.endswith(")"):
            depth = 0
            index = len(prefix) - 1
            while index >= 0:
                if prefix[index] == ")":
                    depth += 1
                elif prefix[index] == "(":
                    depth -= 1
                    if depth == 0:
                        break
                index -= 1
            prefix = prefix[:index].rstrip() if index >= 0 else prefix

        if CONDITIONAL_KEYWORD.search(prefix):
            blocks.append(brace_pos)
    return tuple(blocks)


def find_method_body(content: str, start_brace: int) -> str:
    """
    Return the body between a method's braces, given its opening brace index.

    The outer braces are excluded so that a statement at the top level of the
    method sits at brace depth 0.
    """
    depth = 1
    pos = start_brace + 1
    while pos < len(content) and depth > 0:
        if content[pos] == "{":
            depth += 1
        elif content[pos] == "}":
            depth -= 1
        pos += 1
    return content[start_brace + 1: pos - 1]


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
    no_payload = []

    method_starts = list(
        re.finditer(r"int MachineObject::command_(\w+)\s*\(([^)]*)\)\s*{", content)
    )

    for match in method_starts:
        cmd_name = match.group(1)
        signature_params = match.group(2)
        start_brace = match.end() - 1
        body = find_method_body(content, start_brace)

        spec = parse_command_method(cmd_name, signature_params, body, enums, virtual_ids)
        if spec:
            commands[cmd_name] = spec
        else:
            # Methods that publish G-code rather than a JSON payload (e.g.
            # command_set_nozzle sends "M104 S..."). Emitting an empty spec for
            # these would let callers build a payload of {}.
            no_payload.append(cmd_name)

    # publish_gcode isn't named command_*, but it is the transport for several
    # AMS operations (refresh RFID, calibrate, select tray all send M620
    # G-code), so the gcode_line payload it builds has to be extractable.
    gcode_match = re.search(
        r"int MachineObject::publish_gcode\s*\(([^)]*)\)\s*{", content
    )
    if gcode_match:
        gcode_body = find_method_body(content, gcode_match.end() - 1)
        gcode_spec = parse_command_method(
            "gcode_line", gcode_match.group(1), gcode_body, enums, virtual_ids
        )
        if gcode_spec:
            commands["gcode_line"] = gcode_spec

    # Also pick up direct publish_json calls built from inline JSON literals.
    publish_pattern = r"publish_json\s*\(\s*json\s*\(\s*({[^}]+})\s*\)\s*\)"
    for match in re.finditer(publish_pattern, content, re.DOTALL):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        cmd = (payload.get("print", {}).get("command")
               or payload.get("system", {}).get("command")
               or payload.get("info", {}).get("command")
               or payload.get("pushing", {}).get("command"))
        if cmd and cmd not in commands:
            commands[cmd] = infer_spec_from_json(payload)

    # Clear out specs from a previous run so removed commands don't linger.
    for stale in output_dir.glob("*.json"):
        if stale.name != "index.json":
            stale.unlink()

    for cmd_name, spec in commands.items():
        with open(output_dir / f"{cmd_name}.json", "w") as f:
            json.dump(spec, f, indent=2)

    print(f"  Extracted {len(commands)} commands")
    if no_payload:
        print(f"  Skipped {len(no_payload)} method(s) that build no JSON payload: "
              f"{', '.join(sorted(no_payload))}")
    return commands


def parse_command_method(
    cmd_name: str, signature_params: str, body: str, enums: Dict, virtual_ids: Dict
) -> Dict:
    """Parse a command_* method body into a field spec."""
    spec = {
        "command": cmd_name,
        "category": infer_category(cmd_name),
        "required_fields": [],
        "optional_fields": [],
        "field_definitions": {},
        "sections": {},
    }

    var_types = collect_var_types(signature_params, body)

    json_pattern = r'j\["(\w+)"\]\["(\w+)"\]\s*=\s*([^;]+);'

    # Collect assignments first: whether a field is really optional depends on
    # how its enclosing blocks compare with every other field's.
    assignments: List[Dict[str, Any]] = []
    for match in re.finditer(json_pattern, body):
        assignments.append({
            "section": match.group(1),
            "field": match.group(2),
            "value_expr": match.group(3).strip(),
            "blocks": conditional_blocks_at(body, match.start()),
        })

    if not assignments:
        return None

    # A branch enclosing every assignment is a guard on the whole payload (e.g.
    # command_ams_control validates its action before building anything), not a
    # per-field condition. Ignore those blocks.
    guard_blocks = set(assignments[0]["blocks"])
    for assignment in assignments[1:]:
        guard_blocks &= set(assignment["blocks"])

    seen: Dict[Tuple[str, str], bool] = {}
    for assignment in assignments:
        section = assignment["section"]
        field = assignment["field"]
        conditional = bool(set(assignment["blocks"]) - guard_blocks)

        key = (section, field)
        if key in seen:
            # Assigned more than once (if/else branches). It is unconditional
            # overall if any one assignment is unconditional.
            if not conditional and seen[key]:
                seen[key] = False
                field_def = spec["field_definitions"].get(field)
                if field_def is not None:
                    field_def["conditional"] = False
            continue
        seen[key] = conditional

        field_spec = {
            "section": section,
            "type": infer_type(assignment["value_expr"], var_types),
            "description": "",
            "enum_ref": infer_enum_ref(field, enums, virtual_ids),
            "default": infer_default(assignment["value_expr"]),
            "conditional": conditional,
        }

        spec["sections"].setdefault(section, {})[field] = field_spec
        spec["field_definitions"][field] = field_spec

    # A field must be supplied by the caller when it is always sent and has no
    # literal default to fall back on.
    for field, field_def in spec["field_definitions"].items():
        caller_supplied = field_def["default"] is None and not field_def["conditional"]
        if caller_supplied:
            spec["required_fields"].append(field)
        else:
            spec["optional_fields"].append(field)

    return spec


def infer_enum_ref(field: str, enums: Dict, virtual_ids: Dict) -> Optional[str]:
    """Map a field name to an enum reference."""
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


def infer_category(cmd_name: str) -> str:
    """Infer the payload section a command belongs to."""
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


def infer_spec_from_json(payload: dict) -> Dict:
    """Infer a command spec from an inline JSON literal."""
    spec = {
        "command": "",
        "category": "print",
        "required_fields": [],
        "optional_fields": [],
        "field_definitions": {},
        "sections": {},
    }

    for section in ("print", "system", "info", "pushing"):
        if section in payload and "command" in payload[section]:
            spec["command"] = payload[section]["command"]
            spec["category"] = infer_category(spec["command"])
            break

    json_type_of = {
        bool: "boolean",
        int: "integer",
        float: "number",
        str: "string",
        list: "array",
        dict: "object",
    }

    for section_name, section_data in payload.items():
        if not isinstance(section_data, dict):
            continue
        spec["sections"][section_name] = {}
        for field, value in section_data.items():
            field_spec = {
                "section": section_name,
                "type": json_type_of.get(type(value), "string"),
                "description": "",
                "enum_ref": None,
                "default": value if not isinstance(value, (dict, list)) else None,
                "conditional": False,
            }
            spec["sections"][section_name][field] = field_spec
            spec["field_definitions"][field] = field_spec

            if field_spec["default"] is None:
                spec["required_fields"].append(field)
            else:
                spec["optional_fields"].append(field)

    return spec


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

    enums = {}
    for f in (config_dir / "enums").glob("*.json"):
        if f.name != "index.json":
            with open(f) as fp:
                enums[f.stem] = json.load(fp)

    virtual_ids = {}
    vid_file = config_dir / "virtual_ids.json"
    if vid_file.exists():
        with open(vid_file) as fp:
            virtual_ids = json.load(fp)

    extract(repo_root, config_dir, printers, enums, virtual_ids)
