"""
Root conftest for the Cache Manager test suite.

IMPORTANT: The env vars below must be set at module load time -- before any
app module is imported -- because both `app_info_cache` and `config` are
module-level singletons instantiated on first import (see
utils/app_info_cache.py and utils/config.py). The real OS keyring backend is
also replaced at module load time, before any application code gets a chance
to call into it: this application's encryption keys are stored under a
keyring service name (`MyPersonalApplicationsService`, see utils/globals.py)
that is shared across every application using the same encryption
infrastructure on this machine -- running key-generation/import/purge code
against the real OS keyring during tests would create, and could even
delete, real secrets belonging to those other applications.

Any nested conftest.py files must not re-import app modules before this file
has run its module-level setup.
"""

import atexit
import os
import shutil
import sys
import tempfile

import keyring
import keyring.backend
import keyring.errors


# ---------------------------------------------------------------------------
# In-memory keyring backend: replaces the real OS credential store (Windows
# Credential Manager / macOS Keychain / Linux Secret Service / whatever
# keyring auto-detects) for the whole test session, so no test can read,
# create, or delete real secrets.
# ---------------------------------------------------------------------------
class InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self._store = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        key = (service, username)
        if key not in self._store:
            raise keyring.errors.PasswordDeleteError(
                f"No password set for service={service!r} username={username!r}"
            )
        del self._store[key]


keyring.set_keyring(InMemoryKeyring())

# ---------------------------------------------------------------------------
# Bootstrap a safe temporary location so that the singletons created during
# initial import never touch the real cache/config/backups files.
# ---------------------------------------------------------------------------
_bootstrap_tmp = tempfile.mkdtemp(prefix="cache_manager_tests_")
os.environ.setdefault("CACHE_MANAGER_CACHE_DIR", os.path.join(_bootstrap_tmp, "cache"))
os.environ.setdefault("CACHE_MANAGER_CONFIGS_DIR", os.path.join(_bootstrap_tmp, "configs"))
os.environ.setdefault("CACHE_MANAGER_BACKUPS_DIR", os.path.join(_bootstrap_tmp, "backups"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.makedirs(os.environ["CACHE_MANAGER_CACHE_DIR"], exist_ok=True)
os.makedirs(os.environ["CACHE_MANAGER_CONFIGS_DIR"], exist_ok=True)
os.makedirs(os.environ["CACHE_MANAGER_BACKUPS_DIR"], exist_ok=True)

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# utils.encryptor is only importable now that _project_root is on sys.path.
# See the class comment on ENABLE_NATIVE_ACL_HARDENING for why this needs
# to be off for the whole test session, same reasoning as the keyring swap
# above: the native win32cred/dbus calls bypass the keyring package (and
# therefore the fake backend) entirely.
from utils.encryptor import PassphraseManager
PassphraseManager.ENABLE_NATIVE_ACL_HARDENING = False

_src_example = os.path.join(_project_root, "configs", "config_example.json")
if os.path.isfile(_src_example):
    # Copied under both names: "config.json" so Config() has an active
    # config ready to go without extra setup, and "config_example.json" so
    # anything that specifically looks for the example file (e.g.
    # Config.create_from_example()) also finds it under the isolated dir.
    shutil.copy(_src_example, os.path.join(os.environ["CACHE_MANAGER_CONFIGS_DIR"], "config.json"))
    shutil.copy(_src_example, os.path.join(os.environ["CACHE_MANAGER_CONFIGS_DIR"], "config_example.json"))

atexit.register(shutil.rmtree, _bootstrap_tmp, True)

import pytest


def repoint_singleton_bindings(monkeypatch, attr_name, old_obj, new_obj):
    """Repoint every imported module's module-level binding of *old_obj* to
    *new_obj* (undone automatically by monkeypatch at test teardown).

    Modules that do e.g. `from utils.app_info_cache import app_info_cache` at
    module level hold their own reference to the singleton, so patching only
    the source module leaves those bindings stale. Sweeping sys.modules
    retires that whack-a-mole: the identity comparison guarantees only
    bindings to the exact old object are touched.
    """
    for module in list(sys.modules.values()):
        try:
            if getattr(module, attr_name, None) is old_obj:
                monkeypatch.setattr(module, attr_name, new_obj)
        except Exception:
            continue


@pytest.fixture(autouse=True)
def isolated_singletons(tmp_path, monkeypatch):
    """Re-initialise the app_info_cache and config singletons, and swap in a
    fresh in-memory keyring, for each test -- pointing everything at a
    per-test temp directory. No production files or real OS keyring entries
    are ever touched."""
    cache_dir = tmp_path / "cache"
    configs_dir = tmp_path / "configs"
    backups_dir = tmp_path / "backups"
    cache_dir.mkdir()
    configs_dir.mkdir()
    backups_dir.mkdir()
    if os.path.isfile(_src_example):
        shutil.copy(_src_example, configs_dir / "config.json")
        shutil.copy(_src_example, configs_dir / "config_example.json")

    monkeypatch.setenv("CACHE_MANAGER_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("CACHE_MANAGER_CONFIGS_DIR", str(configs_dir))
    monkeypatch.setenv("CACHE_MANAGER_BACKUPS_DIR", str(backups_dir))

    # Fresh in-memory keyring per test, so key material from one test can
    # never leak into (or be reused by) the next.
    keyring.set_keyring(InMemoryKeyring())

    import utils.app_info_cache as aic
    import utils.config as cfg
    from utils.encryptor import ENCRYPTOR_CLASSES

    # Cached "which encryptor class" resolutions from any prior test/import;
    # not secret material, but stale entries could hide a fresh-keyring bug.
    ENCRYPTOR_CLASSES.clear()

    old_cache = aic.app_info_cache
    new_cache = aic.AppInfoCache()
    repoint_singleton_bindings(monkeypatch, "app_info_cache", old_cache, new_cache)

    old_config = cfg.config
    new_config = cfg.Config()
    repoint_singleton_bindings(monkeypatch, "config", old_config, new_config)

    yield new_cache
