"""
conftest for tests/unit/.

Re-applies the same env var setup as the root conftest.py. This is necessary
because pytest loads each directory's conftest before collecting tests in
that directory, and the singletons may not yet be imported when the root
conftest runs in some collection orders.
"""

import os

# Re-apply the env vars at module load. setdefault-style guard means the
# root conftest's values win if already set; this just ensures they're
# present either way, so no singleton construction can ever fall through to
# the real cache/config/backups paths.
if "CACHE_MANAGER_CACHE_DIR" not in os.environ:
    import atexit
    import shutil
    import tempfile

    _tmp = tempfile.mkdtemp(prefix="cache_manager_unit_")
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
