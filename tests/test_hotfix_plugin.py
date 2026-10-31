import json
from pathlib import Path


def test_conf_schema_declares_hotfix_group():
    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    hotfix = schema["hotfix"]
    assert hotfix["type"] == "object"
    assert hotfix["items"]["enabled"]["default"] is False
    assert hotfix["items"]["repo"]["default"].startswith("https://")
