import json
from pathlib import Path

import pytest

from modules.hotfix.manifest import ManifestError, load_manifest, parse_root_manifest, version_matches


def write_patch(root: Path, dirname: str, payload: dict, files: dict[str, str] | None = None) -> None:
    patch_dir = root / "patches" / dirname
    patch_dir.mkdir(parents=True)
    (patch_dir / "patch.json").write_text(json.dumps(payload), encoding="utf-8")
    for name, content in (files or {}).items():
        (patch_dir / name).write_text(content, encoding="utf-8")


def test_parse_root_manifest_defaults_patches_dir():
    assert parse_root_manifest({"schema": 1}) == "patches"


def test_parse_root_manifest_accepts_custom_patches_dir():
    assert parse_root_manifest({"schema": 1, "patches_dir": "fixes"}) == "fixes"


def test_parse_root_manifest_rejects_unknown_schema():
    with pytest.raises(ManifestError):
        parse_root_manifest({"schema": 2})


def test_load_manifest_rejects_missing_root_manifest(tmp_path):
    specs, warnings = load_manifest(tmp_path)
    assert specs == []
    assert warnings


def test_load_manifest_reads_sorted_patches(tmp_path):
    (tmp_path / "hotfix.json").write_text('{"schema": 1}', encoding="utf-8")
    write_patch(tmp_path, "b-fix", {"file": "fix.py", "targets": [{"module": "m", "attribute": "a", "source": "s"}]}, {"fix.py": ""})
    write_patch(tmp_path, "a-fix", {"file": "fix.py", "targets": [{"module": "m", "attribute": "a", "source": "s"}]}, {"fix.py": ""})

    specs, warnings = load_manifest(tmp_path)

    assert [spec.name for spec in specs] == ["a-fix", "b-fix"]
    assert warnings == []


def test_load_manifest_rejects_path_traversal(tmp_path):
    (tmp_path / "hotfix.json").write_text('{"schema": 1}', encoding="utf-8")
    write_patch(tmp_path, "bad", {"file": "../../outside.py", "targets": [{"module": "m", "attribute": "a", "source": "s"}]})

    specs, warnings = load_manifest(tmp_path)

    assert specs == []
    assert any("outside.py" in item or "bad" in item for item in warnings)


def test_load_manifest_ignores_directory_without_patch_json(tmp_path):
    (tmp_path / "hotfix.json").write_text('{"schema": 1}', encoding="utf-8")
    (tmp_path / "patches" / "empty").mkdir(parents=True)

    specs, warnings = load_manifest(tmp_path)

    assert specs == []
    assert warnings == []


def test_load_manifest_keeps_first_on_duplicate_name(tmp_path):
    (tmp_path / "hotfix.json").write_text('{"schema": 1}', encoding="utf-8")
    target = [{"module": "m", "attribute": "a", "source": "s"}]
    write_patch(tmp_path, "first", {"name": "same", "file": "f.py", "targets": target}, {"f.py": ""})
    write_patch(tmp_path, "second", {"name": "same", "file": "f.py", "targets": target}, {"f.py": ""})

    specs, warnings = load_manifest(tmp_path)

    assert [spec.name for spec in specs] == ["same"]
    assert len(warnings) == 1


def test_import_as_defaults_to_target_parent_package(tmp_path):
    (tmp_path / "hotfix.json").write_text('{"schema": 1}', encoding="utf-8")
    write_patch(
        tmp_path,
        "forward-content",
        {"file": "f.py", "targets": [{"module": "pkg.sub.mod", "attribute": "A", "source": "A"}]},
        {"f.py": ""},
    )

    specs, _ = load_manifest(tmp_path)

    assert specs[0].import_as == "pkg.sub.hotfix_forward_content"


def test_version_matches():
    assert version_matches("", "4.29.4") is True
    assert version_matches(">=4.29,<5", "4.29.4") is True
    assert version_matches(">=5.0", "4.29.4") is False
    assert version_matches("not a spec", "4.29.4") is False
