from modules.hotfix.webapi import normalize_selection


def test_normalize_selection_accepts_string_list():
    assert normalize_selection({"selected": ["a", "b", "b"]}) == ["a", "b"]


def test_normalize_selection_rejects_non_object():
    assert normalize_selection([]) is None


def test_normalize_selection_rejects_non_string_items():
    assert normalize_selection({"selected": ["a", 1]}) is None


def test_normalize_selection_allows_empty_list():
    assert normalize_selection({"selected": []}) == []
