"""Persist which patches the user enabled for one repository."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class SelectionStore:
    """Read and write the per-repository patch selection."""

    def __init__(self, path: Path, slug: str) -> None:
        self._path = path
        self._slug = slug

    def load(self) -> set[str]:
        repository = self._read().get("repos", {})
        if not isinstance(repository, dict):
            return set()
        entry = repository.get(self._slug, {})
        if not isinstance(entry, dict):
            return set()
        selected = entry.get("selected", [])
        if not isinstance(selected, list):
            return set()
        return {item for item in selected if isinstance(item, str) and item}

    def save(self, selected: Iterable[str]) -> None:
        data = self._read()
        repositories = data.get("repos")
        if not isinstance(repositories, dict):
            repositories = {}
        repositories[self._slug] = {"selected": sorted({item for item in selected if isinstance(item, str) and item})}
        data["repos"] = repositories
        self._write(data)

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self._path)
