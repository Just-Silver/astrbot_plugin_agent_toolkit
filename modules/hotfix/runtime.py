"""Orchestrate repository refresh, manifest loading and patch injection."""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
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
_VERSION_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


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
        self._applied: dict[str, Any] = {}
        self._applied_versions: dict[str, dict[str, str]] = {}
        self._outdated: set[str] = set()
        self._specs: list[PatchSpec] = []
        self._results: dict[str, dict[str, Any]] = {}
        self._selected: set[str] = set()
        self._commit = ""
        self._updated_at = ""
        self._error = ""
        self._enabled = False
        self._repo_url = ""
        self._ref = ""

    def apply(self, *, sync_repo: bool = True) -> None:
        """Refresh configuration state and (re)apply the selected patches.

        ``sync_repo=False`` reuses the local checkout, so saving a selection never
        waits on the network.
        """

        enabled, repo, ref = self._read_config()
        self._enabled, self._repo_url, self._ref = enabled, repo, ref
        self._error = ""
        self._results = {}
        self._specs = []
        self._applied = {}
        self._applied_versions = {}
        self._outdated = set()
        self._loader.revert_all()

        if not enabled:
            self._load_cached(repo)
            return

        if not repo.startswith("https://"):
            self._error = "repo must start with https://"
            self._logger.warning("[hotfix] %s", self._error)
            return

        directory = self._repo.directory(repo)
        if sync_repo:
            update = self._repo.update(repo, ref)
            self._commit = update.commit
            self._updated_at = update.updated_at
            if update.error:
                self._error = update.error
                self._logger.warning("[hotfix] repo update failed: %s", update.error)
                if not directory.exists():
                    return
            else:
                self._logger.info("[hotfix] repo updated: %s @ %s", repo_slug(repo), update.commit)
        elif not directory.exists():
            self._error = "repository cache is missing"
            return

        specs, warnings = load_manifest(directory)
        for warning in warnings:
            self._logger.warning("[hotfix] manifest: %s", warning)
        if warnings and not specs and not self._error:
            self._error = warnings[0]
        self._specs = specs

        store = self._store(repo)
        self._selected = store.load()
        self._applied_versions = store.load_applied()

        applied = skipped = failed = 0
        for spec in specs:
            result = self._evaluate(spec, store)
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

        reverted = self._loader.revert_all()
        for spec in reverted:
            self._logger.info("[hotfix] reverted: %s", spec.name)
        if not reverted:
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
            try:
                self._store(self._repo_url).save(normalized)
            except OSError as exc:
                self._error = f"cannot save selection: {exc}"
                self._logger.warning("[hotfix] %s", self._error)
        self._logger.info("[hotfix] selection saved: %s", ", ".join(normalized))
        self.apply(sync_repo=False)
        return self.status()

    def update(self, names: Sequence[str]) -> dict[str, Any]:
        """Adopt the latest repository version for the named patches."""

        if not self._repo_url:
            return self.status()
        latest = {spec.name: spec for spec in self._specs}
        store = self._store(self._repo_url)
        applied = store.load_applied()
        for name in names:
            spec = latest.get(name)
            if spec is None:
                continue
            applied[name] = {
                "version": spec.version,
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
            self._ensure_snapshot(spec)
        try:
            store.save_applied(applied)
        except OSError as exc:
            self._error = f"cannot save applied versions: {exc}"
            self._logger.warning("[hotfix] %s", self._error)
        self.apply(sync_repo=False)
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
        directory = self._repo.directory(repo)
        if not directory.exists():
            return
        # Disabled mode is expected and must stay silent: warnings here would
        # look like a failure on every normal startup.
        specs, _warnings = load_manifest(directory)
        self._specs = specs
        if repo.startswith("https://"):
            self._selected = self._store(repo).load()
        for spec in specs:
            self._results[spec.name] = self._result(spec, STATE_DISABLED, "")

    def _evaluate(self, spec: PatchSpec, store: SelectionStore) -> dict[str, Any]:
        if spec.name not in self._selected:
            return self._result(spec, STATE_DISABLED, "")
        current = astrbot_version()
        if not version_matches(spec.astrbot, current):
            reason = f"astrbot {current or 'unknown'} does not satisfy {spec.astrbot}"
            self._logger.info("[hotfix] skipped: %s: %s", spec.name, reason)
            return self._result(spec, STATE_INCOMPATIBLE, reason)

        recorded = self._applied_versions.get(spec.name, {})
        recorded_version = str(recorded.get("version") or "")
        outdated = bool(recorded_version and recorded_version != spec.version)
        effective = spec
        if outdated:
            snapshot = self._snapshot_dir(spec.name, recorded_version)
            if snapshot.is_dir():
                effective = self._from_snapshot(spec, snapshot)
            else:
                outdated = False

        try:
            patch = self._loader.load(effective)
        except Exception as exc:  # noqa: BLE001 - one patch must not break the rest
            self._logger.warning("[hotfix] failed: %s: %s", spec.name, exc)
            return self._result(spec, STATE_FAILED, str(exc))

        self._applied[spec.name] = patch
        if outdated:
            self._outdated.add(spec.name)
            self._logger.info(
                "[hotfix] applied: %s v%s (latest v%s available)",
                spec.name,
                recorded_version,
                spec.version,
            )
        else:
            self._remember_applied(spec, store)
            targets = ", ".join(f"{target.module}.{target.attribute}" for target in spec.targets)
            self._logger.info("[hotfix] applied: %s v%s -> %s", spec.name, spec.version, targets)

        result = self._result(
            spec,
            STATE_APPLIED,
            "",
            applied_at=datetime.now(timezone.utc).isoformat(),
        )
        result["applied_version"] = recorded_version if outdated else spec.version
        result["outdated"] = outdated
        return result

    def _remember_applied(self, spec: PatchSpec, store: SelectionStore) -> None:
        self._applied_versions[spec.name] = {
            "version": spec.version,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            store.save_applied(self._applied_versions)
        except OSError as exc:
            self._logger.warning("[hotfix] cannot save applied versions: %s", exc)
        self._ensure_snapshot(spec)

    def _ensure_snapshot(self, spec: PatchSpec) -> None:
        directory = spec.directory or spec.file.parent
        target = self._snapshot_dir(spec.name, spec.version)
        if target.is_dir():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(directory, target)
        except OSError as exc:
            self._logger.warning("[hotfix] cannot snapshot %s: %s", spec.name, exc)

    def _from_snapshot(self, spec: PatchSpec, snapshot: Path) -> PatchSpec:
        directory = spec.directory or spec.file.parent
        relative = spec.file.relative_to(directory) if spec.file.is_relative_to(directory) else Path(spec.file.name)
        return replace(spec, file=snapshot / relative, directory=snapshot)

    def _snapshot_dir(self, name: str, version: str) -> Path:
        slug = repo_slug(self._repo_url) if self._repo_url else "_"
        safe_version = _VERSION_SAFE.sub("_", version) or "0"
        return self._data_root / "applied" / slug / name / safe_version

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
            "latest_version": spec.version,
            "applied_version": "",
            "outdated": False,
            "changelog": list(spec.changelog),
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
