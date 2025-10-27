import json
import os
from typing import List, Dict

from utils.encryptor import encrypt_data_to_file, decrypt_data_from_file
from utils.encryptor import KeyEncapsulation
from utils.encryption_strategy import EncryptionStrategy
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._

# Service and app identifiers for this cache manager application
SERVICE_NAME = "MyPersonalApplicationsService"
APP_IDENTIFIER = "cache_manager"


class AppInfoCache:
    CACHE_LOC = os.path.join(os.path.dirname(os.path.abspath(os.path.dirname(__file__))), "app_info_cache.enc")
    
    def __init__(self):
        self._cache = {'applications': []}
        self.load()
        self._add_self_to_cache()
    
    def store(self):
        """Store the cache to encrypted file"""
        try:
            cache_data = json.dumps(self._cache).encode('utf-8')
            encrypt_data_to_file(
                cache_data,
                SERVICE_NAME,
                APP_IDENTIFIER,
                self.CACHE_LOC
            )
        except Exception as e:
            logger.error(_("Error storing cache: {}".format(str(e))))
            raise e
    
    def load(self):
        """Load the cache from encrypted file"""
        try:
            if os.path.exists(self.CACHE_LOC):
                encrypted_data = decrypt_data_from_file(
                    self.CACHE_LOC,
                    SERVICE_NAME,
                    APP_IDENTIFIER
                )
                self._cache = json.loads(encrypted_data.decode('utf-8'))
            else:
                # First run - create empty cache
                self._cache = {'applications': []}
        except Exception as e:
            logger.error(_("Error loading cache: {}".format(str(e))))
            # If decryption fails, start with empty cache
            self._cache = {'applications': []}
    
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
            if app.get('service_name') == SERVICE_NAME and app.get('app_identifier') == APP_IDENTIFIER:
                return  # Already exists
        
        # Add this cache manager to the list
        # Determine encryption strategy based on OQS availability
        if KeyEncapsulation is not None:
            strategy = EncryptionStrategy.OQS.value
        else:
            strategy = EncryptionStrategy.STANDARD.value
        
        self._cache['applications'].append({
            'name': 'Cache Manager',
            'service_name': SERVICE_NAME,
            'app_identifier': APP_IDENTIFIER,
            'cache_location': self.CACHE_LOC,
            'encryption_strategy': strategy
        })
        self.store()


# Global instance
app_info_cache = AppInfoCache()

