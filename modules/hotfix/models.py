"""Shared types for the remote hotfix runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATE_APPLIED = "applied"
STATE_DISABLED = "disabled"
STATE_INCOMPATIBLE = "incompatible"
STATE_FAILED = "failed"


@dataclass(frozen=True)
class Target:
    """One attribute replacement inside a target module."""

    module: str
    attribute: str
    source: str


@dataclass(frozen=True)
class PatchSpec:
    """One patch declared by ``patches/<name>/patch.json``."""

    name: str
    description: str
    file: Path
    file_display: str
    astrbot: str
    import_as: str
    targets: tuple[Target, ...]
