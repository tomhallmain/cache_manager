import os

import pytest

from cache_manager.cache_backup_manager import CacheBackupManager
from cache_manager.recovery_bundle_manager import RecoveryBundleManager
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file


APP_NAME = "Managed App"
SERVICE_NAME = "ManagedAppService"
APP_IDENTIFIER = "managed_app"
RECOVERY_PASSPHRASE = "correct horse battery staple"


def _managed_app_entry(cache_location):
    return {
        "name": APP_NAME,
        "service_name": SERVICE_NAME,
        "app_identifier": APP_IDENTIFIER,
        "cache_location": str(cache_location),
        "encryption_strategy": "standard",
    }


def test_backup_export_purge_import_restores_decryptability(tmp_path):
    """End-to-end happy path for the recovery-bundle feature: back up a
    managed app's encrypted cache, export a recovery bundle, simulate losing
    the local keys (as if starting fresh on a different computer), then
    import the bundle and confirm the cache is decryptable again. Everything
    here runs against the isolated temp dirs and the fake in-memory keyring
    installed by tests/conftest.py -- no real OS keyring entries or repo
    files are touched at any point.
    """
    cache_location = tmp_path / "managed_app_cache.enc"
    encrypt_data_to_file(b"the real cache payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    backup_path = manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)
    assert backup_path is not None

    bundle_path = RecoveryBundleManager.get_default_bundle_path(manager.get_effective_backup_dir())
    export_result = RecoveryBundleManager.export_bundle(
        applications=[_managed_app_entry(cache_location)],
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
    )
    assert export_result["exported_count"] == 1
    assert export_result["error_count"] == 0
    assert os.path.exists(bundle_path)

    # Simulate arriving on a different computer: the local key material for
    # this app is gone, so the existing cache file can no longer be decrypted.
    RecoveryBundleManager._purge_existing_key_material(SERVICE_NAME, APP_IDENTIFIER)
    with pytest.raises(Exception):
        decrypt_data_from_file(str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    # Losing the local key also destroys the cache file itself, standing in
    # for a fresh install where it never existed on this machine at all.
    os.remove(cache_location)

    import_result = RecoveryBundleManager.import_bundle(
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
        overwrite_existing=True,
    )
    assert import_result["imported_count"] == 1
    assert import_result["failed_count"] == 0

    assert os.path.exists(cache_location)
    restored = decrypt_data_from_file(str(cache_location), SERVICE_NAME, APP_IDENTIFIER)
    assert restored == b"the real cache payload"


def test_import_wrong_passphrase_fails_cleanly(tmp_path):
    cache_location = tmp_path / "managed_app_cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    bundle_path = RecoveryBundleManager.get_default_bundle_path(manager.get_effective_backup_dir())
    RecoveryBundleManager.export_bundle(
        applications=[_managed_app_entry(cache_location)],
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
    )

    with pytest.raises(Exception):
        RecoveryBundleManager.import_bundle(
            bundle_path=bundle_path,
            recovery_passphrase="wrong passphrase",
            overwrite_existing=True,
        )


def test_import_skips_existing_keys_unless_overwrite_requested(tmp_path):
    cache_location = tmp_path / "managed_app_cache.enc"
    encrypt_data_to_file(b"original payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    bundle_path = RecoveryBundleManager.get_default_bundle_path(manager.get_effective_backup_dir())
    RecoveryBundleManager.export_bundle(
        applications=[_managed_app_entry(cache_location)],
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
    )

    # Local keys for this app still exist (never purged) -- importing without
    # overwrite_existing must skip rather than clobber them.
    result = RecoveryBundleManager.import_bundle(
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
        overwrite_existing=False,
    )
    assert result["imported_count"] == 0
    assert result["skipped_count"] == 1
