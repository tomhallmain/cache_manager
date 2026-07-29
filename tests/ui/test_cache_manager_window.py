import os

from main import CacheManagerWindow


def test_window_constructs_and_lists_only_self_registered_app(qtbot, isolated_singletons):
    window = CacheManagerWindow()
    qtbot.addWidget(window)
    window.refresh_timer.stop()

    assert window.windowTitle() == "Cache Manager"
    apps = window.config_manager.get_applications()
    assert window.apps_table.rowCount() == len(apps)
    assert len(apps) == 1
    assert apps[0]["name"] == "Cache Manager"


def test_window_backup_folder_label_uses_isolated_dir(qtbot, isolated_singletons):
    window = CacheManagerWindow()
    qtbot.addWidget(window)
    window.refresh_timer.stop()

    backups_dir_env = os.environ["CACHE_MANAGER_BACKUPS_DIR"]
    effective_dir = window.backup_manager.get_effective_backup_dir()

    assert os.path.abspath(effective_dir) == os.path.abspath(backups_dir_env)
    assert os.path.abspath(effective_dir) != os.path.abspath("backups")
    assert os.path.abspath(effective_dir) in window.backup_dir_label.text()


def test_add_application_via_dialog_updates_table(qtbot, isolated_singletons, monkeypatch):
    from main import AddEditApplicationDialog
    from PySide6.QtWidgets import QDialog

    window = CacheManagerWindow()
    qtbot.addWidget(window)
    window.refresh_timer.stop()

    new_app_data = {
        "name": "New App",
        "service_name": "NewAppService",
        "app_identifier": "new_app",
        "cache_location": "/tmp/new_app.enc",
        "encryption_strategy": "standard",
    }

    monkeypatch.setattr(AddEditApplicationDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(AddEditApplicationDialog, "get_data", lambda self: new_app_data)

    window.add_application()

    apps = window.config_manager.get_applications()
    names = [a["name"] for a in apps]
    assert "New App" in names
    assert window.apps_table.rowCount() == len(apps)
