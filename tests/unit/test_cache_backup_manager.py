import itertools
import os
from datetime import datetime, timedelta

import cache_manager.cache_backup_manager as cbm_module
from cache_manager.cache_backup_manager import CacheBackupManager
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file


def _write_encrypted_cache(path, service_name, app_identifier, payload=b"hello world"):
    encrypt_data_to_file(payload, service_name, app_identifier, str(path))


def test_backup_dir_uses_env_override(isolated_singletons):
    manager = CacheBackupManager()
    backups_dir_env = os.environ["CACHE_MANAGER_BACKUPS_DIR"]

    assert os.path.abspath(manager.backup_dir) == os.path.abspath(backups_dir_env)
    assert os.path.abspath(manager.backup_dir) != os.path.abspath("backups")


def test_create_backup_writes_verified_copy(isolated_singletons, tmp_path):
    cache_location = tmp_path / "app_cache.enc"
    _write_encrypted_cache(cache_location, "TestBackupService", "test_backup_app", b"cache payload")

    manager = CacheBackupManager()
    backup_path = manager.create_backup("Test App", str(cache_location), "TestBackupService", "test_backup_app")

    assert backup_path is not None
    assert os.path.dirname(os.path.abspath(backup_path)) == os.path.abspath(manager.backup_dir)
    decrypted = decrypt_data_from_file(backup_path, "TestBackupService", "test_backup_app")
    assert decrypted == b"cache payload"


def test_create_backup_rejects_undecryptable_file(isolated_singletons, tmp_path):
    """A file that isn't actually encrypted for this service/app must fail
    verification and leave no stray backup file behind."""
    cache_location = tmp_path / "not_really_encrypted.enc"
    cache_location.write_bytes(b"plain bytes, not a real encrypted payload")

    manager = CacheBackupManager()
    backup_path = manager.create_backup("Bad App", str(cache_location), "TestBackupService", "bad_app")

    assert backup_path is None
    assert os.listdir(manager.backup_dir) == [] or all(
        not f.startswith("bad_app_") for f in os.listdir(manager.backup_dir)
    )


def test_rotation_removes_oldest_backups_beyond_limit(isolated_singletons, tmp_path, monkeypatch):
    """Creating more backups than max_backups_per_app must prune the oldest
    ones and keep the metadata file in sync."""
    counter = itertools.count()
    base = datetime(2024, 1, 1)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return base + timedelta(seconds=next(counter))

    monkeypatch.setattr(cbm_module, "datetime", FrozenDateTime)

    cache_location = tmp_path / "rotating_cache.enc"
    _write_encrypted_cache(cache_location, "TestBackupService", "rotating_app", b"v1")

    manager = CacheBackupManager(max_backups_per_app=3)
    for _ in range(5):
        result = manager.create_backup("Rotating App", str(cache_location), "TestBackupService", "rotating_app")
        assert result is not None

    backups = manager.list_backups("Rotating App")
    assert len(backups) == 3
    for backup in backups:
        assert os.path.exists(backup["path"])

    backup_files = [f for f in os.listdir(manager.backup_dir) if f.startswith("rotating_app_") and f.endswith(".enc")]
    assert len(backup_files) == 3
