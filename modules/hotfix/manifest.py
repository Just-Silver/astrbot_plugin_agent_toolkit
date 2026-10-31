"""Parse and validate the patch repository manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion

from .models import PatchSpec, Target

DEFAULT_PATCHES_DIR = "patches"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")


class ManifestError(Exception):
    """Raised when a manifest entry cannot be used."""


def parse_root_manifest(data: object) -> str:
    """Return the patches directory declared by the repository root manifest."""

    if not isinstance(data, dict):
        raise ManifestError("root manifest must be a JSON object")
    if data.get("schema") != 1:
        raise ManifestError(f"unsupported manifest schema: {data.get('schema')!r}")
    patches_dir = data.get("patches_dir", DEFAULT_PATCHES_DIR)
    if not isinstance(patches_dir, str) or not patches_dir.strip():
        raise ManifestError("patches_dir must be a non-empty string")
    if "/" in patches_dir or "\\" in patches_dir or patches_dir in {".", ".."}:
        raise ManifestError(f"patches_dir must be a single directory name: {patches_dir!r}")
    return patches_dir


def load_manifest(repo_root: Path) -> tuple[list[PatchSpec], list[str]]:
    """Load all usable patches, sorted by directory name.

    A broken root manifest or a broken patch only produces warnings; the rest of
    the repository stays usable.
    """

    warnings: list[str] = []
    root_manifest = repo_root / "hotfix.json"
    try:
        payload = json.loads(root_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"root manifest unavailable: {exc}"]
    try:
        patches_dir = parse_root_manifest(payload)
    except ManifestError as exc:
        return [], [str(exc)]

    base = repo_root / patches_dir
    if not base.is_dir():
        return [], []

    specs: list[PatchSpec] = []
    seen: set[str] = set()
    for patch_dir in sorted((path for path in base.iterdir() if path.is_dir()), key=lambda path: path.name):
        manifest_path = patch_dir / "patch.json"
        if not manifest_path.is_file():
            continue
        try:
            spec = _load_patch(patch_dir, manifest_path)
        except ManifestError as exc:
            warnings.append(f"{patch_dir.name}: {exc}")
            continue
        if spec.name in seen:
            warnings.append(f"{patch_dir.name}: duplicate patch name {spec.name!r}")
            continue
        seen.add(spec.name)
        specs.append(spec)
    return specs, warnings


def version_matches(spec: str, current: str) -> bool:
    """Return whether *current* satisfies a PEP 440 range; an empty range matches."""

    if not spec.strip():
        return True
    try:
        return SpecifierSet(spec).contains(current, prereleases=True)
    except (InvalidSpecifier, InvalidVersion):
        return False


def _load_patch(patch_dir: Path, manifest_path: Path) -> PatchSpec:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"patch.json unavailable: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("patch.json must be a JSON object")

    name = data.get("name") or patch_dir.name
    if not isinstance(name, str) or not name.strip():
        raise ManifestError("name must be a non-empty string")

    description = data.get("description") or ""
    if not isinstance(description, str):
        raise ManifestError("description must be a string")

    astrbot = data.get("astrbot") or ""
    if not isinstance(astrbot, str):
        raise ManifestError("astrbot must be a string")

    targets = _parse_targets(data.get("targets"))

    raw_file = data.get("file")
    if not isinstance(raw_file, str) or not raw_file.strip():
        raise ManifestError("file must be a non-empty string")
    file_path = (patch_dir / raw_file).resolve()
    if not file_path.is_relative_to(patch_dir.resolve()):
        raise ManifestError(f"file escapes the patch directory: {raw_file}")
    if not file_path.is_file():
        raise ManifestError(f"file not found: {raw_file}")

    import_as = data.get("import_as")
    if import_as is None:
        import_as = _default_import_as(targets[0].module, name)
    if not isinstance(import_as, str) or not import_as.strip():
        raise ManifestError("import_as must be a non-empty string")

    return PatchSpec(
        name=name,
        description=description,
        file=file_path,
        file_display=f"{patch_dir.parent.name}/{patch_dir.name}/{raw_file}",
        astrbot=astrbot,
        import_as=import_as,
        targets=targets,
    )


def _parse_targets(raw_targets: Any) -> tuple[Target, ...]:
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ManifestError("targets must be a non-empty list")
    targets: list[Target] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            raise ManifestError("each target must be an object")
        values = []
        for field in ("module", "attribute", "source"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ManifestError(f"target {field} must be a non-empty string")
            values.append(value)
        targets.append(Target(module=values[0], attribute=values[1], source=values[2]))
    return tuple(targets)


def _default_import_as(module: str, name: str) -> str:
    safe_name = _SAFE_NAME.sub("_", name)
    parent = module.rsplit(".", 1)[0] if "." in module else ""
    if not parent:
        return f"hotfix_{safe_name}"
    return f"{parent}.hotfix_{safe_name}"
