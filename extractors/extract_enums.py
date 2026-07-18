#!/usr/bin/env python3
"""
Extract enum definitions from C++ header files.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any


def extract(repo_root: Path, config_dir: Path) -> Dict[str, Any]:
    """Extract all enums from C++ headers."""
    devdefs_h = repo_root / "src" / "slic3r" / "GUI" / "DeviceCore" / "DevDefs.h"
    devconfigutil_h = repo_root / "src" / "slic3r" / "GUI" / "DeviceCore" / "DevConfigUtil.h"
    bambu_networking_hpp = repo_root / "src" / "slic3r" / "Utils" / "bambu_networking.hpp"

    output_dir = config_dir / "enums"
    output_dir.mkdir(parents=True, exist_ok=True)

    enums = {}

    # DevDefs.h enums
    if devdefs_h.exists():
        content = devdefs_h.read_text()
        enums.update(parse_cpp_enum(content, "PrinterArch"))
        enums.update(parse_cpp_enum(content, "PrinterSeries"))
        enums.update(parse_cpp_enum(content, "DevAmsType"))
        enums.update(parse_cpp_enum(content, "NozzleFlowType"))
        enums.update(parse_cpp_enum(content, "NozzleDiameterType"))
        enums.update(parse_cpp_enum(content, "DevPrintingSpeedLevel"))
        enums.update(parse_cpp_enum(content, "DevFirmwareUpgradeState"))
        enums.update(parse_cpp_enum(content, "AmsStatusMain"))
        enums.update(parse_cpp_enum(content, "DevFilamentStep"))
        enums.update(parse_cpp_enum(content, "PrintFromType", namespace="GUI"))

    # DevConfigUtil.h enums
    if devconfigutil_h.exists():
        content = devconfigutil_h.read_text()
        enums.update(parse_cpp_enum(content, "ToolHeadComponent"))
        enums.update(parse_cpp_enum(content, "ToolHeadNameCase"))

    # bambu_networking.hpp enums
    if bambu_networking_hpp.exists():
        content = bambu_networking_hpp.read_text()
        enums.update(parse_cpp_enum(content, "MessageFlag"))
        enums.update(parse_cpp_enum(content, "SendingPrintJobStage"))
        enums.update(parse_cpp_enum(content, "PublishingStage"))
        enums.update(parse_cpp_enum(content, "BindJobStage"))
        enums.update(parse_cpp_enum(content, "ConnectStatus"))

    # Write individual enum files
    for enum_name, values in enums.items():
        output_file = output_dir / f"{enum_name}.json"
        with open(output_file, "w") as f:
            json.dump({
                "name": enum_name,
                "values": values
            }, f, indent=2)

    return enums


def parse_cpp_enum(content: str, enum_name: str, namespace: str = "") -> Dict[str, Any]:
    """Parse a C++ enum definition."""
    # Match enum (class) Name [: type] {
    if namespace:
        pattern = rf"(?:enum\s+(?:class\s+)?{namespace}::{enum_name}|enum\s+(?:class\s+)?{enum_name})"
    else:
        pattern = rf"enum\s+(?:class\s+)?{enum_name}"

    match = re.search(pattern, content)
    if not match:
        return {}

    # Find the opening brace after the enum name
    start = content.find('{', match.end())
    if start == -1:
        return {}

    # Find matching closing brace
    brace_count = 1
    end = start + 1
    for i, ch in enumerate(content[start+1:], start+1):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i
                break

    enum_body = content[start+1:end]

    # Remove inline comments before parsing
    enum_body = re.sub(r'//.*', '', enum_body)

    # Parse enum values
    values = {}
    current_val = 0
    for line in enum_body.split(','):
        line = line.strip()
        if not line:
            continue

        if '=' in line:
            name, val = line.split('=', 1)
            name = name.strip()
            val = val.strip().rstrip(',')
            try:
                current_val = int(val, 0)
            except:
                pass
        else:
            name = line.rstrip(',')

        if name:
            values[name] = current_val
            current_val += 1

    return {enum_name: values}


if __name__ == "__main__":
    import sys
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
    config_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "config"
    extract(repo_root, config_dir)