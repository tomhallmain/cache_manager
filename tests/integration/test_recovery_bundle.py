"""
Regression tests for the recovery-bundle cross-machine restore path (export
on one machine -> simulate arriving on a different one -> import). Each test
encodes one specific behavior the feature needs in order to actually restore
decryptability on a different computer. As written, every test in this file
is expected to FAIL against the current implementation -- that is the point:
they encode the behavior the feature *should* have, so that fixing the
underlying issue turns the corresponding test green.

The passphrase type bug covered separately in
tests/unit/test_encryptor_passphrase_fallback.py doesn't involve the
recovery bundle machinery at all, so it isn't repeated here.
"""

import os
import shutil
from datetime import datetime, timedelta

import cache_manager.cache_backup_manager as cbm_module
from cache_manager.cache_backup_manager import CacheBackupManager
from cache_manager.recovery_bundle_manager import RecoveryBundleManager
from utils.app_info_cache import AppInfoCache
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file


SERVICE_NAME = "RecoveryTestService"
APP_IDENTIFIER = "recovery_test_app"
APP_NAME = "Recovery Test App"
RECOVERY_PASSPHRASE = "correct horse battery staple"


def _managed_app_entry(cache_location, name=APP_NAME, service_name=SERVICE_NAME, app_identifier=APP_IDENTIFIER):
    return {
        "name": name,
        "service_name": service_name,
        "app_identifier": app_identifier,
        "cache_location": str(cache_location),
        "encryption_strategy": "standard",
    }


def test_undecryptable_cache_file_is_not_silently_destroyed(isolated_singletons):
    """
    Simulates copying an app_info_cache.enc over from another machine: the
    file exists but cannot be decrypted with whatever keys are locally
    available (there are none yet). AppInfoCache.__init__ must not silently
    replace it with a fresh, self-only cache and no backup -- that destroys
    the very config a recovery-bundle import would need, before the user
    ever gets a chance to run one.
    """
    cache_path = isolated_singletons._cache_loc
    foreign_bytes = b"stand-in for an app_info_cache.enc encrypted on a different machine"
    with open(cache_path, "wb") as f:
        f.write(foreign_bytes)

    AppInfoCache()  # simulates the app launching against this file

    backup_slots = [f"{cache_path}.bak{'' if i == 1 else i}" for i in range(1, AppInfoCache.NUM_BACKUPS + 1)]

    def _read(path):
        with open(path, "rb") as f:
            return f.read()

    preserved_somewhere = (os.path.exists(cache_path) and _read(cache_path) == foreign_bytes) or any(
        os.path.exists(p) and _read(p) == foreign_bytes for p in backup_slots
    )
    assert preserved_somewhere, (
        "Content that could not be decrypted locally was destroyed with no backup "
        "when AppInfoCache re-initialized over it."
    )


def test_restore_does_not_blindly_create_directories_for_stale_paths(tmp_path):
    """
    The bundle records cache_location as an absolute path from the original
    (exporting) machine. When that directory structure was never created on
    the importing machine -- the normal case for "a different computer" --
    recovery import must not silently manufacture and write into it.
    """
    real_cache_location = tmp_path / "real_install" / "managed_app_cache.enc"
    real_cache_location.parent.mkdir()
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(real_cache_location))

    manager = CacheBackupManager()
    backup_path = manager.create_backup(APP_NAME, str(real_cache_location), SERVICE_NAME, APP_IDENTIFIER)
    assert backup_path is not None

    stale_foreign_path = tmp_path / "this_directory_tree_never_existed_on_this_machine" / "deep" / "cache.enc"
    bundle_path = RecoveryBundleManager.get_default_bundle_path(manager.get_effective_backup_dir())
    RecoveryBundleManager.export_bundle(
        applications=[_managed_app_entry(stale_foreign_path)],
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
    )

    RecoveryBundleManager._purge_existing_key_material(SERVICE_NAME, APP_IDENTIFIER)

    RecoveryBundleManager.import_bundle(
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
        overwrite_existing=True,
    )

    assert not os.path.exists(stale_foreign_path.parent), (
        "Recovery import must not silently create a directory tree implied by a "
        "foreign machine's exported cache_location."
    )


def test_import_result_reports_whether_cache_was_restored(tmp_path):
    """
    import_bundle()'s result must let the caller distinguish "keys imported
    AND cache decryptability restored" from "keys imported but no matching
    backup was found next to the bundle" -- today it reports only
    imported/skipped/failed key counts, so this information doesn't exist at
    all yet.
    """
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
    RecoveryBundleManager._purge_existing_key_material(SERVICE_NAME, APP_IDENTIFIER)
    os.remove(cache_location)

    result = RecoveryBundleManager.import_bundle(
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
        overwrite_existing=True,
    )

    assert "cache_restored_count" in result, "import_bundle() must report how many caches were actually restored"
    assert result["cache_restored_count"] == 1
    assert result.get("cache_not_restored", []) == []


