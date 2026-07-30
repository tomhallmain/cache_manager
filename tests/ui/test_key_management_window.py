from PySide6.QtWidgets import QMessageBox

from cache_manager.key_management_window import KeyManagementWindow
from main import CacheManagerWindow
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file

SERVICE_NAME = "KeyMgmtUiService"
APP_IDENTIFIER = "key_mgmt_ui_app"
APP_NAME = "Key Mgmt UI App"


def test_table_lists_self_registered_app(qtbot, isolated_singletons):
    main_window = CacheManagerWindow()
    qtbot.addWidget(main_window)
    main_window.refresh_timer.stop()

    key_window = KeyManagementWindow(main_window, main_window.config_manager, main_window.backup_manager)
    qtbot.addWidget(key_window)

    assert key_window.table.rowCount() == 1
    assert key_window.table.item(0, 0).text() == "Cache Manager"


def test_rotate_without_selection_warns(qtbot, isolated_singletons, monkeypatch):
    main_window = CacheManagerWindow()
    qtbot.addWidget(main_window)
    main_window.refresh_timer.stop()

    key_window = KeyManagementWindow(main_window, main_window.config_manager, main_window.backup_manager)
    qtbot.addWidget(key_window)

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a) or QMessageBox.Ok)

    key_window.rotate_selected()
    assert len(warned) == 1


def test_rotate_selected_reencrypts_cache_and_updates_table(qtbot, isolated_singletons, monkeypatch, tmp_path):
    main_window = CacheManagerWindow()
    qtbot.addWidget(main_window)
    main_window.refresh_timer.stop()

    cache_location = tmp_path / "cache.enc"
    encrypt_data_to_file(b"payload", SERVICE_NAME, APP_IDENTIFIER, str(cache_location))
    main_window.config_manager.add_application(APP_NAME, SERVICE_NAME, APP_IDENTIFIER, str(cache_location), "standard")

    key_window = KeyManagementWindow(main_window, main_window.config_manager, main_window.backup_manager)
    qtbot.addWidget(key_window)

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(main_window, "_ensure_recovery_passphrase", lambda: None)

    row = next(r for r in range(key_window.table.rowCount()) if key_window.table.item(r, 0).text() == APP_NAME)
    key_window.table.selectRow(row)

    key_window.rotate_selected()

    assert decrypt_data_from_file(str(cache_location), SERVICE_NAME, APP_IDENTIFIER) == b"payload"
    assert "T" in key_window.table.item(row, 5).text()  # ISO timestamp, not the "Never" placeholder


def test_rotation_failure_shows_warning_not_crash(qtbot, isolated_singletons, monkeypatch, tmp_path):
    main_window = CacheManagerWindow()
    qtbot.addWidget(main_window)
    main_window.refresh_timer.stop()

    main_window.config_manager.add_application(APP_NAME, SERVICE_NAME, "unrotated_app", "/nonexistent/cache.enc", "standard")

    key_window = KeyManagementWindow(main_window, main_window.config_manager, main_window.backup_manager)
    qtbot.addWidget(key_window)

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a) or QMessageBox.Ok)

    row = next(r for r in range(key_window.table.rowCount()) if key_window.table.item(r, 0).text() == APP_NAME)
    key_window.table.selectRow(row)

    key_window.rotate_selected()
    assert len(warned) == 1
