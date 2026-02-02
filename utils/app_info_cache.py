import json
import os
import shutil
from typing import List, Dict

from utils.globals import AppInfo
from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file
from utils.encryptor import KeyEncapsulation
from utils.encryption_strategy import EncryptionStrategy
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._



class AppInfoCache:
    CACHE_LOC = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "app_info_cache.enc")
    JSON_LOC = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "app_info_cache.json")
    NUM_BACKUPS = 4  # Number of backup files to maintain

    def __init__(self):
        self._cache = {'applications': []}
        self.load()
        self.validate()
        self._add_self_to_cache()
    
    def store(self):
        """Persist cache to encrypted file. Returns True on success, False if encrypted store failed but JSON fallback succeeded. Raises on encoding or JSON fallback failure."""
        try:
            cache_data = json.dumps(self._cache).encode('utf-8')
        except Exception as e:
            raise Exception(_("Error compiling application cache: {}").format(e))

        try:
            encrypt_data_to_file(
                cache_data,
                AppInfo.SERVICE_NAME,
                AppInfo.APP_IDENTIFIER,
                self.CACHE_LOC
            )
            return True  # Encryption successful
        except Exception as e:
            logger.error(_("Error encrypting cache: {}").format(e))

        try:
            with open(self.JSON_LOC, "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
            return False  # Encryption failed, but JSON fallback succeeded
        except Exception as e:
            raise Exception(_("Error storing application cache: {}").format(e))
    
    def _try_load_cache_from_file(self, path):
        """Attempt to load and decrypt the cache from the given file path. Raises on failure."""
        encrypted_data = decrypt_data_from_file(
            path,
            AppInfo.SERVICE_NAME,
            AppInfo.APP_IDENTIFIER
        )
        return json.loads(encrypted_data.decode('utf-8'))

    def load(self):
        """Load the cache from encrypted file"""
        try:
            if os.path.exists(self.JSON_LOC):
                logger.info(_("Detected JSON-format application cache, will attempt migration to encrypted store"))
                with open(self.JSON_LOC, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                if self.store():
                    logger.info(_("Migrated application cache from {} to encrypted store").format(self.JSON_LOC))
                    os.remove(self.JSON_LOC)
                else:
                    logger.warning(_("Encrypted store of application cache failed; keeping JSON cache file"))
                return

            # Try encrypted cache and backups in order
            cache_paths = [self.CACHE_LOC] + self._get_backup_paths()
            any_exist = any(os.path.exists(path) for path in cache_paths)
            if not any_exist:
                logger.info(f"No cache file found at {AppInfoCache.CACHE_LOC}, creating new cache")
                return

            for path in cache_paths:
                if os.path.exists(path):
                    try:
                        self._cache = self._try_load_cache_from_file(path)
                        # Only shift backups if we loaded from the main file
                        if path == self.CACHE_LOC:
                            message = f"Loaded cache from {self.CACHE_LOC}"
                            rotated_count = self._rotate_backups()
                            if rotated_count > 0:
                                message += f", rotated {rotated_count} backups"
                            logger.info(message)
                        else:
                            logger.warning(f"Loaded cache from backup: {path}")
                        return
                    except Exception as e:
                        logger.error(f"Failed to load cache from {path}: {e}")
                        continue
            # If we get here, all attempts failed (but at least one file existed)
            raise Exception(f"Failed to load cache from all locations: {cache_paths}")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(_("Error loading cache: {}".format(str(e))))
            # If decryption fails, start with empty cache
            self._cache = {'applications': []}

    def validate(self):
        pass

    def get_applications(self) -> List[Dict]:
        """Get list of all configured applications"""
        return self._cache.get('applications', [])
    
    def add_application(self, name: str, service_name: str, app_identifier: str, cache_location: str, encryption_strategy: str = None):
        """Add a new application to the configuration"""
        app = {
            'name': name,
            'service_name': service_name,
            'app_identifier': app_identifier,
            'cache_location': cache_location,
            'encryption_strategy': encryption_strategy or EncryptionStrategy.UNKNOWN.value
        }
        if 'applications' not in self._cache:
            self._cache['applications'] = []
        self._cache['applications'].append(app)
        self.store()
    
    def remove_application(self, index: int):
        """Remove an application from the configuration"""
        if 'applications' in self._cache and 0 <= index < len(self._cache['applications']):
            del self._cache['applications'][index]
            self.store()
    
    def update_application(self, index: int, name: str, service_name: str, app_identifier: str, cache_location: str, encryption_strategy: str = None):
        """Update an existing application in the configuration"""
        if 'applications' in self._cache and 0 <= index < len(self._cache['applications']):
            self._cache['applications'][index] = {
                'name': name,
                'service_name': service_name,
                'app_identifier': app_identifier,
                'cache_location': cache_location,
                'encryption_strategy': encryption_strategy or EncryptionStrategy.UNKNOWN.value
            }
            self.store()
    
    def _add_self_to_cache(self):
        """Add this cache manager to its own application list if not already present"""
        if 'applications' not in self._cache:
            self._cache['applications'] = []
        
        # Check if already exists
        for app in self._cache['applications']:
            if app.get('service_name') == AppInfo.SERVICE_NAME and app.get('app_identifier') == AppInfo.APP_IDENTIFIER:
                return  # Already exists
        
        # Add this cache manager to the list
        # Determine encryption strategy based on OQS availability
        if KeyEncapsulation is not None:
            strategy = EncryptionStrategy.OQS.value
        else:
            strategy = EncryptionStrategy.STANDARD.value
        
        self._cache['applications'].append({
            'name': 'Cache Manager',
            'service_name': AppInfo.SERVICE_NAME,
            'app_identifier': AppInfo.APP_IDENTIFIER,
            'cache_location': self.CACHE_LOC,
            'encryption_strategy': strategy
        })
        self.store()

    def _get_backup_paths(self):
        """Get list of backup file paths in order of preference"""
        backup_paths = []
        for i in range(1, self.NUM_BACKUPS + 1):
            index = "" if i == 1 else f"{i}"
            path = f"{self.CACHE_LOC}.bak{index}"
            backup_paths.append(path)
        return backup_paths

    def _rotate_backups(self):
        """Rotate backup files: move each backup to the next position, oldest gets overwritten"""
        backup_paths = self._get_backup_paths()
        rotated_count = 0
        
        # Remove the oldest backup if it exists
        if os.path.exists(backup_paths[-1]):
            os.remove(backup_paths[-1])
        
        # Shift backups: move each backup to the next position
        for i in range(len(backup_paths) - 1, 0, -1):
            if os.path.exists(backup_paths[i - 1]):
                shutil.copy2(backup_paths[i - 1], backup_paths[i])
                rotated_count += 1
        
        # Copy main cache to first backup position
        shutil.copy2(self.CACHE_LOC, backup_paths[0])
        
        return rotated_count


# Global instance
app_info_cache = AppInfoCache()

