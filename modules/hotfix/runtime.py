"""Orchestrate repository refresh, manifest loading and patch injection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .loader import PatchLoader
from .manifest import load_manifest, version_matches
from .models import (
    STATE_APPLIED,
    STATE_DISABLED,
    STATE_FAILED,
    STATE_INCOMPATIBLE,
    PatchSpec,
)
from .repo import RepoCache, repo_slug
from .selection import SelectionStore

PLUGIN_DATA_DIR = "astrbot_plugin_agent_toolkit"


def astrbot_version() -> str:
    """Return the running AstrBot version, or an empty string when unavailable."""

    try:
        from astrbot import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001 - running outside AstrBot must not break the plugin
        return ""


def _default_data_root() -> Path:
    from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

    return Path(get_astrbot_plugin_data_path()) / PLUGIN_DATA_DIR / "hotfix"


class HotfixRuntime:
    """Apply the selected patches once per plugin load and expose a status snapshot."""

    def __init__(
        self,
        config: Mapping[str, Any],
        logger: Any,
        data_root: Path | None = None,
        repo_timeout: float = 60.0,
    ) -> None:
        self._config = config
        self._logger = logger
        self._data_root = Path(data_root) if data_root is not None else _default_data_root()
        self._repo = RepoCache(self._data_root, timeout=repo_timeout)
        self._loader = PatchLoader()
        self._specs: list[PatchSpec] = []
        self._results: dict[str, dict[str, Any]] = {}
        self._selected: set[str] = set()
        self._commit = ""
        self._updated_at = ""
        self._error = ""
        self._enabled = False
        self._repo_url = ""
        self._ref = ""

    def apply(self) -> None:
        """Refresh configuration state and (re)apply the selected patches."""

        enabled, repo, ref = self._read_config()
        self._enabled, self._repo_url, self._ref = enabled, repo, ref
        self._commit = ""
        self._updated_at = ""
        self._error = ""
        self._results = {}
        self._specs = []
        self._loader.revert_all()

        if not enabled:
            self._load_cached(repo)
            self._logger.info("[hotfix] disabled")
            return

        if not repo.startswith("https://"):
            self._error = "repo must start with https://"
            self._logger.warning("[hotfix] %s", self._error)
            return

        update = self._repo.update(repo, ref)
        self._commit = update.commit
        self._updated_at = update.updated_at
        directory = self._repo.directory(repo)
        if update.error:
            self._logger.warning("[hotfix] repo update failed: %s", update.error)
            if not directory.exists():
                self._error = update.error
                return
        else:
            self._logger.info("[hotfix] repo updated: %s @ %s", repo_slug(repo), update.commit)

        specs, warnings = load_manifest(directory)
        for warning in warnings:
            self._logger.warning("[hotfix] manifest: %s", warning)
        if warnings and not specs:
            self._error = warnings[0]
        self._specs = specs
        self._selected = self._store(repo).load()

        applied = skipped = failed = 0
        for spec in specs:
            result = self._evaluate(spec)
            self._results[spec.name] = result
            if result["state"] == STATE_APPLIED:
                applied += 1
            elif result["state"] == STATE_FAILED:
                failed += 1
            else:
                skipped += 1
        self._logger.info(
            "[hotfix] summary: %d applied, %d skipped, %d failed",
            applied,
            skipped,
            failed,
        )

    def revert(self) -> None:
        """Undo every injected patch."""

        self._loader.revert_all()
        self._logger.info("[hotfix] reverted")

    def refresh(self) -> dict[str, Any]:
        """Force a repository refresh and reapply the current selection."""

        self.apply()
        return self.status()

    def set_selection(self, selected: Sequence[str]) -> dict[str, Any]:
        """Persist the enabled patch names and reapply immediately."""

        if not self._specs:
            self.apply()
        known = {spec.name for spec in self._specs}
        normalized = sorted({name for name in selected if isinstance(name, str) and name in known})
        if self._repo_url:
            self._store(self._repo_url).save(normalized)
        self._logger.info("[hotfix] selection saved: %s", ", ".join(normalized))
        self.apply()
        return self.status()

    def status(self) -> dict[str, Any]:
        """Return the snapshot consumed by the management view."""

        return {
            "enabled": self._enabled,
            "repo": self._repo_url,
            "ref": self._ref,
            "commit": self._commit,
            "updated_at": self._updated_at,
            "astrbot_version": astrbot_version(),
            "patches": [self._results[spec.name] for spec in self._specs if spec.name in self._results],
            "error": self._error,
        }

    def _load_cached(self, repo: str) -> None:
        if not repo:
            return
        specs, warnings = load_manifest(self._repo.directory(repo))
        for warning in warnings:
            self._logger.warning("[hotfix] manifest: %s", warning)
        self._specs = specs
        if repo.startswith("https://"):
            self._selected = self._store(repo).load()
        for spec in specs:
            self._results[spec.name] = self._result(spec, STATE_DISABLED, "")

    def _evaluate(self, spec: PatchSpec) -> dict[str, Any]:
        if spec.name not in self._selected:
            return self._result(spec, STATE_DISABLED, "")
        current = astrbot_version()
        if not version_matches(spec.astrbot, current):
            reason = f"astrbot {current or 'unknown'} does not satisfy {spec.astrbot}"
            return self._result(spec, STATE_INCOMPATIBLE, reason)
        try:
            self._loader.load(spec)
        except Exception as exc:  # noqa: BLE001 - one patch must not break the rest
            return self._result(spec, STATE_FAILED, str(exc))
        return self._result(
            spec,
            STATE_APPLIED,
            "",
            applied_at=datetime.now(timezone.utc).isoformat(),
        )

    def _result(
        self,
        spec: PatchSpec,
        state: str,
        reason: str,
        applied_at: str = "",
    ) -> dict[str, Any]:
        return {
            "name": spec.name,
            "description": spec.description,
            "file": spec.file_display,
            "astrbot": spec.astrbot,
            "targets": [f"{target.module}.{target.attribute}" for target in spec.targets],
            "selected": spec.name in self._selected,
            "state": state,
            "reason": reason,
            "applied_at": applied_at,
        }

    def _store(self, repo: str) -> SelectionStore:
        return SelectionStore(self._data_root / "state.json", repo_slug(repo))

    def _read_config(self) -> tuple[bool, str, str]:
        raw: Any = self._config.get("hotfix", {}) if isinstance(self._config, Mapping) else {}
        if not isinstance(raw, Mapping):
            return False, "", ""
        enabled = bool(raw.get("enabled", False))
        repo = raw.get("repo", "")
        ref = raw.get("ref", "")
        return (
            enabled,
            repo.strip() if isinstance(repo, str) else "",
            ref.strip() if isinstance(ref, str) else "",
        )