def test_import_result_flags_apps_with_no_matching_backup(tmp_path):
    """
    If only the bundle file itself was carried over -- without the backups
    directory it originally sat next to -- no cache file can be restored.
    The result must surface that per app instead of silently reporting
    success via key-import counts alone.
    """
    cache_location = tmp_path / "managed_app_cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    original_bundle_path = RecoveryBundleManager.get_default_bundle_path(manager.get_effective_backup_dir())
    RecoveryBundleManager.export_bundle(
        applications=[_managed_app_entry(cache_location)],
        bundle_path=original_bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
    )
    RecoveryBundleManager._purge_existing_key_material(SERVICE_NAME, APP_IDENTIFIER)

    # Copy *only* the bundle file to an otherwise-empty directory -- no
    # accompanying backups, simulating a user who copied just the bundle
    # itself and expected it alone to be enough.
    lonely_bundle_dir = tmp_path / "lonely_bundle_only"
    lonely_bundle_dir.mkdir()
    lonely_bundle_path = lonely_bundle_dir / RecoveryBundleManager.BUNDLE_FILENAME
    shutil.copy(original_bundle_path, lonely_bundle_path)

    result = RecoveryBundleManager.import_bundle(
        bundle_path=str(lonely_bundle_path),
        recovery_passphrase=RECOVERY_PASSPHRASE,
        overwrite_existing=True,
    )

    assert result["imported_count"] == 1  # keys import fine on their own
    assert "cache_restored_count" in result, "import_bundle() must report how many caches were actually restored"
    assert result["cache_restored_count"] == 0
    assert result.get("cache_not_restored", []) == [APP_NAME]


def test_latest_backup_uses_recorded_timestamps_not_mtime(isolated_singletons, tmp_path, monkeypatch):
    """
    "Latest backup" must be chosen using the timestamps already recorded in
    the app's backup metadata, not filesystem mtime -- copy/zip/cloud-sync
    tools commonly reset or fail to preserve mtimes across a machine-to-
    machine transfer, which is exactly the situation this feature is for.
    """
    counter = {"n": 0}
    base = datetime(2024, 1, 1)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            counter["n"] += 1
            return base + timedelta(seconds=counter["n"])

    monkeypatch.setattr(cbm_module, "datetime", FrozenDateTime)

    cache_location = tmp_path / "cache.enc"
    manager = CacheBackupManager()

    encrypt_data_to_file(b"payload_v1_older", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))
    older_backup_path = manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    encrypt_data_to_file(b"payload_v2_newer", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))
    newer_backup_path = manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    assert older_backup_path != newer_backup_path

    # Simulate a transfer tool (zip/cloud-sync/plain copy) that scrambled
    # mtimes: the file recorded as "older" in the backup metadata now has a
    # *newer* mtime on disk than the one recorded as "newer".
    now = os.path.getmtime(newer_backup_path)
    os.utime(older_backup_path, (now + 100, now + 100))
    os.utime(newer_backup_path, (now - 100, now - 100))

    chosen_path = RecoveryBundleManager._find_latest_backup_for_app(manager.backup_dir, APP_NAME)
    chosen_content = decrypt_data_from_file(chosen_path, SERVICE_NAME, APP_IDENTIFIER)

    assert chosen_content == b"payload_v2_newer", (
        "Latest-backup selection must follow the recorded backup timestamps, "
        "not filesystem mtime, which transfer tools routinely don't preserve."
    )


def test_restore_backs_up_pre_existing_cache_before_overwriting(tmp_path):
    """
    If cache_location already holds content on the importing machine (e.g.
    the target app was already installed and run there), recovery import
    must not silently replace it with no way to recover what was there
    before.
    """
    cache_location = tmp_path / "managed_app_cache.enc"
    encrypt_data_to_file(b"backed_up_payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))

    manager = CacheBackupManager()
    manager.create_backup(APP_NAME, str(cache_location), SERVICE_NAME, APP_IDENTIFIER)

    bundle_path = RecoveryBundleManager.get_default_bundle_path(manager.get_effective_backup_dir())
    RecoveryBundleManager.export_bundle(
        applications=[_managed_app_entry(cache_location)],
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
    )
    RecoveryBundleManager._purge_existing_key_material(SERVICE_NAME, APP_IDENTIFIER)

    # Something else now occupies cache_location on "this machine" -- not
    # the exported backup's content, and it predates the recovery import.
    pre_existing_content = b"legitimate content that predates recovery and must not vanish without a trace"
    with open(cache_location, "wb") as f:
        f.write(pre_existing_content)

    RecoveryBundleManager.import_bundle(
        bundle_path=bundle_path,
        recovery_passphrase=RECOVERY_PASSPHRASE,
        overwrite_existing=True,
    )

    cache_dir = os.path.dirname(cache_location)
    sibling_files = [
        os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if os.path.join(cache_dir, f) != str(cache_location)
    ]

    def _contains_original(path):
        try:
            with open(path, "rb") as f:
                return f.read() == pre_existing_content
        except OSError:
            return False

    assert any(_contains_original(p) for p in sibling_files), (
        "Pre-existing cache_location content must be preserved somewhere before "
        "recovery import overwrites it."
    )
