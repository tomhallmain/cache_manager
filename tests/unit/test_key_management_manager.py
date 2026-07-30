import os

import pytest

from cache_manager.cache_backup_manager import CacheBackupManager
from cache_manager.key_management_manager import (
    KeyManagementManager, STATUS_OK, STATUS_MISSING, STATUS_NOT_APPLICABLE
)
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file


SERVICE_NAME = "KeyMgmtTestService"
APP_IDENTIFIER = "key_mgmt_test_app"
APP_NAME = "Key Mgmt Test App"


def _app(cache_location=None, strategy="standard", service_name=SERVICE_NAME, app_identifier=APP_IDENTIFIER):
    return {
        "name": APP_NAME,
        "service_name": service_name,
        "app_identifier": app_identifier,
        "cache_location": str(cache_location) if cache_location else "",
        "encryption_strategy": strategy,
    }


def test_get_key_info_not_applicable_for_unencrypted_app():
    info = KeyManagementManager.get_key_info(_app(strategy="none"))
    assert info["status"] == STATUS_NOT_APPLICABLE
    assert info["actual_type"] is None


def test_get_key_info_missing_when_no_keys_generated_yet():
    info = KeyManagementManager.get_key_info(_app(service_name="NeverUsedService", app_identifier="never_used_app"))
    assert info["status"] == STATUS_MISSING


def test_get_key_info_ok_once_keys_exist(tmp_path):
    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    info = KeyManagementManager.get_key_info(_app(cache_location))
    assert info["status"] == STATUS_OK
    assert info["actual_type"] is not None
    assert info["fingerprint"] and len(info["fingerprint"]) == 16
    assert info["rotated_at"] is None


def test_collect_rotation_targets_includes_cache_and_local_backups(tmp_path):
    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    backup_path = manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)
    assert backup_path is not None

    targets, skipped = KeyManagementManager.collect_rotation_targets(_app(cache_location), manager)
    assert str(cache_location) in targets
    assert backup_path in targets
    assert skipped == []


def test_collect_rotation_targets_flags_missing_backup_file(tmp_path):
    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    missing_path = os.path.join(manager.backup_dir, "never_written.enc")
    manager._save_backup_metadata(APP_NAME, missing_path)

    targets, skipped = KeyManagementManager.collect_rotation_targets(_app(cache_location), manager)
    assert missing_path not in targets
    assert any(path == missing_path for path, _reason in skipped)


def test_collect_rotation_targets_flags_unreachable_external_dir(tmp_path):
    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    unreachable_dir = str(tmp_path / "unplugged_drive")
    manager.external_backup_dir = unreachable_dir  # bypass set_external_backup_dir's os.makedirs

    targets, skipped = KeyManagementManager.collect_rotation_targets(_app(cache_location), manager)
    assert any(path == unreachable_dir for path, _reason in skipped)


def test_rotate_key_reencrypts_cache_and_all_backups(tmp_path):
    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"live payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    backup_path = manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    old_fingerprint = KeyManagementManager.get_key_info(_app(cache_location))["fingerprint"]

    result = KeyManagementManager.rotate_key(_app(cache_location), manager)
    assert set(result["re_encrypted"]) == {str(cache_location), backup_path}
    assert result["skipped"] == []

    assert decrypt_data_from_file(str(cache_location), SERVICE_NAME, APP_IDENTIFIER) == b"live payload"
    assert decrypt_data_from_file(backup_path, SERVICE_NAME, APP_IDENTIFIER) == b"live payload"

    new_info = KeyManagementManager.get_key_info(_app(cache_location))
    assert new_info["status"] == STATUS_OK
    assert new_info["fingerprint"] != old_fingerprint
    assert new_info["rotated_at"] is not None


def test_rotate_key_refuses_unencrypted_app():
    with pytest.raises(ValueError):
        KeyManagementManager.rotate_key(_app(strategy="none"), CacheBackupManager())


def test_rotate_key_refuses_when_no_keys_exist():
    app = _app(service_name="NeverRotatedService", app_identifier="never_rotated_app")
    with pytest.raises(ValueError):
        KeyManagementManager.rotate_key(app, CacheBackupManager())


def test_rotate_key_leaves_everything_unchanged_on_failure(tmp_path):
    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"live payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    good_backup = manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)
    assert good_backup is not None

    corrupt_backup_path = os.path.join(manager.backup_dir, "corrupt.enc")
    with open(corrupt_backup_path, "wb") as f:
        f.write(b"not a valid encrypted payload")
    manager._save_backup_metadata(APP_NAME, corrupt_backup_path)

    with pytest.raises(Exception):
        KeyManagementManager.rotate_key(_app(cache_location), manager)

    # Old key still works; nothing was swapped and no temp files were left behind.
    assert decrypt_data_from_file(str(cache_location), SERVICE_NAME, APP_IDENTIFIER) == b"live payload"
    assert decrypt_data_from_file(good_backup, SERVICE_NAME, APP_IDENTIFIER) == b"live payload"
    leftover = [f for f in os.listdir(manager.backup_dir) if f.endswith(".rotating.tmp")]
    assert leftover == []
    assert not os.path.exists(f"{cache_location}.rotating.tmp")
