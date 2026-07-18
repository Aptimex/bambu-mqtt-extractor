#!/usr/bin/env python3
"""
Main entry point for Bambu Studio MQTT payload config extraction.
Extracts all configuration data from Bambu Studio C++ codebase and generates
versioned JSON config files for the Python MQTT library.

Usage:
    python3 extract_all.py REPO_PATH [OUTPUT_DIR]

    REPO_PATH: Path to Bambu Studio repository (required)
    OUTPUT_DIR: Path to output config directory (default: ./config)
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from extractors import (
    extract_printers,
    extract_enums,
    extract_commands,
    extract_virtual_ids,
    extract_feature_flags,
    extract_filament_presets,
    generate_indices,
    generate_schema_version,
)


def main():
    parser = argparse.ArgumentParser(
        description="Extract Bambu Studio MQTT payload configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 extract_all.py /path/to/BambuStudio
  python3 extract_all.py /path/to/BambuStudio /path/to/output
  python3 extract_all.py /path/to/BambuStudio ./my-config
        """
    )
    parser.add_argument(
        "repo_path",
        type=Path,
        help="Path to Bambu Studio repository (required)"
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        default="./config",
        help="Path to output config directory (default: ./config)"
    )
    args = parser.parse_args()

    repo_root = args.repo_path.resolve()
    config_dir = args.output_dir.resolve()

    # Verify repo path
    if not repo_root.exists():
        parser.error(f"Repository path does not exist: {repo_root}")
    if not (repo_root / "resources" / "printers").exists():
        parser.error(f"'{repo_root}' does not appear to be a Bambu Studio repo (missing resources/printers)")

    print(f"Repo root: {repo_root}")
    print(f"Config output: {config_dir}")

    # Ensure output directories exist
    for subdir in ["printers", "commands", "enums", "filament_presets"]:
        (config_dir / subdir).mkdir(parents=True, exist_ok=True)

    print("\n=== Extracting printers ===")
    printers = extract_printers.extract(repo_root, config_dir)

    print("\n=== Extracting enums ===")
    enums = extract_enums.extract(repo_root, config_dir)

    print("\n=== Extracting virtual IDs ===")
    virtual_ids = extract_virtual_ids.extract(repo_root, config_dir)

    print("\n=== Extracting commands ===")
    commands = extract_commands.extract(repo_root, config_dir, printers, enums, virtual_ids)

    print("\n=== Extracting filament presets ===")
    presets = extract_filament_presets.extract(repo_root, config_dir, printers)

    print("\n=== Extracting feature flags ===")
    feature_flags = extract_feature_flags.extract(repo_root, config_dir, printers)

    print("\n=== Generating indices ===")
    generate_indices.generate(config_dir)

    print("\n=== Generating schema version ===")
    generate_schema_version.generate(config_dir, repo_root)

    print("\n=== Extraction complete ===")
    print(f"Config files written to: {config_dir}")


if __name__ == "__main__":
    main()