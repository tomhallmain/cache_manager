import os

from utils.app_info_cache import AppInfoCache
from utils.globals import AppInfo


def test_cache_paths_are_isolated_from_repo(isolated_singletons):
    """The active cache/json paths must live under the test's temp dir, never
    under the real repo (where app_info_cache.enc etc. actually live)."""
    cache = isolated_singletons
    cache_dir_env = os.environ["CACHE_MANAGER_CACHE_DIR"]

    assert os.path.dirname(cache._cache_loc) == os.path.normpath(cache_dir_env)
    assert os.path.dirname(cache._json_loc) == os.path.normpath(cache_dir_env)
    assert cache._cache_loc != AppInfoCache.CACHE_LOC
    assert not os.path.exists(AppInfoCache.CACHE_LOC), (
        "Test run must never touch the real app_info_cache.enc"
    )


def test_self_registers_cache_manager_application(isolated_singletons):
    cache = isolated_singletons
    apps = cache.get_applications()
    matches = [
        a for a in apps
        if a.get("service_name") == AppInfo.SERVICE_NAME and a.get("app_identifier") == AppInfo.APP_IDENTIFIER
    ]
    assert len(matches) == 1
    assert matches[0]["cache_location"] == cache._cache_loc


def test_add_update_remove_application_roundtrip(isolated_singletons):
    cache = isolated_singletons
    initial_count = len(cache.get_applications())

    cache.add_application("Widget App", "WidgetService", "widget_app", "/tmp/widget.enc", "standard")
    apps = cache.get_applications()
    assert len(apps) == initial_count + 1
    added_index = len(apps) - 1
    assert apps[added_index]["name"] == "Widget App"

    cache.update_application(added_index, "Widget App v2", "WidgetService", "widget_app", "/tmp/widget2.enc", "standard")
    assert cache.get_applications()[added_index]["name"] == "Widget App v2"
    assert cache.get_applications()[added_index]["cache_location"] == "/tmp/widget2.enc"

    cache.remove_application(added_index)
    assert len(cache.get_applications()) == initial_count


def test_store_and_reload_persists_within_isolated_dir(isolated_singletons):
    """A second AppInfoCache instance pointed at the same (isolated) location
    should be able to decrypt what the first one wrote -- proving persistence
    works without ever touching the real cache file or OS keyring."""
    cache = isolated_singletons
    cache.add_application("Persisted App", "PersistedService", "persisted_app", "/tmp/persisted.enc", "standard")

    reloaded = AppInfoCache()
    names = [a["name"] for a in reloaded.get_applications()]
    assert "Persisted App" in names


def test_backup_rotation_stays_within_isolated_dir(isolated_singletons):
    """Triggering enough store()/load() cycles to rotate backups must only
    ever touch files under the isolated cache dir, never the real repo's
    app_info_cache.enc.bak* files."""
    cache = isolated_singletons
    cache_dir = os.environ["CACHE_MANAGER_CACHE_DIR"]
    real_backup_paths = {f"{AppInfoCache.CACHE_LOC}.bak{'' if i == 1 else i}" for i in range(1, AppInfoCache.NUM_BACKUPS + 1)}
    real_backups_before = {p for p in real_backup_paths if os.path.exists(p)}

    rotated_any = False
    for i in range(AppInfoCache.NUM_BACKUPS + 2):
        cache.add_application(f"App {i}", f"Service{i}", f"app_{i}", f"/tmp/app_{i}.enc", "standard")
        reloaded = AppInfoCache()  # reload triggers _rotate_backups() on a successful load
        rotated_any = rotated_any or any(os.path.exists(p) for p in reloaded._get_backup_paths())

    assert rotated_any, "Expected at least one backup file to be rotated into the isolated dir"
    for path in cache._get_backup_paths():
        assert os.path.dirname(path) == os.path.normpath(cache_dir)
        assert path not in real_backup_paths

    real_backups_after = {p for p in real_backup_paths if os.path.exists(p)}
    assert real_backups_after == real_backups_before, "Real repo backup files must be untouched"


def test_set_get_roundtrip(isolated_singletons):
    cache = isolated_singletons
    assert cache.get("nonexistent_key") is None
    cache.set("some_key", {"nested": True})
    assert cache.get("some_key") == {"nested": True}
