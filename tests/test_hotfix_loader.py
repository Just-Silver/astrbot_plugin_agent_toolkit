import sys
import types
from pathlib import Path

import pytest

from modules.hotfix.loader import PatchLoadError, PatchLoader
from modules.hotfix.models import PatchSpec, Target


@pytest.fixture
def target_module(monkeypatch):
    module = types.ModuleType("fake_target")
    module.Widget = object
    monkeypatch.setitem(sys.modules, "fake_target", module)
    return module


def make_spec(tmp_path: Path, source: str = "Patched") -> PatchSpec:
    patch_file = tmp_path / "patched.py"
    patch_file.write_text(f"class {source}: pass\n", encoding="utf-8")
    return PatchSpec(
        name="demo",
        description="",
        file=patch_file,
        file_display="patches/demo/patched.py",
        astrbot="",
        import_as="fake_target.hotfix_demo",
        targets=(Target(module="fake_target", attribute="Widget", source=source),),
    )


def test_load_injects_and_revert_restores(tmp_path, target_module):
    original = target_module.Widget
    loader = PatchLoader()
    applied = loader.load(make_spec(tmp_path))

    assert target_module.Widget is not original
    loader.revert(applied)
    assert target_module.Widget is original


def test_revert_all_is_idempotent(tmp_path, target_module):
    loader = PatchLoader()
    original = target_module.Widget
    loader.load(make_spec(tmp_path))
    loader.revert_all()
    loader.revert_all()
    assert target_module.Widget is original


def test_missing_attribute_rolls_back_and_raises(tmp_path, target_module):
    original = target_module.Widget
    spec = make_spec(tmp_path)
    spec = PatchSpec(
        **{
            **spec.__dict__,
            "targets": (
                Target(module="fake_target", attribute="Widget", source="Patched"),
                Target(module="fake_target", attribute="Missing", source="Patched"),
            ),
        }
    )
    loader = PatchLoader()

    with pytest.raises(PatchLoadError):
        loader.load(spec)
    assert target_module.Widget is original


def test_module_import_error_cleans_sys_modules(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    spec = PatchSpec(
        name="bad",
        description="",
        file=bad,
        file_display="patches/bad/bad.py",
        astrbot="",
        import_as="fake_target.hotfix_bad",
        targets=(Target(module="fake_target", attribute="Widget", source="X"),),
    )
    with pytest.raises(PatchLoadError):
        PatchLoader().load(spec)
    assert "fake_target.hotfix_bad" not in sys.modules
