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


def test_applied_versions_roundtrip(tmp_path):
    store = SelectionStore(tmp_path / "state.json", "repo-a")
    store.save_applied({"demo": {"version": "1.0.0"}})
    assert store.load_applied() == {"demo": {"version": "1.0.0"}}


def test_applied_versions_are_isolated_by_repo(tmp_path):
    path = tmp_path / "state.json"
    SelectionStore(path, "repo-a").save_applied({"demo": {"version": "1"}})
    SelectionStore(path, "repo-b").save_applied({"demo": {"version": "2"}})
    assert SelectionStore(path, "repo-a").load_applied() == {"demo": {"version": "1"}}
    assert SelectionStore(path, "repo-b").load_applied() == {"demo": {"version": "2"}}


def test_selection_and_applied_do_not_overwrite_each_other(tmp_path):
    path = tmp_path / "state.json"
    store = SelectionStore(path, "repo-a")
    store.save({"demo"})
    store.save_applied({"demo": {"version": "1.0.0"}})
    store.save({"demo", "other"})
    assert store.load_applied() == {"demo": {"version": "1.0.0"}}
