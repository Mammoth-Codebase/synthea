"""Assemble the South African resource overlay that is placed ahead of the Synthea jar
on the Java classpath.

Synthea loads most of its reference data through ``Resources.getResource`` which returns
the first match on the classpath, so a directory holding South African versions of
``names.yml``, ``geography/*.csv``, ``providers/*.csv`` and so on overrides the US data
without rebuilding the jar. Disease modules that must replace built in modules are passed
separately through Synthea's ``-d`` local modules option, because every ``modules``
directory on the classpath is scanned and the jar's copy would win for duplicate names.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from synthea_za.config import DATA_DIR, GenerationConfig

# Files and folders copied from the package data directory onto the classpath overlay.
OVERLAY_ITEMS = [
    "names.yml",
    "language_lookup.json",
    "languages.json",
    "immunization_schedule.json",
    "geography",
    "providers",
    "payers",
    "costs",
    "modules",  # only lookup tables live here; JSON modules go through local_modules
    "templates",
]
LOCAL_MODULES_DIR = "local_modules"
MODULE_OVERRIDES_FILE = "module_overrides.properties"
BASE_PROPERTIES_FILE = "synthea_za.properties"


@dataclass
class OverlayPaths:
    overlay_dir: Path
    properties_file: Path
    local_modules_dir: Optional[Path]
    module_overrides_file: Optional[Path]


def _copy_item(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def dynamic_properties(config: GenerationConfig) -> Dict[str, str]:
    """Properties derived from the run configuration (merged over the base file)."""
    properties = {
        "exporter.years_of_history": str(config.years_of_history),
        "exporter.clinical_note.export": "true" if config.clinical_notes else "false",
        "exporter.csv.export": "true" if config.csv_export else "false",
        "generate.only_alive_patients": "true" if config.only_alive else "false",
    }
    properties.update(config.extra_properties)
    return properties


def write_properties(base_file: Path, target: Path, overrides: Dict[str, str],
                     module_overrides_file: Optional[Path]) -> None:
    """Write the base properties file with the given keys replaced or appended."""
    lines = base_file.read_text(encoding="utf-8").splitlines()
    remaining = dict(overrides)
    if module_overrides_file is not None:
        remaining["module_override"] = module_overrides_file.resolve().as_posix()
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key} = {remaining.pop(key)}")
                continue
        output.append(line)
    if remaining:
        output.append("")
        output.append("# values supplied by synthea-za at run time")
        for key, value in remaining.items():
            output.append(f"{key} = {value}")
    target.write_text("\n".join(output) + "\n", encoding="utf-8")


def build_overlay(config: GenerationConfig, data_dir: Path = DATA_DIR) -> OverlayPaths:
    """Create (or refresh) the overlay directory for a run and return its paths."""
    overlay_dir = config.overlay_dir
    if overlay_dir.exists():
        shutil.rmtree(overlay_dir)
    overlay_dir.mkdir(parents=True)

    for item in OVERLAY_ITEMS:
        _copy_item(data_dir / item, overlay_dir / item)

    local_modules: Optional[Path] = None
    source_modules = data_dir / LOCAL_MODULES_DIR
    if source_modules.is_dir() and any(source_modules.rglob("*.json")):
        local_modules = overlay_dir.parent / LOCAL_MODULES_DIR
        if local_modules.exists():
            shutil.rmtree(local_modules)
        shutil.copytree(source_modules, local_modules)

    module_overrides: Optional[Path] = None
    source_overrides = data_dir / MODULE_OVERRIDES_FILE
    if source_overrides.is_file():
        module_overrides = overlay_dir.parent / MODULE_OVERRIDES_FILE
        shutil.copy2(source_overrides, module_overrides)

    properties_file = overlay_dir.parent / BASE_PROPERTIES_FILE
    write_properties(data_dir / BASE_PROPERTIES_FILE, properties_file,
                     dynamic_properties(config), module_overrides)

    return OverlayPaths(
        overlay_dir=overlay_dir,
        properties_file=properties_file,
        local_modules_dir=local_modules,
        module_overrides_file=module_overrides,
    )
