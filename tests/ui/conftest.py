"""
conftest for tests/ui/.

Re-applies the same env var setup as the root conftest.py (see the note
there on why this must happen per-directory), plus a defensive
QT_QPA_PLATFORM default since this directory is the one that actually
constructs Qt widgets (via pytest-qt's `qtbot` fixture) and must never
require a real display.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if "CACHE_MANAGER_CACHE_DIR" not in os.environ:
    import atexit
    import shutil
    import tempfile

    _tmp = tempfile.mkdtemp(prefix="cache_manager_ui_")
    os.environ["CACHE_MANAGER_CACHE_DIR"] = os.path.join(_tmp, "cache")
    os.environ["CACHE_MANAGER_CONFIGS_DIR"] = os.path.join(_tmp, "configs")
    os.environ["CACHE_MANAGER_BACKUPS_DIR"] = os.path.join(_tmp, "backups")
    os.makedirs(os.environ["CACHE_MANAGER_CACHE_DIR"], exist_ok=True)
    os.makedirs(os.environ["CACHE_MANAGER_CONFIGS_DIR"], exist_ok=True)
    os.makedirs(os.environ["CACHE_MANAGER_BACKUPS_DIR"], exist_ok=True)
    _src = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "config_example.json")
    if os.path.isfile(_src):
        shutil.copy(_src, os.path.join(os.environ["CACHE_MANAGER_CONFIGS_DIR"], "config.json"))
        shutil.copy(_src, os.path.join(os.environ["CACHE_MANAGER_CONFIGS_DIR"], "config_example.json"))
    atexit.register(shutil.rmtree, _tmp, True)
