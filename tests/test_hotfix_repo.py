import subprocess

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
    (directory / ".git").mkdir(parents=True)
    cache.update("https://github.com/owner/repo", "main")
    assert any("fetch" in call for call in calls)
    assert any("reset" in call for call in calls)


def test_sha_ref_clones_then_fetches_sha(tmp_path):
    calls = []
    sha = "a" * 40
    cache = RepoCache(tmp_path, runner=ok_run(calls))
    cache.update("https://github.com/owner/repo", sha)

    assert "--branch" not in calls[0]
    assert any("fetch" in call and sha in call for call in calls)
    assert any("reset" in call for call in calls)


def test_timeout_reports_error(tmp_path):
    def timeout(args, timeout_value):
        raise subprocess.TimeoutExpired(args, timeout_value)

    result = RepoCache(tmp_path, runner=timeout).update("https://github.com/owner/repo")
    assert result.ok is False
    assert result.error


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
