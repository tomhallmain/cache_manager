from PySide6.QtWidgets import QDialog

from main import AddEditApplicationDialog
from utils.encryption_strategy import EncryptionStrategy


def test_add_dialog_starts_blank(qtbot):
    dialog = AddEditApplicationDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Add Application"
    data = dialog.get_data()
    assert data["name"] == ""
    assert data["service_name"] == ""
    assert data["app_identifier"] == ""
    assert data["cache_location"] == ""
    assert data["encryption_strategy"] == EncryptionStrategy.UNKNOWN.value


def test_add_dialog_get_data_reflects_typed_input(qtbot):
    dialog = AddEditApplicationDialog()
    qtbot.addWidget(dialog)

    qtbot.keyClicks(dialog.name_edit, "My App")
    qtbot.keyClicks(dialog.service_edit, "MyAppService")
    qtbot.keyClicks(dialog.identifier_edit, "my_app")
    qtbot.keyClicks(dialog.location_edit, "/tmp/my_app_cache.enc")

    index = dialog.strategy_combo.findData(EncryptionStrategy.STANDARD.value)
    dialog.strategy_combo.setCurrentIndex(index)

    data = dialog.get_data()
    assert data == {
        "name": "My App",
        "service_name": "MyAppService",
        "app_identifier": "my_app",
        "cache_location": "/tmp/my_app_cache.enc",
        "encryption_strategy": EncryptionStrategy.STANDARD.value,
    }


def test_edit_dialog_prefills_existing_application_data(qtbot):
    app_data = {
        "name": "Existing App",
        "service_name": "ExistingService",
        "app_identifier": "existing_app",
        "cache_location": "/tmp/existing.enc",
        "encryption_strategy": EncryptionStrategy.OQS.value,
    }
    dialog = AddEditApplicationDialog(app_data=app_data)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Edit Application"
    assert dialog.get_data() == app_data


def test_dialog_is_modal_qdialog(qtbot):
    dialog = AddEditApplicationDialog()
    qtbot.addWidget(dialog)

    assert isinstance(dialog, QDialog)
    assert dialog.isModal()
