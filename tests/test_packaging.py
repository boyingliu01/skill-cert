"""Guard: the data directories the engine reads at runtime must ship in the wheel.

``Grader._load_judge_template`` degrades to an empty prompt and the harness
taskgen/judge raise FileNotFoundError when ``prompts/`` is missing — both only
happen for *installed* (non-editable) users, so the unit suite cannot see it.
These tests pin the build configuration instead.
"""

from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib", reason="TOML parsing needs Python 3.11+")

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

DATA_DIRS = {
    "prompts": ["judge.md", "judge-output.md", "harness-taskgen.md", "harness-judge.md"],
    "templates": ["minimum-evals.json"],
    "schemas": ["report.schema.json"],
}


def test_package_finder_covers_the_data_directories():
    find = PYPROJECT["tool"]["setuptools"]["packages"]["find"]

    assert find["namespaces"] is True, (
        "data dirs have no __init__.py; the default finder drops them"
    )
    included = " ".join(find["include"])
    for name in DATA_DIRS:
        assert f"{name}*" in included


def test_package_data_declares_each_data_directory():
    package_data = PYPROJECT["tool"]["setuptools"]["package-data"]

    assert package_data["prompts"] == ["*.md"]
    assert set(package_data["templates"]) == {"*.json"}
    assert set(package_data["schemas"]) == {"*.json"}


@pytest.mark.parametrize("directory", sorted(DATA_DIRS))
def test_referenced_data_files_exist_in_the_repository(directory):
    missing = [f for f in DATA_DIRS[directory] if not (ROOT / directory / f).is_file()]
    assert not missing, f"{directory}/ lacks {missing} — the include pattern would ship nothing"
