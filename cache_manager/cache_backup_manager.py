import json
import os
import shutil
from datetime import datetime
from typing import Optional
from pathlib import Path

from utils.encryptor import decrypt_data_from_file
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class CacheBackupManager:
    def __init__(self):
        self.backup_dir = "backups"
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self, app_name: str, cache_location: str, service_name: str, app_identifier: str) -> Optional[str]:
        """
        Create a manual backup of the cache file (outside normal rotation).
        
        Returns:
            Path to the backup file if successful, None otherwise
        """
        if not os.path.exists(cache_location):
            return None
        
        try:
            # Create timestamp for backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{app_name}_{timestamp}.enc"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Copy the cache file
            shutil.copy2(cache_location, backup_path)
            
            # Verify the backup was successful by attempting to decrypt
            try:
                decrypt_data_from_file(backup_path, service_name, app_identifier)
            except Exception as e:
                # Only delete the failed backup file, never touch the original cache
                logger.warning(_("Backup verification failed: {0}. Removing failed backup file.".format(str(e))))
                os.remove(backup_path)
                return None
            
            # Store metadata about this backup
            self._save_backup_metadata(app_name, backup_path)
            
            return backup_path
        except Exception as e:
            logger.error(_("Error creating backup: {}".format(str(e))))
            return None
    
    def _save_backup_metadata(self, app_name: str, backup_path: str):
        """Save metadata about when the backup was created"""
        metadata_file = os.path.join(self.backup_dir, f"{app_name}_backups.json")
        
        if os.path.exists(metadata_file):
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
        metadata_file = os.path.join(self.backup_dir, f"{app_name}_backups.json")
        
        if not os.path.exists(metadata_file):
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
        metadata_file = os.path.join(self.backup_dir, f"{app_name}_backups.json")
        
        if not os.path.exists(metadata_file):
            return []
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            return metadata.get('backups', [])
        except Exception as e:
            logger.error(_("Error reading backup metadata: {}".format(str(e))))
            return []

