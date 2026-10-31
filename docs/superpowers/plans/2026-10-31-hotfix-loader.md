<!-- 职责：远程热补丁加载器与管理视图的分任务实现计划；不写设计取舍理由（见 spec）与发布流程。 -->

# 远程热补丁加载器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让插件从配置的 GitHub 仓库拉取补丁清单，按用户在独立 WebUI 视图里的选择注入 AstrBot 运行中的模块，并支持还原、刷新与失败降级。

**Architecture:** `modules/hotfix/` 子包分层：`manifest` 解析与校验仓库清单，`repo` 管理 git 缓存，`selection` 持久化开关选择，`loader` 负责模块加载/注入/还原，`runtime` 编排流程并产出状态快照，`webapi` 暴露管理接口。前端在现有 `webui/` 中新增独立入口 `hotfix.html`，构建到 `views/hotfix/`。

**Tech Stack:** Python 3.10+ / AstrBot 插件 API / `packaging` / pytest；Vue 3 + Vite 6 + Naive UI。

**Spec:** `docs/superpowers/specs/2026-10-31-hotfix-loader-design.md`

## Global Constraints

- 补丁默认全部关闭，只有用户在管理界面显式开启后才加载
- `repo` 只接受 `https://`；清单 `file` 必须位于补丁目录内
- 任何失败都不抛出到插件生命周期，`web_fetch` 始终可用
- 配置项只在原生配置页修改，WebUI 只读
- 插件入口必须是根 `main.py`（AstrBot 约定）
- 日志统一前缀 `[hotfix]`
- 前端构建产物提交到 `views/hotfix/`，与 `views/toolkit/` 并列

## Review Focus

- 清单 `file` 含 `..` 或绝对路径时，必须拒绝该补丁，不能读到仓库外文件
- 选择状态文件损坏或只写了一半时，视为全部关闭，不影响插件启动
- git 拉取失败但本地缓存可用时，用缓存继续；无缓存时安静跳过
- 补丁模块 import 抛错、或某个 target 属性不存在时，该补丁必须完整回滚，不能留下半套注入
- 未被选择或总开关关闭时，绝不能加载补丁文件（远程代码不得在未授权时执行）

---

### Task 1: 数据模型与清单校验

**Files:**
- Create: `modules/hotfix/__init__.py`
- Create: `modules/hotfix/models.py`
- Create: `modules/hotfix/manifest.py`
- Test: `tests/test_hotfix_manifest.py`

