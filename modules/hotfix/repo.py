"""Keep a shallow git clone of the patch repository under the plugin data dir."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)
_INVALID_SLUG = re.compile(r"[^a-z0-9_-]+")


class RepoError(Exception):
    """Raised when a git command exits non-zero."""


@dataclass(frozen=True)
class RepoUpdate:
    ok: bool
    commit: str
    updated_at: str
    error: str
    changed: bool = True


def repo_slug(repo_url: str) -> str:
    """Return a filesystem-safe name for the repository."""

    path = repo_url.rstrip("/").removesuffix(".git")
    parts = [part for part in path.split("/") if part]
    tail = "_".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")
    slug = _INVALID_SLUG.sub("-", tail.lower())
    return slug.strip("-")


class RepoCache:
    """Clone or refresh the patch repository once per plugin load."""

    def __init__(
        self,
        root: Path,
        timeout: float = 60.0,
        runner: Callable[[list[str], float], Any] | None = None,
    ) -> None:
        self._root = root
        self._timeout = timeout
        self._runner = runner or _default_runner

    def directory(self, repo_url: str) -> Path:
        return self._root / repo_slug(repo_url)

    def update(self, repo_url: str, ref: str = "") -> RepoUpdate:
        directory = self.directory(repo_url)
        updated_at = datetime.now(timezone.utc).isoformat()
        try:
            if not (directory / ".git").exists():
                # A leftover directory without .git is a broken cache; rebuilding
                # it is cheaper than debugging git's confusing errors later.
                if directory.exists():
                    shutil.rmtree(directory)
                args = ["git", "clone", "--depth", "1", "--single-branch"]
                if ref and not _SHA.fullmatch(ref):
                    args.extend(["--branch", ref])
                args.extend([repo_url, str(directory)])
                self._call(args)
                if ref and _SHA.fullmatch(ref):
                    self._call(["git", "-C", str(directory), "fetch", "--depth", "1", "origin", ref])
                    self._call(["git", "-C", str(directory), "reset", "--hard", "FETCH_HEAD"])
            else:
                before = self._resolve(directory, "HEAD")
                fetch = ["git", "-C", str(directory), "fetch", "--depth", "1", "origin"]
                if ref:
                    fetch.append(ref)
                self._call(fetch)
                remote = self._resolve(directory, "FETCH_HEAD")
                if before and remote and before == remote:
                    # Nothing new on the remote: leave the checkout and the
                    # injected classes untouched.
                    return RepoUpdate(True, before[:7], updated_at, "", changed=False)
                self._call(["git", "-C", str(directory), "reset", "--hard", "FETCH_HEAD"])
            return RepoUpdate(True, self._head(directory), updated_at, "")
        except (RepoError, OSError, subprocess.TimeoutExpired) as exc:
            message = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else "git failed"
            return RepoUpdate(False, self._head(directory), updated_at, message)

    def _call(self, args: list[str]) -> None:
        result = self._runner(args, self._timeout)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
            raise RepoError(message)

    def _head(self, directory: Path) -> str:
        return self._resolve(directory, "HEAD")[:7]

    def _resolve(self, directory: Path, revision: str) -> str:
        if not (directory / ".git").exists():
            return ""
        try:
            result = self._runner(
                ["git", "-C", str(directory), "rev-parse", revision],
                self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        return (result.stdout or "").strip()


def _default_runner(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
        check=False,
    )
