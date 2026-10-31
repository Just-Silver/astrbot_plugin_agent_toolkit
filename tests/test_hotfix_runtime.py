import types
from pathlib import Path

import modules.hotfix.runtime as runtime_module
from modules.hotfix.repo import RepoUpdate
from modules.hotfix.runtime import HotfixRuntime


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, message, *args):
        self.infos.append(message % args if args else message)

    def warning(self, message, *args):
        self.warnings.append(message % args if args else message)


def make_spec(name="demo", astrbot=""):
    return types.SimpleNamespace(
        name=name,
        astrbot=astrbot,
        targets=(),
        description="",
        file_display=f"patches/{name}/x.py",
        file=Path(f"/tmp/{name}.py"),
        import_as=f"pkg.hotfix_{name}",
    )


def make_runtime(tmp_path, monkeypatch, enabled=True, patches=None, selected=None):
    calls = []

    def fake_update(self, repo_url, ref=""):
        calls.append(repo_url)
        return RepoUpdate(True, "abc1234", "2026-10-31T00:00:00+00:00", "")

    monkeypatch.setattr(runtime_module.RepoCache, "update", fake_update)
    monkeypatch.setattr(runtime_module, "load_manifest", lambda root: (patches or [], []))
    monkeypatch.setattr(runtime_module, "astrbot_version", lambda: "4.29.4")
    config = {"hotfix": {"enabled": enabled, "repo": "https://github.com/o/r", "ref": ""}}
    runtime = HotfixRuntime(config, FakeLogger(), data_root=tmp_path)
    if selected is not None:
        runtime.set_selection(selected)
    return runtime, calls


def test_disabled_does_not_touch_git(tmp_path, monkeypatch):
    runtime, calls = make_runtime(tmp_path, monkeypatch, enabled=False)
    runtime.apply()
    assert calls == []


def test_unselected_patches_are_not_loaded(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "disabled"


def test_unselected_incompatible_patch_stays_disabled(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec(astrbot=">=5")])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "disabled"


def test_selected_incompatible_patch_is_reported(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec(astrbot=">=5")], selected=["demo"])
    runtime.apply()
    assert runtime.status()["patches"][0]["state"] == "incompatible"


def test_unknown_selection_names_are_ignored(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.set_selection(["ghost"])
    assert runtime.status()["patches"][0]["state"] == "disabled"


def test_loader_failure_is_reported_as_failed(tmp_path, monkeypatch):
    spec = make_spec()
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[spec], selected=["demo"])

    def boom(self, patch):
        raise RuntimeError("inject boom")

    monkeypatch.setattr(runtime_module.PatchLoader, "load", boom)
    runtime.apply()
    status = runtime.status()
    assert status["patches"][0]["state"] == "failed"
    assert "inject boom" in status["patches"][0]["reason"]


def test_writes_hotfix_log_lines(tmp_path, monkeypatch):
    runtime, _ = make_runtime(tmp_path, monkeypatch, patches=[make_spec()])
    runtime.apply()
    lines = runtime._logger.infos + runtime._logger.warnings
    assert any("[hotfix]" in line for line in lines)
