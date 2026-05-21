from __future__ import annotations

import ast
import pathlib
import tomllib


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_pyproject_declares_jarvis_package_metadata():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["project"]["name"] == "jarvis"
    assert data["project"]["requires-python"] == ">=3.11"
    assert "mss>=9.0.0" in data["project"]["dependencies"]
    assert "pillow>=10.0.0" in data["project"]["dependencies"]
    assert "ocr" in data["project"]["optional-dependencies"]
    assert "hands" in data["project"]["optional-dependencies"]


def test_requirements_include_websockets_for_remote_bridge():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert any(line.startswith("websockets") for line in requirements)


def test_setup_py_delegates_to_setuptools_setup():
    tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))

    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert any(getattr(call.func, "id", "") == "setup" for call in calls)


def test_readme_documents_rawvision_quick_start():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "RawVision" in readme
    assert "pip install rawvision" in readme
    assert "RawVision.capture()" in readme
