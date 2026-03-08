import json
import os
import shutil
from datetime import datetime
from typing import Optional

from utils.encryptor import decrypt_data_from_file
from utils.logging_setup import get_logger
from utils.translations import I18N
from utils.utils import Utils

logger = get_logger(__name__)
_ = I18N._


def sanitize_filename(name: str) -> str:
    """Convert application name to a filesystem-friendly filename"""
    # Convert to lowercase, replace spaces with underscores
    return name.lower().replace(' ', '_')


class CacheBackupManager:
    def __init__(self, max_backups_per_app: int = 10):
        self.backup_dir = "backups"
        self.external_backup_dir = None
        self.max_backups_per_app = max_backups_per_app
        os.makedirs(self.backup_dir, exist_ok=True)

    def set_external_backup_dir(self, external_backup_dir: Optional[str]):
        """Set optional external backup directory."""
        if external_backup_dir:
            self.external_backup_dir = os.path.abspath(external_backup_dir)
            os.makedirs(self.external_backup_dir, exist_ok=True)
        else:
            self.external_backup_dir = None
    
    def create_backup(self, app_name: str, cache_location: str, service_name: str, app_identifier: str) -> Optional[str]:
        """
        Create a manual backup of the cache file (outside normal rotation).
        
        Returns:
            Path to the backup file if successful, None otherwise
        """
        if not Utils.isfile_with_retry(cache_location):
            return None
        
        try:
            # Create timestamp for backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = sanitize_filename(app_name)
            backup_filename = f"{safe_name}_{timestamp}.enc"
            local_backup_path = os.path.join(self.backup_dir, backup_filename)
            external_backup_path = None

            self._copy_and_verify_backup(
                cache_location=cache_location,
                backup_path=local_backup_path,
                service_name=service_name,
                app_identifier=app_identifier,
            )

            if self.external_backup_dir:
                external_backup_path = os.path.join(self.external_backup_dir, backup_filename)
                self._copy_and_verify_backup(
                    cache_location=cache_location,
                    backup_path=external_backup_path,
                    service_name=service_name,
                    app_identifier=app_identifier,
                )

            # Only persist metadata when all configured backup targets succeeded.
            self._save_backup_metadata(app_name, local_backup_path)

            # Clean up old backups if we exceed the limit
            self._cleanup_old_backups(app_name)
            
            return local_backup_path
        except Exception as e:
            logger.error(_("Error creating backup: {}".format(str(e))))
            return None

    def _copy_and_verify_backup(self, cache_location: str, backup_path: str, service_name: str, app_identifier: str):
        """Copy cache to backup_path and verify decryptability."""
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(cache_location, backup_path)

        try:
            decrypt_data_from_file(backup_path, service_name, app_identifier)
        except Exception as e:
            logger.warning(_("Backup verification failed: {0}. Removing failed backup file.".format(str(e))))
            if Utils.isfile_with_retry(backup_path):
                os.remove(backup_path)
            raise

    def get_latest_backup_path(self, app_name: str) -> Optional[str]:
        """Get the newest local backup path for an application."""
        backups = self.list_backups(app_name)
        if not backups:
            return None
        latest_backup = max(backups, key=lambda b: b.get("timestamp", ""))
        return latest_backup.get("path")

    def get_effective_backup_dir(self) -> str:
        """Get user-facing backup directory (external if configured, else local)."""
        if self.external_backup_dir:
            return self.external_backup_dir
        return os.path.abspath(self.backup_dir)

    def open_effective_backup_dir(self):
        """Open user-facing backup directory in file manager."""
        backup_dir = self.get_effective_backup_dir()
        os.makedirs(backup_dir, exist_ok=True)
        Utils.open_file(backup_dir)

    def get_external_backup_dir(self) -> Optional[str]:
        return self.external_backup_dir

    def list_backup_targets(self) -> list:
        """Return all active backup targets (local always, external optionally)."""
        targets = [os.path.abspath(self.backup_dir)]
        if self.external_backup_dir:
            targets.append(self.external_backup_dir)
        return targets

    def get_latest_backup_message_suffix(self) -> str:
        """Return text describing active backup destinations for UI messaging."""
        targets = self.list_backup_targets()
        if len(targets) == 1:
            return targets[0]
        return "\n".join(targets)
    
    def _save_backup_metadata(self, app_name: str, backup_path: str):
        """Save metadata about when the backup was created"""
        safe_name = sanitize_filename(app_name)
        metadata_file = os.path.join(self.backup_dir, f"{safe_name}_backups.json")
        
        if Utils.isfile_with_retry(metadata_file):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {'backups': []}
        
        metadata['backups'].append({
            'path': backup_path,
            'timestamp': datetime.now().isoformat()
        })
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def get_last_backup_time(self, app_name: str) -> Optional[datetime]:
        """Get the timestamp of the last backup for an application"""
        safe_name = sanitize_filename(app_name)
        metadata_file = os.path.join(self.backup_dir, f"{safe_name}_backups.json")
        
        if not Utils.isfile_with_retry(metadata_file):
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            backups = metadata.get('backups', [])
            if not backups:
                return None
            
            last_backup = backups[-1]
            return datetime.fromisoformat(last_backup['timestamp'])
        except Exception as e:
            logger.error(_("Error reading backup metadata: {}".format(str(e))))
            return None
    
    def list_backups(self, app_name: str) -> list:
        """List all backups for an application"""
        safe_name = sanitize_filename(app_name)
        metadata_file = os.path.join(self.backup_dir, f"{safe_name}_backups.json")
        
        if not Utils.isfile_with_retry(metadata_file):
            return []
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            return metadata.get('backups', [])
        except Exception as e:
            logger.error(_("Error reading backup metadata: {}".format(str(e))))
            return []
    
    def _cleanup_old_backups(self, app_name: str):
        """Remove old backups if we exceed the maximum count"""
        backups = self.list_backups(app_name)
        
        if len(backups) <= self.max_backups_per_app:
            return
        
        # Sort backups by timestamp (oldest first)
        backups_sorted = sorted(backups, key=lambda x: x['timestamp'])
        
        # Keep only the most recent backups
        backups_to_keep = backups_sorted[-self.max_backups_per_app:]
        backups_to_remove = backups_sorted[:-self.max_backups_per_app]
        
        # Remove old backup files
        for backup in backups_to_remove:
            backup_path = backup.get('path')
            if backup_path and Utils.isfile_with_retry(backup_path):
                try:
                    os.remove(backup_path)
                    logger.info(_("Removed old backup: {}".format(backup_path)))
                except Exception as e:
                    logger.error(_("Error removing old backup: {}".format(str(e))))
        
        # Update metadata file to reflect only the kept backups
        safe_name = sanitize_filename(app_name)
        metadata_file = os.path.join(self.backup_dir, f"{safe_name}_backups.json")
        
        try:
            metadata = {'backups': backups_to_keep}
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(_("Error updating backup metadata: {}".format(str(e))))