**Interfaces:**
- Produces:
  - `models.Target(module: str, attribute: str, source: str)`（frozen dataclass）
  - `models.PatchSpec(name, description, file: Path, file_display: str, astrbot: str, import_as: str, targets: tuple[Target, ...])`（frozen dataclass）
  - `models.STATE_APPLIED/DISABLED/INCOMPATIBLE/FAILED` 四个字符串常量
  - `manifest.ManifestError(Exception)`
  - `manifest.parse_root_manifest(data: object) -> str` 返回 `patches_dir`
  - `manifest.load_manifest(repo_root: Path) -> tuple[list[PatchSpec], list[str]]` 返回按目录名排序的补丁与警告
  - `manifest.version_matches(spec: str, current: str) -> bool`，`spec` 为空返回 `True`，解析失败返回 `False`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_manifest.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_manifest.py -v`
Expected: 全部 FAIL（模块不存在）

- [ ] **Step 3: 实现 models.py 与 manifest.py**

`models.py` 定义 dataclass 与状态常量。`manifest.py` 要点：

- `parse_root_manifest`：`schema` 必须为 `1`；`patches_dir` 缺省 `"patches"`，必须是单层目录名（不含 `/`、`\`、`..`）
- `load_manifest`：读 `hotfix.json` 调 `parse_root_manifest`；扫描 `<patches_dir>/*/patch.json`；按目录名 `sorted()`；每个补丁校验：
  - `file` 非空、相对路径，`(patch_dir / file).resolve()` 必须仍在 `patch_dir.resolve()` 内
  - `targets` 非空，每项 `module`/`attribute`/`source` 非空字符串
  - `name` 缺省取目录名；重复时保留先出现的并追加 warning
  - `astrbot` 为空字符串表示不限制
  - `import_as` 缺省为 `f"{targets[0].module.rsplit('.', 1)[0]}.hotfix_{safe_name}"`，`safe_name` 把非 `[A-Za-z0-9_]` 换成 `_`
  - 单个补丁校验失败只追加 warning，不中断其他补丁
- `version_matches` 用 `packaging.specifiers.SpecifierSet`，`contains(current, prereleases=True)`

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_hotfix_manifest.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/hotfix/__init__.py modules/hotfix/models.py modules/hotfix/manifest.py tests/test_hotfix_manifest.py
git commit -m "feat(hotfix): 清单解析与校验"
```

---

### Task 2: 选择状态持久化

**Files:**
- Create: `modules/hotfix/selection.py`
- Test: `tests/test_hotfix_selection.py`

**Interfaces:**
- Consumes: 无
- Produces: `selection.SelectionStore(path: Path, slug: str)`，方法 `load() -> set[str]`、`save(selected: Iterable[str]) -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_selection.py
from modules.hotfix.selection import SelectionStore


def test_default_is_empty(tmp_path):
    store = SelectionStore(tmp_path / "state.json", "repo-a")
    assert store.load() == set()


def test_save_and_load_roundtrip(tmp_path):
    store = SelectionStore(tmp_path / "state.json", "repo-a")
    store.save({"forward-content"})
    assert store.load() == {"forward-content"}


def test_repos_are_isolated(tmp_path):
    path = tmp_path / "state.json"
    SelectionStore(path, "repo-a").save({"a"})
    SelectionStore(path, "repo-b").save({"b"})
    assert SelectionStore(path, "repo-a").load() == {"a"}
    assert SelectionStore(path, "repo-b").load() == {"b"}


def test_corrupt_file_means_all_off(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert SelectionStore(path, "repo-a").load() == set()


def test_save_is_atomic_replace(tmp_path):
    path = tmp_path / "state.json"
    store = SelectionStore(path, "repo-a")
    store.save({"a"})
    store.save({"b"})
    assert store.load() == {"b"}
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_selection.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 selection.py**

结构为 `{"repos": {slug: {"selected": [...]}}}`。`save` 用同目录临时文件 + `os.replace`；`load` 捕获 `OSError`/`json.JSONDecodeError`/类型错误并返回空集。目录不存在时 `mkdir(parents=True, exist_ok=True)`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_hotfix_selection.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/hotfix/selection.py tests/test_hotfix_selection.py
git commit -m "feat(hotfix): 选择状态持久化"
```

---

### Task 3: 仓库缓存与 git 更新

**Files:**
- Create: `modules/hotfix/repo.py`
- Test: `tests/test_hotfix_repo.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `repo.RepoUpdate(ok: bool, commit: str, updated_at: str, error: str)`（frozen dataclass）
  - `repo.repo_slug(repo_url: str) -> str`
  - `repo.RepoCache(root: Path, timeout: float = 60.0, runner: Callable | None = None)`，方法 `directory(repo_url: str) -> Path`、`update(repo_url: str, ref: str = "") -> RepoUpdate`
  - `runner` 签名为 `(args: list[str], timeout: float) -> subprocess.CompletedProcess`，默认 `subprocess.run(..., capture_output=True, text=True, env=...)`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_repo.py
import subprocess
from pathlib import Path

from modules.hotfix.repo import RepoCache, repo_slug


def ok_run(calls):
    def runner(args, timeout):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")
    return runner


def test_repo_slug():
    assert repo_slug("https://github.com/Just-Silver/AstrBot-hotfix") == "just-silver_astrbot-hotfix"


def test_first_update_clones(tmp_path):
    calls = []
    cache = RepoCache(tmp_path, runner=ok_run(calls))
    result = cache.update("https://github.com/owner/repo")
    assert calls[0][:2] == ["git", "clone"]
    assert result.ok is True


def test_existing_directory_fetches_and_resets(tmp_path):
    calls = []
    cache = RepoCache(tmp_path, runner=ok_run(calls))
    directory = cache.directory("https://github.com/owner/repo")
    directory.mkdir(parents=True)
    cache.update("https://github.com/owner/repo", "main")
    assert any(call[:2] == ["git", "fetch"] for call in calls)
    assert any("reset" in call for call in calls)


def test_network_failure_reports_error(tmp_path):
    def failing(args, timeout):
        return subprocess.CompletedProcess(args, 1, "", "boom")

    cache = RepoCache(tmp_path, runner=failing)
    result = cache.update("https://github.com/owner/repo")
    assert result.ok is False
    assert "boom" in result.error


def test_existing_cache_is_usable_after_failure(tmp_path):
    cache = RepoCache(tmp_path, runner=ok_run([]))
    directory = cache.directory("https://github.com/owner/repo")
    (directory / ".git").mkdir(parents=True)

    def failing(args, timeout):
        return subprocess.CompletedProcess(args, 1, "", "offline")

    result = RepoCache(tmp_path, runner=failing).update("https://github.com/owner/repo")
    assert result.ok is False
    assert directory.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_repo.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 repo.py**

- `repo_slug`：取 URL 路径的 `owner/repo`，转小写，非 `[a-z0-9]` 换 `-`
- `directory`：`root / repo_slug(repo_url)`
- `update`：
  - 目录不存在：`git clone --depth 1 --single-branch`，`ref` 非空且不是 40 位十六进制时追加 `--branch ref`
  - 目录存在：`git -C <dir> fetch --depth 1 origin [ref]`，然后 `git -C <dir> reset --hard FETCH_HEAD`
  - 结束后 `git -C <dir> rev-parse HEAD`，`commit` 取前 7 位
  - 子进程环境加 `GIT_TERMINAL_PROMPT=0`；捕获 `subprocess.TimeoutExpired` 与 `OSError`
  - 失败：`ok=False`，`error` 为 stderr 首行（截断 200 字符），`commit` 仍尝试读现有 HEAD（读不到为空）
  - `updated_at` 用 `datetime.now(timezone.utc).isoformat()`

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_hotfix_repo.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/hotfix/repo.py tests/test_hotfix_repo.py
git commit -m "feat(hotfix): git 仓库缓存与更新"
```

---

### Task 4: 补丁加载、注入与还原

**Files:**
- Create: `modules/hotfix/loader.py`
- Test: `tests/test_hotfix_loader.py`

**Interfaces:**
- Consumes: `models.PatchSpec`、`models.Target`
- Produces:
  - `loader.PatchLoadError(Exception)`
  - `loader.AppliedPatch(spec: PatchSpec, module: ModuleType, targets: list[tuple[ModuleType, str, object]])`（普通 dataclass）
  - `loader.PatchLoader()`，方法 `load(spec: PatchSpec) -> AppliedPatch`、`revert(applied: AppliedPatch) -> None`、`revert_all() -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_loader.py
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
    spec = PatchSpec(**{**spec.__dict__, "targets": (
        Target(module="fake_target", attribute="Widget", source="Patched"),
        Target(module="fake_target", attribute="Missing", source="Patched"),
    )})
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_loader.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 loader.py**

要点：

- `load`：先 `importlib.import_module(spec.import_as.rsplit(".", 1)[0])`；用 `spec_from_file_location` + `module_from_spec`，写入 `sys.modules[spec.import_as]` 后 `exec_module`
- 对每个 target：`importlib.import_module(target.module)`，`getattr(spec_module, target.source)`，`hasattr(target_module, target.attribute)` 为假则抛错
- 任一 target 失败：按已注入记录逆序 `setattr` 还原，删除 `sys.modules[spec.import_as]`，抛 `PatchLoadError`
- `revert`：逆序还原；`revert_all` 从后往前调用 `revert`，清空列表

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_hotfix_loader.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/hotfix/loader.py tests/test_hotfix_loader.py
git commit -m "feat(hotfix): 补丁加载、注入与还原"
```

---

### Task 5: 运行时编排

**Files:**
- Create: `modules/hotfix/runtime.py`
- Test: `tests/test_hotfix_runtime.py`

**Interfaces:**
- Consumes: Task 1–4 的 `load_manifest`、`version_matches`、`SelectionStore`、`RepoCache`、`PatchLoader`、`models.STATE_*`
- Produces: `runtime.HotfixRuntime(config: Mapping[str, Any], logger, data_root: Path | None = None)`，方法 `apply()`、`revert()`、`refresh() -> dict`、`set_selection(selected: Sequence[str]) -> dict`、`status() -> dict`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_runtime.py
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
    runtime, _ = make_runtime(
        tmp_path, monkeypatch, patches=[make_spec(astrbot=">=5")], selected=["demo"]
    )
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_runtime.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 runtime.py**

要点：

- 配置读取：`config.get("hotfix", {})`，`enabled`/`repo`/`ref`；`repo` 非 `https://` 开头时记 warning 并当作未启用
- 模块级 `astrbot_version() -> str`：`from astrbot import __version__` 并返回；导入失败返回 `""`
- 数据根：`data_root` 缺省 `Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_agent_toolkit" / "hotfix"`；`state.json` 与 `<slug>/` 都在其下
- 构造时保存 `self._logger` 供测试与日志使用
- `apply()`：
  1. 未启用：只读本地缓存清单与选择，生成快照，不调用 git、不加载补丁
  2. `repo.update()`；失败且无缓存目录：记 error，生成空快照
  3. `load_manifest()`；失败：记 error
  4. 读 `SelectionStore`
  5. 先 `revert()`，再按选择逐个：未选择 → `disabled`；版本不匹配 → `incompatible`；`PatchLoader.load()` 成功 → `applied`，失败 → `failed` + reason
  6. 记录 `commit`、`updated_at`、`applied_at`，输出以 `[hotfix]` 开头的 summary 日志
- `status()` 返回 spec 约定的 dict（`enabled/repo/ref/commit/updated_at/astrbot_version/patches/error`），`targets` 渲染成 `module.attribute` 字符串列表
- `set_selection()`：归一化为清单内已知名字 → 保存 → `apply()` → 返回 `status()`；日志 `[hotfix] selection saved: a, b`
- `refresh()`：强制 `repo.update()` 后 `apply()` → 返回 `status()`
- `revert()`：`PatchLoader.revert_all()`，清空 applied 列表，日志 `[hotfix] reverted`

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_hotfix_runtime.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/hotfix/runtime.py tests/test_hotfix_runtime.py
git commit -m "feat(hotfix): 运行时编排与状态快照"
```

---

### Task 6: 管理接口

**Files:**
- Create: `modules/hotfix/webapi.py`
- Test: `tests/test_hotfix_webapi.py`

**Interfaces:**
- Consumes: `runtime.HotfixRuntime`
- Produces:
  - `webapi.normalize_selection(payload: object) -> list[str] | None`（非法返回 `None`）
  - `webapi.build_status(runtime) -> dict`（直接返回 `runtime.status()`）
  - `webapi.handle_status(plugin)` / `handle_selection(plugin)` / `handle_refresh(plugin)`（async）
  - `webapi.register_hotfix_routes(context, plugin, plugin_name: str) -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_webapi.py
from modules.hotfix.webapi import normalize_selection


def test_normalize_selection_accepts_string_list():
    assert normalize_selection({"selected": ["a", "b", "b"]}) == ["a", "b"]


def test_normalize_selection_rejects_non_object():
    assert normalize_selection([]) is None


def test_normalize_selection_rejects_non_string_items():
    assert normalize_selection({"selected": ["a", 1]}) is None


def test_normalize_selection_allows_empty_list():
    assert normalize_selection({"selected": []}) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_webapi.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 webapi.py**

- 用 `from astrbot.api.web import error_response, json_response, request`
- `handle_status`：`json_response(plugin._hotfix.status())`
- `handle_selection`：`payload = await request.json(default=None)`；`normalize_selection` 为 `None` 或 runtime 未启用 → `error_response(..., status_code=400)`；否则 `json_response(runtime.set_selection(names))`
- `handle_refresh`：未启用 → 400；否则 `json_response(runtime.refresh())`
- `register_hotfix_routes` 注册三条路径（GET status、POST selection、POST refresh）
- 测试只覆盖纯函数；handler 由 Task 7 的手工验收覆盖

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_hotfix_webapi.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add modules/hotfix/webapi.py tests/test_hotfix_webapi.py
git commit -m "feat(hotfix): 管理接口"
```

---

### Task 7: 插件接线与配置

**Files:**
- Modify: `main.py`
- Modify: `_conf_schema.json`
- Test: `tests/test_hotfix_plugin.py`

**Interfaces:**
- Consumes: `HotfixRuntime`、`register_hotfix_routes`
- Produces: `Main._hotfix` 实例；`terminate()` 调用 `revert()`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotfix_plugin.py
import json
from pathlib import Path


def test_conf_schema_declares_hotfix_group():
    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    hotfix = schema["hotfix"]
    assert hotfix["type"] == "object"
    assert hotfix["items"]["enabled"]["default"] is False
    assert hotfix["items"]["repo"]["default"].startswith("https://")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_hotfix_plugin.py -v`
Expected: KeyError（`hotfix` 不存在）

- [ ] **Step 3: 实现配置与接线**

`_conf_schema.json` 追加：

```json
"hotfix": {
  "description": "远程热补丁",
  "type": "object",
  "items": {
    "enabled": {"description": "启用远程热补丁", "type": "bool", "default": false},
    "repo": {"description": "热补丁仓库地址，仅支持 https", "type": "string", "default": "https://github.com/Just-Silver/AstrBot-hotfix"},
    "ref": {"description": "分支、标签或提交；留空跟随默认分支", "type": "string", "default": ""}
  }
}
```

`main.py`：

- import `HotfixRuntime`、`register_hotfix_routes`
- `__init__` 中在 web_fetch 注册前：`register_hotfix_routes(self.context, self, PLUGIN_NAME)`
- `self._hotfix = HotfixRuntime(self.config, logger)`，在 web_fetch 分支之后调用 `self._hotfix.apply()`（不受 `enabled`（web_fetch 开关）影响）
- `terminate()` 中 `self._hotfix.revert()`
- 热补丁初始化与 `web_fetch` 的 `enabled` 互不影响

- [ ] **Step 4: 运行全部测试**

Run: `python -m pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add main.py _conf_schema.json tests/test_hotfix_plugin.py
git commit -m "feat(hotfix): 接入插件生命周期与配置"
```

---

### Task 8: 前端管理视图

**Files:**
- Modify: `webui/src/bridge.ts`
- Create: `webui/hotfix.html`
- Create: `webui/src/hotfix.ts`
- Create: `webui/src/HotfixApp.vue`
- Create: `webui/src/components/HotfixList.vue`
- Create: `webui/src/components/HotfixSummary.vue`
- Create: `webui/vite.hotfix.config.ts`
- Modify: `webui/package.json`
- Modify: `.astrbot-plugin/i18n/zh-CN.json`
- Modify: `.astrbot-plugin/i18n/en-US.json`
- Build output: `views/hotfix/`

**Interfaces:**
- Consumes: Task 6 的 `GET/{plugin_name}/hotfix/status`、`POST .../selection`、`POST .../refresh`
- Produces: 视图 `hotfix`，供 AstrBot 插件页发现

- [ ] **Step 1: 扩展 bridge 类型与方法**

```ts
export interface HotfixTargetInfo { ... }
export interface HotfixPatch {
  name: string
  description: string
  file: string
  astrbot: string
  targets: string[]
  selected: boolean
  state: 'applied' | 'disabled' | 'incompatible' | 'failed'
  reason: string
  applied_at: string
}
export interface HotfixStatus {
  enabled: boolean
  repo: string
  ref: string
  commit: string
  updated_at: string
  astrbot_version: string
  patches: HotfixPatch[]
  error: string
}
export async function getHotfixStatus(): Promise<HotfixStatus>
export async function applyHotfixSelection(selected: string[]): Promise<HotfixStatus>
export async function refreshHotfix(): Promise<HotfixStatus>
```

接口路径用 `bridge.apiGet('hotfix/status')`、`apiPost('hotfix/selection', {selected})`、`apiPost('hotfix/refresh')`。

- [ ] **Step 2: 实现组件**

- `HotfixSummary.vue`：props `total/applied/pending`，渲染 `N 个补丁 · M 个已应用 · K 个待应用`
- `HotfixList.vue`：props `patches`、`selectedOverride`；emit `toggle(name)`；每行可展开显示 `targets`、`file`、`applied_at`；状态色：applied 绿、incompatible 黄、failed 红、disabled 灰；`pending` 行加标记
- `HotfixApp.vue`：加载 status、错误提示条、汇总、列表、底部「放弃 / 应用更改（N）」、顶部「刷新」；`enabled=false` 时禁用操作并显示提示

- [ ] **Step 3: 多入口构建**

`vite.hotfix.config.ts` 与现有 `vite.config.ts` 同构，改 `rollupOptions.input` 为 `hotfix.html`、`outDir` 为 `../views/hotfix`。`package.json` 的 `build` 改为：

```json
"build": "vue-tsc --noEmit && vite build && vite build --config vite.hotfix.config.ts"
```

- [ ] **Step 4: i18n**

`zh-CN.json` 与 `en-US.json` 增加 `views.hotfix.*`：`title`、`description`、`refresh`、`summary`、`apply`、`discard`、`pending`、`status_applied`、`status_disabled`、`status_incompatible`、`status_failed`、`not_enabled`、`error_fetch`、`empty`、`targets`、`file`、`applied_at`。

- [ ] **Step 5: 构建并提交产物**

```bash
cd webui
npm install
npm run build
cd ..
git add webui views/hotfix .astrbot-plugin/i18n
git commit -m "feat(hotfix): 管理视图与多入口构建"
```

Expected: `views/hotfix/index.html` 与 `views/hotfix/assets/*` 生成，`views/toolkit/` 仍可构建

---

### Task 9: 文档

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Create: `docs/research/astrbot-hotfix-repository.md`

**Interfaces:**
- Consumes: 全部已完成功能
- Produces: 用户可见的配置、使用与清单格式说明

- [ ] **Step 1: 更新 README**

增加「热补丁」一节：功能说明、配置三项、管理视图入口、默认关闭、失败降级、上游修复后停止使用的提醒。

- [ ] **Step 2: 补仓库侧文档**

`docs/research/astrbot-hotfix-repository.md`：补丁仓库布局（`hotfix.json` + `patches/<name>/patch.json` + 补丁文件）、字段表、示例，并链接到 spec 作为字段唯一事实源。在 `docs/README.md` 文档地图登记。

- [ ] **Step 3: 提交**

```bash
git add README.md docs/README.md docs/research/astrbot-hotfix-repository.md
git commit -m "docs: 热补丁使用与仓库清单格式"
```

---

### Task 10: 补丁仓库改造（跨仓库）

**Files:**
- Modify: `E:\Code\Projects\Applications\AstrBot\forks\AstrBot-hotfix`（独立仓库）
- Create: `hotfix.json`
- Create: `patches/forward-content/patch.json`
- Move: `forward-content/*` → `patches/forward-content/`

**Interfaces:**
- Consumes: Task 1 定义的清单格式（以 spec 为唯一事实源）
- Produces: 可被本插件加载的补丁仓库布局

- [ ] **Step 1: 调整目录**

```text
hotfix.json
patches/forward-content/
├── patch.json
├── chain_parser.py
└── check-upstream.ps1
```

`patch.json`：

```json
{
  "name": "forward-content",
  "description": "引用合并转发时读不到转发正文",
  "file": "chain_parser.py",
  "astrbot": ">=4.29,<5",
  "targets": [
    {
      "module": "astrbot.core.utils.quoted_message.extractor",
      "attribute": "OneBotPayloadParser",
      "source": "OneBotPayloadParser"
    }
  ]
}
```

- [ ] **Step 2: 更新该仓库 README**

挂载方式保留为兜底，新增「插件远程加载」说明与目录结构；字段定义指向本插件 spec 的链接。

- [ ] **Step 3: 提交**

```bash
git add hotfix.json patches forward-content README.md
git commit -m "feat: 支持插件远程热补丁加载"
```

- [ ] **Step 4: 手工验收**

在 AstrBot 中安装本插件，配置 `hotfix.enabled=true`，打开「热补丁」视图确认列表出现 `forward-content`，开启并应用后引用一条合并转发，输出带 `<转发>` 标签。
