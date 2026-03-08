#!/usr/bin/env python
"""
Cache Manager Application
Manages backup and inspection of application caches
"""

import os
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QMessageBox, QDialog, QLineEdit, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QInputDialog
from PySide6.QtCore import Qt, QTimer
from datetime import datetime, timedelta

from cache_manager.config_manager import ConfigManager
from cache_manager.cache_backup_manager import CacheBackupManager
from cache_manager.recovery_bundle_manager import RecoveryBundleManager
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.encryption_strategy import EncryptionStrategy
from utils.utils import Utils

logger = get_logger(__name__)
_ = I18N._


class AddEditApplicationDialog(QDialog):
    """Dialog for adding or editing an application"""
    
    def __init__(self, parent=None, app_data=None):
        super().__init__(parent)
        self.setWindowTitle(_("Add Application") if app_data is None else _("Edit Application"))
        self.setModal(True)
        self.app_data = app_data
        
        layout = QVBoxLayout()
        
        # Name field
        layout.addWidget(QLabel(_("Application Name:")))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)
        
        # Service name field
        layout.addWidget(QLabel(_("Service Name:")))
        self.service_edit = QLineEdit()
        layout.addWidget(self.service_edit)
        
        # App identifier field
        layout.addWidget(QLabel(_("App Identifier:")))
        self.identifier_edit = QLineEdit()
        layout.addWidget(self.identifier_edit)
        
        # Cache location field
        location_layout = QHBoxLayout()
        layout.addWidget(QLabel(_("Cache Location:")))
        self.location_edit = QLineEdit()
        location_layout.addWidget(self.location_edit)
        browse_btn = QPushButton(_("Browse..."))
        browse_btn.clicked.connect(self.browse_cache_location)
        location_layout.addWidget(browse_btn)
        layout.addLayout(location_layout)
        
        # Encryption strategy field
        layout.addWidget(QLabel(_("Encryption Strategy:")))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem(_("Unknown"), EncryptionStrategy.UNKNOWN.value)
        self.strategy_combo.addItem(_("None"), EncryptionStrategy.NONE.value)
        self.strategy_combo.addItem(_("Standard"), EncryptionStrategy.STANDARD.value)
        self.strategy_combo.addItem(_("OQS (Quantum)"), EncryptionStrategy.OQS.value)
        layout.addWidget(self.strategy_combo)
        
        # Buttons
        button_layout = QHBoxLayout()
        ok_btn = QPushButton(_("OK"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(_("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Populate fields if editing
        if app_data:
            self.name_edit.setText(app_data.get('name', ''))
            self.service_edit.setText(app_data.get('service_name', ''))
            self.identifier_edit.setText(app_data.get('app_identifier', ''))
            self.location_edit.setText(app_data.get('cache_location', ''))
            # Set encryption strategy
            encryption_strategy = app_data.get('encryption_strategy', EncryptionStrategy.NONE.value)
            index = self.strategy_combo.findData(encryption_strategy)
            if index >= 0:
                self.strategy_combo.setCurrentIndex(index)
    
    def browse_cache_location(self):
        """Open file dialog to select cache location"""
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            _("Select Cache File"),
            "",
            _("Encrypted Files (*.enc);;All Files (*)")
        )
        if filename:
            # Normalize path to use platform-appropriate separators
            normalized_path = os.path.normpath(filename)
            self.location_edit.setText(normalized_path)
    
    def get_data(self):
        """Get the entered application data"""
        return {
            'name': self.name_edit.text(),
            'service_name': self.service_edit.text(),
            'app_identifier': self.identifier_edit.text(),
            'cache_location': self.location_edit.text(),
            'encryption_strategy': self.strategy_combo.currentData()
        }


class CacheManagerWindow(QMainWindow):
    """Main window for cache manager"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(_("Cache Manager"))
        self.setGeometry(100, 100, 1200, 600)
        self._sort_column = None
        self._sort_order = Qt.AscendingOrder
        
        self.config_manager = ConfigManager()
        self.backup_manager = CacheBackupManager()
        self.backup_manager.set_external_backup_dir(self.config_manager.get_external_backup_dir())
        
        # Setup UI
        self.setup_ui()
        
        # Load applications
        self.refresh_applications()
        
        # Auto-refresh every 5 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_applications)
        self.refresh_timer.start(5000)
    
    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        
        # Application list header row
        header_layout = QHBoxLayout()
        apps_label = QLabel(_("Applications:"))
        header_layout.addWidget(apps_label)
        header_layout.addStretch()

        self.backup_dir_label = QLabel()
        header_layout.addWidget(self.backup_dir_label)

        open_backup_folder_btn = QPushButton(_("Open Backup Folder"))
        open_backup_folder_btn.clicked.connect(self.open_backup_folder)
        header_layout.addWidget(open_backup_folder_btn)

        set_external_backup_btn = QPushButton(_("Set External Backup Path"))
        set_external_backup_btn.clicked.connect(self.set_external_backup_folder)
        header_layout.addWidget(set_external_backup_btn)

        import_recovery_bundle_btn = QPushButton(_("Import Recovery Bundle"))
        import_recovery_bundle_btn.clicked.connect(self.import_recovery_bundle)
        header_layout.addWidget(import_recovery_bundle_btn)

        reset_recovery_password_btn = QPushButton(_("Reset Recovery Password"))
        reset_recovery_password_btn.clicked.connect(self.reset_recovery_passphrase)
        header_layout.addWidget(reset_recovery_password_btn)

        self._update_backup_folder_label()
        layout.addLayout(header_layout)
        
        self.apps_table = QTableWidget()
        self.apps_table.setColumnCount(8)
        self.apps_table.setHorizontalHeaderLabels([
            _("Application"),
            _("Cache Location"),
            _("Cache Updated"),
            _("Last Accessed"),
            _("Last Backup"),
            _("Alert"),
            _("Size"),
            _("Encryption"),
        ])
        self.apps_table.horizontalHeader().setStretchLastSection(True)
        self.apps_table.horizontalHeader().setSortIndicatorShown(True)
        self.apps_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.apps_table.cellDoubleClicked.connect(self.on_app_double_clicked)
        self.apps_table.horizontalHeader().sectionClicked.connect(self.on_table_header_clicked)
        layout.addWidget(self.apps_table)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Action buttons
        self.backup_btn = QPushButton(_("Create Backup"))
        self.backup_btn.clicked.connect(self.create_backup)
        self.backup_btn.setEnabled(False)
        button_layout.addWidget(self.backup_btn)
        
        # TODO: Implement buttons (disabled for now)
        inspect_btn = QPushButton(_("Inspect"))
        inspect_btn.setEnabled(False)
        inspect_btn.setToolTip(_("TODO: Implement cache inspection"))
        button_layout.addWidget(inspect_btn)
        
        modify_btn = QPushButton(_("Modify"))
        modify_btn.setEnabled(False)  # TODO: Implement cache modification
        modify_btn.setToolTip(_("TODO: Implement cache property modification"))
        button_layout.addWidget(modify_btn)
        
        migrate_btn = QPushButton(_("Migrate"))
        migrate_btn.setEnabled(False)  # TODO: Implement cache migration
        migrate_btn.setToolTip(_("TODO: Implement cache migration to switch encryption keys and strategy"))
        button_layout.addWidget(migrate_btn)
        
        button_layout.addStretch()
        
        # Management buttons
        add_btn = QPushButton(_("Add Application"))
        add_btn.clicked.connect(self.add_application)
        button_layout.addWidget(add_btn)
        
        edit_btn = QPushButton(_("Edit Application"))
        edit_btn.clicked.connect(self.edit_application)
        button_layout.addWidget(edit_btn)
        
        remove_btn = QPushButton(_("Remove Application"))
        remove_btn.clicked.connect(self.remove_application)
        button_layout.addWidget(remove_btn)
        
        refresh_btn = QPushButton(_("Refresh"))
        refresh_btn.clicked.connect(self.refresh_applications)
        button_layout.addWidget(refresh_btn)
        
        layout.addLayout(button_layout)
        
        central_widget.setLayout(layout)
    
    def refresh_applications(self):
        """Refresh the applications list from disk and update the table."""
        apps = self.config_manager.get_applications()
        rows = []
        now = datetime.now()

        for app_index, app in enumerate(apps):
            cache_updated = self.get_cache_last_modified(app['cache_location'])
            if cache_updated:
                cache_updated_text = cache_updated.strftime("%Y-%m-%d %H:%M")
                cache_age_seconds = (now - cache_updated).total_seconds()
            else:
                cache_updated_text = _("Not found")
                cache_age_seconds = float("inf")

            last_accessed = self.get_cache_last_accessed(app['cache_location'])
            if last_accessed:
                last_accessed_text = last_accessed.strftime("%Y-%m-%d %H:%M")
            else:
                last_accessed_text = _("Not found")

            last_backup = self.backup_manager.get_last_backup_time(app['name'])
            if last_backup:
                backup_text = last_backup.strftime("%Y-%m-%d %H:%M")
                # "Never" should be treated as oldest, so it sorts before dated backups in ascending order.
                last_backup_key = last_backup.timestamp()
            else:
                backup_text = _("Never")
                last_backup_key = float("-inf")

            stale_backup_alert = bool(last_backup and (now - last_backup) > timedelta(days=30))

            cache_size = self.get_cache_size(app['cache_location'])

            encryption_strategy = app.get('encryption_strategy', EncryptionStrategy.UNKNOWN.value)
            strategy_enum = EncryptionStrategy.from_string(encryption_strategy)
            strategy_display = strategy_enum.display_value(_)

            rows.append({
                "app_index": app_index,
                "app": app,
                "cache_updated": cache_updated,
                "cache_updated_text": cache_updated_text,
                "last_accessed": last_accessed,
                "last_accessed_text": last_accessed_text,
                "last_backup": last_backup,
                "backup_text": backup_text,
                "cache_age_seconds": cache_age_seconds,
                "last_backup_key": last_backup_key,
                "stale_backup_alert": stale_backup_alert,
                "cache_size": cache_size,
                "strategy_display": strategy_display,
            })

        # Default sort: last backup ascending, then cache age ascending.
        if self._sort_column is None:
            rows.sort(key=lambda r: (r["last_backup_key"], r["cache_age_seconds"]))
            self.apps_table.horizontalHeader().setSortIndicator(4, Qt.AscendingOrder)
        else:
            reverse = self._sort_order == Qt.DescendingOrder
            rows = self._sort_rows(rows, self._sort_column, reverse)
            self.apps_table.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)

        self.apps_table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            app = row["app"]
            # Application name
            name_item = QTableWidgetItem(app['name'])
            name_item.setData(Qt.UserRole, row["app_index"])
            self.apps_table.setItem(i, 0, name_item)
            
            # Cache location
            location_item = QTableWidgetItem(app['cache_location'])
            location_item.setToolTip(app['cache_location'])
            self.apps_table.setItem(i, 1, location_item)
            
            # Cache updated (most recent mtime of project cache: .enc or .json)
            self.apps_table.setItem(i, 2, QTableWidgetItem(row["cache_updated_text"]))
            
            # Last accessed (most recent atime of project cache: .enc or .json)
            self.apps_table.setItem(i, 3, QTableWidgetItem(row["last_accessed_text"]))
            
            # Last backup
            self.apps_table.setItem(i, 4, QTableWidgetItem(row["backup_text"]))

            # Alert when last backup is older than 30 days
            alert_item = QTableWidgetItem("❗" if row["stale_backup_alert"] else "")
            alert_item.setTextAlignment(Qt.AlignCenter)
            self.apps_table.setItem(i, 5, alert_item)
            
            # Cache size
            self.apps_table.setItem(i, 6, QTableWidgetItem(row["cache_size"]))
            
            # Encryption strategy
            self.apps_table.setItem(i, 7, QTableWidgetItem(row["strategy_display"]))
        
        self.apps_table.resizeColumnsToContents()
        
        # Enable/disable backup button based on selection
        self.backup_btn.setEnabled(len(self.apps_table.selectedItems()) > 0)

    def _sort_rows(self, rows, column, reverse=False):
        """Sort precomputed table rows for user-selected column/order."""
        if column == 0:
            key_fn = lambda r: r["app"]["name"].lower()
        elif column == 1:
            key_fn = lambda r: r["app"]["cache_location"].lower()
        elif column == 2:
            key_fn = lambda r: r["cache_updated"] or datetime.min
        elif column == 3:
            key_fn = lambda r: r["last_accessed"] or datetime.min
        elif column == 4:
            key_fn = lambda r: r["last_backup"] or datetime.min
        elif column == 5:
            key_fn = lambda r: r["stale_backup_alert"]
        elif column == 6:
            key_fn = lambda r: r["cache_size"]
        elif column == 7:
            key_fn = lambda r: r["strategy_display"].lower()
        else:
            key_fn = lambda r: r["app"]["name"].lower()
        return sorted(rows, key=key_fn, reverse=reverse)

    def on_table_header_clicked(self, column):
        """Allow user to override sort by clicking table headers."""
        if self._sort_column == column:
            self._sort_order = Qt.DescendingOrder if self._sort_order == Qt.AscendingOrder else Qt.AscendingOrder
        else:
            self._sort_column = column
            self._sort_order = Qt.AscendingOrder
        self.refresh_applications()

    def open_backup_folder(self):
        """Open the backup folder in the platform file manager."""
        try:
            self.backup_manager.open_effective_backup_dir()
        except Exception as e:
            QMessageBox.warning(
                self,
                _("Unable to Open Backup Folder"),
                _("Failed to open backup folder: {0}").format(str(e)),
            )

    def set_external_backup_folder(self):
        """Prompt user for external backup folder and persist it."""
        current_path = self.backup_manager.get_external_backup_dir() or ""
        selected_path = QFileDialog.getExistingDirectory(
            self,
            _("Select External Backup Folder"),
            current_path
        )
        if not selected_path:
            return
        selected_path = os.path.abspath(os.path.normpath(selected_path))
        self.config_manager.set_external_backup_dir(selected_path)
        self.backup_manager.set_external_backup_dir(selected_path)
        self._update_backup_folder_label()
        QMessageBox.information(
            self,
            _("External Backup Path Updated"),
            _("External backup path set to:\n{0}").format(selected_path)
        )

    def _update_backup_folder_label(self):
        """Show active backup location (external preferred)."""
        effective_path = self.backup_manager.get_effective_backup_dir()
        self.backup_dir_label.setText(_("Backup Folder: {0}").format(effective_path))
        self.backup_dir_label.setToolTip(effective_path)

    def _get_selected_config_indices(self):
        """Map selected table rows to ConfigManager application indices."""
        selected_indices = set()
        for item in self.apps_table.selectedItems():
            row = item.row()
            name_item = self.apps_table.item(row, 0)
            if name_item is None:
                continue
            app_index = name_item.data(Qt.UserRole)
            if isinstance(app_index, int):
                selected_indices.add(app_index)
        return selected_indices
    
    def _get_cache_paths(self, cache_location):
        """Yield paths to check for cache file(s): the configured path and, if .enc, also app_info_cache.json in same dir."""
        if Utils.isfile_with_retry(cache_location):
            yield cache_location
        if cache_location.endswith(".enc"):
            json_path = os.path.join(os.path.dirname(cache_location), "app_info_cache.json")
            if Utils.isfile_with_retry(json_path):
                yield json_path

    def get_cache_last_modified(self, cache_location):
        """Return the most recent modification time (mtime) of the project cache file(s).
        Checks the configured path and, if it looks like app_info_cache.enc,
        also app_info_cache.json in the same directory.
        Returns datetime or None if no file exists.
        """
        times = []
        for path in self._get_cache_paths(cache_location):
            try:
                times.append(datetime.fromtimestamp(os.path.getmtime(path)))
            except (OSError, ValueError):
                pass
        return max(times) if times else None

    def get_cache_last_accessed(self, cache_location):
        """Return the most recent access time (atime) of the project cache file(s).
        Checks the configured path and, if it looks like app_info_cache.enc,
        also app_info_cache.json in the same directory.
        Returns datetime or None if no file exists.
        """
        times = []
        for path in self._get_cache_paths(cache_location):
            try:
                times.append(datetime.fromtimestamp(os.path.getatime(path)))
            except (OSError, ValueError):
                pass
        return max(times) if times else None

    def get_cache_size(self, cache_location):
        """Get human-readable cache file size"""
        try:
            if not Utils.isfile_with_retry(cache_location):
                return _("Not found")
            
            size_bytes = os.path.getsize(cache_location)
            
            # Convert to human-readable format
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size_bytes < 1024.0:
                    return f"{size_bytes:.2f} {unit}"
                size_bytes /= 1024.0
            
            return f"{size_bytes:.2f} TB"
        except Exception as e:
            return _("Error")
    
    def create_backup(self):
        """Create a backup for the selected application"""
        selected_rows = self._get_selected_config_indices()
        
        if not selected_rows:
            QMessageBox.warning(self, _("No Selection"), _("Please select an application to backup."))
            return

        recovery_passphrase = self._ensure_recovery_passphrase()
        if not recovery_passphrase:
            QMessageBox.warning(
                self,
                _("Recovery Passphrase Required"),
                _("A recovery passphrase is required before backups can proceed.")
            )
            return
        
        for row in selected_rows:
            app = self.config_manager.get_applications()[row]
            
            backup_path = self.backup_manager.create_backup(
                app['name'],
                app['cache_location'],
                app['service_name'],
                app['app_identifier']
            )
            
            if backup_path:
                backup_targets = "\n".join(self.backup_manager.list_backup_targets())
                QMessageBox.information(
                    self,
                    _("Backup Successful"),
                    _("Backup created for: {0}\n\nWritten to:\n{1}").format(app['name'], backup_targets)
                )
            else:
                QMessageBox.warning(
                    self,
                    _("Backup Failed"),
                    _("Failed to create backup for: {}\n\nMake sure the cache file exists and is accessible.").format(app['name'])
                )

        self._refresh_recovery_bundle_after_backup(recovery_passphrase)
        
        self.refresh_applications()

    def _ensure_recovery_passphrase(self):
        """Get or prompt for recovery bundle passphrase and persist if newly set."""
        saved = RecoveryBundleManager.get_saved_passphrase()
        if saved:
            return saved

        passphrase, ok = QInputDialog.getText(
            self,
            _("Set Recovery Passphrase"),
            _("Create a passphrase for encrypted recovery bundles:"),
            QLineEdit.Password,
        )
        if not ok or not passphrase:
            return None

        confirm, ok_confirm = QInputDialog.getText(
            self,
            _("Confirm Recovery Passphrase"),
            _("Re-enter recovery passphrase:"),
            QLineEdit.Password,
        )
        if not ok_confirm or passphrase != confirm:
            QMessageBox.warning(self, _("Passphrase Mismatch"), _("Recovery passphrase confirmation did not match."))
            return None

        RecoveryBundleManager.set_saved_passphrase(passphrase)
        return passphrase

    def _refresh_recovery_bundle_after_backup(self, recovery_passphrase):
        """Re-export the encrypted recovery bundle after backup operations."""
        try:
            effective_backup_dir = self.backup_manager.get_effective_backup_dir()
            bundle_path = RecoveryBundleManager.get_default_bundle_path(effective_backup_dir)
            result = RecoveryBundleManager.export_bundle(
                applications=self.config_manager.get_applications(),
                bundle_path=bundle_path,
                recovery_passphrase=recovery_passphrase,
            )
            if result.get("error_count", 0) > 0:
                logger.warning(
                    _("Recovery bundle export completed with errors: {0}").format("; ".join(result.get("errors", [])))
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                _("Recovery Bundle Export Failed"),
                _("Backups were created, but recovery bundle export failed:\n{0}").format(str(e)),
            )

    def reset_recovery_passphrase(self):
        """Reset saved recovery passphrase and immediately re-export recovery bundle."""
        new_passphrase, ok = QInputDialog.getText(
            self,
            _("Reset Recovery Passphrase"),
            _("Enter new recovery passphrase:"),
            QLineEdit.Password,
        )
        if not ok or not new_passphrase:
            return

        confirm_passphrase, ok_confirm = QInputDialog.getText(
            self,
            _("Confirm New Recovery Passphrase"),
            _("Re-enter new recovery passphrase:"),
            QLineEdit.Password,
        )
        if not ok_confirm or new_passphrase != confirm_passphrase:
            QMessageBox.warning(self, _("Passphrase Mismatch"), _("Recovery passphrase confirmation did not match."))
            return

        try:
            RecoveryBundleManager.set_saved_passphrase(new_passphrase)
            self._refresh_recovery_bundle_after_backup(new_passphrase)
            QMessageBox.information(
                self,
                _("Recovery Passphrase Reset"),
                _("Recovery passphrase was updated and recovery bundle was re-exported."),
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                _("Recovery Passphrase Reset Failed"),
                _("Failed to reset recovery passphrase:\n{0}").format(str(e)),
            )

    def import_recovery_bundle(self):
        """Import a recovery bundle from disk and rehydrate key material."""
        initial_dir = self.backup_manager.get_effective_backup_dir()
        bundle_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            _("Select Recovery Bundle"),
            initial_dir,
            _("Encrypted Bundle (*.enc);;All Files (*)")
        )
        if not bundle_path:
            return

        passphrase, ok = QInputDialog.getText(
            self,
            _("Recovery Bundle Passphrase"),
            _("Enter passphrase for this recovery bundle:"),
            QLineEdit.Password,
        )
        if not ok or not passphrase:
            return

        overwrite = QMessageBox.question(
            self,
            _("Overwrite Existing Keys?"),
            _("Overwrite existing key material for matching apps?"),
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes

        try:
            result = RecoveryBundleManager.import_bundle(
                bundle_path=bundle_path,
                recovery_passphrase=passphrase,
                overwrite_existing=overwrite,
            )
            QMessageBox.information(
                self,
                _("Recovery Bundle Import Complete"),
                _(
                    "Imported: {0}\nSkipped: {1}\nFailed: {2}"
                ).format(result["imported_count"], result["skipped_count"], result["failed_count"]),
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                _("Recovery Bundle Import Failed"),
                _("Failed to import recovery bundle:\n{0}").format(str(e)),
            )
    
    def add_application(self):
        """Add a new application"""
        dialog = AddEditApplicationDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            
            # Validate
            if not all(data.values()):
                QMessageBox.warning(self, _("Invalid Input"), _("All fields are required."))
                return
            
            self.config_manager.add_application(
                data['name'],
                data['service_name'],
                data['app_identifier'],
                data['cache_location'],
                data.get('encryption_strategy')
            )
            self.refresh_applications()
    
    def edit_application(self):
        """Edit the selected application"""
        selected_rows = self._get_selected_config_indices()
        
        if not selected_rows:
            QMessageBox.warning(self, _("No Selection"), _("Please select an application to edit."))
            return
        
        row = list(selected_rows)[0]
        app_data = self.config_manager.get_applications()[row]
        
        dialog = AddEditApplicationDialog(self, app_data)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            
            # Validate
            if not all(data.values()):
                QMessageBox.warning(self, _("Invalid Input"), _("All fields are required."))
                return
            
            self.config_manager.update_application(
                row,
                data['name'],
                data['service_name'],
                data['app_identifier'],
                data['cache_location'],
                data.get('encryption_strategy')
            )
            self.refresh_applications()
    
    def remove_application(self):
        """Remove the selected application"""
        selected_rows = self._get_selected_config_indices()
        
        if not selected_rows:
            QMessageBox.warning(self, _("No Selection"), _("Please select an application to remove."))
            return
        
        reply = QMessageBox.question(
            self,
            _("Confirm Removal"),
            _("Are you sure you want to remove the selected application?"),
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remove in reverse order to maintain indices
            for row in sorted(selected_rows, reverse=True):
                self.config_manager.remove_application(row)
            
            self.refresh_applications()
    
    def on_app_double_clicked(self, row, column):
        """Handle double-click on application row"""
        self.create_backup()


def main():
    app = QApplication(sys.argv)
    
    window = CacheManagerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

