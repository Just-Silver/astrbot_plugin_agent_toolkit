"""Load patch modules and swap the declared attributes in memory."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from types import ModuleType

from .models import PatchSpec


class PatchLoadError(Exception):
    """Raised when a patch module or one of its targets cannot be applied."""


@dataclass
class AppliedPatch:
    spec: PatchSpec
    module: ModuleType
    targets: list[tuple[ModuleType, str, object]] = field(default_factory=list)


class PatchLoader:
    """Apply patches in order and remember the originals for rollback."""

    def __init__(self) -> None:
        self._applied: list[AppliedPatch] = []

    def load(self, spec: PatchSpec) -> AppliedPatch:
        patch_module = self._load_module(spec)
        replacements: list[tuple[ModuleType, str, object]] = []
        try:
            for target in spec.targets:
                target_module = importlib.import_module(target.module)
                value = getattr(patch_module, target.source)
                if not hasattr(target_module, target.attribute):
                    raise PatchLoadError(
                        f"{spec.name}: {target.module}.{target.attribute} does not exist"
                    )
                replacements.append(
                    (target_module, target.attribute, getattr(target_module, target.attribute))
                )
                setattr(target_module, target.attribute, value)
        except Exception as exc:
            self._restore(replacements)
            sys.modules.pop(spec.import_as, None)
            if isinstance(exc, PatchLoadError):
                raise
            raise PatchLoadError(f"{spec.name}: {exc}") from exc

        applied = AppliedPatch(spec=spec, module=patch_module, targets=replacements)
        self._applied.append(applied)
        return applied

    def revert(self, applied: AppliedPatch) -> None:
        self._restore(applied.targets)
        sys.modules.pop(applied.spec.import_as, None)

    def revert_all(self) -> None:
        while self._applied:
            self.revert(self._applied.pop())

    def _load_module(self, spec: PatchSpec) -> ModuleType:
        parent = spec.import_as.rsplit(".", 1)[0] if "." in spec.import_as else ""
        try:
            if parent:
                importlib.import_module(parent)
            module_spec = importlib.util.spec_from_file_location(spec.import_as, spec.file)
            if module_spec is None or module_spec.loader is None:
                raise ImportError(f"cannot load {spec.file}")
            module = importlib.util.module_from_spec(module_spec)
            sys.modules[spec.import_as] = module
            module_spec.loader.exec_module(module)
            return module
        except Exception as exc:
            sys.modules.pop(spec.import_as, None)
            raise PatchLoadError(f"{spec.name}: {exc}") from exc

    @staticmethod
    def _restore(replacements: list[tuple[ModuleType, str, object]]) -> None:
        for target_module, attribute, original in reversed(replacements):
            try:
                setattr(target_module, attribute, original)
            except Exception:  # noqa: BLE001 - restoring must not stop the rest
                continue
