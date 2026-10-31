"""Persist which patches the user enabled for one repository."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class SelectionStore:
    """Read and write the per-repository patch selection."""

    def __init__(self, path: Path, slug: str) -> None:
        self._path = path
        self._slug = slug

    def load(self) -> set[str]:
        entry = self._entry()
        selected = entry.get("selected", [])
        if not isinstance(selected, list):
            return set()
        return {item for item in selected if isinstance(item, str) and item}

    def save(self, selected: Iterable[str]) -> None:
        data = self._read()
        entry = self._entry(data)
        entry["selected"] = sorted({item for item in selected if isinstance(item, str) and item})
        self._write_entry(data, entry)

    def load_applied(self) -> dict[str, dict[str, str]]:
        entry = self._entry()
        applied = entry.get("applied", {})
        if not isinstance(applied, dict):
            return {}
        return {
            name: {key: value for key, value in record.items() if isinstance(key, str) and isinstance(value, str)}
            for name, record in applied.items()
            if isinstance(name, str) and isinstance(record, dict)
        }

    def save_applied(self, applied: Mapping[str, Mapping[str, str]]) -> None:
        data = self._read()
        entry = self._entry(data)
        entry["applied"] = {name: dict(record) for name, record in applied.items()}
        self._write_entry(data, entry)

    def _entry(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        source = data if data is not None else self._read()
        repositories = source.get("repos")
        if not isinstance(repositories, dict):
            return {}
        entry = repositories.get(self._slug)
        return entry if isinstance(entry, dict) else {}

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_entry(self, data: dict[str, Any], entry: dict[str, Any]) -> None:
        repositories = data.get("repos")
        if not isinstance(repositories, dict):
            repositories = {}
        repositories[self._slug] = entry
        data["repos"] = repositories
        self._write(data)

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self._path)
