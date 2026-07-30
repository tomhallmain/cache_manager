from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt

from cache_manager.key_management_manager import (
    KeyManagementManager, STATUS_OK, STATUS_MISSING, STATUS_VERIFY_FAILED, STATUS_NOT_APPLICABLE
)
from utils.translations import _


class KeyManagementWindow(QDialog):
    def __init__(self, main_window, config_manager, backup_manager, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.config_manager = config_manager
        self.backup_manager = backup_manager
        self.setWindowTitle(_("Key Management"))
        self.resize(750, 400)

        layout = QVBoxLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            _("Application"), _("Configured Strategy"), _("Actual Type"),
            _("Key Status"), _("Fingerprint"), _("Last Rotated"),
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        button_layout = QHBoxLayout()

        verify_all_btn = QPushButton(_("Verify All"))
        verify_all_btn.clicked.connect(self.refresh_table)
        button_layout.addWidget(verify_all_btn)

        rotate_btn = QPushButton(_("Rotate Key..."))
        rotate_btn.clicked.connect(self.rotate_selected)
        button_layout.addWidget(rotate_btn)

        button_layout.addStretch()

        close_btn = QPushButton(_("Close"))
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.refresh_table()

    def refresh_table(self):
        apps = self.config_manager.get_applications()
        self.table.setRowCount(len(apps))

        status_labels = {
            STATUS_OK: _("OK"),
            STATUS_MISSING: _("Missing"),
            STATUS_VERIFY_FAILED: _("Verify Failed"),
            STATUS_NOT_APPLICABLE: _("N/A"),
        }

        for row, app in enumerate(apps):
            info = KeyManagementManager.get_key_info(app)

            name_item = QTableWidgetItem(app.get("name", ""))
            name_item.setData(Qt.UserRole, row)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(info["configured_strategy"].display_value(_)))
            self.table.setItem(row, 2, QTableWidgetItem(info["actual_type"] or _("None")))
            self.table.setItem(row, 3, QTableWidgetItem(status_labels.get(info["status"], info["status"])))
            self.table.setItem(row, 4, QTableWidgetItem(info["fingerprint"] or ""))
            self.table.setItem(row, 5, QTableWidgetItem(info["rotated_at"] or _("Never")))

    def _selected_app(self):
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        index = self.table.item(row, 0).data(Qt.UserRole)
        return self.config_manager.get_applications()[index]

    def rotate_selected(self):
        app = self._selected_app()
        if app is None:
            QMessageBox.warning(self, _("No Selection"), _("Please select an application to rotate."))
            return

        try:
            targets, skipped = KeyManagementManager.collect_rotation_targets(app, self.backup_manager)
        except Exception as e:
            QMessageBox.warning(self, _("Rotation Failed"), str(e))
            return

        message = _(
            "This will generate a new key for '{0}' and re-encrypt {1} file(s) "
            "(the live cache plus its local/external backups).\n\n"
            "Backups not stored in this app's configured backup location(s) will "
            "not be updated and will become unreadable after rotation."
        ).format(app["name"], len(targets))
        if skipped:
            message += "\n\n" + _("Skipped (will remain on the old key):\n{0}").format(
                "\n".join(f"{path} ({reason})" for path, reason in skipped)
            )
        message += "\n\n" + _("Continue?")

        confirm = QMessageBox.question(self, _("Rotate Key"), message, QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        try:
            result = KeyManagementManager.rotate_key(app, self.backup_manager)
        except Exception as e:
            QMessageBox.warning(
                self, _("Rotation Failed"),
                _("Failed to rotate key for '{0}':\n{1}").format(app["name"], str(e))
            )
            return

        self._refresh_recovery_bundle()

        QMessageBox.information(
            self, _("Rotation Complete"),
            _("Re-encrypted {0} file(s) for '{1}'.").format(len(result["re_encrypted"]), app["name"])
        )
        self.refresh_table()

    def _refresh_recovery_bundle(self):
        passphrase = self.main_window._ensure_recovery_passphrase()
        if passphrase:
            self.main_window._refresh_recovery_bundle_after_backup(passphrase)
