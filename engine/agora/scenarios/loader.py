"""Load and validate scenario YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import ScenarioSpec


def load_scenario(path: Path) -> ScenarioSpec:
    """Parse a YAML file and return a validated ScenarioSpec.

    Raises ValueError with details if the file is invalid.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Scenario file must be a YAML mapping, got {type(raw).__name__}")

    try:
        return ScenarioSpec.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid scenario '{path.name}':\n{exc}") from exc
